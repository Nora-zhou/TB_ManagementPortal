# API Contracts: 商品订单实付价格走势

**Feature**: 005-product-order-price-trend | **Version**: 1.0.0

---

## POST `/api/sub-orders/import`

上传新格式（子订单格式）淘宝订单 xlsx，解析后 upsert 入 `suborder` 表。

### Request

```
POST /api/sub-orders/import
Content-Type: multipart/form-data
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | File | ✅ | 淘宝导出子订单 xlsx，仅接受 `.xlsx` 扩展名 |

**必填列**（xlsx 第 1 行 header 中必须包含）:

```
子订单编号, 主订单编号, 商品ID, 商品标题, 购买数量, 商品价格,
商品属性, 订单状态, 支付单号, 买家实付金额, 退款金额, 订单创建时间, 订单付款时间
```

### Response

#### 200 OK — 导入成功

```json
{
  "imported": 2300,
  "updated": 91,
  "skipped": 0,
  "errors": [
    "第 15 行：商品ID 为空，已跳过",
    "第 42 行：买家实付金额 '???' 无法解析，已跳过"
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `imported` | int | 新插入的子订单数 |
| `updated` | int | 以 `sub_order_id` 为键更新的子订单数 |
| `skipped` | int | 因重复且内容无变化跳过的行数（当前实现始终为 0） |
| `errors` | string[] | 无效行描述，最多包含全部无效行信息；空数组表示无错误 |

#### 415 Unsupported Media Type — 非 xlsx 文件

```json
{ "detail": "仅支持 .xlsx 格式文件" }
```

#### 422 Unprocessable Entity — 缺少必填列

```json
{ "detail": "文件缺少必填列：['商品ID', '买家实付金额']" }
```

#### 422 Unprocessable Entity — 文件无法解析

```json
{ "detail": "无法解析 xlsx 文件，请确认文件未损坏" }
```

---

## GET `/api/products/{id}/order-price-series`

返回指定商品基于已导入子订单的实付价格数列，供前端散点图使用。

### Request

```
GET /api/products/{id}/order-price-series?days=90
```

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| `id` | path | int | ✅ | Product 表主键 |
| `days` | query | string | ❌ | `"30"` / `"90"` / `"all"` / 缺省；缺省与 `"all"` 均返回全部时间 |

### Filtering Logic

后端依次应用以下过滤条件：

1. `SubOrder.taobao_item_id = Product.taobao_item_id`（通过 product_id 查找 taobao_item_id）
2. `SubOrder.status = '交易成功'`
3. `SubOrder.refund_amount = '无退款申请'`
4. 若 `days` 为 `"30"` 或 `"90"`：`SubOrder.created_at >= datetime.now() - timedelta(days=int(days))`
5. `ORDER BY SubOrder.created_at ASC`
6. `LIMIT 1000`

### Response

#### 200 OK — 正常返回

```json
{
  "product_id": 42,
  "taobao_item_id": "844555963059",
  "days": 90,
  "total": 128,
  "truncated": false,
  "points": [
    {
      "created_at": "2026-02-15T09:32:00",
      "buyer_paid": 99.00,
      "quantity": 1,
      "product_attr": "颜色:红色;尺寸:M",
      "sub_order_id": "3141234567890"
    },
    {
      "created_at": "2026-03-01T14:23:00",
      "buyer_paid": 198.00,
      "quantity": 2,
      "product_attr": "颜色:黑色;尺寸:L",
      "sub_order_id": "3141234567891"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `product_id` | int | 查询的商品主键 |
| `taobao_item_id` | string | 淘宝商品 ID |
| `days` | int \| null | 时间范围（天数），全部时为 `null` |
| `total` | int | 过滤后有效子订单总数（不受 1000 上限影响） |
| `truncated` | bool | `total > 1000` 时为 `true` |
| `points[].created_at` | datetime (ISO 8601) | 订单创建时间（本地时间，无时区标记） |
| `points[].buyer_paid` | float | 买家实付金额（子订单级，单位：元） |
| `points[].quantity` | int | 购买数量 |
| `points[].product_attr` | string \| null | 商品属性（规格），如 `"颜色:红色;尺寸:M"` |
| `points[].sub_order_id` | string | 子订单编号（前端 Tooltip 辅助展示） |

**前端单件均价计算**:
```js
const unitPrice = point.buyer_paid / Math.max(point.quantity, 1)
```

#### 200 OK — 数据被截断（total > 1000）

```json
{
  "product_id": 42,
  "taobao_item_id": "844555963059",
  "days": null,
  "total": 1523,
  "truncated": true,
  "points": [ /* 1000 条，按 created_at ASC */ ]
}
```

#### 200 OK — 无匹配数据

```json
{
  "product_id": 42,
  "taobao_item_id": "844555963059",
  "days": 90,
  "total": 0,
  "truncated": false,
  "points": []
}
```

#### 404 Not Found — 商品不存在

```json
{ "detail": "商品不存在" }
```

---

## Frontend API Module

### `src/api/sub_orders.js`

```js
const BASE = '/api'

export async function importSubOrders(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/sub-orders/import`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json()  // SubOrderImportResult
}
```

### `src/api/products.js` 新增函数

```js
export async function fetchOrderPriceSeries(productId, days = '90') {
  const params = days && days !== 'all' ? `?days=${days}` : ''
  const res = await fetch(`${BASE}/products/${productId}/order-price-series${params}`)
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json()  // OrderPriceSeriesResponse
}
```
