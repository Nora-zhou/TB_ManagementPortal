# Implementation Plan: 纯利润分析与 RPA 平台费用采集

**Feature Branch**: `012-pure-profit-rpa`

**Created**: 2026-10-12

**Status**: Implemented

## Technical Context

| 项 | 值 |
|---|---|
| 后端 | Python 3.12 + FastAPI + SQLModel + SQLite |
| 前端 | Vue 3 + Vite + vue-router + ECharts |
| RPA | Playwright 1.58（sync API，独立线程） |
| 加密 | `cryptography` Fernet（AES-128-CBC + HMAC-SHA256） |
| 配置 | `python-dotenv`，`.env` 位于项目根（已 gitignore） |
| 执行模型 | FastAPI lifespan 启动常驻工作线程，串行消费 `pending` 任务 |

## Architecture

```
┌──────────────────────────────────────────────┐
│ Vue 3 前端                                    │
│  PureProfitAnalysis.vue  AccountManage.vue   │
└───────────────┬──────────────────────────────┘
                │ /api/profit /api/credentials /api/rpa
┌───────────────▼──────────────────────────────┐
│ FastAPI                                       │
│  routes/profit_analysis.py  (纯利润聚合)      │
│  routes/credentials.py      (账号 CRUD + 加密)│
│  routes/rpa_tasks.py        (任务创建/查询)   │
└───────────────┬──────────────────────────────┘
                │ 唤醒事件
┌───────────────▼──────────────────────────────┐
│ rpa/runner.py  ── 常驻工作线程（单线程串行）  │
│   ├─ rpa/browser.py    Playwright 会话管理   │
│   ├─ rpa/qianniu.py    千牛抓取               │
│   ├─ rpa/alimama.py    阿里妈妈抓取           │
│   ├─ rpa/selectors.py  选择器集中管理         │
│   └─ rpa/crypto.py     Fernet 加解密          │
└───────────────┬──────────────────────────────┘
                │
        SQLite: platformaccount / rpatask /
                storeplatformexpense / sessioncookie
```

## Key Design Decisions

### 1. Playwright sync API + 独立线程

FastAPI 主线程运行 asyncio 事件循环，Playwright 的 sync API 自带事件循环，
**不能**在 asyncio 线程内运行。因此 `rpa/runner.py` 使用 `threading.Thread(daemon=True)`
作为常驻工作线程，`POST /api/rpa/tasks` 通过 `threading.Event` 唤醒。

### 2. 持久化浏览器 profile 代替 Cookie 手动管理

`launch_persistent_context(user_data_dir=browser_data/account-{id})`：
登录态由 Chromium 自行持久化到磁盘，重复抓取免登录；账号间目录隔离互不污染。
`SessionCookie` 表保留作预留（展示有效期 / 未来切换 API 直连）。

### 3. 凭据加密与脱敏

- 写入：`encrypt(plain) → password_enc`
- 读取：仅 RPA 执行时 `decrypt()`，明文只存在于内存
- 展示：`mask()` 保留前 2 位，其余 `*`
- 密钥：`.env` 的 `RPA_MASTER_KEY`；密钥与密文不匹配时抛 `CryptoError`，
  账号列表显示「⚠️ 密钥不匹配」而不是崩溃

### 4. 费用写入幂等

`StorePlatformExpense` 唯一约束 `(store, period_month, category, sub_category)`。
`runner._upsert_expenses()` 先查后写，重复抓取覆盖而非追加。

### 5. 失败策略：告警而非写 0

千牛 / 阿里妈妈页面经常改版。抓取逻辑取不到金额时：
- 记录 warning 到任务日志
- 自动保存截图到 `rpa_screenshots/`
- **不写入 0 值记录**（0 会虚增纯利润）

### 6. 人工验证处理

`RPA_HEADLESS=false` 时浏览器窗口可见。检测到滑块（`CAPTCHA_SLIDER` 选择器）时
抛 `NeedManualVerification` → `wait_for_manual_verification()` 轮询 URL 直到离开登录页，
超时（默认 300s）则任务置为 `need_verify`。

## Files Created / Modified

### 新增 — 后端

| 文件 | 说明 |
|---|---|
| `backend/rpa/__init__.py` | 包说明 |
| `backend/rpa/config.py` | `.env` 加载，`RPAConfig` dataclass |
| `backend/rpa/crypto.py` | `encrypt` / `decrypt` / `mask` / `CryptoError` |
| `backend/rpa/browser.py` | `BrowserSession`、`NeedManualVerification`、`LoginFailed`、`ScrapeError` |
| `backend/rpa/selectors.py` | 全部平台选择器（集中维护） |
| `backend/rpa/qianniu.py` | 千牛抓取（平台扣费 / 运费险 / 订单级卖家服务费） |
| `backend/rpa/alimama.py` | 阿里妈妈抓取（直通车 / 引力魔方 / 万相台 / 其它） |
| `backend/rpa/runner.py` | 任务执行器（工作线程 + 状态机 + 幂等写入） |
| `backend/routes/credentials.py` | 账号 CRUD + 测试登录 |
| `backend/routes/rpa_tasks.py` | 任务创建 / 查询 / 取消 |
| `backend/routes/profit_analysis.py` | 纯利润聚合 + 费用 CRUD |

### 修改

| 文件 | 改动 |
|---|---|
| `backend/models.py` | 新增 4 张表 + `PLATFORMS` / `PLATFORM_DATASETS` / `EXPENSE_CATEGORIES` 常量 |
| `backend/schemas.py` | 新增账号 / 任务 / 纯利润 / 费用 4 组 Pydantic schema |
| `backend/main.py` | 注册 3 个 router；lifespan 启动 RPA 工作线程（失败不影响主服务） |
| `backend/requirements.txt` | 新增 `playwright` / `cryptography` / `python-dotenv` |
| `.env.example` | 新增（RPA_MASTER_KEY、headless、延迟、超时等） |
| `frontend/src/main.js` | 新增 `/profit`、`/accounts` 路由 |
| `frontend/src/App.vue` | 导航新增「纯利润分析」；下拉新增「平台账号管理」 |

### 新增 — 前端

| 文件 | 说明 |
|---|---|
| `frontend/src/api/credentials.js` | 账号 API |
| `frontend/src/api/rpa_tasks.js` | 任务 API |
| `frontend/src/api/profit.js` | 纯利润 / 费用 API |
| `frontend/src/components/PureProfitAnalysis.vue` | 主页面（KPI + 构成图 + 明细 + 抓取弹窗 + 日志弹窗 + 费用录入） |
| `frontend/src/components/AccountManage.vue` | 账号管理页 |

## Verification

| 检查 | 结果 |
|---|---|
| `import main` | ✅ 55 条路由 |
| `GET /api/profit/pure` | ✅ 200，KPI 正常聚合 |
| `GET /api/credentials/platforms` | ✅ 千牛 3 项 / 阿里妈妈 4 项数据集 |
| 账号 CRUD | ✅ 201/200/204，密码返回脱敏 `**` |
| 任务创建 / 查询 / 取消 | ✅ 201/200/200，状态机 `pending → cancelled` |
| 非法数据集校验 | ✅ 422 |
| 费用 CRUD + KPI 联动 | ✅ 录入 ¥123.45 后 `total_promotion` 同步变化 |
| 数据源状态 | ✅ 正确反映 `configured` 与最近任务状态 |
| `npm run build` | ✅ built in 8.15s |
| IDE diagnostics | ✅ 0 errors |
