"""汇总账单（运营成本）导入测试。"""
import io

import openpyxl

HEADERS = [
    "月份", "业务大类", "开票方向", "账单编号", "币种",
    "本月付款", "本月交易额", "扣费金额合计 (元）", "退款金额",
]

SAMPLE_ROWS = [
    ["202610", "先用后付技术服务费", "平台开票给商家", "202610001", "CNY",
     "24.58", "6148.96", "24.58", "0.00"],
    ["202610", "淘金币软件服务费", "平台开票给商家", "202610002", "CNY",
     "462.35", "11679.43", "465.53", "3.18"],
    ["202610", "消费券代付资金扣回", "平台开票给商家", "202610003", "CNY",
     "430.02", "4190.10", "434.21", "4.19"],
]


def _make_bill(rows=SAMPLE_ROWS, headers=HEADERS, with_title=True) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "账单"
    if with_title:
        ws.append(["汇总账单"])
        ws.append([])
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _post_bill(client, data: bytes, store=1, filename="汇总账单.xlsx"):
    return client.post(
        "/api/profit/expenses/import-bill",
        files={
            "file": (
                filename,
                data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"store": store},
    )


def test_import_bill_maps_categories_and_amounts(client):
    resp = _post_bill(client, _make_bill())
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["imported"] == 3
    assert body["updated"] == 0
    assert body["month"] == "2026-10"
    assert body["total_amount"] == 916.95
    assert body["errors"] == []

    categories = {item["business_type"]: item["category"] for item in body["items"]}
    assert categories["先用后付技术服务费"] == "platform_fee"
    assert categories["淘金币软件服务费"] == "platform_fee"
    assert categories["消费券代付资金扣回"] == "other"

    listed = client.get("/api/profit/expenses", params={"store": 1, "source": "xlsx"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 3


def test_multiple_bills_same_business_type_are_summed(client):
    rows = [
        ["202610", "基础软件服务费", "平台开票给商家", "A001", "CNY",
         "100.00", "1000.00", "100.00", "0.00"],
        ["202610", "基础软件服务费", "平台开票给商家", "A002", "CNY",
         "50.00", "500.00", "50.00", "0.00"],
    ]
    resp = _post_bill(client, _make_bill(rows))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 1
    assert body["total_amount"] == 150.0

    listed = client.get("/api/profit/expenses", params={"store": 1, "source": "xlsx"}).json()
    assert listed["total"] == 1
    assert listed["items"][0]["amount"] == 150.0


def test_reimport_updates_same_business_type(client):
    _post_bill(client, _make_bill())
    body = _post_bill(client, _make_bill()).json()

    assert body["imported"] == 0
    assert body["updated"] == 3
    listed = client.get("/api/profit/expenses", params={"store": 1, "source": "xlsx"})
    assert listed.json()["total"] == 3


def test_imported_costs_feed_pure_profit(client):
    _post_bill(client, _make_bill())

    pure = client.get("/api/profit/pure").json()
    item = next(row for row in pure["items"] if row["month"] == "2026-10")

    assert item["platform_fee_s1"] == 486.93
    assert item["other_s1"] == 430.02
    assert item["profit_s1"] == -916.95


def test_header_found_in_second_sheet(client):
    wb = openpyxl.Workbook()
    note_sheet = wb.active
    note_sheet.title = "说明"
    note_sheet.append(["账单说明"])
    bill_sheet = wb.create_sheet("账单")
    bill_sheet.append(HEADERS)
    for row in SAMPLE_ROWS:
        bill_sheet.append(row)
    buf = io.BytesIO()
    wb.save(buf)

    resp = _post_bill(client, buf.getvalue())
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 3


def test_expense_analysis_aggregates_categories_and_items(client):
    _post_bill(client, _make_bill())

    resp = client.get("/api/profit/expense-analysis")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["months"] == ["2026-10"]
    assert body["kpi"]["total_expense"] == 916.95
    assert body["kpi"]["top_category"] == "platform_fee"
    assert body["kpi"]["top_item"] == "淘金币软件服务费"

    monthly = body["monthly"][0]
    assert monthly["platform_fee"] == 486.93
    assert monthly["other"] == 430.02
    assert monthly["total"] == 916.95

    items = {item["name"]: item for item in body["items"]}
    assert items["淘金币软件服务费"]["total"] == 462.35
    assert items["消费券代付资金扣回"]["category"] == "other"


def test_expense_analysis_computes_roi(client):
    _post_bill(client, _make_bill())

    body = client.get("/api/profit/expense-analysis").json()
    monthly = body["monthly"][0]
    assert monthly["transaction_amount"] == 22018.49
    assert monthly["roi"] == 24.01

    assert body["kpi"]["total_transaction_amount"] == 22018.49
    assert body["kpi"]["roi"] == 24.01
    assert body["kpi"]["latest_roi"] == 24.01

    items = {item["name"]: item for item in body["items"]}
    assert items["淘金币软件服务费"]["transaction_amount"] == 11679.43
    assert items["淘金币软件服务费"]["roi"] == 25.26


def test_expense_analysis_without_transaction_amount_has_no_roi(client):
    headers = ["月份", "业务大类", "本月付款"]
    rows = [["202610", "基础软件服务费", "100.00"]]
    _post_bill(client, _make_bill(rows=rows, headers=headers))

    body = client.get("/api/profit/expense-analysis").json()
    assert body["monthly"][0]["transaction_amount"] == 0.0
    assert body["monthly"][0]["roi"] is None
    assert body["kpi"]["roi"] is None


def test_expense_analysis_zero_fills_month_range(client):
    _post_bill(client, _make_bill())

    resp = client.get(
        "/api/profit/expense-analysis",
        params={"start_month": "2026-08", "end_month": "2026-10"},
    )
    body = resp.json()
    assert body["months"] == ["2026-08", "2026-09", "2026-10"]
    assert [item["total"] for item in body["monthly"]] == [0.0, 0.0, 916.95]
    assert body["kpi"]["month_count"] == 1


def test_expense_analysis_filters_by_store_and_range(client):
    _post_bill(client, _make_bill(), store=1)
    _post_bill(client, _make_bill(rows=SAMPLE_ROWS[:1]), store=2)

    store1 = client.get("/api/profit/expense-analysis", params={"store": 1}).json()
    store2 = client.get("/api/profit/expense-analysis", params={"store": 2}).json()
    assert store1["kpi"]["total_expense"] == 916.95
    assert store2["kpi"]["total_expense"] == 24.58

    invalid = client.get(
        "/api/profit/expense-analysis",
        params={"start_month": "2026-10", "end_month": "2026-08"},
    )
    assert invalid.status_code == 422


def test_missing_required_columns_returns_422(client):
    bad = _make_bill(headers=["月份", "币种"], rows=[["202610", "CNY"]])
    resp = _post_bill(client, bad)
    assert resp.status_code == 422
    assert "业务大类" in resp.json()["detail"]


def test_invalid_store_returns_422(client):
    resp = _post_bill(client, _make_bill(), store=3)
    assert resp.status_code == 422


def test_non_xlsx_returns_415(client):
    resp = _post_bill(client, b"not-an-excel", filename="账单.csv")
    assert resp.status_code == 415
