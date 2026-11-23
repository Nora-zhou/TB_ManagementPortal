const BASE = '/api/reconcile'

/** 月度核对结果（库内汇总 vs 平台基准）。 */
export async function fetchMonthlyChecks({ store, startMonth, endMonth } = {}) {
  const query = new URLSearchParams()
  if (store != null) query.set('store', String(store))
  if (startMonth) query.set('start_month', startMonth)
  if (endMonth) query.set('end_month', endMonth)
  const resp = await fetch(`${BASE}/monthly?${query}`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

/** 已登记的平台月度基准。 */
export async function listPlatformStats(store) {
  const query = new URLSearchParams()
  if (store != null) query.set('store', String(store))
  const resp = await fetch(`${BASE}/platform-stats?${query}`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

/** 新增或更新某个「店铺 × 月份」的平台指标。 */
export async function savePlatformStat(payload) {
  const resp = await fetch(`${BASE}/platform-stats`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function deletePlatformStat(store, periodMonth) {
  const resp = await fetch(`${BASE}/platform-stats/${store}/${periodMonth}`, { method: 'DELETE' })
  if (!resp.ok && resp.status !== 204) {
    throw new Error((await resp.json()).detail || resp.statusText)
  }
}
