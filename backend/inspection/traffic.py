"""千牛「商品分析」导出文件的解析与入库。

设计取舍：
- **列名容错**。千牛不同版本的导列表头不一样（「访客数」/「访客」/「UV」），
  用别名表按归一化列名匹配，匹配不到的列原样回传给前端，让用户看到差在哪。
- **按 (store, item_id, period_days) 覆盖**。同一商品同一周期重复导入时以最新为准，
  不产生重复行，历史周期（7 天 / 30 天）互不覆盖。
- **不猜单位**。金额去掉 ¥ 和千分位、百分比除以 100、"1.2万" 展开为 12000；
  解析失败一律存 None，绝不填 0 —— 0 会污染后续转化率计算。
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, time
from html.parser import HTMLParser
from pathlib import Path

from sqlmodel import Session, func, select

from inspection.models import ItemTraffic

# 标准字段 → 可能的表头写法（归一化后比较）
# 覆盖生意参谋「商品效果 / 商品360」与千牛「商品分析」两套导出的常见列名
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "item_id": (
        "商品id", "宝贝id", "商品编号", "宝贝编号", "商品", "宝贝",
        "商品链接", "宝贝链接", "itemid", "id",
    ),
    "title": (
        "商品名称", "商品标题", "宝贝名称", "宝贝标题", "商品简称", "标题", "title",
    ),
    "visitors": ("访客数", "访客", "商品访客数", "uv", "访客人数", "visitors"),
    "page_views": ("浏览量", "商品浏览量", "pv", "浏览量pv", "pageviews"),
    "pay_buyers": ("支付买家数", "支付人数", "买家数", "paybuyers"),
    "pay_units": ("支付件数", "支付子订单数", "件数", "payunits"),
    "pay_amount": ("支付金额", "支付金额元", "成交金额", "payamount"),
    # 商品支付转化率必须排在「转化率」包含匹配之前：报表里同时有「下单转化率」，
    # 否则会话会把下单转化率当成支付转化率（两者差得很远）。
    "conversion_rate": ("商品支付转化率", "支付转化率", "转化率", "conversionrate"),
    "cart_units": ("加购件数", "加购人数", "商品加购件数", "加购", "cartunits"),
    "fav_units": ("收藏件数", "收藏人数", "商品收藏件数", "收藏", "favunits"),
    # ── 承接质量：这些列一直在导出文件里，之前没认 ──
    "avg_stay_seconds": ("平均停留时长", "停留时长", "avgstay"),
    "bounce_rate": ("商品详情页跳出率", "详情页跳出率", "跳出率", "bouncerate"),
    "cart_buyers": ("商品加购人数", "加购人数", "cartbuyers"),
    "order_buyers": ("下单买家数", "下单人数", "orderbuyers"),
    "order_amount": ("下单金额", "orderamount"),
    "order_conversion_rate": ("下单转化率", "orderconversionrate"),
    "search_visitors": ("搜索引导访客数", "搜索访客数", "searchvisitors"),
    "search_conversion_rate": ("搜索引导支付转化率", "搜索引导转化率"),
}

# 表头定位用的关键词：一行里命中 ≥2 个才认作表头
_HEADER_HINTS = (
    "商品id", "宝贝id", "商品名称", "商品标题", "访客", "浏览量",
    "支付金额", "支付买家", "支付件数", "转化率", "加购", "收藏",
)

_ID_IN_TEXT_RE = re.compile(r"[?&]id=(\d+)")
_DATE_RE = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})")


def parse_period(text: str) -> tuple[date, date] | None:
    """从文件名或文本里解析统计周期。

    生意参谋文件名形如「【生意参谋平台】商品_全部_2026-10-21_2026-10-27.xls」，
    取前两个日期作为起止；只有一个日期时视为单日。
    """
    hits = _DATE_RE.findall(text or "")
    if not hits:
        return None
    try:
        dates = [date(int(y), int(m), int(d)) for y, m, d in hits]
    except ValueError:
        return None
    if len(dates) == 1:
        return dates[0], dates[0]
    return min(dates[0], dates[1]), max(dates[0], dates[1])


def period_label(start: date, end: date) -> str:
    return f"{start.isoformat()} ~ {end.isoformat()}"

_NUM_CLEAN_RE = re.compile(r"[,\s¥￥$]")
_INT_FIELDS = {
    "visitors", "page_views", "pay_buyers", "pay_units", "cart_units", "fav_units",
    "cart_buyers", "order_buyers", "search_visitors",
}
_RATE_FIELDS = {
    "conversion_rate", "bounce_rate", "order_conversion_rate", "search_conversion_rate",
}


def _normalize_key(text: object) -> str:
    """表头归一化：去空格、括号内容、下划线，转小写。"""
    raw = str(text or "")
    raw = re.sub(r"[（(].*?[)）]", "", raw)
    raw = re.sub(r"[\s_\-—:：]", "", raw)
    return raw.strip().lower()


def _to_number(text: object) -> float | None:
    if text is None:
        return None
    raw = _NUM_CLEAN_RE.sub("", str(text)).lstrip("≈~<>")
    if not raw or raw in {"-", "--", "—", "null", "None"}:
        return None
    scale = 1.0
    if raw.endswith("万"):
        scale, raw = 10000.0, raw[:-1]
    elif raw.endswith("亿"):
        scale, raw = 100000000.0, raw[:-1]
    try:
        return float(raw) * scale
    except ValueError:
        return None


def _to_int(text: object) -> int | None:
    value = _to_number(text)
    return None if value is None else int(round(value))


def _to_rate(text: object) -> float | None:
    """转化率统一存 0–1。'2.35%' → 0.0235；裸 2.35 视为百分比。"""
    if text is None:
        return None
    raw = str(text).strip()
    if not raw or raw in {"-", "--", "—"}:
        return None
    has_pct = "%" in raw
    value = _to_number(raw.replace("%", ""))
    if value is None:
        return None
    if has_pct or value > 1:
        value = value / 100
    return round(value, 6)


def _decode(content: bytes) -> str:
    """生意参谋导出的文本可能是 UTF-8 也可能是 GBK。"""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _read_xlsx(content: bytes) -> list[list[list]]:
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    return [
        [list(row) for row in sheet.iter_rows(values_only=True)]
        for sheet in workbook.worksheets
    ]


def _read_xls(content: bytes) -> list[list[list]]:
    """真 BIFF 格式的 .xls（OLE2 文件头）。需要 xlrd。"""
    try:
        import xlrd
    except ImportError as exc:  # noqa: TRY003
        raise ValueError(
            "这个 .xls 是老版二进制格式（不是网页表格），需要 xlrd 才能读。"
            "两个办法任选：① 在 Excel 里「另存为」.xlsx 再导入；"
            "② 后端执行 pip install xlrd"
        ) from exc

    book = xlrd.open_workbook(file_contents=content)
    return [
        [sheet.row_values(index) for index in range(sheet.nrows)]
        for sheet in book.sheets()
    ]


class _TableParser(HTMLParser):
    """从 HTML 里抽 <table>。生意参谋导出的 .xls 常常是这种。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._rows: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._rows = []
        elif tag == "tr" and self._rows is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).replace("\xa0", " ").strip())
            self._cell = None
        elif tag == "tr" and self._row is not None and self._rows is not None:
            if any(cell for cell in self._row):
                self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._rows is not None:
            if self._rows:
                self.tables.append(self._rows)
            self._rows = None


def _read_html(content: bytes) -> list[list[list]]:
    parser = _TableParser()
    parser.feed(_decode(content))
    if not parser.tables:
        raise ValueError("文件里没有找到表格（<table>）")
    # 行数最多的表最可能是数据明细，其余多为页头/页脚
    return sorted(parser.tables, key=len, reverse=True)


def _read_csv(content: bytes) -> list[list[list]]:
    return [[row for row in csv.reader(io.StringIO(_decode(content)))]]


def read_sheets(filename: str, content: bytes) -> list[list[list]]:
    """读文件为多个二维表（一个 sheet 一张表）。

    按**文件头**判断真实格式，不看扩展名——生意参谋导出的 `.xls`
    多半是 HTML 表格，用扩展名判断会误伤。

    - `PK\\x03\\x04` → xlsx（改过扩展名也能读）
    - `\\xd0\\xcf\\x11\\xe0` → 老版 BIFF .xls（需要 xlrd）
    - 含 `<table` → HTML 表格
    - 其余 → CSV / 文本
    """
    head = content[:8]
    if head.startswith(b"PK\x03\x04"):
        return _read_xlsx(content)
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return _read_xls(content)

    suffix = Path(filename).suffix.lower()
    lowered = content[:2048].lower()
    if suffix in {".xls", ".htm", ".html"} or b"<table" in lowered or b"<html" in lowered:
        return _read_html(content)
    if suffix in {".xlsx", ".xlsm"}:
        return _read_xlsx(content)
    return _read_csv(content)


def read_table(filename: str, content: bytes) -> list[list]:
    """读第一个 sheet（兼容旧调用）。"""
    sheets = read_sheets(filename, content)
    return sheets[0] if sheets else []


def _row_score(row: list) -> int:
    keys = [_normalize_key(cell) for cell in row if cell not in (None, "")]
    return sum(1 for key in keys if any(hint in key for hint in _HEADER_HINTS))


def locate_header(table: list[list], limit: int = 15) -> int:
    """在前若干行里找表头行（命中关键词最多的一行）。

    生意参谋导出一般前 1–3 行是标题/日期/口径说明，直接取第一行会解析失败。
    """
    best_index, best_score = -1, 0
    for index, row in enumerate(table[:limit]):
        score = _row_score(row)
        if score > best_score:
            best_index, best_score = index, score
    if best_score < 2:
        raise ValueError("找不到表头行（前 15 行里没有「商品ID / 访客数 / 支付金额」这类列名）")
    return best_index


def build_header(table: list[list], header_index: int) -> tuple[list[str], int]:
    """返回 (表头, 数据起始行)。

    处理两种常见形态：
    - 单行表头 → 原样使用；
    - 两行表头（上行是「支付」这类合并分组，下行为子列名）→ 用下行补空位。
      只补空位、不拼接，避免出现「商品商品名称」这种错误列名。
    """
    header_row = table[header_index]
    headers = ["" if cell is None else str(cell).strip() for cell in header_row]
    data_start = header_index + 1

    next_row = table[header_index + 1] if header_index + 1 < len(table) else []
    if next_row and _row_score(next_row) >= 2:
        for index in range(len(headers)):
            if not headers[index] and index < len(next_row) and next_row[index] not in (None, ""):
                headers[index] = str(next_row[index]).strip()
        data_start = header_index + 2

    return headers, data_start


def _extract_item_id(cell: object) -> str:
    """商品 ID 可能是纯数字、浮点（1234567890.0）或商品链接。"""
    if cell in (None, ""):
        return ""
    text = str(cell).strip()
    if text.isdigit():
        return text
    match = _ID_IN_TEXT_RE.search(text)
    if match:
        return match.group(1)
    integer_part = text.split(".")[0]
    return integer_part if integer_part.isdigit() else ""


def map_columns(headers: list) -> tuple[dict[int, str], list[str]]:
    """返回 (列索引 → 标准字段, 未识别的表头)。

    先精确匹配，再做包含匹配；一个字段只取第一个命中的列。
    """
    normalized = [_normalize_key(item) for item in headers]
    mapping: dict[int, str] = {}
    used: set[str] = set()

    for field, aliases in FIELD_ALIASES.items():
        for idx, key in enumerate(normalized):
            if not key or idx in mapping:
                continue
            if key in aliases:
                mapping[idx] = field
                used.add(field)
                break

    for field, aliases in FIELD_ALIASES.items():
        if field in used:
            continue
        for idx, key in enumerate(normalized):
            if not key or idx in mapping:
                continue
            if any(alias in key for alias in aliases if len(alias) >= 2):
                mapping[idx] = field
                used.add(field)
                break

    unknown = [
        str(headers[idx]) for idx in range(len(headers))
        if idx not in mapping and _normalize_key(headers[idx])
    ]
    return mapping, unknown


def _collect(table: list[list], data_start: int, mapping: dict[int, str]) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    errors: list[str] = []

    for offset in range(data_start, len(table)):
        row = table[offset]
        if not row or all(cell in (None, "") for cell in row):
            continue

        record: dict = {}
        for idx, field in mapping.items():
            cell = row[idx] if idx < len(row) else None
            if field == "item_id":
                record[field] = _extract_item_id(cell)
            elif field == "title":
                record[field] = str(cell).strip() if cell not in (None, "") else None
            elif field in _RATE_FIELDS:
                record[field] = _to_rate(cell)
            elif field in _INT_FIELDS:
                record[field] = _to_int(cell)
            else:
                record[field] = _to_number(cell)

        if not record.get("item_id"):
            # 千牛/生意参谋导出常在末尾追加「合计」行，不算错误
            first_cell = str(row[0]) if row and row[0] is not None else ""
            if any(word in first_cell for word in ("合计", "总计", "小计", "汇总")):
                continue
            errors.append(f"第 {offset + 1} 行：商品 ID 无效")
            continue
        records.append(record)

    return records, errors


def parse_rows(
    filename: str, content: bytes
) -> tuple[list[dict], list[dict], list[str], list[str]]:
    """解析文件为记录列表。返回 (记录, 识别到的列, 未识别列, 行级错误)。

    会逐个 sheet 尝试定位表头，跳过「数据说明」这类无表头的表。
    """
    sheets = read_sheets(filename, content)
    if not sheets:
        raise ValueError("文件为空")

    last_error: Exception | None = None

    for table in sheets:
        if not table:
            continue
        try:
            header_index = locate_header(table)
        except ValueError as exc:
            last_error = exc
            continue

        headers, data_start = build_header(table, header_index)
        mapping, unknown = map_columns(headers)

        if "item_id" not in mapping.values():
            preview = "、".join(header for header in headers if header)[:300]
            last_error = ValueError(
                "没有找到商品 ID 列。识别到的表头：" + (preview or "（空）")
            )
            continue

        records, errors = _collect(table, data_start, mapping)
        recognized = [
            {"field": field, "column": headers[idx]}
            for idx, field in mapping.items()
        ]
        return records, recognized, unknown, errors

    raise last_error or ValueError("没有找到可解析的数据表")


def upsert_traffic(
    session: Session,
    records: list[dict],
    *,
    store: int = 1,
    period_start: date,
    period_end: date,
    source_file: str | None = None,
) -> dict:
    """按 (store, item_id, period_start, period_end) 覆盖写入。

    同一期重复导入覆盖，不同期各存一份 —— 这是多期对比的基础。
    同时清理旧格式（没有日期）的遗留记录，避免同一批商品被算两次。
    """
    days = (period_end - period_start).days + 1
    start_dt = datetime.combine(period_start, time.min)
    end_dt = datetime.combine(period_end, time.max)

    legacy = session.exec(
        select(ItemTraffic).where(
            ItemTraffic.store == store,
            ItemTraffic.period_start.is_(None),
        )
    ).all()
    for row in legacy:
        session.delete(row)

    imported = 0
    for record in records:
        existing = session.exec(
            select(ItemTraffic).where(
                ItemTraffic.store == store,
                ItemTraffic.item_id == record["item_id"],
                ItemTraffic.period_start == start_dt,
                ItemTraffic.period_end == end_dt,
            )
        ).first()

        payload = {
            key: value
            for key, value in record.items()
            if key in ItemTraffic.model_fields and key not in {"id", "item_id"}
        }

        if existing is None:
            session.add(
                ItemTraffic(
                    item_id=record["item_id"],
                    store=store,
                    period_days=days,
                    period_start=start_dt,
                    period_end=end_dt,
                    source_file=source_file,
                    imported_at=datetime.now(),
                    **payload,
                )
            )
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.period_days = days
            existing.source_file = source_file
            existing.imported_at = datetime.now()
            session.add(existing)
        imported += 1

    session.commit()
    return {
        "imported": imported,
        "cleaned_legacy": len(legacy),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "period_days": days,
        "store": store,
    }


MIN_MEANINGFUL_VISITORS = 50
"""访客低于这个数，转化率没有统计意义（1 单就能翻倍）。"""

LOW_RATE_RATIO = 0.6
"""转化率低于店铺均值的这个比例，才算「明显偏低」。

全店清单和单品诊断共用这一个阈值 —— 两处各定一套会导致
同一商品在一处报问题、另一处不报。
"""


def _rate(buyers: int, visitors: int) -> float:
    """统一转化率口径：支付买家数 ÷ 访客数。

    不用报表里的 conversion_rate 字段 —— 实测它与这两个数不一致
    （差 0.1–2.7 个百分点），混用会让同一商品在不同位置显示不同转化率。
    """
    return buyers / visitors if visitors else 0.0


def list_periods(session: Session, *, store: int = 1) -> list[dict]:
    """已导入的期次列表（新到旧）。"""
    rows = session.exec(
        select(
            ItemTraffic.period_start,
            ItemTraffic.period_end,
            ItemTraffic.period_days,
            func.count(),
        )
        .where(
            ItemTraffic.store == store,
            ItemTraffic.period_start.is_not(None),
        )
        .group_by(
            ItemTraffic.period_start, ItemTraffic.period_end, ItemTraffic.period_days
        )
        .order_by(ItemTraffic.period_start.desc())
    ).all()

    periods = []
    for start, end, days, count in rows:
        if start is None or end is None:
            continue
        periods.append(
            {
                "period_start": start.date().isoformat(),
                "period_end": end.date().isoformat(),
                "period_days": days,
                "item_count": count,
                "label": f"{start.date().isoformat()} ~ {end.date().isoformat()}",
            }
        )
    return periods


def resolve_period(
    session: Session, *, store: int, period_start: date | None, period_end: date | None
) -> tuple[datetime, datetime] | None:
    """确定要分析的期次：指定了就用指定的，否则取最新一期。"""
    if period_start and period_end:
        return (
            datetime.combine(period_start, time.min),
            datetime.combine(period_end, time.max),
        )

    row = session.exec(
        select(ItemTraffic.period_start, ItemTraffic.period_end)
        .where(ItemTraffic.store == store, ItemTraffic.period_start.is_not(None))
        .order_by(ItemTraffic.period_start.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def _period_rows(
    session: Session, *, store: int, bounds: tuple[datetime, datetime] | None
) -> list[ItemTraffic]:
    statement = select(ItemTraffic).where(ItemTraffic.store == store)
    if bounds:
        statement = statement.where(
            ItemTraffic.period_start == bounds[0],
            ItemTraffic.period_end == bounds[1],
        )
    else:
        statement = statement.where(ItemTraffic.period_start.is_not(None))
    return list(session.exec(statement).all())


def _percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * ratio)))
    return ordered[index]


def traffic_analysis(
    session: Session,
    *,
    store: int = 1,
    period_start: date | None = None,
    period_end: date | None = None,
) -> dict:
    """流量结构分析：分档、集中度、高流量低转化清单。

    为什么不直接按「转化率排序」：这个店 85% 的商品零成交，
    按转化率排出来全是 0，没有信息量。必须先按访客分层，再看层内转化。
    """
    bounds = resolve_period(
        session, store=store, period_start=period_start, period_end=period_end
    )
    rows = _period_rows(session, store=store, bounds=bounds)
    period_info = {
        "period_start": bounds[0].date().isoformat() if bounds else None,
        "period_end": bounds[1].date().isoformat() if bounds else None,
        "period_days": rows[0].period_days if rows else 0,
    }

    if not rows:
        return {"empty": True, "item_count": 0, **period_info}

    items = [
        {
            "item_id": row.item_id,
            "title": row.title,
            "visitors": row.visitors or 0,
            "pay_buyers": row.pay_buyers or 0,
            "pay_amount": round(row.pay_amount or 0.0, 2),
            "conversion_rate": round(_rate(row.pay_buyers or 0, row.visitors or 0), 6),
        }
        for row in rows
    ]
    items.sort(key=lambda item: item["visitors"], reverse=True)

    visitors_total = sum(item["visitors"] for item in items)
    buyers_total = sum(item["pay_buyers"] for item in items)
    revenue_total = sum(item["pay_amount"] for item in items)
    overall_cr = buyers_total / visitors_total if visitors_total else 0.0
    aov = revenue_total / buyers_total if buyers_total else 0.0

    visitor_values = [item["visitors"] for item in items]

    # ── 分档：按访客量分层看转化 ──
    bands = (
        ("无访客", 0, 1),
        ("1–9 访客", 1, 10),
        ("10–49 访客", 10, 50),
        ("50–99 访客", 50, 100),
        ("100+ 访客", 100, None),
    )
    band_stats = []
    for label, low, high in bands:
        group = [
            item for item in items
            if item["visitors"] >= low and (high is None or item["visitors"] < high)
        ]
        if not group:
            continue
        group_visitors = sum(item["visitors"] for item in group)
        group_buyers = sum(item["pay_buyers"] for item in group)
        band_stats.append(
            {
                "label": label,
                "items": len(group),
                "visitors": group_visitors,
                "buyers": group_buyers,
                "conversion_rate": round(group_buyers / group_visitors, 6)
                if group_visitors
                else None,
                "revenue": round(sum(item["pay_amount"] for item in group), 2),
            }
        )

    # ── 集中度：访客是否也压在少数商品上 ──
    top10 = items[:10]
    top10_visitors = sum(item["visitors"] for item in top10)

    # ── 高流量低转化：访客够多、转化明显低于店铺均值 ──
    threshold = overall_cr * LOW_RATE_RATIO
    suspects = []
    for item in items:
        if item["visitors"] < MIN_MEANINGFUL_VISITORS:
            continue
        rate = item["conversion_rate"]
        if rate >= threshold:
            continue
        # 机会损失按商品自身客单价算；无成交时才退回全店均值，
        # 否则低客单商品会被高估、高客单商品会被压低。
        own_aov = (
            item["pay_amount"] / item["pay_buyers"] if item["pay_buyers"] else aov
        )
        expected_buyers = item["visitors"] * overall_cr
        lost_buyers = max(0.0, expected_buyers - item["pay_buyers"])
        suspects.append(
            {
                **item,
                "gap_pp": round((overall_cr - rate) * 100, 2),
                "expected_buyers": round(expected_buyers, 1),
                "lost_buyers": round(lost_buyers, 1),
                "lost_revenue": round(lost_buyers * own_aov, 2),
                "aov_basis": "self" if item["pay_buyers"] else "store",
            }
        )
    suspects.sort(key=lambda item: item["lost_revenue"], reverse=True)

    return {
        "empty": False,
        **period_info,
        "item_count": len(items),
        "totals": {
            "visitors": visitors_total,
            "buyers": buyers_total,
            "revenue": round(revenue_total, 2),
            "conversion_rate": round(overall_cr, 6),
            "aov": round(aov, 2),
        },
        "distribution": {
            "visitor_p50": _percentile(visitor_values, 0.5),
            "visitor_p75": _percentile(visitor_values, 0.75),
            "visitor_p90": _percentile(visitor_values, 0.90),
            "visitor_max": visitor_values[0] if visitor_values else 0,
            "with_traffic": sum(1 for value in visitor_values if value > 0),
            "zero_visitor": sum(1 for value in visitor_values if value == 0),
            "zero_order": sum(1 for item in items if not item["pay_buyers"]),
            "meaningful_items": sum(
                1 for value in visitor_values if value >= MIN_MEANINGFUL_VISITORS
            ),
        },
        "concentration": {
            "top10_visitors": top10_visitors,
            "top10_share": round(top10_visitors / visitors_total, 4)
            if visitors_total
            else 0.0,
            "top_items": top10,
        },
        "bands": band_stats,
        "suspects": suspects[:20],
        "suspect_rule": {
            "min_visitors": MIN_MEANINGFUL_VISITORS,
            "threshold_ratio": LOW_RATE_RATIO,
            "threshold_rate": round(threshold, 6),
        },
    }


def item_traffic(
    session: Session, *, item_id: str, store: int = 1, period_days: int = 7
) -> dict:
    """单个商品的流量表现 + 在店铺内的位置 + 一句诊断。

    诊断不做模型推断，只用两条轴的组合：流量高低（对 P75）与转化好坏（对店铺均值）。
    四种组合对应四种完全不同的动作，混在一起说就是废话。
    """
    rows = session.exec(
        select(ItemTraffic).where(
            ItemTraffic.store == store,
            ItemTraffic.period_days == period_days,
        )
    ).all()

    if not rows:
        return {"available": False, "reason": "no_data", "period_days": period_days}

    target = next((row for row in rows if row.item_id == item_id), None)
    if target is None:
        return {
            "available": False,
            "reason": "item_not_found",
            "period_days": period_days,
            "item_count": len(rows),
        }

    visitors_total = sum(row.visitors or 0 for row in rows)
    buyers_total = sum(row.pay_buyers or 0 for row in rows)
    revenue_total = sum(row.pay_amount or 0 for row in rows)
    overall_cr = buyers_total / visitors_total if visitors_total else 0.0
    aov = revenue_total / buyers_total if buyers_total else 0.0

    visitor_values = [row.visitors or 0 for row in rows]
    p50 = _percentile(visitor_values, 0.5)
    p75 = _percentile(visitor_values, 0.75)

    visitors = target.visitors or 0
    buyers = target.pay_buyers or 0
    revenue = round(target.pay_amount or 0.0, 2)
    # 转化率与全店清单同一口径现算，不读报表字段
    rate = _rate(buyers, visitors)

    # 排名：访客按全店排；转化率只在「有统计意义」的商品里排
    visitor_rank = 1 + sum(1 for value in visitor_values if value > visitors)
    meaningful = [
        row for row in rows
        if (row.visitors or 0) >= MIN_MEANINGFUL_VISITORS
    ]
    rate_rank = None
    if visitors >= MIN_MEANINGFUL_VISITORS:
        rate_rank = 1 + sum(
            1 for row in meaningful
            if _rate(row.pay_buyers or 0, row.visitors or 0) > rate
        )

    # 门槛取 P75 与 50 的较大值：这个店访客 P75 只有 8，
    # 单用分位数会把「26 个访客 0 单」误判成有流量，而它只是样本太小。
    high_traffic = visitors >= max(p75, MIN_MEANINGFUL_VISITORS)
    good_rate = rate >= overall_cr

    if visitors == 0:
        diagnosis = {
            "code": "no_traffic",
            "label": "零曝光",
            "advice": "七天没有访客。问题不在页面，在标题、类目或推广；改主图不会有任何效果。",
        }
    elif visitors < MIN_MEANINGFUL_VISITORS:
        diagnosis = {
            "code": "low_sample",
            "label": "流量不足，暂不判定转化",
            "advice": (
                f"访客 {visitors} 人，低于 {MIN_MEANINGFUL_VISITORS} 人的判定门槛，"
                "转化率没有统计意义。先解决曝光（标题 / 类目 / 推广），再回头看转化。"
            ),
        }
    elif high_traffic and not good_rate:
        diagnosis = {
            "code": "high_traffic_low_rate",
            "label": "有流量不转化",
            "advice": "访客在全店前 25%，转化却低于均值。这是最该动手的一类：查主图、详情页、价格锚点。",
        }
    elif high_traffic and good_rate:
        diagnosis = {
            "code": "healthy",
            "label": "流量与转化都正常",
            "advice": "在全店前 25% 且转化不低于均值，保持现状，把精力放到别的商品上。",
        }
    elif good_rate:
        diagnosis = {
            "code": "low_traffic_good_rate",
            "label": "转化好但没曝光",
            "advice": "转化率不低于均值，说明页面能打动人，问题是没人看到。该做的是标题优化和流量获取，不是改图。",
        }
    else:
        diagnosis = {
            "code": "low_both",
            "label": "既没流量也不转化",
            "advice": "优先级最低。先确认这个商品还值不值得留，不值得就别投入优化成本。",
        }

    expected_buyers = visitors * overall_cr
    lost_buyers = max(0.0, expected_buyers - buyers)

    return {
        "available": True,
        "period_days": period_days,
        "item": {
            "item_id": target.item_id,
            "title": target.title,
            "visitors": visitors,
            "pay_buyers": buyers,
            "pay_amount": revenue,
            "conversion_rate": round(rate, 6),
            "cart_units": target.cart_units,
            "fav_units": target.fav_units,
            # 承接质量：报表里有就带出来，没有则为 None（老数据未回填）
            "page_views": target.page_views,
            "avg_stay_seconds": target.avg_stay_seconds,
            "bounce_rate": target.bounce_rate,
            "cart_buyers": target.cart_buyers,
            "order_buyers": target.order_buyers,
            "order_amount": target.order_amount,
            "search_visitors": target.search_visitors,
        },
        "benchmark": {
            "visitor_p50": p50,
            "visitor_p75": p75,
            "conversion_rate": round(overall_cr, 6),
            "aov": round(aov, 2),
            "item_count": len(rows),
            "meaningful_items": len(meaningful),
        },
        "rank": {
            "visitor_rank": visitor_rank,
            "rate_rank": rate_rank,
            "total": len(rows),
        },
        "gap": {
            "vs_average_pp": round((rate - overall_cr) * 100, 2),
            "expected_buyers": round(expected_buyers, 1),
            "lost_buyers": round(lost_buyers, 1),
            "lost_revenue": round(lost_buyers * aov, 2),
        },
        "diagnosis": diagnosis,
    }


def traffic_overview(session: Session, *, store: int = 1, period_days: int = 7) -> dict:
    """导入后的整体流量概览（做汇总，不做排名）。"""
    rows = session.exec(
        select(ItemTraffic).where(
            ItemTraffic.store == store,
            ItemTraffic.period_days == period_days,
        )
    ).all()

    items = [
        {
            "item_id": row.item_id,
            "title": row.title,
            "visitors": row.visitors,
            "page_views": row.page_views,
            "pay_buyers": row.pay_buyers,
            "pay_units": row.pay_units,
            "pay_amount": row.pay_amount,
            "conversion_rate": row.conversion_rate,
            "cart_units": row.cart_units,
            "fav_units": row.fav_units,
        }
        for row in rows
    ]
    items.sort(key=lambda item: item["visitors"] or 0, reverse=True)

    visitors = sum(item["visitors"] or 0 for item in items)
    buyers = sum(item["pay_buyers"] or 0 for item in items)
    revenue = sum(item["pay_amount"] or 0 for item in items)
    carts = sum(item["cart_units"] or 0 for item in items)
    favs = sum(item["fav_units"] or 0 for item in items)

    zero_visitor = [item for item in items if not item["visitors"]]
    return {
        "period_days": period_days,
        "item_count": len(items),
        "totals": {
            "visitors": visitors,
            "page_views": sum(item["page_views"] or 0 for item in items),
            "pay_buyers": buyers,
            "pay_amount": round(revenue, 2),
            "conversion_rate": round(buyers / visitors, 6) if visitors else None,
            "cart_rate": round(carts / visitors, 6) if visitors else None,
            "fav_rate": round(favs / visitors, 6) if visitors else None,
            "aov": round(revenue / buyers, 2) if buyers else None,
        },
        "zero_visitor_items": len(zero_visitor),
        "items": items,
    }
