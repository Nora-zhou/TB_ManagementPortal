# Implementation Plan: UX 功能增强

**Branch**: `004-ux-enhancements` | **Date**: 2026-05-26 | **Spec**: [spec.md](./spec.md)

## Summary

本次迭代纯属存量代码改造，不引入新数据表和新依赖。四项变更范围清晰、互相独立：
1. **仪表盘时间筛选**：后端补全 `/stats/status` 的日期过滤参数，前端在 `OrderDashboard.vue` 增加筛选条对所有 API 调用传入 `start_date`/`end_date`。
2. **Goods 目录导入**：后端新增一个目录扫描端点，替代现有浏览器文件上传端点；前端 `ProductImport.vue` 改为单按钮触发。
3. **合并导入菜单**：新增 `DataImport.vue` 容器组件（内含 Tab），将现有 `ProductImport.vue` 和 `OrderImport.vue` 作为 Tab 面板嵌入；调整路由与导航栏。
4. **商品列表近90天销量**：在 `GET /api/products` 响应中新增聚合字段 `sold_90d`，前端 `ProductList.vue` 增加对应列。依赖 Spec 005 的 `SubOrder` 表（表不存在或为空时 `sold_90d` 默认为 0）。

## Technical Context

**Language/Version**: Python 3.11+, Node.js 18+

**Primary Dependencies**: 无新增依赖（复用现有 `pathlib`、`csv`、`vue-router`）

**Storage**: SQLite（现有 `product` 表已具备 `taobao_item_id` 唯一键，可直接 upsert）

**Target Platform**: 本地单用户工具，无需认证

**Performance Goals**:
- 统计 API 加日期过滤后响应 < 300ms（万级数据）
- Goods 目录导入：100 条以内同步完成，无需进度条

**Constraints**:
- 不修改数据库 schema（`product` 表 upsert 逻辑复用现有 `import/csv` 代码）
- `POST /api/products/import/csv` 端点保留但不在前端暴露（避免破坏已有测试）
- 走势图粒度（日/周/月）切换逻辑不变

## Architecture Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| 近 N 天日期计算 | 前端计算 `today 00:00:00 - N days`，以 `YYYY-MM-DD` 格式传给后端 | 后端现有端点已接受 `start_date`/`end_date` 字符串参数，无需改接口签名 |
| 月份选择器 | `<input type="month">` 原生控件 | 无需引入日期选择库；兼容 Chromium 内核（本地工具） |
| status 端点日期过滤 | 在 `order_status_dist()` 函数中补加 `start_date`/`end_date` 参数，复用已有 `_apply_date_filter` 模式 | 与其他 stats 端点保持一致 |
| Goods 扫描端点 | `POST /api/products/import/from-goods-dir`（无请求体） | POST 语义符合"触发写操作"；不传文件，后端自行读目录 |
| 目录路径 | `pathlib.Path(__file__).parent.parent / "data" / "Goods"` | 相对于 `routes/products.py` 的两级父目录，与现有 `data/` 目录层级一致 |
| Goods upsert 策略 | 商品 ID 不存在 → `imported++`；存在 → 更新 name/price → `updated++` | 与 spec 中 `{imported, updated}` 返回值对齐 |
| DataImport 路由 | 新增 `/import`，删除 `/products/import` 和 `/orders/import` | 不做重定向（内部工具，无需向后兼容） |
| Tab 实现 | `DataImport.vue` 持有 `activeTab` ref，条件渲染 `ProductImport.vue` 和 `OrderImport.vue` | 复用现有组件，最小改动 |
| sold_90d 聚合位置 | 后端 `list_products()` 分页取出商品后，用一条 GROUP BY 聚合查询批量获取 sold_90d，避免 N+1 | 前端只需直接读字段，零额外请求 |
| sold_90d 过滤条件 | `status = '交易成功' AND refund_amount = '无退款申请' AND paid_at >= today - 90d` | 与 Spec 005 价格走势的过滤逻辑一致 |
| sold_90d 空值降级 | SubOrder 表不存在（`OperationalError`）或查询结果为 null 时，`sold_90d` 置为 `0` | 保证在 Spec 005 数据未导入时商品列表正常渲染 |

## Project Structure

### Documentation

```text
specs/004-ux-enhancements/
├── spec.md
├── plan.md          # 本文件
├── contracts/
│   └── api.md
└── tasks.md
```

### Source Code 变更

```text
backend/
└── routes/
    ├── products.py    # 新增 import_from_goods_dir 端点；保留 import_csv 端点
    └── orders.py      # order_status_dist() 补加 start_date / end_date 参数

frontend/src/
├── main.js            # 路由调整：新增 /import，删除 /products/import 和 /orders/import
├── App.vue            # 导航栏：删除「导入商品」「导入订单」，新增「基础数据导入」
├── components/
│   ├── DataImport.vue       # 新增：Tab 容器，内嵌商品导入和订单导入
│   ├── ProductImport.vue    # 改造：移除文件上传控件，改为「从 Goods 目录导入」按钮
│   └── OrderDashboard.vue   # 改造：新增时间筛选条，所有 API 调用携带 dateRange 参数
└── api/
    └── products.js          # 新增 importFromGoodsDir() 调用新端点

backend/
├── schemas.py               # ProductRead 新增 sold_90d: int = 0 字段
└── routes/
    └── products.py          # list_products() 批量聚合 sold_90d；_product_to_read() 接受并写入 sold_90d

frontend/src/components/
└── ProductList.vue          # 新增「近90天销量」列（表头 + 单元格）
```

## API Endpoint Overview

### 新增端点

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/products/import/from-goods-dir` | 扫描 `data/Goods/` 目录，upsert 所有 CSV，返回 `{imported, updated, errors}` |

### 修改端点

| Method | Path | 变更说明 |
|--------|------|---------|
| GET | `/api/orders/stats/status` | 新增 `start_date` / `end_date` 可选查询参数 |
| GET | `/api/products` | 响应 `items[*]` 新增聚合字段 `sold_90d: int`（过去90天符合条件的 quantity 合计） |

### 不变端点（已支持日期参数）

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/orders/stats/summary` | 已有 `start_date`/`end_date` |
| GET | `/api/orders/stats/trend` | 已有 `start_date`/`end_date` |
| GET | `/api/orders/stats/top-products` | 已有 `start_date`/`end_date` |

## Data Model

**无数据表变更。** `product` 表结构不变；`sold_90d` 是运行时聚合值，不持久化。

### `ProductRead` schema 变更（`backend/schemas.py`）

```python
class ProductRead(BaseModel):
    id: int
    taobao_item_id: str
    name: str
    url: Optional[str]
    current_price: Optional[float]
    alert_low: Optional[float]
    alert_high: Optional[float]
    last_updated: Optional[datetime]
    alert_status: str
    snapshot_count: Optional[int] = None
    sold_90d: int = 0   # 新增：近90天卖出件数（来自 SubOrder 聚合）
```

## Frontend State Design（Story 1）

`OrderDashboard.vue` 新增时间筛选状态：

```js
// 快捷模式: 'days7' | 'days30' | 'days90' | 'month' | 'custom'
const filterMode = ref('days30')

// 实际传给后端的日期字符串
const startDate = ref('')   // 'YYYY-MM-DD'
const endDate = ref('')     // 'YYYY-MM-DD'

// 月份选择器绑定值
const selectedMonth = ref('')  // 'YYYY-MM'

// 自定义日期输入
const customStart = ref('')
const customEnd = ref('')
```

**日期计算规则**：

| 模式 | startDate | endDate |
|------|-----------|---------|
| days7 | `today - 6d`（00:00:00） | `today` |
| days30 | `today - 29d` | `today` |
| days90 | `today - 89d` | `today` |
| month | `YYYY-MM-01` | `YYYY-MM-{lastDay}` |
| custom | 用户输入 | 用户输入 |

所有 load* 函数统一接收 `{ start_date, end_date }` 并透传至 API 调用。

## Key Implementation Notes

### Story 2 - Goods 目录导入端点

```python
# backend/routes/products.py（新增）
GOODS_DIR = Path(__file__).parent.parent / "data" / "Goods"

@router.post("/import/from-goods-dir", response_model=GoodsDirImportResponse)
def import_from_goods_dir(session: SessionDep) -> GoodsDirImportResponse:
    # 1. 检查目录存在性
    # 2. 收集所有 *.csv 文件
    # 3. 逐文件解析，跳过缺少 item_id 列的文件并记录 errors
    # 4. 每条记录 upsert：不存在 → imported++，存在 → 更新 name/price → updated++
    # 5. 返回 {imported, updated, errors: [{file, reason}]}
```

新增 `GoodsDirImportResponse` schema：
```python
class GoodsDirImportResponse(SQLModel):
    imported: int
    updated: int
    errors: list[dict]   # [{file: str, reason: str}]
```

### Story 3 - DataImport.vue 结构

```vue
<!-- DataImport.vue -->
<template>
  <div class="data-import">
    <div class="tab-bar">
      <button :class="{active: activeTab==='product'}" @click="activeTab='product'">商品导入</button>
      <button :class="{active: activeTab==='order'}"   @click="activeTab='order'">订单导入</button>
    </div>
    <ProductImport v-if="activeTab==='product'" />
    <OrderImport   v-if="activeTab==='order'" />
  </div>
</template>
```

路由变更：
```js
// 删除
{ path: '/products/import', component: ProductImport },
{ path: '/orders/import',   component: OrderImport },

// 新增
{ path: '/import', component: DataImport },
```

### Story 5 - 商品列表近90天销量

**后端：`list_products()` 批量聚合**

```python
# backend/routes/products.py
from datetime import date, timedelta

def list_products(session: SessionDep, ...) -> ProductListResponse:
    # ... 现有分页查询，得到 products 列表 ...

    # 批量聚合 sold_90d（一条 SQL，避免 N+1）
    cutoff = datetime.now() - timedelta(days=90)
    item_ids = [p.taobao_item_id for p in products]
    try:
        rows = session.exec(
            select(SubOrder.taobao_item_id, func.sum(SubOrder.quantity))
            .where(
                SubOrder.taobao_item_id.in_(item_ids),
                SubOrder.status == "交易成功",
                SubOrder.refund_amount == "无退款申请",
                SubOrder.paid_at >= cutoff,
            )
            .group_by(SubOrder.taobao_item_id)
        ).all()
        sold_map = {tid: qty for tid, qty in rows}
    except Exception:
        sold_map = {}   # SubOrder 表不存在时降级

    return ProductListResponse(
        total=total, page=page, page_size=page_size,
        items=[
            _product_to_read(p, session, sold_90d=sold_map.get(p.taobao_item_id, 0))
            for p in products
        ],
    )
```

**`_product_to_read()` 签名扩展**

```python
def _product_to_read(
    product: Product,
    session: Session,
    include_snapshot_count: bool = False,
    sold_90d: int = 0,          # 新增参数
) -> ProductRead:
    ...
    return ProductRead(
        ...,
        sold_90d=sold_90d,
    )
```

**前端：`ProductList.vue` 新增列**

```html
<!-- 表头 -->
<th>近90天销量</th>

<!-- 数据行 -->
<td>{{ item.sold_90d ?? 0 }}</td>
```

列位置：插入「近90天销量」列于「当前价格」之后（即第三列顺序：商品 ID / 商品标题 / 当前价格 / 近90天销量 / 最近更新 / 预警）。
