# Feature Specification: 供应商采购分析仪表盘

**Feature Branch**: `007-supplier-dashboard`

**Created**: 2026-05-26

**Status**: Ready for Planning

## Overview

在 006 供应商管理功能基础上，新增一个独立的供应商分析仪表盘页面（路由 `/suppliers/dashboard`），通过三张 ECharts 图表对 Top 15 供应商进行可视化分析：展示各供应商的历史总采购金额，以及按月对比订单数量和采购金额。用户可从现有供应商管理页面点击"供应商图表"按钮跳转至仪表盘，快速掌握采购集中度与月度变化趋势。

本功能仅新增前端页面组件和一个后端统计接口，不修改现有数据模型，不影响已有供应商导入与汇总功能。

## 1688 状态排除规则（继承自 006）

与 006 一致，仪表盘统计**排除**以下状态的订单：

| 排除状态 | 说明 |
|----------|------|
| `等待买家付款` | 未付款，不计入采购 |
| `退款中` | 退款处理中，不计入实际采购 |
| `交易关闭` | 交易关闭，不计入实际采购 |

## Clarified Decisions

| 决策项 | 结论 |
|--------|------|
| 图表库 | 使用已安装的 ECharts（vue-echarts + echarts/core），与 OrderDashboard.vue 保持一致 |
| Top N 数量 | 固定展示 Top 15 供应商；后端参数 `top_n` 默认值为 15，前端不暴露调节控件 |
| 排除状态 | 排除 `等待买家付款`、`退款中`、`交易关闭` 三种状态的订单 |
| Top 15 排名依据 | 以**历史总实付款金额**（paid_amount 合计）排名取前 15 |
| 图表 1：总采购金额 | 水平条形图（横向 Bar Chart）；X 轴为金额（元），Y 轴为供应商名（按金额降序排列，最大值在顶部） |
| 图表 2：按月订单数量 | **堆叠柱状图（Stacked Bar Chart）**；X 轴为月份（YYYY-MM），Y 轴为订单数，每家供应商为一个 series；堆叠展示各家占比和月总量趋势 |
| 图表 3：按月采购金额 | **堆叠柱状图（Stacked Bar Chart）**；X 轴为月份，Y 轴为金额（元），每家供应商为一个 series；堆叠展示各家占比和月总金额趋势 |
| 月份范围 | 支持通过 `start_month`（YYYY-MM）和 `end_month`（YYYY-MM）参数对全部图表动态过滤；默认不传时展示**全量历史数据**；Top 15 排名同步应用所选月份范围 |
| 颜色方案 | ECharts 默认调色板（与 OrderDashboard.vue 保持一致），不自定义颜色 |
| 图表交互 | 鼠标悬停显示 tooltip；图表底部显示 **legend（可滚动，`legend.type: 'scroll'`）**，点击可隐藏/显示单个供应商 series；进入页面后自动加载 |
| 导航入口 | 仅在 `SupplierManagement.vue` 页面内顶部增加「查看图表分析」按钮，点击通过 Vue Router 跳转至 `/suppliers/dashboard`；顶部导航栏不新增入口 |
| 返回导航 | 仪表盘页面提供"返回供应商列表"按钮，跳转回 `/suppliers` |
| 响应式布局 | 三张图表**垂直排列（上下 3 张）**，各占页面全宽，每张图表高度不低于 400px；不要求移动端适配 |
| API 调用时机 | 仪表盘组件挂载（`onMounted`）时调用一次，无自动刷新 |
| 加载状态 | 数据加载期间显示 loading 状态；接口出错时显示错误提示信息 |

## Data Model

**无新增数据表**。本功能仅在现有 `PurchaseOrder` 表上执行聚合查询。

### 查询逻辑说明

后端接口对 `PurchaseOrder` 表执行以下逻辑：

1. 过滤掉排除状态的订单（`status NOT IN ('等待买家付款')`）
2. 按 `seller_name` 聚合，计算每家供应商的历史 `paid_amount` 总和
3. 取总金额前 `top_n`（默认 15）名供应商
4. 对这 Top N 供应商，按 `seller_name` + `订单创建时间月份` 二维聚合，统计订单数和金额
5. 提取数据库中所有年月（来自步骤 4 的结果），按升序排列

## API Contract

### GET /api/purchase-orders/dashboard

**描述**: 返回 Top N 供应商的历史采购汇总及按月明细数据，用于仪表盘图表渲染。

**查询参数**:

| 参数 | 类型 | 默认值 | 必填 | 说明 |
|------|------|--------|------|---------|
| `top_n` | integer | 15 | 否 | 取采购总金额排名前 N 的供应商（应用月份过滤后数据） |
| `start_month` | string | null | 否 | 开始月，格式 `YYYY-MM`；不传时包含全部历史 |
| `end_month` | string | null | 否 | 结束月，格式 `YYYY-MM`；不传时包含全部历史 |

**响应体**（HTTP 200）:

```json
{
  "top_suppliers": [
    {
      "seller_name": "供应商A公司",
      "total_amount": 158320.50,
      "total_orders": 42
    }
  ],
  "months": ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"],
  "monthly_data": [
    {
      "seller_name": "供应商A公司",
      "monthly_orders": {
        "2025-10": 5,
        "2025-11": 8,
        "2025-12": 3,
        "2026-01": 0,
        "2026-02": 12,
        "2026-03": 14
      },
      "monthly_amounts": {
        "2025-10": 12500.00,
        "2025-11": 18900.00,
        "2025-12": 7200.00,
        "2026-01": 0.0,
        "2026-02": 58320.00,
        "2026-03": 61400.50
      }
    }
  ]
}
```

**响应字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `top_suppliers` | array | Top N 供应商列表，按 `total_amount` 降序排列 |
| `top_suppliers[].seller_name` | string | 供应商名称 |
| `top_suppliers[].total_amount` | float | 历史实付款总金额（元） |
| `top_suppliers[].total_orders` | integer | 历史有效订单总数 |
| `months` | array[string] | 所有出现过的年月，格式 `YYYY-MM`，升序排列 |
| `monthly_data` | array | 每个 Top N 供应商的按月明细 |
| `monthly_data[].seller_name` | string | 供应商名称 |
| `monthly_data[].monthly_orders` | object | 键为月份字符串，值为该月订单数；不存在的月份键值为 0 |
| `monthly_data[].monthly_amounts` | object | 键为月份字符串，值为该月实付款总金额（元）；不存在的月份键值为 0.0 |

**错误响应**:

| HTTP 状态码 | 场景 |
|-------------|------|
| 200 | 成功（若无数据，返回空的 `top_suppliers`、`months`、`monthly_data`） |
| 422 | `top_n` 参数非正整数 |
| 500 | 数据库查询异常 |

---

## User Scenarios & Testing

### User Story 1 - 从供应商列表跳转至仪表盘 (Priority: P1)

作为店主，我希望在供应商管理页面直接进入图表仪表盘，无需手动输入 URL，以便快速查看采购分析。

**Why this priority**: 导航入口是仪表盘可用性的基础；无入口则功能对用户不可见。

**Independent Test**: 在已有 1688 订单数据的情况下，打开供应商管理页面，点击"供应商图表"按钮，确认页面跳转至 `/suppliers/dashboard` 并加载出三张图表。

**Acceptance Scenarios**:

1. **Given** 我在供应商管理页面（`/suppliers`），**When** 我点击"供应商图表"按钮，**Then** 页面跳转至 `/suppliers/dashboard`，仪表盘正常加载。
2. **Given** 我在仪表盘页面，**When** 我点击"返回供应商列表"按钮，**Then** 页面跳转回 `/suppliers`。
3. **Given** 数据库中没有任何采购订单数据，**When** 仪表盘加载完成，**Then** 三张图表区域显示空状态提示（如"暂无数据"），页面不崩溃。

---

### User Story 2 - 查看 Top 15 供应商总采购金额图表 (Priority: P1)

作为店主，我希望通过水平条形图一眼看出哪些供应商的历史采购金额最高，以便识别核心供应商和采购集中度。

**Why this priority**: 总采购金额图表提供全局视角，是三张图表中信息密度最高、决策价值最大的一张。

**Independent Test**: 仪表盘加载后，确认图表 1 显示不超过 15 条水平条形，按金额降序排列，悬停任一条形时 tooltip 显示供应商名和金额。

**Acceptance Scenarios**:

1. **Given** 数据库中有超过 15 家供应商的采购记录，**When** 仪表盘加载完成，**Then** 图表 1 展示恰好 15 条水平条形，金额最高的供应商显示在最顶部。
2. **Given** 图表 1 已渲染，**When** 我将鼠标悬停在任意条形上，**Then** tooltip 显示该供应商名称和历史总实付款金额。
3. **Given** 数据库中只有 8 家供应商，**When** 仪表盘加载，**Then** 图表 1 显示 8 条条形，无截断。

---

### User Story 3 - 查看 Top 15 供应商按月趋势对比图表 (Priority: P2)

作为店主，我希望通过按月分组柱状图对比各供应商的月度订单数量和采购金额变化，以便发现季节性规律或异常采购月份。

**Why this priority**: 月度趋势图提供时间维度的分析价值，是对图表 1 的有效补充，但依赖图表 1 确定 Top 15 名单。

**Independent Test**: 仪表盘加载后，确认图表 2 和图表 3 的 X 轴月份与数据库中实际存在的月份一致；点击 legend 中某供应商名称，该供应商的柱条从图表中隐藏。

**Acceptance Scenarios**:

1. **Given** 数据库中有多个月份的采购数据，**When** 仪表盘加载，**Then** 图表 2 和图表 3 的 X 轴显示按升序排列的所有月份，每个月份包含最多 15 组柱条。
2. **Given** 某供应商在某月无订单，**When** 仪表盘渲染，**Then** 该供应商在该月的柱条高度为 0（不缺失月份列）。
3. **Given** 图表 2 已渲染，**When** 我点击 legend 中某供应商名称，**Then** 该供应商对应的柱条从图表中隐藏，其他供应商不受影响。

---

### Edge Cases

- **无数据时**：数据库无任何采购记录，API 返回空结构，前端三张图表显示空状态提示，不抛出 JavaScript 错误。
- **单一供应商**：数据库中仅有 1 家供应商，图表正常渲染单条数据，不报错。
- **供应商名称过长**：供应商名称超过 20 个字符，Y 轴标签自动截断或换行，不影响图表布局。
- **月份跨度极大**：数据跨越 3 年以上，X 轴月份密集，图表水平滚动或缩放均不崩溃。
- **并发访问**：多个浏览器标签同时请求 `/api/purchase-orders/dashboard`，每次返回一致结果。

## Requirements

### Functional Requirements

- **FR-001**: 系统必须在 `/suppliers/dashboard` 路由下提供独立的仪表盘页面，可通过 Vue Router 直接访问。
- **FR-002**: 供应商管理页面（`/suppliers`）必须提供"供应商图表"导航按钮，点击后跳转至仪表盘页面。
- **FR-003**: 仪表盘页面必须提供"返回供应商列表"按钮，点击后跳转回 `/suppliers`。
- **FR-004**: 系统必须提供 `GET /api/purchase-orders/dashboard?top_n=15` 接口，返回 Top 15 供应商的汇总与按月明细数据。
- **FR-005**: 接口必须排除 `订单状态 IN ('等待买家付款', '退款中', '交易关闭')` 的订单。
- **FR-006**: 接口返回的 `top_suppliers` 必须按历史 `paid_amount` 合计降序排列，最多返回 `top_n` 条。
- **FR-007**: 接口返回的 `months` 数组必须包含数据库中实际存在的所有年月（基于 `created_at` 字段），按升序排列。
- **FR-008**: `monthly_orders` 和 `monthly_amounts` 字典中，对于 Top N 供应商在某月无数据的情况，对应键的值必须为 0 或 0.0（确保前端无需处理缺失键）。
- **FR-009**: 仪表盘必须展示图表 1（供应商总采购金额水平条形图），Y 轴为供应商名，X 轴为总金额，按金额降序排列。
- **FR-010**: 仪表盘必须展示图表 2（按月订单数量分组柱状图），X 轴为月份，Y 轴为订单数，每家 Top 15 供应商为独立 series。
- **FR-011**: 仪表盘必须展示图表 3（按月采购金额分组柱状图），X 轴为月份，Y 轴为金额（元），每家 Top 15 供应商为独立 series。
- **FR-012**: 三张图表均必须支持鼠标悬停 tooltip，显示供应商名称和对应数值。
- **FR-013**: 图表 2 和图表 3 必须在图表下方显示 legend，支持点击单个供应商 series 进行显示/隐藏切换。
- **FR-014**: 仪表盘加载期间必须显示 loading 状态；接口请求失败时必须显示用户可读的错误提示信息。
- **FR-015**: 当数据库无采购记录时，三张图表必须显示空状态提示，页面不崩溃。

### Non-Functional Requirements

- **NFR-001 性能**: 在 PurchaseOrder 表不超过 50,000 条记录的情况下，`/api/purchase-orders/dashboard` 接口响应时间不超过 3 秒。
- **NFR-002 可维护性**: 仪表盘组件（`SupplierDashboard.vue`）与供应商列表组件（`SupplierManagement.vue`）保持独立，互不耦合。
- **NFR-003 兼容性**: 图表在 Chrome、Edge 最新版本下正常渲染；不要求 IE 或移动端支持。
- **NFR-004 安全性**: 接口无需身份验证（与现有 API 保持一致）；`top_n` 参数必须校验为正整数，防止异常输入导致查询错误。

## Success Criteria

### Measurable Outcomes

- **SC-001**: 用户从供应商管理页面点击"供应商图表"到三张图表全部渲染完成，不超过 5 秒（含网络往返和图表渲染）。
- **SC-002**: Top 15 排名结果与手工对 PurchaseOrder 表按 `seller_name` 分组后取前 15 的 SQL 查询结果一致，误差为零。
- **SC-003**: 月度数据中每个月份的订单数和金额合计，与对 PurchaseOrder 表按月过滤后的手工统计结果一致，精度到小数点后 2 位。
- **SC-004**: 所有三张图表在存在 15 个供应商、跨度超过 6 个月的数据集上正常渲染，无 JavaScript 报错。
- **SC-005**: 当 PurchaseOrder 表为空时，仪表盘页面加载成功（HTTP 200），三张图表区域显示空状态提示而非报错。

## Assumptions

- 现有 PurchaseOrder 表（006 创建）已存在于数据库，并包含 `seller_name`、`paid_amount`、`status`、`created_at` 字段，与本 spec 的查询逻辑兼容。
- 前端已安装 `vue-echarts` 和 `echarts/core`，可直接复用 `OrderDashboard.vue` 中的组件注册方式（`CanvasRenderer`、`BarChart`、`VChart`）。
- Vue Router 已配置，可新增路由 `/suppliers/dashboard` 而无需修改路由器初始化逻辑。
- 本功能不引入分页、筛选器或时间范围选择控件；所有图表基于数据库全量数据计算。
- `top_n=15` 为固定业务需求，未来如需调整由后端参数控制，前端无需改动。
