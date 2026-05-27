# Feature Specification: 订单数据分析平台

**Feature Branch**: `003-order-analytics`

**Created**: 2026-05-25

**Status**: Draft

## Overview

基于淘宝导出订单列表（ExportOrderList xlsx 文件），为店主提供订单数据导入、列表浏览与多维度经营分析的可视化平台。用户上传 xlsx 文件后，可查看按月/周/日的销售走势、订单状态分布、退款率分析及热销商品排行。本功能基于现有 FastAPI + Vue 3 技术栈新增独立模块，不影响已有商品价格走势功能。

## Data Source

ExportOrderList xlsx 文件字段（来自淘宝导出格式）：

| 字段名 | 说明 | 示例 |
|--------|------|------|
| 订单编号 | 唯一主键 | `3304355160546003165` |
| 支付单号 | 支付平台流水号 | `2026052523001169541433654549` |
| 支付详情 | 支付方式与金额描述 | `支付方式：支付宝，金额：0.00；` |
| 总金额 | 商品定价总额（元） | `38.90` |
| 买家实付金额 | 买家实际支付（优惠后） | `32.71` |
| 订单状态 | 交易成功/交易关闭/卖家已发货等 | `交易成功` |
| 订单创建时间 | 格式 `YYYY-MM-DD HH:MM:SS` | `2026-05-25 17:14:23` |
| 商品标题 | 商品标题，多商品用逗号分隔 | `S925纯银山鬼内凹隔片...` |
| 卖家服务费 | 平台收取服务费（元） | `0.00` |
| 退款金额 | 已退款金额（元） | `32.23` |

## Clarified Decisions

| 决策项 | 结论 |
|--------|------|
| 文件格式 | 支持 .xlsx（淘宝标准导出格式）；不支持 .csv |
| 去重策略 | 以「订单编号」为唯一键，重复导入时更新已有记录 |
| 多商品标题 | 商品标题含逗号时，按逗号分割后各自作为独立商品标题统计 |
| 统计口径 | 销售额统计仅计「交易成功」状态；退款额统计所有状态 |
| 数据留存 | 无上限，全量保留所有导入的历史订单 |
| 时区 | 订单时间按文件原始时间存储，不做时区转换（默认 CST） |

## User Scenarios & Testing

### User Story 1 - 导入订单文件 (Priority: P1)

As a user, I can upload a Taobao ExportOrderList xlsx file to import all orders into the platform.

**Why this priority**: 没有订单数据，所有分析功能无法运行，是所有后续功能的前提。

**Independent Test**: 上传 ExportOrderList26500483109.xlsx，等待导入完成，确认页面显示「导入 1756 条订单，更新 0 条」。

**Acceptance Scenarios**:

1. **Given** 我在导入页面，**When** 我上传符合格式的 xlsx 文件并点击"导入"，**Then** 系统解析文件并将订单写入数据库，返回 `{imported, updated, skipped}`。
2. **Given** 我重新上传包含相同订单编号的文件，**When** 导入完成，**Then** 重复订单被更新而非重复插入，`updated` 计数增加。
3. **Given** 上传的文件缺少「订单编号」或「订单创建时间」列，**When** 我点击导入，**Then** 系统返回 422 错误，提示缺失字段名称。
4. **Given** 文件行数超过 5000 条，**When** 导入时，**Then** 前端显示进度条，后端流式返回进度。

---

### User Story 2 - 查看订单列表 (Priority: P1)

As a user, I can browse all imported orders with filtering by status, date range, and keyword search.

**Why this priority**: 订单列表是基础数据视图，用于核对数据完整性和查找特定订单。

**Independent Test**: 导入订单后，打开列表页，使用状态筛选「交易成功」，确认只显示成功订单；再按关键词「S925」搜索，确认只显示标题含该词的订单。

**Acceptance Scenarios**:

1. **Given** 已导入订单，**When** 我打开订单列表页，**Then** 看到分页列表，每页 20 条，展示订单编号、商品标题（截断至 40 字）、实付金额、订单状态、创建时间。
2. **Given** 列表页已加载，**When** 我选择状态筛选「交易成功」，**Then** 列表仅显示状态为「交易成功」的订单。
3. **Given** 列表页已加载，**When** 我在搜索框输入关键词，**Then** 列表仅显示商品标题包含该关键词的订单，输入 300ms 防抖。
4. **Given** 列表页已加载，**When** 我选择日期范围（开始日期 ~ 结束日期），**Then** 列表仅显示该时间段内创建的订单。

---

### User Story 3 - 查看销售走势图 (Priority: P1)

As a user, I can view a daily/weekly/monthly revenue trend chart to understand business growth.

**Why this priority**: 销售走势是店主最核心的分析需求，直接反映经营健康度。

**Independent Test**: 打开分析仪表盘，切换到「月度」维度，确认折线图显示 2025-09 至 2026-05 的 9 个月数据点，且 2026-04 对应最高峰（约 21,039 元）。

**Acceptance Scenarios**:

1. **Given** 已有订单数据，**When** 我打开分析仪表盘，**Then** 默认显示近 30 天的每日销售额折线图（仅计「交易成功」订单的买家实付金额）。
2. **Given** 走势图已显示，**When** 我切换维度至「周」或「月」，**Then** 图表聚合数据并刷新，X 轴显示对应的周/月标签。
3. **Given** 走势图已显示，**When** 我将鼠标悬停在某数据点，**Then** Tooltip 显示该时段的总销售额、订单数、平均客单价。
4. **Given** 筛选后无数据，**When** 图表更新，**Then** 显示空状态提示"所选时间范围内暂无成功订单"。

---

### User Story 4 - 查看订单状态分布 (Priority: P2)

As a user, I can see a pie chart showing the distribution of order statuses to understand conversion rates.

**Why this priority**: 状态分布揭示转化率和关闭率，是优化运营的关键指标。

**Independent Test**: 打开分析仪表盘，确认饼图显示 6 种状态，「交易成功」占比最大（约 65%），「交易关闭」其次（约 29%）。

**Acceptance Scenarios**:

1. **Given** 已有订单数据，**When** 我查看状态分布饼图，**Then** 图表显示所有状态的订单数量及占比，悬停显示具体数字。
2. **Given** 饼图显示，**When** 我点击某个状态分区，**Then** 订单列表自动按该状态筛选。

---

### User Story 5 - 查看退款分析 (Priority: P2)

As a user, I can view refund amount trends and refund rate to monitor after-sales health.

**Why this priority**: 退款率是客户满意度的重要指标，店主需要及时发现异常波动。

**Independent Test**: 打开分析仪表盘，确认退款卡片显示总退款额 27,906.76 元，退款率（退款额/总实付额）约 28.9%。

**Acceptance Scenarios**:

1. **Given** 已有订单数据，**When** 我查看退款卡片，**Then** 显示总退款额（元）和退款率（退款额 ÷ 买家实付总额 × 100%）。
2. **Given** 已有数据，**When** 我查看退款走势图，**Then** 按月显示退款额折线，与销售额折线对比显示在同一图表中。

---

### User Story 6 - 查看热销商品排行 (Priority: P3)

As a user, I can see a top-10 products ranking by revenue or order count to identify best sellers.

**Why this priority**: 热销商品分析帮助店主优化选品和备货策略。

**Independent Test**: 打开排行榜，确认「超薄S925纯银镀24K金隔片」排在第一位，收入约 10,708 元。

**Acceptance Scenarios**:

1. **Given** 已有「交易成功」订单，**When** 我查看热销商品排行，**Then** 显示 Top 10 商品，按买家实付金额降序，展示商品标题、订单数、总销售额。
2. **Given** 排行榜显示，**When** 我切换排序维度为「订单数」，**Then** 排行按订单数量重新排序。

---

## Out of Scope

- 订单明细的子商品拆分（多件商品在同一订单中的逐件分析）
- 与淘宝开放平台 API 实时同步订单（仅支持手动上传文件）
- 买家维度分析（支付单号不含买家信息）
- 多店铺数据合并（当前版本仅支持单次导入的单一数据集）
