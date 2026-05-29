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

---

---

# Part 2: 供应商综合评估看板

**Feature**: `007-supplier-dashboard` (extension) | **Spec**: [spec.md](./spec.md) — Part 2 | **Plan**: [plan.md](./plan.md) — Part 2

**Organization**: 任务严格按执行顺序排列（按执行顺序生成 task）；[后端] 任务先行，[前端] 任务在后端 API 完成后推进。

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: 可并行执行（不同文件，无未完成依赖）
- **[USE1/USE2/USE3]**: 所属 User Story（USE1 评分列表 / USE2 雷达图 / USE3 折线图）
- 每个任务包含精确文件路径

---

## Phase 6: [后端] Foundational — Schemas + 辅助函数

**Purpose**: 新增 4 个 Pydantic Schema 和 3 个纯 Python 辅助函数，为评估端点提供类型系统与计算基础；所有后续任务均依赖此阶段完成

**⚠️ 关键**: T011–T012 全部完成后，Phase 7 方可推进

- [x] T011 在 `backend/schemas.py` 末尾（`SupplierDashboardResponse` 类之后）新增 4 个 Pydantic 类：`SupplierEvaluationItem`（字段：seller_name: str、score: Optional[float]、label: str、completion_rate: Optional[float]、price_stability: Optional[float]、activity_rate: Optional[float]、price_trend_score: Optional[float]、total_amount: float、order_count: int）；`SupplierEvaluationResponse`（suppliers: list[SupplierEvaluationItem]）；`PriceHistoryPoint`（month: str、goods_title: str、avg_unit_price: float）；`SupplierEvaluationDetail`（seller_name: str、score: Optional[float]、label: str、dimensions: dict[str, Optional[float]]、price_history: list[PriceHistoryPoint]）；所有类继承 `BaseModel`，`Optional` 已在文件顶部导入

- [x] T012 在 `backend/routes/purchase_orders.py` 文件顶部现有 import 块中追加 `import math`；在 `get_supplier_dashboard` 函数末尾之后追加 3 个辅助函数：`_linear_slope(ys: list[float]) -> float`（OLS 斜率：n=len(ys)，n<2 返回 0.0；xs=list(range(n))；denom = n*Σx²-(Σx)²，denom==0 返回 0.0；return (n*Σxy - Σx*Σy)/denom）；`_months_in_window(start: Optional[str], end: Optional[str], db_min: Optional[str], db_max: Optional[str]) -> int`（s=start or db_min，e=end or db_max，两者任一为 None 返回 1；sy,sm=int(s[:4]),int(s[5:7])；ey,em=int(e[:4]),int(e[5:7])；return max((ey-sy)*12 + (em-sm) + 1, 1)）；`_score_label(score: Optional[float]) -> str`（None→"数据不足"；≥85→"优质供应商 ⭐⭐⭐"；≥65→"稳定合作商 ⭐⭐"；≥45→"一般供应商 ⭐"；else→"需关注 ⚠️"）

**Checkpoint**: `python -c "from schemas import SupplierEvaluationDetail; print('OK')"` 输出 OK；`python -c "from routes.purchase_orders import _linear_slope; print(_linear_slope([1.0,2.0,3.0]))"` 输出 1.0

---

## Phase 7: [后端] 核心计算函数 + 评估端点（阻塞所有前端任务）

**Purpose**: 扩展 schema import 块，新增批量评分核心函数 `_compute_all_evaluations()`，再依次追加两个评估端点

**⚠️ 关键**: T013–T016 全部完成后，[前端] 各 Phase 方可推进

- [x] T013 在 `backend/routes/purchase_orders.py` 顶部的 `from schemas import (...)` 块中追加 4 个名称：`SupplierEvaluationItem`、`SupplierEvaluationResponse`、`PriceHistoryPoint`、`SupplierEvaluationDetail`

- [x] T014 在 `backend/routes/purchase_orders.py` 的 `_score_label` 函数之后追加 `_compute_all_evaluations(session: Session, start_month: Optional[str], end_month: Optional[str]) -> list[SupplierEvaluationItem]` 函数，按以下 7 步实现：①Step 0：查询 `MIN(strftime('%Y-%m', created_at))` 和 `MAX(strftime('%Y-%m', created_at))`（WHERE created_at IS NOT NULL + 可选日期过滤），调用 `_months_in_window(start_month, end_month, db_min, db_max)` 得到 `total_months`；②Step 1 (stmt1)：按 seller_name 聚合，CASE WHEN 计算 `denom`（status != '等待买家付款' 的订单数）、`numer`（status = '交易成功' 的订单数）、`total_amount`（status='交易成功' 且 paid_amount IS NOT NULL 的 paid_amount 合计），WHERE status != '等待买家付款' AND created_at IS NOT NULL + 可选日期过滤；③Step 2 (stmt2)：按 (seller_name, goods_title) 聚合 `AVG(unit_price)` 为 avg_price、`AVG(unit_price * unit_price) - AVG(unit_price) * AVG(unit_price)` 为 var_price、`SUM(paid_amount)` 为 total_paid，WHERE status='交易成功' AND unit_price IS NOT NULL AND goods_title IS NOT NULL AND created_at IS NOT NULL + 可选日期过滤；Python 端对每个供应商计算各货品 `std=sqrt(max(var_price,0))`、`cv=std/avg_price if avg_price>0 else 0`，`weighted_cv=Σ(total_paid×cv)/Σ(total_paid) if Σ(total_paid)>0 else 0`，`price_stability=max(0, 1-weighted_cv)×100`（若该供应商无 stmt2 数据行则 price_stability=0）；④Step 3 (stmt3)：按 seller_name 聚合 `COUNT(DISTINCT strftime('%Y-%m', created_at))` 为 active_months，WHERE status='交易成功' AND created_at IS NOT NULL + 可选日期过滤；`activity_rate=min(active_months/total_months×100, 100)`；⑤Step 4 (stmt4)：按 (seller_name, ym) 聚合 `SUM(unit_price×quantity)/SUM(quantity)` 为 wavg_price，WHERE status='交易成功' AND unit_price IS NOT NULL AND quantity IS NOT NULL AND quantity>0 AND created_at IS NOT NULL + 可选日期过滤，ORDER BY seller_name, ym；Python 端按 seller_name 分组提取排序好的 wavg_prices 列表，调用 `_linear_slope` 得 slope；⑥Step 5：收集所有供应商的 slope；positive_slopes=[k for k in all_slopes if k>0]；若 len(positive_slopes)==0 则所有供应商 trend_score=100；若 len(positive_slopes)==1 则该供应商 trend_score=0；否则 k_min=min(positive_slopes)、k_max=max(positive_slopes)，k_min==k_max 时所有正斜率 trend_score=0，否则 trend_score=(1-(k-k_min)/(k_max-k_min))×100；k≤0 的供应商 trend_score=100；⑦Step 6：denom<3 时 score=None；否则 `score=round(completion_rate×0.35 + price_stability×0.30 + activity_rate×0.20 + trend_score×0.15, 2)`；Step 7：结果按 score 降序排列（None 排末尾）返回 `list[SupplierEvaluationItem]`

- [x] T015 [USE1] 在 `backend/routes/purchase_orders.py` 中 `_compute_all_evaluations` 函数之后追加端点：`@router.get("/evaluation", response_model=SupplierEvaluationResponse) def get_supplier_evaluation(start_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"), end_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"), session: Session = Depends(get_session))`；函数体调用 `_compute_all_evaluations(session, start_month, end_month)` 返回 `SupplierEvaluationResponse(suppliers=items)`

- [x] T016 [USE2] [USE3] 在 `backend/routes/purchase_orders.py` 中 `get_supplier_evaluation` 之后追加端点：`@router.get("/evaluation/{seller_name}", response_model=SupplierEvaluationDetail) def get_supplier_evaluation_detail(seller_name: str, start_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"), end_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"), session: Session = Depends(get_session))`；函数体：①`exists_stmt = select(PurchaseOrder.seller_name).where(PurchaseOrder.seller_name == seller_name).limit(1)`，结果为空则 `raise HTTPException(status_code=404, detail="供应商不存在")`（seller_name 通过 SQLModel `.where(PurchaseOrder.seller_name == seller_name)` 参数绑定，严禁字符串拼接到 SQL，满足 NFR-E005）；②调用 `_compute_all_evaluations(session, start_month, end_month)` 并用 `next()` 提取 target，target 为 None 时构造全 null 得分的 `SupplierEvaluationItem`；③`top10_stmt`：对该 seller_name 的 '交易成功' 订单按 goods_title 分组，`SUM(paid_amount)` 降序 `.limit(10)`；④`ph_stmt`：对 Top 10 goods_title 按 (goods_title, ym) 聚合 `SUM(unit_price×quantity)/SUM(quantity)` 为 wavg，WHERE unit_price IS NOT NULL AND quantity IS NOT NULL AND quantity>0；返回 `SupplierEvaluationDetail(seller_name, score, label, dimensions={"completion_rate":…,"price_stability":…,"activity_rate":…,"price_trend_score":…}, price_history=list[PriceHistoryPoint])`

**Checkpoint**: `GET /api/purchase-orders/evaluation` 返回 HTTP 200，`suppliers` 数组中每项含 seller_name/score/label/completion_rate/price_stability/activity_rate/price_trend_score/total_amount/order_count；`GET /api/purchase-orders/evaluation/{存在的供应商名}` 返回 HTTP 200，含 dimensions dict 和 price_history 数组；`GET /api/purchase-orders/evaluation/不存在供应商名` 返回 HTTP 404；空数据库时返回 `{"suppliers": []}`

---

## Phase 8: [前端] API 客户端（US-E1 / US-E2 / US-E3）

**Purpose**: 新增两个前端 API 封装函数，为 SupplierEvaluation.vue 提供数据层接口；此阶段可与 T015/T016 后端开发并行（不同文件）

- [x] T017 [P] [USE1] 在 `frontend/src/api/purchase_orders.js` 末尾追加两个 export 函数：`fetchSupplierEvaluation({ startMonth, endMonth } = {})` — 用 `URLSearchParams` 组装 start_month/end_month（仅有值时 `p.append`），`const qs = p.toString() ? '?' + p : ''`，`fetch` 调用 `${BASE}/evaluation${qs}`，`!res.ok` 时 `throw await res.json()`，否则 `return res.json()`；`fetchSupplierEvaluationDetail(sellerName, { startMonth, endMonth } = {})` — 同样构造 URLSearchParams，`fetch` 调用 `${BASE}/evaluation/${encodeURIComponent(sellerName)}${qs}`，相同错误处理，`return res.json()`

**Checkpoint**: 浏览器控制台 `await fetchSupplierEvaluation()` 返回 `{suppliers: [...]}`；`await fetchSupplierEvaluationDetail("不存在供应商")` 抛出含 detail 字段的 JSON 错误对象

---

## Phase 9: [前端] SupplierEvaluation.vue 组件（US-E1 / US-E2 / US-E3）

**Goal**: 新建 `frontend/src/components/SupplierEvaluation.vue`，实现评分表格、行内展开详情（雷达图 + 折线图）及月份过滤

**Independent Test**: 访问 `/#/suppliers/evaluation`，评分表格渲染并按分数降序排列；点击任意行"查看详情"，行下方内联展开雷达图（4 轴：完成率/价格稳定性/活跃度/价格走势）和折线图（各货品月度单价走势）；再次点击"收起"，详情区域折叠；月份过滤联动表格数据

- [x] T018 [USE1] 新建 `frontend/src/components/SupplierEvaluation.vue`，写入完整 `<script setup>` 块：①导入：`ref`、`onMounted` from 'vue'；`useRouter` from 'vue-router'；`use` from 'echarts/core'；`CanvasRenderer` from 'echarts/renderers'；`RadarChart`、`LineChart` from 'echarts/charts'；`TitleComponent`、`TooltipComponent`、`LegendComponent`、`LegendScrollComponent` from 'echarts/components'；`VChart` from 'vue-echarts'；`fetchAvailableMonths`、`fetchSupplierEvaluation`、`fetchSupplierEvaluationDetail` from `'../api/purchase_orders.js'`；②调用 `use([CanvasRenderer, RadarChart, LineChart, TitleComponent, TooltipComponent, LegendComponent, LegendScrollComponent])`；③`const router = useRouter()`；④ref 声明：`availableMonths`([])、`startMonth`('')、`endMonth`('')、`loading`(false)、`error`(null)、`suppliers`([])、`expandedSet`(new Set())、`detailLoading`({})、`detailError`({})、`detailData`({})；⑤工具函数：`monthKey(m)` 返回 `` `${m.year}-${String(m.month).padStart(2,'0')}` ``；`badgeStyle(score)` 返回 `{ color: ... }` 对象（null→'#888'、≥85→'green'、≥65→'#409eff'、≥45→'#e6a23c'、else→'#f56c6c'）；`trendIndicator(score)` 返回 null→'—'、≥70→'↓'、else→'↑'；⑥`loadMonths()`：调用 `fetchAvailableMonths()`，按 monthKey 升序 sort 后存入 `availableMonths`，catch 时置空数组；⑦`loadEvaluation()`：loading=true、error=null；重置 `expandedSet.value = new Set()`、`detailData.value = {}`、`detailError.value = {}`；构造 params（含 startMonth/endMonth 若有值），调用 `fetchSupplierEvaluation(params)`，赋值 `suppliers.value = data.suppliers`；catch 设 `error.value = e?.detail || '加载失败，请稍后重试'`；finally loading=false；⑧`onFilterChange()` 直接调用 `loadEvaluation()`；⑨`toggleDetail(sellerName)`：若 `expandedSet.value.has(sellerName)` 则 `expandedSet.value.delete(sellerName)` 并 return；否则 `expandedSet.value.add(sellerName)`；若 `detailData.value[sellerName]` 已存在则 return；否则 `detailLoading.value[sellerName] = true`、`detailError.value[sellerName] = null`，调用 `fetchSupplierEvaluationDetail(sellerName, params)` 存入 `detailData.value[sellerName]`，catch 设 `detailError.value[sellerName]`，finally `detailLoading.value[sellerName] = false`；⑩`radarOption(detail)`：dimKeys=['completion_rate','price_stability','activity_rate','price_trend_score']，dimLabels=['完成率','价格稳定性','活跃度','价格走势']，返回 option（title.text:'维度得分雷达图' left:'center' textStyle.fontSize:13；tooltip trigger:'item'；radar.indicator 4 个 {name,max:100} + radius:'65%'；series[{type:'radar', data:[{name:detail.seller_name, value:dimKeys.map(k=>detail.dimensions[k]??0)}], areaStyle:{opacity:0.3}}]）；⑪`priceTrendOption(detail)`：若 detail.price_history 为空返回 {}；否则从 price_history 提取唯一 months（升序）和唯一 goods_titles，构建 lookup: `{goods_title: {month: avg_unit_price}}`，每个 goods_title 生成一条 series（type:'line', smooth:true, connectNulls:false, data:months.map(m => lookup[t]?.[m] ?? null)）；返回 option（title.text:'月度单价走势（Top 10 货品）' textStyle.fontSize:13；tooltip trigger:'axis' formatter 展示月份+`${p.marker}${p.seriesName}：¥${Number(p.value).toFixed(2)}`；legend type:'scroll' bottom:0；grid left:'2%' right:'4%' bottom:'15%' containLabel:true；xAxis type:'category' data:months boundaryGap:false；yAxis type:'value' name:'单价（元）'）；⑫`onMounted(async () => { await loadMonths(); await loadEvaluation() })`；在 `</script>` 后附加占位模板 `<template><div></div></template>`（T019 将替换）

- [x] T019 [USE1] [USE2] 将 `frontend/src/components/SupplierEvaluation.vue` 的占位 `<template>` 替换为完整模板：根 `<div class="supplier-evaluation">`；①`<div class="eval-header">` — `<button class="btn-back-eval" @click="router.push('/suppliers/dashboard')">← 返回仪表盘</button>` + `<h2>供应商综合评估</h2>`；②`<div class="filter-row">` — 开始月/结束月各一个 `<select>`（v-model 绑定 startMonth/endMonth，`@change="onFilterChange"`，选项来自 availableMonths 用 monthKey(m) 生成值，含空值"全部"默认选项）；③状态行：`<div v-if="loading" class="status-msg">加载中…</div>`、`<div v-else-if="error" class="error-msg">{{ error }}</div>`、`<div v-else-if="suppliers.length === 0" class="status-msg">暂无供应商数据</div>`；④`<table v-else class="eval-table">` — thead 含 10 列（# / 供应商 / 综合得分 / 标签 / 完成率 / 价格稳定性 / 活跃度 / 价格走势 / 总采购额 / 操作）；tbody 用 `<template v-for="(s, idx) in suppliers" :key="s.seller_name">` 包含主行 `<tr>` 和详情行 `<tr>`；主行 td 依次为：idx+1、s.seller_name、`<span class="score-badge" :style="badgeStyle(s.score)">{{ s.score !== null ? s.score.toFixed(1) : '—' }}</span>`、`<span :style="badgeStyle(s.score)">{{ s.label }}</span>`、`{{ s.completion_rate !== null ? s.completion_rate.toFixed(1) : '--' }}`（price_stability / activity_rate 同理）、`{{ trendIndicator(s.price_trend_score) }}`、`` `¥${s.total_amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` ``、`<button @click="toggleDetail(s.seller_name)">{{ expandedSet.has(s.seller_name) ? '收起' : '查看详情' }}</button>`；详情行 `<tr v-if="expandedSet.has(s.seller_name)" class="detail-row"><td colspan="10"><div v-if="detailLoading[s.seller_name]" class="status-msg">加载详情中…</div><div v-else-if="detailError[s.seller_name]" class="error-msg">{{ detailError[s.seller_name] }}</div><div v-else-if="detailData[s.seller_name]" class="detail-charts"><v-chart :option="radarOption(detailData[s.seller_name])" autoresize style="height:320px;width:100%;max-width:480px;" /><v-chart :option="priceTrendOption(detailData[s.seller_name])" autoresize style="height:320px;width:100%;flex:1;" /></div></td></tr>`

- [x] T020 [USE1] 在 `frontend/src/components/SupplierEvaluation.vue` 末尾追加 `<style scoped>`：`.supplier-evaluation { padding: 16px; }`；`.eval-header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }`；`.btn-back-eval { padding: 6px 14px; background: #f0f0f0; border: 1px solid #ccc; border-radius: 4px; cursor: pointer; font-size: 14px; }`；`.btn-back-eval:hover { background: #ddd; }`；`.filter-row { display: flex; gap: 20px; margin-bottom: 20px; font-size: 14px; }`；`.filter-row select { margin-left: 6px; padding: 4px 8px; }`；`.eval-table { width: 100%; border-collapse: collapse; font-size: 13px; }`；`.eval-table th, .eval-table td { border: 1px solid #eee; padding: 8px 10px; text-align: center; }`；`.eval-table th { background: #f5f7fa; font-weight: 600; }`；`.score-badge { font-weight: 700; font-size: 15px; }`；`.detail-row td { background: #fafafa; text-align: left; }`；`.detail-charts { display: flex; gap: 16px; padding: 12px; flex-wrap: wrap; align-items: flex-start; }`；`.status-msg { text-align: center; color: #888; padding: 40px; }`；`.error-msg { text-align: center; color: #c00; padding: 40px; }`

**Checkpoint**: US-E1 独立可用 — 评分表格渲染，数据行按分数降序排列，"数据不足"行徽章显示灰色；US-E2 可用 — 点击"查看详情"后行内展开，雷达图 4 轴数值与 API `dimensions` 字段一致；US-E3 可用 — 展开详情区域折线图显示各货品月度单价，X 轴月份升序

---

## Phase 10: [前端] 路由注册 + 导航入口

- [x] T021 [P] [USE1] 在 `frontend/src/main.js` 中，于现有组件 import 列表末尾追加 `import SupplierEvaluation from './components/SupplierEvaluation.vue'`；在 `routes` 数组 `'/suppliers/dashboard'` 条目之后追加 `{ path: '/suppliers/evaluation', component: SupplierEvaluation }`

- [x] T022 [P] [USE1] 在 `frontend/src/components/SupplierDashboard.vue` 的 `<div class="dashboard-header">` 内、现有"← 返回供应商列表"按钮之后追加 `<button class="btn-eval" @click="router.push('/suppliers/evaluation')">供应商评估</button>`；在 `<style scoped>` 末尾追加 `.btn-eval { padding: 6px 16px; background: #67c23a; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }` 和 `.btn-eval:hover { background: #529b2e; }`

**Checkpoint**: `/#/suppliers/dashboard` 头部出现绿色"供应商评估"按钮；点击后跳转至 `/#/suppliers/evaluation`；评估页表格正常加载

---

## Phase 11: Polish & Build Validation

- [x] T023 [P] 在 `frontend/` 目录执行 `npm run build`，确认零编译错误；访问 `GET /api/purchase-orders/evaluation` 确认 HTTP 200，响应体 `suppliers` 数组每项含 seller_name、score（float 或 null）、label、四维度得分、total_amount、order_count；访问 `GET /api/purchase-orders/evaluation/{存在的供应商名}` 确认 HTTP 200，`dimensions` 含 4 个键，`price_history` 为数组；访问 `GET /api/purchase-orders/evaluation/不存在的供应商名` 确认 HTTP 404；验证空数据场景：数据库无采购记录时 API 返回 `{"suppliers": []}`，前端 `/#/suppliers/evaluation` 显示"暂无供应商数据"而非 JS 报错

---

## Dependencies（Part 2 Story 完成顺序）

```
T011（Schemas）
  └─► T012（Helper Functions + import math）
        └─► T013（Schema Imports in purchase_orders.py）
              └─► T014（_compute_all_evaluations）
                    ├─► T015（GET /evaluation）           ← USE1
                    └─► T016（GET /evaluation/{name}）    ← USE2/E3
                          └─► T017（API Client）[P]       ← 可与 T015/T016 并行
                                └─► T018（Vue Script Setup）
                                      ├─► T019（Vue Template）     ← USE1/E2 done
                                      │     └─► T020（Vue Style）  ← USE3 done
                                      ├─► T021（Route Reg.）[P]
                                      └─► T022（Nav Button）[P]
                                            └─► T023（Build Validation）
```

## Parallel Execution Examples

**Phase 7–8 跨并行**（T014 完成后）:
- `T017` API 客户端（`purchase_orders.js`）可与 `T015`/`T016` 并行开发（不同文件）

**Phase 9–10 内部并行**（T018 完成后）:
- `T021` 路由注册 ‖ `T022` 导航按钮（不同文件，与 T019/T020 并行）

## Implementation Strategy

**MVP 范围**（T011–T015 + T017–T022）: 覆盖 USE1 全部验收场景 — 后端评分列表接口 + 前端评分表格 + 路由与导航

**完整交付**（加 T016 + T018 中 `radarOption`/`priceTrendOption` + T019 详情行）: 覆盖 USE2（雷达图）和 USE3（折线图）验收场景

**文件变更汇总（Part 2）**:

| 文件 | 操作 | 任务 |
|------|------|------|
| `backend/schemas.py` | Edit | T011 |
| `backend/routes/purchase_orders.py` | Edit | T012, T013, T014, T015, T016 |
| `frontend/src/api/purchase_orders.js` | Edit | T017 |
| `frontend/src/components/SupplierEvaluation.vue` | **Create** | T018, T019, T020 |
| `frontend/src/main.js` | Edit | T021 |
| `frontend/src/components/SupplierDashboard.vue` | Edit | T022 |
