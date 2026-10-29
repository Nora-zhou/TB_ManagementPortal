# Implementation Plan: 店铺内容检测模块（拆细版）

**Feature Branch**: `013-store-inspection`

**Created**: 2026-10-29

**Status**: Planning

**上游依据**: `迭代计划v2_基于spec-kit-app.html`

**与 v2 的关系**: v2 是 8 个迭代 59h，单个迭代 6–10h，节奏上是「两周一个交付物」。本计划把它拆成 **16 个 1–5h 的迭代**，工时合计 58h（另 2h 可选），但**每个迭代结束时都必须有一条能跑的命令和一个能看的产物**。拆分不改变目标，只改变颗粒度和反馈频率。

---

## 一、拆分原则

1. **一个迭代 = 一条命令 + 一个产物**。没有可执行验收的迭代不允许开工，也不允许拆出来。
2. **单迭代 ≤ 5h**。按 8h/周算，每周能完成 1–2 个迭代，最迟 5 天能看到一次进展。
3. **不确定性前置**。I01–I02 只做一件事：证明「抓得到、抓得准」。这两步不过，后面全部作废。
4. **事实层只增不改**。I03 一次性把 `item_snapshot` 字段定够，之后只加列不删列——`PriceSnapshot` 只有一个 `price` 字段的历史教训已经付过学费了。
5. **换源不改下游**。I01 就留出 `source` 抽象，I04 接 TOP API 时下游零改动。这是应对 G01 失败的根本保障。

---

## 二、总体路线：5 个里程碑

| 里程碑 | 达成标准 | 包含迭代 | 累计工时 | 时间 |
|---|---|---|---|---|
| **M1 单商品可信** | 一条命令拿到一个 SKU 的完整内容，可信度可解释 | I00–I03 + G01 | 15h | 第 1–2 周 |
| **M2 整店可采** | 一条命令跑完 30 个 SKU，数据自带校验结论 | I04–I06 | 26h | 第 3–4 周 |
| **M3 能下判断** | 一条命令输出指标、信号、七维评分 | I07–I10 | 40h | 第 5–6 周 |
| **M4 能交付** | 一条命令出一份 8 页 PDF | I11–I12 | 48h | 第 7 周 |
| **M5 可持续** | 归因、月度对比、定时全通 | I13–I15 | 58h | 第 8 周 |

> 8h/周、58h 理论 7.3 周，留 0.7 周缓冲，**承诺 8 周**。

---

## 三、迭代明细

| # | 迭代目标 | 结束时可跑的命令 / 可见产物 | 工时 | 依赖 |
|---|---|---|---|---|
| **I00** | 还技术债 + 轻量迁移机制 + 检测模块骨架（6 张表、空 CLI） | `python inspect_cli.py --version` 可用；删除 `tasks.db` 后重启自动重建全部表；`pytest` 全绿；`git status` 无 db 文件 | 4h | — |
| **I01** | 单商品「取数 → 存档 → 解析」最小闭环 | `python inspect_cli.py collect --item <id>` 打印标题/价格/主图数/详情图数/月销文本；`data/raw/<run_id>/` 下有 XHR JSON + HTML + 截图 | 3h | I00 |
| **I02** | 双通道互校 + 字段级可信度 + 改版哨兵 | `collect --item <id> --verify` 输出每字段 `{xhr, dom, reliable}`；核心字段全空时**不写库**并 `exit 2` | 3h | I01 |
| **I03** | 全字段落库（SKU / 价格结构 / 图片 meta / 评价结构 / 服务 / 状态） | `collect` 写 `item_snapshot`；`show --item <id>` 回读结果与你手工看页面逐项一致 | 4h | I02 |
| **G01** | **数据准确性闸门**（人工 + 自动 diff） | 5 个自有 SKU 核对表全通过；Top30 与 API 结果字段级 diff 无重大偏差；不通过则停 | 1h | I03 |
| **I04** | TOP API 数据源接入（自有店 / 利润版客户店） | `collect --item <id> --source api` 输出同一结构；与页面结果一致率 ≥ 95% | 3h | G01 |
| **I05** | 整店批量采集（源 = 现有 `Product` 表，Top N + 限速 + 断点续跑） | `collect --store 1 --limit 30` 无报错；中断后重跑从中断点继续；`inspection_run` 有完整记录 | 4h | I04 |
| **I06** | 断言引擎（pydantic 契约 + 业务规则 + 降级标记） | `validate --run <id>` 输出断言表；喂残缺数据不崩、`field_reliable` 标 0、下游可跳过 | 4h | I05 |
| **I07** | 指标引擎（动销率 / Top10 集中度 / 价格带 / 图评 / 标题覆盖） | `analyze --run <id>` 写 `metric` 表；集中度与手工 Excel 算的一致 | 4h | I06 |
| **I08** | 信号矩阵（8 组纯 Python 规则） | `signals --run <id>` 输出问题域；自有店命中 ≥ 3 组且你人工认可 | 3h | I07 |
| **I09** | 六维评分卡（rubric 配置化 + `rule_version` + evidence） | `score --run <id>` 输出总分与六维分；每个扣分项能说清依据 | 5h | I08 |
| **I10** | 第七维「利润健康度」 | 自有店评分含 profit 维（复用 `profit_analysis.py`）；客户店留空且报告隐藏该维 | 2h | I09 |
| **I11** | 八页报告 HTML（Jinja2 + CSS） | `report --run <id>` 生成 `report.html`，浏览器打开八页结构完整 | 5h | I10 |
| **I12** | PDF 导出 + 打印校验 | `report --run <id> --pdf`；PDF 正好 8 页、无错位、黑白打印可读 | 3h | I11 |
| **I13** | LLM 差评归因 + 缓存 + 输出校验 + 规则回退 | 同数据连跑 3 次结构一致；输出必过 schema；脏数据自动回退且报告标注 | 4h | I12 |
| **I14** | 两期快照 diff | `diff --run A --run B` 指出价格/主图/评分/指标的逐项变化 | 3h | I13 |
| **I15** | 定时 + CLI 收口 + 使用文档 | Windows 任务计划连续 3 天成功；7 个子命令 `--help` 齐全；`README` 一页可自助运行 | 3h | I14 |
| *I05b* | *可选：店铺页翻页（竞品用，不阻塞里程碑）* | *`collect --shop <url> --limit 30`* | *2h* | *I05* |

**合计：必做 58h，可选 2h。** 与 v2 的 59h 基本持平——拆细后新增的「分源抽象」「双通道互校」被并入了原 I1/I2 的预算，没有额外膨胀。

---

## 四、最关键三个迭代的设计（其余迭代照 v2 执行）

### I01：为什么先做「取数与解析分离」

```
collect --item <id>
  ├─ fetch_item(url) -> raw_dir        # 只负责：goto、监听 response、落盘
  └─ parse_item(raw_dir) -> dict       # 纯函数：只吃 raw 目录，不碰网络
```

- 好处一：解析器可以**用历史 raw 做单元测试**，不需要联网、不会触发风控。
- 好处二：页面改版后能拿旧 raw **重放**，判断是取数断了还是解析断了。这一条直接决定 G01 失败时能不能救。
- 好处三：天然支持 I05 的断点续跑（raw 已存在则跳过取数）和 I15 的 `recompute`。

### I02：字段分级 + 字段级可信度

`item_snapshot.reliable INTEGER` 是整条记录级，一个字段失败整条作废，与 I06「断言失败只跳过该字段」直接矛盾。改为 `field_reliable_json`：

```json
{"title": 1, "price": 1, "image_count": 1, "sales": 0, "review": 0}
```

同时把字段分两级，断言和报告按级处理：

- **CORE（必须有）**：`title`、`price`、`image_count`、`detail_image_count`
- **ENHANCED（可缺省）**：SKU、评价结构、图片 meta、服务、库存

CORE 全空 → 直接失败退出，绝不写一条「看起来成功」的空快照。

### I05：不自找麻烦的批量方案

v2 把批量等同于「店铺页翻页」，但自有店的 `Product` 表里已经有全部 `taobao_item_id`（`models.py:16`）。所以：

- **I05 必做**：从 `Product` 表按销量取 Top N → 逐个 `collect` → 限速 + 断点续跑。零翻页、零点选器、零新增风控面。
- **I05b 可选**：店铺页翻页只服务竞品，等真有竞品分析需求再做，不影响任何里程碑。

---

## 五、五个关键设计决策

| # | 决策 | 理由 |
|---|---|---|
| 1 | 采集统一产出 `ItemSnapshot`，`source ∈ {api, page_xhr, page_dom}` | I04 换源时下游零改动；G01 失败可整体切 API |
| 2 | 取数与解析分离，raw 目录即中间产物 | 可重放、可单测、可断点续跑 |
| 3 | 可信度做到字段级（`field_reliable_json`） | 与断言层「只跳过该字段」的语义对齐 |
| 4 | 字段分 CORE / ENHANCED 两级 | 页面改版只影响 ENHANCED，核心链路不死 |
| 5 | 事实层（`item_snapshot`）与判定层（`metric` / `score`）分离，带 `rule_version` | 改规则可对历史 run 重算做回归 |

---

## 六、表结构（I00 建 6 张，I03 扩字段）

沿用 v2 的 6 张表（`inspection_run` / `item_snapshot` / `assertion_result` / `metric` / `score` / `inspection_report`），`item_snapshot` 相对 v2 增列：

```sql
price_min_cents   INTEGER   -- SKU 价格区间
price_max_cents   INTEGER
promo_price_cents INTEGER   -- 券后/促销价
stock_total       INTEGER
item_status       TEXT      -- onsale | offsale | soldout
sku_json          TEXT      -- [{sku_id,name,price_cents,stock,img}]
image_meta_json   TEXT      -- [{url,w,h,ratio,is_white_bg,has_text}]
detail_meta_json  TEXT      -- {img_count,total_height,text_len,has_video,has_param_table}
review_json       TEXT      -- {count,neg_count,img_count,recent30,addon_rate,qa_count}
service_json      TEXT      -- {free_ship,shipping_insurance,ship_hours}
field_reliable_json TEXT    -- 字段级可信度（替代 reliable INTEGER）
source            TEXT      -- api | page_xhr | page_dom
```

JSON 列会让 I07 的指标计算多一层解析，但比开 6 张子表划算得多——检测数据量在千级以内。

---

## 七、闸门与止损

**G01（I03 后，第 2 周）**：5 个 SKU 人工核对。价格必须 100% 一致；主图数误差 ≤ 1；销量区间正确。**任一项不达标就停**，不进 I04。

**降级路线（G01 失败时）**：不推倒重来，按顺序切：
1. I04 的 TOP API 提到前面，页面采集只保留 DOM 兜底 → 自有店链路立刻可用；
2. 客户店/竞品退回「手工导 Excel / 手工填表」→ 只保留 `validate → analyze → report`；
3. 因为 I01–I03 已锁定 `ItemSnapshot` 结构，**下游 11 个迭代一行不用改**。这是把不确定性关在 I01–I03 里的收益。

**G02（I09 后，第 6 周）**：若评分与你的经验判断差 > 1 分，**改 rubric 不改代码**。评分卡错了，后面每份报告都是错的，而报告是唯一交付物。

---

## 八、明确不做

| 不做 | 原因 |
|---|---|
| 检测功能的 Vue 页面 | CLI + PDF 足以服务前 5 个客户 |
| 竞品店铺页翻页（I05b） | 非评分卡必需，可随时补 |
| 图片 CV / OCR 自动打标 | 需新依赖，I03 用「尺寸 + 比例 + 首图文字区域」启发式足够 |
| 视频下载与分析 | 只记「有无视频 + 时长」 |
| 多平台（京东/拼多多/抖音） | 一个平台做透 |
| 实时监控大屏 | 月度订阅只需要每月一份 PDF |

---

## 九、新增 / 修改文件

**新增**

| 文件 | 主要迭代 |
|---|---|
| `backend/inspection/models.py`（6 张表 + 枚举） | I00 |
| `backend/inspection/collect/{item.py,parser.py,raw_store.py,api_source.py,shop_batch.py}` | I01–I05 |
| `backend/inspection/validate/{schema.py,assertions.py}` | I06 |
| `backend/inspection/analyze/{metrics.py,signals.py,score.py,llm.py}` | I07–I10、I13 |
| `backend/inspection/report/{builder.py,pdf.py,templates/report.html.j2,styles/report.css}` | I11–I12 |
| `backend/inspection/runner.py` | I05 |
| `backend/inspect_cli.py` | I00 起，I15 收口 |
| `backend/config/rules.yaml` | I07 起持续增补 |
| `backend/config/prompts/*.v1.md` | I13 |
| `backend/tests/inspection/*` | 每个迭代同步 |

**修改**

| 文件 | 改动 |
|---|---|
| `backend/database.py` | 编号 SQL 迁移 + `schema_version` 表（I00） |
| `backend/rpa/selectors.py` | 追加 `TAOBAO_ITEM` 段（I01） |
| `backend/taobao_client.py` | `fetch_store_items` 的 `fields` 扩到 SKU / 图片 / 属性（I04） |
| `backend/models.py` | 检测表统一放 `inspection/models.py`，此处不动 |
| `backend/requirements.txt` | 新增 `jinja2`（I11）、`pyyaml`（I07） |

---

## 十、风险与对策

| 风险 | 影响迭代 | 对策 |
|---|---|---|
| 详情页 XHR 接口加密 / 需 sign | I01 | DOM 兜底；I04 API 分源兜底；I05 降级路线 |
| 评价内容需登录态，公开页只拿得到数量与评分 | I03 / I13 | I13 的输入先降级为「评价数 + 评分 + 可见摘要」；差评原文后续走千牛后台（已有登录态）补 |
| TOP API 的 `fields` 权限与字段名需逐个核 | I04 | I04 预留 1h 用官方文档 + 实际调用核一遍，不假设 |
| 采集字段加多了，改版时断点变多 | 全程 | CORE / ENHANCED 分级；每字段必须对应一条指标或评分要素，否则不进表 |
| 拆分过细导致上下文切换成本 | 全程 | 按里程碑提交；I01–I03 连续做，不插入其他任务 |

---

## 十一、执行建议

- 每个迭代结束后 **一次 commit**，commit message 用 `013-I05: ...`，里程碑末打 tag（`013-m1`）。
- I00–I03 + G01 建议连续两周做完再动其他事。这一段决定项目生死，中间不要切去修 bug。
- 周五只做验收，不写新代码：跑一遍当周所有命令，确认「每迭代都有可执行产物」这条纪律没破。
