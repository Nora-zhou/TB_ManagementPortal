const BASE = '/api/products'

export async function fetchProducts(params = {}) {
  const query = new URLSearchParams()
  if (params.page) query.set('page', params.page)
  if (params.page_size) query.set('page_size', params.page_size)
  if (params.q) query.set('q', params.q)
  if (params.min_price != null) query.set('min_price', params.min_price)
  if (params.max_price != null) query.set('max_price', params.max_price)
  if (params.store != null) query.set('store', params.store)
  if (params.sort_by) query.set('sort_by', params.sort_by)
  if (params.sort_order) query.set('sort_order', params.sort_order)
  if (params.margin_filter) query.set('margin_filter', params.margin_filter)
  const resp = await fetch(`${BASE}?${query}`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function fetchProduct(id) {
  const resp = await fetch(`${BASE}/${id}`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function importCsv(file) {
  const form = new FormData()
  form.append('file', file)
  const resp = await fetch(`${BASE}/import/csv`, { method: 'POST', body: form })
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function importGoodsXlsx(file, store) {
  const form = new FormData()
  form.append('file', file)
  form.append('store', store)
  const resp = await fetch(`${BASE}/import/goods-xlsx`, { method: 'POST', body: form })
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function importTaobao(payload) {
  const resp = await fetch(`${BASE}/import/taobao`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function deleteProduct(id) {
  const resp = await fetch(`${BASE}/${id}`, { method: 'DELETE' })
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
}

export async function importFromGoodsDir(store) {
  const resp = await fetch(`${BASE}/import/from-goods-dir?store=${store}`, { method: 'POST' })
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function fetchOrderPriceSeries(productId, days) {
  const query = new URLSearchParams()
  if (days && days !== 'all') query.set('days', days)
  const resp = await fetch(`${BASE}/${productId}/order-price-series?${query}`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

// ---------------------------------------------------------------------------
// 010-product-profit-analysis API functions
// ---------------------------------------------------------------------------

export async function fetchSKUList(id) {
  const resp = await fetch(`${BASE}/${id}/sku-list`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function fetchSKUCosts(id) {
  const resp = await fetch(`${BASE}/${id}/sku-costs`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function saveSKUCosts(id, items) {
  const resp = await fetch(`${BASE}/${id}/sku-costs`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function fetchSKUCostSuggest(id) {
  const resp = await fetch(`${BASE}/${id}/sku-cost-suggest`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function fetchProfitSummary(id) {
  const resp = await fetch(`${BASE}/${id}/profit-summary`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function fetchProductProfitMonthly(id) {
  const resp = await fetch(`${BASE}/${id}/profit-monthly`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function fetchMonthOrders(id, month) {
  const resp = await fetch(`${BASE}/${id}/profit-monthly/${month}/orders`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}
