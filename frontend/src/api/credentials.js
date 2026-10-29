const BASE = '/api/credentials'

/** 平台与可抓取数据集选项 */
export async function fetchPlatforms() {
  const resp = await fetch(BASE + '/platforms')
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

export async function fetchAccounts(platform) {
  const query = platform ? '?platform=' + platform : ''
  const resp = await fetch(BASE + query)
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

export async function createAccount(payload) {
  const resp = await fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

export async function updateAccount(id, payload) {
  const resp = await fetch(BASE + '/' + id, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

export async function deleteAccount(id) {
  const resp = await fetch(BASE + '/' + id, { method: 'DELETE' })
  if (!resp.ok) throw new Error(await _error(resp))
}

/** 测试登录（只验证登录，不抓数据） */
export async function testLogin(id) {
  const resp = await fetch(BASE + '/' + id + '/test-login', { method: 'POST' })
  if (!resp.ok) throw new Error(await _error(resp))
  return resp.json()
}

async function _error(resp) {
  const body = await resp.json().catch(() => ({}))
  return body.detail || resp.statusText
}
