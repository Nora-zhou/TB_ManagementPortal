# Implementation Plan: 1688采购订单供应商管理

**Spec**: `specs/006-supplier-management/spec.md`
**Branch**: `006-supplier-management`
**Status**: Planning

---

## Technical Context

| Item | Detail |
|------|--------|
| Python | 3.11+ |
| Backend framework | FastAPI + SQLModel + SQLite |
| Frontend framework | Vue 3 + Vite (Node.js 18+) |
| xlsx parsing | `openpyxl` (already installed) |
| New table | `PurchaseOrder` — additive only, no migration needed |
| Existing tables untouched | `Order`, `SubOrder`, `Product`, `PriceSnapshot`, `Task` |
| Data facts | 1778 master rows, 459 continuation rows ignored, 11 pending-payment excluded from stats, 71 unique suppliers, date range 2026-02 to 2026-05 |

---

## Architecture Decisions

### 1. Data Model

Add `PurchaseOrder` to `backend/models.py`. Because SQLModel creates the table on `create_db_and_tables()` startup, no Alembic migration is required.

```python
class PurchaseOrder(SQLModel, table=True):
    id:             Optional[int]       = Field(default=None, primary_key=True)
    order_id:       str                 = Field(unique=True, index=True, max_length=64)
    seller_name:    str                 = Field(index=True, max_length=200)
    seller_member:  Optional[str]       = Field(default=None, max_length=200)
    goods_total:    Optional[float]     = None
    shipping_fee:   Optional[float]     = None
    discount:       Optional[float]     = None
    paid_amount:    float
    status:         str                 = Field(max_length=64)
    goods_title:    Optional[str]       = Field(default=None, max_length=500)  # 货品标题 (first/only item)
    created_at:     Optional[datetime]  = None   # 订单创建时间
    paid_at:        Optional[datetime]  = None   # 订单付款时间
    imported_at:    datetime            = Field(default_factory=lambda: datetime.now(timezone.utc))
```

**Why `goods_title` on the master row**: the spec requires showing a truncated goods title in the detail view. The 1688 xlsx puts the goods title on the master row (first item row). Storing it avoids a join or a separate items table.

### 2. API Design

New router prefix: `/api/purchase-orders`  
File: `backend/routes/purchase_orders.py`

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/purchase-orders/import` | Upload + parse 1688.xlsx, upsert rows |
| `GET`  | `/api/purchase-orders/months` | Return list of `{year, month}` present in DB |
| `GET`  | `/api/purchase-orders/summary` | Supplier summary for given `year` & `month` |
| `GET`  | `/api/purchase-orders/detail` | Paginated order detail for one supplier + month |

Query params:
- Summary: `year: int`, `month: int`
- Detail: `seller_name: str`, `year: int`, `month: int`, `page: int = 1`, `page_size: int = 20`

### 3. Frontend Components

| File | Role |
|------|------|
| `frontend/src/api/purchase_orders.js` | API calls (import, months, summary, detail) |
| `frontend/src/components/SupplierManagement.vue` | Main view: month selector + summary table + inline detail panel |

No Vue Router changes needed — the existing app uses component-swap navigation (like `OrderDashboard`). Add `SupplierManagement` to the nav bar in `App.vue`.

---

## Implementation Steps

### Step 1 — Backend: Add `PurchaseOrder` model

**File**: `backend/models.py`

Append at the end of the file (after `SubOrder`):

```python
class PurchaseOrder(SQLModel, table=True):
    id:            Optional[int]      = Field(default=None, primary_key=True)
    order_id:      str                = Field(unique=True, index=True, max_length=64)
    seller_name:   str                = Field(index=True, max_length=200)
    seller_member: Optional[str]      = Field(default=None, max_length=200)
    goods_total:   Optional[float]    = None
    shipping_fee:  Optional[float]    = None
    discount:      Optional[float]    = None
    paid_amount:   float
    status:        str                = Field(max_length=64)
    goods_title:   Optional[str]      = Field(default=None, max_length=500)
    created_at:    Optional[datetime] = None
    paid_at:       Optional[datetime] = None
    imported_at:   datetime           = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
```

The existing `datetime` and `timezone` imports already cover this.

---

### Step 2 — Backend: Add schemas

**File**: `backend/schemas.py`

Add the following classes:

```python
# --- Purchase Order schemas ---

class PurchaseOrderImportResult(BaseModel):
    imported: int
    updated: int
    errors: int

class SupplierSummaryItem(BaseModel):
    seller_name: str
    order_count: int
    total_paid: float

class SupplierSummaryResponse(BaseModel):
    year: int
    month: int
    items: list[SupplierSummaryItem]

class AvailableMonth(BaseModel):
    year: int
    month: int

class PurchaseOrderDetail(BaseModel):
    order_id: str
    goods_title: Optional[str]
    paid_amount: float
    status: str
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}

class PurchaseOrderDetailResponse(BaseModel):
    seller_name: str
    year: int
    month: int
    page: int
    page_size: int
    total: int
    items: list[PurchaseOrderDetail]
```

---

### Step 3 — Backend: Create route file

**File**: `backend/routes/purchase_orders.py` (new file)

Key implementation details:

**POST /import**

```python
REQUIRED_COLUMNS = {"订单编号", "卖家公司名", "实付款(元)", "订单状态", "订单创建时间"}
EXCLUDED_STATUS  = "等待买家付款"

@router.post("/import", response_model=PurchaseOrderImportResult)
async def import_purchase_orders(file: UploadFile, session: Session = Depends(get_session)):
    # 1. Validate .xlsx extension
    # 2. Parse with openpyxl (read_only=True, data_only=True)
    # 3. First row = headers; check REQUIRED_COLUMNS present → 422 if missing
    # 4. Iterate rows[1:]; skip row if 订单编号 is None/empty (continuation rows)
    # 5. Skip row if 实付款(元) is None/unparseable → increment errors
    # 6. Upsert: SELECT by order_id; if found → update fields + increment updated;
    #            else → create new + increment imported
    # 7. session.commit() after all rows; return counts
```

Upsert pattern (mirrors existing `orders.py`):
```python
existing = session.exec(
    select(PurchaseOrder).where(PurchaseOrder.order_id == order_id)
).first()
if existing:
    existing.seller_name = seller_name
    # ... update all fields ...
    session.add(existing)
    updated += 1
else:
    session.add(PurchaseOrder(...))
    imported += 1
```

**GET /months**

```python
@router.get("/months", response_model=list[AvailableMonth])
def get_available_months(session: Session = Depends(get_session)):
    # SQLite strftime to extract year/month from created_at
    # Use func.strftime('%Y', PurchaseOrder.created_at) + func.strftime('%m', ...)
    # DISTINCT, ORDER BY year DESC, month DESC
    # Return list[{year, month}]
```

Implementation note: SQLite stores datetime as text (`YYYY-MM-DD HH:MM:SS`). Use `func.strftime` via SQLAlchemy:
```python
from sqlalchemy import func, distinct
year_col  = func.cast(func.strftime('%Y', PurchaseOrder.created_at), Integer)
month_col = func.cast(func.strftime('%m', PurchaseOrder.created_at), Integer)
rows = session.exec(
    select(year_col, month_col)
    .where(PurchaseOrder.created_at.isnot(None))
    .distinct()
    .order_by(year_col.desc(), month_col.desc())
).all()
```

**GET /summary**

```python
@router.get("/summary", response_model=SupplierSummaryResponse)
def get_supplier_summary(year: int, month: int, session: Session = Depends(get_session)):
    # Filter: created_at year/month match, status != EXCLUDED_STATUS
    # GROUP BY seller_name
    # SELECT seller_name, COUNT(*) AS order_count, SUM(paid_amount) AS total_paid
    # ORDER BY total_paid DESC
```

SQL pattern:
```python
stmt = (
    select(
        PurchaseOrder.seller_name,
        func.count().label("order_count"),
        func.sum(PurchaseOrder.paid_amount).label("total_paid"),
    )
    .where(
        func.strftime('%Y', PurchaseOrder.created_at) == str(year),
        func.strftime('%m', PurchaseOrder.created_at) == f"{month:02d}",
        PurchaseOrder.status != EXCLUDED_STATUS,
        PurchaseOrder.created_at.isnot(None),
    )
    .group_by(PurchaseOrder.seller_name)
    .order_by(func.sum(PurchaseOrder.paid_amount).desc())
)
```

**GET /detail**

```python
@router.get("/detail", response_model=PurchaseOrderDetailResponse)
def get_supplier_detail(
    seller_name: str,
    year: int,
    month: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    # Filter: seller_name, year/month, status != EXCLUDED_STATUS
    # COUNT for total
    # SELECT with OFFSET/LIMIT for pagination
    # Truncate goods_title to 40 chars in Python before returning
```

---

### Step 4 — Backend: Register router in `main.py`

**File**: `backend/main.py`

Add two lines:
```python
from routes.purchase_orders import router as purchase_orders_router
# ...
app.include_router(purchase_orders_router, prefix="/api")
```

The `PurchaseOrder` table is auto-created on startup because `create_db_and_tables()` calls `SQLModel.metadata.create_all()` which picks up all `table=True` models imported anywhere before that call. Importing the router in `main.py` triggers the model import.

---

### Step 5 — Frontend: API module

**File**: `frontend/src/api/purchase_orders.js` (new file)

```js
const BASE = '/api/purchase-orders'

export async function importPurchaseOrders(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/import`, { method: 'POST', body: form })
  if (!res.ok) throw await res.json()
  return res.json()
}

export async function fetchAvailableMonths() {
  const res = await fetch(`${BASE}/months`)
  if (!res.ok) throw await res.json()
  return res.json()  // [{year, month}, ...]
}

export async function fetchSupplierSummary(year, month) {
  const res = await fetch(`${BASE}/summary?year=${year}&month=${month}`)
  if (!res.ok) throw await res.json()
  return res.json()  // {year, month, items: [...]}
}

export async function fetchSupplierDetail(sellerName, year, month, page = 1) {
  const params = new URLSearchParams({ seller_name: sellerName, year, month, page })
  const res = await fetch(`${BASE}/detail?${params}`)
  if (!res.ok) throw await res.json()
  return res.json()
}
```

---

### Step 6 — Frontend: `SupplierManagement.vue`

**File**: `frontend/src/components/SupplierManagement.vue` (new file)

Component structure (single-file component, `<script setup>`):

```
SupplierManagement
├── Import section
│   ├── <input type="file" accept=".xlsx">
│   ├── "导入" button → calls importPurchaseOrders()
│   └── Result banner: "导入 N 条，更新 M 条，错误 E 条"
├── Month selector
│   ├── <select> populated from fetchAvailableMonths()
│   └── Default: current year-month (matched against available months)
├── Summary table (v-if="!selectedSeller")
│   ├── Columns: 供应商名称 | 订单数 | 实付款合计(元)
│   ├── Sorted by total_paid DESC (server-side)
│   ├── Empty state: "暂无数据" when items.length === 0
│   └── Row click → set selectedSeller, load detail
└── Detail panel (v-if="selectedSeller")
    ├── "← 返回" button → clear selectedSeller
    ├── Supplier name + month header
    ├── Paginated table: 订单编号 | 货品标题 | 实付款(元) | 状态 | 创建时间
    ├── Empty state: "暂无有效订单"
    └── Pagination controls (prev/next, page X of N)
```

State variables:
```js
const availableMonths = ref([])      // [{year, month}]
const selectedMonth = ref(null)      // {year, month}
const summaryItems = ref([])         // SupplierSummaryItem[]
const selectedSeller = ref(null)     // string | null
const detailItems = ref([])          // PurchaseOrderDetail[]
const detailTotal = ref(0)
const detailPage = ref(1)
const importResult = ref(null)       // {imported, updated, errors} | null
const importError = ref(null)        // string | null
const loading = ref(false)
```

Watchers:
- `watch(selectedMonth, loadSummary)` — reload summary on month change
- `watch([selectedSeller, detailPage], loadDetail)` — reload detail on seller/page change

On mount: call `fetchAvailableMonths()`, pick current or latest month, then load summary.

---

### Step 7 — Frontend: Add nav entry in `App.vue`

**File**: `frontend/src/App.vue`

Locate the nav bar section and add a new nav item that sets the active view to `'supplier'` (following the same pattern as existing nav items like `'orders'`, `'products'`). Add a `v-if="currentView === 'supplier'"` block that renders `<SupplierManagement />`.

---

## File Checklist

| File | Change |
|------|--------|
| `backend/models.py` | Add `PurchaseOrder` class |
| `backend/schemas.py` | Add 6 new schema classes |
| `backend/routes/purchase_orders.py` | **Create** (4 endpoints) |
| `backend/main.py` | Import + register `purchase_orders_router` |
| `frontend/src/api/purchase_orders.js` | **Create** (4 API functions) |
| `frontend/src/components/SupplierManagement.vue` | **Create** |
| `frontend/src/App.vue` | Add nav entry + view slot |

---

## Acceptance Verification

| Test | Command / Action |
|------|-----------------|
| Import 1688.xlsx | `POST /api/purchase-orders/import` with `data/1688.xlsx` → expect `{imported:1778, updated:0, errors:0}` |
| Re-import (upsert) | Re-POST same file → expect `{imported:0, updated:1778, errors:0}` |
| Missing column 422 | POST a malformed xlsx (remove `卖家公司名` column) → expect HTTP 422 |
| Months list | `GET /api/purchase-orders/months` → `[{year:2026,month:5},{year:2026,month:4},{year:2026,month:3},{year:2026,month:2}]` |
| Summary 2026-03 | `GET /api/purchase-orders/summary?year=2026&month=3` → 71 suppliers max, no `等待买家付款` rows included |
| Detail pagination | `GET /api/purchase-orders/detail?seller_name=万道珠宝首饰厂&year=2026&month=3&page=1` → count matches summary row |
| NFR import speed | `time curl -F "file=@data/1688.xlsx" http://localhost:8000/api/purchase-orders/import` → < 15s |

---

## Constraints & Notes

- **No SQLite datetime index**: SQLite doesn't support function-based indexes. For 1778 rows the full-table scan with `strftime` is well within the 500ms budget. No special indexing required.
- **`goods_title` source**: Take the value from the `货品标题` column on the master row. If a master row has no goods_title (rare), store `None`; the frontend shows `—`.
- **Continuation rows**: Rows where `订单编号` is `None` or empty string must be skipped in the import loop. Do not attempt to parse their `实付款(元)`.
- **`等待买家付款` exclusion**: Applied at query time (summary + detail endpoints), not at import time. The rows are stored but filtered out of all stats and views.
- **Pagination offset**: `offset = (page - 1) * page_size`; use `.offset(offset).limit(page_size)` on the SQLModel query.
- **Frontend build**: After adding `SupplierManagement.vue` run `npm run build` from `frontend/` to confirm no compile errors before integration testing.
