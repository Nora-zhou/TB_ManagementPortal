# Tasks: 商品订单实付价格走势

**Feature**: `005-product-order-price-trend` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Organization**: 任务按 User Story 分组，支持独立实现与测试。

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: 可并行执行（不同文件，无未完成依赖）
- **[Story]**: 所属 User Story（US1 / US2 / US3）
- 每个任务包含精确文件路径

---

## Phase 1: Setup（共享基础设施）

**Purpose**: 安装新依赖，为功能实现做好环境准备

- [x] T001 在 `frontend/` 目录执行 `npm install echarts-stat`，安装趋势线统计扩展包

---

## Phase 2: Foundational（阻塞性前置任务）

**Purpose**: 新增数据模型、Pydantic Schema 及路由注册，所有 User Story 均依赖此阶段完成

**⚠️ 关键**: 此阶段全部完成后，各 User Story 方可并行推进

- [x] T002 在 `backend/models.py` 中新增 `SubOrder` SQLModel 类（字段：`sub_order_id` unique+index、`main_order_id`、`taobao_item_id` index、`product_title`、`product_price`、`quantity`、`product_attr`、`status`、`payment_id`、`buyer_paid`、`refund_amount`、`created_at`、`paid_at`、`imported_at`）
- [x] T003 [P] 在 `backend/schemas.py` 中新增三个 Pydantic 类：`SubOrderImportResult`（imported/updated/skipped/errors）、`OrderPricePoint`（created_at/buyer_paid/quantity/product_attr/sub_order_id）、`OrderPriceSeriesResponse`（product_id/taobao_item_id/days/total/truncated/points）
- [x] T004 在 `backend/main.py` 中 import 并注册 `sub_orders_router`，prefix 为 `/api/sub-orders`

**Checkpoint**: 数据库表 `suborder` 已创建，Schema 可用，路由前缀已注册 → 各 User Story 可开始实现

---

## Phase 3: User Story 2 — 导入子订单 xlsx 文件（Priority: P1）

**Goal**: 卖家可上传新格式（15 列子订单格式）xlsx，系统解析后 upsert 入 `suborder` 表，返回 `{imported, updated, skipped, errors}` 统计。

**Independent Test**: 上传 `ExportOrderList*.xlsx`，确认 `suborder` 表写入记录，响应含正确的 imported/updated/errors 计数；再次上传同一文件，确认 `updated` 增加而非重复插入。

### Implementation for User Story 2

- [x] T005 [US2] 新建 `backend/routes/sub_orders.py`，实现 `POST /import` 端点：文件类型校验（415）、必填列校验（422）、openpyxl 解析 xlsx、按 `sub_order_id` upsert、跳过商品ID为空或金额无法解析的行并计入 errors、返回 `SubOrderImportResult`
- [x] T006 [P] [US2] 新建 `frontend/src/api/sub_orders.js`，实现 `importSubOrders(file)` 函数：构造 FormData 后 POST `/api/sub-orders/import`，统一抛出 `err.detail` 错误
- [x] T007 [P] [US2] 新建 `frontend/src/components/SubOrderImport.vue`：文件选择器（仅接受 .xlsx）、上传按钮、loading 状态、成功后展示 imported/updated/errors 统计结果、错误时展示 detail 信息
- [x] T008 [US2] 在 `frontend/src/components/DataImport.vue`（或对应导入页面组件）中引入并渲染 `SubOrderImport.vue`，与现有 OrderImport / ProductImport 并列

**Checkpoint**: US2 独立可用 — 可上传 xlsx、写入 `suborder` 表、查看导入统计，与走势图功能无关

---

## Phase 4: User Story 1 — 商品详情页查看订单实付价格走势（Priority: P1）🎯 MVP

**Goal**: 商品详情页新增「订单实付价格走势」散点图（含线性回归趋势线），以 `订单创建时间` 为 X 轴、`单件均价（buyer_paid ÷ quantity）` 为 Y 轴，支持近 30 天 / 近 90 天 / 全部时间范围切换，匹配到 0 条数据时展示空状态。

**Independent Test**: 先完成 US2 导入含 `商品ID = 844555963059` 的 xlsx，进入对应商品详情页，确认散点图显示且点数与「交易成功 + 无退款」子订单数一致；切换至「近 30 天」，确认数据点减少；悬停散点，确认 Tooltip 显示时间、单件均价、购买数量、规格。

### Implementation for User Story 1

- [x] T009 [US1] 在 `backend/routes/products.py` 中新增 `GET /{id}/order-price-series` 端点：通过 product_id 查 taobao_item_id，按 status='交易成功'、refund_amount='无退款申请'、days 参数过滤，ORDER BY created_at ASC，LIMIT 1000，返回 `OrderPriceSeriesResponse`（含 total、truncated）；商品不存在时返回 404
- [x] T010 [P] [US1] 在 `frontend/src/api/products.js` 中新增 `fetchOrderPriceSeries(productId, days)` 函数：调用 `GET /api/products/{id}/order-price-series?days={days}`，返回 `OrderPriceSeriesResponse`
- [x] T011 [US1] 新建 `frontend/src/components/OrderPriceChart.vue`：调用 `fetchOrderPriceSeries`、使用 `echarts.registerTransform(ecStat.transform.regression)` 注册线性回归、配置 ECharts dataset + transform 实现散点图叠加趋势线、前端计算 `unitPrice = buyer_paid / Math.max(quantity, 1)`、Tooltip 展示时间/单件均价/购买数量/商品属性、包含 30/90/全部时间范围切换按钮、空状态展示「暂无匹配订单数据，请先导入订单文件」
- [x] T012 [US1] 在 `frontend/src/components/ProductDetail.vue` 中引入并渲染 `OrderPriceChart.vue`，置于现有 `PriceChart.vue` 下方，传入 `productId` prop 与默认 `days=90`

**Checkpoint**: US1 独立可用 — 导入数据后可在商品详情页看到散点走势图与趋势线，支持时间范围切换

---

## Phase 5: User Story 3 — 商品详情页价格走势图布局（Priority: P2）

**Goal**: 商品详情页同时展示「快照标价走势」和「订单实付价格走势」两个独立图表，上下排列，布局清晰。

**Independent Test**: 进入同时有快照数据和子订单数据的商品详情页，确认页面由上至下顺序为：商品信息区 → 快照价格走势（PriceChart）→ 订单实付价格走势（OrderPriceChart）；仅有快照数据时，OrderPriceChart 显示空状态而非报错。

### Implementation for User Story 3

- [x] T013 [P] [US3] 检查并更新 `frontend/src/components/ProductDetail.vue` 的布局结构，确保 `PriceChart` 和 `OrderPriceChart` 上下排列，两者之间添加适当间距（如 `margin-top: 24px`），两个图表宽度一致
- [x] T014 [P] [US3] 在 `frontend/src/components/OrderPriceChart.vue` 中完善双空状态文案区分：`suborder` 表为空时显示「暂无订单数据，请先导入订单文件」；表有数据但当前商品无匹配时显示「暂无匹配订单数据，无法展示价格走势」

**Checkpoint**: US1、US2、US3 全部可用 — 商品详情页双图并列展示，导入和走势功能完整

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 边界处理、截断提示、集成验证

- [x] T015 [P] 在 `frontend/src/components/OrderPriceChart.vue` 中，当响应 `truncated: true` 时在图表标题或图表下方展示「数据已截断，仅显示最近 1000 条记录」提示
- [x] T016 在 `backend/routes/sub_orders.py` 中验证 `quantity=0` 的子订单可正常导入（不跳过、不报错），前端 `OrderPriceChart.vue` 中确认 `Math.max(quantity, 1)` 防零除逻辑已生效
- [x] T017 [P] 手工验证 `POST /api/sub-orders/import` 上传非 xlsx 文件返回 415，缺少 `商品ID` 列返回 422，并确认 OpenAPI 文档（`/docs`）显示两个新端点的类型注解

---

## Dependencies（Story 完成顺序）

```
T001（Setup）
  └─→ T002 T003 T004（Phase 2: Foundational）
        ├─→ T005 T006 T007 T008（US2: 导入）   ← 独立，可单独交付
        ├─→ T009 T010 T011 T012（US1: 走势图）  ← 依赖 US2 完成以提供测试数据
        └─→ T013 T014（US3: 布局）              ← 依赖 US1 的 OrderPriceChart 存在
              └─→ T015 T016 T017（Polish）
```

## Parallel Execution Examples

**US2 内部并行**（Phase 3 完成后可同步推进）:
- `T006` 前端 API 模块 ‖ `T005` 后端路由（不同文件）
- `T007` SubOrderImport 组件 ‖ `T005` 后端路由（不同文件）

**US1 内部并行**（T009 完成后）:
- `T010` 前端 API 函数 ‖ `T011` 图表组件（不同文件）

**US3 内部并行**:
- `T013` 布局调整 ‖ `T014` 空状态文案（同文件，顺序执行更安全）

**Polish 并行**:
- `T015` 截断提示 ‖ `T017` 端点验证（不同文件）

---

## Phase 7: SKU 颜色区分 + 图表类型切换（Spec 更新：FR-012 / FR-013 / FR-014）

**Goal**: 走势图散点按 SKU（`product_attr`）着色，附带图例；新增散点图/折线图切换按钮，折线图模式下各 SKU 独立连线。

**Independent Test**: 导入含 2 个以上不同 `商品属性` 值的子订单 xlsx，进入对应商品详情页，确认：① 散点图各 SKU 颜色不同；② 图例可识别每种颜色对应的 SKU；③ 点击「折线图」按钮后，各 SKU 以各自颜色连线；④ 切换时无额外网络请求；⑤ 仅 1 个数据点的 SKU 在折线图模式下显示孤立点不报错。

### Implementation

- [x] T018 [US1] 改造 `frontend/src/components/OrderPriceChart.vue`：① 新增 `chartType` ref（默认 `'scatter'`）及右上角「散点图 | 折线图」Toggle 按钮；② 新增 `SKU_COLORS` 调色板（10 色）和 `skuColorMap` computed（按 `product_attr` 首次出现顺序分配颜色）；③ **散点图模式**：将现有单一 dataset/series 改为按 SKU 分组生成多个 `ScatterSeries`，每个 series `name = SKU 值`、`itemStyle.color = skuColorMap[sku]`，趋势线 series 保留（灰色，不计入 Legend）；④ 注册 `LegendComponent`，在 `use(...)` 调用中添加；⑤ ECharts option 中加入 `legend: { type: 'scroll', bottom: 0 }` 显示 SKU 图例
- [x] T019 [US1] 在 `frontend/src/components/OrderPriceChart.vue` 中实现**折线图模式**：当 `chartType === 'line'` 时，按 SKU 分组并将各组数据点按 `created_at` 升序排列，为每组生成独立 `LineSeries`（`name = SKU 值`、`color = skuColorMap[sku]`、`showSymbol: true`、`symbolSize: 6`）；仅 1 个点的 SKU 正常渲染（ECharts 折线图单点不报错，无需特殊处理）；趋势线 series 在折线图模式下同样保留；`chartType` 切换时复用当前 `points` 数据，不重新请求接口
- [x] T020 [P] [US1] 更新 `frontend/src/components/OrderPriceChart.vue` 的 Tooltip formatter：在原有「时间 / 单件均价 / 购买数量 / 商品属性」信息前，新增与该 SKU 对应颜色的小色块（`<span>` inline-block，宽高 10px），使 Tooltip 与图例颜色一致

**Checkpoint**: 散点图和折线图模式均可用，SKU 颜色贯穿两种模式，切换流畅无请求

---

## Dependencies（完整）

```
T001（Setup）
  └─→ T002 T003 T004（Phase 2: Foundational）
        ├─→ T005 T006 T007 T008（US2: 导入）   ← 独立，可单独交付 ✅
        ├─→ T009 T010 T011 T012（US1: 走势图）  ← 依赖 US2 提供测试数据 ✅
        │     └─→ T018 T019 T020（Phase 7: SKU + Toggle）← 改造已有组件
        └─→ T013 T014（US3: 布局）              ← 依赖 US1 ✅
              └─→ T015 T016 T017（Polish）✅
```

## Implementation Strategy

**MVP 范围（仅 US2 + US1）**:
1. 完成 Phase 1 + Phase 2（Setup + Foundational）
2. 完成 Phase 3（US2 导入）— 可独立验收
3. 完成 Phase 4（US1 走势图）— 核心价值交付

US3 布局和 Polish 可在 MVP 验收后补充完成。
Phase 7（SKU 颜色 + 折线图切换）为 Phase 4 的后续增强，依赖 T011 已完成。

---

## Task Count Summary

| Phase | Tasks | Notes |
|-------|-------|-------|
| Phase 1: Setup | 1 | T001 ✅ |
| Phase 2: Foundational | 3 | T002–T004 ✅ |
| Phase 3: US2 Import (P1) | 4 | T005–T008 ✅ |
| Phase 4: US1 Trend (P1) | 4 | T009–T012 ✅ |
| Phase 5: US3 Layout (P2) | 2 | T013–T014 ✅ |
| Phase 6: Polish | 3 | T015–T017 ✅ |
| Phase 7: SKU Color + Toggle | 3 | T018–T020 🆕 |
| **Total** | **20** | |

**Parallel opportunities**: 9 tasks marked [P]（T020 可与 T019 并行）
**Independent test criteria**: Each user story phase has a standalone verification scenario
**MVP scope**: T001–T012 (Phases 1–4); Phase 7 enhances US1 chart
