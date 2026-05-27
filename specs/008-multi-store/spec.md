# Feature Specification: 多店铺数据区分与统计

**Feature Branch**: `008-multi-store`

**Created**: 2026-05-27

**Status**: Ready for Planning

## Overview

当前系统所有数据（淘宝订单、子订单、1688 采购订单）均无店铺归属，无法区分不同店铺的经营数据。本功能为系统新增「店铺」维度：导入数据时用户选择店铺（店铺1 / 店铺2），所有统计界面新增店铺筛选，使店主能分别查看和对比两家店铺的经营与采购数据。

本功能修改现有数据模型（新增 `store` 字段）、导入接口（新增 `store` 参数）和所有统计/列表接口（新增 `store` 过滤参数），并在前端所有导入入口和统计页面增加店铺选择控件。

## 店铺定义

| 值 | 含义 |
|----|------|
| `1` | 店铺1 |
| `2` | 店铺2 |

店铺字段为**必填整数**，导入时不选择则拒绝提交；查询时可传 `store=1` 或 `store=2` 过滤，不传则返回全部数据（合并视图）。

## Clarified Decisions

| 决策项 | 结论 |
|--------|------|
| 店铺数量 | 固定为两家店铺（店铺1 / 店铺2）；不支持动态新增店铺 |
| 店铺字段类型 | 整数 `store: int`，取值 `1` 或 `2`；数据库层面不使用外键 |
| 涉及模型 | `Order`、`SubOrder`、`PurchaseOrder`、**`Product`**、**`PriceSnapshot`** 五张表均新增 `store` 字段（商品数据也按店铺区分） |
| 历史数据迁移 | 新增 `store` 字段默认值为 `1`（历史数据归属店铺1）；通过 SQLite `ALTER TABLE` 迁移，无需数据重新导入 |
| 导入入口 — 淘宝订单 | `DataImport.vue` 提供**统一店铺选择控件**，`OrderImport` 和 `SubOrderImport` 共享同一 `store` 值（联动），用户只需选一次 |
| 导入入口 — 采购订单 | `PurchaseOrderImport.vue` 独立店铺选择控件（单选，必填） |
| 导入入口 — 商品 | 商品导入（Goods 目录扫描）新增店铺选择控件（单选，必填） |
| 重复检测 | 店铺字段**不参与**去重逻辑；唯一键仍为 `order_id` / `sub_order_id` / `taobao_item_id`；重复导入同一记录会更新 `store` 字段为最新值（upsert） |
| 店铺可修改性 | **不提供手动修改入口**；若误选店铺，重新以正确店铺导入同一文件即可覆盖 |
| 统计页面店铺筛选 | 订单分析仪表盘、供应商管理列表、供应商采购仪表盘、商品列表均新增「全部 / 店铺1 / 店铺2」三态筛选控件 |
| 订单列表显示 | `OrderList.vue` 表格**新增「店铺」列**，显示每条订单的店铺归属 |
| 月份筛选与店铺筛选 | 两个筛选**相互独立**，切换店铺不重置月份筛选，反之亦然；两者同时生效（AND 关系） |
| 默认筛选值 | 所有统计页面默认显示「全部」（不传 `store` 参数）；用户切换后当前会话内记住选择，刷新后重置为「全部」 |
| 筛选控件位置 | 页面顶部工具栏（与现有月份筛选控件并排） |
| API 兼容性 | 现有 API 不传 `store` 参数时行为不变（返回全部数据），保持向后兼容 |

## 受影响模块一览

| 模块 | 变更类型 | 说明 |
|------|---------|------|
| `backend/models.py` | 修改 | `Order`、`SubOrder`、`PurchaseOrder`、`Product`、`PriceSnapshot` 新增 `store: int = Field(default=1)` |
| `backend/database.py` | 修改 | 启动时对五张表执行 `ALTER TABLE ... ADD COLUMN store INTEGER DEFAULT 1` 迁移（已有列时跳过） |
| `backend/schemas.py` | 修改 | 相关 Import/Response schema 新增 `store` 字段 |
| `backend/routes/orders.py` | 修改 | 导入接口接受 `store` 参数；列表/统计接口新增 `store` 过滤 |
| `backend/routes/sub_orders.py` | 修改 | 导入接口接受 `store` 参数 |
| `backend/routes/purchase_orders.py` | 修改 | 导入接口接受 `store` 参数；汇总/仪表盘接口新增 `store` 过滤 |
| `frontend/src/components/OrderImport.vue` | 修改 | 接收父组件（DataImport）传入的 `store` prop，不单独渲染店铺选择控件 |
| `frontend/src/components/SubOrderImport.vue` | 修改 | 接收父组件（DataImport）传入的 `store` prop，不单独渲染店铺选择控件 |
| `frontend/src/components/PurchaseOrderImport.vue` | 修改 | 新增店铺选择（单选必填） |
| `frontend/src/components/DataImport.vue` | 修改 | 提供**统一店铺选择控件**（单选必填），将 `store` 值传递给 `OrderImport` 和 `SubOrderImport` 子组件 |
| `frontend/src/components/OrderList.vue` | 修改 | 表格新增「店铺」列，显示每条订单的店铺归属 |
| `frontend/src/components/OrderDashboard.vue` | 修改 | 新增「全部/店铺1/店铺2」切换控件，所有图表/指标卡按 store 过滤 |
| `frontend/src/components/SupplierManagement.vue` | 修改 | 列表新增店铺筛选 |
| `frontend/src/components/SupplierDashboard.vue` | 修改 | 仪表盘新增店铺筛选，三张图表按 store 过滤 |
| `frontend/src/api/orders.js` | 修改 | 导入/列表/统计函数新增 `store` 参数 |
| `frontend/src/api/purchase_orders.js` | 修改 | 导入/汇总/仪表盘函数新增 `store` 参数 |

## Data Model

### 模型变更

以下五个模型均新增字段：

```python
store: int = Field(default=1)  # 1=店铺1, 2=店铺2
```

涉及：`Order`、`SubOrder`、`PurchaseOrder`、`Product`、`PriceSnapshot`

### 数据库迁移策略

在 `backend/database.py` 的 `create_db_and_tables()` 函数中，在 `SQLModel.metadata.create_all(engine)` 之后追加以下迁移逻辑（幂等执行，已有列时捕获异常跳过）：

```python
with engine.connect() as conn:
    for table in ("order", "suborder", "purchaseorder", "product", "pricesnapshot"):
        try:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN store INTEGER DEFAULT 1"))
            conn.commit()
        except Exception:
            pass  # Column already exists
```

## API Contract

### 变更概述

所有变更均为**追加式**（backward-compatible）：

1. 导入接口新增必填 `store` body 字段（整数 1 或 2）
2. 查询/统计接口新增可选 `store` query 参数（整数，不传返回全部）

---

### POST /api/orders/import — 变更

新增 form-data 字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `store` | integer | ✅ 是 | `1` 或 `2` |

---

### POST /api/sub-orders/import — 变更

新增 form-data 字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `store` | integer | ✅ 是 | `1` 或 `2` |

---

### POST /api/purchase-orders/import — 变更

新增 form-data 字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `store` | integer | ✅ 是 | `1` 或 `2` |

---

### GET /api/orders — 变更

新增可选查询参数：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `store` | integer | null | `1` 或 `2`；不传返回全部 |

响应体新增字段：每个订单对象包含 `"store": 1` 或 `"store": 2`。

---

### GET /api/orders/dashboard — 变更

新增可选查询参数：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `store` | integer | null | `1` 或 `2`；不传统计全部 |

---

### GET /api/purchase-orders/summary — 变更

新增可选查询参数：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `store` | integer | null | `1` 或 `2`；不传统计全部 |

---

### GET /api/purchase-orders/dashboard — 变更

新增可选查询参数：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `store` | integer | null | `1` 或 `2`；不传统计全部 |

---

## User Scenarios & Testing

### User Story 1 - 导入时选择店铺 (Priority: P1)

As a user, I can select store 1 or store 2 when importing orders or purchase orders so that imported data is correctly tagged with the store it belongs to.

**Why this priority**: 这是多店铺功能的数据基础，没有正确的店铺标签，后续所有按店铺统计都无意义。

**Independent Test**: 打开「基础数据导入」页面，选择店铺1后上传一批淘宝订单文件，导入成功后通过 `/api/orders?store=1` 接口确认新导入的订单 `store=1`；再选择店铺2上传另一批文件，通过 `/api/orders?store=2` 确认这批订单 `store=2`。

**Acceptance Scenarios**:

1. **Given** 我在「淘宝订单导入」页面，**When** 页面加载完成，**Then** 店铺选择控件可见，默认选中「店铺1」，显示「店铺1 / 店铺2」两个选项。
2. **Given** 我已选择文件但未选择店铺，**When** 我点击导入按钮，**Then** 前端提示「请选择店铺」，不发起请求。
3. **Given** 我选择「店铺2」并上传有效文件，**When** 导入成功，**Then** 本次导入的所有订单 `store` 字段值为 `2`；接口返回的摘要信息包含店铺信息确认。
4. **Given** 我在「1688采购订单导入」页面，**When** 我选择「店铺1」并上传有效文件，**Then** 本次导入的所有采购订单 `store` 字段值为 `1`。
5. **Given** 同一订单编号的数据已以店铺1导入，**When** 我以店铺2重新导入同一文件，**Then** 该订单的 `store` 字段更新为 `2`（upsert 行为）；金额等字段同步更新。

---

### User Story 2 - 订单分析仪表盘按店铺过滤 (Priority: P1)

As a user, I can filter the order analytics dashboard by store so that I can view performance metrics for each store independently.

**Why this priority**: 订单分析是最核心的统计功能，店主最需要区分两店的销售情况。

**Independent Test**: 订单分析仪表盘顶部新增「全部 / 店铺1 / 店铺2」切换；分别切换三个选项，确认 KPI 卡片（总销售额、订单数等）和所有图表数据随之变化，其中「全部」的数据等于「店铺1 + 店铺2」之和。

**Acceptance Scenarios**:

1. **Given** 我在订单分析仪表盘，**When** 页面加载完成，**Then** 页面顶部显示「全部 / 店铺1 / 店铺2」切换控件，默认选中「全部」；所有图表和 KPI 卡片显示全部数据。
2. **Given** 仪表盘已加载，**When** 我切换到「店铺1」，**Then** 所有图表和 KPI 卡片仅反映 `store=1` 的订单数据，页面标题/标识显示当前筛选状态「店铺1」。
3. **Given** 仪表盘已加载，**When** 我切换到「店铺2」，**Then** 所有图表和 KPI 卡片仅反映 `store=2` 的订单数据。
4. **Given** 已同时设置「时间筛选」和「店铺筛选」，**When** 图表刷新，**Then** 数据同时满足两个过滤条件（AND 关系）。
5. **Given** 某店铺在所选时间范围内无数据，**When** 切换到该店铺，**Then** 图表显示空状态，KPI 卡片显示 0。

---

### User Story 3 - 供应商采购统计按店铺过滤 (Priority: P2)

As a user, I can filter the supplier management list and supplier dashboard by store so that I can analyze procurement data per store separately.

**Why this priority**: 采购数据同样需要按店铺区分，但频率低于淘宝订单分析，故定为 P2。

**Independent Test**: 供应商管理列表和供应商采购仪表盘均新增「全部/店铺1/店铺2」切换；切换后供应商列表、订单数量汇总、仪表盘图表数据均随之变化。

**Acceptance Scenarios**:

1. **Given** 我在供应商管理页面，**When** 页面加载完成，**Then** 顶部显示「全部 / 店铺1 / 店铺2」切换控件，默认「全部」；供应商列表显示所有店铺的采购数据。
2. **Given** 供应商管理页面已加载，**When** 我切换到「店铺2」，**Then** 供应商列表仅显示 `store=2` 的采购订单对应的供应商汇总；总金额、订单数均只计算店铺2数据。
3. **Given** 我在供应商采购仪表盘，**When** 我切换到「店铺1」，**Then** 三张 ECharts 图表（总采购金额、按月订单数、按月采购金额）仅基于 `store=1` 数据渲染。
4. **Given** 供应商采购仪表盘已设置月份范围，**When** 我再切换店铺，**Then** 月份范围和店铺两个过滤同时生效（AND 关系）。

---

### User Story 4 - 历史数据向后兼容（迁移） (Priority: P2)

As a user, existing imported data remains accessible after the upgrade so that I don't need to re-import all historical records.

**Why this priority**: 保证已有数据不丢失，用户无需重新导入，是功能上线的基本要求。

**Independent Test**: 在已有历史数据的环境中部署本次变更，启动后端服务后确认：数据库三张表均新增 `store` 列且默认值为 `1`；通过 `/api/orders` 接口确认历史订单 `store=1`；通过 `/api/orders?store=1` 确认能查到所有历史订单；通过 `/api/orders?store=2` 确认返回空列表。

**Acceptance Scenarios**:

1. **Given** 数据库已有历史 `order` / `suborder` / `purchaseorder` 记录（无 `store` 列），**When** 后端服务首次启动本次版本，**Then** 数据库自动执行 `ALTER TABLE ... ADD COLUMN store INTEGER DEFAULT 1`，历史数据 `store` 字段均为 `1`；服务正常启动，无报错。
2. **Given** 迁移完成后，**When** 我通过 `/api/orders` 或 `/api/purchase-orders/summary` 访问历史数据（不传 `store` 参数），**Then** 接口返回结果与迁移前一致（全量数据）。
3. **Given** 迁移完成后，**When** 我通过 `/api/orders?store=1` 查询，**Then** 返回所有历史订单（均 `store=1`）；`/api/orders?store=2` 返回空列表。

---

### Edge Cases

- 导入时 `store` 参数传入 `0`、`3` 或其他非 `1`/`2` 值时，后端返回 HTTP 422，前端显示「店铺参数无效」。
- 同一文件被以不同店铺多次导入时，订单的店铺归属以**最后一次导入**为准（upsert）。
- 后端 `store` 过滤参数传入非整数字符串时，FastAPI 自动返回 HTTP 422（参数校验）。
- 数据库迁移已运行后再次启动服务，`ALTER TABLE` 因列已存在而抛出异常，被 `except` 捕获并静默跳过，服务正常启动。
- 子订单（SubOrder）导入时若 `store` 与对应主订单（Order）的 `store` 不一致，系统按子订单自身的 `store` 字段存储，不做跨表校验（两者由 DataImport 统一店铺选择控件保证一致性）。
- 商品（Product）按店铺区分后，同一 `taobao_item_id` 可能在不同店铺都存在；去重键变更为 `(taobao_item_id, store)` 组合唯一索引（而非仅 `taobao_item_id`），规划阶段需评估对现有唯一约束的影响。
