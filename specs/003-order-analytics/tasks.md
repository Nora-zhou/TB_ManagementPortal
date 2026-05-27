# Tasks: 订单数据分析平台

**Input**: [plan.md](./plan.md) | [spec.md](./spec.md) | [contracts/api.md](./contracts/api.md)

## Format: `[ID] [P?] [USn?] Description` �?`📁 path/hint`
- **[P]**: 可与�?Phase 内其�?[P] 任务并行执行
- **[USn]**: 对应用户故事编号

---

## Phase 1: 依赖安装

> 所有后续任务的先决条件�?

- [x] T001 �?`backend/requirements.txt` 末尾追加 `openpyxl` �?`📁 backend/requirements.txt`

---

## Phase 2: 后端数据�?

> 依赖 T001。T002–T003 可并行�?

- [x] T002 [P] �?`backend/models.py` 末尾追加 `Order` SQLModel 表类，字段：`id`（PK）、`order_id`（UNIQUE TEXT）、`payment_id`、`payment_detail`、`total_amount`（REAL）、`buyer_paid`（REAL）、`status`、`created_at`（DATETIME）、`product_title`、`seller_fee`（REAL）、`refund_amount`（REAL）、`imported_at`（DATETIME，server_default=now）�?`📁 backend/models.py`
- [x] T003 [P] �?`backend/schemas.py` 末尾追加以下 schema：`OrderRead`（含所有字段）、`OrderListResponse`（含 `total/page/page_size/items`）、`ImportResult`（`imported/updated/skipped/errors`）、`ImportProgress`（`status/processed/total/percent`）、`SummaryStats`、`TrendResponse`（`granularity/labels/revenue/refund/order_count`）、`StatusDistItem`、`TopProductItem`、`TopProductsResponse` �?`📁 backend/schemas.py`

---

## Phase 3: 后端路由骨架注册

> 依赖 T002、T003�?

- [x] T004 新建 `backend/routes/orders.py`：创�?`router = APIRouter(prefix="/orders", tags=["orders"])` 骨架，声明模块级 `_import_progress: dict` 用于进度跟踪，暂不添加端�?�?`📁 backend/routes/orders.py`
- [x] T005 �?`backend/main.py` 中导入并注册 `orders_router`（prefix `/api`�?�?`📁 backend/main.py`

---

## Phase 4: 后端导入端点实现

> 依赖 T004�?

- [x] T006 [US1] �?`routes/orders.py` 实现 `POST /api/orders/import`：接�?`UploadFile`，校验扩展名�?`.xlsx`；用 `openpyxl` 读取第一�?Sheet，校验必填列存在；按行解析，转换字段类型（金�?str→float，时�?str→datetime）；�?`order_id` upsert（存在则更新，不存在则插入）；返�?`ImportResult`。行解析异常跳过并记�?`errors` 列表 �?`📁 backend/routes/orders.py`
- [x] T007 [US1] �?`routes/orders.py` 实现 `GET /api/orders/import/progress`：返�?`_import_progress` 当前状态（`idle` �?`running` �?`processed/total/percent`�?�?`📁 backend/routes/orders.py`

---

## Phase 5: 后端订单列表端点

> 依赖 T004�?

- [x] T008 [US2] �?`routes/orders.py` 实现 `GET /api/orders`：支�?`page`、`page_size`、`status`（精确）、`q`（标�?LIKE）、`start_date`、`end_date`（按 `created_at` 过滤）、`sort_by`（`created_at`/`buyer_paid`/`refund_amount`）、`sort_dir`（`asc`/`desc`）；返回 `OrderListResponse` �?`📁 backend/routes/orders.py`

---

## Phase 6: 后端统计端点实现

> 依赖 T004。T009–T012 可并行�?

- [x] T009 [P] [US3,US5] �?`routes/orders.py` 实现 `GET /api/orders/stats/summary`：支�?`start_date`/`end_date` 过滤；统�?`total_orders`、`success_orders`、`total_revenue`（仅「交易成功」`buyer_paid` 之和）、`total_refund`（所有订�?`refund_amount` 之和）、`refund_rate`、`avg_order_value`、`date_range`；返�?`SummaryStats` �?`📁 backend/routes/orders.py`
- [x] T010 [P] [US3,US5] �?`routes/orders.py` 实现 `GET /api/orders/stats/trend`：支�?`granularity`（`day`/`week`/`month`）和日期过滤；用 SQLite `strftime` 分组，计算每组的「交易成功」`buyer_paid` 之和、`refund_amount` 之和、订单数；返�?`TrendResponse` �?`📁 backend/routes/orders.py`
- [x] T011 [P] [US4] �?`routes/orders.py` 实现 `GET /api/orders/stats/status`：按 `status` 分组统计数量，计算各状态占比（保留两位小数）；返回 `StatusDistItem` 列表 �?`📁 backend/routes/orders.py`
- [x] T012 [P] [US6] �?`routes/orders.py` 实现 `GET /api/orders/stats/top-products`：仅统计「交易成功」订单；在应用层�?`product_title` 按逗号分割，Python 聚合各子标题�?`buyer_paid` 之和与订单数；按 `sort_by`（`revenue`/`count`）降序取�?`limit` 条；返回 `TopProductsResponse` �?`📁 backend/routes/orders.py`

---

## Phase 7: 后端测试

> 依赖 T006–T012。T013–T014 可并行�?

- [x] T013 [P] 新建 `backend/tests/test_orders.py`：覆�?xlsx 导入（正�?重复导入/缺失�?�?xlsx 格式）、列表分页、状态筛选、关键词搜索、日期范围筛�?�?`📁 backend/tests/test_orders.py`
- [x] T014 [P] �?`test_orders.py` 中追加统计接口测试：summary 数字正确性、trend �?granularity 返回正确标签数、status 分布占比之和�?100%、top-products 返回排序正确 �?`📁 backend/tests/test_orders.py`

---

## Phase 8: 前端 API �?

> 依赖 Phase 4�? 完成�?

- [x] T015 新建 `frontend/src/api/orders.js`：封装以下函数：`importOrders(file)`（POST multipart）、`pollImportProgress()`（GET progress）、`getOrders(params)`、`getOrderSummary(params)`、`getOrderTrend(params)`、`getStatusDist()`、`getTopProducts(params)` �?`📁 frontend/src/api/orders.js`

---

## Phase 9: 前端路由配置

> 依赖 T015�?

- [x] T016 �?`frontend/src/main.js` 路由表中追加三条路由：`/orders/import`→`OrderImport`、`/orders`→`OrderList`、`/orders/dashboard`→`OrderDashboard` �?`📁 frontend/src/main.js`
- [x] T017 �?`frontend/src/App.vue` 导航栏中追加「订单分析」入口链接（指向 `/orders/dashboard`�?�?`📁 frontend/src/App.vue`

---

## Phase 10: 前端组件实现

> 依赖 T015–T016。T018–T020 可并行�?

- [x] T018 [P] [US1] 新建 `frontend/src/components/OrderImport.vue`：拖�?点击上传 xlsx 文件；调�?`importOrders()`；大文件�?500 行估算时）轮�?`pollImportProgress()` 显示进度条（�?500ms 一次）；导入完成后显示 `ImportResult`（imported/updated/skipped/errors 数量）并提供「查看订单列表」按�?�?`📁 frontend/src/components/OrderImport.vue`
- [x] T019 [P] [US2] 新建 `frontend/src/components/OrderList.vue`：顶部筛选栏（状态下拉、关键词输入 300ms 防抖、日期范围选择器、排序选择）；调用 `getOrders()` 分页展示；表格列：订单编号（截断 10 位）、商品标题（截断 40 字）、实付金额、状态（不同状态对应不同颜色标签）、创建时间；分页控件 �?`📁 frontend/src/components/OrderList.vue`
- [x] T020 [P] [US3,US4,US5,US6] 新建 `frontend/src/components/OrderDashboard.vue`�?
  - 顶部 4 个数字卡片：总销售额、退款额、退款率、平均客单价（数据来�?`getOrderSummary()`�?
  - 销�?退款走势折线图：双折线（收�?+ 退款），支�?day/week/month 维度切换（ECharts，数据来�?`getOrderTrend()`�?
  - 订单状态分布饼图（ECharts，数据来�?`getStatusDist()`，点击状态片段跳转至 OrderList 对应筛选）
  - 热销商品排行表格：支持「收入�?「订单数」维度切换，显示排名、商品标题（截断 30 字）、订单数、总销售额（数据来�?`getTopProducts()`�?
  �?`📁 frontend/src/components/OrderDashboard.vue`
