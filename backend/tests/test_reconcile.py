"""导入后自动核对：库内月度汇总 × 平台月度基准。"""

import calendar
import io
from datetime import date

import openpyxl
from fastapi.testclient import TestClient

SUB_ORDER_HEADERS = [
    "子订单编号", "主订单编号", "商品ID", "商品标题", "购买数量", "商品价格",
    "商品属性", "订单状态", "支付单号", "买家实付金额", "退款金额",
    "订单创建时间", "订单付款时间",
]


def _shift_month(month: str, delta: int) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _make_xlsx(rows: list[dict]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(SUB_ORDER_HEADERS)
    for row in rows:
        ws.append([row.get(h, "") for h in SUB_ORDER_HEADERS])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(client: TestClient, rows: list[dict], store: int = 1):
    data = _make_xlsx(rows)
    return client.post(
        "/api/sub-orders/import",
        files={
            "file": (
                "sub_orders.xlsx",
                data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"store": str(store)},
    )


def _row(idx: int, month: str, day: int, amount: float, quantity: int = 1) -> dict:
    stamp = f"{month}-{day:02d} 10:00:00"
    return {
        "子订单编号": f"S{idx:04d}",
        "主订单编号": f"M{idx:04d}",
        "商品ID": "1001",
        "商品标题": "测试商品",
        "购买数量": quantity,
        "商品价格": "50.00",
        "商品属性": "默认",
        "订单状态": "交易成功",
        "支付单号": f"P{idx:04d}",
        "买家实付金额": f"{amount:.2f}",
        "退款金额": "无退款申请",
        "订单创建时间": stamp,
        "订单付款时间": stamp,
    }


def _month_samples() -> tuple[str, str, str, list[dict]]:
    """前月/上月/本月：上月单量骤降，用于触发「疑似漏单」。"""
    middle = _shift_month(date.today().strftime("%Y-%m"), -1)
    prev = _shift_month(middle, -1)
    current = _shift_month(middle, 1)

    rows: list[dict] = []
    idx = 1
    for i in range(12):
        rows.append(_row(idx, prev, i % 20 + 1, 100.0))
        idx += 1
    for i in range(2):
        rows.append(_row(idx, middle, i + 1, 100.0))
        idx += 1
    for i in range(12):
        rows.append(_row(idx, current, i % 20 + 1, 100.0))
        idx += 1
    return prev, middle, current, rows


def test_import_returns_reconcile_with_gap_hint(client: TestClient):
    prev, middle, current, rows = _month_samples()
    resp = _upload(client, rows)
    assert resp.status_code == 200

    body = resp.json()
    months = [item["month"] for item in body["reconcile"]]
    assert months == sorted({prev, middle, current})

    target = next(item for item in body["reconcile"] if item["month"] == middle)
    assert target["store"] == 1
    assert target["db_orders"] == 2
    assert target["expected_days"] == calendar.monthrange(
        int(middle[:4]), int(middle[5:7])
    )[1]
    assert target["has_platform"] is False
    assert target["status"] == "warning"
    assert any("疑似漏单" in hint for hint in target["hints"])

    steady = next(item for item in body["reconcile"] if item["month"] == current)
    assert steady["status"] == "ok"


def test_platform_stat_upsert_and_diff(client: TestClient):
    _, middle, _, rows = _month_samples()
    _upload(client, rows)

    resp = client.put(
        "/api/reconcile/platform-stats",
        json={
            "store": 1,
            "period_month": middle,
            "pay_amount": 400.0,
            "refund_amount": 0.0,
            "paid_items": 4,
            "paid_buyers": 3,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["pay_amount"] == 400.0

    check = client.get(
        "/api/reconcile/monthly",
        params={"store": 1, "start_month": middle, "end_month": middle},
    )
    assert check.status_code == 200
    item = check.json()["items"][0]
    assert item["has_platform"] is True
    assert item["db_pay_amount"] == 200.0
    assert item["pay_diff_pct"] == -50.0
    assert item["status"] == "gap"
    assert item["platform_paid_buyers"] == 3

    # 更新同一条记录不应新增行
    again = client.put(
        "/api/reconcile/platform-stats",
        json={"store": 1, "period_month": middle, "pay_amount": 200.0},
    )
    assert again.status_code == 200
    stats = client.get("/api/reconcile/platform-stats", params={"store": 1}).json()
    assert len([s for s in stats if s["period_month"] == middle]) == 1
    assert stats[0]["pay_amount"] == 200.0

    deleted = client.delete(f"/api/reconcile/platform-stats/1/{middle}")
    assert deleted.status_code == 204
    assert client.get("/api/reconcile/platform-stats", params={"store": 1}).json() == []


def test_monthly_endpoint_without_platform_data(client: TestClient):
    prev, middle, current, rows = _month_samples()
    _upload(client, rows)

    resp = client.get(
        "/api/reconcile/monthly",
        params={"store": 1, "start_month": prev, "end_month": current},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["month"] for i in items] == [prev, middle, current]
    assert all(i["has_platform"] is False for i in items)
    assert all(i["pay_diff_pct"] is None for i in items)


def test_monthly_endpoint_rejects_bad_month(client: TestClient):
    resp = client.get("/api/reconcile/monthly", params={"store": 1, "start_month": "2026/06"})
    assert resp.status_code == 422
