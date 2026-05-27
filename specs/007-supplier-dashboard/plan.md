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
