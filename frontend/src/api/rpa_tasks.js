const BASE = '/api/rpa/tasks'

/** 触发一次 RPA 抓取任务 */
export async function createTask(payload) {
  const resp = await fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

export async function fetchTasks(limit = 50) {
  const resp = await fetch(BASE + '?limit=' + limit)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

export async function fetchTask(id) {
  const resp = await fetch(BASE + '/' + id)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

export async function cancelTask(id) {
  const resp = await fetch(BASE + '/' + id + '/cancel', { method: 'POST' })
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

async function _error(resp) {
  const body = await resp.json().catch(() => ({}))
  return body.detail || resp.statusText
}
