"""抓取任务执行器。

单用户本地工具，采用「后台单工作线程 + 内存任务表」的轻量方案：
- `POST /api/rpa/tasks` 创建任务后立即唤醒工作线程；
- 工作线程串行执行（同时只跑一个 RPA 任务，避免多浏览器抢占焦点）；
- 进度 / 日志实时写入 `RPATask` 表，前端可轮询查看。
"""

from __future__ import annotations

import json
import threading
import traceback
from datetime import datetime, timezone

from sqlmodel import Session, select

from database import engine
from models import PlatformAccount, RPATask, StorePlatformExpense
from rpa.browser import NeedManualVerification
from rpa.crypto import decrypt
from rpa.logging_utils import safe_print

_worker: threading.Thread | None = None
_lock = threading.Lock()
_wakeup = threading.Event()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _log(task_id: int, message: str) -> None:
    """追加任务日志（带时间戳）。"""
    stamp = _utcnow().astimezone().strftime("%H:%M:%S")
    line = f"[{stamp}] {message}"
    with Session(engine) as session:
        task = session.get(RPATask, task_id)
        if task is None:
            return
        task.log = (task.log + "\n" + line) if task.log else line
        session.add(task)
        session.commit()
    safe_print(line)


def _set_status(task_id: int, status: str, **fields) -> None:
    with Session(engine) as session:
        task = session.get(RPATask, task_id)
        if task is None:
            return
        task.status = status
        for key, value in fields.items():
            if hasattr(task, key):
                setattr(task, key, value)
        if status in {"success", "failed", "cancelled", "need_verify"}:
            task.finished_at = _utcnow()
        session.add(task)
        session.commit()


def _upsert_expenses(task: RPATask, records: list) -> int:
    """按 (store, month, category, sub_category) 去重写入费用记录。"""
    written = 0
    with Session(engine) as session:
        for rec in records:
            data = rec.as_dict() if hasattr(rec, "as_dict") else rec
            existing = session.exec(
                select(StorePlatformExpense).where(
                    StorePlatformExpense.store == task.store,
                    StorePlatformExpense.period_month == data["month"],
                    StorePlatformExpense.category == data["category"],
                    StorePlatformExpense.sub_category == data["sub_category"],
                )
            ).first()
            if existing is None:
                session.add(
                    StorePlatformExpense(
                        store=task.store,
                        period_month=data["month"],
                        category=data["category"],
                        sub_category=data["sub_category"],
                        amount=float(data["amount"]),
                        source="rpa",
                        rpa_task_id=task.id,
                        note=data.get("note"),
                    )
                )
            else:
                existing.amount = float(data["amount"])
                existing.source = "rpa"
                existing.rpa_task_id = task.id
                existing.note = data.get("note")
                session.add(existing)
            written += 1
        session.commit()
    return written


def _execute(task_id: int) -> None:
    with Session(engine) as session:
        task = session.get(RPATask, task_id)
        if task is None:
            return
        account = session.get(PlatformAccount, task.account_id)
        if account is None:
            _set_status(task_id, "failed", error_message="关联的平台账号不存在")
            return
        platform = task.platform
        datasets = json.loads(task.datasets or "[]")
        store = task.store
        username = account.username
        password = decrypt(account.password_enc) or ""
        label = account.account_label

    _set_status(task_id, "running", started_at=_utcnow(), progress=5)
    _log(task_id, f"开始执行：{label} / {platform} / 数据集 {datasets}")

    from rpa.browser import BrowserSession
    from rpa import alimama, qianniu

    try:
        with BrowserSession(task.account_id, label) as session:
            if platform == "qianniu":
                outcome = qianniu.scrape(session, datasets, username, password, store)
                records, warnings = outcome.records, outcome.warnings
            elif platform == "alimama":
                outcome = alimama.scrape(session, datasets, username, password, store)
                records, warnings = outcome.records, outcome.warnings
            else:
                raise ValueError(f"不支持的平台：{platform}")

            for warning in warnings:
                _log(task_id, f"⚠️ {warning}")

            if not records:
                _set_status(
                    task_id,
                    "failed",
                    progress=100,
                    error_message="未抓取到任何数据，请查看日志与截图",
                )
                return

            _set_status(task_id, "running", progress=80)
            written = _upsert_expenses(task, records)
            _set_status(
                task_id,
                "success",
                progress=100,
                result_summary=json.dumps(
                    {"records_written": written, "warnings": warnings}, ensure_ascii=False
                ),
            )
            _log(task_id, f"完成：写入 {written} 条费用记录")
            if session.screenshots:
                _log(task_id, f"截图 {len(session.screenshots)} 张保存在 {session.screenshots[0]} 所在目录")

    except NeedManualVerification as exc:
        _set_status(task_id, "need_verify", progress=60, error_message=str(exc))
        _log(task_id, f"⏸ 需要人工验证：{exc}")
    except Exception as exc:  # noqa: BLE001
        detail = f"{type(exc).__name__}: {exc}"
        _set_status(task_id, "failed", progress=100, error_message=detail)
        _log(task_id, f"❌ 失败：{detail}")
        _log(task_id, traceback.format_exc(limit=5))


def _worker_loop() -> None:
    while True:
        _wakeup.wait(timeout=30)
        _wakeup.clear()

        try:
            with Session(engine) as session:
                task = session.exec(
                    select(RPATask)
                    .where(RPATask.status == "pending")
                    .order_by(RPATask.id)
                ).first()
                if task is None:
                    continue
                task_id = task.id
        except Exception as exc:  # noqa: BLE001
            safe_print(f"[rpa] 读取待执行任务失败：{exc}")
            continue

        # 先抢占为 running：若 _execute 在写入 running 之前就抛错，任务不会
        # 永远停留在 pending 而被反复重试。
        try:
            _set_status(task_id, "running")
        except Exception as exc:  # noqa: BLE001
            safe_print(f"[rpa] 更新任务状态失败：{exc}")
            continue

        try:
            _execute(task_id)
        except Exception as exc:  # noqa: BLE001 — 保底，保证线程不死
            detail = f"执行器异常：{type(exc).__name__}: {exc}"
            try:
                _set_status(task_id, "failed", progress=100, error_message=detail)
                _log(task_id, traceback.format_exc(limit=8))
            except Exception:  # noqa: BLE001 — 连日志都写不进去也不能让线程死掉
                safe_print(f"[rpa] 记录任务失败信息时出错：{exc}")


def start_worker() -> None:
    """启动后台工作线程（幂等）。"""
    global _worker
    with _lock:
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_worker_loop, name="rpa-worker", daemon=True)
        _worker.start()


def notify_new_task() -> None:
    _wakeup.set()
