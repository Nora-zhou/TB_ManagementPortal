import io
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from models import Product, PriceSnapshot
import routes.snapshots as snapshots_module

_VALID_CSV = b"item_id,name,price,url\n777,\xe6\xb5\x8b\xe8\xaf\x95\xe5\x95\x86\xe5\x93\x81,99.0,http://x\n"


def _seed_product(client: TestClient) -> int:
    client.post(
        "/api/products/import/csv",
        files={"file": ("p.csv", io.BytesIO(_VALID_CSV), "text/csv")},
    )
    return client.get("/api/products").json()["items"][0]["id"]


# ---------------------------------------------------------------------------
# POST /api/snapshots
# ---------------------------------------------------------------------------

def test_trigger_snapshot(client: TestClient):
    product_id = _seed_product(client)
    with patch(
        "routes.snapshots.fetch_item_price",
        new=AsyncMock(return_value=88.0),
    ):
        resp = client.post(
            "/api/snapshots",
            json={"session_key": "tok", "app_key": "key", "app_secret": "secret"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated"] == 1
    assert data["failed"] == 0

    # product current_price should be updated
    product_resp = client.get(f"/api/products/{product_id}")
    assert product_resp.json()["current_price"] == 88.0


def test_trigger_snapshot_item_error(client: TestClient):
    _seed_product(client)
    with patch(
        "routes.snapshots.fetch_item_price",
        new=AsyncMock(side_effect=ValueError("商品已下架")),
    ):
        resp = client.post(
            "/api/snapshots",
            json={"session_key": "tok", "app_key": "key", "app_secret": "secret"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["failed"] == 1
    assert data["updated"] == 0
    assert data["errors"][0]["reason"] == "商品已下架"


# ---------------------------------------------------------------------------
# GET /api/products/{id}/snapshots
# ---------------------------------------------------------------------------

def test_get_snapshots_empty(client: TestClient):
    product_id = _seed_product(client)
    resp = client.get(f"/api/products/{product_id}/snapshots")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_snapshots_with_data(client: TestClient, session: Session):
    product_id = _seed_product(client)
    session.add(PriceSnapshot(product_id=product_id, price=50.0))
    session.add(PriceSnapshot(product_id=product_id, price=55.0))
    session.commit()

    resp = client.get(f"/api/products/{product_id}/snapshots")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["price"] == 50.0
    assert data[1]["price"] == 55.0


def test_get_snapshots_product_not_found(client: TestClient):
    resp = client.get("/api/products/9999/snapshots")
    assert resp.status_code == 404


def test_snapshot_retention_trim(client: TestClient, session: Session):
    """After 365 snapshots, oldest is dropped when a new one is added."""
    product_id = _seed_product(client)
    now = datetime.now(timezone.utc)
    # L3 — give each snapshot a distinct timestamp for deterministic ordering
    for i in range(365):
        session.add(PriceSnapshot(
            product_id=product_id,
            price=float(i),
            recorded_at=now - timedelta(seconds=365 - i),  # oldest first
        ))
    session.commit()

    with patch(
        "routes.snapshots.fetch_item_price",
        new=AsyncMock(return_value=999.0),
    ):
        client.post(
            "/api/snapshots",
            json={"session_key": "t", "app_key": "k", "app_secret": "s"},
        )

    resp = client.get(f"/api/products/{product_id}/snapshots")
    snaps = resp.json()
    assert len(snaps) == 365
    # newest snapshot (price=999) should be last
    assert snaps[-1]["price"] == 999.0
    # price=0.0 (the oldest) must have been trimmed
    prices = [s["price"] for s in snaps]
    assert 0.0 not in prices


def test_snapshot_409_when_in_progress(client: TestClient):  # M3
    """Second call while snapshot is in progress must return 409."""
    original = snapshots_module._snapshot_in_progress
    snapshots_module._snapshot_in_progress = True
    try:
        resp = client.post(
            "/api/snapshots",
            json={"session_key": "t", "app_key": "k", "app_secret": "s"},
        )
        assert resp.status_code == 409
    finally:
        snapshots_module._snapshot_in_progress = original
