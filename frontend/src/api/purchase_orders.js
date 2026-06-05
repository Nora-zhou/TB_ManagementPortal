const BASE = '/api/purchase-orders'

/**
 * T006 — Upload a 1688 .xlsx file and import purchase orders.
 * @param {File} file
 * @returns {Promise<{imported: number, updated: number, errors: number}>}
 */
export async function importPurchaseOrders(file, store) {
  const form = new FormData()
  form.append('file', file)
  form.append('store', String(store))
  const res = await fetch(`${BASE}/import`, { method: 'POST', body: form })
  if (!res.ok) throw await res.json()
  return res.json()
}

/**
 * T010 — Fetch available year/month pairs that have purchase order data.
 * @returns {Promise<Array<{year: number, month: number}>>}
 */
export async function fetchAvailableMonths() {
  const res = await fetch(`${BASE}/months`)
  if (!res.ok) throw await res.json()
  return res.json()
}

/**
 * T010 — Fetch supplier summary for a given year and month.
 * @param {number} year
 * @param {number} month
 * @returns {Promise<{year: number, month: number, items: Array}>}
 */
export async function fetchSupplierSummary(year, month, store) {
  const p = new URLSearchParams({ year: String(year), month: String(month) })
  if (store != null) p.append('store', String(store))
  const res = await fetch(`${BASE}/summary?${p}`)
  if (!res.ok) throw await res.json()
  return res.json()
}

/**
 * T014 — Fetch paginated order detail for a specific supplier and month.
 * @param {string} sellerName
 * @param {number} year
 * @param {number} month
 * @param {number} [page=1]
 * @returns {Promise<{seller_name: string, total: number, items: Array}>}
 */
export async function fetchSupplierDetail(sellerName, year, month, page = 1) {
  const params = new URLSearchParams({
    seller_name: sellerName,
    year: String(year),
    month: String(month),
    page: String(page),
  })
  const res = await fetch(`${BASE}/detail?${params}`)
  if (!res.ok) throw await res.json()
  return res.json()
}

/**
 * T004 — Fetch supplier dashboard data (Top N suppliers with monthly breakdowns).
 * @param {{ topN?: number, startMonth?: string, endMonth?: string }} options
 * @returns {Promise<{top_suppliers: Array, months: string[], monthly_data: Array}>}
 */
export async function fetchSupplierDashboard({ topN = 15, startMonth, endMonth, store } = {}) {
  const p = new URLSearchParams({ top_n: String(topN) })
  if (startMonth) p.append('start_month', startMonth)
  if (endMonth) p.append('end_month', endMonth)
  if (store != null) p.append('store', String(store))
  const res = await fetch(`${BASE}/dashboard?${p}`)
  if (!res.ok) throw await res.json()
  return res.json()
}

/**
 * T017 — Fetch supplier evaluation scores for all suppliers.
 * @param {{ startMonth?: string, endMonth?: string }} options
 */
export async function fetchSupplierEvaluation({ startMonth, endMonth } = {}) {
  const p = new URLSearchParams()
  if (startMonth) p.append('start_month', startMonth)
  if (endMonth) p.append('end_month', endMonth)
  const qs = p.toString() ? '?' + p : ''
  const res = await fetch(`${BASE}/evaluation${qs}`)
  if (!res.ok) throw await res.json()
  return res.json()
}

/**
 * T017 — Fetch detailed evaluation for a single supplier.
 * @param {string} sellerName
 * @param {{ startMonth?: string, endMonth?: string }} options
 */
export async function fetchSupplierEvaluationDetail(sellerName, { startMonth, endMonth } = {}) {
  const p = new URLSearchParams()
  if (startMonth) p.append('start_month', startMonth)
  if (endMonth) p.append('end_month', endMonth)
  const qs = p.toString() ? '?' + p : ''
  const res = await fetch(`${BASE}/evaluation/${encodeURIComponent(sellerName)}${qs}`)
  if (!res.ok) throw await res.json()
  return res.json()
}

export async function fetchRefundOrders(sellerName, goodsTitle, { startMonth, endMonth } = {}) {
  const p = new URLSearchParams({
    seller_name: sellerName,
    goods_title: goodsTitle,
  })
  if (startMonth) p.append('start_month', startMonth)
  if (endMonth) p.append('end_month', endMonth)
  const res = await fetch(`${BASE}/refund-orders?${p}`)
  if (!res.ok) throw await res.json()
  return res.json()
}

export async function fetchRefundOrdersBySeller(sellerName, { startMonth, endMonth, store } = {}) {
  const p = new URLSearchParams({ seller_name: sellerName })
  if (startMonth) p.append('start_month', startMonth)
  if (endMonth) p.append('end_month', endMonth)
  if (store != null) p.append('store', String(store))
  const res = await fetch(`${BASE}/refund-orders-by-seller?${p}`)
  if (!res.ok) throw await res.json()
  return res.json()
}
