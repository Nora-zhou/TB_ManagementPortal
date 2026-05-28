# Implementation Plan: 首页利润分析仪表盘

**Feature Branch**: `009-home-profit-dashboard`
**Spec**: [specs/009-home-profit-dashboard/spec.md](spec.md)
**Status**: Ready for Implementation

---

## Technical Context

| Item | Detail |
|------|--------|
| Backend framework | FastAPI + SQLModel + SQLite |
| Frontend framework | Vue 3 Composition API + Vue Router (hash history) + ECharts |
| New DB tables | None — reads from existing `SubOrder` + `PurchaseOrder` |
| New backend files | `backend/routes/stats.py` |
| New frontend files | `frontend/src/components/HomeDashboard.vue`, `frontend/src/api/stats.js` |
| Modified backend files | `backend/schemas.py`, `backend/main.py` |
| Modified frontend files | `frontend/src/main.js`, `frontend/src/App.vue` |

---

## Architecture Overview

```
[Browser] GET /#/
    └─> HomeDashboard.vue
          ├─ filter inputs (startMonth, endMonth)
          ├─> fetchProfitMonthly()  ──> GET /api/stats/profit-monthly
          │                               └─ routes/stats.py
          │                                    ├─ SubOrder grouped query
          │                                    └─ PurchaseOrder grouped query
          ├─ KPI cards (CSS Grid, 3-col × 3-row)
          ├─ Trend chart (dual Y-axis, line+bar)
          └─ Pie chart  (donut, 3 sectors)
```

---

## Phase 1: Backend

### Step 1.1 — Add schemas to `backend/schemas.py`

Append the following classes at the end of `backend/schemas.py`:

```python
# ---------------------------------------------------------------------------
# HomeDashboard profit schemas (009-home-profit-dashboard)
# ---------------------------------------------------------------------------

class ProfitMonthlySeries(BaseModel):
    revenue_s1:    list[float]
    revenue_s2:    list[float]
    cost_s1:       list[float]
    cost_s2:       list[float]
    refund_s1:     list[float]
    refund_s2:     list[float]
    profit_s1:     list[float]
    profit_s2:     list[float]
    total_revenue: list[float]
    total_cost:    list[float]
    total_refund:  list[float]
    total_profit:  list[float]


class ProfitMonthlyKPI(BaseModel):
    revenue_s1:    float
    revenue_s2:    float
    cost_s1:       float
    cost_s2:       float
    refund_s1:     float
    refund_s2:     float
    profit_s1:     float
    profit_s2:     float
    total_revenue: float
    total_cost:    float
    total_refund:  float
    total_profit:  float


class ProfitMonthlyResponse(BaseModel):
    months: list[str]
    series: ProfitMonthlySeries
    kpi:    ProfitMonthlyKPI
```

### Step 1.2 — Create `backend/routes/stats.py`

Create a new file `backend/routes/stats.py` with the full content below.

**SQL logic:**

For **SubOrder** monthly aggregation:
```sql
SELECT
  store,
  strftime('%Y-%m', COALESCE(paid_at, created_at)) AS month_key,
  SUM(CASE WHEN status = '交易成功' THEN buyer_paid ELSE 0.0 END)                              AS revenue,
  SUM(CASE WHEN status IN ('交易成功','交易关闭') THEN CAST(refund_amount AS FLOAT) ELSE 0.0 END) AS refund
FROM suborder
WHERE COALESCE(paid_at, created_at) IS NOT NULL
  [AND strftime('%Y-%m', COALESCE(paid_at, created_at)) >= :start_month]
  [AND strftime('%Y-%m', COALESCE(paid_at, created_at)) <= :end_month]
GROUP BY store, strftime('%Y-%m', COALESCE(paid_at, created_at))
```

For **PurchaseOrder** monthly aggregation:
```sql
SELECT
  store,
  strftime('%Y-%m', COALESCE(paid_at, created_at)) AS month_key,
  SUM(paid_amount) AS cost
FROM purchaseorder
WHERE status NOT IN ('等待买家付款', '退款中', '交易关闭')
  AND COALESCE(paid_at, created_at) IS NOT NULL
  [AND strftime('%Y-%m', COALESCE(paid_at, created_at)) >= :start_month]
  [AND strftime('%Y-%m', COALESCE(paid_at, created_at)) <= :end_month]
GROUP BY store, strftime('%Y-%m', COALESCE(paid_at, created_at))
```

**Profit formula:**
```
profit_sN[i] = revenue_sN[i] - refund_sN[i] - cost_sN[i]
total_profit[i] = profit_s1[i] + profit_s2[i]
```
KPI values are the sum of each series list across all months.

**Full file content:**

```python
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Float as SAFloat
from sqlalchemy import case
from sqlalchemy import cast as sa_cast
from sqlmodel import Session, func, select

from database import get_session
from models import PurchaseOrder, SubOrder
from schemas import ProfitMonthlyKPI, ProfitMonthlySeries, ProfitMonthlyResponse

router = APIRouter(prefix="/stats", tags=["stats"])

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_PO_EXCLUDED = ("等待买家付款", "退款中", "交易关闭")
_SO_SUCCESS   = "交易成功"
_SO_REFUND_STATUSES = ("交易成功", "交易关闭")


def _validate_month(value: Optional[str], param: str) -> None:
    if value is not None and not _MONTH_RE.match(value):
        raise HTTPException(status_code=422, detail=f"{param} 格式非法，应为 YYYY-MM")


# ---------------------------------------------------------------------------
# GET /api/stats/profit-monthly
# ---------------------------------------------------------------------------

@router.get("/profit-monthly", response_model=ProfitMonthlyResponse)
def get_profit_monthly(
    start_month: Optional[str] = Query(default=None),
    end_month:   Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
):
    _validate_month(start_month, "start_month")
    _validate_month(end_month,   "end_month")

    # ------------------------------------------------------------------
    # Query 1: SubOrder — revenue and refund grouped by (store, month)
    # ------------------------------------------------------------------
    so_coalesce = func.coalesce(SubOrder.paid_at, SubOrder.created_at)
    so_month    = func.strftime("%Y-%m", so_coalesce)

    so_stmt = (
        select(
            SubOrder.store,
            so_month.label("month_key"),
            func.sum(
                case((SubOrder.status == _SO_SUCCESS, SubOrder.buyer_paid), else_=0.0)
            ).label("revenue"),
            func.sum(
                case(
                    (SubOrder.status.in_(list(_SO_REFUND_STATUSES)),
                     sa_cast(SubOrder.refund_amount, SAFloat)),
                    else_=0.0,
                )
            ).label("refund"),
        )
        .where(so_coalesce.isnot(None))
        .group_by(SubOrder.store, so_month)
    )
    if start_month:
        so_stmt = so_stmt.where(so_month >= start_month)
    if end_month:
        so_stmt = so_stmt.where(so_month <= end_month)

    so_rows = session.exec(so_stmt).all()

    # ------------------------------------------------------------------
    # Query 2: PurchaseOrder — cost grouped by (store, month)
    # ------------------------------------------------------------------
    po_coalesce = func.coalesce(PurchaseOrder.paid_at, PurchaseOrder.created_at)
    po_month    = func.strftime("%Y-%m", po_coalesce)

    po_stmt = (
        select(
            PurchaseOrder.store,
            po_month.label("month_key"),
            func.sum(PurchaseOrder.paid_amount).label("cost"),
        )
        .where(
            po_coalesce.isnot(None),
            PurchaseOrder.status.not_in(list(_PO_EXCLUDED)),
        )
        .group_by(PurchaseOrder.store, po_month)
    )
    if start_month:
        po_stmt = po_stmt.where(po_month >= start_month)
    if end_month:
        po_stmt = po_stmt.where(po_month <= end_month)

    po_rows = session.exec(po_stmt).all()

    # ------------------------------------------------------------------
    # Merge into dict: (store, month_key) -> {revenue, refund, cost}
    # ------------------------------------------------------------------
    data: dict[tuple[int, str], dict] = {}

    for r in so_rows:
        key = (int(r.store), r.month_key)
        if key not in data:
            data[key] = {"revenue": 0.0, "refund": 0.0, "cost": 0.0}
        data[key]["revenue"] = float(r.revenue or 0.0)
        data[key]["refund"]  = float(r.refund  or 0.0)

    for r in po_rows:
        key = (int(r.store), r.month_key)
        if key not in data:
            data[key] = {"revenue": 0.0, "refund": 0.0, "cost": 0.0}
        data[key]["cost"] = float(r.cost or 0.0)

    # ------------------------------------------------------------------
    # Build sorted month list (union of both tables)
    # ------------------------------------------------------------------
    all_months = sorted({mk for (_, mk) in data.keys()})

    if not all_months:
        empty_kpi = ProfitMonthlyKPI(
            revenue_s1=0.0, revenue_s2=0.0,
            cost_s1=0.0,    cost_s2=0.0,
            refund_s1=0.0,  refund_s2=0.0,
            profit_s1=0.0,  profit_s2=0.0,
            total_revenue=0.0, total_cost=0.0,
            total_refund=0.0,  total_profit=0.0,
        )
        empty_series = ProfitMonthlySeries(
            revenue_s1=[], revenue_s2=[],
            cost_s1=[],    cost_s2=[],
            refund_s1=[],  refund_s2=[],
            profit_s1=[],  profit_s2=[],
            total_revenue=[], total_cost=[],
            total_refund=[],  total_profit=[],
        )
        return ProfitMonthlyResponse(months=[], series=empty_series, kpi=empty_kpi)

    def _v(store: int, month: str, field: str) -> float:
        return data.get((store, month), {}).get(field, 0.0)

    # Per-store monthly lists
    rev_s1    = [_v(1, m, "revenue") for m in all_months]
    rev_s2    = [_v(2, m, "revenue") for m in all_months]
    cost_s1   = [_v(1, m, "cost")    for m in all_months]
    cost_s2   = [_v(2, m, "cost")    for m in all_months]
    refund_s1 = [_v(1, m, "refund")  for m in all_months]
    refund_s2 = [_v(2, m, "refund")  for m in all_months]

    profit_s1 = [round(rev_s1[i] - refund_s1[i] - cost_s1[i], 2)  for i in range(len(all_months))]
    profit_s2 = [round(rev_s2[i] - refund_s2[i] - cost_s2[i], 2)  for i in range(len(all_months))]

    total_revenue = [round(rev_s1[i]  + rev_s2[i],    2) for i in range(len(all_months))]
    total_cost    = [round(cost_s1[i] + cost_s2[i],   2) for i in range(len(all_months))]
    total_refund  = [round(refund_s1[i] + refund_s2[i], 2) for i in range(len(all_months))]
    total_profit  = [round(profit_s1[i] + profit_s2[i],  2) for i in range(len(all_months))]

    def _sum(lst: list[float]) -> float:
        return round(sum(lst), 2)

    kpi = ProfitMonthlyKPI(
        revenue_s1=_sum(rev_s1),    revenue_s2=_sum(rev_s2),
        cost_s1=_sum(cost_s1),      cost_s2=_sum(cost_s2),
        refund_s1=_sum(refund_s1),  refund_s2=_sum(refund_s2),
        profit_s1=round(_sum(rev_s1) - _sum(refund_s1) - _sum(cost_s1), 2),
        profit_s2=round(_sum(rev_s2) - _sum(refund_s2) - _sum(cost_s2), 2),
        total_revenue=round(_sum(rev_s1)  + _sum(rev_s2),    2),
        total_cost=round(_sum(cost_s1)    + _sum(cost_s2),   2),
        total_refund=round(_sum(refund_s1) + _sum(refund_s2), 2),
        total_profit=round(
            _sum(rev_s1) + _sum(rev_s2)
            - _sum(refund_s1) - _sum(refund_s2)
            - _sum(cost_s1)   - _sum(cost_s2),
            2,
        ),
    )

    series = ProfitMonthlySeries(
        revenue_s1=rev_s1,    revenue_s2=rev_s2,
        cost_s1=cost_s1,      cost_s2=cost_s2,
        refund_s1=refund_s1,  refund_s2=refund_s2,
        profit_s1=profit_s1,  profit_s2=profit_s2,
        total_revenue=total_revenue, total_cost=total_cost,
        total_refund=total_refund,   total_profit=total_profit,
    )

    return ProfitMonthlyResponse(months=all_months, series=series, kpi=kpi)
```

### Step 1.3 — Register the router in `backend/main.py`

Add two lines to `backend/main.py`:

**Import** (after existing router imports):
```python
from routes.stats import router as stats_router
```

**Registration** (after existing `app.include_router` calls):
```python
app.include_router(stats_router, prefix="/api")
```

**Exact diff** — change this block:
```python
# BEFORE
from routes.products import router as products_router
from routes.orders import router as orders_router
from routes.sub_orders import router as sub_orders_router
from routes.purchase_orders import router as purchase_orders_router
```
```python
# AFTER
from routes.products import router as products_router
from routes.orders import router as orders_router
from routes.sub_orders import router as sub_orders_router
from routes.purchase_orders import router as purchase_orders_router
from routes.stats import router as stats_router
```

And:
```python
# BEFORE
app.include_router(products_router, prefix="/api")
app.include_router(orders_router, prefix="/api")
app.include_router(sub_orders_router, prefix="/api")
app.include_router(purchase_orders_router, prefix="/api")
```
```python
# AFTER
app.include_router(products_router, prefix="/api")
app.include_router(orders_router, prefix="/api")
app.include_router(sub_orders_router, prefix="/api")
app.include_router(purchase_orders_router, prefix="/api")
app.include_router(stats_router, prefix="/api")
```

---

## Phase 2: Frontend

### Step 2.1 — Create `frontend/src/api/stats.js`

```javascript
const BASE = '/api/stats'

/**
 * Fetch monthly profit data for the home dashboard.
 * @param {{ startMonth?: string, endMonth?: string }} options
 * @returns {Promise<{ months: string[], series: object, kpi: object }>}
 */
export async function fetchProfitMonthly({ startMonth, endMonth } = {}) {
  const p = new URLSearchParams()
  if (startMonth) p.append('start_month', startMonth)
  if (endMonth)   p.append('end_month',   endMonth)
  const url = `${BASE}/profit-monthly${p.toString() ? '?' + p.toString() : ''}`
  const res = await fetch(url)
  if (!res.ok) throw await res.json()
  return res.json()
}
```

### Step 2.2 — Create `frontend/src/components/HomeDashboard.vue`

Full component structure:

**Script setup responsibilities:**
- `startMonth` / `endMonth` refs (text inputs, YYYY-MM format)
- `MONTH_RE = /^\d{4}-\d{2}$/` validation guard
- `loading`, `error`, `data` refs
- `loadData()` — validates inputs, calls `fetchProfitMonthly`, updates `data`
- `onMounted(loadData)` + `watch([startMonth, endMonth], loadData)`
- `kpi` computed — falls back to all-zero object when `data` is null
- `fmt(n)` — formats number with 2 decimal places + thousands separator
- `trendOption` computed — dual Y-axis ECharts config
- `pieOption` computed — donut ECharts config with profit-floor-at-zero logic

**Dual Y-axis trend chart config pattern:**
```javascript
const trendOption = computed(() => {
  if (!data.value?.months?.length) return {}
  const { months, series: s } = data.value
  return {
    tooltip: {
      trigger: 'axis',
      formatter(params) {
        const month = params[0].axisValue
        let html = `<b>${month}</b><br/>`
        for (const p of params) {
          const val = `¥${Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
          html += `${p.marker}${p.seriesName}：${val}<br/>`
        }
        return html
      },
    },
    legend: { type: 'scroll', bottom: 0 },
    grid: { left: '3%', right: '8%', bottom: '15%', containLabel: true },
    xAxis: { type: 'category', data: months, boundaryGap: false },
    yAxis: [
      { type: 'value', name: '金额（元）', position: 'left',
        axisLabel: { formatter: v => `¥${(v / 1000).toFixed(0)}K` } },
      { type: 'value', name: '分店利润（元）', position: 'right',
        axisLabel: { formatter: v => `¥${(v / 1000).toFixed(0)}K` } },
    ],
    series: [
      { name: '总收入', type: 'line', smooth: true, yAxisIndex: 0,
        data: s.total_revenue, itemStyle: { color: '#409eff' } },
      { name: '总成本', type: 'line', smooth: true, yAxisIndex: 0,
        data: s.total_cost,    itemStyle: { color: '#e6a23c' } },
      { name: '净利润', type: 'line', smooth: true, yAxisIndex: 0,
        data: s.total_profit,  itemStyle: { color: '#67c23a' } },
      { name: '1店利润', type: 'bar', yAxisIndex: 1,
        data: s.profit_s1,    itemStyle: { color: 'rgba(64,158,255,0.5)' } },
      { name: '2店利润', type: 'bar', yAxisIndex: 1,
        data: s.profit_s2,    itemStyle: { color: 'rgba(103,194,58,0.5)' } },
    ],
  }
})
```

**Donut pie chart config pattern (profit floored at 0):**
```javascript
const pieOption = computed(() => {
  if (!data.value) return {}
  const { total_profit, total_cost, total_refund } = data.value.kpi
  const profitVal = Math.max(0, total_profit)
  const pieData = []
  if (profitVal > 0) {
    pieData.push({ name: '净利润', value: profitVal, itemStyle: { color: '#67c23a' } })
  }
  pieData.push({ name: '总成本', value: total_cost,   itemStyle: { color: '#e6a23c' } })
  if (total_refund > 0) {
    pieData.push({ name: '退款',   value: total_refund, itemStyle: { color: '#f56c6c' } })
  }
  return {
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}：¥{c} ({d}%)',
    },
    legend: { orient: 'horizontal', bottom: 0 },
    series: [{
      name: '收入构成',
      type: 'pie',
      radius: ['40%', '68%'],
      data: pieData,
      label: { formatter: '{b}\n{d}%' },
      emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.3)' } },
    }],
  }
})
```

**KPI card layout (CSS Grid):**
```
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}
```
Cards arranged as:
- Row 1: 1店收入 | 1店成本 | 1店利润
- Row 2: 2店收入 | 2店成本 | 2店利润
- Row 3 (合计, full-width via colspan trick or separate row): 合计收入 | 合计成本 | 合计净利润

Use a `kpi-profit` class on profit cards with green text when positive, red when negative.

**Full component code:**

```vue
<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { fetchProfitMonthly } from '../api/stats.js'

use([CanvasRenderer, BarChart, LineChart, PieChart,
     GridComponent, TooltipComponent, LegendComponent, TitleComponent])

const MONTH_RE = /^\d{4}-\d{2}$/

const startMonth = ref('')
const endMonth   = ref('')
const loading    = ref(false)
const error      = ref(null)
const data       = ref(null)

async function loadData() {
  if (startMonth.value && !MONTH_RE.test(startMonth.value)) return
  if (endMonth.value   && !MONTH_RE.test(endMonth.value))   return
  loading.value = true
  error.value   = null
  try {
    data.value = await fetchProfitMonthly({
      startMonth: startMonth.value || undefined,
      endMonth:   endMonth.value   || undefined,
    })
  } catch (e) {
    error.value = e?.detail || '数据加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
watch([startMonth, endMonth], loadData)

const kpi = computed(() => data.value?.kpi ?? {
  revenue_s1: 0, revenue_s2: 0, cost_s1: 0, cost_s2: 0,
  refund_s1: 0,  refund_s2: 0,  profit_s1: 0, profit_s2: 0,
  total_revenue: 0, total_cost: 0, total_refund: 0, total_profit: 0,
})

function fmt(n) {
  return Number(n ?? 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

const trendOption = computed(() => {
  if (!data.value?.months?.length) return {}
  const { months, series: s } = data.value
  return {
    tooltip: {
      trigger: 'axis',
      formatter(params) {
        const month = params[0].axisValue
        let html = `<b>${month}</b><br/>`
        for (const p of params) {
          const val = `¥${Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
          html += `${p.marker}${p.seriesName}：${val}<br/>`
        }
        return html
      },
    },
    legend: { type: 'scroll', bottom: 0 },
    grid: { left: '3%', right: '8%', bottom: '15%', containLabel: true },
    xAxis: { type: 'category', data: months, boundaryGap: false },
    yAxis: [
      {
        type: 'value', name: '金额（元）', position: 'left',
        axisLabel: { formatter: v => `¥${(v / 1000).toFixed(0)}K` },
      },
      {
        type: 'value', name: '分店利润（元）', position: 'right',
        axisLabel: { formatter: v => `¥${(v / 1000).toFixed(0)}K` },
      },
    ],
    series: [
      { name: '总收入', type: 'line', smooth: true, yAxisIndex: 0,
        data: s.total_revenue, itemStyle: { color: '#409eff' } },
      { name: '总成本', type: 'line', smooth: true, yAxisIndex: 0,
        data: s.total_cost,    itemStyle: { color: '#e6a23c' } },
      { name: '净利润', type: 'line', smooth: true, yAxisIndex: 0,
        data: s.total_profit,  itemStyle: { color: '#67c23a' } },
      { name: '1店利润', type: 'bar', yAxisIndex: 1,
        data: s.profit_s1,    itemStyle: { color: 'rgba(64,158,255,0.5)' } },
      { name: '2店利润', type: 'bar', yAxisIndex: 1,
        data: s.profit_s2,    itemStyle: { color: 'rgba(103,194,58,0.5)' } },
    ],
  }
})

const pieOption = computed(() => {
  if (!data.value) return {}
  const { total_profit, total_cost, total_refund } = data.value.kpi
  const profitVal = Math.max(0, total_profit)
  const pieData = []
  if (profitVal > 0) {
    pieData.push({ name: '净利润', value: profitVal, itemStyle: { color: '#67c23a' } })
  }
  pieData.push({ name: '总成本', value: total_cost, itemStyle: { color: '#e6a23c' } })
  if (total_refund > 0) {
    pieData.push({ name: '退款', value: total_refund, itemStyle: { color: '#f56c6c' } })
  }
  return {
    tooltip: { trigger: 'item', formatter: '{a} <br/>{b}：¥{c} ({d}%)' },
    legend: { orient: 'horizontal', bottom: 0 },
    series: [{
      name: '收入构成',
      type: 'pie',
      radius: ['40%', '68%'],
      data: pieData,
      label: { formatter: '{b}\n{d}%' },
      emphasis: {
        itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.3)' },
      },
    }],
  }
})

const hasData = computed(() => data.value?.months?.length > 0)
</script>

<template>
  <div class="home-dashboard">
    <h2 class="page-title">利润分析总览</h2>

    <!-- Filter row -->
    <div class="filter-row">
      <label class="filter-label">
        开始月份：
        <input
          v-model="startMonth"
          type="text"
          placeholder="YYYY-MM"
          class="month-input"
          maxlength="7"
        />
      </label>
      <label class="filter-label">
        结束月份：
        <input
          v-model="endMonth"
          type="text"
          placeholder="YYYY-MM"
          class="month-input"
          maxlength="7"
        />
      </label>
    </div>

    <!-- Loading / error states -->
    <div v-if="loading" class="status-msg">加载中…</div>
    <div v-else-if="error" class="error-msg">{{ error }}</div>

    <!-- KPI cards -->
    <template v-if="!loading && !error">
      <div class="kpi-section">
        <div class="kpi-store-label">1 店</div>
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-title">1店 收入</div>
            <div class="kpi-value">¥{{ fmt(kpi.revenue_s1) }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-title">1店 成本</div>
            <div class="kpi-value">¥{{ fmt(kpi.cost_s1) }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-title">1店 净利润</div>
            <div class="kpi-value" :class="kpi.profit_s1 >= 0 ? 'kpi-profit' : 'kpi-loss'">
              ¥{{ fmt(kpi.profit_s1) }}
            </div>
          </div>
          <div class="kpi-card">
            <div class="kpi-title">2店 收入</div>
            <div class="kpi-value">¥{{ fmt(kpi.revenue_s2) }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-title">2店 成本</div>
            <div class="kpi-value">¥{{ fmt(kpi.cost_s2) }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-title">2店 净利润</div>
            <div class="kpi-value" :class="kpi.profit_s2 >= 0 ? 'kpi-profit' : 'kpi-loss'">
              ¥{{ fmt(kpi.profit_s2) }}
            </div>
          </div>
        </div>

        <div class="kpi-store-label kpi-total-label">合计</div>
        <div class="kpi-grid">
          <div class="kpi-card kpi-card--total">
            <div class="kpi-title">合计 收入</div>
            <div class="kpi-value">¥{{ fmt(kpi.total_revenue) }}</div>
          </div>
          <div class="kpi-card kpi-card--total">
            <div class="kpi-title">合计 成本</div>
            <div class="kpi-value">¥{{ fmt(kpi.total_cost) }}</div>
          </div>
          <div class="kpi-card kpi-card--total">
            <div class="kpi-title">合计 净利润</div>
            <div class="kpi-value" :class="kpi.total_profit >= 0 ? 'kpi-profit' : 'kpi-loss'">
              ¥{{ fmt(kpi.total_profit) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Trend chart -->
      <div class="chart-block">
        <div class="chart-title">月度利润走势</div>
        <div v-if="!hasData" class="chart-empty">暂无数据</div>
        <v-chart v-else :option="trendOption" autoresize style="height: 420px; width: 100%;" />
      </div>

      <!-- Pie chart -->
      <div class="chart-block">
        <div class="chart-title">收入构成（净利润 / 成本 / 退款）</div>
        <div v-if="!hasData" class="chart-empty">暂无数据</div>
        <v-chart v-else :option="pieOption" autoresize style="height: 360px; width: 100%;" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.home-dashboard {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--text);
}

/* Filter row */
.filter-row {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.filter-label {
  font-size: 14px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 6px;
}

.month-input {
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 14px;
  width: 100px;
  outline: none;
  background: var(--bg);
  color: var(--text);
}

.month-input:focus {
  border-color: #409eff;
}

/* KPI section */
.kpi-section {
  margin-bottom: 28px;
}

.kpi-store-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.kpi-total-label {
  margin-top: 16px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 4px;
}

.kpi-card {
  background: var(--bg-subtle, #f5f7fa);
  border: 1px solid var(--border-subtle, #e4e7ed);
  border-radius: 8px;
  padding: 16px 20px;
}

.kpi-card--total {
  background: var(--bg, #fff);
  border-color: var(--border-subtle, #e4e7ed);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.kpi-title {
  font-size: 12px;
  color: var(--text-muted, #909399);
  margin-bottom: 6px;
}

.kpi-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--text, #303133);
  letter-spacing: -0.3px;
}

.kpi-profit {
  color: #67c23a;
}

.kpi-loss {
  color: #f56c6c;
}

/* Charts */
.chart-block {
  background: var(--bg-subtle, #f5f7fa);
  border: 1px solid var(--border-subtle, #e4e7ed);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text, #303133);
  margin-bottom: 12px;
}

.chart-empty {
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted, #909399);
  font-size: 14px;
}

/* Status */
.status-msg {
  text-align: center;
  padding: 40px;
  color: var(--text-muted, #909399);
  font-size: 14px;
}

.error-msg {
  text-align: center;
  padding: 40px;
  color: #f56c6c;
  font-size: 14px;
}
</style>
```

### Step 2.3 — Update `frontend/src/main.js`

**Two changes:**

1. Import `HomeDashboard` (add after existing imports):
```javascript
import HomeDashboard from './components/HomeDashboard.vue'
```

2. Replace the redirect route with the component route:
```javascript
// BEFORE
{ path: '/', redirect: '/products' },

// AFTER
{ path: '/', component: HomeDashboard },
```

**Full updated routes array:**
```javascript
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/',                  component: HomeDashboard },
    { path: '/products',          component: ProductList },
    { path: '/products/:id',      component: ProductDetail },
    { path: '/orders',            component: OrderList },
    { path: '/orders/dashboard',  component: OrderDashboard },
    { path: '/import',            component: DataImport },
    { path: '/suppliers',         component: SupplierManagement },
    { path: '/suppliers/dashboard', component: SupplierDashboard },
  ],
})
```

### Step 2.4 — Update `frontend/src/App.vue`

Add `首页` nav link as the **first** link inside `<nav class="nav-links">`:

```html
<!-- BEFORE -->
<nav class="nav-links">
  <router-link to="/products" class="nav-link" active-class="nav-link--active">商品列表</router-link>
  ...
</nav>

<!-- AFTER -->
<nav class="nav-links">
  <router-link to="/" class="nav-link" active-class="nav-link--active" exact-active-class="nav-link--active">首页</router-link>
  <router-link to="/products" class="nav-link" active-class="nav-link--active">商品列表</router-link>
  ...
</nav>
```

> Note: Use `exact-active-class` on the `/` link to avoid it always being highlighted when nested routes are active.

---

## Phase 3: Verification

### Manual smoke tests

| Test | Expected |
|------|----------|
| `GET /api/stats/profit-monthly` (no params) | 200, `months` array, `series` arrays all same length, `kpi` object |
| `GET /api/stats/profit-monthly?start_month=2026-01&end_month=2026-03` | 200, only months in range |
| `GET /api/stats/profit-monthly?start_month=bad` | 422 |
| Navigate to `/#/` | HomeDashboard renders, not redirected |
| Nav bar | 首页 link appears leftmost |
| KPI cards | 6 store cards + 3 total cards displayed, values formatted as `¥12,345.67` |
| Trend chart | 5 series (3 lines on left Y-axis, 2 bars on right Y-axis), legend clickable |
| Pie chart | 2–3 sectors (净利润 hidden when ≤ 0), percentage labels |
| Month filter | Type `2026-01` in start field → charts/KPI refresh; type `bad` → no request fired |
| Empty DB | All KPIs show `0.00`, charts show "暂无数据" placeholder |

### Automated regression

Existing backend tests in `backend/tests/` should still pass unchanged — the new `stats` router does not modify any existing routes.

---

## File Change Summary

| File | Action | Purpose |
|------|--------|---------|
| `backend/schemas.py` | Modify (append) | Add `ProfitMonthlySeries`, `ProfitMonthlyKPI`, `ProfitMonthlyResponse` |
| `backend/routes/stats.py` | **Create** | `GET /api/stats/profit-monthly` endpoint |
| `backend/main.py` | Modify | Import and register `stats_router` |
| `frontend/src/api/stats.js` | **Create** | `fetchProfitMonthly()` API helper |
| `frontend/src/components/HomeDashboard.vue` | **Create** | Full dashboard component |
| `frontend/src/main.js` | Modify | Route `/` → `HomeDashboard`; import component |
| `frontend/src/App.vue` | Modify | Add 首页 nav link leftmost |
