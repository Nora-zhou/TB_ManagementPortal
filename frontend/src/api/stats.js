const BASE = '/api/stats'

/**
 * Fetch monthly profit data for the home dashboard.
 * @param {{ startMonth?: string, endMonth?: string }} options
 * @returns {Promise<import('../types').ProfitMonthlyResponse>}
 */
export async function fetchProfitMonthly({ startMonth, endMonth } = {}) {
  const query = new URLSearchParams()
  if (startMonth) query.set('start_month', startMonth)
  if (endMonth) query.set('end_month', endMonth)
  const url = `${BASE}/profit-monthly${query.toString() ? '?' + query : ''}`
  const resp = await fetch(url)
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error(body.detail || resp.statusText)
  }
  return resp.json()
}
