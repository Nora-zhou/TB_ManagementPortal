"""Tests for the orders module (T013 + T014)."""
import io
from datetime import datetime, timezone

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from models import Order


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_xlsx(rows: list[dict]) -> bytes:
    """Build a minimal xlsx file with the expected Taobao header."""
    headers = [
        "订单编号", "支付单号", "支付详情", "总金额",
        "买家实付金额", "订单状态", "订单创建时间",
        "商品标题", "卖家服务费", "退款金额",
    ]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h, "") for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


SAMPLE_ROWS = [
    {
        "订单编号": "ORD001",
        "支付单号": "PAY001",
        "支付详情": "支付宝",
        "总金额": "100.00",
        "买家实付金额": "90.00",
        "订单状态": "交易成功",
        "订单创建时间": "2026-03-01 10:00:00",
        "商品标题": "商品A,商品B",
        "卖家服务费": "0.00",
        "退款金额": "0.00",
    },
    {
        "订单编号": "ORD002",
        "支付单号": "PAY002",
        "支付详情": "微信",
        "总金额": "50.00",
        "买家实付金额": "50.00",
        "订单状态": "交易关闭",
        "订单创建时间": "2026-03-15 12:00:00",
        "商品标题": "商品C",
        "卖家服务费": "0.00",
        "退款金额": "50.00",
    },
    {
        "订单编号": "ORD003",
        "支付单号": "PAY003",
        "支付详情": "支付宝",
        "总金额": "200.00",
        "买家实付金额": "180.00",
        "订单状态": "交易成功",
        "订单创建时间": "2026-04-01 09:00:00",
        "商品标题": "商品A",
        "卖家服务费": "0.00",
        "退款金额": "0.00",
    },
]


def _upload(client: TestClient, rows=None, filename="orders.xlsx"):
    data = _make_xlsx(rows if rows is not None else SAMPLE_ROWS)
    return client.post(
        "/api/orders/import",
        files={"file": (filename, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )


# ---------------------------------------------------------------------------
# T013 — Import tests
# ---------------------------------------------------------------------------

def test_import_xlsx_normal(client: TestClient):
    resp = _upload(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 3
    assert body["updated"] == 0
    assert body["skipped"] == 0
    assert body["errors"] == []


def test_import_xlsx_dedup(client: TestClient):
    _upload(client)
    resp = _upload(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 0
    assert body["updated"] == 3


def test_import_missing_column(client: TestClient):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["订单编号", "支付单号"])  # missing most columns
    ws.append(["ORD999", "PAY999"])
    buf = io.BytesIO()
    wb.save(buf)
    resp = client.post(
        "/api/orders/import",
        files={"file": ("bad.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 422
    assert "缺少必填列" in resp.json()["detail"]


def test_import_wrong_format(client: TestClient):
    resp = client.post(
        "/api/orders/import",
        files={"file": ("orders.csv", b"col1,col2\nval1,val2", "text/csv")},
    )
    assert resp.status_code == 415


# ---------------------------------------------------------------------------
# T013 — List / filter tests
# ---------------------------------------------------------------------------

def test_list_orders_pagination(client: TestClient):
    _upload(client)
    resp = client.get("/api/orders?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2


def test_list_orders_status_filter(client: TestClient):
    _upload(client)
    resp = client.get("/api/orders?status=交易成功")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert all(i["status"] == "交易成功" for i in body["items"])


def test_list_orders_keyword_search(client: TestClient):
    _upload(client)
    resp = client.get("/api/orders?q=商品C")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert "商品C" in body["items"][0]["product_title"]


def test_list_orders_date_range(client: TestClient):
    _upload(client)
    resp = client.get("/api/orders?start_date=2026-04-01&end_date=2026-04-30")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["order_id"] == "ORD003"


# ---------------------------------------------------------------------------
# T014 — Stats tests
# ---------------------------------------------------------------------------

def test_summary_stats(client: TestClient):
    _upload(client)
    resp = client.get("/api/orders/stats/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_orders"] == 3
    assert body["success_orders"] == 2
    # Revenue = 90 + 180 = 270
    assert abs(body["total_revenue"] - 270.0) < 0.01
    # Refund = 50
    assert abs(body["total_refund"] - 50.0) < 0.01
    assert body["refund_rate"] == round(50 / 270, 4)


def test_trend_monthly(client: TestClient):
    _upload(client)
    resp = client.get("/api/orders/stats/trend?granularity=month")
    assert resp.status_code == 200
    body = resp.json()
    assert body["granularity"] == "month"
    # ORD001 in 2026-03, ORD003 in 2026-04 → 2 revenue labels
    assert "2026-03" in body["labels"]
    assert "2026-04" in body["labels"]


def test_trend_daily(client: TestClient):
    _upload(client)
    resp = client.get("/api/orders/stats/trend?granularity=day")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["labels"]) >= 2


def test_status_distribution_sums_to_100(client: TestClient):
    _upload(client)
    resp = client.get("/api/orders/stats/status")
    assert resp.status_code == 200
    items = resp.json()
    total_pct = sum(i["percent"] for i in items)
    assert abs(total_pct - 100.0) < 0.1


def test_top_products_by_revenue(client: TestClient):
    _upload(client)
    resp = client.get("/api/orders/stats/top-products?sort_by=revenue&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sort_by"] == "revenue"
    # 商品A appears in ORD001 (90.00) and ORD003 (180.00) → total 270
    top = body["items"][0]
    assert top["product_title"] == "商品A"
    assert abs(top["total_revenue"] - 270.0) < 0.01
    assert top["rank"] == 1


def test_top_products_by_count(client: TestClient):
    _upload(client)
    resp = client.get("/api/orders/stats/top-products?sort_by=count&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    top = body["items"][0]
    assert top["product_title"] == "商品A"
    assert top["order_count"] == 2


# ---------------------------------------------------------------------------
# T004 — status distribution date filter tests
# ---------------------------------------------------------------------------

def test_status_dist_date_filter_march(client: TestClient):
    """Only March orders: ORD001(交易成功) + ORD002(交易关闭)."""
    _upload(client)
    resp = client.get("/api/orders/stats/status?start_date=2026-03-01&end_date=2026-03-31")
    assert resp.status_code == 200
    items = resp.json()
    statuses = {i["status"]: i["count"] for i in items}
    assert statuses.get("交易成功") == 1
    assert statuses.get("交易关闭") == 1
    assert "交易成功" in statuses  # ORD003 (April) must not appear


def test_status_dist_date_filter_april(client: TestClient):
    """Only April orders: ORD003(交易成功)."""
    _upload(client)
    resp = client.get("/api/orders/stats/status?start_date=2026-04-01&end_date=2026-04-30")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["status"] == "交易成功"
    assert items[0]["count"] == 1
    assert items[0]["percent"] == 100.0


def test_status_dist_date_filter_no_data(client: TestClient):
    """Date range with no orders should return empty list."""
    _upload(client)
    resp = client.get("/api/orders/stats/status?start_date=2025-01-01&end_date=2025-01-31")
    assert resp.status_code == 200
    assert resp.json() == []
