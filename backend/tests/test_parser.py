"""013-I01·T6：parse_item 测试（离线，基于脱敏 fixture）。"""

import json
from pathlib import Path

from inspection.collect import raw_store
from inspection.collect.parser import parse_item

FIXTURE = Path(__file__).parent / "inspection" / "fixtures" / "run-1052810876450"


def test_parse_full_fixture():
    data = parse_item(FIXTURE)

    assert data["item_id"] == "1052810876450"
    assert data["title"] == "S925通体纯银鲨鱼背三通佛头文玩手串配饰diy金刚百香菩提配件"
    assert data["price_cents"] == 4990          # priceMoney 本身是分
    assert data["image_count"] == 5
    assert len(data["image_urls"]) == 5
    assert all(u.startswith("https://img.alicdn.com/") for u in data["image_urls"])
    assert data["detail_image_count"] == 13     # 合成 desc.html 的 img 数
    assert data["sales_text"] == "已售 12"
    assert data["source"] == "page_dom"         # 数据确实从 HTML 解析出来
    assert data["raw_path"] == str(FIXTURE)


def _page_html(payload: dict) -> str:
    """用 json.dumps 拼 SSR 页面，避免手写大括号出错。"""
    return (
        "<html><body><script>!(function () {var a = window.__ICE_APP_CONTEXT__ || {};"
        f"var b = {json.dumps(payload, ensure_ascii=False)};"
        "for (var k in a) {b[k] = a[k]}window.__ICE_APP_CONTEXT__=b;})();"
        "</script></body></html>"
    )


def test_parse_price_falls_back_to_trade_params(tmp_path):
    """priceVO 缺失时兜底用 pcTrade.pcBuyParams.current_price（元 → 分）。"""
    run = raw_store.new_run("1", "u", raw_root=tmp_path)
    payload = {
        "loaderData": {
            "home": {
                "data": {
                    "res": {
                        "item": {"title": "t", "images": []},
                        "pcTrade": {"pcBuyParams": {"current_price": "49.90"}},
                    }
                }
            }
        }
    }
    (run / "page.html").write_text(_page_html(payload), encoding="utf-8")

    data = parse_item(run)
    assert data["price_cents"] == 4990


def test_parse_missing_ssr_data(tmp_path):
    """HTML 里没有 __ICE_APP_CONTEXT__：全 None + source=none（不抛异常）。"""
    run = raw_store.new_run("999", "u", raw_root=tmp_path)
    (run / "page.html").write_text(
        "<html><body>login wall or empty page</body></html>", encoding="utf-8"
    )

    data = parse_item(run)
    assert data["title"] is None
    assert data["price_cents"] is None
    assert data["image_count"] is None
    assert data["detail_image_count"] is None
    assert data["sales_text"] is None
    assert data["source"] == "none"


def test_parse_missing_page_html(tmp_path):
    """连 page.html 都没有（取数中途失败）：同样返回全 None。"""
    run = raw_store.new_run("998", "u", raw_root=tmp_path)

    data = parse_item(run)
    assert data["source"] == "none"
    assert data["item_id"] == "998"
