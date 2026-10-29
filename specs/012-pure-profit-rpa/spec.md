# Feature Specification: 纯利润分析与 RPA 平台费用采集

**Feature Branch**: `012-pure-profit-rpa`

**Created**: 2026-10-12

**Status**: Implemented

## Clarification Decisions (2026-10-12)

| # | 问题 | 决策 |
|---|------|------|
| Q1 | RPA 技术栈 | **Playwright**（Python sync API，独立线程运行） |
| Q2 | 部署形式 | **本机直接跑 Python 进程**（FastAPI 内置 RPA 工作线程，无 Docker） |
| Q3 | 凭据主密钥 | 由开发方生成 Fernet key 写入项目根 `.env` 的 `RPA_MASTER_KEY`，模板见 `.env.example` |
| Q4 | 触发方式 | **按钮触发**（无定时任务） |
| Q5 | 滑块/短信验证 | **人工处理**：`RPA_HEADLESS=false`，浏览器窗口对用户可见，任务进入 `need_verify` 状态等待 |
| Q6 | 账号体系 | **千牛与阿里妈妈独立账号记录**，各自可配置；用户可选择拉取哪个数据集 |
| Q7 | 实施节奏 | **一次性全部实现**（基础设施 + 纯利润页 + RPA） |

## Overview

现有利润口径（009 首页 / 010 单品毛利）只计算「收入 − 退款 − 采购成本」，未扣除平台扣费、
推广费、运费险等。这些费用无法从千牛导出的订单 Excel 中获取，需要登录千牛工作台与
阿里妈妈投放后台查看。

本功能提供：

1. **独立的「纯利润分析」页面**（`/profit`），口径为
   `净利润 = 收入 − 退款 − 采购成本 − 平台扣费 − 推广费 − 运费险 − 其它费用`；
2. **RPA 自动采集**：通过 Playwright 登录千牛 / 阿里妈妈，抓取平台扣费、运费险、
   直通车 / 引力魔方 / 万相台推广花费，用户可勾选要拉取的数据集；
3. **平台账号管理页**（`/accounts`）：保存千牛 / 阿里妈妈登录凭据，密码 AES 加密存储；
4. **额外费用手工录入**：RPA 抓不到时可手动补录 / 修正，与 RPA 数据同表存储。

## 利润计算公式

```
净收入      = SUM(SubOrder.buyer_paid) − SUM(SubOrder.refund_amount)
采购成本    = SUM(PurchaseOrder.paid_amount)   WHERE status NOT IN ('等待买家付款','退款中','交易关闭')
平台扣费    = SUM(StorePlatformExpense.amount) WHERE category = 'platform_fee'
推广费      = SUM(StorePlatformExpense.amount) WHERE category = 'promotion'
运费险      = SUM(StorePlatformExpense.amount) WHERE category = 'shipping_insurance'
其它费用    = SUM(StorePlatformExpense.amount) WHERE category = 'other'

纯利润      = 净收入 − 采购成本 − 平台扣费 − 推广费 − 运费险 − 其它费用
纯利润率    = 纯利润 / 净收入 × 100%
```

> 收入 / 退款 / 采购成本口径与 `GET /api/stats/profit-monthly`（009）保持一致，
> 仅在其基础上追加四类额外费用的扣减。

---

## User Scenarios & Testing

### User Story 1 — 配置平台账号 (Priority: P1)

用户在「平台账号管理」页新增千牛账号（用户名 + 密码），点击「测试登录」确认凭据可用。

**Why this priority**: 没有账号就无法进行任何 RPA 抓取。

**Independent Test**: 新增账号后调用测试登录接口，返回 `ok` / `fail` / `need_verify` 三种状态之一。

**Acceptance Scenarios**:

1. **Given** 账号管理页为空，**When** 用户填写账号名称 / 用户名 / 密码 / 关联店铺并保存，**Then** 列表新增一条记录，密码列显示脱敏值（前 2 位 + `*`）
2. **Given** 已保存账号，**When** 用户点击「测试登录」，**Then** 系统弹出浏览器完成登录并返回状态；成功时 `last_login_status = ok`
3. **Given** 已保存账号，**When** 用户点击「编辑」并清空密码字段保存，**Then** 原密码保持不变
4. **Given** 已保存账号，**When** 用户点击「删除」并确认，**Then** 记录删除，其密码立即失效

---

### User Story 2 — 触发 RPA 抓取 (Priority: P1)

用户在「纯利润分析」页点击「触发 RPA 抓取」，选择账号、勾选要拉取的数据集，创建抓取任务。

**Why this priority**: 这是补齐费用数据的唯一自动化入口。

**Independent Test**: 创建任务后，任务状态从 `pending` → `running` → `success/failed/need_verify`，日志实时可见。

**Acceptance Scenarios**:

1. **Given** 已配置账号，**When** 用户打开触发弹窗，**Then** 账号下拉列出所有账号，数据集复选框按平台动态展示
2. **Given** 未勾选任何数据集，**When** 用户点击「开始抓取」，**Then** 提示「请至少勾选一项要拉取的数据」
3. **Given** 选择了千牛账号但勾选了阿里妈妈专属数据集（通过接口绕过前端校验），**Then** 返回 422
4. **Given** 抓取过程中出现滑块验证，**Then** 任务状态变为 `need_verify`，日志提示人工处理，浏览器窗口保持可见
5. **Given** 抓取成功，**Then** 费用记录写入 `StorePlatformExpense`，任务 `result_summary` 含写入条数
6. **Given** 任务进行中，**When** 用户点击「取消任务」，**Then** 状态变为 `cancelled`

---

### User Story 3 — 查看纯利润 (Priority: P1)

用户打开「纯利润分析」页，查看合计与分店铺的纯利润、纯利润率、环比，以及月度构成图。

**Why this priority**: 页面的核心价值。

**Independent Test**: 有子订单 + 采购单数据时，页面 KPI 与手工按公式计算结果一致。

**Acceptance Scenarios**:

1. **Given** 存在订单与采购数据，**When** 页面加载，**Then** 展示 8 张合计 KPI 卡（收入/退款/采购成本/平台扣费/推广费/运费险/其它/纯利润）与 2 张补充卡（净收入、纯利润率）
2. **Given** 纯利润为正，**Then** KPI 值显示为成功色（绿色）；为负显示危险色（红色）
3. **Given** 至少 2 个月数据，**Then** 纯利润卡显示环比百分比
4. **Given** 费用项为 0（尚未抓取或录入），**Then** 该 KPI 显示 ¥0.00 而非报错
5. **Given** 月度明细表，**Then** 每月展示各费用项与纯利润、纯利润率

---

### User Story 4 — 手动录入 / 修正费用 (Priority: P2)

RPA 抓取失败或需要修正时，用户手动录入费用记录。

**Why this priority**: RPA 依赖页面结构，必须有兜底手段。

**Independent Test**: 手动录入一条推广费后，纯利润 KPI 立即减少对应金额。

**Acceptance Scenarios**:

1. **Given** 用户点击「+ 手动录入费用」，**When** 填写店铺 / 月份 / 类别 / 金额并保存，**Then** 明细表新增一条来源为「手动」的记录
2. **Given** 已存在同店铺 + 同月份 + 同类别 + 同子类的记录，**When** 再次保存，**Then** 覆盖原记录（幂等）
3. **Given** 月份格式非法，**Then** 提示「月份格式应为 YYYY-MM」
4. **Given** 用户编辑某条记录，**When** 保存，**Then** 金额与备注更新，来源标记不变
5. **Given** 用户删除某条记录，**Then** 确认后记录删除，纯利润重新计算

---

## Data Model

| 表 | 用途 | 关键字段 |
|---|---|---|
| `PlatformAccount` | 平台登录凭据 | `platform`, `account_label`, `username`, `password_enc`(Fernet), `store`, `last_login_status` |
| `RPATask` | 抓取任务 | `platform`, `account_id`, `datasets`(JSON), `status`, `progress`, `log`, `result_summary`, `error_message` |
| `StorePlatformExpense` | 额外费用明细 | `store`, `period_month`, `category`, `sub_category`, `amount`, `source`(rpa/manual/xlsx), `rpa_task_id` |
| `SessionCookie` | 会话 Cookie（预留） | `account_id`, `domain`, `cookies_json_enc`, `expires_at`, `is_valid` |

`StorePlatformExpense` 唯一约束：`(store, period_month, category, sub_category)`，保证重复抓取幂等覆盖。

## API Contracts

```
GET    /api/credentials/platforms            平台 + 数据集选项
GET    /api/credentials                      账号列表（密码脱敏）
POST   /api/credentials                      新增账号
PUT    /api/credentials/{id}                 更新（密码留空=不修改）
DELETE /api/credentials/{id}                 删除
POST   /api/credentials/{id}/test-login      测试登录

POST   /api/rpa/tasks                        创建抓取任务
GET    /api/rpa/tasks                        任务列表
GET    /api/rpa/tasks/{id}                   任务详情（含日志）
POST   /api/rpa/tasks/{id}/cancel            取消任务

GET    /api/profit/pure                      纯利润分析（月度 + KPI + 数据源状态）
GET    /api/profit/expenses                  费用明细
POST   /api/profit/expenses                  新增/覆盖
PUT    /api/profit/expenses/{id}             更新金额/备注
DELETE /api/profit/expenses/{id}             删除
```

## Non-Functional Requirements

- **安全**：密码 / Cookie 使用 Fernet（AES-128-CBC + HMAC）加密；密钥仅存于 `.env`，
  `.env` 已在 `.gitignore` 中排除；数据库文件 `tasks.db` 不得提交到版本库。
- **反风控**：页面操作间随机延迟 1.0~2.5 秒（可配置）；每账号独立浏览器 profile 目录，
  复用登录态避免频繁登录；同一时刻仅执行一个 RPA 任务。
- **可观测**：每个抓取步骤写日志到 `RPATask.log`；失败时自动截图保存到
  `rpa_screenshots/`，日志中给出截图路径。
- **健壮性**：选择器集中在 `backend/rpa/selectors.py`；抓不到数据时返回明确告警，
  **绝不写入 0 值**（避免污染利润数据）。

## Out of Scope

- 定时自动抓取（当前仅按钮触发）
- Docker 化部署
- 多用户 / 权限隔离
- 订单级平台扣费逐条拆分（`order_fee_detail` 仅做页面级汇总兜底）
- 1688 采购后台 RPA 抓取（采购数据仍走 Excel 导入）
