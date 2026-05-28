# Feature Specification: 商品单品毛利率分析

**Feature Branch**: `010-product-profit-analysis`

**Created**: 2026-05-28

**Status**: Draft

## Clarification Decisions (2026-05-28)

| # | 问题 | 决策 |
|---|------|------|
| Q1 | 月度走势图时间范围 | **B** — 最近 12 个自然月（滚动窗口） |
| Q2 | 成本未设置时的显示 | **A** — 显示"未设置"占位，隐藏毛利率数值 |
| Q3 | 多规格 SKU 成本录入 | **B** — SKU 级别分别录入，需新增 `ProductSKUCost` 数据模型 |
| Q4 | 警告色阈值 | **B** — 双阈值：毛利率 < 10% 标橙，< 0% 标红 |
| Q5 | 采购成本来源 | **B** — 提供「从采购单推算均价」辅助按钮，用户确认后填入 |

## Overview

在商品详情页中新增「利润分析」区块，将淘宝子订单的实际销售数据与每件商品的 1688 采购成本打通，计算单品毛利率。用户可在商品详情页设置或更新该商品的 1688 采购均价，系统据此自动计算：已销售数量、总销售额、总成本、毛利润及毛利率，并展示月度毛利走势图，帮助识别高利润商品与高风险（低利润/亏损）商品。

## 利润计算公式

- **销售额（Revenue）** = SUM(SubOrder.buyer_paid WHERE taobao_item_id = X AND status = '交易成功') − SUM(CAST(SubOrder.refund_amount AS FLOAT) WHERE taobao_item_id = X AND status IN ('交易成功', '交易关闭'))
- **已销数量（Units Sold）** = SUM(SubOrder.quantity WHERE taobao_item_id = X AND status = '交易成功')
- **总成本（Cost）** = Units Sold × Purchase Cost Per Unit
- **毛利润（Gross Profit）** = Revenue − Cost
- **毛利率（Gross Margin %）** = Gross Profit / Revenue × 100%

> 与现有 `stats/summary` 统计口径保持一致：销售额仅计「交易成功」；退款额统计「交易成功」和「交易关闭」两种状态。

---

## User Scenarios & Testing

### User Story 1 — 设置商品采购成本并查看利润指标 (Priority: P1)

运营人员在商品详情页中看到「采购成本（元/件）」输入字段，填入该商品在 1688 上的采购均价后保存。系统立即展示 KPI 指标卡，包括：已销数量、总销售额、总成本、毛利润和毛利率。

**Why this priority**: 这是整个功能的核心交互——没有成本录入，毛利率无从计算。

**Independent Test**: 在商品详情页输入采购成本后点击保存，验证 KPI 指标卡显示正确的计算结果（可用已知数据手动验证）。

**Acceptance Scenarios**:

1. **Given** 商品详情页已加载，**When** 用户在「采购成本」字段输入 `25.00` 并点击保存，**Then** 系统保存该值并展示基于此成本计算的毛利率指标卡
2. **Given** 已设置采购成本，**When** 用户修改采购成本为新值并保存，**Then** 所有 KPI 指标立即以新成本重新计算
3. **Given** 该商品尚无任何交易成功的子订单，**When** 采购成本已设置，**Then** KPI 卡展示已销数量 0、销售额 ¥0.00、毛利率显示 "—"（无法计算）
4. **Given** 采购成本为 0 或未设置，**Then** 毛利率区块显示提示语「请先设置采购成本以启用利润分析」

---

### User Story 2 — 查看月度毛利走势 (Priority: P2)

运营人员在商品详情页利润区块中，通过月度柱状图了解该商品逐月的毛利润变化，识别利润高峰与低谷月份。

**Why this priority**: 月度走势比单一汇总数字更能揭示商品利润的时间分布规律，支持营销与采购决策。

**Independent Test**: 对有多个月度销售记录的商品设置采购成本后，验证月度柱状图中各月毛利润值与手动计算一致。

**Acceptance Scenarios**:

1. **Given** 商品已设置采购成本且有跨月的历史子订单，**When** 用户查看商品详情页，**Then** 月度毛利柱状图展示各月份的毛利润（元），X 轴为 YYYY-MM 格式
2. **Given** 某月退款导致净收入为负，**When** 图表渲染，**Then** 该月柱体以不同颜色（如红色）显示，直观提示亏损月份
3. **Given** 采购成本未设置，**When** 用户查看月度图表区域，**Then** 图表区域以占位提示代替（不渲染空图）

---

### User Story 3 — 商品列表快速识别高/低利润商品 (Priority: P3)

运营人员在商品列表页中，通过利润率列快速比较各商品的毛利率，无需逐一进入详情页。

**Why this priority**: 扩展商品列表的信息密度，让运营人员可以快速排序和筛选高/低利润商品，但不影响核心功能。

**Independent Test**: 在商品列表页验证已设置采购成本的商品显示毛利率列，未设置的显示 "—"。

**Acceptance Scenarios**:

1. **Given** 商品列表页，**When** 页面加载，**Then** 列表新增「毛利率」列，已设置成本且有销售记录的商品显示百分比（如 `35.2%`），其余显示 `—`
2. **Given** 商品列表，**When** 用户点击「毛利率」列表头，**Then** 列表按毛利率降序/升序排序（已设置成本优先排列）

---

### Edge Cases

- 采购成本设置为 0 时，系统不应进行除零计算，毛利率应显示 "—" 并提示「成本为零无法计算毛利率」
- 某商品存在退款导致净收入为负值时，毛利率显示负百分比，并以红色警告色标注（< 0% 标红，≥ 0% 且 < 10% 标橙）
- `SubOrder.refund_amount` 为字符串型，计算时须转换为浮点数，无效值按 0 处理
- 月度走势图展示最近 12 个自然月（滚动窗口）；缺失某月数据（该月无销售），该月不显示柱体（跳过，而非显示 0 柱）
- 商品同时属于多个店铺分析场景：利润分析默认合计所有店铺（与商品 taobao_item_id 匹配即计入）
- 部分 SKU 存在子订单但无对应 `ProductSKUCost` 记录时：该 SKU 成本按 0 计入，汇总结果须标注 `has_missing_sku_cost = true` 并在前端 KPI 卡显示黄色警告提示
- 「从采购单推算均价」按钮：若无相关采购单数据，按钮应禁用并 tooltip 提示「暂无匹配采购单数据」

---

## Requirements

### Functional Requirements

- **FR-001**: 新增 `ProductSKUCost` 数据模型，字段包含 `taobao_item_id`、`sku_id`（SKU 标识字符串）、`sku_name`（规格描述）、`purchase_cost`（元/件，非负浮点，不可为 null）；同一商品可有多条 SKU 成本记录
- **FR-002**: 商品详情页 MUST 展示 SKU 成本列表，每行显示规格名称与采购成本输入框，允许分别录入/更新后整批保存
- **FR-003**: 后端 MUST 提供接口，基于 `taobao_item_id`，将子订单的 `sku_id` 与 `ProductSKUCost` 匹配，计算并返回该商品的汇总利润指标（销售额、已销数量、加权平均成本、毛利润、毛利率）；未匹配到成本的 SKU 子订单按成本 0 计入，须标注 `has_missing_sku_cost`
- **FR-004**: 后端 MUST 提供接口，返回该商品**最近 12 个自然月**（滚动窗口，以当前月份向前推 12 个月）按月聚合的毛利润数据，用于前端渲染月度走势图
- **FR-005**: 商品详情页 MUST 展示利润 KPI 指标卡（汇总视图）
- **FR-006**: 商品详情页 MUST 展示月度毛利润柱状图（趋势视图，最近 12 个自然月）
- **FR-007**: 当该商品所有 SKU 均未设置成本时，系统 MUST 在利润区块显示「请先设置 SKU 采购成本以启用利润分析」占位提示，隐藏毛利率数值，不渲染空图表
- **FR-008**: 月度图表柱体颜色 MUST 遵循双阈值规则：毛利率 < 0% 标红，≥ 0% 且 < 10% 标橙，≥ 10% 正常色；列表毛利率列同规则着色
- **FR-009**: 商品列表页 MUST 新增「毛利率」列；已设置成本且有销售记录的商品显示百分比（并按 FR-008 着色），未设置成本显示 `—`
- **FR-010**: 商品列表页的「毛利率」列 MUST 支持排序（升序/降序）
- **FR-011**: 商品详情页 SKU 成本录入区域 MUST 提供「从采购单推算均价」辅助按钮；点击后系统根据相关采购单计算 SKU 加权均价，以可编辑预填充形式展示，用户确认后方保存；若无匹配采购单则按钮禁用并显示 tooltip 提示

### Non-functional Requirements

- **NFR-001**: 利润指标接口响应时间不超过 2 秒（基于现有数据规模）
- **NFR-002**: `ProductSKUCost.purchase_cost` 字段仅接受非负数值（≥ 0），后端需校验
- **NFR-003**: SKU 级成本录入的批量保存须在单次 API 请求中完成（upsert），避免多次往返

---

## Key Entities

- **ProductSKUCost**（新数据模型）: `id`、`taobao_item_id`（关联 Product）、`sku_id`（SKU 标识符）、`sku_name`（规格描述，如"颜色:红色;尺寸:M"）、`purchase_cost`（float，非负，元/件）
- **ProductProfitSummary**（新响应模型）: 商品利润汇总——`taobao_item_id`、`units_sold`、`revenue`、`weighted_avg_cost`、`cost`、`gross_profit`、`gross_margin_pct`、`has_missing_sku_cost`（bool，标注是否存在未匹配成本的 SKU）
- **ProductProfitMonthly**（新响应模型）: 月度毛利润数据点——`month`（YYYY-MM）、`units_sold`、`revenue`、`cost`、`gross_profit`、`gross_margin_pct`

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: 运营人员在商品详情页完成采购成本录入到看到毛利率结果的操作流程不超过 30 秒
- **SC-002**: 利润指标卡与月度图表的计算结果与手动核算数据误差在 ±0.01 元以内
- **SC-003**: 商品列表页新增毛利率列后，页面加载时间较原来增加不超过 500 毫秒
- **SC-004**: 亏损商品（毛利率 < 0）在商品列表和详情页均有明确视觉标识，用户无需计算即可识别
- **SC-005**: 商品列表按毛利率排序后，运营人员可在 10 秒内识别出毛利率最高的前 3 件商品

---

## Assumptions

- 采购成本为商品级别（`taobao_item_id`），而非 SKU/规格级别，即同一商品不同规格共用同一采购均价
- `PurchaseOrder` 与 `SubOrder` 之间不存在直接外键关联，成本通过用户手动录入 `Product.purchase_cost` 字段来表达，而非从 1688 订单自动匹配
- 月度利润统计使用 `SubOrder.paid_at`（若为 null 则退 fallback 至 `SubOrder.created_at`），与 009-home-profit-dashboard 保持一致
- 本功能不修改现有 `stats/summary` 接口或 `HomeDashboard` 的计算逻辑
- 前端图表库沿用已安装的 ECharts（vue-echarts + echarts/core），与现有组件保持一致
- 采购成本字段的历史数据迁移（数据库 migration）通过 Alembic 或 SQLModel 自动建表完成，无需手动脚本
