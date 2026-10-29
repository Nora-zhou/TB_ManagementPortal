"""013-I03：把解析结果落库（inspection_run + item_snapshot）。

原则：
- 事实层只增不改：同一 run_id 重复写入时覆盖同一条快照，不产生重复行。
- 整条记录级 reliable 由 CORE 字段决定（任一为 0 则整条标记不可信），
  字段级结论仍以 field_reliable_json 为准（I02 起下游按字段跳过）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Engine
from sqlmodel import Session, select

from inspection.models import CORE_FIELDS, InspectionRun, ItemSnapshot

# parse 返回的 Python 对象字段 → 表里的 JSON 文本列
_JSON_COLUMNS = {
    "image_urls": "image_urls",
    "image_meta": "image_meta_json",
    "review": "review_json",
    "sku_json": "sku_json",
    "service_json": "service_json",
    "detail_meta": "detail_meta_json",
    "field_reliable": "field_reliable_json",
}

# 直接同名列拷贝的标量字段
_SCALAR_COLUMNS = (
    "item_id",
    "title",
    "price_cents",
    "promo_price_cents",
    "price_min_cents",
    "price_max_cents",
    "image_count",
    "detail_image_count",
    "sales_text",
    "sales_parsed",
    "review_count",
    "rating",
    "stock_total",
    "item_status",
    "raw_path",
    "source",
)


def _snapshot_payload(data: dict) -> dict:
    payload: dict = {"run_id": data["run_id"]}
    for column in _SCALAR_COLUMNS:
        if column in data:
            payload[column] = data[column]
    for source_key, column in _JSON_COLUMNS.items():
        value = data.get(source_key)
        payload[column] = (
            json.dumps(value, ensure_ascii=False) if value is not None else None
        )

    reliable = data.get("field_reliable") or {}
    payload["reliable"] = int(all(reliable.get(f, 0) for f in CORE_FIELDS))
    payload["collected_at"] = datetime.now(timezone.utc)
    return payload


def save_snapshot(
    engine: Engine,
    data: dict,
    *,
    store: int = 1,
    subject: str = "self",
    subject_name: str | None = None,
) -> str:
    """写入一次 run + 一条快照，返回 run_id。"""
    run_id: str = data["run_id"]
    ok = data.get("source") == "page_dom"
    reliable = data.get("field_reliable") or {}

    with Session(engine) as session:
        run = session.exec(
            select(InspectionRun).where(InspectionRun.run_id == run_id)
        ).first()
        if run is None:
            run = InspectionRun(
                run_id=run_id,
                store=store,
                subject=subject,
                subject_name=subject_name,
                scope="item",
                item_target=1,
                item_success=1 if ok else 0,
                status="ok" if ok else "partial",
                finished_at=datetime.now(timezone.utc),
            )
            session.add(run)
        else:
            run.item_success = 1 if ok else 0
            run.status = "ok" if ok else "partial"
            run.finished_at = datetime.now(timezone.utc)
            session.add(run)

        payload = _snapshot_payload(data)
        existing = session.exec(
            select(ItemSnapshot).where(
                ItemSnapshot.run_id == run_id,
                ItemSnapshot.item_id == payload["item_id"],
            )
        ).first()
        if existing is None:
            session.add(ItemSnapshot(**payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
            session.add(existing)

        session.commit()

    if reliable and not all(reliable.get(f, 0) for f in CORE_FIELDS):
        # 不抛异常：数据已入库，由调用方决定是否展示降级提示
        return run_id
    return run_id


def latest_snapshot(
    engine: Engine,
    *,
    item_id: str | None = None,
    run_id: str | None = None,
) -> ItemSnapshot | None:
    with Session(engine) as session:
        statement = select(ItemSnapshot)
        if item_id:
            statement = statement.where(ItemSnapshot.item_id == item_id)
        if run_id:
            statement = statement.where(ItemSnapshot.run_id == run_id)
        statement = statement.order_by(ItemSnapshot.collected_at.desc()).limit(1)
        return session.exec(statement).first()


def _local(moment: datetime | None) -> str | None:
    """库里存的是 naive UTC，展示时换成本地时间。"""
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def to_display(snapshot: ItemSnapshot) -> dict:
    """把快照还原成便于打印的结构（JSON 列解码）。"""
    result = {
        "run_id": snapshot.run_id,
        "item_id": snapshot.item_id,
        "title": snapshot.title,
        "price_cents": snapshot.price_cents,
        "promo_price_cents": snapshot.promo_price_cents,
        "price_min_cents": snapshot.price_min_cents,
        "price_max_cents": snapshot.price_max_cents,
        "image_count": snapshot.image_count,
        "detail_image_count": snapshot.detail_image_count,
        "sales_text": snapshot.sales_text,
        "sales_parsed": snapshot.sales_parsed,
        "review_count": snapshot.review_count,
        "stock_total": snapshot.stock_total,
        "item_status": snapshot.item_status,
        "source": snapshot.source,
        "reliable": snapshot.reliable,
        "raw_path": snapshot.raw_path,
        "collected_at": _local(snapshot.collected_at),
    }
    for key in ("sku_json", "image_urls", "review_json", "service_json",
                "image_meta_json", "detail_meta_json", "field_reliable_json"):
        raw = getattr(snapshot, key, None)
        target = key.replace("_json", "")
        result[target] = json.loads(raw) if raw else None
    return result
