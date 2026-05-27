# Tasks: UX 功能增强

**Input**: [plan.md](./plan.md) | [spec.md](./spec.md)

## Format: `[ID] [P?] [USn?] Description` → `📁 path/hint`
- **[P]**: 可与同 Phase 内其他 [P] 任务并行执行
- **[USn]**: 对应用户故事编号

---

## Phase 1: 后端 — status 端点补全日期过滤

> Story 1 的后端唯一变更点。独立可先行。

- [x] T001 [US1] 在 `routes/orders.py` 的 `order_status_dist()` 函数签名中新增 `start_date: Optional[str] = Query(default=None)` 和 `end_date: Optional[str] = Query(default=None)` 参数，复用已有 `_apply_date_filter` 模式（参照 `order_summary()` 实现），将日期过滤应用至分组查询的 `stmt` → `📁 backend/routes/orders.py`

---

## Phase 2: 后端 — Goods 目录导入端点

> Story 2 的后端实现。T002–T003 可并行。

- [x] T002 [P] [US2] 在 `backend/schemas.py` 末尾追加 `GoodsDirImportResponse` schema：字段 `imported: int`、`updated: int`、`errors: list[dict]`（每项含 `file: str` 和 `reason: str`）→ `📁 backend/schemas.py`
- [x] T003 [P] [US2] 在 `routes/products.py` 顶部导入 `pathlib.Path`，定义模块级常量 `GOODS_DIR = Path(__file__).parent.parent / "data" / "Goods"`；新增 `POST /import/from-goods-dir` 端点，逻辑：① 若 `GOODS_DIR` 不存在或无 CSV 文件，返回 `{imported:0, updated:0, errors:[{file:"", reason:"Goods 目录下未找到 CSV 文件"}]}`；② 遍历所有 `*.csv`，逐文件用 `csv.DictReader` 解析，校验 `item_id` 列存在，否则记录 error 跳过；③ 对每条合法行执行 upsert（`item_id` 不存在 → 插入 → `imported++`，存在 → 更新 `name`/`price`/`url` → `updated++`）；④ 返回 `GoodsDirImportResponse` → `📁 backend/routes/products.py`

---

## Phase 3: 后端测试

> 依赖 T001、T003。T004–T005 可并行。

- [x] T004 [P] [US1] 在 `backend/tests/test_orders.py` 末尾追加 `test_status_dist_date_filter`：导入跨月订单，分别请求 `?start_date=X&end_date=Y` 验证返回的状态分布只包含该时段内订单；验证无该时段数据时返回空列表 → `📁 backend/tests/test_orders.py`
- [x] T005 [P] [US2] 新建 `backend/tests/test_products_goods_dir.py`：用 `tmp_path` fixture 临时构造 CSV 文件并 monkeypatch `GOODS_DIR`；覆盖：① 首次导入5条 → `{imported:5, updated:0}`；② 再次导入（文件不变）→ `{imported:0, updated:5}`；③ 追加含3条新+2条旧ID（价格不同）→ `{imported:3, updated:2}`；④ 目录为空 → error 提示；⑤ CSV 缺少 `item_id` 列 → 跳过并记录 errors → `📁 backend/tests/test_products_goods_dir.py`

---

## Phase 4: 前端 — products API 扩展

> 依赖 T003 完成（或与 T003 并行，前端先写调用桩）。

- [x] T006 [US2] 在 `frontend/src/api/products.js` 末尾追加 `importFromGoodsDir()` 函数：调用 `POST /api/products/import/from-goods-dir`（无请求体），返回响应 JSON → `📁 frontend/src/api/products.js`

---

## Phase 5: 前端 — ProductImport.vue 改造

> 依赖 T006。

- [x] T007 [US2] 改造 `frontend/src/components/ProductImport.vue`：① 移除 `<input type="file">` 文件上传控件及相关 `handleFile` / `uploadCsv` 逻辑；② 新增「从 Goods 目录导入」按钮，点击调用 `importFromGoodsDir()`；③ 请求中显示 loading 状态；④ 完成后展示结果摘要（`imported X 条 / updated Y 条`），若 `errors` 非空以折叠列表显示文件名与原因 → `📁 frontend/src/components/ProductImport.vue`

---

## Phase 6: 前端 — DataImport.vue 新增与路由调整

> 依赖 T007。T008–T010 可并行。

- [x] T008 [P] [US3] 新建 `frontend/src/components/DataImport.vue`：持有 `activeTab` ref（默认 `'product'`）；渲染两个 Tab 按钮（「商品导入」/「订单导入」），选中项高亮；用 `v-if` 条件渲染 `<ProductImport />` 和 `<OrderImport />`；Tab 切换不重置子组件状态（使用 `v-show` 可选）→ `📁 frontend/src/components/DataImport.vue`
- [x] T009 [P] [US3] 修改 `frontend/src/main.js`：① 删除路由 `{ path: '/products/import', component: ProductImport }` 和 `{ path: '/orders/import', component: OrderImport }`；② 新增路由 `{ path: '/import', component: DataImport }`；③ 引入 `DataImport` 组件 → `📁 frontend/src/main.js`
- [x] T010 [P] [US3] 修改 `frontend/src/App.vue` 导航栏：① 删除 `<RouterLink to="/products/import">导入商品</RouterLink>` 和 `<RouterLink to="/orders/import">导入订单</RouterLink>`；② 在「商品价格走势」链接后新增 `<RouterLink to="/import">基础数据导入</RouterLink>` → `📁 frontend/src/App.vue`

---

## Phase 7: 前端 — OrderDashboard.vue 时间筛选

> 依赖 T001（后端 status 端点）。T011 为单一组件改造任务。

- [x] T011 [US1] 改造 `frontend/src/components/OrderDashboard.vue`：
  1. 新增时间筛选状态：`filterMode`（`'days30'` 默认）、`startDate`、`endDate`、`selectedMonth`、`customStart`、`customEnd`
  2. 新增 `computeDateRange()` 函数：根据 `filterMode` 计算 `startDate`/`endDate`（近 N 天：以今天 00:00:00 为基准往前推 N-1 天；按月：该月第一天到最后一天；自定义：直接取用户输入）
  3. 在模板顶部新增筛选条 UI：「近7天」「近30天」「近90天」快捷按钮（选中高亮）；「按月份」选项触发 `<input type="month">`；「自定义」选项触发两个 `<input type="date">` + 确认按钮，开始日期晚于结束日期时前端 alert 拦截
  4. 将所有 `load*()` 函数改为接受 `{ start_date, end_date }` 参数并传入对应 API 调用（`loadSummary`、`loadTrend`、`loadPie`、`loadTopProducts`）
  5. 时间筛选变更时统一调用 `loadAll()` 刷新所有图表；图表空数据时显示「所选时间范围内暂无订单数据」提示
  → `📁 frontend/src/components/OrderDashboard.vue`

---

## Phase 8: 集成验证

> 依赖所有前序 Phase 完成。

- [ ] T012 [US1] 手工验证仪表盘时间筛选：① 默认加载近30天；② 点击「近7天」图表刷新；③ 选择月份（如 2026-04）图表更新至该自然月；④ 自定义日期区间正常工作；⑤ 空时段显示空状态提示；⑥ 自定义日期起止顺序错误时前端拦截
- [ ] T013 [US2] 手工验证 Goods 目录导入：① 在 `data/Goods/` 放入测试 CSV，点击按钮确认导入计数；② 再次点击确认 updated 计数；③ 目录为空时确认错误提示显示
- [ ] T014 [US3] 手工验证合并菜单：① 导航栏只有「基础数据导入」；② 默认打开商品导入 Tab；③ 切换订单导入 Tab 功能完整；④ 直接访问旧路由 `/products/import` 不报错（vue-router 默认 404 或重定向到 `/`）

---

## Phase 9: 前端 — ProductList.vue 商品 ID 列与标题排序

> User Story 4 纯前端改动，不依赖新增后端接口，T015–T016 可并行执行。

- [x] T015 [P] [US4] 在 `frontend/src/components/ProductList.vue` 的表格中新增「商品 ID」列作为第一列：在 `<thead>` 第一列插入 `<th>商品 ID</th>`，在 `<tbody>` 每行第一列插入 `<td>{{ product.item_id }}</td>` → `📁 frontend/src/components/ProductList.vue`
- [x] T016 [P] [US4] 在 `frontend/src/components/ProductList.vue` 的「商品标题」列表头实现三态本地排序：① 新增 `sortOrder` ref，初始值 `'none'`（三态：`'none'` → `'asc'` → `'desc'` → `'none'`）；② 新增 `sortedProducts` computed，基于 `sortOrder` 对 `products` prop 排序（`'none'` 返回原始顺序，`'asc'`/`'desc'` 按 `name` 字段排序）；③ 「商品标题」`<th>` 绑定点击事件切换 `sortOrder`，并根据状态显示对应箭头（`'none'` → `⇅`，`'asc'` → `↑`，`'desc'` → `↓`）；④ `v-for` 改用 `sortedProducts` 渲染 → `📁 frontend/src/components/ProductList.vue`

---

## Phase 10: 商品列表近90天销量列

> User Story 5。三项改动互相独立，T017–T019 可全部并行。

- [ ] T017 [P] [US5] 在 `backend/schemas.py` 的 `ProductRead` schema 末尾追加字段 `sold_90d: int = 0` → `📁 backend/schemas.py`
- [ ] T018 [P] [US5] 在 `backend/routes/products.py` 中：① 在文件顶部补充导入 `from datetime import datetime, timedelta`（若未导入）；② 为 `_product_to_read()` 增加关键字参数 `sold_90d: int = 0` 并在返回的 `ProductRead(...)` 中传入该字段；③ 在 `list_products()` 获取分页 `products` 列表后，用一次批量 GROUP BY 聚合查询统计近90天成交销量：筛选条件为 `status='交易成功'`、`refund_amount='无退款申请'`、`paid_at >= datetime.now() - timedelta(days=90)`、`taobao_item_id IN [p.taobao_item_id for p in products]`，结果聚合为 `sold_map: dict[str, int]`；整个查询包裹在 `try/except Exception`（SubOrder 表不存在时降级为 `sold_map = {}`）；④ 在循环内调用 `_product_to_read(p, sold_90d=sold_map.get(p.taobao_item_id, 0))` → `📁 backend/routes/products.py`
- [ ] T019 [P] [US5] 在 `frontend/src/components/ProductList.vue` 表格「当前价格」列之后插入销量列：在 `<thead>` 对应位置追加 `<th>近90天销量</th>`，在 `<tbody>` 每行对应位置追加 `<td>{{ item.sold_90d ?? 0 }}</td>` → `📁 frontend/src/components/ProductList.vue`
