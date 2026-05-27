# Implementation Plan: 订单数据分析平台

**Branch**: `003-order-analytics` | **Date**: 2026-05-25 | **Spec**: [spec.md](./spec.md)

## Summary

在现有 FastAPI + Vue 3 技术栈之上，新增独立的订单数据分析模块。后端新增 `Order` SQLite 表，提供 xlsx 文件导入、订单列表分页查询、多维度统计聚合等 REST 接口。前端新增导入页、列表页和分析仪表盘，使用 Apache ECharts 渲染销售走势折线图、订单状态饼图和热销商品排行。

## Technical Context

**Language/Version**: Python 3.11+, Node.js 18+

**Primary Dependencies**:
- Backend 新增: `openpyxl`（解析淘宝导出 xlsx 文件）
- Frontend: 复用已有 `echarts`、`vue-echarts`（spec 002 已安装）

**Storage**: SQLite（沿用现有 SQLModel 引擎，新增 `order` 表）

**Target Platform**: 本地单用户工具，无需认证

**Performance Goals**:
- 订单列表 API（含分页）< 300ms（1 万条以内）
- xlsx 导入：1756 条约 2–3 秒，超 3000 条显示前端进度条

**Constraints**:
- 不引入新数据库引擎，继续使用 SQLite
- 仅支持淘宝标准导出 xlsx 格式（10 列固定顺序）
- 统计口径：销售额仅计「交易成功」，退款额计所有状态的「退款金额」字段
- 商品标题含逗号时按逗号分割，各子标题独立参与热销排行聚合

## Architecture Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| xlsx 解析库 | `openpyxl` | 纯 Python，无需 C 扩展；淘宝导出文件无复杂格式 |
| 聚合查询 | SQLite `strftime` + `GROUP BY` | 避免引入 Pandas，减少依赖；数据量级（万级）SQLite 足够 |
| 热销排行 | 应用层按逗号拆分标题后 Python 聚合 | 数据库层难以按逗号分割字符串，Python 拆分更灵活 |
| 图表复用 | 复用 spec 002 安装的 `vue-echarts` | 无需重复安装，保持 bundle 一致 |
| 路由扩展 | 新增 `routes/orders.py` | 与现有 products/snapshots/tasks 路由保持同等层级 |
| 进度反馈 | 前端轮询 `GET /api/orders/import/progress` | 避免 WebSocket 复杂度；文件大时每 500ms 轮询一次 |

## Project Structure

### Documentation

```text
specs/003-order-analytics/
├── spec.md          # Feature specification
├── plan.md          # This file
├── contracts/
│   └── api.md       # API endpoint contracts
└── tasks.md         # Implementation tasks
```

### Source Code 变更

```text
backend/
├── main.py                  # 注册 orders_router
├── models.py                # 新增 Order 表
├── schemas.py               # 新增 Order 相关 schema
├── routes/
│   ├── tasks.py             # 不变
│   ├── products.py          # 不变
│   ├── snapshots.py         # 不变
│   └── orders.py            # 新增：订单导入、列表、统计端点
└── requirements.txt         # 新增 openpyxl

frontend/src/
├── App.vue                  # 新增导航链接至订单分析页
├── api/
│   ├── tasks.js             # 不变
│   ├── products.js          # 不变
│   ├── snapshots.js         # 不变
│   └── orders.js            # 新增：订单相关 API 调用
└── components/
    ├── (现有组件不变)
    ├── OrderImport.vue      # xlsx 文件上传，含进度条
    ├── OrderList.vue        # 订单列表（状态筛选、关键词、日期范围、分页）
    └── OrderDashboard.vue   # 分析仪表盘（走势图 + 饼图 + 退款卡片 + 排行榜）
```

## API Endpoint Overview

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/orders/import` | 上传 xlsx，返回导入结果 |
| GET | `/api/orders/import/progress` | 轮询导入进度 |
| GET | `/api/orders` | 订单列表，支持分页/状态/关键词/日期筛选 |
| GET | `/api/orders/stats/summary` | 总览数字卡片（总销售额、退款率等） |
| GET | `/api/orders/stats/trend` | 销售/退款走势，支持 day/week/month 维度 |
| GET | `/api/orders/stats/status` | 订单状态分布饼图数据 |
| GET | `/api/orders/stats/top-products` | 热销商品排行，支持 revenue/count 排序 |

## Data Model

### Order 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| order_id | TEXT UNIQUE | 订单编号（淘宝唯一） |
| payment_id | TEXT | 支付单号 |
| payment_detail | TEXT | 支付详情（原文存储） |
| total_amount | REAL | 总金额（元） |
| buyer_paid | REAL | 买家实付金额（元） |
| status | TEXT | 订单状态 |
| created_at | DATETIME | 订单创建时间 |
| product_title | TEXT | 商品标题（原始，含逗号） |
| seller_fee | REAL | 卖家服务费（元） |
| refund_amount | REAL | 退款金额（元） |
| imported_at | DATETIME | 本地导入时间（服务端写入） |
