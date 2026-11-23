"""首页利润总览接口：成本口径应包含运营费用。"""
from datetime import datetime

from models import PurchaseOrder, StorePlatformExpense, SubOrder


def _seed_october(session):
    session.add(
        SubOrder(
            sub_order_id="SUB001",
            main_order_id="MAIN001",
            taobao_item_id="ITEM001",
            product_title="测试商品",
            status="交易成功",
            buyer_paid=1000.0,
            refund_amount="100.00",
            paid_at=datetime(2026, 10, 5, 10, 0, 0),
            store=1,
        )
    )
    session.add(
        PurchaseOrder(
            order_id="PO001",
            seller_name="供应商A",
            paid_amount=300.0,
            status="交易成功",
            paid_at=datetime(2026, 10, 6, 10, 0, 0),
            store=1,
        )
    )
    session.add(
        StorePlatformExpense(
            store=1,
            period_month="2026-10",
            category="platform_fee",
            sub_category="基础软件服务费",
            amount=50.0,
            source="xlsx",
        )
    )
    session.add(
        StorePlatformExpense(
            store=1,
            period_month="2026-10",
            category="other",
            sub_category="消费券代付资金扣回",
            amount=20.0,
            source="xlsx",
        )
    )
    session.commit()


def test_profit_monthly_includes_operating_expenses(client, session):
    _seed_october(session)

    resp = client.get("/api/stats/profit-monthly")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["months"] == ["2026-10"]
    assert body["series"]["cost_s1"] == [370.0]
    assert body["series"]["profit_s1"] == [530.0]
    assert body["kpi"]["total_cost"] == 370.0
    assert body["kpi"]["total_profit"] == 530.0


def test_profit_monthly_only_operating_expense_month(client, session):
    session.add(
        StorePlatformExpense(
            store=2,
            period_month="2026-09",
            category="promotion",
            sub_category="直通车",
            amount=80.0,
            source="xlsx",
        )
    )
    session.commit()

    body = client.get("/api/stats/profit-monthly").json()
    assert body["months"] == ["2026-09"]
    assert body["series"]["cost_s2"] == [80.0]
    assert body["series"]["profit_s2"] == [-80.0]
    assert body["kpi"]["total_profit"] == -80.0
