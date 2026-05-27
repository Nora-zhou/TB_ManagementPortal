# Tasks: 供应商采购分析仪表盘

**Feature**: `007-supplier-dashboard` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Organization**: 任务按 User Story 分组，支持独立实现与测试。

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: 可并行执行（不同文件，无未完成依赖）
- **[Story]**: 所属 User Story（US1 / US2 / US3）
- 每个任务包含精确文件路径

---

## Phase 1: Setup（确认依赖）

**Purpose**: 确认前端图表依赖就绪，无需安装新包

- [X] T001 确认 `frontend/package.json` 中已包含 `echarts` 与 `vue-echarts`；确认 `BarChart` 可从 `echarts/charts` 导入、`LegendScrollComponent` 可从 `echarts/components` 导入；无需执行 `npm install`

---

## Phase 2: Foundational（后端 API — 阻塞所有前端任务）

**Purpose**: 新增 Pydantic Schema 与仪表盘端点，所有前端 User Story 均依赖此阶段完成

**⚠️ 关键**: 此阶段全部完成后，前端各 User Story 方可并行推进

- [X] T002 在 `backend/schemas.py` 末尾（`PurchaseOrderDetailResponse` 类之后）新增三个 Pydantic 类：`TopSupplierItem`（seller_name: str、total_amount: float、total_orders: int）、`SupplierMonthlyItem`（seller_name: str、monthly_orders: dict[str, int]、monthly_amounts: dict[str, float]）、`SupplierDashboardResponse`（top_suppliers: list[TopSupplierItem]、months: list[str]、monthly_data: list[SupplierMonthlyItem]）
- [X] T003 在 `backend/routes/purchase_orders.py` 的 schema import 块中追加 `TopSupplierItem`、`SupplierMonthlyItem`、`SupplierDashboardResponse`；在文件末尾新增 `GET /dashboard` 端点 `get_supplier_dashboard(top_n: int = Query(default=15, ge=1, le=100), start_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"), end_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"), session: Session = Depends(get_session))`；实现步骤：①复用已有 `EXCLUDED_STATUSES` 构建 base_filters（排除三种状态 + created_at/paid_amount 非空 + 可选月份范围过滤）；②第一条 SQL：按 `seller_name` 聚合 `paid_amount` 求和与 `id` 计数，降序排列取前 `top_n`，空结果直接返回空 `SupplierDashboardResponse`；③第二条 SQL：对 Top N 供应商按 `seller_name` + `strftime("%Y-%m", created_at)` 二维聚合；④Python 端收集所有月份升序排列；⑤逐供应商 `dict.get(m, 0)` 零填充；⑥返回 `SupplierDashboardResponse`；response_model 设为 `SupplierDashboardResponse`

**Checkpoint**: `python -c "from schemas import SupplierDashboardResponse; print('OK')"` 输出 OK；`GET /api/purchase-orders/dashboard` 返回 HTTP 200，响应体含 `top_suppliers`、`months`、`monthly_data` 三个字段

---

## Phase 3: User Story 1 + User Story 2 — 仪表盘页面与导航入口（Priority: P1）🎯 MVP

**Goal**: 用户可从供应商管理页跳转至 `/suppliers/dashboard`，页面加载后显示月份过滤器与 Chart 1（水平条形图——Top 15 供应商历史总采购金额）

**Independent Test**: 在供应商管理页（`/#/suppliers`）点击「供应商图表」按钮，确认跳转至 `/#/suppliers/dashboard`；页面加载完成后 Chart 1 显示不超过 15 条水平条形，金额最高的供应商在最顶部，悬停显示 tooltip；点击「返回供应商列表」跳回 `/#/suppliers`

### Implementation for User Story 1 + User Story 2

- [X] T004 [P] [US1] 在 `frontend/src/api/purchase_orders.js` 末尾新增 `fetchSupplierDashboard({ topN = 15, startMonth, endMonth } = {})` 函数：用 `URLSearchParams` 构造 `top_n`（含 `start_month` / `end_month` 若有值），`fetch` 调用 `${BASE}/dashboard?${p}`，`!res.ok` 时 `throw await res.json()`，成功返回 `res.json()`
- [X] T005 [US1] [US2] 新建 `frontend/src/components/SupplierDashboard.vue`（`<script setup>` 单文件组件）：①导入并 `use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, LegendScrollComponent])`；②导入 `useRouter`、`fetchAvailableMonths`、`fetchSupplierDashboard`、`VChart`；③声明 ref：`availableMonths`、`startMonth`（''）、`endMonth`（''）、`loading`、`error`、`dashData`、`chart1Option`（{}）；④实现 `monthKey(m)` 工具函数（返回 `YYYY-MM` 字符串）；⑤实现 `loadMonths()`（调用 `fetchAvailableMonths`，按月份升序排列存入 `availableMonths`）；⑥实现 `buildCharts()`：当 `dashData` 无数据时将三个 option 置为 `{}`；否则构建 Chart 1 option（`type: 'bar'`，`xAxis.type: 'value'`，`yAxis.type: 'category'`，供应商列表逆序使金额最高者在顶部，`axisLabel.overflow: 'truncate'`，`width: 120`，tooltip formatter 展示供应商名和金额）；⑦实现 `loadDashboard()`（设置 loading、传入 startMonth/endMonth 调用 API、调用 buildCharts、捕获错误）；⑧`onMounted` 顺序调用 `loadMonths()` 与 `loadDashboard()`；⑨template 包含：header 区（`← 返回供应商列表`按钮 + 页面标题）、月份过滤行（开始月/结束月两个 `<select>`，选项来自 `availableMonths`，`@change` 触发 `loadDashboard`）、loading/error/暂无数据状态、Chart 1 VChart 块（`style="height:420px; width:100%"` + `autoresize`）；⑩scoped style：`.supplier-dashboard`、`.dashboard-header`、`.btn-back`、`.filter-row`、`.chart-block`（含 `margin-bottom:32px`）、`.status-msg`、`.error-msg`
- [X] T006 [US1] 在 `frontend/src/main.js` 中导入 `SupplierDashboard`（与现有组件 import 并列），并在 `routes` 数组的 `/suppliers` 条目之后新增 `{ path: '/suppliers/dashboard', component: SupplierDashboard }`
- [X] T007 [P] [US1] 在 `frontend/src/components/SupplierManagement.vue` 的 `<script setup>` 顶部新增 `import { useRouter } from 'vue-router'` 与 `const router = useRouter()`；在模板顶层 `<div>` 内（月份选择器之前）新增按钮 `<button @click="router.push('/suppliers/dashboard')" class="btn-chart">供应商图表</button>` 及其包装 `<div style="margin-bottom:12px;">`；在 `<style scoped>` 中追加 `.btn-chart`（padding、background `#409eff`、color white、border none、border-radius、cursor pointer、font-size 14px）和 `.btn-chart:hover { background: #337ecc; }`

**Checkpoint**: US1 + US2 独立可用 — 「供应商图表」按钮可见，点击跳转正常，仪表盘页面 Chart 1 水平条形图渲染正确，「返回供应商列表」可用

---

## Phase 4: User Story 3 — 按月趋势对比图表（Priority: P2）

**Goal**: 在 Chart 1 下方新增 Chart 2（按月订单数量堆叠柱状图）与 Chart 3（按月采购金额堆叠柱状图），legend 支持滚动与点击隐藏

**Independent Test**: 仪表盘加载后 Chart 2 和 Chart 3 的 X 轴显示按升序排列的全部月份；点击 legend 中某供应商名称，该供应商柱条从图表消失，其他供应商不受影响；某供应商在某月无订单时对应柱高为 0 而非缺失

### Implementation for User Story 3

- [X] T008 [US3] 在 `SupplierDashboard.vue` 的 `buildCharts()` 函数中（Chart 1 option 赋值之后）追加 Chart 2 逻辑：声明 `chart2Option` ref（初始 `{}`）；构建 `series2`（按 top_suppliers 顺序遍历，每家供应商一个 `{ name, type: 'bar', stack: 'orders', data: months.map(...monthly_orders[m] ?? 0), emphasis: { focus: 'series' } }` 对象）；赋值 `chart2Option`（title `按月订单数量对比（Top 供应商）`、tooltip trigger `axis`、`legend { type: 'scroll', bottom: 0 }`、xAxis category months、yAxis value 单位「订单数」）；在模板 Chart 1 VChart 块之后新增 Chart 2 `<div class="chart-block">` 包含 `<v-chart :option="chart2Option" autoresize style="height:440px; width:100%;" />`
- [X] T009 [US3] 在 `SupplierDashboard.vue` 的 `buildCharts()` 中（Chart 2 之后）追加 Chart 3 逻辑：声明 `chart3Option` ref（初始 `{}`）；构建 `series3`（结构同 Chart 2 但 `stack: 'amounts'`，data 来自 `monthly_amounts`）；赋值 `chart3Option`（title `按月采购金额对比（Top 供应商）`、tooltip 含 `valueFormatter: v => '¥' + v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })`、`legend { type: 'scroll', bottom: 0 }`、yAxis 单位「金额（元）」）；在模板 Chart 2 VChart 块之后新增 Chart 3 `<div class="chart-block">` 包含 `<v-chart :option="chart3Option" autoresize style="height:440px; width:100%;" />`；确认 `buildCharts()` 在无数据分支中也将 `chart2Option` 和 `chart3Option` 置为 `{}`

**Checkpoint**: US3 完成 — 三张图表全部渲染，月份过滤联动所有图表，legend 可交互（点击隐藏/显示单个供应商 series）

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: 构建验证与端到端冒烟测试

- [X] T010 [P] 在 `frontend/` 目录执行 `npm run build`，确认零编译错误；访问 `GET /api/purchase-orders/dashboard?top_n=15`，确认 HTTP 200 且响应体结构含 `top_suppliers`（数组，每项含 seller_name / total_amount / total_orders）、`months`（字符串数组，格式 YYYY-MM）、`monthly_data`（数组，每项含 seller_name / monthly_orders / monthly_amounts）；验证空数据场景（若表为空，API 返回 `{top_suppliers:[], months:[], monthly_data:[]}`，前端显示「暂无数据」而非崩溃）

---

## Dependencies（Story 完成顺序）

```
T001（Setup）
  └─► T002 T003（Phase 2: Foundational — 后端 API）
        ├─► T004 T005 T006 T007（US1 + US2: 仪表盘页面 + Chart 1 + 导航）  ← 独立，可单独交付
        └─► T008 T009（US3: Charts 2 & 3）                                   ← 依赖 T005 组件基础
              └─► T010（Polish）
```

## Parallel Execution Examples

**Phase 2 内部并行**（T001 完成后）:
- `T002` Schema（schemas.py）与后续 `T003` 端点串行（T003 导入 T002 的类）

**Phase 3 内部并行**（T003 完成后）:
- `T004` 前端 API 函数 ‖ `T007` SupplierManagement.vue 按钮（不同文件，相互独立）
- `T005` 创建 SupplierDashboard.vue → `T006` 注册路由（T006 依赖 T005 先存在）

**Phase 4 内部**（T005 完成后）:
- `T008` Chart 2 → `T009` Chart 3（同一文件，顺序追加）

**跨 Story 并行**（T003 完成后）:
- Phase 3 全部任务（T004–T007）可与后端无关的准备工作并行
- Phase 3 完成后 Phase 4（T008–T009）独立推进，不影响 Phase 5 的构建验证启动

---

## Implementation Strategy

**MVP 范围**（Phase 1–3，T001–T007）: 后端 API + 仪表盘页面 + Chart 1 + 导航入口 — 覆盖 US1 与 US2 全部验收场景，可独立交付

**完整交付**（Phase 4，T008–T009）: 追加 Charts 2 & 3，覆盖 US3 月度趋势分析功能

**文件变更汇总**:

| 文件 | 操作 | 任务 |
|------|------|------|
| `backend/schemas.py` | Edit | T002 |
| `backend/routes/purchase_orders.py` | Edit | T003 |
| `frontend/src/api/purchase_orders.js` | Edit | T004 |
| `frontend/src/components/SupplierDashboard.vue` | **Create** | T005, T008, T009 |
| `frontend/src/main.js` | Edit | T006 |
| `frontend/src/components/SupplierManagement.vue` | Edit | T007 |
