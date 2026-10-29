from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from database import get_session
from models import PLATFORM_DATASETS, PlatformAccount, RPATask
from rpa import runner
from schemas import RPATaskCreate, RPATaskListResponse, RPATaskRead

router = APIRouter(prefix="/rpa/tasks", tags=["rpa"])


@router.get("", response_model=RPATaskListResponse)
def list_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> RPATaskListResponse:
    stmt = select(RPATask).order_by(RPATask.id.desc()).limit(limit)  # type: ignore[attr-defined]
    rows = session.exec(stmt).all()
    return RPATaskListResponse(total=len(rows), items=[_to_read(t, session) for t in rows])


@router.post("", response_model=RPATaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: RPATaskCreate, session: Session = Depends(get_session)) -> RPATaskRead:
    account = session.get(PlatformAccount, payload.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="平台账号不存在")

    valid_keys = {d["key"] for d in PLATFORM_DATASETS.get(account.platform, [])}
    invalid = [d for d in payload.datasets if d not in valid_keys]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"数据集 {invalid} 不属于平台 {account.platform}，可选：{sorted(valid_keys)}",
        )

    task = RPATask(
        platform=account.platform,
        account_id=account.id or 0,
        store=payload.store,
        datasets=json.dumps(payload.datasets, ensure_ascii=False),
        period_month=payload.period_month,
        status="pending",
        progress=0,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    runner.start_worker()
    runner.notify_new_task()

    return _to_read(task, session)


@router.get("/{task_id}", response_model=RPATaskRead)
def get_task(task_id: int, session: Session = Depends(get_session)) -> RPATaskRead:
    task = session.get(RPATask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _to_read(task, session)


@router.post("/{task_id}/cancel", response_model=RPATaskRead)
def cancel_task(task_id: int, session: Session = Depends(get_session)) -> RPATaskRead:
    task = session.get(RPATask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in {"pending", "running"}:
        raise HTTPException(status_code=409, detail=f"当前状态 {task.status} 不可取消")
    task.status = "cancelled"
    task.finished_at = datetime.now(timezone.utc)
    session.add(task)
    session.commit()
    session.refresh(task)
    return _to_read(task, session)


def _to_read(task: RPATask, session: Session) -> RPATaskRead:
    try:
        datasets = json.loads(task.datasets or "[]")
    except json.JSONDecodeError:
        datasets = []
    account = session.get(PlatformAccount, task.account_id)
    return RPATaskRead(
        id=task.id or 0,
        platform=task.platform,
        account_id=task.account_id,
        account_label=account.account_label if account else None,
        store=task.store,
        datasets=datasets,
        period_month=task.period_month,
        status=task.status,
        progress=task.progress,
        log=task.log,
        result_summary=task.result_summary,
        error_message=task.error_message,
        started_at=task.started_at,
        finished_at=task.finished_at,
        created_at=task.created_at,
    )
