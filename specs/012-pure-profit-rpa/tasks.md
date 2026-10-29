# Tasks: 纯利润分析与 RPA 平台费用采集

**Feature Branch**: `012-pure-profit-rpa`

**Status**: 已完成

| # | 任务 | 状态 |
|---|------|------|
| 1 | 安装依赖 `playwright` / `cryptography` / `python-dotenv` 并确认 Chromium 可用 | ✅ |
| 2 | 生成 Fernet 主密钥，创建 `.env.example` 与 `.env` | ✅ |
| 3 | `rpa/config.py` 环境配置加载 | ✅ |
| 4 | `rpa/crypto.py` 加解密与脱敏 | ✅ |
| 5 | `rpa/selectors.py` 选择器集中管理 | ✅ |
| 6 | `rpa/browser.py` Playwright 持久化会话 + 登录 + 人工验证等待 + 金额提取 | ✅ |
| 7 | `rpa/qianniu.py` 千牛抓取（平台扣费 / 运费险 / 订单级卖家服务费） | ✅ |
| 8 | `rpa/alimama.py` 阿里妈妈抓取（直通车 / 引力魔方 / 万相台 / 其它） | ✅ |
| 9 | `rpa/runner.py` 常驻工作线程 + 任务状态机 + 幂等写入 | ✅ |
| 10 | `models.py` 新增 `PlatformAccount` / `RPATask` / `StorePlatformExpense` / `SessionCookie` | ✅ |
| 11 | `schemas.py` 新增账号 / 任务 / 纯利润 / 费用 schema | ✅ |
| 12 | `routes/credentials.py` 账号 CRUD + 测试登录 | ✅ |
| 13 | `routes/rpa_tasks.py` 任务创建 / 查询 / 取消 | ✅ |
| 14 | `routes/profit_analysis.py` 纯利润聚合 + 费用 CRUD | ✅ |
| 15 | `main.py` 注册路由 + lifespan 启动 RPA 工作线程 | ✅ |
| 16 | 前端 API 模块 `credentials.js` / `rpa_tasks.js` / `profit.js` | ✅ |
| 17 | `AccountManage.vue` 账号管理页 | ✅ |
| 18 | `PureProfitAnalysis.vue` 纯利润主页面 | ✅ |
| 19 | 路由 + 导航菜单接入 | ✅ |
| 20 | 后端 API 冒烟测试（全端点） | ✅ |
| 21 | 前端 `npm run build` 验证 | ✅ |
| 22 | spec / plan / tasks 文档 | ✅ |

## 后续待办（未纳入本次）

| # | 事项 | 说明 |
|---|------|------|
| A | 千牛 / 阿里妈妈选择器实测校准 | 首次真实抓取时需按实际页面结构调整 `rpa/selectors.py`，失败时截图在 `rpa_screenshots/` |
| B | 千牛财务页账期切换 | 当前抓取页面当前账期；如需回溯历史月，需在 `qianniu.py` 增加日期选择器操作 |
| C | `OrderList.vue` 误导性「利润」列 | 显示 `实付 − 退款` 但标注为利润，建议改名或接真实毛利 |
| D | `PurchaseOrder.shipping_fee` 纳入 SKU 成本 | 采购运费当前未计入成本 |
| E | 定时抓取 | 如需每日自动跑，可引入 APScheduler |
| F | `SessionCookie` 表启用 | 当前 Playwright profile 自行管理登录态，该表暂未使用 |
