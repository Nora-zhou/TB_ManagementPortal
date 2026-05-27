# Feature Specification: UX 功能增强

**Feature Branch**: `004-ux-enhancements`

**Created**: 2026-05-26

**Status**: Draft

## Overview

本次迭代聚焦于三项用户体验增强：（1）为订单分析仪表盘新增按时间范围筛选功能，使各图表和指标卡可按时段聚焦分析；（2）商品价格走势的导入方式改为读取本地 `data/Goods` 目录下的文件，并支持增量导入（仅追加新增商品，不重复写入已有记录）；（3）将「导入商品」与「导入订单」两个入口合并为统一的「基础数据导入」菜单，降低导航复杂度。

## Clarified Decisions

| 决策项 | 结论 |
|--------|------|
| 时间筛选范围 | 仪表盘提供「近 7 天 / 近 30 天 / 近 90 天 / 按月份选择 / 自定义日期范围」快捷选项 |
| 近 N 天边界计算 | 从**今天 00:00:00** 往前推 N 天（含今天，共 N 天），结束时间为今天 23:59:59 |
| 时间筛选作用域 | 同时作用于销售走势图、状态分布图、退款分析、热销排行 |
| 走势图聚合粒度 | 始终由用户手动切换日/周/月维度；时间筛选不自动改变粒度 |
| Goods 文件格式 | 与现有 CSV 格式保持一致（商品 ID、商品名称、价格、商品 URL），目录路径为后端 `data/Goods/` |
| Goods 导入替代策略 | **完全替代**原有浏览器 CSV 文件上传入口；移除上传按钮，仅保留「从 Goods 目录导入」 |
| 增量导入去重键 | 以「商品 ID」为唯一键；已存在的记录**更新价格和名称**，不产生重复记录（upsert） |
| 合并菜单位置 | 导航栏新增「基础数据导入」一级菜单，原「导入商品」与「导入订单」作为其子页签（Tab） |
| 原有独立入口 | 废弃原导航中独立的「导入商品」和「导入订单」菜单项及其路由，不做重定向 |
| 商品 ID 列显示位置 | 在商品列表表格中新增「商品 ID」列，放置于表格**第一列**（最左侧，其余列顺序不变） |
| 商品标题排序方式 | 前端**本地排序**，点击「商品标题」列表头在升序 → 降序 → 无排序三态间循环切换；不调用任何新的后端接口 |
| 排序初始状态 | 页面加载时默认无排序（保持后端返回的原始顺序），列表头显示双向箭头指示可排序 |

## User Scenarios & Testing

### User Story 1 - 订单分析仪表盘按时间范围筛选 (Priority: P1)

As a user, I can filter the order analytics dashboard by a time range so that all charts and KPI cards reflect data within the selected period.

**Why this priority**: 按时间筛选是分析型仪表盘最基础的交互，没有它用户无法聚焦特定经营周期进行复盘。

**Independent Test**: 打开订单分析仪表盘，选择「近 7 天」，确认销售走势图、状态分布图、退款卡片和热销排行均只反映最近 7 天的数据；切换至「按月份」并选择 2026-04，确认图表数据更新至 2026-04-01 ~ 2026-04-30；切换至「自定义」并选择 2026-01-01 ~ 2026-01-31，确认图表数据更新至该时段。

**Acceptance Scenarios**:

1. **Given** 我在订单分析仪表盘，**When** 页面加载完成，**Then** 默认显示「近 30 天」的快捷选项，所有图表和指标卡按此时段展示数据。
2. **Given** 仪表盘已加载，**When** 我点击「近 7 天 / 近 30 天 / 近 90 天」快捷按钮，**Then** 后端以今天 00:00:00 为基准往前推 N 天（含今天）作为查询范围，所有图表和指标卡立即刷新，被选中按钮高亮；走势图的日/周/月聚合粒度保持用户当前选择不变。
3. **Given** 仪表盘已加载，**When** 我选择「按月份」并在月份选择器中选定某年某月（如 2026-04），**Then** 所有图表和指标卡刷新为该自然月（1日 00:00:00 ~ 月末 23:59:59）的数据，选择器显示已选月份。
4. **Given** 仪表盘已加载，**When** 我选择「自定义」并输入开始日期与结束日期后点击确认，**Then** 所有图表和指标卡刷新至该自定义时段的数据。
5. **Given** 所选时段内无数据，**When** 图表刷新，**Then** 各图表显示空状态提示「所选时间范围内暂无订单数据」，指标卡显示 0 / 0.00。
6. **Given** 自定义时段中开始日期晚于结束日期，**When** 我点击确认，**Then** 前端校验报错「开始日期不能晚于结束日期」，不发起请求。

---

### User Story 2 - 商品价格走势从 data/Goods 目录增量导入 (Priority: P1)

As a user, I can trigger an import from the `data/Goods` directory so that only new products are added without overwriting or duplicating existing records.

**Why this priority**: 现有 CSV 上传交互繁琐，且每次重新导入会覆盖/重复记录；改为目录扫描 + 增量模式可显著降低操作成本与数据风险。

**Independent Test**: 在 `data/Goods/` 目录下放置 goods_batch1.csv（含 5 条商品），点击「从 Goods 目录导入」，确认返回 `{imported: 5, updated: 0}`；再次点击（文件不变），确认返回 `{imported: 0, updated: 5}`；追加 goods_batch2.csv（含 3 条新商品 ID + 2 条已有 ID 但价格不同），再次点击，确认返回 `{imported: 3, updated: 2}`。

**Acceptance Scenarios**:

1. **Given** `data/Goods/` 目录下存在一个或多个 CSV 文件，**When** 我点击「从 Goods 目录导入」按钮，**Then** 后端扫描目录下所有 CSV 文件，对每条记录执行 upsert（以商品 ID 为键：新增写入，已存在则更新价格和名称），返回 `{imported, updated, skipped}` 计数，前端显示导入结果摘要。
2. **Given** 已导入过部分商品，**When** 我再次触发目录导入且文件内容不变，**Then** 所有记录命中 upsert 的「更新」分支（值相同），`updated` 计数反映记录数；若文件新增了商品 ID，则 `imported` 计数增加。
3. **Given** `data/Goods/` 目录为空或不存在 CSV 文件，**When** 我点击导入，**Then** 系统返回提示「Goods 目录下未找到 CSV 文件」，不影响已有数据。
4. **Given** CSV 文件中缺少「商品 ID」必填列，**When** 触发导入，**Then** 跳过该文件并在结果中标注文件名及错误原因，其余合法文件正常处理。

---

### User Story 3 - 合并为「基础数据导入」菜单 (Priority: P2)

As a user, I can access product import and order import from a single "基础数据导入" menu so that the navigation is simpler and more consistent.

**Why this priority**: 随着导入入口增多，独立菜单导致导航过于分散；合并后降低认知负担，同时为未来扩展更多导入类型预留位置。

**Independent Test**: 打开应用，确认导航栏中「导入商品」和「导入订单」独立条目已消失，出现「基础数据导入」菜单；点击后进入含「商品导入」和「订单导入」两个 Tab 的页面；切换 Tab 可分别触发各自的导入功能，且功能与改版前一致。

**Acceptance Scenarios**:

1. **Given** 应用导航栏，**When** 页面加载，**Then** 显示「基础数据导入」菜单项，原独立的「导入商品」和「导入订单」菜单项不再出现。
2. **Given** 点击「基础数据导入」，**When** 页面打开，**Then** 默认选中「商品导入」Tab，显示商品导入表单（含「从 Goods 目录导入」按钮）。
3. **Given** 「基础数据导入」页面已打开，**When** 我切换到「订单导入」Tab，**Then** 显示订单导入表单（xlsx 文件上传），功能与原「导入订单」页面完全一致。
4. **Given** 「基础数据导入」页面已打开，**When** 商品导入完成（成功或失败），**Then** 导入结果摘要显示在商品导入 Tab 内，不影响订单导入 Tab 状态。

---

### User Story 4 - 商品列表显示商品 ID 并支持按标题排序 (Priority: P2)

As a user, I can see the product ID in the product list and sort products by title so that I can quickly locate and compare products.

**Why this priority**: 商品 ID 是与外部系统（如淘宝）对照的关键字段，缺失会导致核对困难；按标题排序是在大量商品中定位记录的基本操作，优先级次于核心数据分析功能。

**Independent Test**: 打开商品列表页，确认表格第一列为「商品 ID」且正确显示各商品的 item_id；点击「商品标题」列表头一次，确认列表按标题升序排列，列表头显示向上箭头；再次点击，确认按降序排列，列表头显示向下箭头；第三次点击，确认恢复原始加载顺序，列表头显示双向箭头。

**Acceptance Scenarios**:

1. **Given** 商品列表已加载，**When** 页面渲染完成，**Then** 表格第一列为「商品 ID」，显示每条商品记录的 item_id 值，其余列（商品标题、价格等）顺序不变。
2. **Given** 商品列表已加载，**When** 页面初次渲染，**Then** 「商品标题」列表头显示双向箭头（表示可排序），列表保持后端返回的原始顺序。
3. **Given** 商品列表已加载，**When** 我点击「商品标题」列表头（第一次），**Then** 列表在前端本地按商品标题升序重新排列，列表头箭头变为向上（升序），无网络请求发出。
4. **Given** 列表当前处于升序状态，**When** 我再次点击「商品标题」列表头，**Then** 列表在前端本地按商品标题降序重新排列，列表头箭头变为向下（降序），无网络请求发出。
5. **Given** 列表当前处于降序状态，**When** 我再次点击「商品标题」列表头，**Then** 列表恢复后端返回的原始顺序，列表头箭头恢复双向（无排序），无网络请求发出。
6. **Given** 商品列表数据为空，**When** 页面渲染完成，**Then** 表格仍显示「商品 ID」列表头和「商品标题」列表头（含排序箭头），正文区显示空状态提示，排序交互不报错。

---

### User Story 5 - 商品列表显示近90天卖出数量 (Priority: P2)

As a user, I can see the quantity sold in the last 90 days for each product in the product list so that I can quickly assess which products are selling well without navigating into each product's detail page.

**Why this priority**: 近90天销量是评估商品热销程度的核心指标，直接在列表中展示可避免用户逐一进入商品详情查阅，提升操作效率。优先级与「商品列表显示商品 ID / 按标题排序」同级（P2），不阻塞核心数据分析功能。

**Dependency**: 依赖 Spec 005（子订单 `SubOrder` 表）已完成并导入数据；`suborder` 表不存在或为空时，所有商品销量显示 `0`，不报错。

**Independent Test**: 导入至少一批子订单数据，打开商品列表，确认表格包含「近90天销量」列；选取一个已知子订单数据的商品，确认该列数值等于过去90天内状态为「交易成功」且无退款申请的子订单件数合计；对近90天无销售记录的商品，确认显示 `0` 而非空白。

**Acceptance Scenarios**:

1. **Given** 商品列表已加载，**When** 页面渲染完成，**Then** 表格新增「近90天销量」列，对每条商品记录显示过去90天（今天 00:00:00 往前推90天，含今天共90天）内 `status = '交易成功'` 且 `refund_amount = '无退款申请'` 的子订单件数（`quantity` 字段）合计。
2. **Given** 某商品近90天内无符合条件的子订单，**When** 列表渲染，**Then** 该商品「近90天销量」显示 `0`，不显示空白或 `null`。
3. **Given** `suborder` 表中无任何数据，**When** 商品列表加载，**Then** 所有商品「近90天销量」均显示 `0`，页面不报错、不影响其他列正常展示。
4. **Given** 商品列表已加载，**When** 页面初次渲染，**Then** 「近90天销量」数据通过现有 `GET /api/products` 端点返回（新增聚合字段 `sold_90d`），不额外发起任何 API 请求。
5. **Given** `GET /api/products` 返回带 `sold_90d` 字段的数据，**When** 子订单数据中同一商品在近90天有多条子订单记录，**Then** `sold_90d` 为该商品所有符合条件子订单 `quantity` 字段之和（而非订单笔数）。

---

## Out of Scope

- 仪表盘时间筛选状态的 URL 持久化（当前版本仅保存在组件内存中）
- `data/Goods/` 目录的自动监听与实时同步（当前仅支持手动触发导入）
- 商品价格走势 CSV 字段格式的变更（保持现有 4 字段格式不变）
- 导入历史记录与审计日志功能
- 原「导入商品」/「导入订单」旧路由的重定向（直接删除，不保留向后兼容）
- 走势图聚合粒度随时间窗口自动切换（粒度始终由用户手动选择）
