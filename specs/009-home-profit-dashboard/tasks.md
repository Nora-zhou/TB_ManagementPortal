---
description: "Task list for 009-home-profit-dashboard"
---

# Tasks: 首页利润分析仪表�?

**Input**: `specs/009-home-profit-dashboard/`

**Prerequisites**: plan.md �? spec.md �?

**Organization**: Backend first (Phases 1�?), then Frontend by user story (Phases 3�?).
No new DB tables �?queries run against existing `SubOrder` and `PurchaseOrder` tables.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with sibling tasks (different files, no shared dependency)
- **[Story]**: US1 / US2 / US3 / US4 maps to spec.md user stories
- Exact file paths and change descriptions are included in every task

---

## Phase 1: Backend Schemas (Blocking prerequisite for Phase 2)

**Purpose**: Add the three Pydantic response models that `backend/routes/stats.py` will import.  
No existing schemas are modified �?all additions are appended to the end of the file.

- [x] T001 [US1] Append `ProfitMonthlySeries`, `ProfitMonthlyKPI`, and `ProfitMonthlyResponse` Pydantic classes to `backend/schemas.py`
  - Add `ProfitMonthlySeries(BaseModel)` with 12 `list[float]` fields: `revenue_s1`, `revenue_s2`, `cost_s1`, `cost_s2`, `refund_s1`, `refund_s2`, `profit_s1`, `profit_s2`, `total_revenue`, `total_cost`, `total_refund`, `total_profit`
  - Add `ProfitMonthlyKPI(BaseModel)` with the same 12 names but as `float` scalars
  - Add `ProfitMonthlyResponse(BaseModel)` with fields `months: list[str]`, `series: ProfitMonthlySeries`, `kpi: ProfitMonthlyKPI`

**Checkpoint**: `from schemas import ProfitMonthlyResponse` succeeds in a Python REPL.

---

## Phase 2: Backend Route (depends on T001)

**Purpose**: Implement the `GET /api/stats/profit-monthly` endpoint and wire it into FastAPI.

- [x] T002 [US1] Create `backend/routes/stats.py` �?router skeleton, constants, and `_validate_month` helper
  - `from __future__ import annotations`, import `re`, `Optional`, `APIRouter`, `Depends`, `HTTPException`, `Query`, `SQLAlchemy Float`, `case`, `cast`, `Session`, `func`, `select`
  - Import `get_session` from `database`, `PurchaseOrder`, `SubOrder` from `models`, and the 3 new schemas from `schemas`
  - Define `router = APIRouter(prefix="/stats", tags=["stats"])`
  - Define module-level constants: `_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")`, `_PO_EXCLUDED`, `_SO_SUCCESS`, `_SO_REFUND_STATUSES`
  - Define `_validate_month(value, param)` �?raises `HTTPException(422)` if value is not None and doesn't match `_MONTH_RE`

- [x] T003 [US1] Add `GET /api/stats/profit-monthly` endpoint to `backend/routes/stats.py` �?SubOrder aggregation query
  - Add `@router.get("/profit-monthly", response_model=ProfitMonthlyResponse)` function with `start_month`, `end_month` Query params and `session` dependency
  - Call `_validate_month` for both params
  - Build `so_stmt` using `func.coalesce(SubOrder.paid_at, SubOrder.created_at)` as `so_coalesce`, `func.strftime("%Y-%m", so_coalesce)` as `so_month`
  - `SELECT SubOrder.store, so_month.label("month_key"), SUM(CASE status='交易成功' THEN buyer_paid ELSE 0.0).label("revenue"), SUM(CASE status IN refund_statuses THEN CAST(refund_amount AS FLOAT) ELSE 0.0).label("refund")`
  - `.where(so_coalesce.isnot(None)).group_by(SubOrder.store, so_month)`
  - Conditionally `.where(so_month >= start_month)` / `.where(so_month <= end_month)` if params are provided
  - Execute: `so_rows = session.exec(so_stmt).all()`

- [x] T004 [US1] Add PurchaseOrder aggregation query and data-merge logic to `backend/routes/stats.py`
  - Build `po_stmt`: `SELECT PurchaseOrder.store, po_month.label("month_key"), SUM(paid_amount).label("cost")` using `func.coalesce(PurchaseOrder.paid_at, PurchaseOrder.created_at)` �?exclude `_PO_EXCLUDED` statuses via `.where(PurchaseOrder.status.not_in(list(_PO_EXCLUDED)))`, apply optional month range filters, group by store + month
  - Execute: `po_rows = session.exec(po_stmt).all()`
  - Merge rows into `data: dict[tuple[int, str], dict]` keyed by `(store, month_key)` with sub-keys `revenue`, `refund`, `cost` �?defaulting missing keys to `0.0`

- [x] T005 [US1] Add response-building logic and return statement to `backend/routes/stats.py`
  - Build `all_months = sorted({mk for (_, mk) in data.keys()})`
  - Return empty-data guard: if `not all_months`, return `ProfitMonthlyResponse` with empty `months=[]`, all-zero `ProfitMonthlyKPI`, and empty-list `ProfitMonthlySeries`
  - Define `_v(store, month, field)` helper returning `data.get((store, month), {}).get(field, 0.0)`
  - Build per-store monthly lists: `rev_s1`, `rev_s2`, `cost_s1`, `cost_s2`, `refund_s1`, `refund_s2`
  - Compute: `profit_sN[i] = round(rev_sN[i] - refund_sN[i] - cost_sN[i], 2)`; `total_*` lists summing both stores
  - Build `ProfitMonthlyKPI` by summing each list, with `profit_sN = _sum(rev_sN) - _sum(refund_sN) - _sum(cost_sN)` and `total_profit` summing both
  - Build `ProfitMonthlySeries` from the 12 computed lists
  - Return `ProfitMonthlyResponse(months=all_months, series=series, kpi=kpi)`

- [x] T006 [US1] Register `stats_router` in `backend/main.py`
  - Add import line after existing router imports: `from routes.stats import router as stats_router`
  - Add after last `app.include_router(...)` call: `app.include_router(stats_router, prefix="/api")`

**Checkpoint**: `GET http://localhost:8000/api/stats/profit-monthly` returns HTTP 200 with `months`, `series`, and `kpi` fields; `GET .../profit-monthly?start_month=bad` returns HTTP 422.

---

## Phase 3: Frontend US-1 �?首页利润概览 (depends on T006)

**Goal**: Render KPI cards at `/#/` showing 1�?/ 2�?/ 合计 revenue, cost, and net profit.

**Independent Test**: Navigate to `/#/`; 9 KPI cards display with `¥X,XXX.XX` formatted values; no redirect occurs.

- [x] T007 [P] [US1] Create `frontend/src/api/stats.js`
  - `const BASE = '/api/stats'`
  - Export `async function fetchProfitMonthly({ startMonth, endMonth } = {})` that builds `URLSearchParams`, constructs the URL, fetches, throws on non-ok, and returns `res.json()`

- [x] T008 [US1] Create `frontend/src/components/HomeDashboard.vue` �?`<script setup>` section
  - Import `{ ref, computed, onMounted, watch }` from `vue`
  - Import ECharts tree-shaking: `use` from `echarts/core`; `CanvasRenderer`; `BarChart`, `LineChart`, `PieChart`; `GridComponent`, `TooltipComponent`, `LegendComponent`, `TitleComponent`
  - Import `VChart` from `vue-echarts`; import `fetchProfitMonthly` from `'../api/stats.js'`
  - Call `use([CanvasRenderer, BarChart, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent])`
  - Define `MONTH_RE = /^\d{4}-\d{2}$/`
  - Define refs: `startMonth`, `endMonth` (empty string), `loading` (false), `error` (null), `data` (null)
  - Define `async function loadData()` �?validates both month refs against `MONTH_RE` (returns early if invalid and non-empty), sets `loading = true`, calls `fetchProfitMonthly`, sets `data.value`, handles errors in catch, sets `loading = false` in finally
  - Call `onMounted(loadData)` and `watch([startMonth, endMonth], loadData)`
  - Define `kpi` computed �?returns `data.value?.kpi` or an all-zero fallback object with all 12 KPI fields
  - Define `fmt(n)` �?`Number(n ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })`
  - Define `hasData` computed �?`data.value?.months?.length > 0`

- [x] T009 [US1] Add `<template>` and `<style scoped>` to `HomeDashboard.vue` �?filter row and KPI cards
  - Root `<div class="home-dashboard">` with `<h2>利润分析总览</h2>`
  - Filter row: `<div class="filter-row">` containing two `<label class="filter-label">` each with a `<input v-model type="text" placeholder="YYYY-MM" class="month-input" maxlength="7">`; first label: 开始月�? second: 结束月份
  - Loading state: `<div v-if="loading" class="status-msg">加载中�?/div>`
  - Error state: `<div v-else-if="error" class="error-msg">{{ error }}</div>`
  - KPI section (`<template v-if="!loading && !error">`): `<div class="kpi-section">` containing:
    - Label `<div class="kpi-store-label">1 �?/div>`
    - First `<div class="kpi-grid">` with 6 `<div class="kpi-card">` �?1店收�? 1店成�? 1店净利润, 2店收�? 2店成�? 2店净利润; profit cards use `:class="kpi.profit_sN >= 0 ? 'kpi-profit' : 'kpi-loss'"`
    - Label `<div class="kpi-store-label kpi-total-label">合计</div>`
    - Second `<div class="kpi-grid">` with 3 `<div class="kpi-card kpi-card--total">` �?合计收入, 合计成本, 合计净利润
  - Add `<style scoped>` with: `.home-dashboard` (max-width 1100px, centered, padded), `.filter-row` (flex, gap 16px), `.month-input` (border, border-radius 6px, width 100px, focus border #409eff), `.kpi-grid` (CSS Grid `repeat(3, 1fr)`, gap 12px), `.kpi-card` (border-radius 8px, padding 16px 20px), `.kpi-value` (font-size 20px, font-weight 600), `.kpi-profit` (color #67c23a), `.kpi-loss` (color #f56c6c), `.kpi-card--total` (box-shadow), `.status-msg` (centered, 40px padding), `.error-msg` (color #f56c6c)

**Checkpoint**: `/#/` renders without redirect; 9 KPI cards show formatted `¥` amounts; invalid month input does not trigger a fetch.

---

## Phase 4: Frontend US-2 �?月度利润走势�?(depends on T008–T009)

**Goal**: Dual Y-axis line + bar ECharts chart showing monthly trend of revenue, cost, and profit.

**Independent Test**: Chart renders with 5 series (3 lines on left Y-axis, 2 bars on right); legend toggles work; tooltip shows all series on hover.

- [x] T010 [US2] Add `trendOption` computed property to `HomeDashboard.vue` `<script setup>`
  - Guard: `if (!data.value?.months?.length) return {}`
  - Destructure `{ months, series: s }` from `data.value`
  - Return ECharts option with: `tooltip.trigger='axis'` + custom `formatter` using `toLocaleString('zh-CN', {minimumFractionDigits:2})`; `legend: { type: 'scroll', bottom: 0 }`; `grid: { left: '3%', right: '8%', bottom: '15%', containLabel: true }`
  - `xAxis: { type: 'category', data: months, boundaryGap: false }`
  - `yAxis` array: index 0 (`name: '金额（元�?`, left, label formatter `¥${v/1000}K`), index 1 (`name: '分店利润（元�?`, right, same label format)
  - `series`: `总收入` (line, smooth, yAxisIndex 0, color #409eff, data `s.total_revenue`); `总成本` (line, smooth, yAxisIndex 0, color #e6a23c, data `s.total_cost`); `净利润` (line, smooth, yAxisIndex 0, color #67c23a, data `s.total_profit`); `1店利润` (bar, yAxisIndex 1, color rgba(64,158,255,0.5), data `s.profit_s1`); `2店利润` (bar, yAxisIndex 1, color rgba(103,194,58,0.5), data `s.profit_s2`)

- [x] T011 [US2] Add trend chart block to `HomeDashboard.vue` `<template>` (after KPI section, inside the `v-if` wrapper)
  - `<div class="chart-block">` containing `<div class="chart-title">月度利润走势</div>`
  - `<div v-if="!hasData" class="chart-empty">暂无数据</div>`
  - `<v-chart v-else :option="trendOption" autoresize style="height: 420px; width: 100%;" />`
  - Add `.chart-block` CSS (background `var(--bg-subtle, #f5f7fa)`, border, border-radius 8px, padding 16px, margin-bottom 20px), `.chart-title` (font-size 14px, font-weight 600), `.chart-empty` (height 120px, flex center, color muted)

**Checkpoint**: Trend chart renders with 5 legend entries; clicking a legend entry toggles that series; tooltip on hover shows all 5 series values for that month.

---

## Phase 5: Frontend US-4 �?成本与利润比例图 (depends on T008–T009)

**Goal**: Donut ECharts pie chart showing net profit / total cost / refund proportions.

**Independent Test**: Pie chart shows 2�? sectors; when total_profit �?0 the 净利润 sector is absent; percentage labels visible.

- [x] T012 [US4] Add `pieOption` computed property to `HomeDashboard.vue` `<script setup>`
  - Guard: `if (!data.value) return {}`
  - Destructure `{ total_profit, total_cost, total_refund }` from `data.value.kpi`
  - `const profitVal = Math.max(0, total_profit)`; build `pieData = []`; conditionally push `{ name: '净利润', value: profitVal, itemStyle: { color: '#67c23a' } }` if `profitVal > 0`; always push `{ name: '总成�?, value: total_cost, itemStyle: { color: '#e6a23c' } }`; conditionally push `{ name: '退�?, value: total_refund, itemStyle: { color: '#f56c6c' } }` if `total_refund > 0`
  - Return option with `tooltip: { trigger: 'item', formatter: '{a} <br/>{b}：¥{c} ({d}%)' }`; `legend: { orient: 'horizontal', bottom: 0 }`; single `series` entry: `type: 'pie'`, `radius: ['40%', '68%']` (donut), `data: pieData`, `label: { formatter: '{b}\n{d}%' }`, `emphasis.itemStyle` shadow

- [x] T013 [US4] Add pie chart block to `HomeDashboard.vue` `<template>` (after trend chart block)
  - `<div class="chart-block">` containing `<div class="chart-title">收入构成（净利润 / 成本 / 退款）</div>`
  - `<div v-if="!hasData" class="chart-empty">暂无数据</div>`
  - `<v-chart v-else :option="pieOption" autoresize style="height: 360px; width: 100%;" />`

**Checkpoint**: Pie chart renders as donut with 2�? labeled sectors; sector percentages sum to 100%; applying a month filter updates both charts simultaneously.

---

## Phase 6: Routing & Navigation (depends on T008; enables US-1 entry point)

**Purpose**: Wire `HomeDashboard` into the Vue Router and add the 首页 nav link.

- [x] T014 [US1] Update `frontend/src/main.js` �?change root route from redirect to HomeDashboard
  - Add import: `import HomeDashboard from './components/HomeDashboard.vue'` (after existing component imports)
  - Replace `{ path: '/', redirect: '/products' }` with `{ path: '/', component: HomeDashboard }`

- [x] T015 [US1] Add 首页 nav link to `frontend/src/App.vue`
  - Inside `<nav class="nav-links">`, insert as the **first** child before `商品列表`:
    ```html
    <router-link to="/" class="nav-link" active-class="nav-link--active" exact-active-class="nav-link--active">首页</router-link>
    ```
  - Use `exact-active-class` to prevent the 首页 link from being highlighted when navigating to nested routes like `/products`

**Checkpoint**: Navigating to `http://localhost:5173/#/` renders `HomeDashboard` directly; nav bar shows 首页 as the leftmost link; 首页 link is only highlighted when on `/`.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T016 [P] Verify `GET /api/stats/profit-monthly?start_month=2026-01&end_month=2026-03` returns only months in range and all `series.*` arrays have the same length as `months`
- [x] T017 [P] Verify `GET /api/stats/profit-monthly?start_month=bad-month` returns HTTP 422 (not 500)
- [x] T018 [P] Confirm existing backend tests (`backend/tests/`) still pass �?the new `stats` router adds no changes to existing routes

---

## Dependencies

```
T001
 └─ T002
     └─ T003
         └─ T004
             └─ T005
                 └─ T006   �?backend complete
                     └─ T007 (can run with T008 in parallel)
                         └─ T008
                             └─ T009   �?US-1 & US-3 complete
                                 ├─ T010
                                 �?  └─ T011   �?US-2 complete
                                 └─ T012
                                     └─ T013   �?US-4 complete
T014 (depends on T008)
T015 (depends on T014)
T016–T018: verification, run after T006 / T015
```

## Parallel Opportunities

Within Phase 3: T007 (`api/stats.js`) can be created in parallel with any other task �?it has no dependencies beyond T006.

Within Phase 4 & 5: T010–T011 (trend chart) and T012–T013 (pie chart) can be worked in parallel since they modify the same file but in independent sections �?coordinate by completing T009 first to avoid merge conflicts.

## Implementation Strategy

**MVP** (just US-1): Complete T001–T009, T014–T015 �?`/` shows KPI cards with month filter.  
**Full delivery**: Add T010–T013 �?trend and pie charts appear below KPI cards.
