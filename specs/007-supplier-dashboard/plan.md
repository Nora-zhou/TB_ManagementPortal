# Implementation Plan: 供应商采购分析仪表盘

**Spec**: specs/007-supplier-dashboard/spec.md  
**Feature Branch**: `007-supplier-dashboard`  
**Status**: Ready for Implementation

---

## Technical Context

| Item | Detail |
|------|--------|
| Backend framework | FastAPI + SQLModel + SQLite |
| Frontend framework | Vue 3 (Composition API) + Vue Router (hash history) |
| Chart library | vue-echarts + echarts/core (already installed) |
| Existing chart example | `frontend/src/components/OrderDashboard.vue` |
| ECharts already registered | `CanvasRenderer`, `LineChart`, `GridComponent`, `TooltipComponent`, `LegendComponent`, `TitleComponent`, `ToolboxComponent` |
| New ECharts components needed | `BarChart`, `LegendScrollComponent` (register in SupplierDashboard.vue via `use()`) |
| Excluded statuses constant | `EXCLUDED_STATUSES = ("等待买家付款", "退款中", "交易关闭")` in `backend/routes/purchase_orders.py` |
| Month format (backend) | `strftime("%Y-%m", created_at)` |
| Router history mode | `createWebHashHistory()` — routes use `#/...` prefix |
| Existing routes | `/products`, `/products/:id`, `/orders`, `/orders/dashboard`, `/import`, `/suppliers` |
| Available months endpoint | `GET /api/purchase-orders/months` → `list[AvailableMonth]` (already exists) |

---

## Constitution Check

- No new data models required — all queries are on existing `PurchaseOrder` table.
- New endpoint follows existing route structure under `/api/purchase-orders/` prefix.
- `EXCLUDED_STATUSES` reused from existing constant — no duplication.
- Pydantic schemas added to the existing `backend/schemas.py` section for purchase orders.
- Frontend component follows `OrderDashboard.vue` patterns — same ECharts setup, same API error handling.
- No navigation bar changes — entry point is scoped to `SupplierManagement.vue` only.

---

## Phase 1: Backend

### 1.1 — New Pydantic schemas (`backend/schemas.py`)

Append after the existing `PurchaseOrderDetailResponse` class (end of file):

```python
# ---------------------------------------------------------------------------
# SupplierDashboard schemas (007-supplier-dashboard)
# ---------------------------------------------------------------------------

class TopSupplierItem(BaseModel):
    seller_name: str
    total_amount: float
    total_orders: int


class SupplierMonthlyItem(BaseModel):
    seller_name: str
    monthly_orders: dict[str, int]
    monthly_amounts: dict[str, float]


class SupplierDashboardResponse(BaseModel):
    top_suppliers: list[TopSupplierItem]
    months: list[str]
    monthly_data: list[SupplierMonthlyItem]
```

**Notes**:
- `dict[str, int]` / `dict[str, float]` serialise cleanly to JSON objects with month-string keys.
- No `Optional` wrappers needed — missing months are filled with `0` / `0.0` by the endpoint logic.

---

### 1.2 — New endpoint (`backend/routes/purchase_orders.py`)

**Import additions** (add to existing import block at top of file):

```python
from schemas import (
    ...existing imports...,
    SupplierDashboardResponse,
    TopSupplierItem,
    SupplierMonthlyItem,
)
```

**Endpoint** — append after the existing `get_available_months` function:

```python
# ---------------------------------------------------------------------------
# GET /api/purchase-orders/dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=SupplierDashboardResponse)
def get_supplier_dashboard(
    top_n: int = Query(default=15, ge=1, le=100),
    start_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    end_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    """Return Top-N suppliers by total paid_amount with per-month breakdowns."""

    month_col = func.strftime("%Y-%m", PurchaseOrder.created_at)

    # --- Step 1: Build base filter predicate ---
    base_filters = [
        PurchaseOrder.status.not_in(EXCLUDED_STATUSES),
        PurchaseOrder.created_at.isnot(None),
        PurchaseOrder.paid_amount.isnot(None),
    ]
    if start_month:
        base_filters.append(month_col >= start_month)
    if end_month:
        base_filters.append(month_col <= end_month)

    # --- Step 2: Aggregate by seller_name to find Top N ---
    top_stmt = (
        select(
            PurchaseOrder.seller_name,
            func.sum(PurchaseOrder.paid_amount).label("total_amount"),
            func.count(PurchaseOrder.id).label("total_orders"),
        )
        .where(*base_filters)
        .group_by(PurchaseOrder.seller_name)
        .order_by(func.sum(PurchaseOrder.paid_amount).desc())
        .limit(top_n)
    )
    top_rows = session.exec(top_stmt).all()

    if not top_rows:
        return SupplierDashboardResponse(
            top_suppliers=[], months=[], monthly_data=[]
        )

    top_supplier_names = [r.seller_name for r in top_rows]
    top_suppliers = [
        TopSupplierItem(
            seller_name=r.seller_name,
            total_amount=round(float(r.total_amount), 2),
            total_orders=int(r.total_orders),
        )
        for r in top_rows
    ]

    # --- Step 3: Monthly breakdown for Top N suppliers ---
    monthly_stmt = (
        select(
            PurchaseOrder.seller_name,
            month_col.label("ym"),
            func.count(PurchaseOrder.id).label("cnt"),
            func.sum(PurchaseOrder.paid_amount).label("amt"),
        )
        .where(
            *base_filters,
            PurchaseOrder.seller_name.in_(top_supplier_names),
        )
        .group_by(PurchaseOrder.seller_name, month_col)
        .order_by(month_col)
    )
    monthly_rows = session.exec(monthly_stmt).all()

    # --- Step 4: Collect all months in range (sorted ascending) ---
    all_months: list[str] = sorted({r.ym for r in monthly_rows})

    # --- Step 5: Build per-supplier month maps, fill zeros ---
    monthly_map: dict[str, dict] = {
        name: {"orders": {}, "amounts": {}} for name in top_supplier_names
    }
    for r in monthly_rows:
        monthly_map[r.seller_name]["orders"][r.ym] = int(r.cnt)
        monthly_map[r.seller_name]["amounts"][r.ym] = round(float(r.amt), 2)

    monthly_data = [
        SupplierMonthlyItem(
            seller_name=name,
            monthly_orders={m: monthly_map[name]["orders"].get(m, 0) for m in all_months},
            monthly_amounts={m: monthly_map[name]["amounts"].get(m, 0.0) for m in all_months},
        )
        for name in top_supplier_names
    ]

    return SupplierDashboardResponse(
        top_suppliers=top_suppliers,
        months=all_months,
        monthly_data=monthly_data,
    )
```

**Key design decisions**:
- Two SQL queries (not a subquery join) — simpler SQLModel expression, easier to debug.
- `month_col` computed once and reused in both queries.
- `start_month` / `end_month` validated via `pattern=r"^\d{4}-\d{2}$"` — FastAPI returns 422 automatically on mismatch.
- Zero-fill happens in Python (dict `.get(m, 0)`) after querying — avoids complex outer-join SQL.
- `top_n` bounded `ge=1, le=100` to prevent abuse.

---

## Phase 2: Frontend

### 2.1 — New API function (`frontend/src/api/purchase_orders.js`)

Append to end of file:

```javascript
/**
 * T020 — Fetch supplier dashboard data (Top N suppliers with monthly breakdown).
 * @param {Object} params
 * @param {number} [params.topN=15]
 * @param {string} [params.startMonth]  - YYYY-MM
 * @param {string} [params.endMonth]    - YYYY-MM
 * @returns {Promise<{top_suppliers: Array, months: Array, monthly_data: Array}>}
 */
export async function fetchSupplierDashboard({ topN = 15, startMonth, endMonth } = {}) {
  const p = new URLSearchParams({ top_n: String(topN) })
  if (startMonth) p.append('start_month', startMonth)
  if (endMonth) p.append('end_month', endMonth)
  const res = await fetch(`${BASE}/dashboard?${p}`)
  if (!res.ok) throw await res.json()
  return res.json()
}
```

---

### 2.2 — Route registration (`frontend/src/main.js`)

Add import and route entry. Changes are minimal — two lines:

```javascript
// Add import alongside existing component imports:
import SupplierDashboard from './components/SupplierDashboard.vue'

// Add route inside the routes array (after the /suppliers entry):
{ path: '/suppliers/dashboard', component: SupplierDashboard },
```

Full diff context:
```diff
 import SupplierManagement from './components/SupplierManagement.vue'
+import SupplierDashboard from './components/SupplierDashboard.vue'

 const router = createRouter({
   ...
     { path: '/suppliers', component: SupplierManagement },
+    { path: '/suppliers/dashboard', component: SupplierDashboard },
   ],
 })
```

---

### 2.3 — Navigation button (`frontend/src/components/SupplierManagement.vue`)

Add `useRouter` import and a button at the top of the template.

**Script addition** (at top of `<script setup>`):

```javascript
import { useRouter } from 'vue-router'
const router = useRouter()
```

**Template addition** — place immediately after the opening `<div>` wrapper, before the month selector:

```html
<div style="margin-bottom: 12px;">
  <button @click="router.push('/suppliers/dashboard')" class="btn-chart">
    供应商图表
  </button>
</div>
```

**Style addition**:
```css
.btn-chart {
  padding: 6px 16px;
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}
.btn-chart:hover { background: #337ecc; }
```

---

### 2.4 — New component (`frontend/src/components/SupplierDashboard.vue`)

Full file structure:

```vue
<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent,
  TitleComponent, LegendScrollComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { fetchAvailableMonths, fetchSupplierDashboard } from '../api/purchase_orders.js'

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent,
     LegendComponent, TitleComponent, LegendScrollComponent])

const router = useRouter()

// ── Filter state ──────────────────────────────────────────────────────────────
const availableMonths = ref([])        // [{year, month}] from /months
const startMonth = ref('')             // YYYY-MM
const endMonth = ref('')               // YYYY-MM

// ── Data & loading state ──────────────────────────────────────────────────────
const loading = ref(false)
const error = ref(null)
const dashData = ref(null)             // raw API response

// ── Chart option refs ─────────────────────────────────────────────────────────
const chart1Option = ref({})
const chart2Option = ref({})
const chart3Option = ref({})

// ── Helpers ───────────────────────────────────────────────────────────────────
function monthKey(m) {
  return `${m.year}-${String(m.month).padStart(2, '0')}`
}

// ── Load available months for pickers ────────────────────────────────────────
async function loadMonths() {
  try {
    const data = await fetchAvailableMonths()
    // Sort ascending for display
    availableMonths.value = [...data].sort((a, b) =>
      monthKey(a).localeCompare(monthKey(b))
    )
  } catch {
    availableMonths.value = []
  }
}

// ── Load dashboard data and build chart options ───────────────────────────────
async function loadDashboard() {
  loading.value = true
  error.value = null
  try {
    const params = {}
    if (startMonth.value) params.startMonth = startMonth.value
    if (endMonth.value) params.endMonth = endMonth.value
    dashData.value = await fetchSupplierDashboard(params)
    buildCharts()
  } catch (e) {
    error.value = e?.detail || '加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

// ── Build ECharts option objects ──────────────────────────────────────────────
function buildCharts() {
  const d = dashData.value
  if (!d || d.top_suppliers.length === 0) {
    chart1Option.value = {}
    chart2Option.value = {}
    chart3Option.value = {}
    return
  }

  const months = d.months          // ["2025-10", ...]
  const suppliers = d.top_suppliers.map(s => s.seller_name)  // order = rank 1..N

  // -- Chart 1: Horizontal bar — total paid amount --
  // Reverse supplier list so rank-1 appears at top of Y axis
  const suppliersRev = [...suppliers].reverse()
  const amountsRev = suppliersRev.map(name => {
    const s = d.top_suppliers.find(x => x.seller_name === name)
    return s ? s.total_amount : 0
  })

  chart1Option.value = {
    title: { text: 'Top 供应商历史总采购金额', left: 'center' },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: params => {
        const p = params[0]
        return `${p.name}<br/>总金额：¥${p.value.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
      },
    },
    grid: { left: '20%', right: '8%', top: '10%', bottom: '8%' },
    xAxis: { type: 'value', name: '金额（元）' },
    yAxis: { type: 'category', data: suppliersRev, axisLabel: { width: 120, overflow: 'truncate' } },
    series: [{
      type: 'bar',
      data: amountsRev,
      label: { show: false },
    }],
  }

  // -- Chart 2: Stacked bar — monthly order counts --
  const series2 = suppliers.map(name => {
    const md = d.monthly_data.find(x => x.seller_name === name)
    return {
      name,
      type: 'bar',
      stack: 'orders',
      data: months.map(m => md ? (md.monthly_orders[m] ?? 0) : 0),
      emphasis: { focus: 'series' },
    }
  })

  chart2Option.value = {
    title: { text: '按月订单数量对比（Top 供应商）', left: 'center' },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { type: 'scroll', bottom: 0 },
    grid: { left: '5%', right: '5%', top: '10%', bottom: '15%', containLabel: true },
    xAxis: { type: 'category', data: months },
    yAxis: { type: 'value', name: '订单数' },
    series: series2,
  }

  // -- Chart 3: Stacked bar — monthly paid amounts --
  const series3 = suppliers.map(name => {
    const md = d.monthly_data.find(x => x.seller_name === name)
    return {
      name,
      type: 'bar',
      stack: 'amounts',
      data: months.map(m => md ? (md.monthly_amounts[m] ?? 0) : 0),
      emphasis: { focus: 'series' },
    }
  })

  chart3Option.value = {
    title: { text: '按月采购金额对比（Top 供应商）', left: 'center' },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: v => `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
    },
    legend: { type: 'scroll', bottom: 0 },
    grid: { left: '5%', right: '5%', top: '10%', bottom: '15%', containLabel: true },
    xAxis: { type: 'category', data: months },
    yAxis: { type: 'value', name: '金额（元）' },
    series: series3,
  }
}

// ── Filter handlers ───────────────────────────────────────────────────────────
function onFilterChange() {
  loadDashboard()
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  await loadMonths()
  await loadDashboard()
})
</script>

<template>
  <div class="supplier-dashboard">
    <!-- Header row -->
    <div class="dashboard-header">
      <button class="btn-back" @click="router.push('/suppliers')">← 返回供应商列表</button>
      <h2>供应商采购分析仪表盘</h2>
    </div>

    <!-- Month filter -->
    <div class="filter-row">
      <label>开始月：
        <select v-model="startMonth" @change="onFilterChange">
          <option value="">全部</option>
          <option v-for="m in availableMonths" :key="monthKey(m)" :value="monthKey(m)">
            {{ monthKey(m) }}
          </option>
        </select>
      </label>
      <label>结束月：
        <select v-model="endMonth" @change="onFilterChange">
          <option value="">全部</option>
          <option v-for="m in availableMonths" :key="monthKey(m)" :value="monthKey(m)">
            {{ monthKey(m) }}
          </option>
        </select>
      </label>
    </div>

    <!-- Loading / Error -->
    <div v-if="loading" class="status-msg">加载中…</div>
    <div v-else-if="error" class="error-msg">{{ error }}</div>
    <div v-else-if="!dashData || dashData.top_suppliers.length === 0" class="status-msg">暂无数据</div>

    <!-- Charts -->
    <template v-else>
      <div class="chart-block">
        <v-chart :option="chart1Option" autoresize style="height:420px; width:100%;" />
      </div>
      <div class="chart-block">
        <v-chart :option="chart2Option" autoresize style="height:440px; width:100%;" />
      </div>
      <div class="chart-block">
        <v-chart :option="chart3Option" autoresize style="height:440px; width:100%;" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.supplier-dashboard { padding: 16px; }
.dashboard-header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.btn-back {
  padding: 6px 14px; background: #f0f0f0; border: 1px solid #ccc;
  border-radius: 4px; cursor: pointer; font-size: 14px;
}
.btn-back:hover { background: #ddd; }
.filter-row { display: flex; gap: 20px; margin-bottom: 20px; font-size: 14px; }
.filter-row select { margin-left: 6px; padding: 4px 8px; }
.chart-block { margin-bottom: 32px; border: 1px solid #eee; border-radius: 6px; padding: 8px; }
.status-msg { text-align: center; color: #888; padding: 40px; }
.error-msg { text-align: center; color: #c00; padding: 40px; }
</style>
```

---

## Implementation Order

Tasks should be completed in this sequence to allow incremental testing:

| Step | File | Change | Test Signal |
|------|------|--------|-------------|
| 1 | `backend/schemas.py` | Add 3 new Pydantic models | `python -c "from schemas import SupplierDashboardResponse; print('OK')"` |
| 2 | `backend/routes/purchase_orders.py` | Add dashboard endpoint + schema imports | `GET /api/purchase-orders/dashboard` returns 200 |
| 3 | `frontend/src/api/purchase_orders.js` | Add `fetchSupplierDashboard()` | Manual `fetch` in browser console |
| 4 | `frontend/src/components/SupplierDashboard.vue` | Create new file | Navigate to `/#/suppliers/dashboard` renders page |
| 5 | `frontend/src/main.js` | Import + register `/suppliers/dashboard` route | Route accessible |
| 6 | `frontend/src/components/SupplierManagement.vue` | Add `useRouter` + "供应商图表" button | Button visible, click navigates |

---

## Edge Case Handling

| Scenario | Handling |
|----------|----------|
| No purchase order data | Backend returns empty lists; frontend shows "暂无数据" |
| Fewer than 15 suppliers | `top_n` limit is a cap; fewer rows returned normally |
| Supplier with 0 orders in a month | Zero-filled in Python (`dict.get(m, 0)`) — no missing month keys |
| `start_month > end_month` | Backend returns empty result (no rows match filter) — frontend shows "暂无数据"; no validation error enforced at API level |
| Long supplier names | Chart 1 Y-axis: `axisLabel.overflow: 'truncate'` with `width: 120` |
| `top_n` out of range | FastAPI Query `ge=1, le=100` returns 422 automatically |

---

## Files Summary

| File | Action | Change Description |
|------|--------|--------------------|
| `backend/schemas.py` | Edit | Add `TopSupplierItem`, `SupplierMonthlyItem`, `SupplierDashboardResponse` |
| `backend/routes/purchase_orders.py` | Edit | Add `get_supplier_dashboard()` endpoint + schema imports |
| `frontend/src/api/purchase_orders.js` | Edit | Add `fetchSupplierDashboard()` |
| `frontend/src/components/SupplierDashboard.vue` | **Create** | New dashboard component with 3 ECharts |
| `frontend/src/main.js` | Edit | Import `SupplierDashboard`, add `/suppliers/dashboard` route |
| `frontend/src/components/SupplierManagement.vue` | Edit | Import `useRouter`, add "供应商图表" button |

---

---

# Part 2 Implementation Plan: 供应商综合评估看板

**Spec**: specs/007-supplier-dashboard/spec.md — Part 2  
**Feature Branch**: `007-supplier-dashboard` (extension)  
**Status**: Ready for Implementation

---

## Architecture Overview

No new database tables. All scoring is computed at request time via SQL aggregation + Python arithmetic.

| Layer | Files Changed | What Changes |
|-------|---------------|--------------|
| Backend schemas | `backend/schemas.py` | 4 new Pydantic models |
| Backend routes | `backend/routes/purchase_orders.py` | 2 new endpoints + helper functions |
| Frontend API | `frontend/src/api/purchase_orders.js` | 2 new fetch functions |
| Frontend component | `frontend/src/components/SupplierEvaluation.vue` | **New file** — evaluation table + radar + line chart |
| Frontend routing | `frontend/src/main.js` | 1 new route |
| Navigation | `frontend/src/components/SupplierDashboard.vue` | "供应商评估" button in header |

ECharts additions: `RadarChart` component (new) registered inside `SupplierEvaluation.vue` via `use()`. `LineChart` is already imported in `SupplierDashboard.vue` but must be registered independently in the new component.

---

## Phase 1: Backend

### 1.1 — New Pydantic Schemas (`backend/schemas.py`)

Append after the existing `SupplierDashboardResponse` class:

```python
# ---------------------------------------------------------------------------
# SupplierEvaluation schemas (007-supplier-dashboard Part 2)
# ---------------------------------------------------------------------------

class SupplierEvaluationItem(BaseModel):
    seller_name: str
    score: Optional[float]
    label: str
    completion_rate: Optional[float]
    price_stability: Optional[float]
    activity_rate: Optional[float]
    price_trend_score: Optional[float]
    total_amount: float
    order_count: int


class SupplierEvaluationResponse(BaseModel):
    suppliers: list[SupplierEvaluationItem]


class PriceHistoryPoint(BaseModel):
    month: str
    goods_title: str
    avg_unit_price: float


class SupplierEvaluationDetail(BaseModel):
    seller_name: str
    score: Optional[float]
    label: str
    dimensions: dict[str, Optional[float]]
    price_history: list[PriceHistoryPoint]
```

**Import additions** needed in `purchase_orders.py`:

```python
from schemas import (
    ...existing imports...,
    SupplierEvaluationItem,
    SupplierEvaluationResponse,
    PriceHistoryPoint,
    SupplierEvaluationDetail,
)
```

---

### 1.2 — Helper Functions (`backend/routes/purchase_orders.py`)

Add these pure-Python helpers before the new endpoints (after the existing `get_supplier_dashboard` function). They have no side effects and are easy to unit-test independently.

```python
# ---------------------------------------------------------------------------
# Evaluation helpers (007 Part 2)
# ---------------------------------------------------------------------------

import math


def _linear_slope(ys: list[float]) -> float:
    """OLS slope of ys against 0-indexed x. Returns 0.0 if fewer than 2 points."""
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    sx = sum(xs)
    sy = sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sxx = sum(x * x for x in xs)
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0
    return (n * sxy - sx * sy) / denom


def _months_in_window(start: Optional[str], end: Optional[str],
                      db_min: Optional[str], db_max: Optional[str]) -> int:
    """Natural month count (inclusive) for the global activity-rate denominator."""
    s = start or db_min
    e = end or db_max
    if not s or not e:
        return 1
    sy, sm = int(s[:4]), int(s[5:7])
    ey, em = int(e[:4]), int(e[5:7])
    total = (ey - sy) * 12 + (em - sm) + 1
    return max(total, 1)


def _score_label(score: Optional[float]) -> str:
    if score is None:
        return "数据不足"
    if score >= 85:
        return "优质供应商 ⭐⭐⭐"
    if score >= 65:
        return "稳定合作商 ⭐⭐"
    if score >= 45:
        return "一般供应商 ⭐"
    return "需关注 ⚠️"
```

**Design note**: `_linear_slope` accepts a pre-sorted list of y-values (monthly weighted average prices) with implicit 0-indexed x. This avoids date parsing inside the function and keeps it pure.

---

### 1.3 — Scoring Algorithm (Python pseudocode with SQL queries)

The batch evaluation is computed in a single function called by both endpoints. This ensures the detail endpoint's score always matches the list endpoint (percentile context is identical).

```
function compute_all_evaluations(session, start_month, end_month):

  # ── Step 0: Global time window for activity-rate denominator ────────────────
  min_max_stmt = SELECT MIN(strftime('%Y-%m', created_at)), MAX(strftime('%Y-%m', created_at))
                 FROM purchase_orders
                 WHERE created_at IS NOT NULL
                   AND [month_col >= start_month if provided]
                   AND [month_col <= end_month   if provided]
  db_min, db_max = result

  total_months = _months_in_window(start_month, end_month, db_min, db_max)

  # ── Step 1: Completion rate + order counts per supplier ────────────────────
  # Note: date range filter applied; no global EXCLUDED_STATUSES pre-filter here
  # because '退款中' and '交易关闭' must appear in the completion-rate denominator.
  stmt1 = SELECT
            seller_name,
            SUM(CASE WHEN status != '等待买家付款' THEN 1 ELSE 0 END) AS denom,
            SUM(CASE WHEN status = '交易成功'      THEN 1 ELSE 0 END) AS numer,
            SUM(CASE WHEN status = '交易成功' AND paid_amount IS NOT NULL
                     THEN paid_amount ELSE 0 END)                    AS total_amount
          FROM purchase_orders
          WHERE created_at IS NOT NULL
            AND [month_col >= start_month if provided]
            AND [month_col <= end_month   if provided]
            AND status != '等待买家付款'     -- exclude entirely unpaid (not in denom either)
          GROUP BY seller_name

  # Build dict: seller_name → {denom, numer, total_amount}
  # Suppliers with denom < 3 → score = null later

  # ── Step 2: Price stability per (seller_name, goods_title) ─────────────────
  # Only '交易成功' orders with unit_price not null
  stmt2 = SELECT
            seller_name,
            goods_title,
            COUNT(*)                                    AS cnt,
            AVG(unit_price)                             AS avg_price,
            -- population variance via E[x²] - (E[x])²
            AVG(unit_price * unit_price)
              - AVG(unit_price) * AVG(unit_price)       AS var_price,
            SUM(paid_amount)                            AS total_paid
          FROM purchase_orders
          WHERE status = '交易成功'
            AND unit_price IS NOT NULL
            AND goods_title IS NOT NULL
            AND created_at IS NOT NULL
            AND [date range]
          GROUP BY seller_name, goods_title

  # In Python, for each supplier:
  #   for each goods_title row:
  #     std = sqrt(max(var_price, 0))
  #     cv  = std / avg_price  if avg_price > 0 else 0
  #   weighted_cv = sum(total_paid * cv) / sum(total_paid)
  #                 if sum(total_paid) > 0 else 0
  #   price_stability = max(0, 1 - weighted_cv) * 100
  # If supplier has no rows (all unit_price null): price_stability = 0

  # ── Step 3: Activity rate per supplier ─────────────────────────────────────
  stmt3 = SELECT
            seller_name,
            COUNT(DISTINCT strftime('%Y-%m', created_at)) AS active_months
          FROM purchase_orders
          WHERE status = '交易成功'
            AND created_at IS NOT NULL
            AND [date range]
          GROUP BY seller_name

  # activity_rate = (active_months / total_months) * 100, capped at 100

  # ── Step 4: Monthly weighted average unit price per supplier ───────────────
  stmt4 = SELECT
            seller_name,
            strftime('%Y-%m', created_at)              AS ym,
            SUM(unit_price * quantity) / SUM(quantity) AS wavg_price
          FROM purchase_orders
          WHERE status = '交易成功'
            AND unit_price IS NOT NULL
            AND quantity   IS NOT NULL
            AND quantity   > 0
            AND created_at IS NOT NULL
            AND [date range]
          GROUP BY seller_name, ym
          ORDER BY seller_name, ym

  # In Python, for each supplier:
  #   sorted_months = ordered list of ym values for this supplier
  #   wavg_prices   = corresponding wavg_price values
  #   slope = _linear_slope(wavg_prices)
  # Collect all slopes across suppliers

  # ── Step 5: Price trend score (percentile mapping) ─────────────────────────
  # Split suppliers into k <= 0 (score=100) and k > 0
  # positive_slopes = [k for k in all_slopes if k > 0]
  # if len(positive_slopes) == 0: all trend scores = 100
  # elif len(positive_slopes) == 1: lone positive slope → score = 0
  # else:
  #   k_min = min(positive_slopes)
  #   k_max = max(positive_slopes)
  #   if k_min == k_max: all positive slopes → score = 0
  #   else:
  #     trend_score = (1 - (k - k_min) / (k_max - k_min)) * 100

  # ── Step 6: Composite score ────────────────────────────────────────────────
  # score = None if denom < 3
  # else:
  #   score = round(
  #     completion_rate * 0.35 +
  #     price_stability * 0.30 +
  #     activity_rate   * 0.20 +
  #     trend_score     * 0.15,
  #     2
  #   )

  # ── Step 7: Sort by score desc (None last), return list ───────────────────
  return sorted results
```

**Key design decisions**:
- Four SQL queries (not one mega-join) — each query is independently readable and debuggable.
- `stmt1` intentionally does **not** pre-filter `EXCLUDED_STATUSES` so that `退款中` / `交易关闭` are counted in the completion-rate denominator (spec requirement). The `AND status != '等待买家付款'` in the WHERE clause limits the fetched rows to exactly what is needed.
- Variance computed via `E[x²] - (E[x])²` (population variance) — works natively in SQLite without `STDDEV` aggregate.
- `_linear_slope` receives a list of y-values in month order; x is implicit 0, 1, 2, … (uniform spacing). Converting month strings to offsets is not needed because the formula only uses relative positions.
- The scoring logic is extracted into a standalone `_compute_all_evaluations(session, start_month, end_month)` helper that both endpoints call. This guarantees the detail endpoint's scores are always percentile-consistent with the list endpoint.

---

### 1.4 — New Endpoints (`backend/routes/purchase_orders.py`)

#### GET /api/purchase-orders/evaluation

```python
@router.get("/evaluation", response_model=SupplierEvaluationResponse)
def get_supplier_evaluation(
    start_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    end_month:   Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    items = _compute_all_evaluations(session, start_month, end_month)
    return SupplierEvaluationResponse(suppliers=items)
```

#### GET /api/purchase-orders/evaluation/{seller_name}

```python
@router.get("/evaluation/{seller_name}", response_model=SupplierEvaluationDetail)
def get_supplier_evaluation_detail(
    seller_name: str,
    start_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    end_month:   Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    # 1. Check supplier exists (any status, any date) to return 404 quickly
    exists_stmt = select(PurchaseOrder.seller_name).where(
        PurchaseOrder.seller_name == seller_name
    ).limit(1)
    if not session.exec(exists_stmt).first():
        raise HTTPException(status_code=404, detail="供应商不存在")

    # 2. Re-run full evaluation to get percentile-consistent scores
    all_items = _compute_all_evaluations(session, start_month, end_month)
    target = next((x for x in all_items if x.seller_name == seller_name), None)

    if target is None:
        # Supplier exists in DB but has no data in the selected window → return nulls
        target = SupplierEvaluationItem(
            seller_name=seller_name, score=None, label="数据不足",
            completion_rate=None, price_stability=None,
            activity_rate=None, price_trend_score=None,
            total_amount=0.0, order_count=0,
        )

    # 3. Query Top 10 goods_title by paid_amount for this supplier
    month_col = func.strftime("%Y-%m", PurchaseOrder.created_at)
    base = [
        PurchaseOrder.seller_name == seller_name,
        PurchaseOrder.status == "交易成功",
        PurchaseOrder.goods_title.isnot(None),
        PurchaseOrder.created_at.isnot(None),
    ]
    if start_month:
        base.append(month_col >= start_month)
    if end_month:
        base.append(month_col <= end_month)

    top10_stmt = (
        select(
            PurchaseOrder.goods_title,
            func.sum(PurchaseOrder.paid_amount).label("total_paid"),
        )
        .where(*base)
        .group_by(PurchaseOrder.goods_title)
        .order_by(func.sum(PurchaseOrder.paid_amount).desc())
        .limit(10)
    )
    top10_rows = session.exec(top10_stmt).all()
    top10_titles = [r.goods_title for r in top10_rows]

    price_history: list[PriceHistoryPoint] = []
    if top10_titles:
        # 4. Monthly weighted avg unit price for Top 10 goods_titles
        ph_stmt = (
            select(
                PurchaseOrder.goods_title,
                month_col.label("ym"),
                (
                    func.sum(PurchaseOrder.unit_price * PurchaseOrder.quantity)
                    / func.sum(PurchaseOrder.quantity)
                ).label("wavg"),
            )
            .where(
                *base,
                PurchaseOrder.unit_price.isnot(None),
                PurchaseOrder.quantity.isnot(None),
                PurchaseOrder.quantity > 0,
                PurchaseOrder.goods_title.in_(top10_titles),
            )
            .group_by(PurchaseOrder.goods_title, month_col)
            .order_by(PurchaseOrder.goods_title, month_col)
        )
        for r in session.exec(ph_stmt).all():
            price_history.append(
                PriceHistoryPoint(
                    month=r.ym,
                    goods_title=r.goods_title,
                    avg_unit_price=round(float(r.wavg), 2),
                )
            )

    return SupplierEvaluationDetail(
        seller_name=target.seller_name,
        score=target.score,
        label=target.label,
        dimensions={
            "completion_rate":  target.completion_rate,
            "price_stability":  target.price_stability,
            "activity_rate":    target.activity_rate,
            "price_trend_score": target.price_trend_score,
        },
        price_history=price_history,
    )
```

**Security note**: `seller_name` is passed as a bound parameter via SQLModel's `.where(PurchaseOrder.seller_name == seller_name)` — never string-interpolated into SQL (NFR-E005).

---

## Phase 2: Frontend

### 2.1 — New API Functions (`frontend/src/api/purchase_orders.js`)

Append to the end of the existing file:

```javascript
/**
 * Fetch all supplier evaluation scores.
 * @param {{ startMonth?: string, endMonth?: string }} params
 */
export async function fetchSupplierEvaluation({ startMonth, endMonth } = {}) {
  const p = new URLSearchParams()
  if (startMonth) p.append('start_month', startMonth)
  if (endMonth)   p.append('end_month',   endMonth)
  const qs = p.toString() ? `?${p}` : ''
  const res = await fetch(`${BASE}/evaluation${qs}`)
  if (!res.ok) throw await res.json()
  return res.json()
}

/**
 * Fetch evaluation detail for a single supplier (radar + price history).
 * @param {string} sellerName
 * @param {{ startMonth?: string, endMonth?: string }} params
 */
export async function fetchSupplierEvaluationDetail(sellerName, { startMonth, endMonth } = {}) {
  const p = new URLSearchParams()
  if (startMonth) p.append('start_month', startMonth)
  if (endMonth)   p.append('end_month',   endMonth)
  const qs = p.toString() ? `?${p}` : ''
  const res = await fetch(`${BASE}/evaluation/${encodeURIComponent(sellerName)}${qs}`)
  if (!res.ok) throw await res.json()
  return res.json()
}
```

---

### 2.2 — Route Registration (`frontend/src/main.js`)

```javascript
import SupplierEvaluation from './components/SupplierEvaluation.vue'

// Inside routes array, after /suppliers/dashboard:
{ path: '/suppliers/evaluation', component: SupplierEvaluation },
```

---

### 2.3 — Navigation Button (`frontend/src/components/SupplierDashboard.vue`)

In the `dashboard-header` div, alongside the existing "← 返回供应商列表" button:

```html
<button class="btn-eval" @click="router.push('/suppliers/evaluation')">
  供应商评估
</button>
```

```css
.btn-eval {
  padding: 6px 16px;
  background: #67c23a;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}
.btn-eval:hover { background: #529b2e; }
```

---

### 2.4 — New Component (`frontend/src/components/SupplierEvaluation.vue`)

#### ECharts registrations

```javascript
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart, LineChart } from 'echarts/charts'
import {
  TitleComponent, TooltipComponent, LegendComponent, LegendScrollComponent,
} from 'echarts/components'

use([CanvasRenderer, RadarChart, LineChart,
     TitleComponent, TooltipComponent, LegendComponent, LegendScrollComponent])
```

#### State

```javascript
const availableMonths  = ref([])    // for month pickers
const startMonth       = ref('')
const endMonth         = ref('')
const loading          = ref(false)
const error            = ref(null)
const suppliers        = ref([])    // SupplierEvaluationItem[]

// Per-row detail state
const expandedSet      = ref(new Set())   // seller_names currently expanded
const detailLoading    = ref({})          // { [seller_name]: bool }
const detailError      = ref({})          // { [seller_name]: string|null }
const detailData       = ref({})          // { [seller_name]: SupplierEvaluationDetail }
```

#### Key computed helpers

```javascript
function badgeStyle(score) {
  if (score === null) return { color: 'gray' }
  if (score >= 85) return { color: 'green' }
  if (score >= 65) return { color: '#409eff' }  // blue
  if (score >= 45) return { color: '#e6a23c' }  // orange
  return { color: '#f56c6c' }                    // red
}

function trendIndicator(score) {
  if (score === null) return '—'
  return score >= 70 ? '↓' : '↑'
}
```

#### Row expand/collapse

```javascript
async function toggleDetail(sellerName) {
  if (expandedSet.value.has(sellerName)) {
    expandedSet.value.delete(sellerName)
    return
  }
  expandedSet.value.add(sellerName)
  if (detailData.value[sellerName]) return    // already loaded

  detailLoading.value[sellerName] = true
  detailError.value[sellerName]   = null
  try {
    const params = {}
    if (startMonth.value) params.startMonth = startMonth.value
    if (endMonth.value)   params.endMonth   = endMonth.value
    detailData.value[sellerName] = await fetchSupplierEvaluationDetail(sellerName, params)
  } catch (e) {
    detailError.value[sellerName] = e?.detail || '加载失败'
  } finally {
    detailLoading.value[sellerName] = false
  }
}
```

**Note**: When the month filter changes and the list is reloaded, `detailData`, `detailError`, and `expandedSet` should be reset so stale detail data is not shown for the new time window.

#### Radar chart option builder

```javascript
function radarOption(detail) {
  const d = detail.dimensions
  const dimLabels = ['完成率', '价格稳定性', '活跃度', '价格走势']
  const dimKeys   = ['completion_rate', 'price_stability', 'activity_rate', 'price_trend_score']
  return {
    title: { text: '维度得分雷达图', left: 'center', textStyle: { fontSize: 13 } },
    tooltip: { trigger: 'item' },
    radar: {
      indicator: dimLabels.map(name => ({ name, max: 100 })),
      radius: '65%',
    },
    series: [{
      type: 'radar',
      data: [{
        name: detail.seller_name,
        value: dimKeys.map(k => d[k] ?? 0),
      }],
      areaStyle: { opacity: 0.3 },
    }],
  }
}
```

#### Price trend line chart option builder

```javascript
function priceTrendOption(detail) {
  if (!detail.price_history || detail.price_history.length === 0) return {}

  // Collect unique months and goods_titles from price_history
  const monthSet  = new Set(detail.price_history.map(p => p.month))
  const titleSet  = new Set(detail.price_history.map(p => p.goods_title))
  const months    = [...monthSet].sort()
  const titles    = [...titleSet]

  // Build lookup: goods_title → { month → avg_unit_price }
  const lookup = {}
  for (const p of detail.price_history) {
    if (!lookup[p.goods_title]) lookup[p.goods_title] = {}
    lookup[p.goods_title][p.month] = p.avg_unit_price
  }

  const series = titles.map(title => ({
    name: title,
    type: 'line',
    smooth: true,
    connectNulls: false,
    data: months.map(m => lookup[title]?.[m] ?? null),
  }))

  return {
    title: { text: '月度单价走势（Top 10 货品）', left: 'center', textStyle: { fontSize: 13 } },
    tooltip: {
      trigger: 'axis',
      formatter(params) {
        let html = `<b>${params[0].axisValue}</b><br/>`
        for (const p of params) {
          if (p.value !== null)
            html += `${p.marker}${p.seriesName}：¥${Number(p.value).toFixed(2)}<br/>`
        }
        return html
      },
    },
    legend: { type: 'scroll', bottom: 0 },
    grid: { left: '2%', right: '4%', bottom: '15%', containLabel: true },
    xAxis: { type: 'category', data: months, boundaryGap: false },
    yAxis: { type: 'value', name: '单价（元）' },
    series,
  }
}
```

#### Template structure

```html
<template>
  <div class="supplier-evaluation">
    <!-- Header -->
    <div class="eval-header">
      <button @click="router.push('/suppliers/dashboard')">← 返回仪表盘</button>
      <h2>供应商综合评估</h2>
    </div>

    <!-- Month filter (same pattern as SupplierDashboard) -->
    <div class="filter-row">
      <label>开始月：
        <select v-model="startMonth" @change="onFilterChange">
          <option value="">全部</option>
          <option v-for="m in availableMonths" :key="monthKey(m)" :value="monthKey(m)">
            {{ monthKey(m) }}
          </option>
        </select>
      </label>
      <label>结束月：
        <select v-model="endMonth" @change="onFilterChange">
          <option value="">全部</option>
          <option v-for="m in availableMonths" :key="monthKey(m)" :value="monthKey(m)">
            {{ monthKey(m) }}
          </option>
        </select>
      </label>
    </div>

    <!-- Loading / Error / Empty states -->
    <div v-if="loading">加载中…</div>
    <div v-else-if="error">{{ error }}</div>
    <div v-else-if="suppliers.length === 0">暂无供应商数据</div>

    <!-- Evaluation table -->
    <table v-else class="eval-table">
      <thead>
        <tr>
          <th>#</th>
          <th>供应商</th>
          <th>综合得分</th>
          <th>标签</th>
          <th>完成率</th>
          <th>价格稳定性</th>
          <th>活跃度</th>
          <th>价格走势</th>
          <th>总采购额</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(s, idx) in suppliers" :key="s.seller_name">
          <!-- Main row -->
          <tr>
            <td>{{ idx + 1 }}</td>
            <td>{{ s.seller_name }}</td>
            <td>
              <span :style="badgeStyle(s.score)" class="score-badge">
                {{ s.score !== null ? s.score.toFixed(1) : '—' }}
              </span>
            </td>
            <td :style="badgeStyle(s.score)">{{ s.label }}</td>
            <td>{{ s.completion_rate !== null ? s.completion_rate.toFixed(1) : '--' }}</td>
            <td>{{ s.price_stability !== null ? s.price_stability.toFixed(1) : '--' }}</td>
            <td>{{ s.activity_rate !== null ? s.activity_rate.toFixed(1) : '--' }}</td>
            <td>{{ trendIndicator(s.price_trend_score) }}</td>
            <td>¥{{ s.total_amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}</td>
            <td>
              <button @click="toggleDetail(s.seller_name)">
                {{ expandedSet.has(s.seller_name) ? '收起' : '查看详情' }}
              </button>
            </td>
          </tr>
          <!-- Inline detail row -->
          <tr v-if="expandedSet.has(s.seller_name)" class="detail-row">
            <td colspan="10">
              <div v-if="detailLoading[s.seller_name]">加载详情中…</div>
              <div v-else-if="detailError[s.seller_name]">{{ detailError[s.seller_name] }}</div>
              <div v-else-if="detailData[s.seller_name]" class="detail-charts">
                <v-chart :option="radarOption(detailData[s.seller_name])"
                         autoresize style="height:320px; width:100%; max-width:480px;" />
                <v-chart :option="priceTrendOption(detailData[s.seller_name])"
                         autoresize style="height:320px; width:100%; flex:1;" />
              </div>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
```

#### Scoped styles (key rules)

```css
.eval-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.eval-table th, .eval-table td { border: 1px solid #eee; padding: 8px 10px; text-align: center; }
.eval-table th { background: #f5f7fa; }
.score-badge { font-weight: 700; font-size: 15px; }
.detail-row td { background: #fafafa; }
.detail-charts { display: flex; gap: 16px; padding: 12px; flex-wrap: wrap; }
```

---

## Edge Case Handling

| Scenario | Handling |
|----------|----------|
| Supplier with denom < 3 | All dimension scores and composite score returned as `null`; label = "数据不足" |
| All `unit_price` null for a supplier | `price_stability` = 0 (conservative default per spec Q5) |
| Only one month of data | `_linear_slope` returns 0.0 (n < 2); trend score = 100 |
| Only one supplier with k > 0 | Lone positive slope → trend score = 0 (conservative) |
| All suppliers have k ≤ 0 | All trend scores = 100; no percentile mapping needed |
| `k_min == k_max` (all positive slopes identical) | denom = 0 → trend score = 0 for all |
| `seller_name` with special chars in path | `encodeURIComponent()` in frontend; FastAPI URL-decodes path params automatically |
| Month filter window produces 0 suppliers | `suppliers: []` returned; frontend shows "暂无供应商数据" |
| Detail called for supplier not in current window | `target` from `_compute_all_evaluations` will be `None`; return null-score item with empty `price_history` |
| `start_month > end_month` | SQL returns 0 rows; returns empty result cleanly |

---

## Implementation Sequence

| Step | File | Change | Test Signal |
|------|------|--------|-------------|
| 1 | `backend/schemas.py` | Add 4 evaluation Pydantic models | `python -c "from schemas import SupplierEvaluationDetail; print('OK')"` |
| 2 | `backend/routes/purchase_orders.py` | Add `_linear_slope`, `_months_in_window`, `_score_label` helpers | Unit-testable in isolation |
| 3 | `backend/routes/purchase_orders.py` | Add `_compute_all_evaluations()` inner function + `get_supplier_evaluation()` endpoint | `GET /api/purchase-orders/evaluation` returns 200 |
| 4 | `backend/routes/purchase_orders.py` | Add `get_supplier_evaluation_detail()` endpoint | `GET /api/purchase-orders/evaluation/{name}` returns 200 or 404 |
| 5 | `frontend/src/api/purchase_orders.js` | Add `fetchSupplierEvaluation`, `fetchSupplierEvaluationDetail` | Console fetch test |
| 6 | `frontend/src/components/SupplierEvaluation.vue` | Create full component | Navigate to `/#/suppliers/evaluation` |
| 7 | `frontend/src/main.js` | Add `/suppliers/evaluation` route | Route accessible via URL |
| 8 | `frontend/src/components/SupplierDashboard.vue` | Add "供应商评估" navigation button | Button visible in dashboard header |

---

## Files Summary (Part 2)

| File | Action | Change Description |
|------|--------|--------------------|
| `backend/schemas.py` | Edit | Add `SupplierEvaluationItem`, `SupplierEvaluationResponse`, `PriceHistoryPoint`, `SupplierEvaluationDetail` |
| `backend/routes/purchase_orders.py` | Edit | Add helpers (`_linear_slope`, `_months_in_window`, `_score_label`), `_compute_all_evaluations()`, `GET /evaluation`, `GET /evaluation/{seller_name}` |
| `frontend/src/api/purchase_orders.js` | Edit | Add `fetchSupplierEvaluation()`, `fetchSupplierEvaluationDetail()` |
| `frontend/src/components/SupplierEvaluation.vue` | **Create** | New evaluation page: table + inline radar + price trend line chart |
| `frontend/src/main.js` | Edit | Import `SupplierEvaluation`, add `/suppliers/evaluation` route |
| `frontend/src/components/SupplierDashboard.vue` | Edit | Add "供应商评估" button in dashboard header |
