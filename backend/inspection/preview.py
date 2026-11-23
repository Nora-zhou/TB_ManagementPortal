"""013-I03：把一条快照渲染成本地预览 HTML（不依赖前端框架）。

用途：人工核对采集准确性（G01）。打开 data/raw/<run_id>/preview.html 即可看到
字段对照表、可信度标记、主图网格、SKU 表与截图。

设计取舍：
- 单文件、内联 CSS，不引用任何本地资源（图片走 alicdn 远程 URL）。
- 只读快照与 run 目录，不写数据库。
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from inspection.models import CORE_FIELDS

_CSS = """
* { box-sizing: border-box; }
body { margin:0; padding:36px 28px 64px; background:#FAFAF8; color:#1F1F1D;
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
  font-size:14px; line-height:1.7; }
.wrap { max-width:1000px; margin:0 auto; }
h1 { font-size:22px; font-weight:500; margin:0 0 6px; }
.sub { color:#7A7A72; font-size:13px; margin-bottom:26px; }
h2 { font-size:15px; font-weight:500; margin:32px 0 12px; padding-bottom:6px;
  border-bottom:1px solid #E5E3DC; }
table { width:100%; border-collapse:collapse; background:#fff; font-size:13px; }
th,td { text-align:left; padding:8px 12px; border-bottom:1px solid #EDEBE4; }
th { color:#55554E; font-weight:500; font-size:12px; white-space:nowrap; }
td.k { color:#2F5D50; white-space:nowrap; width:150px; }
.badge { display:inline-block; font-size:11px; padding:1px 8px; border-radius:100px; }
.ok { background:#E1F5EE; color:#0F6E56; }
.bad { background:#FBEEEC; color:#8B3A32; }
.muted { color:#A8A8A0; }
.grid { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; }
.grid figure { margin:0; background:#fff; border:1px solid #E5E3DC; border-radius:8px;
  overflow:hidden; }
.grid img { width:100%; aspect-ratio:3/4; object-fit:cover; display:block; background:#F0EFE9; }
.grid figcaption { font-size:11px; color:#8A8A82; padding:4px 6px; }
.shot { max-width:720px; border:1px solid #E5E3DC; border-radius:8px; display:block; }
pre { background:#FCFCFA; border:1px solid #E5E3DC; border-radius:8px; padding:14px 16px;
  font-size:12px; overflow:auto; max-height:320px; }
.note { background:#F2F5F1; border-left:2px solid #2F5D50; padding:10px 14px;
  border-radius:6px; font-size:13px; color:#2A4A40; }
tr.fail { background:#FEF8F7; }
.rid { font-family:ui-monospace,Consolas,monospace; font-size:10.5px; color:#A8A8A0;
  margin-left:6px; }
"""


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def _badge(field: str, reliable: dict) -> str:
    if reliable.get(field):
        return '<span class="badge ok">可信</span>'
    return '<span class="badge bad">缺失</span>'


def _yuan(cents: object) -> str:
    if not isinstance(cents, int):
        return "-"
    return f"¥{cents / 100:.2f}"


def from_parse(data: dict) -> dict:
    """把 parse_item() 的输出转成 to_display() 的展示结构（键名对齐）。"""
    reliable = data.get("field_reliable") or {}
    return {
        "run_id": data.get("run_id"),
        "item_id": data.get("item_id"),
        "title": data.get("title"),
        "price_cents": data.get("price_cents"),
        "promo_price_cents": data.get("promo_price_cents"),
        "price_min_cents": data.get("price_min_cents"),
        "price_max_cents": data.get("price_max_cents"),
        "image_count": data.get("image_count"),
        "detail_image_count": data.get("detail_image_count"),
        "sales_text": data.get("sales_text"),
        "stock_total": data.get("stock_total"),
        "item_status": data.get("item_status"),
        "review_count": data.get("review_count"),
        "source": data.get("source"),
        "raw_path": data.get("raw_path"),
        "collected_at": data.get("collected_at")
        or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reliable": int(all(reliable.get(f) for f in CORE_FIELDS)),
        "field_reliable": reliable,
        "image_meta": data.get("image_meta") or [],
        "sku": data.get("sku") or data.get("sku_json") or [],
        "service": data.get("service") or data.get("service_json") or {},
        "review": data.get("review") or {},
    }


def render_preview(data: dict, run_dir: Path) -> Path:
    """data 为展示结构（to_display 或 from_parse 的返回值）。"""
    reliable = data.get("field_reliable") or {}
    shots = sorted(run_dir.glob("*.png"))
    images = data.get("image_meta") or []
    skus = data.get("sku") or []
    service = data.get("service") or {}
    review = data.get("review") or {}
    core_ok = all(reliable.get(f) == 1 for f in CORE_FIELDS)

    rows = [
        ("商品 ID", data["item_id"], "item_id"),
        ("标题", data["title"], "title"),
        ("主价", _yuan(data["price_cents"]), "price_cents"),
        ("券后价", _yuan(data["promo_price_cents"]), None),
        (
            "SKU 价格区间",
            f"{_yuan(data['price_min_cents'])} ~ {_yuan(data['price_max_cents'])}",
            None,
        ),
        ("主图张数", data["image_count"], "image_count"),
        ("详情图张数", data["detail_image_count"], "detail_image_count"),
        ("月销", data["sales_text"], "sales_text"),
        ("库存合计", data["stock_total"], "stock_total"),
        ("商品状态", data["item_status"], None),
        ("评价数", data["review_count"], "review_count"),
        ("数据来源", data["source"], None),
        ("采集时间", data["collected_at"], None),
        ("原始目录", data["raw_path"], None),
    ]

    row_html = "\n".join(
        f"<tr><td class='k'>{_esc(label)}</td><td>{_esc(value)}</td>"
        f"<td>{_badge(field, reliable) if field else '<span class=\"muted\">-</span>'}</td></tr>"
        for label, value, field in rows
    )

    image_html = "\n".join(
        f"<figure><img src='{_esc(img.get('url'))}' loading='lazy' alt=''>"
        f"<figcaption>{img.get('w') or '?'}×{img.get('h') or '?'}"
        f"{' · 3:4' if img.get('ratio') == 0.75 else ''}</figcaption></figure>"
        for img in images
    ) or "<p class='muted'>无主图数据</p>"

    sku_rows = "\n".join(
        f"<tr><td>{_esc(s.get('sku_id'))}</td><td>{_esc(s.get('name'))}</td>"
        f"<td>{_yuan(s.get('price_cents'))}</td><td>{_esc(s.get('stock'))}</td>"
        f"<td>{_esc(s.get('quantity_text'))}</td><td>{_esc(s.get('logistics'))}</td></tr>"
        for s in skus
    ) or "<tr><td colspan='6' class='muted'>无 SKU 数据</td></tr>"

    shot_html = (
        f"<img class='shot' src='{_esc(shots[0].name)}' alt='页面截图'>"
        if shots
        else "<p class='muted'>无截图</p>"
    )

    from inspection.validate import run_assertions

    assertions = run_assertions(data)
    summary = assertions["summary"]
    assert_rows = "\n".join(
        f"<tr class='{'fail' if not item['passed'] else ''}'>"
        f"<td><span class='badge {'ok' if item['passed'] else 'bad'}'>"
        f"{'通过' if item['passed'] else '不通过'}</span></td>"
        f"<td>{_esc(item['title'])}<span class='rid'>{_esc(item['rule_id'])}</span></td>"
        f"<td>{_esc(item['expected'])}</td><td>{_esc(item['actual'])}</td>"
        f"<td class='muted'>{_esc(item['message'])}</td></tr>"
        for item in assertions["results"]
    ) or "<tr><td colspan='5' class='muted'>无可判定断言</td></tr>"
    assert_note = (
        f"共 {summary['total']} 项 · 通过 {summary['passed']} · 不通过 {summary['failed']}"
        + (f" · 因数据不足跳过 {summary['skipped']}" if summary["skipped"] else "")
    )

    verdict = (
        "<div class='note'>核心字段（标题/价格/主图数/详情图数）全部采到，可用于下游指标。</div>"
        if core_ok
        else "<div class='note' style='border-color:#A8453A;background:#FBEEEC;color:#6E2A22'>"
        "核心字段有缺失，本次快照标记为不可信（reliable=0），下游指标应跳过。</div>"
    )

    document = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>采集结果 · {_esc(data['item_id'])}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
<h1>{_esc(data['title'] or '(无标题)')}</h1>
<div class="sub">{_esc(data['run_id'])} · {_esc(data['collected_at'])} ·
<span class="badge {'ok' if core_ok else 'bad'}">reliable={data.get('reliable')}</span></div>
{verdict}

<h2>断言检查</h2>
<div class="sub">{_esc(assert_note)}</div>
<table><tr><th>结果</th><th>检查项</th><th>期望</th><th>实际</th><th>说明</th></tr>
{assert_rows}</table>

<h2>字段对照</h2>
<table><tr><th>字段</th><th>采集值</th><th>可信度</th></tr>{row_html}</table>

<h2>主图（{len(images)} 张）</h2>
<div class="grid">{image_html}</div>

<h2>SKU</h2>
<table><tr><th>SKU ID</th><th>规格</th><th>价格</th><th>库存</th><th>库存文案</th><th>发货</th></tr>
{sku_rows}</table>

<h2>服务与评价</h2>
<table>
<tr><td class="k">邮费</td><td>{_esc(service.get('freight'))}</td></tr>
<tr><td class="k">发货时效</td><td>{_esc(service.get('ship_aging'))}</td></tr>
<tr><td class="k">发货地</td><td>{_esc(service.get('delivery_from'))}</td></tr>
<tr><td class="k">店铺标签</td><td>{_esc('、'.join(service.get('labels') or []))}</td></tr>
<tr><td class="k">评价数</td><td>{_esc(review.get('count'))}</td></tr>
<tr><td class="k">好评率</td><td>{_esc(review.get('favorable_rate'))}</td></tr>
</table>

<h2>页面截图</h2>
{shot_html}

<h2>原始数据（field_reliable / 图片元数据）</h2>
<pre>{_esc(json.dumps({'field_reliable': reliable, 'image_meta': images},
                     ensure_ascii=False, indent=2))}</pre>
</div></body></html>
"""

    path = run_dir / "preview.html"
    path.write_text(document, encoding="utf-8")
    return path
