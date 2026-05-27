# Functional Acceptance Checklist: 商品详情页订单实付价格走势

**Purpose**: Validate requirement completeness, clarity, consistency, and measurability across all FR, SC, user story acceptance scenarios, and edge cases — "unit tests for the spec"
**Created**: 2026-05-26
**Feature**: [spec.md](../spec.md)

---

## Requirement Completeness

- [ ] CHK001 — 商品详情页新增图表区域的尺寸、布局占比是否有明确规格，还是仅说明「位于快照走势图下方」？ [Completeness, Spec §FR-001]
- [ ] CHK002 — 是否明确规定新图表加入后，现有快照价格走势图的布局和功能保持完全不变？ [Completeness, Spec §FR-001]
- [ ] CHK003 — X 轴时间刻度格式（如 `YYYY-MM-DD` 或 `MM/DD`）是否已指定？ [Completeness, Spec §FR-003]
- [ ] CHK004 — Y 轴（单件均价）的刻度精度（小数位数）、单位标注（元/¥）、最小/最大边界规则是否已指定？ [Completeness, Spec §FR-003]
- [ ] CHK005 — 趋势线的视觉样式（颜色、线宽、透明度、是否延伸至数据范围外）是否已规定？ [Completeness, Spec §FR-011]
- [ ] CHK006 — 价格走势图加载中（API 响应未返回前）的 Loading 状态要求是否已定义？ [Gap]
- [ ] CHK007 — 价格走势图 API 调用失败（网络错误、5xx）时的错误状态展示要求是否已定义？ [Gap]
- [ ] CHK008 — Tooltip 中 `订单创建时间` 的显示格式（如精确到分钟还是天）是否已指定？ [Completeness, Spec §FR-005]
- [ ] CHK009 — Tooltip 中「单件均价」的小数精度（保留几位）是否已指定？ [Completeness, Spec §FR-005]
- [ ] CHK010 — `GET /api/products/{id}/order-price-series` 完整响应体 schema（字段名、类型、嵌套结构）是否已规范？ [Completeness, Spec §FR-008]
- [ ] CHK011 — 子订单导入 API 响应体中 `errors` 字段的内容格式是否已指定（仅错误总数，还是含逐行错误详情）？ [Completeness, Spec §FR-009]
- [ ] CHK012 — 导入接口和价格走势接口的鉴权/权限要求是否已定义？ [Gap]
- [ ] CHK013 — 当返回数据点恰好等于 1000 条时，`truncated` 字段是 `true` 还是 `false` 是否有明确规定（边界行为）？ [Completeness, Spec §FR-008]
- [ ] CHK014 — 超大 xlsx 文件导入（如 10 万行以上）的内存/流式处理要求是否已定义？ [Gap]

---

## Requirement Clarity & Ambiguity Resolution

- [ ] CHK015 — 「近 90 天」是从当前日期往前推 90 个自然日，还是从最后一条导入记录的日期往前推？ [Ambiguity, Spec §FR-004]
- [ ] CHK016 — `单件均价 = 买家实付金额 ÷ 购买数量` — 当 `购买数量 = 0` 时（除零情况）的处理行为是否已指定？ [Ambiguity, Spec §FR-003]
- [ ] CHK017 — `errors` 字段记录的跳过行，是指 `商品ID` 为空或金额无法解析两种之一，还是同时包含其他无效情形？边界枚举是否完整？ [Ambiguity, Spec §FR-009]
- [ ] CHK018 — 「`商品ID` 为空」是否明确包含：`null`、空字符串 `""`、纯空白字符串 `"  "` 三种情形？ [Ambiguity, Spec §FR-009]
- [ ] CHK019 — 「金额无法解析」是否给出具体示例（如含字母、负数、超出范围值），使测试人员可客观判断？ [Ambiguity, Spec §FR-009]
- [ ] CHK020 — `订单状态 = 交易成功` 是否为大小写敏感的精确字符串匹配？首尾空格是否被 trim？ [Ambiguity, Spec §FR-002]
- [ ] CHK021 — 当 `days` 参数传入非法值（如 `days=45` 或 `days=abc`）时，API 的行为（400 错误 vs. 默认 90 天）是否已规定？ [Ambiguity, Spec §FR-008]
- [ ] CHK022 — 趋势线（线性回归）是由前端计算还是后端计算，是否已明确（影响 API schema 设计）？ [Ambiguity, Spec §FR-011]
- [ ] CHK023 — 当用户切换时间范围后，所选时段内无任何数据点时，图表显示规则（空状态 vs. 空坐标系）是否已规定？ [Ambiguity, Spec §FR-004, §FR-006]
- [ ] CHK024 — `truncated: true` 是针对整体 1000 条上限，还是在特定 `days` 筛选下超 1000 条也会触发？ [Ambiguity, Spec §FR-008]

---

## Acceptance Criteria Measurability

- [ ] CHK025 — SC-001「2 秒内完成渲染」的起点是否明确（页面导航开始 / 组件挂载 / API 响应到达）？ [Measurability, Spec §SC-001]
- [ ] CHK026 — SC-003「图表数据在 1 秒内刷新」的计时起点（用户点击时间范围选项 vs. API 请求发出）是否已规定？ [Measurability, Spec §SC-003]
- [ ] CHK027 — SC-004「空状态提示可读且说明原因」的验收标准是否可客观判断，还是依赖主观评审？ [Measurability, Spec §SC-004]
- [ ] CHK028 — SC-006「视觉验证，无精度要求」是否有最低可观测标准（如趋势线不得与散点整体方向相反），以支持客观验收？ [Measurability, Spec §SC-006]
- [ ] CHK029 — SC-005 中引用的 2391 行测试数据集是否已准备并可供验收测试使用？ [Assumption, Spec §SC-005]
- [ ] CHK030 — SC-002「散点数量与有效子订单数量完全一致」中，「有效」的判定条件（状态=交易成功 AND 退款金额=无退款申请）是否在验收文档中显式对齐？ [Clarity, Spec §SC-002]

---

## User Story 1 — Scenario Coverage（在商品详情页查看订单实付价格走势）

- [ ] CHK031 — Scenario 1：是否规定了「每个有效子订单对应一个数据点」在时间段内有超过 1000 条时的截断展示行为？ [Coverage, Gap]
- [ ] CHK032 — 是否有场景覆盖：商品有关联子订单，但所有子订单均因退款或非「交易成功」状态被排除，走势图显示什么？ [Coverage, Gap]
- [ ] CHK033 — Scenario 2 的 Tooltip 中，`商品属性` 为空字符串时的显示规则是否已定义？ [Coverage, Gap]
- [ ] CHK034 — 是否有场景覆盖：切换时间范围（近 30 天 / 近 90 天 / 全部）时，若当前范围内无数据而其他范围有数据，图表如何响应？ [Coverage, Gap]
- [ ] CHK035 — Scenario 3 的空状态提示文案是否已在 spec 中固定，还是留给实现自行决定？ [Clarity, Spec §FR-006]
- [ ] CHK036 — 是否有场景明确验证「近 30 天」筛选仅展示该时段数据点，而非全量数据的前 30 天？ [Coverage, Spec §FR-004]

---

## User Story 2 — Scenario Coverage（导入子订单 xlsx）

- [ ] CHK037 — Scenario 1：`{imported, updated, skipped, errors}` 各字段的语义是否精确定义（如 `skipped` 与 `errors` 的区别）？ [Clarity, Spec §FR-009]
- [ ] CHK038 — Scenario 2：缺少列时，错误响应是否应包含所有缺失列名，还是仅第一个？ [Completeness, Spec §FR-009]
- [ ] CHK039 — Scenario 3（upsert）：当同一 xlsx 文件内存在重复 `子订单编号` 时（文件内冲突），系统行为是否已定义？ [Coverage, Gap]
- [ ] CHK040 — 是否有场景覆盖：`退款金额` 字段包含意外类型（如数值型而非字符串）的 xlsx 行如何处理？ [Coverage, Gap]
- [ ] CHK041 — 是否有场景覆盖：上传非 xlsx 格式文件（如 .csv 或 .xls）时的错误响应？ [Edge Case, Gap]
- [ ] CHK042 — 是否有场景覆盖：xlsx 文件内所有行均为无效行（全量跳过）时的响应内容？ [Edge Case, Gap]

---

## User Story 3 — Scenario Coverage（价格走势图布局）

- [ ] CHK043 — Scenario 1：「商品信息 → 快照价格走势图 → 订单实付价格走势图」的垂直排列顺序是否已在规格中固定，以防止实现时顺序颠倒？ [Clarity, Spec §User Story 3 SC1]
- [ ] CHK044 — 是否有场景覆盖：商品有订单数据但无快照数据时，快照走势图区域的显示规则（空状态 vs. 完全隐藏）？ [Coverage, Gap]
- [ ] CHK045 — 是否有场景覆盖：两个走势图同时处于加载中时的页面布局（防止跳动/重排）？ [Coverage, Gap]

---

## Edge Case Coverage

- [ ] CHK046 — 边界案例「`sub_orders` 表为空」的空状态提示文案是否与 FR-006 中「`taobao_item_id` 无匹配」的空状态文案区分，以准确传达不同原因？ [Clarity, Spec §Edge Cases]
- [ ] CHK047 — 边界案例「同日多笔子订单」在 X 轴上完全重叠时，散点的视觉重叠处理规则（透明度、抖动/jitter、堆叠）是否已规定？ [Clarity, Spec §Edge Cases]
- [x] CHK048 — `购买数量 = 0` 的子订单（除零风险）是否被明确列入边界案例并规定处理方式（跳过 / 报错 / 原值保留）？ → **已决策：单件均价显示为 ¥0.00，不跳过，不报错** [Resolved]
- [ ] CHK049 — `订单创建时间` 为 null 或无法解析的子订单行，是否在导入时跳过并计入 `errors`，还是作为另一类无效行处理？ [Edge Case, Gap]
- [ ] CHK050 — `退款金额` 为空字符串（既非 `"无退款申请"` 也非数值字符串）的子订单，是否明确归类为「有退款」（排除）还是「无退款」（保留）？ [Edge Case, Gap]
- [ ] CHK051 — 同一 `商品ID` 对应多条 `Product` 记录时（数据质量问题），`order-price-series` 接口的行为是否已定义？ [Edge Case, Gap]

---

## Data Model & Integration Requirements

- [ ] CHK052 — `SubOrder` 表是否需要在 `(taobao_item_id, created_at, status)` 上建复合索引以满足 SC-001/SC-003 的性能目标？索引策略是否已文档化？ [Completeness, Spec §Data Model]
- [ ] CHK053 — `SubOrder.taobao_item_id` 与 `Product.taobao_item_id` 的关联是逻辑关联还是数据库外键约束？不一致时的行为是否已定义？ [Completeness, Spec §Data Model]
- [ ] CHK054 — 导入子订单时，若 `taobao_item_id` 在 `products` 表中不存在（孤立子订单），系统是继续导入还是跳过并计入 `errors`？ [Edge Case, Gap]
- [ ] CHK055 — `SubOrder.imported_at` 字段是由应用层写入还是数据库默认值（`DEFAULT NOW()`）？其精度和时区要求是否已规定？ [Clarity, Spec §Data Model]
- [ ] CHK056 — 现有依赖 `Order` 表的功能（如旧订单看板）是否有明确的不回归声明，以保证 `SubOrder` 并存不影响现有功能？ [Consistency, Spec §Assumptions]

---

## Non-Functional Requirements

- [ ] CHK057 — SC-001/SC-003 的性能目标是否涵盖网络条件（如 100ms 延迟网络），还是仅适用于 localhost/局域网场景？ [Completeness, Spec §SC-001, §SC-003]
- [ ] CHK058 — 是否规定了支持的浏览器品牌和最低版本（如 Chrome 110+、Safari 16+），而非仅写「桌面浏览器 1280px 以上」？ [Completeness, Spec §Assumptions]
- [ ] CHK059 — `sub_orders` 表的数据清理/归档策略（历史数据多久清除）是否已定义或明确排除在本迭代范围外？ [Gap]
- [ ] CHK060 — 图表在 1280px 宽度下与在 1920px 宽度下的最小/最大渲染尺寸需求是否已规定？ [Completeness, Spec §Assumptions]
- [x] CHK061 — 日期/时间的显示时区（系统本地时区 vs. UTC vs. 用户浏览器时区）要求是否已明确定义？ → **已决策：使用浏览器本地时间，不使用服务器时间，前端负责时区转换** [Resolved]

---

## Notes

- 本清单所有条目均测试**需求文档本身的质量**（完整性、明确性、一致性、可衡量性），而非验证实现行为。
- 标记 `[Gap]` 的条目表示 spec 中尚未覆盖的需求，需在进入 planning/tasking 前补充或明确排除。
- 标记 `[Ambiguity]` 的条目表示 spec 中已有描述但存在多义解读，需作者确认正确语义。
- 标记 `[Completeness]` 的条目表示需求已提及但细节不足，需补充规格。
- 勾选前请在条目后记录结论（已补充 / 已确认排除 / 已澄清），便于追溯。
