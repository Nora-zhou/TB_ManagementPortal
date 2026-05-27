# Tasks: 多店铺数据区分与统计

**Feature**: `008-multi-store` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Organization**: 任务按 User Story 分组，支持独立实现与测试。

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: 可并行执行（不同文件，无未完成依赖）
- **[Story]**: 所属 User Story（US1 / US2 / US3）
- 每个任务包含精确文件路径

---

## Phase 1: Setup（数据模型基础——阻塞所有后续任务）

**Purpose**: 在五个模型类中新增 `store` 字段并配置数据库迁移——这是整个功能的绝对基础，必须最先完成

- [X] T001 在 `backend/models.py` 中为以下五个模型类各追加 `store: int = Field(default=1)  # 1=店铺1, 2=店铺2` 字段：`Order`（`imported_at` 字段之后）、`SubOrder`（`imported_at` 之后）、`PurchaseOrder`（`imported_at` 之后）、`Product`（`created_at` 之后）、`PriceSnapshot`（`recorded_at` 之后）；确认每个类中 `Field` 已从 `sqlmodel` 导入
- [X] T002 在 `backend/database.py` 的 `create_db_and_tables()` 函数中，紧接 `SQLModel.metadata.create_all(engine)` 之后追加幂等迁移块：循环 `("order", "suborder", "purchaseorder", "product", "pricesnapshot")`，对每张表执行 `conn.execute(text(f"ALTER TABLE {table} ADD COLUMN store INTEGER DEFAULT 1"))`，在 `try` 块内 `conn.commit()`，`except Exception: pass`（列已存在时静默跳过）；在文件顶部 `from sqlalchemy import text`（若未导入则补充）

**Checkpoint**: 重启后端服务无报错；`python -c "from models import Order; print(Order.model_fields['store'])"` 输出字段信息；在 SQLite 客户端执行 `SELECT store, count(*) FROM "order" GROUP BY store` 确认历史数据 `store=1`

---

## Phase 2: Foundational（Schema 字段——阻塞所有接口任务）

**Purpose**: 补充响应 Schema 的 `store` 字段，使列表响应正确携带店铺信息——所有路由任务的前置依赖

**⚠️ 关键**: 此阶段完成后，Phase 3–5 的接口任务方可并行推进

- [X] T003 在 `backend/schemas.py` 中为 `OrderRead` 类追加 `store: int = 1` 字段（使 `GET /api/orders` 响应中每条订单包含店铺字段）；为 `PurchaseOrderDetail` 类追加 `store: int = 1` 字段（使采购订单列表响应包含店铺字段）；Import Result schema（`OrderImportResult`、`SubOrderImportResult`、`PurchaseOrderImportResult`）无需修改（`store` 为输入参数而非输出字段）

**Checkpoint**: `python -c "from schemas import OrderRead; print(OrderRead.model_fields.get('store'))"` 输出非 None

---

## Phase 3: User Story 1 — 导入时选择店铺（Priority: P1）🎯 MVP

**Goal**: 所有导入入口均新增店铺选择控件（必填），导入后的记录被正确打上 `store` 标签；未选择店铺时前端拒绝提交并提示；重复导入同一文件以不同店铺会更新 `store` 字段（upsert 覆盖）

**Independent Test**: 在「基础数据导入」页面选择「店铺2」后上传淘宝子订单文件，导入成功后通过 `GET /api/orders?store=2` 确认本次导入订单 `store=2`；再不选择店铺直接点导入按钮，确认前端显示「请选择店铺」且不发起请求；通过 `POST /api/sub-orders/import` 不传 `store` 参数，确认返回 HTTP 422

### 后端接口变更（可并行，不同文件）

- [X] T004 [P] [US1] 在 `backend/routes/sub_orders.py` 中为 `POST /api/sub-orders/import` 端点新增 `store: int = Form(...)` 参数（在 `file: UploadFile` 参数之后）；在函数体首行添加校验 `if store not in (1, 2): raise HTTPException(status_code=422, detail="store 必须为 1 或 2")`；在 upsert `values` 字典中追加 `"store": store`（确保 update 分支也通过 `setattr` 或 values 覆盖 store）；在 `from fastapi import` 语句中补充 `Form`（若未导入）
- [X] T005 [P] [US1] 在 `backend/routes/orders.py` 中为 `POST /api/orders/import` 端点新增 `store: int = Form(...)` 参数；在函数体首行添加校验 `if store not in (1, 2): raise HTTPException(status_code=422, detail="store 必须为 1 或 2")`；在 upsert `values` 字典中追加 `"store": store`；在 `if existing:` update 分支中确认 `store` 通过 `setattr(existing, k, v)` 遍历被覆盖（实现 upsert 更新 store）；在 `from fastapi import` 中补充 `Form`（若未导入）
- [X] T006 [P] [US1] 在 `backend/routes/purchase_orders.py` 中为 `POST /api/purchase-orders/import` 端点新增 `store: int = Form(...)` 参数；在函数体首行添加校验 `if store not in (1, 2): raise HTTPException(status_code=422, detail="store 必须为 1 或 2")`；在 upsert `values` 字典中追加 `"store": store`；在 `from fastapi import` 中补充 `Form`（若未导入）
- [X] T007 [P] [US1] 在 `backend/routes/products.py` 中检查商品导入/目录扫描端点的签名；若该端点接受文件或触发写入 Product 记录，则新增 `store: int = Form(...)` 参数（或 `Query` 参数，依端点类型而定）、添加 `store not in (1, 2)` 校验、将 `store` 写入 Product upsert 的 `values` 字典；若端点不写入 Product 记录则跳过后端修改并记录原因

### 前端 API 层变更（可并行，不同文件）

- [X] T008 [P] [US1] 在 `frontend/src/api/orders.js` 中修改 `importOrders`（或对应导入函数）：新增 `store` 形参，在构建 `FormData` 时追加 `form.append('store', String(store))`；保持函数其余逻辑不变
- [X] T009 [P] [US1] 在 `frontend/src/api/sub_orders.js` 中修改子订单导入函数（`importSubOrders` 或对应函数）：新增 `store` 形参，在 `FormData` 中追加 `form.append('store', String(store))`
- [X] T010 [P] [US1] 在 `frontend/src/api/purchase_orders.js` 中修改采购订单导入函数（`importPurchaseOrders` 或对应函数）：新增 `store` 形参，在 `FormData` 中追加 `form.append('store', String(store))`
- [X] T011 [P] [US1] 在 `frontend/src/api/products.js` 中修改商品导入/目录扫描函数：新增 `store` 形参，在请求参数（FormData 或 query string）中传递 `store`（与 T007 后端修改对应）

### 前端组件变更

- [X] T012 [US1] 在 `frontend/src/components/DataImport.vue` 中新增统一店铺选择控件：在 `<script setup>` 中声明 `const selectedStore = ref(1)`；在模板中，当 `activeTab` 为订单信息相关 tab 时（在 Tab bar 上方）显示 radio 组（`<input type="radio" :value="1" v-model="selectedStore" /> 店铺1`、`<input type="radio" :value="2" v-model="selectedStore" /> 店铺2`）；将 `:store="selectedStore"` prop 传给 `<SubOrderImport>` 与 `<OrderImport>` 子组件（若两者均在此组件中使用）；在 `<style scoped>` 中添加 `.store-selector { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }` 及 `.store-selector label { display: flex; align-items: center; gap: 4px; cursor: pointer; font-size: 13px; }`
- [X] T013 [P] [US1] 在 `frontend/src/components/SubOrderImport.vue` 中接收 store prop：在 `<script setup>` 中添加 `const props = defineProps({ store: { type: Number, default: 1 } })`；在导入提交函数中将 `props.store` 传入 `importSubOrders(file, props.store)`；移除组件内已存在的独立店铺选择控件（若有）
- [X] T014 [P] [US1] 在 `frontend/src/components/OrderImport.vue` 中接收 store prop：在 `<script setup>` 中添加 `const props = defineProps({ store: { type: Number, default: 1 } })`；在订单导入提交函数中将 `props.store` 传入 orders 导入 API 调用；确认 `DataImport.vue` 已向此组件传入 `:store="selectedStore"`（与 SubOrderImport 共享同一值）
- [X] T015 [US1] 在 `frontend/src/components/PurchaseOrderImport.vue` 中新增独立店铺选择控件：在 `<script setup>` 中声明 `const selectedStore = ref(null)` 与 `const storeError = ref('')`；实现 `validateStore()` 函数（`!selectedStore.value` 时设 `storeError.value = '请选择店铺'` 返回 false，否则清空错误返回 true）；在提交处理函数顶部调用 `if (!validateStore()) return`；将 `selectedStore.value` 传入 `importPurchaseOrders(file, selectedStore.value)`；在文件导入区域上方添加模板：radio 组（店铺1 / 店铺2）+ `<span v-if="storeError" class="error-text">{{ storeError }}</span>`；添加 `.store-selector` 与 `.error-text { color: #f56c6c; font-size: 12px; }` scoped 样式
- [X] T016 [P] [US1] 在 `frontend/src/components/ProductImport.vue` 中新增独立店铺选择控件：与 T015（`PurchaseOrderImport.vue`）完全相同的实现模式（`selectedStore` ref + `storeError` ref + `validateStore` 函数 + 提交前校验 + radio 模板 + scoped 样式）；在商品导入 API 调用中将 `selectedStore.value` 作为 `store` 参数传入

**Checkpoint**: US1 独立可用 — 淘宝订单导入页面店铺 radio 可见且默认选中「店铺1」；选「店铺2」上传文件后 `GET /api/orders?store=2` 返回有数据；采购订单导入页面不选店铺点提交显示「请选择店铺」且不发起网络请求；`POST /api/sub-orders/import` 缺少 `store` 字段返回 HTTP 422

---

## Phase 4: User Story 2 — 订单分析仪表盘按店铺过滤（Priority: P1）🎯 MVP

**Goal**: 订单分析仪表盘顶部新增「全部 / 店铺1 / 店铺2」三态切换；切换后所有 KPI 卡片与图表数据即时更新；`OrderList.vue` 新增「店铺」列显示每条订单归属；月份筛选与店铺筛选独立并行（AND 逻辑）

**Independent Test**: 打开订单分析仪表盘，确认顶部有三个切换按钮；点击「店铺1」确认 KPI 数值变化；再切换月份确认两个筛选同时生效（AND）；打开订单列表确认每行显示「店铺1」或「店铺2」；刷新页面确认店铺筛选重置为「全部」（session 范围）

### 后端接口变更

- [X] T017 [US2] 在 `backend/routes/orders.py` 中为以下五个端点各新增 `store: Optional[int] = Query(default=None)` 参数，并在 query 构建处追加 `if store is not None: stmt = stmt.where(Order.store == store)`：`GET /api/orders`（同时对 `count_stmt` 追加相同过滤）、`GET /api/orders/stats/summary`、`GET /api/orders/stats/trend`、`GET /api/orders/stats/status-dist`、`GET /api/orders/stats/top-products`；在文件顶部确认 `Optional` 已从 `typing` 导入（或已有 `Optional` 用法）
- [X] T018 [US2] 在 `backend/routes/orders.py` 中为 `POST /api/orders/sync-from-sub-orders` 端点补充 store 传播逻辑：在聚合每组 SubOrder 数据时，读取 `items[0].store` 作为 `store_val`；将 `"store": store_val` 加入 upsert `values` 字典，使聚合生成的 Order 记录继承其 SubOrder 的店铺归属

### 前端 API 层变更

- [X] T019 [US2] 在 `frontend/src/api/orders.js` 中为 `getOrders`、`getOrderSummary`、`getOrderTrend`、`getStatusDist`、`getTopProducts`（或对应函数）各新增 store 传参逻辑：在 `URLSearchParams` 构建处追加 `if (params.store != null) query.set('store', params.store)`（或等价写法）

### 前端组件变更

- [X] T020 [P] [US2] 在 `frontend/src/components/OrderList.vue` 的订单表格中新增「店铺」列：在 `<thead>` 适当位置添加 `<th>店铺</th>`；在 `<tbody>` 对应数据行添加 `<td>店铺{{ order.store ?? 1 }}</td>`（`?? 1` 兼容迁移前 store 为 null 的历史行）
- [X] T021 [P] [US2] 在 `frontend/src/components/OrderDashboard.vue` 中新增店铺筛选：在 `<script setup>` 中声明 `const storeFilter = ref(null)`（null = 全部）；实现 `setStore(val)` 函数（更新 `storeFilter.value` 并调用现有数据加载函数）；实现 `storeParams()` 辅助函数（`storeFilter.value != null ? { store: storeFilter.value } : {}`）；将 `...storeParams()` 合并进所有现有 API 调用的参数对象（`getOrderSummary`、`getOrderTrend`、`getStatusDist`、`getTopProducts` 等）；在模板顶部筛选工具栏（现有月份筛选之后）新增店铺按钮组：三个 `<button>`（「全部」/ 「店铺1」/ 「店铺2」），`:class="{ active: storeFilter === null/1/2 }"`，`@click="setStore(null/1/2)"`；在 `<style scoped>` 中添加 `.store-filter { display: inline-flex; gap: 4px; }` 与 `.store-filter button { padding: 4px 12px; border: 1px solid #ddd; background: transparent; border-radius: 4px; cursor: pointer; font-size: 13px; }` 与 `.store-filter button.active { background: #000; color: #fff; border-color: #000; }`

**Checkpoint**: US2 独立可用 — 仪表盘切换「店铺1」后 KPI 卡片数值变化；同时选择月份确认 AND 过滤生效；刷新页面店铺恢复「全部」；`OrderList` 表格「店铺」列正常显示且历史数据显示「店铺1」

---

## Phase 5: User Story 3 — 供应商页面按店铺过滤（Priority: P2）

**Goal**: 供应商管理列表与供应商采购仪表盘各新增「全部 / 店铺1 / 店铺2」筛选，与现有月份筛选独立并行（AND 逻辑）

**Independent Test**: 打开供应商管理页，确认顶部有店铺切换按钮；点击「店铺1」确认供应商汇总只含店铺1采购记录；打开供应商仪表盘，切换店铺确认三张图表随之更新；月份与店铺筛选同时生效（AND）；刷新页面店铺重置为「全部」

### 后端接口变更

- [X] T022 [US3] 在 `backend/routes/purchase_orders.py` 中为 `GET /api/purchase-orders/summary` 端点新增 `store: Optional[int] = Query(default=None)` 参数；在 `base_filters` 列表构建处，当 `store is not None` 时追加 `PurchaseOrder.store == store` 条件；确认 `Optional` 已导入
- [X] T023 [P] [US3] 在 `backend/routes/purchase_orders.py` 中为 `GET /api/purchase-orders/dashboard` 端点新增 `store: Optional[int] = Query(default=None)` 参数；在 `base_filters` 列表构建处，当 `store is not None` 时追加 `PurchaseOrder.store == store` 条件

### 前端 API 层变更

- [X] T024 [P] [US3] 在 `frontend/src/api/purchase_orders.js` 中为 `fetchSupplierDashboard` 函数新增 `store` 参数支持：在函数参数解构中追加 `store`，当 `store != null` 时 `p.append('store', String(store))`；同样更新 `fetchSupplierSummary`（或对应汇总函数）：接收 `store` 参数并在 query 中传递

### 前端组件变更

- [X] T025 [P] [US3] 在 `frontend/src/components/SupplierManagement.vue` 中新增店铺筛选：在 `<script setup>` 中声明 `const storeFilter = ref(null)`；实现 `setStore(val)` 函数（更新值并调用现有数据加载函数）；在供应商汇总 API 调用（`fetchSupplierSummary` 或等效函数）中传入 `store: storeFilter.value`；在模板工具栏（现有月份筛选并排）添加三态店铺按钮组（与 `OrderDashboard.vue` 相同的 HTML 结构与 CSS 类名）；在 `<style scoped>` 中添加 `.store-filter` 及 `.store-filter button.active` 样式（黑底白字）
- [X] T026 [P] [US3] 在 `frontend/src/components/SupplierDashboard.vue` 中新增店铺筛选：在 `<script setup>` 中声明 `const storeFilter = ref(null)`；在 `loadDashboard()` 函数的参数对象中，当 `storeFilter.value != null` 时传入 `store: storeFilter.value` 给 `fetchSupplierDashboard`；切换店铺触发 `loadDashboard()` 重新加载；在模板月份筛选行之后添加三态店铺按钮组；在 `<style scoped>` 中添加 `.store-filter` 及 `.store-filter button.active` 样式

**Checkpoint**: US3 完成 — 供应商管理页切换「店铺2」后汇总金额发生变化；供应商仪表盘切换店铺后三张图表随之更新；月份与店铺筛选同时生效（AND 逻辑）

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 构建验证与端到端冒烟测试

- [X] T027 [P] 在 `frontend/` 目录执行 `npm run build`，确认零编译错误；手动验证以下场景：①`GET /api/orders?store=1` 返回 HTTP 200，每条订单含 `"store": 1`；②`GET /api/orders/stats/summary?store=2` 返回 HTTP 200；③`GET /api/purchase-orders/dashboard?store=1` 返回 HTTP 200；④`POST /api/orders/import` 不传 `store` 返回 HTTP 422；⑤`POST /api/sub-orders/import` 不传 `store` 返回 HTTP 422；⑥重启后端服务后 `SELECT store, count(*) FROM "order" GROUP BY store` 历史数据均为 `store=1`

---

## Dependencies（Story 完成顺序）

```
T001 T002（Phase 1: 模型 + 迁移）
  └─► T003（Phase 2: Schema 字段）
        ├─► T004 T005 T006 T007（US1 后端导入接口，可并行）
        │     └─► T008 T009 T010 T011（US1 前端 API 层，可并行）
        │           └─► T012（DataImport.vue 统一 store 控件）
        │                 ├─► T013 T014（SubOrderImport / OrderImport prop，可并行）
        │                 └─► T015 T016（PurchaseOrderImport / ProductImport，可并行）
        ├─► T017 T018（US2 后端过滤，T018 依赖 T017 同文件）
        │     └─► T019（US2 前端 API）
        │           ├─► T020（OrderList 店铺列）
        │           └─► T021（OrderDashboard 店铺筛选）
        └─► T022 T023（US3 后端过滤，可并行不同端点）
              └─► T024（US3 前端 API）
                    ├─► T025（SupplierManagement 店铺筛选）
                    └─► T026（SupplierDashboard 店铺筛选）
                          └─► T027（Polish）
```

## Parallel Execution Examples

**Phase 1 内部**（顺序执行）:
- `T001`（models.py）→ `T002`（database.py）（T002 在 T001 确认模型字段后添加迁移）

**Phase 3 后端并行**（T003 完成后）:
- `T004`（sub_orders.py）‖ `T005`（orders.py 导入段）‖ `T006`（purchase_orders.py 导入段）‖ `T007`（products.py）—— 不同文件，相互独立

**Phase 3 前端 API 并行**（T005 等完成后）:
- `T008`（api/orders.js）‖ `T009`（api/sub_orders.js）‖ `T010`（api/purchase_orders.js）‖ `T011`（api/products.js）—— 不同文件

**Phase 3 组件并行**（T012 完成后）:
- `T013`（SubOrderImport.vue）‖ `T014`（OrderImport.vue）—— 不同文件
- `T015`（PurchaseOrderImport.vue）‖ `T016`（ProductImport.vue）—— 不同文件

**Phase 4 组件并行**（T019 完成后）:
- `T020`（OrderList.vue）‖ `T021`（OrderDashboard.vue）—— 不同文件

**Phase 5 并行**（T003 完成后可与 Phase 3/4 并行推进）:
- `T022`（summary 端点）→ `T023`（dashboard 端点）—— 同文件顺序更安全
- `T025`（SupplierManagement.vue）‖ `T026`（SupplierDashboard.vue）—— 不同文件

---

## Implementation Strategy

**MVP 范围**（Phase 1–4，T001–T021）: 后端模型迁移 + 所有导入入口店铺选择 + 订单分析仪表盘店铺过滤 + 订单列表店铺列 — 覆盖 US1 与 US2 全部验收场景，可独立交付

**完整交付**（Phase 5，T022–T026）: 追加供应商管理列表与供应商仪表盘的店铺过滤，覆盖 US3

**文件变更汇总**:

| 文件 | 操作 | 任务 |
|------|------|------|
| `backend/models.py` | Edit | T001 |
| `backend/database.py` | Edit | T002 |
| `backend/schemas.py` | Edit | T003 |
| `backend/routes/sub_orders.py` | Edit | T004 |
| `backend/routes/orders.py` | Edit | T005, T017, T018 |
| `backend/routes/purchase_orders.py` | Edit | T006, T022, T023 |
| `backend/routes/products.py` | Edit | T007 |
| `frontend/src/api/orders.js` | Edit | T008, T019 |
| `frontend/src/api/sub_orders.js` | Edit | T009 |
| `frontend/src/api/purchase_orders.js` | Edit | T010, T024 |
| `frontend/src/api/products.js` | Edit | T011 |
| `frontend/src/components/DataImport.vue` | Edit | T012 |
| `frontend/src/components/SubOrderImport.vue` | Edit | T013 |
| `frontend/src/components/OrderImport.vue` | Edit | T014 |
| `frontend/src/components/PurchaseOrderImport.vue` | Edit | T015 |
| `frontend/src/components/ProductImport.vue` | Edit | T016 |
| `frontend/src/components/OrderList.vue` | Edit | T020 |
| `frontend/src/components/OrderDashboard.vue` | Edit | T021 |
| `frontend/src/components/SupplierManagement.vue` | Edit | T025 |
| `frontend/src/components/SupplierDashboard.vue` | Edit | T026 |
