"""013-I01：把采集能力开放给前端「商品分析」页。

边界：
- 只做**单商品即时采集**（I05 批量另开）；采集是重操作，全局串行。
- Playwright sync API 不能在事件循环线程跑，统一丢到 `asyncio.to_thread`。
- 采集结果同时落 raw 目录 + 数据库 + preview.html，三者用 run_id 关联。
"""

from __future__ import annotations

import asyncio
import re
import threading
from datetime import date, timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from database import DB_PATH, get_session
from inspection.collect.raw_store import RAW_ROOT
from inspection.models import CORE_FIELDS, ItemSnapshot
from inspection.store import to_display

router = APIRouter(prefix="/inspection", tags=["inspection"])

SessionDep = Annotated[Session, Depends(get_session)]

_ITEM_ID_RE = re.compile(r"^\d{6,20}$")
_RUN_ID_RE = re.compile(r"^[\w.-]{1,80}$")

# 浏览器 profile 同一时间只能被一个进程占用，采集必须串行
_collect_lock = threading.Lock()

# 前端可直接打开的文件（白名单，避免任意文件读取）
_SERVED_FILES = {"preview.html", "shot.png"}

# 采集失败类型 → HTTP 状态与提示
_FAILURE_MAP = {
    "need_login": (401, "登录态失效：请先在本机运行 python inspect_cli.py login 完成扫码登录"),
    "need_verify": (409, "页面出现滑块验证，请在浏览器窗口中手动处理后重试"),
    "item_gone": (404, "商品不存在或已下架"),
    "no_data": (502, "页面未返回商品数据（可能登录态失效或页面改版）"),
}


class CollectRequest(BaseModel):
    item_id: str
    headless: bool = False


def _run_links(run_id: str) -> dict:
    run_dir = RAW_ROOT / run_id
    return {
        "preview_url": f"/api/inspection/runs/{run_id}/preview.html",
        "shot_url": f"/api/inspection/runs/{run_id}/shot.png"
        if (run_dir / "shot.png").exists()
        else None,
    }


def _collect_blocking(item_id: str, headless: bool) -> dict:
    """同步采集：抓页面 → 解析 → 落库 → 断言 → 生成预览。在线程池里执行。"""
    from db_migrate import make_engine
    from inspection.collect.item import CollectError, fetch_item
    from inspection.collect.parser import parse_item
    from inspection.preview import from_parse, render_preview
    from inspection.store import save_assertions, save_snapshot
    from inspection.validate import run_assertions

    run_dir = fetch_item(item_id, headed=not headless)
    data = parse_item(run_dir)

    view = from_parse(data)
    engine = make_engine(DB_PATH)
    db_error = None
    try:
        save_snapshot(engine, data, store=1)
    except Exception as exc:  # noqa: BLE001 — 落库失败不影响本次产物
        db_error = str(exc)

    assertions = run_assertions(view)
    try:
        save_assertions(engine, view["run_id"], assertions["results"], view["item_id"])
    except Exception as exc:  # noqa: BLE001 — 断言落库失败不阻断采集
        db_error = db_error or f"断言未入库：{exc}"

    render_preview(view, run_dir)

    reliable = view.get("field_reliable") or {}
    return {
        "run_id": view["run_id"],
        "reliable": view["reliable"],
        "core_fields": list(CORE_FIELDS),
        "core_missing": [f for f in CORE_FIELDS if not reliable.get(f)],
        "snapshot": view,
        "assertions": assertions,
        "db_error": db_error,
        **_run_links(view["run_id"]),
    }


@router.post("/collect")
async def collect(payload: CollectRequest) -> dict:
    """采集一个商品页。串行执行，单次 30–60 秒，会弹出本机浏览器窗口。"""
    item_id = payload.item_id.strip()
    if not _ITEM_ID_RE.match(item_id):
        raise HTTPException(status_code=422, detail="商品 ID 应为 6–20 位数字")

    if not _collect_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409, detail="已有采集任务在进行（浏览器同一时间只能开一个），请稍候重试"
        )
    try:
        from inspection.collect.item import CollectError

        try:
            return await asyncio.to_thread(_collect_blocking, item_id, payload.headless)
        except CollectError as exc:
            status, detail = _FAILURE_MAP.get(exc.kind, (500, exc.message))
            raise HTTPException(
                status_code=status, detail=f"{detail}（run_id 见 data/raw）"
            ) from exc
    finally:
        _collect_lock.release()


@router.get("/snapshots")
def list_snapshots(
    item_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict:
    """历史采集记录（新到旧）。前端用它做「最近采集」列表。"""
    statement = select(ItemSnapshot)
    if item_id:
        statement = statement.where(ItemSnapshot.item_id == item_id)
    statement = statement.order_by(ItemSnapshot.collected_at.desc()).limit(limit)

    items = []
    for snapshot in session.exec(statement).all():
        data = to_display(snapshot)
        items.append(
            {
                "run_id": data["run_id"],
                "item_id": data["item_id"],
                "title": data["title"],
                "price_cents": data["price_cents"],
                "image_count": data["image_count"],
                "detail_image_count": data["detail_image_count"],
                "reliable": data["reliable"],
                "collected_at": data["collected_at"],
            }
        )
    return {"total": len(items), "items": items}


@router.get("/snapshots/{run_id}")
def get_snapshot(run_id: str, session: SessionDep) -> dict:
    snapshot = session.exec(
        select(ItemSnapshot).where(ItemSnapshot.run_id == run_id)
    ).first()
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"没有 run_id={run_id} 的快照")

    data = to_display(snapshot)
    reliable = data.get("field_reliable") or {}

    # 断言属判定层：每次读都按当前阈值重算，改 rules.json 后刷新即生效
    from inspection.validate import run_assertions

    assertions = run_assertions(data)
    try:
        from db_migrate import make_engine
        from inspection.store import save_assertions

        save_assertions(
            make_engine(DB_PATH), data["run_id"], assertions["results"], data["item_id"]
        )
    except Exception:  # noqa: BLE001 — 落库失败不影响读取
        pass

    return {
        "run_id": data["run_id"],
        "reliable": data["reliable"],
        "core_fields": list(CORE_FIELDS),
        "core_missing": [f for f in CORE_FIELDS if not reliable.get(f)],
        "snapshot": data,
        "assertions": assertions,
        **_run_links(data["run_id"]),
    }


@router.post("/traffic/import")
async def import_traffic(
    session: SessionDep,
    file: UploadFile = File(...),
    store: int = Form(1),
    period_days: int = Form(7),
    period_start: date | None = Form(default=None),
    period_end: date | None = Form(default=None),
) -> dict:
    """导入千牛「商品分析」导出文件（xlsx / csv）。

    统计周期优先用显式区间的入参，其次从文件名解析（生意参谋导出自带日期），
    最后才按 period_days 回退到「截至今天」。期次必须落到具体日期，
    否则同一批商品在不同天数口径下会互相覆盖。
    """
    from inspection.traffic import parse_period, parse_rows, upsert_traffic

    if period_days not in (1, 7, 14, 30, 90):
        raise HTTPException(status_code=422, detail="period_days 只支持 1 / 7 / 14 / 30 / 90")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="文件为空")

    try:
        records, recognized, unknown, errors = parse_rows(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not records:
        raise HTTPException(
            status_code=422,
            detail=f"没有解析到有效数据行（{errors[:3] if errors else '文件只有表头'}）",
        )

    if period_start and period_end:
        start, end = (
            (period_start, period_end)
            if period_start <= period_end
            else (period_end, period_start)
        )
    else:
        parsed = parse_period(file.filename or "")
        if parsed:
            start, end = parsed
        else:
            end = date.today()
            start = end - timedelta(days=period_days - 1)

    result = upsert_traffic(
        session,
        records,
        store=store,
        period_start=start,
        period_end=end,
        source_file=file.filename,
    )
    return {
        **result,
        "recognized": recognized,
        "unknown_columns": unknown,
        "errors": errors[:20],
    }


@router.get("/traffic/overview")
def traffic_overview_api(
    session: SessionDep,
    period_days: int = Query(default=7, ge=1, le=365),
    store: int = Query(default=1),
) -> dict:
    """导入后的流量概览（访客 / 转化率 / 加购率）。"""
    from inspection.traffic import traffic_overview

    return traffic_overview(session, store=store, period_days=period_days)


@router.get("/traffic/periods")
def traffic_periods_api(session: SessionDep, store: int = Query(default=1)) -> dict:
    """已导入的流量期次（新到旧）。

    前端据此决定哪些周期档位可以点 —— 没导入过的档位不该给出可切换的假象。
    """
    from inspection.traffic import list_periods

    periods = list_periods(session, store=store)
    return {
        "periods": periods,
        "period_days": sorted({p["period_days"] for p in periods}, reverse=True),
    }


@router.get("/traffic/analysis")
def traffic_analysis_api(
    session: SessionDep,
    period_start: date | None = Query(default=None),
    period_end: date | None = Query(default=None),
    period_days: int | None = Query(default=None, ge=1, le=365),
    store: int = Query(default=1),
) -> dict:
    """流量结构分析：访客分档、集中度、高流量低转化清单。

    三种用法：给起止日期按区间分析；只给 period_days 取该档最新一期；
    都不给取最新一期。分析本身始终落在具体期次上，不跨期混合。
    """
    from inspection.models import ItemTraffic
    from inspection.traffic import list_periods, traffic_analysis

    if period_start is None and period_end is None and period_days is not None:
        row = session.exec(
            select(ItemTraffic.period_start, ItemTraffic.period_end)
            .where(
                ItemTraffic.store == store,
                ItemTraffic.period_days == period_days,
                ItemTraffic.period_start.is_not(None),
            )
            .order_by(ItemTraffic.period_start.desc())
            .limit(1)
        ).first()
        if row is None:
            # 这一档没有任何导入记录时，绝不回退到别的期次 ——
            # 否则「近 7 天」会显示 30 天的数字，切换看起来像没生效。
            return {
                "empty": True,
                "item_count": 0,
                "period_start": None,
                "period_end": None,
                "period_days": period_days,
                "reason": "no_period_for_days",
                "available_periods": list_periods(session, store=store)[:6],
            }
        period_start, period_end = row[0].date(), row[1].date()

    return traffic_analysis(
        session, store=store, period_start=period_start, period_end=period_end
    )


@router.get("/traffic/item/{item_id}")
def item_traffic_api(
    item_id: str,
    session: SessionDep,
    period_days: int = Query(default=7, ge=1, le=365),
    store: int = Query(default=1),
) -> dict:
    """单个商品的流量表现、全店排名与诊断。"""
    from inspection.traffic import item_traffic

    return item_traffic(session, item_id=item_id, store=store, period_days=period_days)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    store: int = 1


@router.post("/ai/chat")
def ai_chat_api(session: SessionDep, body: ChatRequest) -> dict:
    """带店铺数据上下文的自由问答。上下文每次现算，不缓存。"""
    from inspection.analyze.ai import chat

    if len(body.messages) > 40:
        raise HTTPException(status_code=422, detail="对话过长，请清空后重开")
    return chat(
        session, store=body.store, messages=[item.model_dump() for item in body.messages]
    )


class ItemChatRequest(BaseModel):
    item_id: str
    messages: list[ChatMessage]
    store: int = 1


@router.get("/item/{item_id}/checkup")
def item_checkup_api(
    item_id: str,
    session: SessionDep,
    store: int = Query(default=1),
    refresh: bool = Query(default=False),
) -> dict:
    """商品体检：规则层列出候选信号，模型裁决哪些成立、哪些是小样本噪声。

    未配置模型时退回规则判定（source=rules），结论结构不变。
    """
    from inspection.analyze.checkup import item_checkup

    return item_checkup(session, item_id=item_id, store=store, refresh=refresh)


@router.post("/ai/item-insight")
def ai_item_insight_api(
    session: SessionDep,
    item_id: str = Query(...),
    store: int = Query(default=1),
    refresh: bool = Query(default=False),
) -> dict:
    """单品诊断：这个商品卡在哪一步、下一步改什么。"""
    from inspection.analyze.ai_item import item_insight

    return item_insight(session, item_id=item_id, store=store, refresh=refresh)


@router.post("/ai/item-chat")
def ai_item_chat_api(session: SessionDep, body: ItemChatRequest) -> dict:
    """围绕单个商品继续追问。"""
    from inspection.analyze.ai_item import item_chat

    if len(body.messages) > 40:
        raise HTTPException(status_code=422, detail="对话过长，请清空后重开")
    return item_chat(
        session,
        item_id=body.item_id,
        store=body.store,
        messages=[item.model_dump() for item in body.messages],
    )


@router.get("/ai/status")
def ai_status_api() -> dict:
    """大模型是否已配置（不返回任何密钥内容）。"""
    from inspection.analyze.ai import status

    return status()


@router.post("/ai/traffic-insight")
def ai_traffic_insight_api(
    session: SessionDep,
    store: int = Query(default=1),
    refresh: bool = Query(default=False),
) -> dict:
    """把 7 天 / 30 天两期流量结构交给大模型解读。

    未配置 AI_API_KEY、调用失败或输出不合规时，自动回退成规则结论，
    前端不需要区分两种模式。
    """
    from inspection.analyze.ai import generate

    return generate(session, store=store, refresh=refresh)


@router.get("/shop/metrics")
def shop_metrics_api(
    session: SessionDep,
    days: int = Query(default=90, ge=7, le=365),
    store: int = Query(default=1),
) -> dict:
    """店铺层交易结构指标（动销率 / 集中度 / 价格带 / 关闭率）。

    数据源是已有订单表，不依赖商品页采集。
    """
    from inspection.analyze import shop_metrics

    return shop_metrics(session, days=days, store=store)


@router.get("/runs/{run_id}/{filename}")
def get_run_file(run_id: str, filename: str) -> FileResponse:
    """预览页与截图（白名单 + 目录约束）。"""
    if not _RUN_ID_RE.match(run_id) or filename not in _SERVED_FILES:
        raise HTTPException(status_code=404, detail="文件不存在")

    path = (RAW_ROOT / run_id / filename).resolve()
    if not path.is_file() or RAW_ROOT.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(path)
