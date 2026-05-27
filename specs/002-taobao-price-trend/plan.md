# Implementation Plan: 淘宝店铺商品价格走势平台

**Branch**: `002-taobao-price-trend` | **Date**: 2026-05-25 | **Spec**: [spec.md](./spec.md)

## Summary

在现有 FastAPI + Vue 3 技术栈之上，新增独立的商品价格走势模块。后端扩展两张 SQLite 表（`product`、`price_snapshot`），提供商品导入（CSV / 淘宝开放平台 API）、价格快照记录、列表检索和走势查询等 REST 接口。前端新增四个页面级组件，使用 Apache ECharts 渲染价格折线图。

## Technical Context

**Language/Version**: Python 3.11+, Node.js 18+

**Primary Dependencies**:
- Backend 新增: `python-multipart`（CSV 文件上传）、`httpx`（调用淘宝开放平台 API）
- Frontend 新增: `echarts`、`vue-echarts`（价格走势折线图）

**Storage**: SQLite（通过现有 SQLModel 引擎，零配置，文件存储于 `backend/database.db`）

**Target Platform**: 本地单用户工具，无需认证

**Performance Goals**:
- 商品列表 API（含分页）< 200ms
- 快照记录：每件商品独立 API 调用，总耗时取决于商品数量，前端显示进度

**Constraints**:
- 不引入新数据库引擎，继续使用 SQLite
- 每件商品最多保留 365 条快照，超出后自动删除最旧记录
- CSV 必填字段：`item_id`、`name`、`price`、`url`

## Architecture Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| 图表库 | Apache ECharts (`vue-echarts`) | 中文社区成熟，折线图/Tooltip 开箱即用，bundle 可按需加载 |
| CSV 解析 | Python 标准库 `csv` + `python-multipart` | 无额外依赖，足够处理简单四字段格式 |
| 淘宝 API 调用 | `httpx` 异步 HTTP 客户端 | 已规划在 requirements 中；淘宝 TOP REST API 使用 HMAC-MD5 签名 |
| 快照触发 | 手动触发（MVP），后端串行调用淘宝 API | 避免引入 Celery/APScheduler 等调度依赖 |
| 快照保留 | 写入时检查数量，超 365 条删除最旧 | 简单可靠，无需独立清理任务 |
| 路由扩展 | 新增 `routes/products.py`、`routes/snapshots.py` | 保持现有 `routes/tasks.py` 不变，关注点分离 |

## Project Structure

### Documentation

```text
specs/002-taobao-price-trend/
├── spec.md          # Feature specification
├── plan.md          # This file
├── contracts/
│   └── api.md       # API endpoint contracts
└── tasks.md         # Implementation tasks
```

### Source Code 变更

```text
backend/
├── main.py                  # 新增注册 products_router、snapshots_router
├── models.py                # 新增 Product、PriceSnapshot 表
├── schemas.py               # 新增 ProductRead、SnapshotRead 等 schema
├── routes/
│   ├── tasks.py             # 不变
│   ├── products.py          # 新增：商品 CRUD、导入端点
│   └── snapshots.py         # 新增：快照触发、历史查询端点
└── requirements.txt         # 新增 python-multipart、httpx

frontend/src/
├── App.vue                  # 新增导航链接至商品列表页
├── api/
│   ├── tasks.js             # 不变
│   ├── products.js          # 新增：商品相关 API 调用
│   └── snapshots.js         # 新增：快照相关 API 调用
└── components/
    ├── (现有组件不变)
    ├── ProductList.vue      # 商品列表（搜索、筛选、分页）
    ├── ProductImport.vue    # 导入页面（CSV 上传 + Taobao Token）
    ├── ProductDetail.vue    # 商品详情 + 价格走势图
    └── PriceChart.vue       # ECharts 折线图封装组件
```

## Data Models

```python
class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    taobao_item_id: str = Field(unique=True, index=True)   # 淘宝商品ID，用于去重
    name: str = Field(max_length=500)
    url: Optional[str] = Field(default=None, max_length=1000)
    current_price: Optional[float] = None                  # 最新快照价格（冗余存储，提速列表查询）
    alert_low: Optional[float] = None                      # 价格下限预警
    alert_high: Optional[float] = None                     # 价格上限预警
    last_updated: Optional[datetime] = None                # 最近一次快照时间
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PriceSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    price: float
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

**快照保留逻辑**（写入时执行）：
```python
# 写入新快照后，删除该商品超出 365 条的最旧记录
def trim_snapshots(session, product_id: int, limit: int = 365):
    count = session.exec(
        select(func.count()).where(PriceSnapshot.product_id == product_id)
    ).one()
    if count > limit:
        oldest = session.exec(
            select(PriceSnapshot)
            .where(PriceSnapshot.product_id == product_id)
            .order_by(PriceSnapshot.recorded_at.asc())
            .limit(count - limit)
        ).all()
        for snap in oldest:
            session.delete(snap)
```

## API Endpoints Summary

| Method | Path | 描述 |
|--------|------|------|
| POST | /api/products/import/csv | 上传 CSV 文件，批量导入/更新商品 |
| POST | /api/products/import/taobao | 通过淘宝 Token 拉取店铺商品列表 |
| GET | /api/products | 获取商品列表（分页、关键词搜索、价格区间筛选） |
| GET | /api/products/{id} | 获取单个商品详情（含预警阈值） |
| PUT | /api/products/{id}/alert | 设置/更新价格预警阈值 |
| DELETE | /api/products/{id} | 删除商品及其所有快照 |
| POST | /api/snapshots | 触发全量快照（实时调用淘宝 API 拉取最新价格） |
| GET | /api/products/{id}/snapshots | 获取该商品的全部价格快照历史 |

详细请求/响应格式见 [contracts/api.md](./contracts/api.md)。

## 淘宝开放平台集成

- **接口**: `taobao.items.onsale.get`（获取在售商品列表）、`taobao.item.get`（获取单品最新价格）
- **认证**: 用户提供 Session Key（OAuth 授权后获得）；后端存储于内存或本地配置文件（不持久化到数据库，避免敏感信息泄露）
- **签名**: HMAC-MD5，按淘宝 TOP 规范拼接参数后签名
- **错误处理**: Token 失效返回 401；网络超时返回 502 并附带提示信息

## Frontend 组件设计

| 组件 | 路由 | 核心功能 |
|------|------|----------|
| `ProductList.vue` | `/products` | 商品列表表格、搜索框、价格区间筛选、分页、"记录快照"按钮、预警标识 |
| `ProductImport.vue` | `/products/import` | Tab 切换（CSV 上传 / Taobao Token 输入）、导入结果提示 |
| `ProductDetail.vue` | `/products/:id` | 商品基本信息、`PriceChart` 图表、阈值设置表单 |
| `PriceChart.vue` | （子组件） | ECharts 折线图，接收 `snapshots[]` props，含参考线（alert_low/high）和 Tooltip |

## Local Development

```bash
# Backend — 安装新依赖
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend — 安装图表依赖
cd frontend
npm install echarts vue-echarts
npm run dev
```

Frontend: http://localhost:5173 | Backend API: http://localhost:8000 | Swagger UI: http://localhost:8000/docs
