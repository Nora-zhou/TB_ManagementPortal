# API Contracts: 订单数据分析平台

**Spec**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md)

## Base URL
`/api`（Vite proxy 转发至 `http://localhost:8000`）

---

## POST /api/orders/import

上传淘宝导出的 xlsx 文件，批量导入或更新订单（以「订单编号」去重）。

**Request**: `multipart/form-data`
- `file`: xlsx 文件，必须包含以下列（顺序不限）：`订单编号`、`支付单号`、`支付详情`、`总金额`、`买家实付金额`、`订单状态`、`订单创建时间`、`商品标题`、`卖家服务费`、`退款金额`

**Response 200**
```json
{
  "imported": 1756,
  "updated": 0,
  "skipped": 0,
  "errors": []
}
```

**Response 422** — 文件格式错误或缺少必填列
```json
{
  "detail": "文件缺少必填列：['订单编号', '订单创建时间']"
}
```

**Response 415** — 文件格式不支持
```json
{
  "detail": "仅支持 .xlsx 格式文件"
}
```

---

## GET /api/orders/import/progress

轮询当前导入任务进度（适用于大文件场景）。

**Response 200** — 导入中
```json
{
  "status": "running",
  "processed": 850,
  "total": 1756,
  "percent": 48
}
```

**Response 200** — 无进行中任务
```json
{
  "status": "idle"
}
```

---

## GET /api/orders

分页查询订单列表。

**Query Parameters**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码（从 1 开始） |
| `page_size` | int | 20 | 每页条数（最大 100） |
| `status` | string | — | 订单状态精确匹配，如 `交易成功` |
| `q` | string | — | 商品标题关键词模糊搜索 |
| `start_date` | string | — | 开始日期，格式 `YYYY-MM-DD` |
| `end_date` | string | — | 结束日期，格式 `YYYY-MM-DD`（含当天） |
| `sort_by` | string | `created_at` | 排序字段：`created_at`\|`buyer_paid`\|`refund_amount` |
| `sort_dir` | string | `desc` | 排序方向：`asc`\|`desc` |

**Response 200**
```json
{
  "total": 1756,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 1,
      "order_id": "3304355160546003165",
      "product_title": "镀金藏式八大守护三通佛头文玩星月金刚菩提手串配饰diy手工配件",
      "total_amount": 38.90,
      "buyer_paid": 0.00,
      "status": "交易关闭",
      "created_at": "2026-05-25T17:14:23",
      "refund_amount": 32.23
    }
  ]
}
```

---

## GET /api/orders/stats/summary

返回整体数据摘要，用于仪表盘顶部数字卡片。

**Query Parameters**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `start_date` | string | — | 统计起始日期 `YYYY-MM-DD` |
| `end_date` | string | — | 统计结束日期 `YYYY-MM-DD` |

**Response 200**
```json
{
  "total_orders": 1756,
  "success_orders": 1146,
  "total_revenue": 68597.55,
  "total_refund": 27906.76,
  "refund_rate": 0.289,
  "avg_order_value": 59.86,
  "date_range": {
    "min": "2025-09-01",
    "max": "2026-05-25"
  }
}
```

---

## GET /api/orders/stats/trend

返回销售额与退款额走势数据，用于折线图。

**Query Parameters**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `granularity` | string | `day` | 聚合粒度：`day`\|`week`\|`month` |
| `start_date` | string | — | 起始日期 `YYYY-MM-DD` |
| `end_date` | string | — | 结束日期 `YYYY-MM-DD` |

**Response 200**
```json
{
  "granularity": "month",
  "labels": ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05"],
  "revenue": [19.27, 101.96, 567.39, 1046.28, 4300.68, 8630.14, 19039.74, 21039.18, 8466.26],
  "refund": [0.00, 0.00, 123.45, 456.78, 1200.00, 3400.00, 8900.00, 9800.00, 4026.53],
  "order_count": [1, 3, 18, 32, 95, 180, 420, 395, 202]
}
```

---

## GET /api/orders/stats/status

返回订单状态分布，用于饼图。

**Response 200**
```json
{
  "items": [
    { "status": "交易成功", "count": 1146, "percent": 65.26 },
    { "status": "交易关闭", "count": 512, "percent": 29.16 },
    { "status": "卖家已发货，等待买家确认", "count": 87, "percent": 4.95 },
    { "status": "买家已付款,等待卖家发货", "count": 9, "percent": 0.51 },
    { "status": "等待买家付款", "count": 1, "percent": 0.06 },
    { "status": "卖家部分发货", "count": 1, "percent": 0.06 }
  ]
}
```

---

## GET /api/orders/stats/top-products

返回热销商品排行，用于排行榜表格。

**Query Parameters**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `sort_by` | string | `revenue` | 排序维度：`revenue`（销售额）\|`count`（订单数） |
| `limit` | int | 10 | 返回条数，最大 50 |
| `start_date` | string | — | 统计起始日期 |
| `end_date` | string | — | 统计结束日期 |

**Response 200**
```json
{
  "sort_by": "revenue",
  "items": [
    {
      "rank": 1,
      "product_title": "超薄S925纯银镀24K金隔片垫片文玩配饰星月柏香猴头金刚D",
      "order_count": 160,
      "total_revenue": 10708.05,
      "avg_price": 66.93
    },
    {
      "rank": 2,
      "product_title": "S925纯银镀金镶嵌彩色锆石隔片藏式文玩配饰diy吊坠挂件饰",
      "order_count": 48,
      "total_revenue": 7548.31,
      "avg_price": 157.26
    }
  ]
}
```
