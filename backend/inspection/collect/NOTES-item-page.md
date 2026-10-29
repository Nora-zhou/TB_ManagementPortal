# 商品页匿名采集探路结论（T0 · 2026-10-29）

探针：`python -m inspection.collect.probe --item <id> [--page pc|h5] [--url <完整URL>]`
环境：Playwright Chromium 1.58，独立 profile `browser_data/account-9001`，
测试商品：`1052810876450`（本店在售淘宝商品）。

## 结论：四条匿名路径全部拿不到商品数据

| # | 入口 | 行为 | 证据 |
|---|---|---|---|
| 1 | `item.taobao.com/item.htm?id=` (PC) | **强制跳登录墙** | 最终 URL → `login.taobao.com/havanaone/login/login.htm?...redirectURL=...pc-detail-ssr-2025..._____tmd_____...`；headless 与 headed 结果一致 |
| 2 | `detail.tmall.com/item.htm?id=` (天猫 PC) | **强制跳登录墙** | 同上（SSR 2025 同一套） |
| 3 | `detail.m.tmall.com/item.htm?id=` (天猫 H5) | **强制跳登录墙** | 同上 |
| 4 | `main.m.taobao.com/security-h5-detail/home?id=` | 不跳登录，**数据静默失败** | 页面骨架 + JS 加载成功，0 个数据 XHR，HTML 无商品数据 |
| 5 | `h5.m.taobao.com/awp/core/detail.htm?id=` (老版 H5) | 不跳登录，**数据静默失败** | console 显示 `loadHtmlSuccess sellerType=C` → `pageInit` → `state undefined` + 连续 Error；mtop 详情接口匿名拿不到 token 链 |

## 关键判断

1. **headless 不是主因**：有头/无头行为一致，排除浏览器特征因素。
2. **这是平台策略，不是反爬随机波动**：PC 侧是 `pc-detail-ssr-2025` + `_____tmd_____` 反爬中间页强制登录；H5 侧 mtop token 流程匿名走不通。
3. **v2 计划的关键假设失效**：「商品详情页是公开页面，不需要登录」不成立（至少 2026-10 起不成立）。
4. 继续硬碰（伪造 cookie 链 / 解 mtop 签名 / 小号登录）= 高维护成本 + 高封号风险，
   按 G01 纪律**不在 I01 做**。

## 决策更新（2026-10-29 下午）：改用「检测专用 profile + 人工扫码登录」

用户决策：不用 API/手工导入，走浏览器登录态采集 —— 打开检测专用浏览器，
人工扫码登录一次，后续采集复用登录态。

实测结论（登录后，account-9001 profile）：
- **headless 首次访问触发滑块**（风控）；headed 正常。
- **详情数据不在 XHR 里，而在 SSR HTML 内嵌的 `window.__ICE_APP_CONTEXT__`**：
  - 主接口未出现 `mtop.taobao.pcdetail.data.get`，数据由服务端直出。
  - 提取锚点：`var b = {...};for (var k in a) {b[k] = a[k]}` 中的 JSON。
- 字段映射（实测已验证）：
  - 标题 `loaderData.home.data.res.item.title`
  - 主图 `...item.images`（5 张，`img.alicdn.com` 完整 URL）
  - 月销 `...item.vagueSellCount` + `componentsVO.titleVO.salesDesc`（"月销 12"）
  - 价格 `componentsVO.priceVO.price.priceMoney`（**单位：分**，如 "4990"）
  - 券后价 `priceVO.extraPrice.priceMoney`（如 "3991"）
  - 评价数 `componentsVO.rateVO.totalCount`
  - SKU `skuCore.sku2info`（`{quantity, price:{priceMoney}, logisticsTime}`，quantity=库存）
  - 服务 `componentsVO.deliveryVO.agingDesc`（"48小时内发货"）
  - 详情页地址 `item.pcADescUrl`（`market.m.taobao.com/app/detail-project/desc/...`，
    二次请求其内容数 `<img>` 即详情图数）

## 可行的替代数据源（按 ROI 排序）

| 方案 | 覆盖范围 | 成熟度 | 风险 |
|---|---|---|---|
| A. TOP API（`taobao.item.get` 扩 fields） | 自有店 + 利润版授权客户店 | 仓库已有 `taobao_client.py` + 生产路由在用 | 低，需核 fields 权限 |
| B. 手工 Excel 导入 → 工具只做出报告 | 任何店铺（基础版客户/竞品） | 可仿照现有订单/商品导入模式 | 无 |
| C. 小号登录态采集 | 全部 | 无 | 高：风控关联主账号，违反隔离原则，不做 |

## 对迭代计划的影响

- I01（页面采集）**暂停**，等数据源决策；
- 若选 A 优先：`collect --item --source api`（原 I04）提前，I01 的 fetch/parse 结构保留给 B 的 Excel 导入复用；
- 「商品内容采集」从「公开页 RPA」重新定义为「API + 手工导入」双通道。

## 复现命令

```powershell
cd backend
python -m inspection.collect.probe --item 1052810876450                    # PC → 登录墙
python -m inspection.collect.probe --item 1052810876450 --page h5          # H5 → 静默失败
python -m inspection.collect.probe --item 1052810876450 --headed           # 排除 headless 因素
```
