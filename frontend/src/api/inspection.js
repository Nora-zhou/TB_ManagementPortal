const BASE = '/api/inspection'

/** 触发单个商品采集（后端串行执行，约 30–60 秒） */
export async function collectItem(itemId, { headless = false } = {}) {
  const resp = await fetch(`${BASE}/collect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_id: itemId, headless }),
  })
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** 历史采集列表 */
export async function fetchSnapshots({ itemId = null, limit = 20 } = {}) {
  const query = new URLSearchParams({ limit })
  if (itemId) query.set('item_id', itemId)
  const resp = await fetch(`${BASE}/snapshots?${query}`)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** 店铺层交易结构指标（动销率 / 集中度 / 价格带） */
export async function fetchShopMetrics({ days = 90, store = 1 } = {}) {
  const query = new URLSearchParams({ days, store })
  const resp = await fetch(`${BASE}/shop/metrics?${query}`)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** 导入千牛「商品分析」导出文件 */
export async function importTraffic(file, { store = 1, periodDays = 7 } = {}) {
  const form = new FormData()
  form.append('file', file)
  form.append('store', store)
  form.append('period_days', periodDays)
  const resp = await fetch(`${BASE}/traffic/import`, { method: 'POST', body: form })
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** 流量概览（访客 / 转化率 / 加购率） */
export async function fetchTrafficOverview({ periodDays = 7, store = 1 } = {}) {
  const query = new URLSearchParams({ period_days: periodDays, store })
  const resp = await fetch(`${BASE}/traffic/overview?${query}`)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** 已导入的流量期次（新到旧），用于判断哪些周期档位可选 */
export async function fetchTrafficPeriods({ store = 1 } = {}) {
  const query = new URLSearchParams({ store })
  const resp = await fetch(`${BASE}/traffic/periods?${query}`)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** 流量结构分析（分档 / 集中度 / 高流量低转化） */
export async function fetchTrafficAnalysis({ periodDays = 7, store = 1 } = {}) {
  const query = new URLSearchParams({ period_days: periodDays, store })
  const resp = await fetch(`${BASE}/traffic/analysis?${query}`)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** 大模型是否已配置（只返回状态，不返回密钥） */
export async function fetchAiStatus() {
  const resp = await fetch(`${BASE}/ai/status`)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** AI 解读：7 天 + 30 天两期流量结构 */
export async function generateAiInsight({ store = 1, refresh = false } = {}) {
  const query = new URLSearchParams({ store, refresh })
  const resp = await fetch(`${BASE}/ai/traffic-insight?${query}`, { method: 'POST' })
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** 与 AI 自由对话（自带店铺数据上下文） */
export async function chatWithAi({ messages, store = 1 }) {
  const resp = await fetch(`${BASE}/ai/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, store }),
  })
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** 商品体检：规则层出候选信号，AI 层裁决；refresh=true 跳过判定缓存 */
export async function fetchItemCheckup(itemId, { store = 1, refresh = false } = {}) {
  const query = new URLSearchParams({ store, refresh })
  const resp = await fetch(`${BASE}/item/${encodeURIComponent(itemId)}/checkup?${query}`)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** 单品 AI 诊断：卡在哪一步、先改什么 */
export async function generateItemInsight({ itemId, store = 1, refresh = false }) {
  const query = new URLSearchParams({ item_id: itemId, store, refresh })
  const resp = await fetch(`${BASE}/ai/item-insight?${query}`, { method: 'POST' })
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** 围绕单个商品与 AI 对话 */
export async function chatWithItemAi({ itemId, messages, store = 1 }) {
  const resp = await fetch(`${BASE}/ai/item-chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_id: itemId, messages, store }),
  })
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** 单个商品的流量表现与诊断 */
export async function fetchItemTraffic(itemId, { periodDays = 7, store = 1 } = {}) {
  const query = new URLSearchParams({ period_days: periodDays, store })
  const resp = await fetch(`${BASE}/traffic/item/${encodeURIComponent(itemId)}?${query}`)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

/** 单条快照详情 */
export async function fetchSnapshot(runId) {
  const resp = await fetch(`${BASE}/snapshots/${encodeURIComponent(runId)}`)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

async function _error(resp) {
  const body = await resp.json().catch(() => ({}))
  return body.detail || resp.statusText
}
