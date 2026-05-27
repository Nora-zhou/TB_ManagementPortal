import io
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from models import PriceSnapshot

_VALID_CSV = b"item_id,name,price,url\n111,T\xe6\x81\xa4,59.9,https://item.taobao.com/item.htm?id=111\n222,\xe7\x89\x9b\xe4\xbb\x94\xe8\xa3\xa4,129.0,https://item.taobao.com/item.htm?id=222\n"


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

def test_import_csv_success(client: TestClient):
    resp = client.post(
        "/api/products/import/csv",
        files={"file": ("products.csv", io.BytesIO(_VALID_CSV), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2
    assert data["updated"] == 0
    assert data["errors"] == []


def test_import_csv_update_existing(client: TestClient):
    client.post(
        "/api/products/import/csv",
        files={"file": ("p.csv", io.BytesIO(_VALID_CSV), "text/csv")},
    )
    resp = client.post(
        "/api/products/import/csv",
        files={"file": ("p.csv", io.BytesIO(_VALID_CSV), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 0
    assert data["updated"] == 2


def test_import_csv_missing_field(client: TestClient):
    bad_csv = b"item_id,name\n111,T\xe6\x81\xa4\n"
    resp = client.post(
        "/api/products/import/csv",
        files={"file": ("bad.csv", io.BytesIO(bad_csv), "text/csv")},
    )
    assert resp.status_code == 422


def test_import_csv_invalid_price(client: TestClient):
    bad_csv = b"item_id,name,price,url\n333,shirt,not-a-number,http://x\n"
    resp = client.post(
        "/api/products/import/csv",
        files={"file": ("bad.csv", io.BytesIO(bad_csv), "text/csv")},
    )
    assert resp.status_code == 422


def test_import_csv_rejects_javascript_url(client: TestClient):  # C1
    evil_csv = "item_id,name,price,url\n999,evil,9.9,javascript:alert(1)\n".encode()
    resp = client.post(
        "/api/products/import/csv",
        files={"file": ("evil.csv", io.BytesIO(evil_csv), "text/csv")},
    )
    assert resp.status_code == 422


def test_import_csv_rejects_negative_price(client: TestClient):  # L1
    bad_csv = b"item_id,name,price,url\n444,shirt,-5.0,https://x\n"
    resp = client.post(
        "/api/products/import/csv",
        files={"file": ("bad.csv", io.BytesIO(bad_csv), "text/csv")},
    )
    assert resp.status_code == 422


def test_import_csv_atomic_rollback(client: TestClient):  # H3
    """A single bad row must abort the entire import."""
    mixed_csv = (
        b"item_id,name,price,url\n"
        b"111,Good Item,50.0,https://good.example.com\n"
        b"222,Bad Item,not-a-price,https://bad.example.com\n"
    )
    resp = client.post(
        "/api/products/import/csv",
        files={"file": ("mixed.csv", io.BytesIO(mixed_csv), "text/csv")},
    )
    assert resp.status_code == 422
    # No products should have been written
    list_resp = client.get("/api/products")
    assert list_resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# List products
# ---------------------------------------------------------------------------

def _seed(client: TestClient):
    client.post(
        "/api/products/import/csv",
        files={"file": ("p.csv", io.BytesIO(_VALID_CSV), "text/csv")},
    )


def test_list_products(client: TestClient):
    _seed(client)
    resp = client.get("/api/products")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_products_pagination(client: TestClient):
    _seed(client)
    resp = client.get("/api/products?page=1&page_size=1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["total"] == 2


def test_list_products_search(client: TestClient):
    _seed(client)
    # L5 — case-insensitive search
    resp_upper = client.get("/api/products?q=T")
    resp_lower = client.get("/api/products?q=t")
    assert resp_upper.status_code == 200
    assert resp_lower.status_code == 200
    assert resp_upper.json()["total"] == resp_lower.json()["total"]
    assert resp_upper.json()["total"] >= 1


def test_list_products_price_filter(client: TestClient):
    _seed(client)
    resp = client.get("/api/products?max_price=60")
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert item["current_price"] <= 60


# ---------------------------------------------------------------------------
# Get single product
# ---------------------------------------------------------------------------

def test_get_product(client: TestClient, session: Session):
    _seed(client)
    list_resp = client.get("/api/products")
    product_id = list_resp.json()["items"][0]["id"]
    # L4 — verify snapshot_count accuracy
    from models import PriceSnapshot
    session.add(PriceSnapshot(product_id=product_id, price=50.0))
    session.add(PriceSnapshot(product_id=product_id, price=60.0))
    session.commit()
    resp = client.get(f"/api/products/{product_id}")
    assert resp.status_code == 200
    assert resp.json()["snapshot_count"] == 2


def test_get_product_not_found(client: TestClient):
    resp = client.get("/api/products/9999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Alert threshold
# ---------------------------------------------------------------------------

def test_update_alert(client: TestClient):
    _seed(client)
    product_id = client.get("/api/products").json()["items"][0]["id"]
    resp = client.put(f"/api/products/{product_id}/alert", json={"alert_low": 40.0, "alert_high": None})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == product_id  # H1 — id must be present
    assert data["alert_low"] == 40.0
    assert data["alert_high"] is None


def test_clear_alert(client: TestClient):
    _seed(client)
    product_id = client.get("/api/products").json()["items"][0]["id"]
    client.put(f"/api/products/{product_id}/alert", json={"alert_low": 40.0, "alert_high": 100.0})
    resp = client.put(f"/api/products/{product_id}/alert", json={"alert_low": None, "alert_high": None})
    assert resp.status_code == 200
    assert resp.json()["alert_low"] is None


def test_alert_status_below_low(client: TestClient):  # H4
    _seed(client)
    product_id = client.get("/api/products").json()["items"][0]["id"]
    # price is 59.9 — set alert_low above it
    client.put(f"/api/products/{product_id}/alert", json={"alert_low": 70.0, "alert_high": None})
    resp = client.get("/api/products")
    matched = [i for i in resp.json()["items"] if i["id"] == product_id]
    assert matched[0]["alert_status"] == "below_low"


def test_alert_status_above_high(client: TestClient):  # H4
    _seed(client)
    product_id = client.get("/api/products").json()["items"][0]["id"]
    # price is 59.9 — set alert_high below it
    client.put(f"/api/products/{product_id}/alert", json={"alert_low": None, "alert_high": 30.0})
    resp = client.get("/api/products")
    matched = [i for i in resp.json()["items"] if i["id"] == product_id]
    assert matched[0]["alert_status"] == "above_high"


def test_alert_status_normal_after_clear(client: TestClient):  # H4
    _seed(client)
    product_id = client.get("/api/products").json()["items"][0]["id"]
    client.put(f"/api/products/{product_id}/alert", json={"alert_low": 70.0, "alert_high": None})
    client.put(f"/api/products/{product_id}/alert", json={"alert_low": None, "alert_high": None})
    resp = client.get("/api/products")
    matched = [i for i in resp.json()["items"] if i["id"] == product_id]
    assert matched[0]["alert_status"] == "normal"


# ---------------------------------------------------------------------------
# Delete product
# ---------------------------------------------------------------------------

def test_delete_product(client: TestClient, session: Session):
    _seed(client)
    product_id = client.get("/api/products").json()["items"][0]["id"]
    # M8 — seed a snapshot and verify cascade delete
    from models import PriceSnapshot
    session.add(PriceSnapshot(product_id=product_id, price=55.0))
    session.commit()
    resp = client.delete(f"/api/products/{product_id}")
    assert resp.status_code == 204
    assert client.get(f"/api/products/{product_id}").status_code == 404
    # Snapshot should also be gone
    from sqlmodel import select
    remaining = session.exec(select(PriceSnapshot).where(PriceSnapshot.product_id == product_id)).all()
    assert remaining == []


# ---------------------------------------------------------------------------
# Taobao import (M4)
# ---------------------------------------------------------------------------

def test_import_taobao_success(client: TestClient):
    mock_items = [
        {"item_id": "555", "title": "淘宝商品", "price": 88.0},
    ]
    with patch("routes.products.fetch_store_items", new=AsyncMock(return_value=mock_items)):
        resp = client.post(
            "/api/products/import/taobao",
            json={"session_key": "tok", "app_key": "key", "app_secret": "sec"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 1
    assert data["updated"] == 0


def test_import_taobao_invalid_token(client: TestClient):
    with patch(
        "routes.products.fetch_store_items",
        new=AsyncMock(side_effect=ValueError("淘宝无效 session失效")),
    ):
        resp = client.post(
            "/api/products/import/taobao",
            json={"session_key": "bad", "app_key": "key", "app_secret": "sec"},
        )
    assert resp.status_code in (401, 502)


def test_import_taobao_network_error(client: TestClient):
    with patch(
        "routes.products.fetch_store_items",
        new=AsyncMock(side_effect=Exception("连接超时")),
    ):
        resp = client.post(
            "/api/products/import/taobao",
            json={"session_key": "tok", "app_key": "key", "app_secret": "sec"},
        )
    assert resp.status_code == 502


# (end of test_products.py)
