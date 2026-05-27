# Implementation Plan: 商品订单实付价格走势

**Branch**: `005-product-order-price-trend` | **Date**: 2026-05-26 | **Spec**: [spec.md](./spec.md)

## Summary

在现有 FastAPI + Vue 3 技术栈之上，新增 `SubOrder` 表及对应的子订单导入端点，并在商品详情页增加「订单实付价格走势」散点图（含线性回归趋势线），与现有快照价格走势图上下并列展示。本次迭代不修改任何现有表结构，与旧 `Order` 表完全并存。

---

## Technical Context

**Language/Version**: Python 3.11+, Node.js 18+

**Primary Dependencies**:
- Backend 新增: 无（已有 `openpyxl`、`SQLModel`、`FastAPI`）
- Frontend: 复用已有 `echarts`、`vue-echarts`（002 起已安装）；趋势线使用 `echarts-stat` 包

**Storage**: SQLite（新增 `suborder` 表，沿用现有 SQLModel 引擎）

**Target Platform**: 本地单用户工具，无认证需求

**Performance Goals**:
- 价格走势 API（≤1000 点）< 500ms
- xlsx 导入（2391 行）< 10s，同步返回，无需进度轮询
- 时间范围切换图表刷新 < 1s

**Constraints**:
- 不修改现有 `Order` / `Product` / `PriceSnapshot` 表
- 仅接受 15 列子订单格式 xlsx（新格式），现有旧主订单导入入口保持不变
- 移动端适配不在范围内

---

## Architecture Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| 新表命名 | `SubOrder`（SQLite 表名 `suborder`） | 区分旧 `Order` 表；Python 类名语义清晰 |
| 趋势线实现 | `echarts-stat` LinearRegression + ECharts `dataset.transform` | 纯前端计算，无需后端额外聚合端点；官方维护，专为统计场景 |
| 散点图组件 | 新建 `OrderPriceChart.vue`，独立于 `PriceChart.vue` | 两种图表数据源和交互逻辑不同，不复用现有组件 |
| 子订单导入路由 | `POST /api/sub-orders/import` | 与现有 `/api/orders/import` 严格分离，避免误用旧格式 |
| 价格走势查询路由 | `GET /api/products/{id}/order-price-series` | 跟随商品资源层级，符合 RESTful 惯例 |
| 幂等键 | `sub_order_id`（子订单编号） | Spec 明确要求 upsert 策略 |
| 退款过滤 | 后端 SQL `WHERE refund_amount = '无退款申请'` | 字符串比较，简单可靠，无需前端关心 |
| 状态过滤 | 后端 SQL `WHERE status = '交易成功'` | 仅有效成交参与走势 |
| 单件均价计算 | 后端返回原始 `buyer_paid` 和 `quantity`，前端计算 `unit_price = buyer_paid / Math.max(quantity, 1)` | 数据库存原始值更利于后续分析；quantity=0 时前端展示 ¥0.00 |
| 数据点上限 | 后端 `LIMIT 1000`，超出时响应含 `truncated: true` | Spec FR-008 明确要求 |
| 时间范围筛选 | `days` 查询参数（`30` / `90` / `all`），后端计算截止时间 | 与现有订单统计 API 模式保持一致 |
| 时区 | 后端存储 naive datetime（本地时间），前端 `new Date()` 展示 | 淘宝导出文件为 CST 本地时间，与浏览器时区一致，无需转换 |
| SKU 颜色映射 | 前端按 `product_attr` 值的出现顺序分配预设调色板（10 色），超出数量循环取色 | 纯前端逻辑，无需后端改动；ECharts Legend 自动使用 series 颜色 |
| 图表类型切换 | `chartType` ref（`'scatter'` / `'line'`）控制 ECharts `option`，切换时重新 `setOption` | 纯前端状态，无需重新请求数据；切换延迟 < 100ms |
| 折线图 SKU 分组 | 前端按 `product_attr` 分组，每组生成独立 `LineSeries`，各自使用对应颜色 | 使每条 SKU 线颜色与散点图一致，用户认知一致 |
| 折线图单点 SKU | 仅 1 个点的 SKU：`LineChart` series 使用 `showSymbol: true`，`symbolSize: 6` | ECharts 单点折线不报错，视觉可见 |

---

## Constitution Check

| 原则 | 符合 | 说明 |
|------|------|------|
| Simplicity First | ✅ | 无新后端依赖；前端仅增 `echarts-stat` |
| Type Safety | ✅ | 新增 `SubOrder` SQLModel 模型 + Pydantic response schema |
| API Contract Clarity | ✅ | 两个新端点均有 OpenAPI 类型注解 |
| Test-First Where Practical | ✅ | 新增 `test_sub_orders.py` 覆盖导入和查询逻辑 |
| Separation of Concerns | ✅ | 退款/状态过滤在后端；趋势线计算在前端 |
| Input Validation | ✅ | 必填列检查在导入端点，金额解析失败计入 errors |
| CORS / Secrets | ✅ | 无新配置需求 |

---

## Phase 0: Research

### 技术选型确认

#### ECharts 趋势线方案

**决策**: 使用 `echarts-stat` 包提供的 `ecStat.transform.regression` 作为 `dataset.transform`。

**理由**:
- ECharts 5 原生支持 `dataset.transform`，`echarts-stat` 是官方维护的统计扩展包
- 无需后端参与，纯前端 JS 计算线性回归
- 安装命令：`npm install echarts-stat`
- 注册方式：`echarts.registerTransform(ecStat.transform.regression)`

**替代方案放弃理由**:
- ECharts `markLine` 统计类型（`average`/`max`/`min`）不支持线性回归
- 手动在组件内计算最小二乘法可行但增加业务代码复杂度

#### SQLModel upsert 策略

**决策**: 沿用现有 `select → update or add` 模式（同 `Order` 导入）。

**理由**:
- `sub_order_id` 具有 `unique=True` 约束，select 查找性能有保证（已有索引）
- 与现有导入逻辑模式一致，降低代码差异

---

## Phase 1: Design

### Data Model

#### 新增：SubOrder 模型（`backend/models.py`）

```python
class SubOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sub_order_id: str = Field(unique=True, index=True, max_length=64)
    main_order_id: str = Field(max_length=64)
    taobao_item_id: str = Field(index=True, max_length=64)
    product_title: str = Field(max_length=500)
    product_price: Optional[float] = None
    quantity: int = Field(default=1)
    product_attr: Optional[str] = Field(default=None, max_length=500)
    status: str = Field(max_length=64)
    payment_id: Optional[str] = Field(default=None, max_length=64)
    buyer_paid: float
    refund_amount: str = Field(max_length=64)  # "无退款申请" 或金额字符串
    created_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    imported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

**索引说明**:
- `sub_order_id`：unique + index（upsert 查找键）
- `taobao_item_id`：index（价格走势查询过滤键）

**字段与 Excel 列名映射**:

| Excel 列名 | 模型字段 |
|-----------|---------|
| 子订单编号 | `sub_order_id` |
| 主订单编号 | `main_order_id` |
| 商品ID | `taobao_item_id` |
| 商品标题 | `product_title` |
| 商品价格 | `product_price` |
| 购买数量 | `quantity` |
| 商品属性 | `product_attr` |
| 订单状态 | `status` |
| 支付单号 | `payment_id` |
| 买家实付金额 | `buyer_paid` |
| 退款金额 | `refund_amount` |
| 订单创建时间 | `created_at` |
| 订单付款时间 | `paid_at` |
| 淘鲜达渠道 | *(跳过，不存储)* |
| 分阶段信息 | *(跳过，不存储)* |

#### 无变更模型

`Product`、`PriceSnapshot`、`Order`、`Task` 均不变。

---

### Pydantic Schemas（`backend/schemas.py` 新增）

```python
class SubOrderImportResult(BaseModel):
    imported: int
    updated: int
    skipped: int
    errors: list[str]

class OrderPricePoint(BaseModel):
    created_at: datetime
    buyer_paid: float
    quantity: int
    product_attr: Optional[str]
    sub_order_id: str

class OrderPriceSeriesResponse(BaseModel):
    product_id: int
    taobao_item_id: str
    days: Optional[int]       # None = 全部
    total: int                # 匹配的有效子订单总数（过滤后，不受 1000 上限影响）
    truncated: bool           # 是否因超 1000 点被截断
    points: list[OrderPricePoint]
```

---

### Project Structure

```text
specs/005-product-order-price-trend/
├── spec.md
├── plan.md              # 本文件
├── contracts/
│   └── api.md
└── tasks.md             # (待生成)

backend/
├── models.py            # 新增 SubOrder 类
├── schemas.py           # 新增 SubOrderImportResult, OrderPricePoint, OrderPriceSeriesResponse
├── main.py              # 注册 sub_orders_router
└── routes/
    ├── sub_orders.py    # 新建：POST /api/sub-orders/import
    └── products.py      # 新增：GET /{id}/order-price-series 端点

frontend/src/
├── api/
│   ├── sub_orders.js    # 新建：importSubOrders(file)
│   └── products.js      # 新增：fetchOrderPriceSeries(id, days)
└── components/
    ├── OrderPriceChart.vue    # 新建：散点图 + 趋势线组件
    ├── ProductDetail.vue      # 改造：引入 OrderPriceChart，新增时间范围选择器
    └── DataImport.vue         # 改造：新增子订单导入 Tab
```

---

## API Endpoint Contracts

完整请求/响应规范见 [contracts/api.md](./contracts/api.md)。

### POST `/api/sub-orders/import`

- **Content-Type**: `multipart/form-data`，字段名 `file`，仅接受 `.xlsx`
- **必填列验证**: `子订单编号`、`商品ID`、`买家实付金额`、`订单状态`、`退款金额`、`订单创建时间`、`购买数量`；缺少任意一列返回 `422`
- **无效行定义**: `商品ID` 为空，或 `买家实付金额` 无法解析为 float；计入 `errors`，其余行继续处理
- **Upsert 逻辑**: 以 `sub_order_id` 为键，存在则 `updated++`，不存在则 `imported++`

**Response 200**:
```json
{
  "imported": 2300,
  "updated": 0,
  "skipped": 0,
  "errors": []
}
```

**Response 422**:
```json
{
  "detail": "文件缺少必填列：['商品ID', '买家实付金额']"
}
```

---

### GET `/api/products/{id}/order-price-series`

- **Path param**: `id` — Product 表主键（int）
- **Query param**: `days` — 可选，`30` / `90`，缺省或传 `all` 表示全部时间范围

**后端过滤条件**（按顺序应用）:
1. `SubOrder.taobao_item_id = Product.taobao_item_id`（join 条件）
2. `SubOrder.status = '交易成功'`
3. `SubOrder.refund_amount = '无退款申请'`
4. 若 `days` 为 `30` 或 `90`：`SubOrder.created_at >= now() - timedelta(days=int(days))`

**Response 200**:
```json
{
  "product_id": 42,
  "taobao_item_id": "844555963059",
  "days": 90,
  "total": 128,
  "truncated": false,
  "points": [
    {
      "created_at": "2026-03-01T14:23:00",
      "buyer_paid": 99.00,
      "quantity": 1,
      "product_attr": "颜色:红色;尺寸:M",
      "sub_order_id": "123456789"
    }
  ]
}
```

**Response 404**: Product 不存在
```json
{ "detail": "商品不存在" }
```

**截断示例**（总数超过 1000）:
```json
{
  "total": 1523,
  "truncated": true,
  "points": [ /* 按 created_at ASC 排序的前 1000 条 */ ]
}
```

---

## Frontend Component Design

### `OrderPriceChart.vue`

**Props**:
```js
defineProps({
  points: { type: Array, default: () => [] },    // OrderPricePoint[]
  truncated: { type: Boolean, default: false },
})
```

**本地状态**:
```js
const chartType = ref('scatter')  // 'scatter' | 'line'
```

**SKU 调色板**（10 色，循环取用）:
```js
const SKU_COLORS = [
  '#5470c6','#91cc75','#fac858','#ee6666','#73c0de',
  '#3ba272','#fc8452','#9a60b4','#ea7ccc','#a5a5a5'
]
// skuColorMap: computed from points，按 product_attr 首次出现顺序分配
const skuColorMap = computed(() => {
  const map = {}
  let idx = 0
  for (const p of props.points) {
    const key = p.product_attr ?? '未知规格'
    if (!(key in map)) map[key] = SKU_COLORS[idx++ % SKU_COLORS.length]
  }
  return map
})
```

**ECharts 注册**:
```js
import * as ecStat from 'echarts-stat'
import * as echarts from 'echarts/core'
echarts.registerTransform(ecStat.transform.regression)
use([ScatterChart, LineChart, GridComponent, TooltipComponent, LegendComponent,
     DatasetComponent, TransformComponent, CanvasRenderer])
```

**功能**:
1. 空状态：`points.length === 0` 时显示「暂无匹配订单数据，无法展示价格走势」
2. 右上角切换按钮：`散点图 | 折线图`，切换 `chartType` ref
3. **散点图模式（默认）**：
   - 每个 SKU 生成独立 `ScatterSeries`，使用 `skuColorMap` 中对应颜色，`name` 为 SKU 值（供 Legend 显示）
   - X 轴为 `created_at`（`new Date(p.created_at).toLocaleString('zh-CN')`），Y 轴为单件均价（`buyer_paid / Math.max(quantity, 1)`）
   - 趋势线：全量数据 `dataset[1]` 的 `transform: regression` 驱动第二个 `LineChart` series，颜色灰色，`symbolSize: 0`
4. **折线图模式**：
   - 每个 SKU 生成独立 `LineSeries`，按 `created_at` 升序排列数据点，使用 `skuColorMap` 对应颜色
   - 仅 1 个数据点的 SKU：`showSymbol: true`，`symbolSize: 6`，不报错
   - 趋势线逻辑同散点图模式
5. **Legend**：两种模式均显示 ECharts Legend，各 SKU 颜色与图例一致
6. Tooltip formatter：显示 `订单创建时间`、`单件均价`（¥）、`购买数量`、`商品属性`、SKU 颜色块
7. 截断 banner：`truncated` 为 true 时在图表上方显示黄色提示条

### `ProductDetail.vue` 改造要点

- 新增 `days` ref（默认 `'90'`），绑定 `<select>` 控件（选项：30 / 90 / all）
- `watch(days, fetchOrderData)` + `onMounted` 各触发一次
- 在快照走势图之后插入 `<h3>订单实付价格走势</h3>` + 选择器 + `<OrderPriceChart />`
- `OrderPriceChart` 内部管理 `chartType`，`ProductDetail` 不需感知切换状态

### `DataImport.vue` 改造要点

- 新增 Tab 选项「导入子订单」
- 文件上传控件 `accept=".xlsx"`
- 调用 `importSubOrders(file)`，展示 `{imported, updated, skipped, errors}` 结果
- 错误列表最多显示前 20 条

---

## Backend Implementation Notes

### `routes/sub_orders.py` 关键逻辑

```python
REQUIRED_COLUMNS = {
    "子订单编号", "主订单编号", "商品ID", "商品标题",
    "购买数量", "商品价格", "商品属性", "订单状态",
    "支付单号", "买家实付金额", "退款金额",
    "订单创建时间", "订单付款时间",
}

# Header 在第 1 行（rows[0]）
# 无效行：商品ID 为空 OR 买家实付金额 无法解析为 float
# quantity = 0 时存入 0，不视为无效行（Spec 明确）
# 单次 session.commit() 在所有行处理完毕后执行（性能优化）
```

### `routes/products.py` 新端点关键逻辑

```python
@router.get("/{product_id}/order-price-series", response_model=OrderPriceSeriesResponse)
def get_order_price_series(
    product_id: int,
    days: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
):
    # 1. 查 Product，not found → 404
    # 2. 构建 SubOrder 查询：taobao_item_id + status='交易成功' + refund_amount='无退款申请'
    # 3. 若 days in ("30","90")：加 created_at >= now - timedelta(days=int(days))
    # 4. total = COUNT(*)（不受 LIMIT 影响）
    # 5. points = query.order_by(created_at.asc()).limit(1000).all()
    # 6. truncated = total > 1000
```

---

## Test Plan

### Backend Tests (`backend/tests/test_sub_orders.py`)

| 测试用例 | 断言 |
|---------|------|
| 上传合法 xlsx（含 2391 行）→ 200 | `imported` == 有效行数，`errors` 为空或仅含预期无效行 |
| 重复导入同一文件 → 200 | `updated` == 行数，`imported` == 0 |
| 缺少必填列（如 `商品ID`）→ 422 | detail 包含缺失列名 |
| 含无效行（`商品ID` 为空）→ 200 | `errors` 计数正确，其余行已导入 |
| 退款行过滤 | `GET /order-price-series` 不返回 `refund_amount != '无退款申请'` 的点 |
| 非交易成功状态过滤 | 不返回非「交易成功」状态的点 |
| `days=30` 时间过滤 | 仅返回近 30 天内数据点 |
| 超 1000 点截断 | `truncated: true`，`points.length == 1000` |
| product_id 不存在 → 404 | detail 含「商品不存在」 |
| quantity=0 行 | 导入成功，不计入 errors |

---

## Dependency Installation

```bash
# 后端无新依赖
# 前端
cd frontend
npm install echarts-stat
```

---

## Implementation Task Order

1. `backend/models.py` — 新增 `SubOrder` 类
2. `backend/schemas.py` — 新增 `SubOrderImportResult`、`OrderPricePoint`、`OrderPriceSeriesResponse`
3. `backend/routes/sub_orders.py` — 新建，实现 `POST /api/sub-orders/import`
4. `backend/routes/products.py` — 新增 `GET /{id}/order-price-series` 端点
5. `backend/main.py` — 注册 `sub_orders_router`
6. `backend/tests/test_sub_orders.py` — 新建测试文件
7. `frontend/` — `npm install echarts-stat`
8. `frontend/src/api/sub_orders.js` — 新建，`importSubOrders(file)`
9. `frontend/src/api/products.js` — 新增 `fetchOrderPriceSeries(id, days)`
10. `frontend/src/components/OrderPriceChart.vue` — 新建：散点图/折线图切换 + SKU 颜色分组 + 趋势线
11. `frontend/src/components/ProductDetail.vue` — 引入 `OrderPriceChart`，新增时间范围选择器
12. `frontend/src/components/DataImport.vue` — 新增子订单导入 Tab

---

## Risks & Mitigations

| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| Excel 标题行不在第 1 行 | 低 | Spec 确认子订单导出第 1 行为标题行；缺列时返回明确 422 |
| `echarts-stat` 与 ECharts 5 不兼容 | 低 | echarts-stat 官方支持 ECharts 5.x；安装后即时验证渲染 |
| SQLite 表名冲突 | 极低 | SQLModel 生成表名 `suborder`，不与 `order`/`product` 冲突 |
| 导入 2391 行超 10s | 低 | openpyxl `read_only=True` 模式 + 单次 `commit`，预估 2-4s |
| SKU 种类数超过 10 种 | 极低 | 调色板循环取色，超出部分颜色重复但仍可通过 Legend 区分；实际电商 SKU 通常 ≤ 5 种 |


