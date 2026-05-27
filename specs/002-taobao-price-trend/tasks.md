# Tasks: 淘宝店铺商品价格走势平台

**Input**: [plan.md](./plan.md) | [spec.md](./spec.md) | [contracts/api.md](./contracts/api.md)

## Format: `[ID] [P?] [USn?] Description` — `📁 path/hint`
- **[P]**: 可与同 Phase 内其他 [P] 任务并行执行
- **[USn]**: 对应用户故事编号

---

## Phase 1: 依赖安装与基础配置

> 所有后续任务的先决条件，必须顺序完成。

- [x] T001 在 `backend/requirements.txt` 末尾追加 `python-multipart` 和 `httpx` — `📁 backend/requirements.txt`
- [x] T002 [P] 在 `frontend/package.json` 的 `dependencies` 中追加 `vue-router@4`、`echarts`、`vue-echarts`，然后运行 `npm install` — `📁 frontend/package.json`

---

## Phase 2: 后端数据层

> 依赖 T001。T003–T005 可并行。

- [x] T003 [P] 在 `backend/models.py` 末尾追加 `Product` 和 `PriceSnapshot` 两个 SQLModel 表类，以及 `trim_snapshots()` 辅助函数（保留最新 365 条） — `📁 backend/models.py`
- [x] T004 [P] 在 `backend/schemas.py` 末尾追加以下 Pydantic schema：`ProductRead`、`ProductListResponse`（含 `total/page/page_size/items`）、`SnapshotRead`、`AlertUpdate`、`TaobaoImportRequest`、`SnapshotTriggerRequest`、`SnapshotTriggerResponse` — `📁 backend/schemas.py`
- [x] T005 [P] 新建 `backend/taobao_client.py`：封装淘宝开放平台 TOP REST API 调用，实现 HMAC-MD5 签名工具函数、`async fetch_store_items(session_key, app_key, app_secret)`（调用 `taobao.items.onsale.get`）、`async fetch_item_price(item_id, session_key, app_key, app_secret)`（调用 `taobao.item.get`）— `📁 backend/taobao_client.py`

---

## Phase 3: 后端路由骨架注册

> 依赖 T003、T004。T006–T007 可并行，T008 必须最后。

- [x] T006 [P] 新建 `backend/routes/products.py`：创建 `router = APIRouter(prefix="/products", tags=["products"])` 骨架，暂不添加端点 — `📁 backend/routes/products.py`
- [x] T007 [P] 新建 `backend/routes/snapshots.py`：创建 `router = APIRouter(tags=["snapshots"])` 骨架，暂不添加端点 — `📁 backend/routes/snapshots.py`
- [x] T008 在 `backend/main.py` 中导入并注册 `products_router`（prefix `/api`）和 `snapshots_router`（prefix `/api`） — `📁 backend/main.py`

---

## Phase 4: 后端商品端点实现

> 依赖 T006。T009–T013 可在各自完成 T006 后并行。

- [x] T009 [P] [US1] 在 `routes/products.py` 添加 `POST /api/products/import/csv`：接收 `UploadFile`，用 `csv.DictReader` 解析，按 `item_id` upsert，返回 `{imported, updated, errors}` — `📁 backend/routes/products.py`
- [x] T010 [P] [US1] 在 `routes/products.py` 添加 `POST /api/products/import/taobao`：调用 `taobao_client.fetch_store_items()`，按 `taobao_item_id` upsert，错误时返回 401/502 — `📁 backend/routes/products.py`（依赖 T005）
- [x] T011 [P] [US2] 在 `routes/products.py` 添加 `GET /api/products`：支持 `page`、`page_size`、`q`（名称模糊搜索）、`min_price`、`max_price` 查询参数，返回 `ProductListResponse`（含 `alert_status` 计算字段） — `📁 backend/routes/products.py`
- [x] T012 [P] [US2] 在 `routes/products.py` 添加 `GET /api/products/{id}`：返回 `ProductRead`（含 `snapshot_count`），不存在时 404 — `📁 backend/routes/products.py`
- [x] T013 [P] [US6] 在 `routes/products.py` 添加 `PUT /api/products/{id}/alert`：接收 `AlertUpdate`（`alert_low`/`alert_high` 可为 null），保存后返回更新后的阈值字段 — `📁 backend/routes/products.py`
- [x] T014 [P] 在 `routes/products.py` 添加 `DELETE /api/products/{id}`：级联删除该商品的所有 `PriceSnapshot` 记录，返回 204 — `📁 backend/routes/products.py`

---

## Phase 5: 后端快照端点实现

> 依赖 T007、T005。T015–T016 可并行。

- [x] T015 [P] [US4] 在 `routes/snapshots.py` 添加 `POST /api/snapshots`：接收 `SnapshotTriggerRequest`，对每件商品串行调用 `taobao_client.fetch_item_price()`，写入 `PriceSnapshot` 并调用 `trim_snapshots()`，同时更新 `Product.current_price` 和 `last_updated`；返回 `SnapshotTriggerResponse`；用内存锁防重复触发 — `📁 backend/routes/snapshots.py`
- [x] T016 [P] [US3] 在 `routes/snapshots.py` 添加 `GET /api/products/{id}/snapshots`：返回该商品所有快照，按 `recorded_at` 升序，用于折线图；商品不存在时 404 — `📁 backend/routes/snapshots.py`

---

## Phase 6: 后端测试

> 依赖 T008–T016，T017–T018 可并行。

- [x] T017 [P] 新建 `backend/tests/test_products.py`：覆盖 CSV 导入（正常/格式错误）、列表分页、关键词搜索、价格筛选、获取单品、设置预警、删除商品 — `📁 backend/tests/test_products.py`
- [x] T018 [P] 新建 `backend/tests/test_snapshots.py`：覆盖快照触发（正常/防重入）、历史查询（正常/单条/不足记录/商品不存在） — `📁 backend/tests/test_snapshots.py`

---

## Phase 7: 前端路由配置

> 依赖 T002。

- [x] T019 修改 `frontend/src/main.js`：引入 `vue-router@4`，定义路由表：`/products`→`ProductList`、`/products/import`→`ProductImport`、`/products/:id`→`ProductDetail`，将 `createRouter` 实例挂载至 app — `📁 frontend/src/main.js`

---

## Phase 8: 前端 API 层

> 依赖 T002。T020–T021 可并行。

- [x] T020 [P] 新建 `frontend/src/api/products.js`：封装 `fetchProducts(params)`、`fetchProduct(id)`、`importCsv(file)`、`importTaobao(payload)`、`updateAlert(id, payload)`、`deleteProduct(id)` — `📁 frontend/src/api/products.js`
- [x] T021 [P] 新建 `frontend/src/api/snapshots.js`：封装 `triggerSnapshot(payload)`、`fetchSnapshots(productId)` — `📁 frontend/src/api/snapshots.js`

---

## Phase 9: 前端组件 — US1 商品导入

> 依赖 T019、T020。

- [x] T022 [US1] 新建 `frontend/src/components/ProductImport.vue`：两个 Tab（"CSV 上传" / "淘宝 Token"）；CSV Tab：文件选择器 + 上传按钮 + 字段格式提示；Token Tab：三个输入框（session_key/app_key/app_secret）+ 连接按钮；两个 Tab 成功后均跳转至 `/products` 并显示导入数量提示；失败时展示后端返回的错误信息 — `📁 frontend/src/components/ProductImport.vue`

---

## Phase 10: 前端组件 — US2+US5 商品列表

> 依赖 T019、T020、T021。

- [x] T023 [US2] [US5] 新建 `frontend/src/components/ProductList.vue`：表格展示（名称、当前价格、最近更新、预警标识）；顶部工具栏含搜索框（关键词）、价格区间筛选（最低/最高）、"筛选"按钮、"清除筛选"按钮；分页控件（上一页/下一页/总数显示）；"记录快照"按钮（点击后进入 loading 态，完成后显示结果 toast）；空状态提示；行点击导航至 `/products/:id` — `📁 frontend/src/components/ProductList.vue`

---

## Phase 11: 前端组件 — US3+US6 商品详情与走势图

> 依赖 T019、T020、T021。T024–T025 可并行。

- [x] T024 [P] [US3] 新建 `frontend/src/components/PriceChart.vue`：接收 props `snapshots: Array`（含 `price`、`recorded_at`）、`alertLow: Number|null`、`alertHigh: Number|null`；用 `vue-echarts` 渲染折线图，X 轴为时间、Y 轴为价格（元）；添加 Tooltip 显示精确价格和时间；当 `alertLow`/`alertHigh` 非空时在图中绘制水平参考线；`snapshots.length < 2` 时显示提示文案而非图表 — `📁 frontend/src/components/PriceChart.vue`
- [x] T025 [P] [US3] [US6] 新建 `frontend/src/components/ProductDetail.vue`：显示商品名称、淘宝 ID、商品 URL 链接、当前价格；加载并传入快照数据给 `PriceChart`；底部设置预警阈值表单（下限/上限输入框 + 保存/清除按钮，调用 `updateAlert`）；返回按钮导航至 `/products` — `📁 frontend/src/components/ProductDetail.vue`

---

## Phase 12: 前端 App 集成收尾

> 依赖 T019、T022–T025。

- [x] T026 更新 `frontend/src/App.vue`：添加顶部导航栏（"商品列表" 链接 → `/products`，"导入商品" 链接 → `/products/import`）；挂载 `<router-view />`；移除不再需要的 HelloWorld 演示内容 — `📁 frontend/src/App.vue`
- [x] T027 [P] 为 `ProductImport.vue`、`ProductList.vue`、`ProductDetail.vue` 统一添加 API 错误 banner（红色提示条，显示后端 `detail` 信息，可手动关闭） — `📁 frontend/src/components/Product*.vue`
- [x] T028 [P] 在 `ProductList.vue` 的"记录快照"按钮旁添加进度提示（显示"正在更新 N 件商品，请稍候…"），并在快照完成后自动刷新列表数据 — `📁 frontend/src/components/ProductList.vue`
