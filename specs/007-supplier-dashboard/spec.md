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

---

# Part 2: 供应商综合评估看板

**Feature Branch**: `007-supplier-dashboard` (extension)

**Created**: 2026-05-29

**Status**: Ready for Planning

## Overview

在现有供应商仪表盘（`/suppliers/dashboard`）基础上，新增供应商综合评估子页面（路由 `/suppliers/evaluation`）。该页面基于现有 `PurchaseOrder` 表数据，对每家供应商进行多维度加权综合评分（0–100 分），并通过评分表格、雷达图和价格趋势折线图帮助运营管理人员快速识别优质供应商与需要关注的供应商。

**P0 范围内不新增任何数据库表**，所有评分在接口请求时通过 SQL 聚合 + Python 实时计算得出。

## 状态排除规则（继承自 006/007）

与 006/007 一致，评估计算**排除**以下状态的订单：

| 排除状态 | 说明 |
|----------|------|
| `等待买家付款` | 未付款，不纳入任何维度计算 |
| `退款中` | 退款处理中，不纳入实际采购统计 |
| `交易关闭` | 交易关闭，不纳入实际采购统计 |

> **完成率维度例外**：完成率的分母为「排除 `等待买家付款` 后的全部订单」（含 `退款中`、`交易关闭`），以真实反映订单的最终达成率；分子为 `交易成功` + `等待卖家发货` + `等待买家确认收货` 三种已履约状态的订单数。其余三个维度（价格稳定性、活跃度、价格走势）仅使用 `交易成功` 状态的订单。

## Clarified Decisions

| 决策项 | 结论 |
|--------|------|
| 路由 | 新增独立页面 `/suppliers/evaluation`（`SupplierEvaluation.vue`） |
| 导航入口 | 在 `SupplierDashboard.vue` 头部新增"供应商评估"按钮，与现有导航按钮并列 |
| 数据库表 | 不新增任何表；所有评分实时计算 |
| 线性回归 | 使用 Python 内置 `statistics` 模块或手写最小二乘公式；不引入 `scipy` 依赖 |
| 最小样本量 | 供应商需有至少 3 条有效订单（状态过滤后），否则 `score = null`，标签 = "数据不足" |
| 价格走势评分映射 | slope ≤ 0 → 100 分；slope > 0 时按所有供应商正斜率的百分位排名，最低百分位 = 100，最高百分位 = 0（线性映射） |
| 详情展开方式 | 点击"查看详情"按钮后，在该行下方内联展开详情区域（非抽屉/弹窗），包含雷达图和价格趋势折线图 |
| 月份范围过滤 | 与 `SupplierDashboard` 保持一致，支持 `start_month` / `end_month`（`YYYY-MM` 格式）；默认展示全量历史 |
| 时间窗口用于活跃度（Q1） | 活跃度分母"总月数"使用**全局窗口**：传参时 = `start_month`~`end_month` 区间的自然月数；未传参时 = 全库 `PurchaseOrder` 中 `MIN(created_at)` ~ `MAX(created_at)` 的自然月数差 + 1。统一基准便于横向对比，接受新供应商活跃度得分偏低的情况 |
| 价格走势一致性（Q2） | `/evaluation/{seller_name}` 详情接口在后端**重新触发全量百分位计算**后提取目标供应商得分，确保详情页雷达图与列表页评分数值完全一致 |
| 价格趋势折线图上限（Q4） | 详情展开中的价格趋势折线图仅展示**按采购金额 Top 10 的 `goods_title`**；API `price_history` 数组仅返回这 10 种货品数据 |
| unit_price 全为 null（Q5） | 若某供应商所有订单的 `unit_price` 均为 null，则价格稳定性维度得分 = **0**（保守默认）；综合评分仍按原权重正常计算 |
| 代码风格 | 严格沿用 `backend/routes/purchase_orders.py` 现有模式（`SQLModel`、`func.strftime`、`EXCLUDED_STATUSES` 常量） |

## Scoring Model

### 综合评分公式

$$\text{Score} = \text{完成率} \times 0.35 + \text{价格稳定性} \times 0.30 + \text{活跃度} \times 0.20 + \text{价格走势} \times 0.15$$

所有维度分数均归一化至 0–100。若供应商有效订单数 < 3，则 `score = null`，跳过所有维度计算。

### 维度定义

#### 完成率（Order Completion Rate，权重 35%）

$$\text{完成率得分} = \frac{\text{状态为「交易成功」+「等待卖家发货」+「等待买家确认收货」的订单数}}{\text{排除「等待买家付款」后的全部订单数}} \times 100$$

- 分子包含已履约的三种状态：`交易成功`（已完成）、`等待卖家发货`（已付款待发）、`等待买家确认收货`（已发货待签收）
- 分母包含 `退款中`、`交易关闭` 等非成功状态，以真实反映履约率
- 结果范围 0–100

#### 价格稳定性（Price Stability，权重 30%）

对该供应商下每个唯一 `goods_title`，计算单价的变异系数 $CV = \sigma / \mu$（其中 $\sigma$ 为标准差，$\mu$ 为均值）。

$$\text{价格稳定性得分} = \max(0,\; 1 - \overline{CV}) \times 100$$

- 仅使用 `交易成功` 订单，且 `unit_price` 不为 null
- $\overline{CV}$ 为该供应商所有 `goods_title` 的 **采购金额加权均值**（Q3）：

$$\overline{CV} = \frac{\sum_j \text{paid\_amount}_j \times CV_j}{\sum_j \text{paid\_amount}_j}$$

其中 $j$ 遍历该供应商下每个唯一 `goods_title`，$\text{paid\_amount}_j$ 为该货品历史总采购金额之和。金额贡献越大的商品对稳定性得分影响越大，避免低频商品主导评分。

- 某 `goods_title` 只有单条记录时，其 CV = 0（无波动）
- 若该供应商所有订单 `unit_price` 均为 null，则本维度得分 = 0（Q5）
- 结果范围 0–100（$\overline{CV}$ ≥ 1 时得分为 0）

#### 活跃度（Activity Rate，权重 20%）

$$\text{活跃度得分} = \frac{\text{有采购记录的自然月数}}{\text{时间窗口总月数}} \times 100$$

- 使用 `交易成功` 订单
- "有采购记录的月"= 该供应商在该月内至少有 1 条有效订单
- "时间窗口总月数"= 查询时间范围内的自然月总数
- 结果范围 0–100

#### 价格走势（Price Trend，权重 15%）

对该供应商所有 `goods_title`，计算每月加权平均单价（以 `quantity` 为权重）：

$$\text{月加权均价}_m = \frac{\sum_i \text{unit\_price}_i \times \text{quantity}_i}{\sum_i \text{quantity}_i}$$

对月度序列拟合线性回归，得到斜率 $k$。

- $k \leq 0$：价格稳定或下降，得分 = 100
- $k > 0$：按全体正斜率供应商的百分位线性映射，最小斜率 → 100，最大斜率 → 0

$$\text{走势得分} = \left(1 - \frac{k - k_{\min}}{k_{\max} - k_{\min}}\right) \times 100 \quad \text{（当 } k > 0\text{）}$$

- 若只有一个月的数据点（无法拟合斜率），视为 $k = 0$，得分 = 100
- 仅使用 `交易成功` 且 `unit_price`、`quantity` 均不为 null 的订单

### 评分标签

| 分数区间 | 标签 | 前端颜色 |
|----------|------|----------|
| 85–100 | 优质供应商 ⭐⭐⭐ | 绿色（green） |
| 65–84 | 稳定合作商 ⭐⭐ | 蓝色（blue） |
| 45–64 | 一般供应商 ⭐ | 黄橙色（yellow/orange） |
| 0–44 | 需关注 ⚠️ | 红色（red） |
| null | 数据不足 | 灰色（gray） |

## Data Model

**无新增数据表**。评估所用字段均来自现有 `PurchaseOrder` 表：

| 字段 | 用途 |
|------|------|
| `seller_name` | 供应商分组键 |
| `status` | 状态过滤及完成率计算 |
| `unit_price` | 价格稳定性、价格走势计算 |
| `quantity` | 价格走势月度加权均价权重 |
| `goods_title` | 价格稳定性分组键；价格走势折线图分组 |
| `created_at` | 活跃度月份统计；价格走势月度聚合 |
| `paid_amount` | 评估页总采购金额展示（仅展示用） |

## API Contract

### GET /api/purchase-orders/evaluation

**描述**: 返回所有供应商的综合评分列表（含各维度分数）。

**查询参数**:

| 参数 | 类型 | 默认值 | 必填 | 说明 |
|------|------|--------|------|------|
| `start_month` | string | null | 否 | 开始月，格式 `YYYY-MM` |
| `end_month` | string | null | 否 | 结束月，格式 `YYYY-MM` |

**响应体**（HTTP 200）:

```json
{
  "suppliers": [
    {
      "seller_name": "供应商A公司",
      "score": 82.5,
      "label": "稳定合作商 ⭐⭐",
      "completion_rate": 91.0,
      "price_stability": 78.3,
      "activity_rate": 75.0,
      "price_trend_score": 100.0,
      "total_amount": 158320.50,
      "order_count": 42
    },
    {
      "seller_name": "供应商B公司",
      "score": null,
      "label": "数据不足",
      "completion_rate": null,
      "price_stability": null,
      "activity_rate": null,
      "price_trend_score": null,
      "total_amount": 3200.00,
      "order_count": 2
    }
  ]
}
```

**响应字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `suppliers` | array | 所有供应商评分列表，按 `score` 降序排列（null 排末尾） |
| `suppliers[].seller_name` | string | 供应商名称 |
| `suppliers[].score` | float \| null | 综合得分（0–100），有效订单 < 3 时为 null |
| `suppliers[].label` | string | 评分标签 |
| `suppliers[].completion_rate` | float \| null | 完成率维度得分（0–100） |
| `suppliers[].price_stability` | float \| null | 价格稳定性维度得分（0–100） |
| `suppliers[].activity_rate` | float \| null | 活跃度维度得分（0–100） |
| `suppliers[].price_trend_score` | float \| null | 价格走势维度得分（0–100） |
| `suppliers[].total_amount` | float | 时间窗口内 `交易成功` 订单的实付款总额（元） |
| `suppliers[].order_count` | integer | 时间窗口内有效订单总数（排除 `等待买家付款`） |

**错误响应**:

| HTTP 状态码 | 场景 |
|-------------|------|
| 200 | 成功（无数据时返回空 `suppliers` 数组） |
| 422 | 月份参数格式不符合 `YYYY-MM` |
| 500 | 数据库查询或计算异常 |

---

### GET /api/purchase-orders/evaluation/{seller_name}

**描述**: 返回单个供应商的详细评分，包含各维度分数及月度价格明细（用于前端雷达图和折线图渲染）。

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `seller_name` | string | 供应商名称（URL 编码） |

**查询参数**:

| 参数 | 类型 | 默认值 | 必填 | 说明 |
|------|------|--------|------|------|
| `start_month` | string | null | 否 | 开始月，格式 `YYYY-MM` |
| `end_month` | string | null | 否 | 结束月，格式 `YYYY-MM` |

**响应体**（HTTP 200）:

```json
{
  "seller_name": "供应商A公司",
  "score": 82.5,
  "label": "稳定合作商 ⭐⭐",
  "dimensions": {
    "completion_rate": 91.0,
    "price_stability": 78.3,
    "activity_rate": 75.0,
    "price_trend_score": 100.0
  },
  "price_history": [
    { "month": "2025-10", "goods_title": "产品A", "avg_unit_price": 25.50 },
    { "month": "2025-11", "goods_title": "产品A", "avg_unit_price": 26.00 },
    { "month": "2025-10", "goods_title": "产品B", "avg_unit_price": 48.00 }
  ]
}
```

**响应字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `seller_name` | string | 供应商名称 |
| `score` | float \| null | 综合得分 |
| `label` | string | 评分标签 |
| `dimensions` | object | 四个维度的具体得分（均为 float \| null） |
| `price_history` | array | 月度加权平均单价明细，每条记录为一个 `(月份, goods_title)` 组合 |
| `price_history[].month` | string | 月份，格式 `YYYY-MM` |
| `price_history[].goods_title` | string | 货品标题 |
| `price_history[].avg_unit_price` | float | 该月该货品的加权平均单价（元） |

**错误响应**:

| HTTP 状态码 | 场景 |
|-------------|------|
| 200 | 成功 |
| 404 | 指定 `seller_name` 在数据库中无任何记录 |
| 422 | 月份参数格式错误 |
| 500 | 数据库查询或计算异常 |

---

## User Scenarios & Testing

### User Story 1 - 查看供应商综合评分排行榜 (Priority: P1)

作为运营管理人员，我希望通过一张评分表格快速看到所有供应商的综合得分和评级，以便识别核心可靠供应商与需要跟进的供应商。

**Why this priority**: 评分列表是整个评估看板的核心视图，决定后续所有操作的入口。

**Independent Test**: 在有超过 5 家供应商、各供应商有不同数量采购记录的数据集上，访问 `/suppliers/evaluation`，确认评分表格渲染正常，包含综合得分、评分徽章（带颜色）、各维度得分列，并按综合得分降序排列。

**Acceptance Scenarios**:

1. **Given** 数据库中有多家供应商且各有不同数量的有效订单，**When** 用户访问 `/suppliers/evaluation`，**Then** 页面展示评分表格，包含排名、供应商名、综合得分（带颜色徽章）、标签、完成率、价格稳定性、活跃度、价格走势方向指示符、总采购金额和"查看详情"按钮。
2. **Given** 某供应商有效订单数 < 3，**When** 评估页加载，**Then** 该供应商的得分显示为"数据不足"，徽章为灰色，维度得分列显示"--"或空。
3. **Given** 评分表格已渲染，**When** 用户选择不同的月份范围并点击查询，**Then** 评分数据根据所选时间窗口重新计算并刷新表格。

---

### User Story 2 - 查看供应商雷达图维度分析 (Priority: P1)

作为运营管理人员，我希望点击某供应商的"查看详情"后，通过雷达图直观看到四个维度的得分分布，以便快速理解该供应商评分高低的原因。

**Why this priority**: 雷达图是评分可解释性的核心；没有维度分解，用户无法理解综合分的来源。

**Independent Test**: 在有足够数据的供应商行上点击"查看详情"，确认行下方展开区域出现 ECharts 雷达图，雷达图四个轴分别标注"完成率"、"价格稳定性"、"活跃度"、"价格走势"，数值与 API 返回的维度得分一致。

**Acceptance Scenarios**:

1. **Given** 评分表格已加载，**When** 用户点击某行的"查看详情"按钮，**Then** 该行下方内联展开详情区域，显示 ECharts 雷达图（四轴：完成率、价格稳定性、活跃度、价格走势）和价格趋势折线图。
2. **Given** 详情区域已展开，**When** 用户再次点击同一行的"收起"按钮，**Then** 详情区域折叠，表格恢复正常行高。
3. **Given** 用户依次点击多行的"查看详情"，**When** 两行同时处于展开状态，**Then** 两个详情区域均正常渲染，互不干扰。

---

### User Story 3 - 查看月度单价走势折线图 (Priority: P2)

作为运营管理人员，我希望在供应商详情区域看到各货品的月度加权平均单价折线图，以便识别哪些货品价格持续上涨，从而优先就这些货品进行价格谈判。

**Why this priority**: 折线图提供价格走势的直观证据，是对走势维度得分的可视化解释。

**Independent Test**: 展开某供应商详情，确认折线图包含多条折线（每条对应一个 `goods_title`），X 轴为月份（升序），Y 轴为加权平均单价，鼠标悬停时 tooltip 显示月份、货品名和价格。

**Acceptance Scenarios**:

1. **Given** 某供应商有多个不同 `goods_title` 的采购记录，**When** 详情区域展开，**Then** 价格趋势折线图渲染多条折线（每条对应一个货品），X 轴显示月份，Y 轴显示加权平均单价（元）。
2. **Given** 某供应商只有一种 `goods_title`，**When** 详情展开，**Then** 折线图渲染单条折线，正常显示不报错。
3. **Given** 折线图已渲染，**When** 用户将鼠标悬停在某数据点上，**Then** tooltip 显示该月份、货品名称和加权平均单价。

---

### Edge Cases

- **无数据时**：数据库中无任何采购记录，`/api/purchase-orders/evaluation` 返回 `{ "suppliers": [] }`，前端显示"暂无供应商数据"，不崩溃。
- **所有供应商数据不足**：全部供应商有效订单数均 < 3，评分表格全部显示"数据不足"灰色徽章。
- **单月数据**：时间窗口内仅有一个月的订单，活跃度得分 = 100，价格走势无法拟合斜率，视为 k=0 得分 = 100。
- **单一货品**：供应商只采购一种货品，价格稳定性只计算该货品的 CV；折线图只渲染一条线。
- **unit_price 为 null**：采购记录中 `unit_price` 字段为空，该条记录不纳入价格稳定性和价格走势计算，但仍纳入完成率和活跃度计算。
- **seller_name 含特殊字符**：供应商名含斜杠、空格等特殊字符时，API 路径参数需正确 URL 编码，后端正常解析。
- **并发请求**：多用户同时请求评估接口，每次返回一致结果，无竞争条件。

## Requirements

### Functional Requirements

- **FR-E001**: 系统必须在 `/suppliers/evaluation` 路由下提供独立的评估页面，可通过 Vue Router 直接访问。
- **FR-E002**: `SupplierDashboard.vue` 头部必须新增"供应商评估"导航按钮，点击后跳转至 `/suppliers/evaluation`。
- **FR-E003**: 系统必须提供 `GET /api/purchase-orders/evaluation` 接口，返回所有供应商的综合评分和四维度得分，按综合得分降序排列（null 排末尾）。
- **FR-E004**: 系统必须提供 `GET /api/purchase-orders/evaluation/{seller_name}` 接口，返回单个供应商的评分详情及月度价格明细。
- **FR-E005**: 评估接口计算时必须排除 `等待买家付款`、`退款中`、`交易关闭` 三种状态的订单（完成率分母除外，见上方状态排除规则说明）。
- **FR-E006**: 综合评分公式必须为：`完成率×0.35 + 价格稳定性×0.30 + 活跃度×0.20 + 价格走势×0.15`。
- **FR-E007**: 有效订单数（排除 `等待买家付款` 后）< 3 的供应商，`score` 必须返回 null，标签返回"数据不足"，维度得分均返回 null。
- **FR-E008**: 评估页必须渲染供应商评分表格，包含列：排名、供应商名、综合得分（带颜色徽章）、标签、完成率得分、价格稳定性得分、活跃度得分、价格走势指示符（↑↓→）、总采购金额、"查看详情"按钮。
- **FR-E009**: 点击"查看详情"后，必须在该行下方内联展开详情区域，包含 ECharts 雷达图（四个维度轴）和 ECharts 价格趋势折线图（按 `goods_title` 分组的月度加权均价）。
- **FR-E010**: 评估页必须提供月份范围过滤器（`start_month` / `end_month`），与 `SupplierDashboard.vue` 相同的交互模式；默认不传参时展示全量历史。
- **FR-E011**: 价格走势指示符规则：维度得分 ≥ 70 显示"→"或"↓"（稳定/下降），得分 < 70 显示"↑"（价格上涨）。
- **FR-E012**: 当 `GET /api/purchase-orders/evaluation/{seller_name}` 的 `seller_name` 在数据库中不存在时，接口必须返回 HTTP 404。
- **FR-E013**: 接口必须支持 `start_month` 和 `end_month` 参数（格式 `YYYY-MM`）；不传参时默认使用数据库全量历史数据计算。

### Non-Functional Requirements

- **NFR-E001 性能**: 在 PurchaseOrder 表不超过 50,000 条记录的情况下，`/api/purchase-orders/evaluation` 接口响应时间不超过 5 秒。
- **NFR-E002 可维护性**: `SupplierEvaluation.vue` 组件与 `SupplierDashboard.vue`、`SupplierManagement.vue` 保持独立，互不耦合；评分计算逻辑集中在后端接口中，不分散到前端。
- **NFR-E003 无新依赖**: 后端不引入 `scipy`、`numpy` 等外部科学计算库；线性回归使用 Python 内置模块或手写最小二乘公式。
- **NFR-E004 兼容性**: 评估页和图表在 Chrome、Edge 最新版本下正常渲染。
- **NFR-E005 安全性**: `seller_name` 路径参数必须经过 URL 解码后用作 SQL 参数绑定，不允许字符串拼接构造 SQL 语句（防止 SQL 注入）。

## Success Criteria

### Measurable Outcomes

- **SC-E001**: 在有 10 家以上供应商、各有不同订单量的数据集上，`/api/purchase-orders/evaluation` 能在 5 秒内返回正确排序的评分列表。
- **SC-E002**: 综合评分的手工验算（按公式分别计算四维度后加权）与接口返回值之间误差不超过 0.1 分。
- **SC-E003**: 有效订单数 ≥ 3 的供应商全部显示数值得分和对应颜色标签；有效订单数 < 3 的供应商全部显示"数据不足"灰色徽章。
- **SC-E004**: 雷达图四个轴的数值与 `GET /api/purchase-orders/evaluation/{seller_name}` 返回的 `dimensions` 字段数值一致，误差为零。
- **SC-E005**: 折线图的月度数据点与 `price_history` 数组中的 `avg_unit_price` 值一致，精度到小数点后 2 位。
- **SC-E006**: 当 PurchaseOrder 表为空或所有供应商均数据不足时，评估页正常加载（HTTP 200），不抛出 JavaScript 错误。

## Assumptions

- `PurchaseOrder` 表中 `unit_price` 和 `quantity` 字段已在 006 中定义，部分历史记录可能存在 null 值；评分计算在上述字段为 null 时跳过该记录（不报错）。
- 前端已安装 `vue-echarts` 和 `echarts/core`，雷达图（`RadarChart`）和折线图（`LineChart`）组件注册方式与 `OrderDashboard.vue` 一致。
- Vue Router 已配置，可新增路由 `/suppliers/evaluation` 无需修改路由器初始化逻辑。
- 价格走势线性回归百分位映射需要在一次请求中计算全体供应商的斜率，因此 `GET /api/purchase-orders/evaluation` 为批量接口（非逐个计算）；单个供应商详情接口的价格走势得分与批量接口保持一致（独立计算时若只有一个供应商，百分位无意义，slope ≤ 0 → 100，slope > 0 → 0）。
- 本功能不涉及退货率维度（需供应商-商品映射表，超出 P0 范围）。
