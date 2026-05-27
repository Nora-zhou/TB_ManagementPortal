"""Tests for POST /api/products/import/from-goods-dir (T005)."""
import csv
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

import routes.products as products_module


def _write_csv(directory: Path, filename: str, rows: list[dict], fieldnames=None) -> Path:
    path = directory / filename
    if fieldnames is None:
        fieldnames = ["item_id", "name", "price", "url"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


BATCH1 = [
    {"item_id": "ID001", "name": "商品一", "price": "10.00", "url": "https://example.com/1"},
    {"item_id": "ID002", "name": "商品二", "price": "20.00", "url": "https://example.com/2"},
    {"item_id": "ID003", "name": "商品三", "price": "30.00", "url": "https://example.com/3"},
    {"item_id": "ID004", "name": "商品四", "price": "40.00", "url": "https://example.com/4"},
    {"item_id": "ID005", "name": "商品五", "price": "50.00", "url": "https://example.com/5"},
]


@pytest.fixture(autouse=True)
def patch_goods_dir(tmp_path, monkeypatch):
    """Redirect GOODS_DIR to a temp directory for each test."""
    goods_dir = tmp_path / "Goods"
    goods_dir.mkdir()
    monkeypatch.setattr(products_module, "GOODS_DIR", goods_dir)
    return goods_dir


# ---------------------------------------------------------------------------
# T005-① First import: 5 new products
# ---------------------------------------------------------------------------

def test_first_import_five_products(client: TestClient, tmp_path, monkeypatch):
    goods_dir = products_module.GOODS_DIR
    _write_csv(goods_dir, "batch1.csv", BATCH1)

    resp = client.post("/api/products/import/from-goods-dir")
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 5
    assert body["updated"] == 0
    assert body["errors"] == []


# ---------------------------------------------------------------------------
# T005-② Re-import same file: 0 imported, 5 updated
# ---------------------------------------------------------------------------

def test_reimport_same_file(client: TestClient):
    goods_dir = products_module.GOODS_DIR
    _write_csv(goods_dir, "batch1.csv", BATCH1)

    client.post("/api/products/import/from-goods-dir")
    resp = client.post("/api/products/import/from-goods-dir")
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 0
    assert body["updated"] == 5


# ---------------------------------------------------------------------------
# T005-③ Add second batch: 3 new + 2 existing (price changed)
# ---------------------------------------------------------------------------

def test_incremental_import_mixed(client: TestClient):
    goods_dir = products_module.GOODS_DIR
    _write_csv(goods_dir, "batch1.csv", BATCH1)
    client.post("/api/products/import/from-goods-dir")

    batch2 = [
        # 2 existing IDs with different prices
        {"item_id": "ID001", "name": "商品一改", "price": "11.00", "url": "https://example.com/1"},
        {"item_id": "ID002", "name": "商品二改", "price": "22.00", "url": "https://example.com/2"},
        # 3 new IDs
        {"item_id": "ID006", "name": "商品六", "price": "60.00", "url": "https://example.com/6"},
        {"item_id": "ID007", "name": "商品七", "price": "70.00", "url": "https://example.com/7"},
        {"item_id": "ID008", "name": "商品八", "price": "80.00", "url": "https://example.com/8"},
    ]
    _write_csv(goods_dir, "batch2.csv", batch2)

    resp = client.post("/api/products/import/from-goods-dir")
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 3   # ID006, ID007, ID008 are new
    # Second scan reads both files: batch1 (5 existing → updated) + batch2 (2 existing → updated)
    assert body["updated"] == 7


# ---------------------------------------------------------------------------
# T005-④ Empty Goods directory
# ---------------------------------------------------------------------------

def test_empty_goods_dir(client: TestClient):
    # goods_dir exists but has no CSV files
    resp = client.post("/api/products/import/from-goods-dir")
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 0
    assert body["updated"] == 0
    assert len(body["errors"]) == 1
    assert "未找到 CSV" in body["errors"][0]["reason"]


# ---------------------------------------------------------------------------
# T005-⑤ CSV missing item_id column → skip file, record error
# ---------------------------------------------------------------------------

def test_csv_missing_item_id(client: TestClient):
    goods_dir = products_module.GOODS_DIR
    # Write a file without item_id column
    _write_csv(goods_dir, "bad.csv",
               [{"product_name": "X", "cost": "5.00"}],
               fieldnames=["product_name", "cost"])
    # Write a valid file alongside
    _write_csv(goods_dir, "good.csv", BATCH1[:2])

    resp = client.post("/api/products/import/from-goods-dir")
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 2          # only good.csv processed
    assert len(body["errors"]) == 1
    assert body["errors"][0]["file"] == "bad.csv"
    assert "item_id" in body["errors"][0]["reason"]
