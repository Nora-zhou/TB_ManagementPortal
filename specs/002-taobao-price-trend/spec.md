# Feature Specification: 淘宝店铺商品价格走势平台

**Feature Branch**: `002-taobao-price-trend`

**Created**: 2026-05-25

**Status**: Draft

## Overview

为淘宝店铺卖家提供一个可视化平台，用于导入自己店铺中的商品信息，并通过定期记录价格快照来追踪每件商品的历史价格走势。用户可以在平台上浏览商品列表、查看价格折线图，并设置价格预警阈值。本功能基于现有 FastAPI + Vue 3 技术栈实现。

## Clarified Decisions

| 决策项 | 结论 |
|--------|------|
| 快照价格来源 | 实时调用淘宝开放平台 API 拉取最新价格 |
| 用户认证 | 单用户本地工具，无需登录认证 |
| MVP 导入方式 | CSV 上传 + 淘宝 API Token 两种方式均在 MVP 中实现 |
| CSV 必填字段 | 4 个字段：商品 ID、商品名称、价格、商品 URL |
| 快照历史保留策略 | 每件商品保留最近 365 条快照（约 1 年），超出后自动删除最旧记录 |

## User Scenarios & Testing

### User Story 1 - 导入店铺商品目录 (Priority: P1)

As a user, I can import my Taobao store's product catalog into the platform so I have products to track.

**Why this priority**: 没有商品数据，平台无法运行，是所有后续功能的前提。

**Independent Test**: 通过上传包含商品 ID、名称、价格、商品 URL 四个字段的 CSV 文件或输入淘宝开放平台 Token，成功导入商品列表，确认商品出现在商品列表页。

**Acceptance Scenarios**:

1. **Given** 我在导入页面，**When** 我上传符合格式的 CSV 文件并点击"导入"，**Then** 系统解析文件并将商品写入数据库，跳转至商品列表页，显示导入的商品数量。
2. **Given** 我在导入页面，**When** 我输入有效的淘宝开放平台 Token 并点击"连接"，**Then** 系统通过 API 拉取店铺商品列表并写入数据库。
3. **Given** 已有商品数据，**When** 我重新导入相同商品（以商品 ID 去重），**Then** 系统更新已有商品信息，不产生重复记录。

---

### User Story 2 - 查看商品列表 (Priority: P1)

As a user, I can view all imported products with their current price and last-updated timestamp.

**Why this priority**: 商品列表是平台的核心入口，用户需要从这里了解全局价格概况并导航至单品详情。

**Independent Test**: 导入商品后，打开商品列表页，确认每条记录显示商品名称、当前价格和最近更新时间。

**Acceptance Scenarios**:

1. **Given** 已导入商品，**When** 我打开商品列表页，**Then** 我看到包含商品名称、当前价格、最近更新时间的列表，默认按最近更新时间降序排列。
2. **Given** 商品数量超过 20 条，**When** 我浏览列表，**Then** 列表分页显示，每页最多 20 条，并提供翻页控件。
3. **Given** 没有任何商品，**When** 我打开商品列表页，**Then** 显示空状态提示"暂无商品，请先导入商品目录"。

---

### User Story 3 - 查看单品价格走势图 (Priority: P1)

As a user, I can click on a product and see a line chart showing its price history over time.

**Why this priority**: 价格走势可视化是本平台的核心价值，是用户使用该平台的主要目的。

**Independent Test**: 点击一件有多条价格记录的商品，确认页面显示折线图，X 轴为时间，Y 轴为价格，各数据点准确对应历史快照。

**Acceptance Scenarios**:

1. **Given** 某商品有 2 条及以上价格快照，**When** 我点击该商品，**Then** 进入详情页并显示价格折线图，X 轴为快照时间，Y 轴为价格（元）。
2. **Given** 折线图已显示，**When** 我将鼠标悬停在某数据点，**Then** 显示该时间点的具体价格和记录时间的 Tooltip。
3. **Given** 某商品仅有 1 条价格快照，**When** 我点击该商品，**Then** 不显示折线图，改为提示"价格历史数据不足，请等待更多快照记录后再查看走势"。

---

### User Story 4 - 记录价格快照 (Priority: P2)

As a user, I can manually trigger a price snapshot recording so the system captures the current price of all products at that moment.

**Why this priority**: 价格快照是走势图的数据来源；手动触发满足 MVP 需求，后续可扩展为定时任务。

**Independent Test**: 点击"立即记录快照"按钮，等待完成后，进入任意商品详情页，确认新增了一条当前时间的价格记录（价格来自淘宝开放平台 API 实时拉取）。

**Acceptance Scenarios**:

1. **Given** 商品列表页已加载，**When** 我点击"立即记录快照"，**Then** 系统实时调用淘宝开放平台 API 获取每件商品的最新价格，记录价格和当前时间戳，操作完成后显示"快照记录成功，共更新 N 件商品"。
2. **Given** 快照记录进行中，**When** 我再次点击"立即记录快照"，**Then** 按钮置灰并提示"记录中，请稍候"，防止重复提交。
3. **Given** 快照记录完成，**When** 我查看商品走势图，**Then** 新快照数据点出现在折线图最右侧。

---

### User Story 5 - 搜索与筛选商品 (Priority: P2)

As a user, I can search products by name or filter by price range to quickly locate specific items.

**Why this priority**: 当商品数量较多时，搜索和筛选是提升效率的关键，减少用户在列表中滚动查找的时间。

**Independent Test**: 在搜索框输入商品名称关键词，确认列表实时过滤；设置价格范围后，确认列表只显示符合条件的商品。

**Acceptance Scenarios**:

1. **Given** 商品列表已加载，**When** 我在搜索框输入关键词，**Then** 列表实时过滤，只显示商品名称包含该关键词的商品（大小写不敏感）。
2. **Given** 商品列表已加载，**When** 我设置最低价和最高价并点击"筛选"，**Then** 列表只显示当前价格在该范围内的商品。
3. **Given** 搜索或筛选结果为空，**When** 无匹配商品，**Then** 显示"未找到符合条件的商品"提示，并提供"清除筛选"按钮。

---

### User Story 6 - 设置价格预警阈值 (Priority: P3)

As a user, I can set a price alert threshold for a product and see a visual indicator when the price goes below or above it.

**Why this priority**: 价格预警是锦上添花的功能，帮助用户主动感知价格异动，但不影响核心走势查看流程。

**Independent Test**: 为某商品设置上限和下限阈值，手动记录一次超出范围的价格快照，确认列表和详情页出现视觉预警标识。

**Acceptance Scenarios**:

1. **Given** 我在商品详情页，**When** 我输入价格下限和/或上限并保存，**Then** 阈值保存成功，折线图上显示对应的水平参考线。
2. **Given** 已设置价格下限，**When** 最新快照价格低于下限，**Then** 商品列表中该商品行显示"价格下跌预警"红色标识，详情页折线图中超出范围的数据点高亮显示。
3. **Given** 已设置价格上限，**When** 最新快照价格高于上限，**Then** 商品列表中该商品行显示"价格上涨预警"橙色标识。
4. **Given** 已设置阈值，**When** 我删除阈值并保存，**Then** 参考线和预警标识消失，恢复正常显示。

---

### Edge Cases

- 某商品仅有 1 条价格快照时：不显示折线图，显示提示信息"价格历史数据不足，请等待更多快照记录后再查看走势"。
- CSV 格式不符合要求或含有解析错误：显示具体错误提示（例如"第 3 行缺少价格字段"），导入中止，数据库不写入任何数据。
- 淘宝开放平台 API 连接失败或 Token 无效：显示"连接失败，请检查 Token 是否正确或网络是否正常"，不影响已有本地数据。
- 商品当前无价格数据（导入时价格字段为空）：在商品列表中显示"暂无价格数据"，详情页不显示折线图。
- 商品目录超过 1000 条：列表分页展示，每页 20 条，确保页面加载不阻塞；快照记录操作需提示预计耗时。
- 某商品快照数量达到 365 条上限：新增快照时自动删除最旧的一条，保持总数不超过 365 条。
