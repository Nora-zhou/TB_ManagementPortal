const BASE = '/api/orders'

/**
 * Upload an xlsx file and import orders.
 * @param {File} file
 * @returns {Promise<{imported: number, updated: number, skipped: number, errors: string[]}>}
 */
export async function importOrders(file, store) {
  const form = new FormData()
  form.append('file', file)
  form.append('store', String(store))
  const resp = await fetch(`${BASE}/import`, { method: 'POST', body: form })
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

/**
 * Poll the current import progress.
 * @returns {Promise<{status: string, processed?: number, total?: number, percent?: number}>}
 */
export async function pollImportProgress() {
  const resp = await fetch(`${BASE}/import/progress`)
  if (!resp.ok) throw new Error(resp.statusText)
  return resp.json()
}

/**
 * Fetch paginated order list with optional filters.
 * @param {{page?: number, page_size?: number, status?: string, q?: string,
 *           start_date?: string, end_date?: string, sort_by?: string, sort_dir?: string}} params
 */
export async function getOrders(params = {}) {
  const query = new URLSearchParams()
  if (params.page) query.set('page', params.page)
  if (params.page_size) query.set('page_size', params.page_size)
  if (params.status) query.set('status', params.status)
  if (params.q) query.set('q', params.q)
  if (params.start_date) query.set('start_date', params.start_date)
  if (params.end_date) query.set('end_date', params.end_date)
  if (params.sort_by) query.set('sort_by', params.sort_by)
  if (params.sort_dir) query.set('sort_dir', params.sort_dir)
  if (params.store != null) query.set('store', params.store)
  const resp = await fetch(`${BASE}?${query}`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

/**
 * Fetch summary statistics for the dashboard.
 * @param {{start_date?: string, end_date?: string}} params
 */
export async function getOrderSummary(params = {}) {
  const query = new URLSearchParams()
  if (params.start_date) query.set('start_date', params.start_date)
  if (params.end_date) query.set('end_date', params.end_date)
  if (params.store != null) query.set('store', params.store)
  const resp = await fetch(`${BASE}/stats/summary?${query}`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

/**
 * Fetch revenue/refund trend data.
 * @param {{granularity?: 'day'|'week'|'month', start_date?: string, end_date?: string}} params
 */
export async function getOrderTrend(params = {}) {
  const query = new URLSearchParams()
  if (params.granularity) query.set('granularity', params.granularity)
  if (params.start_date) query.set('start_date', params.start_date)
  if (params.end_date) query.set('end_date', params.end_date)
  if (params.store != null) query.set('store', params.store)
  const resp = await fetch(`${BASE}/stats/trend?${query}`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

/**
 * Fetch order status distribution.
 * @param {{start_date?: string, end_date?: string}} params
 */
export async function getStatusDist(params = {}) {
  const query = new URLSearchParams()
  if (params.start_date) query.set('start_date', params.start_date)
  if (params.end_date) query.set('end_date', params.end_date)
  if (params.store != null) query.set('store', params.store)
  const resp = await fetch(`${BASE}/stats/status?${query}`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

/**
 * Fetch top products ranking.
 * @param {{sort_by?: 'revenue'|'count', limit?: number, start_date?: string, end_date?: string}} params
 */
export async function getTopProducts(params = {}) {
  const query = new URLSearchParams()
  if (params.sort_by) query.set('sort_by', params.sort_by)
  if (params.limit) query.set('limit', params.limit)
  if (params.start_date) query.set('start_date', params.start_date)
  if (params.end_date) query.set('end_date', params.end_date)
  if (params.store != null) query.set('store', params.store)
  const resp = await fetch(`${BASE}/stats/top-products?${query}`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}
