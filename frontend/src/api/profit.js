const BASE = '/api/profit'

/**
 * 获取纯利润分析数据。
 * @param {{ startMonth?: string, endMonth?: string }} options
 */
export async function fetchPureProfit({ startMonth, endMonth } = {}) {
  const query = new URLSearchParams()
  if (startMonth) query.set('start_month', startMonth)
  if (endMonth) query.set('end_month', endMonth)
  const url = `${BASE}/pure${query.toString() ? '?' + query : ''}`
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

export async function fetchExpenses(params = {}) {
  const query = new URLSearchParams()
  if (params.startMonth) query.set('start_month', params.startMonth)
  if (params.endMonth) query.set('end_month', params.endMonth)
  if (params.category) query.set('category', params.category)
  const url = `${BASE}/expenses${query.toString() ? '?' + query : ''}`
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

export async function createExpense(payload) {
  const resp = await fetch(BASE + '/expenses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

export async function updateExpense(id, payload) {
  const resp = await fetch(`${BASE}/expenses/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

export async function deleteExpense(id) {
  const resp = await fetch(`${BASE}/expenses/${id}`, { method: 'DELETE' })
  if (!resp.ok) throw new Error(await _error(resp))
}

async function _error(resp) {
  const body = await resp.json().catch(() => ({}))
  return body.detail || resp.statusText
}
