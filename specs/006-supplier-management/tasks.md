# Tasks: 1688采购订单供应商管�?

**Feature**: `006-supplier-management` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Organization**: 任务�?User Story 分组，支持独立实现与测试�?

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: 可并行执行（不同文件，无未完成依赖）
- **[Story]**: 所�?User Story（US1 / US2 / US3�?
- 每个任务包含精确文件路径

---

## Phase 1: Setup（共享基础设施�?

**Purpose**: 确认依赖就绪，无需新增 pip/npm �?

- [X] T001 确认 `openpyxl` 已在 `backend/requirements.txt` 中，确认 `backend/routes/__init__.py` 存在；无需安装新依�?

---

## Phase 2: Foundational（阻塞性前置任务）

**Purpose**: 新增数据模型、Pydantic Schema 及路由注册，所�?User Story 均依赖此阶段完成

**⚠️ 关键**: 此阶段全部完成后，各 User Story 方可并行推进

- [X] T002 �?`backend/models.py` 末尾新增 `PurchaseOrder` SQLModel 类（字段：`id` PK autoincrement、`order_id` unique+index max_length=64、`seller_name` index max_length=200、`seller_member` Optional max_length=200、`goods_title` Optional max_length=500、`goods_total` Optional[float]、`shipping_fee` Optional[float]、`discount` Optional[float]、`paid_amount` float、`status` max_length=64、`created_at` Optional[datetime]、`paid_at` Optional[datetime]、`imported_at` datetime default_factory=lambda: datetime.now(timezone.utc)�?
- [X] T003 [P] �?`backend/schemas.py` 中新�?7 �?Pydantic 类：`PurchaseOrderImportResult`（imported/updated/errors int）、`AvailableMonth`（year/month int）、`SupplierSummaryItem`（seller_name str、order_count int、total_paid float、top_goods Optional[str]）、`SupplierSummaryResponse`（year/month int、items list[SupplierSummaryItem]）、`PurchaseOrderDetail`（order_id/goods_title Optional[str]/paid_amount float/status str/created_at Optional[datetime]，model_config from_attributes=True）、`PurchaseOrderDetailResponse`（seller_name str、year/month/page/page_size/total int、items list[PurchaseOrderDetail]�?
- [X] T004 �?`backend/main.py` �?import `purchase_orders_router` 并以 prefix `/api` 注册（与现有 `orders_router` 等并列）；此步触�?`PurchaseOrder` 模型导入，确�?`create_db_and_tables()` 在启动时自动建表

**Checkpoint**: 数据库表 `purchaseorder` 已创建，Schema 可用，路由前缀已注�?�?�?User Story 可开始实�?

---

## Phase 3: User Story 1 �?导入 1688 采购订单文件（Priority: P1）�?MVP

**Goal**: 用户上传 1688 导出�?xlsx 文件，系统解析主订单行并 upsert 入库，返�?`{imported, updated, errors}` 统计�?

**Independent Test**: 上传 `data/1688.xlsx`�?238 行，1778 条主订单），确认响应�?`{imported: 1778, updated: 0, errors: 0}`；重新上传同一文件，确认响应变�?`{imported: 0, updated: 1778, errors: 0}`�?

### Implementation for User Story 1

- [X] T005 [US1] 新建 `backend/routes/purchase_orders.py`：定�?`APIRouter(prefix="/purchase-orders")`；实�?`POST /import` 端点，步骤为：①文件大小超过 10 MB 时抛�?HTTP 413 并返�?`{"detail": "文件过大，请检�?}`；②仅接�?`.xlsx`（否�?415）；③用 `openpyxl(read_only=True, data_only=True)` 解析；④首行�?header，校�?`REQUIRED_COLUMNS = {"订单编号","卖家公司�?,"实付�?�?","订单状�?,"订单创建时间"}` 均存在（缺失�?422 并列出缺少的列名）；⑤逐行迭代 rows[1:]，跳�?`订单编号` �?None/空的续行；⑥`实付�?�?` 无法解析的主订单行跳过并 `errors += 1`；⑦`卖家公司名` 为空时替换为 `'未知供应�?`；⑧�?`order_id` upsert（找到则更新所有字�?`updated += 1`，否则插�?`imported += 1`）；⑨`session.commit()` 后返�?`PurchaseOrderImportResult`
- [X] T006 [P] [US1] 新建 `frontend/src/api/purchase_orders.js`：实�?`importPurchaseOrders(file)` 函数，构�?`FormData` �?`POST /api/purchase-orders/import`，`!res.ok` 时抛�?`await res.json()`，成功返�?`{imported, updated, errors}`
- [X] T007 [P] [US1] 新建 `frontend/src/components/SupplierManagement.vue`（`<script setup>` 单文件组件）：初始化所�?ref 状态变量（`availableMonths`、`selectedMonth`、`summaryItems`、`selectedSeller`、`detailItems`、`detailTotal`、`detailPage`、`importResult`、`importError`、`loading`）；渲染导入区（`.xlsx` 文件选择�?+ "导入" 按钮 + 成功时显示「导�?N 条，更新 M 条，错误 E 条」横�?+ 错误时显�?`importError`）；调用 `importPurchaseOrders` 时捕�?413 错误并展示「文件过大，请检查」提�?

**Checkpoint**: US1 独立可用 �?可上�?xlsx、写�?`purchaseorder` 表、查看导入统计；供应商视图留�?US2

---

## Phase 4: User Story 2 �?按月查看供应商采购汇总（Priority: P1�?

**Goal**: 供应商管理页默认展示当月各供应商订单数与实付款合计（排除待付款），支持月份切换，点击供应商行可内联展开明细�?

**Independent Test**: 选择 2026-03，确认表格显示该月有订单的供应商（≤71 家），排序为实付款合计降序，「万道珠宝首饰厂」的订单数与手工计算一致（排除 `等待买家付款`）�?

### Implementation for User Story 2

- [X] T008 [US2] �?`backend/routes/purchase_orders.py` 中新�?`GET /months` 端点：用 `func.strftime('%Y', PurchaseOrder.created_at)` �?`func.strftime('%m', ...)` 提取年月，`.distinct()` 去重，按 `year DESC, month DESC` 排序，返�?`list[AvailableMonth]`；`created_at IS NOT NULL` 过滤
- [X] T009 [US2] �?`backend/routes/purchase_orders.py` 中新�?`GET /summary` 端点：接�?`year: int, month: int` 查询参数；`WHERE strftime('%Y',created_at)=str(year) AND strftime('%m',created_at)=f"{month:02d}" AND status != '等待买家付款' AND created_at IS NOT NULL`；`GROUP BY seller_name`；`SELECT seller_name, COUNT(*) AS order_count, SUM(paid_amount) AS total_paid`；`ORDER BY total_paid DESC`；同时计�?`top_goods`（子查询：同月同供应商按 `goods_title` 分组�?count 最高的一条），组�?`SupplierSummaryResponse` 返回
- [X] T010 [P] [US2] �?`frontend/src/api/purchase_orders.js` 中新�?`fetchAvailableMonths()` �?`fetchSupplierSummary(year, month)` 函数，调用对应端点，统一抛出响应 json 作为错误
- [X] T011 [US2] �?`frontend/src/components/SupplierManagement.vue` 中补充月份选择器与汇总表：`onMounted` 调用 `fetchAvailableMonths()` 填充下拉列表，默认选中当前年月（若不存在则选最新月）；`watch(selectedMonth, loadSummary)`；渲染汇总表格（列：供应商名�?| 订单�?| 实付款合�?�? | 本月最多采购货品），`items.length === 0` 时显示「暂无数据」；行点击设�?`selectedSeller` 并触发明细加�?
- [X] T012 [US2] �?`frontend/src/App.vue` 中新增「供应商管理」导航项（设�?`currentView = 'supplier'`，样式与现有导航项一致），并在主内容区新�?`v-if="currentView === 'supplier'"` �?`<SupplierManagement />` 插槽；在 `<script setup>` 顶部 import `SupplierManagement` 组件

**Checkpoint**: US2 独立可用 �?导航可到达供应商页，月份切换生效，汇总表数据正确，点击行触发明细加载逻辑

---

## Phase 5: User Story 3 �?查看单个供应商订单明细（Priority: P2�?

**Goal**: 点击供应商行，在同一页面内联展开该供应商当月订单明细（排除待付款），支持分页与折叠�?

**Independent Test**: 选择 2026-03，点击「万道珠宝首饰厂」，确认展开的明细行数与汇总表订单数一致，每条记录�?`等待买家付款` 状态；再次点击同一行，明细折叠�?

### Implementation for User Story 3

- [X] T013 [US3] �?`backend/routes/purchase_orders.py` 中新�?`GET /detail` 端点：接�?`seller_name: str, year: int, month: int, page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100)`；过滤条件同 summary（seller_name + year/month + status != 待付款）；先 `COUNT(*)` �?`total`；再 `OFFSET (page-1)*page_size LIMIT page_size`；Python 端将 `goods_title` 截断�?40 字符；返�?`PurchaseOrderDetailResponse`
- [X] T014 [P] [US3] �?`frontend/src/api/purchase_orders.js` 中新�?`fetchSupplierDetail(sellerName, year, month, page = 1)` 函数：用 `URLSearchParams` 构造查询参数，调用 `GET /api/purchase-orders/detail`
- [X] T015 [US3] �?`frontend/src/components/SupplierManagement.vue` 中补充内联明细面板：点击汇总行时若 `selectedSeller === seller` 则折叠（�?null），否则设置 `selectedSeller` 并重�?`detailPage = 1`；`watch([selectedSeller, detailPage], loadDetail)`；在被选中行下方渲染明细表（列：订单编�?| 货品标题 | 实付�?�? | 订单状�?| 订单创建时间）；`detailItems.length === 0` 时显示「暂无有效订单」；渲染�?下一页分页控件（显示「第 X �?/ �?N 页」）

**Checkpoint**: US1、US2、US3 全部可用 �?导入、月份筛选、汇总、内联明细展开/折叠、分页功能完�?

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 边界校验、集成验证、构建确�?

- [X] T016 [P] 验证 `backend/routes/purchase_orders.py` �?10 MB 限制逻辑：在文件读取前检�?`file.size`（若 `UploadFile` 不暴�?size，则读取内容后检查字节长度），超限抛 `HTTPException(status_code=413, detail="文件过大，请检�?)`；在 `frontend/src/components/SupplierManagement.vue` 导入逻辑中捕�?status 413 并展示正确提示文�?
- [X] T017 [P] �?`frontend/` 目录执行 `npm run build`，确认零编译错误；验证后�?`/docs` 页面显示 4 个新端点（`/purchase-orders/import`、`/purchase-orders/months`、`/purchase-orders/summary`、`/purchase-orders/detail`）及正确的请�?响应类型注解

---

## Dependencies（Story 完成顺序�?

```
T001（Setup�?
  └─�?T002 T003 T004（Phase 2: Foundational�?
        ├─�?T005 T006 T007（US1: 导入�?        �?独立，可单独交付
        ├─�?T008 T009 T010 T011 T012（US2: 汇总） �?依赖 US1 提供测试数据
        └─�?T013 T014 T015（US3: 明细�?         �?依赖 US2 的行点击入口
              └─�?T016 T017（Polish�?
```

## Parallel Execution Examples

**Phase 2 内部并行**（T001 完成后）:
- `T002` 模型 �?`T003` Schema（不同文件）

**US1 内部并行**（T004 完成后）:
- `T006` 前端 API 模块 �?`T005` 后端路由（不同文件）
- `T007` Vue 组件初始框架 �?`T005` 后端路由（不同文件）

**US2 内部并行**（T008/T009 完成后）:
- `T010` 前端 API 函数 �?`T008` 后端 months 端点（不同文件）
- `T009` summary 端点 �?`T011` Vue 月份选择器（后端/前端分离�?

**US3 内部并行**（T013 完成后）:
- `T014` 前端 API 函数 �?`T013` 后端 detail 端点（不同文件）

**Polish 并行**:
- `T016` 413 边界验证 �?`T017` 构建验证（不同文件）

---

## Implementation Strategy

| 阶段 | 内容 | 交付�?|
|------|------|--------|
| MVP（Phase 2 + 3�?| 模型 + Schema + 导入端点 + 前端导入 UI | 可上�?xlsx 并写入数据库 |
| 增量 1（Phase 4�?| 供应商汇总端�?+ 月份选择�?+ 导航入口 | 完整分析视图可用 |
| 增量 2（Phase 5�?| 明细端点 + 内联展开 + 分页 | P2 故事完整交付 |
| 收尾（Phase 6�?| 边界处理验证 + 构建检�?| 功能稳定，可发布 |
