"""013-I03：落库与回读。"""

import json
from pathlib import Path

import pytest
from sqlmodel import SQLModel, Session, create_engine, select
from sqlmodel.pool import StaticPool

from inspection.collect.parser import parse_item
from inspection.models import InspectionRun, ItemSnapshot
from inspection.store import latest_snapshot, save_snapshot, to_display

FIXTURE = Path(__file__).parent / "inspection" / "fixtures" / "run-1052810876450"


@pytest.fixture(name="engine")
def engine_fixture():
    import inspection.models  # noqa: F401 — 注册检测表

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_save_snapshot_roundtrip(engine):
    data = parse_item(FIXTURE)
    run_id = save_snapshot(engine, data)

    assert run_id == data["run_id"]

    with Session(engine) as session:
        run = session.exec(select(InspectionRun)).one()
        assert run.run_id == run_id
        assert run.scope == "item"
        assert run.status == "ok"
        assert run.item_success == 1

        snapshot = session.exec(select(ItemSnapshot)).one()
        assert snapshot.item_id == "1052810876450"
        assert snapshot.price_cents == 4990
        assert snapshot.image_count == 5
        assert snapshot.detail_image_count == 13
        assert snapshot.reliable == 1
        assert json.loads(snapshot.sku_json)[0]["sku_id"] == "6084502265906"
        assert json.loads(snapshot.field_reliable_json)["price_cents"] == 1


def test_save_twice_updates_instead_of_duplicating(engine):
    data = parse_item(FIXTURE)
    save_snapshot(engine, data)
    data["price_cents"] = 5200
    save_snapshot(engine, data)

    with Session(engine) as session:
        assert len(session.exec(select(ItemSnapshot)).all()) == 1
        assert len(session.exec(select(InspectionRun)).all()) == 1
        assert session.exec(select(ItemSnapshot)).one().price_cents == 5200


def test_latest_snapshot_and_display(engine):
    data = parse_item(FIXTURE)
    save_snapshot(engine, data)

    snapshot = latest_snapshot(engine, item_id="1052810876450")
    assert snapshot is not None

    display = to_display(snapshot)
    assert display["title"].startswith("S925")
    assert display["sku"][0]["price_cents"] == 4990
    assert display["service"]["freight"] == "快递: 免运费"
    # naive UTC → 本地时间字符串
    assert len(display["collected_at"]) == 19


def test_missing_snapshot_returns_none(engine):
    assert latest_snapshot(engine, item_id="none") is None
