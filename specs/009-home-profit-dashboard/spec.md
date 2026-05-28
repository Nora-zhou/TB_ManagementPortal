# Feature Specification: 首页利润分析仪表盘

**Feature Branch**: `009-home-profit-dashboard`

**Created**: 2026-05-27

**Status**: Ready for Planning

## Overview

新增一个首页仪表盘（路由 `/`），以多维度可视化方式展示两家店铺的综合利润概览。页面顶部通过 KPI 指标卡分别展示 1 店、2 店及合计的收入、成本与净利润；下方通过两张 ECharts 图表呈现：① 按月走势折线+柱状混合图（收入 / 成本 / 净利润）；② 成本与利润比例饼图（全周期或指定月份范围）。用户无需手动切换多个页面即可掌握两店整体盈利状况及月度变化趋势。

## 利润计算公式

### 收入（Revenue）

按店铺对 `SubOrder` 表聚合：

```
Store N Revenue = SUM(SubOrder.buyer_paid WHERE status = '交易成功' AND store = N)
               - SUM(CAST(SubOrder.refund_amount AS FLOAT) WHERE status IN ('交易成功', '交易关闭') AND store = N)
```

与现有 `OrderDashboard.vue` / `stats/summary` 端点保持一致的统计口径。

### 成本（Cost）

按店铺对 `PurchaseOrder` 表聚合：

```
Store N Cost = SUM(PurchaseOrder.paid_amount WHERE status NOT IN ('等待买家付款', '退款中', '交易关闭') AND store = N)
```

与现有供应商管理功能的排除规则保持一致。

### 净利润（Net Profit）

```
Store N Profit = Store N Revenue - Store N Cost
Total Profit   = Store 1 Profit + Store 2 Profit
```

## Clarified Decisions

| 决策项 | 结论 |
|--------|------|
| 首页路由 | `/`（取消现有重定向到 `/products`，改为渲染 `HomeDashboard.vue`）；导航栏新增「首页」链接排在最左侧 |
| 时间维度 | 按月聚合（`YYYY-MM`），X 轴为月份字符串 |
| 月份范围筛选 | 页面顶部提供「开始月份」/「结束月份」两个文本输入框（格式 `YYYY-MM`），默认空（不传 = 全量历史）；与 `SupplierDashboard` 筛选控件保持同样交互风格 |
| KPI 指标卡 | 三列两行共 6 张卡片：行一为「1 店」（收入 / 成本 / 利润），行二为「2 店」（收入 / 成本 / 利润），底部汇总行显示合计三项；金额单位：元，保留两位小数，使用千位分隔符 |
| NULL paid_at 处理 | 月度分组使用 `COALESCE(paid_at, created_at)`；两张表均适用 |
| 图表一：走势图 | ECharts 折线+柱状**双 Y 轴**混合图；X 轴为月份；**左 Y 轴**绑定三条折线：「总收入」「总成本」「净利润」；**右 Y 轴**绑定分店柱状系列：「1 店利润柱」「2 店利润柱」；鼠标悬停 tooltip；底部带 legend（可点击隐藏/显示） |
| 图表二：比例图 | ECharts 饼图（环形 donut）；三个扇区：**净利润 / 总成本 / 退款**（三者之和隐含总收入，不额外显示总收入标签）；若净利润 ≤ 0，将其**截为 0**（不显示该扇区），仅展示成本与退款 |
| 图表库 | 使用已安装的 ECharts（vue-echarts + echarts/core），与现有 `OrderDashboard.vue` 和 `SupplierDashboard.vue` 保持一致 |
| 图表高度 | 走势图不低于 400px；比例图不低于 350px |
| 数据加载 | 组件挂载（`onMounted`）时调用一次；月份筛选变更后重新请求；显示 loading 状态；接口出错时显示错误提示 |
| 空数据处理 | 若无数据（两张表均为空），各 KPI 卡显示 `0.00`，图表显示空状态提示 |
| 响应式布局 | 单列垂直排列（KPI 卡行 → 走势图 → 比例图）；KPI 卡采用 CSS Grid 均分 |
| API 兼容性 | 新增单独接口 `/api/stats/profit-monthly`，不修改现有接口 |

## User Stories

### US-1：首页利润概览

**As a** 店主，  
**I want to** 打开应用直接看到两店合计及分店利润摘要，  
**So that** 我无需进入多个分析页面即可掌握整体盈利状况。

**Acceptance Criteria:**
- 打开 `/` 路由，页面展示 HomeDashboard 组件（不再重定向到 `/products`）
- 页面顶部显示 6 张 KPI 卡：1 店收入 / 1 店成本 / 1 店利润 / 2 店收入 / 2 店成本 / 2 店利润
- 底部汇总行显示合计收入 / 合计成本 / 合计净利润
- 金额格式：保留两位小数 + 千位分隔符（如 `12,345.67`）

### US-2：月度利润走势图

**As a** 店主，  
**I want to** 查看按月展示的收入、成本、净利润走势，  
**So that** 我能直观了解利润随时间的变化趋势。

**Acceptance Criteria:**
- 页面下方展示 ECharts 混合图（折线 + 柱状）
- X 轴为月份（格式 `YYYY-MM`），按时间升序排列
- 三条折线：「总收入」「总成本」「净利润」
- 两组柱状（可通过 legend 开关）：「1 店利润」「2 店利润」
- tooltip 悬停显示当月所有系列值
- 底部 legend 可单独点击隐藏/显示各系列

### US-3：月份范围筛选

**As a** 店主，  
**I want to** 限定分析的月份范围，  
**So that** 我能查看特定时段（如本季度）的利润表现。

**Acceptance Criteria:**
- 页面顶部提供「开始月份」「结束月份」输入框（YYYY-MM 格式）
- 修改任一输入框后，KPI 卡和两张图表同步刷新
- 清空输入框恢复全量历史数据
- 输入非法格式时忽略（不发起请求，保留上次数据）

### US-4：成本与利润比例图

**As a** 店主，  
**I want to** 以比例图查看成本、利润、退款占收入的比重，  
**So that** 我能快速判断盈利健康度。

**Acceptance Criteria:**
- 展示 ECharts 环形饼图，三个扇区：净利润 / 总成本 / 退款
- 扇区百分比标签显示在图内或 tooltip 中
- 若净利润 ≤ 0，将「净利润」扇区改为「亏损」并使用红色
- 应用当前月份筛选范围

## Data Model

**无新增数据表**。本功能仅在现有 `SubOrder` 和 `PurchaseOrder` 表上执行聚合查询。

### 查询逻辑说明

后端接口对两张表分别执行：

**收入聚合（SubOrder）**：
1. 按 `store` + `strftime('%Y-%m', COALESCE(paid_at, created_at))` 分组
2. 收入：`SUM(buyer_paid)` WHERE `status = '交易成功'`
3. 退款：`SUM(CAST(refund_amount AS FLOAT))` WHERE `status IN ('交易成功', '交易关闭')`
4. 净收入 = 收入 - 退款

**成本聚合（PurchaseOrder）**：
1. 按 `store` + `strftime('%Y-%m', COALESCE(paid_at, created_at))` 分组
2. 成本：`SUM(paid_amount)` WHERE `status NOT IN ('等待买家付款', '退款中', '交易关闭')`

**合并逻辑**：
- 两张表的月份集合取并集作为 X 轴
- 缺失月份对应值补 0

## API Contract

### GET /api/stats/profit-monthly

**描述**: 返回按月、按店铺分组的收入/成本/利润数据，以及汇总 KPI。

**查询参数**:

| 参数 | 类型 | 默认值 | 必填 | 说明 |
|------|------|--------|------|------|
| `start_month` | string | null | 否 | 开始月，格式 `YYYY-MM`；不传时包含全部历史 |
| `end_month` | string | null | 否 | 结束月，格式 `YYYY-MM`；不传时包含全部历史 |

**响应体**（HTTP 200）:

```json
{
  "months": ["2026-01", "2026-02", "2026-03"],
  "series": {
    "revenue_s1":   [12345.67, 9800.00, 11200.50],
    "revenue_s2":   [8000.00,  7500.00, 9100.00],
    "cost_s1":      [7000.00,  6200.00, 6800.00],
    "cost_s2":      [4500.00,  4100.00, 5000.00],
    "refund_s1":    [300.00,   150.00,  200.00],
    "refund_s2":    [100.00,   80.00,   120.00],
    "profit_s1":    [5045.67,  3450.00, 4200.50],
    "profit_s2":    [3400.00,  3320.00, 3980.00],
    "total_revenue":[20345.67, 17300.00, 20300.50],
    "total_cost":   [11500.00, 10300.00, 11800.00],
    "total_refund": [400.00,   230.00,  320.00],
    "total_profit": [8445.67,  6770.00, 8180.50]
  },
  "kpi": {
    "revenue_s1":    33346.17,
    "revenue_s2":    24600.00,
    "cost_s1":       20000.00,
    "cost_s2":       13600.00,
    "refund_s1":     650.00,
    "refund_s2":     300.00,
    "profit_s1":     12696.17,
    "profit_s2":     10700.00,
    "total_revenue": 57946.17,
    "total_cost":    33600.00,
    "total_refund":  950.00,
    "total_profit":  23396.17
  }
}
```

**字段说明**:

| 字段 | 说明 |
|------|------|
| `months` | 月份列表，YYYY-MM 格式，升序排列，为两表月份并集 |
| `series.*_s1` | 1 店逐月数据，与 `months` 等长，缺失月份补 0 |
| `series.*_s2` | 2 店逐月数据，与 `months` 等长，缺失月份补 0 |
| `series.total_*` | 两店合计逐月数据 |
| `kpi.*` | 应用月份筛选后的全周期汇总值 |
| `profit_sN` | `revenue_sN - cost_sN`（已扣除退款后的净利润） |

**错误响应**:

| HTTP 状态码 | 说明 |
|-------------|------|
| 422 | `start_month` 或 `end_month` 格式非法（非 `YYYY-MM`） |
| 500 | 数据库查询异常 |

## 受影响模块一览

| 模块 | 变更类型 | 说明 |
|------|---------|------|
| `backend/routes/orders.py` | 修改 | 新增 `GET /api/stats/profit-monthly` 路由 |
| `frontend/src/components/HomeDashboard.vue` | 新增 | 首页仪表盘组件（KPI 卡 + 走势图 + 比例图） |
| `frontend/src/api/orders.js` | 修改 | 新增 `fetchProfitMonthly(startMonth, endMonth)` 函数 |
| `frontend/src/main.js` | 修改 | 将 `/` 路由从 redirect 改为渲染 `HomeDashboard.vue`；引入组件 |
| `frontend/src/App.vue` | 修改 | 导航栏新增「首页」链接（排在最左侧），指向 `/` |
