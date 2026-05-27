# Implementation Plan: 多店铺数据区分与统计

**Spec**: specs/008-multi-store/spec.md  
**Feature Branch**: `008-multi-store`  
**Status**: Ready for Implementation

---

## Technical Context

| Item | Detail |
|------|--------|
| Backend framework | FastAPI + SQLModel + SQLite |
| Frontend framework | Vue 3 (Composition API) + Vue Router (hash history) |
| Database migration | SQLite `ALTER TABLE ... ADD COLUMN` (idempotent, exception-swallowed) |
| Affected models | `Order`, `SubOrder`, `PurchaseOrder`, `Product`, `PriceSnapshot` |
| Store field type | `int`, values `1` or `2`; no FK; default `1` for history |
| Deduplication key | Unchanged — `order_id` / `sub_order_id` / `taobao_item_id`; store participates only in upsert update |
| Import pattern | `store` passed as required `Form(...)` integer in multipart upload |
| Query filter pattern | Optional `store: Optional[int] = Query(default=None)` — `None` returns all rows |
| Existing dashboard | `OrderDashboard.vue` — already has date-range filter; store filter added in parallel |
| Supplier dashboard | `SupplierDashboard.vue` / `SupplierManagement.vue` — store filter added to existing month filter |
| DataImport.vue layout | Tab-based: 商品目录 → ProductImport, 订单信息 → SubOrderImport, 采购订单 → PurchaseOrderImport |
| Store selector style | Inline `<label>` radio group; matches existing button/filter UX |

---

## Constitution Check

- Five models each gain exactly one nullable-free integer field — no schema breakage.
- `ALTER TABLE` migration is idempotent (exception swallowed when column already exists).
- Import endpoints remain `multipart/form-data`; only one new required field added.
- Query endpoints remain backward-compatible: omitting `store` returns all rows.
- No new routes or components — only modifications to existing files.
- `store` not involved in deduplication — upsert logic unchanged in shape; only `store` added to `values` dict.
- No navigation changes — store filter lives inside existing page components.

---

## Phase 1: Backend

### 1.1 — Model changes (`backend/models.py`)

Add `store: int = Field(default=1)` to each of the five table classes.

**`Product`** — append after `created_at`:
```python
store: int = Field(default=1)  # 1=店铺1, 2=店铺2
```

**`PriceSnapshot`** — append after `recorded_at`:
```python
store: int = Field(default=1)
```

**`Order`** — append after `imported_at`:
```python
store: int = Field(default=1)
```

**`SubOrder`** — append after `imported_at`:
```python
store: int = Field(default=1)
```

**`PurchaseOrder`** — append after `imported_at`:
```python
store: int = Field(default=1)
```

---

### 1.2 — Database migration (`backend/database.py`)

Add `text` import and migration block inside `create_db_and_tables()`, immediately after `SQLModel.metadata.create_all(engine)`:

```python
from sqlalchemy import text   # add to existing imports at top of file

def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)

    # 008-multi-store: Add store column to all affected tables (idempotent)
    with engine.connect() as conn:
        for table in ("order", "suborder", "purchaseorder", "product", "pricesnapshot"):
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN store INTEGER DEFAULT 1"))
                conn.commit()
            except Exception:
                pass  # Column already exists — skip silently
```

**Notes**:
- SQLite table names for SQLModel classes: `Order` → `order`, `SubOrder` → `suborder`, `PurchaseOrder` → `purchaseorder`, `Product` → `product`, `PriceSnapshot` → `pricesnapshot`.
- Each `conn.commit()` is inside the `try` so a failed `ALTER` never leaves an open transaction.
- Existing rows receive `store = 1` via the `DEFAULT 1` clause.

---

### 1.3 — Schema changes (`backend/schemas.py`)

Three sets of changes:

**a) `OrderRead`** — add `store` field so list responses include store:
```python
store: int = 1
```

**b) Import result schemas** — no changes needed (import results already return `imported`, `updated`, `skipped`, `errors`; store is an input, not output).

**c) `OrderListResponse`** — no changes needed; it wraps `list[OrderRead]` so the store field propagates automatically.

**d) New optional — expose `store` in `PurchaseOrderDetail`** — add:
```python
store: int = 1
```

---

### 1.4 — Orders import route (`backend/routes/orders.py`)

**`POST /api/orders/import`** — add `store` as a required `Form` parameter:

```python
from fastapi import ..., Form   # add Form to existing import

@router.post("/import", response_model=ImportResult, status_code=status.HTTP_200_OK)
async def import_orders(
    file: UploadFile,
    store: int = Form(...),          # NEW — required, 1 or 2
    session: Session = Depends(get_session),
):
    if store not in (1, 2):
        raise HTTPException(status_code=422, detail="store 必须为 1 或 2")
    ...
```

Add `"store": store` to the `values` dict inside the loop:
```python
values = {
    ...existing fields...,
    "store": store,
}
```

Also set store on update path:
```python
if existing:
    for k, v in values.items():
        setattr(existing, k, v)
    existing.imported_at = datetime.now(timezone.utc)
```

**`GET /api/orders`** — add optional `store` filter:

```python
@router.get("", response_model=OrderListResponse)
def list_orders(
    ...existing params...,
    store: Optional[int] = Query(default=None),   # NEW
):
    ...
    if store is not None:
        stmt = stmt.where(Order.store == store)
        count_stmt = count_stmt.where(Order.store == store)
```

**`GET /api/orders/stats/summary`** and **`GET /api/orders/stats/trend`** and **`GET /api/orders/stats/status-dist`** and **`GET /api/orders/stats/top-products`** — add optional `store` filter to each endpoint the same way:

```python
store: Optional[int] = Query(default=None),
...
if store is not None:
    stmt = stmt.where(Order.store == store)
```

**`POST /api/orders/sync-from-sub-orders`** — propagate `store` from SubOrder to Order during aggregation:

```python
# Inside the per-group loop, after collecting items:
store_val = items[0].store  # use store from first sub-order in group

values = {
    ...existing fields...,
    "store": store_val,
}
```

---

### 1.5 — Sub-orders import route (`backend/routes/sub_orders.py`)

**`POST /api/sub-orders/import`** — add `store` as required `Form` parameter:

```python
from fastapi import ..., Form   # add Form to existing import

@router.post("/import", response_model=SubOrderImportResult)
async def import_sub_orders(
    session: SessionDep,
    file: UploadFile = File(...),
    store: int = Form(...),         # NEW — required, 1 or 2
) -> SubOrderImportResult:
    if store not in (1, 2):
        raise HTTPException(status_code=422, detail="store 必须为 1 或 2")
    ...
```

Add `"store": store` to the `values` dict inside the upsert loop.

---

### 1.6 — Purchase orders import route (`backend/routes/purchase_orders.py`)

**`POST /api/purchase-orders/import`** — add `store` as required `Form` parameter:

```python
@router.post("/import", response_model=PurchaseOrderImportResult)
async def import_purchase_orders(
    file: UploadFile,
    store: int = Form(...),         # NEW — required, 1 or 2
    session: Session = Depends(get_session),
):
    if store not in (1, 2):
        raise HTTPException(status_code=422, detail="store 必须为 1 或 2")
    ...
```

Add `"store": store` to the `values` dict inside the upsert loop.

**`GET /api/purchase-orders/summary`** — add optional `store` filter:

```python
store: Optional[int] = Query(default=None),
...
if store is not None:
    base_filters.append(PurchaseOrder.store == store)
```

**`GET /api/purchase-orders/dashboard`** — add optional `store` filter to `base_filters`:

```python
store: Optional[int] = Query(default=None),
...
base_filters = [
    PurchaseOrder.status.not_in(EXCLUDED_STATUSES),
    PurchaseOrder.created_at.isnot(None),
    PurchaseOrder.paid_amount.isnot(None),
]
if store is not None:
    base_filters.append(PurchaseOrder.store == store)
```

---

## Phase 2: Frontend

### 2.1 — API layer changes (`frontend/src/api/orders.js`)

**`importOrders`** — add `store` parameter:

```javascript
export async function importOrders(file, store) {
  const form = new FormData()
  form.append('file', file)
  form.append('store', String(store))
  const resp = await fetch(`${BASE}/import`, { method: 'POST', body: form })
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}
```

**`getOrders`** — add `store` to params:

```javascript
export async function getOrders(params = {}) {
  const query = new URLSearchParams()
  ...existing params...
  if (params.store != null) query.set('store', params.store)
  ...
}
```

**`getOrderSummary`**, **`getOrderTrend`**, **`getStatusDist`**, **`getTopProducts`** — add `store` to each:

```javascript
if (params.store != null) query.set('store', params.store)
```

---

### 2.2 — API layer changes (`frontend/src/api/purchase_orders.js`)

**`importPurchaseOrders`** (or equivalent function) — add `store` parameter to FormData.

**`fetchSupplierDashboard`** — add `store`:

```javascript
export async function fetchSupplierDashboard({ topN = 15, startMonth, endMonth, store } = {}) {
  const p = new URLSearchParams({ top_n: String(topN) })
  if (startMonth) p.append('start_month', startMonth)
  if (endMonth) p.append('end_month', endMonth)
  if (store != null) p.append('store', String(store))
  const res = await fetch(`${BASE}/dashboard?${p}`)
  if (!res.ok) throw await res.json()
  return res.json()
}
```

**`fetchSupplierSummary`** (or equivalent) — add `store` to query params.

---

### 2.3 — `DataImport.vue` — unified store selector

Add a store radio group above the tab bar. The selected store value is passed down to `SubOrderImport` via prop.

**Script changes**:
```javascript
import { ref } from 'vue'
import ProductImport from './ProductImport.vue'
import SubOrderImport from './SubOrderImport.vue'
import PurchaseOrderImport from './PurchaseOrderImport.vue'

const activeTab = ref('product')
const selectedStore = ref(1)          // NEW — shared store for 订单信息 tab
```

**Template changes** — add store selector before tab-bar, pass prop to `SubOrderImport`:
```html
<!-- Store selector: only shown for 订单信息 tab -->
<div v-if="activeTab === 'suborder'" class="store-selector">
  <span class="store-label">店铺：</span>
  <label><input type="radio" :value="1" v-model="selectedStore" /> 店铺1</label>
  <label><input type="radio" :value="2" v-model="selectedStore" /> 店铺2</label>
</div>

...

<SubOrderImport v-show="activeTab === 'suborder'" :store="selectedStore" />
```

**Notes**:
- Store selector only appears when "订单信息" tab is active (other tabs manage their own store picker internally).
- Default is `1` so repeated imports without changing the selector are safe.

---

### 2.4 — `SubOrderImport.vue` — accept `store` prop

**Script changes**:
```javascript
const props = defineProps({
  store: { type: Number, default: 1 }
})
```

In the import function, pass `props.store` to the API:
```javascript
import { importSubOrders } from '../api/sub_orders.js'   // or however import is called

// In submit handler:
await importSubOrders(file, props.store)
```

Remove any standalone store picker if it existed; the value now comes from the parent.

---

### 2.5 — `PurchaseOrderImport.vue` — independent store selector

**Script changes** — add local store ref with validation:
```javascript
const selectedStore = ref(null)   // null = not yet selected; forces explicit choice
const storeError = ref('')

function validateStore() {
  if (!selectedStore.value) {
    storeError.value = '请选择店铺'
    return false
  }
  storeError.value = ''
  return true
}
```

In the submit handler, call `validateStore()` before sending:
```javascript
async function handleImport() {
  if (!validateStore()) return
  await importPurchaseOrders(file, selectedStore.value)
  ...
}
```

**Template addition** — place before the file upload section:
```html
<div class="store-selector">
  <span class="store-label">店铺：</span>
  <label><input type="radio" :value="1" v-model="selectedStore" /> 店铺1</label>
  <label><input type="radio" :value="2" v-model="selectedStore" /> 店铺2</label>
  <span v-if="storeError" class="error-text">{{ storeError }}</span>
</div>
```

---

### 2.6 — `ProductImport.vue` — independent store selector

Same pattern as `PurchaseOrderImport.vue` — add local `selectedStore` ref, validation, and pass to the product import API call.

**Notes**: Product import calls the Goods directory scan endpoint. Verify the current endpoint signature in `frontend/src/api/products.js` and add `store` to the FormData or query param accordingly.

---

### 2.7 — `OrderList.vue` — add store column

**Template change** — add a column header and cell in the orders table:

```html
<!-- In <thead> -->
<th>店铺</th>

<!-- In <tbody> row -->
<td>店铺{{ order.store ?? 1 }}</td>
```

**Notes**:
- `?? 1` guards against legacy rows where store is null before migration runs.
- No filter is added to `OrderList.vue`; store filtering is in `OrderDashboard.vue`.

---

### 2.8 — `OrderDashboard.vue` — store filter

Add a three-state store toggle (`全部 / 店铺1 / 店铺2`) alongside the existing date-range filter.

**Script additions**:
```javascript
const storeFilter = ref(null)   // null = 全部, 1 = 店铺1, 2 = 店铺2

function setStore(val) {
  storeFilter.value = val
  loadAll()
}

function storeParams() {
  return storeFilter.value != null ? { store: storeFilter.value } : {}
}
```

Merge `storeParams()` into every API call:
```javascript
summary.value = await getOrderSummary({ ...dateParams(), ...storeParams() })
trend.value = await getOrderTrend({ ...dateParams(), ...storeParams() })
// etc.
```

**Template addition** — place in the filter toolbar, after existing date buttons:
```html
<div class="store-filter">
  <button :class="{ active: storeFilter === null }" @click="setStore(null)">全部</button>
  <button :class="{ active: storeFilter === 1 }"    @click="setStore(1)">店铺1</button>
  <button :class="{ active: storeFilter === 2 }"    @click="setStore(2)">店铺2</button>
</div>
```

**Behavior**:
- `storeFilter` is session-scoped (`ref`); resets to `null` on page reload — matches spec.
- Changing store does **not** reset the date filter; both are sent as independent params.

---

### 2.9 — `SupplierManagement.vue` — store filter

Same three-state toggle pattern as `OrderDashboard.vue`.

**Script additions**:
```javascript
const storeFilter = ref(null)

function setStore(val) {
  storeFilter.value = val
  loadData()   // existing data-loading function name; adjust if different
}
```

Pass `store: storeFilter.value` to the purchase-order summary API call.

**Template** — add store toggle in the toolbar, alongside the existing month selector.

---

### 2.10 — `SupplierDashboard.vue` — store filter

Add `storeFilter` ref and pass to `fetchSupplierDashboard`:

```javascript
const storeFilter = ref(null)

async function loadDashboard() {
  ...
  const params = {}
  if (startMonth.value) params.startMonth = startMonth.value
  if (endMonth.value) params.endMonth = endMonth.value
  if (storeFilter.value != null) params.store = storeFilter.value
  dashData.value = await fetchSupplierDashboard(params)
  ...
}
```

Add the same three-state toggle to the template.

---

## Shared CSS Pattern

Add to each component's `<style scoped>` (or shared style):

```css
.store-selector {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.store-selector label {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  font-size: 13px;
}
.store-label {
  font-size: 13px;
  color: var(--text-muted);
}
.store-filter {
  display: inline-flex;
  gap: 4px;
}
.store-filter button {
  padding: 4px 12px;
  border: 1px solid var(--border, #ddd);
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.store-filter button.active {
  background: #000;
  color: #fff;
  border-color: #000;
}
```

---

## Migration Strategy

| Step | Action |
|------|--------|
| 1 | Update `backend/models.py` — add `store` field to all five models |
| 2 | Update `backend/database.py` — add `ALTER TABLE` migration block |
| 3 | Restart backend — migration runs automatically on startup; existing rows get `store = 1` |
| 4 | Verify via `SELECT store, count(*) FROM "order" GROUP BY store` — should show all rows as `store = 1` |
| 5 | Update route handlers (import + query filter) |
| 6 | Update schemas |
| 7 | Update frontend API functions |
| 8 | Update frontend components |
| 9 | Re-import any data that belongs to store 2 using the new store selector |

**Rollback**: The `store` column can be ignored by the old code; no breaking changes to existing queries. Rolling back the code before step 3 is safe — the column is additive only.

---

## Implementation Order

1. `backend/models.py` + `backend/database.py` (foundation — must be first)
2. `backend/schemas.py`
3. `backend/routes/sub_orders.py`
4. `backend/routes/orders.py`
5. `backend/routes/purchase_orders.py`
6. `frontend/src/api/orders.js` + `frontend/src/api/purchase_orders.js`
7. `frontend/src/components/DataImport.vue` + `SubOrderImport.vue`
8. `frontend/src/components/PurchaseOrderImport.vue` + `ProductImport.vue`
9. `frontend/src/components/OrderList.vue`
10. `frontend/src/components/OrderDashboard.vue`
11. `frontend/src/components/SupplierManagement.vue`
12. `frontend/src/components/SupplierDashboard.vue`
