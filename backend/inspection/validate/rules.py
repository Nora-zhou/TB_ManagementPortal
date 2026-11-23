"""013-I02：断言引擎。

把两类判断分开，这是本模块唯一的设计要点：

- **contract（契约）**：字段在不在、值域对不对。
  失败 = 这份快照不可信，下游指标应跳过该字段。
- **rule（规则）**：值满不满足业务阈值。
  失败本身就是结论（例如「库存 33 个月清不完」），不影响数据可信度。

判定函数返回 `None` 表示「数据不足以判定」——既不算通过也不算失败。
把「没采到」和「采到了不合格」混成一个 0，是这类系统最常见的错误。

阈值一律从 `backend/config/rules.json` 读，代码里不写死。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "rules.json"

DEFAULT_THRESHOLDS: dict = {
    "title_len_min": 5,
    "title_len_max": 120,
    "image_count_min": 1,
    "image_count_max": 10,
    "image_count_min_recommend": 5,
    "image_ratio": 0.75,
    "image_ratio_tolerance": 0.02,
    "image_ratio_min_share": 1.0,
    "detail_image_min": 8,
    "stock_turnover_max_months": 6,
    "sku_price_spread_max_pct": 100,
    "review_count_min": 1,
}

SOURCE_VALUES = ("api", "page_xhr", "page_dom")

Outcome = tuple[bool, str] | None
Checker = Callable[[dict, dict], Outcome]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    kind: str                 # contract | rule
    level: str                # alert | warn | info
    field: str | None         # 关联字段，下游可据此跳过
    title: str                # 人读的检查项名称
    expected: str
    message: str              # 不通过时的说明（说清后果）


# ── contract：数据可信 ────────────────────────────────────────────────


def _c_title(data: dict, th: dict) -> Outcome:
    title = (data.get("title") or "").strip()
    if not title:
        return False, "空"
    return th["title_len_min"] <= len(title) <= th["title_len_max"], f"{len(title)} 字"


def _c_price(data: dict, th: dict) -> Outcome:
    price = data.get("price_cents")
    if price is None:
        return False, "空"
    return price > 0, f"{price / 100:.2f} 元"


def _c_image_count(data: dict, th: dict) -> Outcome:
    count = data.get("image_count")
    if count is None:
        return False, "空"
    return th["image_count_min"] <= count <= th["image_count_max"], f"{count} 张"


def _c_detail_count(data: dict, th: dict) -> Outcome:
    """0 张也算采到了——「够不够」是规则的事（R_DETAIL_MIN）。"""
    count = data.get("detail_image_count")
    if count is None:
        return False, "空"
    return True, f"{count} 张"


def _c_source(data: dict, th: dict) -> Outcome:
    source = data.get("source") or "none"
    return source in SOURCE_VALUES, source


# ── rule：业务合格 ────────────────────────────────────────────────────


def _r_image_ratio(data: dict, th: dict) -> Outcome:
    metas = data.get("image_meta") or []
    if not metas:
        return None
    target, tol = th["image_ratio"], th["image_ratio_tolerance"]
    ok = sum(
        1
        for meta in metas
        if isinstance(meta.get("ratio"), (int, float))
        and abs(meta["ratio"] - target) <= tol
    )
    share = ok / len(metas)
    return share >= th["image_ratio_min_share"], f"{ok}/{len(metas)} 张 3:4"


def _r_image_min(data: dict, th: dict) -> Outcome:
    count = data.get("image_count")
    if count is None:
        count = len(data.get("image_meta") or []) or None
    if count is None:
        return None
    return count >= th["image_count_min_recommend"], f"{count} 张"


def _r_detail_min(data: dict, th: dict) -> Outcome:
    count = data.get("detail_image_count")
    if count is None:
        return None
    return count >= th["detail_image_min"], f"{count} 张"


def _r_stock_turnover(data: dict, th: dict) -> Outcome:
    stock = data.get("stock_total")
    sales = data.get("sales_parsed")
    if stock is None or not sales:
        return None
    months = stock / sales
    return (
        months <= th["stock_turnover_max_months"],
        f"{stock} 件 ÷ 月销 {sales} = {months:.1f} 个月",
    )


def _r_sku_spread(data: dict, th: dict) -> Outcome:
    prices = [s.get("price_cents") for s in (data.get("sku") or []) if s.get("price_cents")]
    if len(prices) < 2:
        return None
    low, high = min(prices), max(prices)
    spread = (high / low - 1) * 100
    return (
        spread <= th["sku_price_spread_max_pct"],
        f"{low / 100:.2f} ~ {high / 100:.2f} 元（跨度 {spread:.0f}%）",
    )


def _r_review(data: dict, th: dict) -> Outcome:
    count = data.get("review_count")
    if count is None:
        return None
    return count >= th["review_count_min"], f"{count} 条"


def _r_service(data: dict, th: dict) -> Outcome:
    service = data.get("service") or {}
    if not service:
        return None
    missing = [
        label
        for key, label in (
            ("freight", "邮费"),
            ("ship_aging", "发货时效"),
            ("delivery_from", "发货地"),
        )
        if not service.get(key)
    ]
    return not missing, "齐全" if not missing else f"缺{'、'.join(missing)}"


# ── 规则表 ───────────────────────────────────────────────────────────

RULES: tuple[tuple[Rule, Checker], ...] = (
    (
        Rule("C_TITLE", "contract", "alert", "title", "标题可采",
             "5–120 字", "标题缺失或长度异常，关键词覆盖无法计算"),
        _c_title,
    ),
    (
        Rule("C_PRICE", "contract", "alert", "price_cents", "主价可采",
             "> 0", "主价缺失，价格带与利润维度都无法计算"),
        _c_price,
    ),
    (
        Rule("C_IMAGE_COUNT", "contract", "alert", "image_count", "主图数量可采",
             "1–10 张", "主图数量异常，素材评分不可信"),
        _c_image_count,
    ),
    (
        Rule("C_DETAIL_COUNT", "contract", "alert", "detail_image_count", "详情图数量可采",
             "≥ 0 张", "详情图数量取不到，详情页缺口无法判断"),
        _c_detail_count,
    ),
    (
        Rule("C_SOURCE", "contract", "alert", None, "数据源有效",
             "api / page_xhr / page_dom", "解析未命中任何数据源，快照为空壳"),
        _c_source,
    ),
    (
        Rule("R_IMAGE_RATIO", "rule", "warn", "image_count", "主图比例",
             "全部 3:4", "有主图不是 3:4，首猜推荐位会被裁切"),
        _r_image_ratio,
    ),
    (
        Rule("R_IMAGE_MIN", "rule", "warn", "image_count", "主图数量",
             "≥ {image_count_min_recommend} 张",
             "主图偏少，轮播展示不充分"),
        _r_image_min,
    ),
    (
        Rule("R_DETAIL_MIN", "rule", "alert", "detail_image_count", "详情图厚度",
             "≥ {detail_image_min} 张",
             "详情图不足，转化页说服力弱"),
        _r_detail_min,
    ),
    (
        Rule("R_STOCK_TURNOVER", "rule", "alert", "stock_total", "库存周转",
             "≤ {stock_turnover_max_months} 个月",
             "按当前月销清不完库存，资金占用偏高"),
        _r_stock_turnover,
    ),
    (
        Rule("R_SKU_SPREAD", "rule", "info", "sku_json", "SKU 价格跨度",
             "≤ {sku_price_spread_max_pct}%",
             "SKU 价格带过宽，客群定位可能混乱"),
        _r_sku_spread,
    ),
    (
        Rule("R_REVIEW", "rule", "warn", "review_count", "评价数",
             "≥ {review_count_min} 条",
             "无评价，新品或评价未展示，转化阻力大"),
        _r_review,
    ),
    (
        Rule("R_SERVICE", "rule", "info", "service_json", "服务信息完整",
             "邮费 / 时效 / 发货地齐全", "服务信息不全，页面显示可能缺项"),
        _r_service,
    ),
)


def load_thresholds(path: Path | None = None) -> dict:
    """读阈值配置；文件缺失或损坏时退回内置默认值（不让报告生成失败）。"""
    target = path or RULES_PATH
    thresholds = dict(DEFAULT_THRESHOLDS)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return thresholds
    thresholds.update(payload.get("thresholds") or {})
    return thresholds


def run_assertions(data: dict, thresholds: dict | None = None) -> dict:
    """对一条快照跑全部断言。

    data 为展示结构（`to_display()` / `from_parse()`），阈值默认从配置文件读。
    """
    th = thresholds or load_thresholds()
    results: list[dict] = []
    skipped: list[str] = []

    for rule, check in RULES:
        outcome = check(data, th)
        if outcome is None:
            skipped.append(rule.rule_id)
            continue
        passed, actual = outcome
        results.append(
            {
                "rule_id": rule.rule_id,
                "kind": rule.kind,
                "level": rule.level,
                "field": rule.field,
                "title": rule.title,
                "passed": 1 if passed else 0,
                "expected": rule.expected.format(**th),
                "actual": str(actual)[:500],
                "message": "" if passed else rule.message,
            }
        )

    failed = [item for item in results if not item["passed"]]
    return {
        "rule_version": th.get("version", "v1"),
        "results": results,
        "summary": {
            "total": len(results),
            "passed": len(results) - len(failed),
            "failed": len(failed),
            "skipped": len(skipped),
            "contract_failed": sum(1 for item in failed if item["kind"] == "contract"),
            "rule_failed": sum(1 for item in failed if item["kind"] == "rule"),
            "skipped_rules": skipped,
        },
    }
