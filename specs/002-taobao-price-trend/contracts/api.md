# API Contracts: 淘宝价格走势平台

**Spec**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md)

## Base URL
`/api`（Vite proxy 转发至 `http://localhost:8000`）

---

## POST /api/products/import/csv

上传 CSV 文件，批量导入或更新商品（以 `item_id` 去重）。

**Request**: `multipart/form-data`
- `file`: CSV 文件，必填字段列：`item_id,name,price,url`

**CSV 示例**
```csv
item_id,name,price,url
123456789,棉质T恤（白色 M码）,59.90,https://item.taobao.com/item.htm?id=123456789
987654321,牛仔裤（蓝色 28腰）,129.00,https://item.taobao.com/item.htm?id=987654321
```

**Response 200**
```json
{
  "imported": 2,
  "updated": 0,
  "errors": []
}
```

**Response 422** — CSV 格式错误
```json
{
  "detail": "第 3 行缺少必填字段 'price'"
}
```

---

## POST /api/products/import/taobao

通过淘宝开放平台 Session Key 拉取店铺在售商品并导入。

**Request Body**
```json
{
  "session_key": "string（用户淘宝 OAuth Session Key）",
  "app_key": "string",
  "app_secret": "string"
}
```

**Response 200**
```json
{
  "imported": 15,
  "updated": 3,
  "errors": []
}
```

**Response 401** — Token 无效或已过期
```json
{
  "detail": "淘宝 Token 无效，请重新授权"
}
```

**Response 502** — 淘宝 API 连接失败
```json
{
  "detail": "连接淘宝开放平台失败，请检查网络或稍后重试"
}
```

---

## GET /api/products

获取商品列表，支持分页、关键词搜索、价格区间筛选。

**Query Parameters**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码（从 1 开始） |
| `page_size` | int | 20 | 每页条数（最大 100） |
| `q` | string | — | 商品名称关键词搜索（模糊匹配） |
| `min_price` | float | — | 当前价格下限（含） |
| `max_price` | float | — | 当前价格上限（含） |

**Response 200**
```json
{
  "total": 42,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 1,
      "taobao_item_id": "123456789",
      "name": "棉质T恤（白色 M码）",
      "url": "https://item.taobao.com/item.htm?id=123456789",
      "current_price": 59.90,
      "alert_low": 45.00,
      "alert_high": null,
      "last_updated": "2026-05-25T10:30:00Z",
      "alert_status": "normal"
    }
  ]
}
```

> `alert_status` 枚举值：`"normal"` | `"below_low"` | `"above_high"`

---

## GET /api/products/{id}

获取单个商品详情。

**Response 200**
```json
{
  "id": 1,
  "taobao_item_id": "123456789",
  "name": "棉质T恤（白色 M码）",
  "url": "https://item.taobao.com/item.htm?id=123456789",
  "current_price": 59.90,
  "alert_low": 45.00,
  "alert_high": null,
  "last_updated": "2026-05-25T10:30:00Z",
  "snapshot_count": 12
}
```

**Response 404**
```json
{ "detail": "Product not found" }
```

---

## PUT /api/products/{id}/alert

设置或更新价格预警阈值（传 `null` 表示清除该阈值）。

**Request Body**
```json
{
  "alert_low": 45.00,
  "alert_high": null
}
```

**Response 200**
```json
{
  "id": 1,
  "alert_low": 45.00,
  "alert_high": null
}
```

---

## DELETE /api/products/{id}

删除商品及其所有价格快照历史。

**Response 204** — No Content

**Response 404**
```json
{ "detail": "Product not found" }
```

---

## POST /api/snapshots

触发全量价格快照：实时调用淘宝开放平台 API 获取每件商品的最新价格并写入数据库。

> 注意：此操作耗时与商品数量成正比。前端应在按钮点击后轮询或等待响应。

**Request Body**
```json
{
  "session_key": "string",
  "app_key": "string",
  "app_secret": "string"
}
```

**Response 200**
```json
{
  "updated": 18,
  "failed": 1,
  "errors": [
    { "taobao_item_id": "999888777", "reason": "商品已下架" }
  ],
  "recorded_at": "2026-05-25T14:00:00Z"
}
```

**Response 409** — 快照记录正在进行中
```json
{ "detail": "快照记录正在进行中，请稍候" }
```

---

## GET /api/products/{id}/snapshots

获取指定商品的全部价格快照历史，按时间升序返回（用于折线图）。

**Response 200**
```json
[
  { "id": 1, "price": 65.00, "recorded_at": "2026-05-01T09:00:00Z" },
  { "id": 2, "price": 59.90, "recorded_at": "2026-05-10T09:00:00Z" },
  { "id": 3, "price": 55.00, "recorded_at": "2026-05-25T10:30:00Z" }
]
```

**Response 404**
```json
{ "detail": "Product not found" }
```
