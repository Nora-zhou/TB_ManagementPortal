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
  if (!resp.ok) throw new Error(await _error(resp, 'GET'))
  return resp.json()
}

export async function fetchExpenses(params = {}) {
  const query = new URLSearchParams()
  if (params.startMonth) query.set('start_month', params.startMonth)
  if (params.endMonth) query.set('end_month', params.endMonth)
  if (params.category) query.set('category', params.category)
  if (params.store != null) query.set('store', String(params.store))
  if (params.source) query.set('source', params.source)
  const url = `${BASE}/expenses${query.toString() ? '?' + query : ''}`
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(await _error(resp, 'GET'))
  return resp.json()
}

/**
 * 运营费用分析：按月分类走势 + 各费用项汇总。
 * @param {{ startMonth?: string, endMonth?: string, store?: number }} params
 */
export async function fetchExpenseAnalysis({ startMonth, endMonth, store } = {}) {
  const query = new URLSearchParams()
  if (startMonth) query.set('start_month', startMonth)
  if (endMonth) query.set('end_month', endMonth)
  if (store != null) query.set('store', String(store))
  const url = `${BASE}/expense-analysis${query.toString() ? '?' + query : ''}`
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(await _error(resp, 'GET'))
  return resp.json()
}

/**
 * 导入淘宝「汇总账单.xlsx」到运营成本（StorePlatformExpense）。
 * @param {File} file
 * @param {number} store 1 | 2
 */
export async function importExpenseBill(file, store) {
  const form = new FormData()
  form.append('file', file)
  form.append('store', String(store))
  console.info('[StoreScope API] POST', `${BASE}/expenses/import-bill`, {
    file: file.name,
    store,
  })
  const resp = await fetch(`${BASE}/expenses/import-bill`, { method: 'POST', body: form })
  if (!resp.ok) throw new Error(await _error(resp, 'POST'))
  return resp.json()
}

export async function createExpense(payload) {
  const resp = await fetch(BASE + '/expenses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error(await _error(resp, 'POST'))
  return resp.json()
}

export async function updateExpense(id, payload) {
  const resp = await fetch(`${BASE}/expenses/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error(await _error(resp, 'PUT'))
  return resp.json()
}

export async function deleteExpense(id) {
  const resp = await fetch(`${BASE}/expenses/${id}`, { method: 'DELETE' })
  if (!resp.ok) throw new Error(await _error(resp, 'DELETE'))
}

async function _error(resp, method) {
  const text = await resp.text().catch(() => '')
  let detail = resp.statusText
  if (text) {
    try {
      const body = JSON.parse(text)
      detail = body.detail || body.message || JSON.stringify(body)
    } catch {
      detail = text
    }
  }
  if (resp.status === 405 && resp.url.includes('/expenses/import-bill')) {
    detail += ' —— 后端未加载新接口：8000 端口仍有旧进程占用，请结束全部旧后端后重启'
  }
  const message = `${resp.status} ${detail} (${method} ${resp.url})`
  console.error('[StoreScope API]', message)
  return message
}
