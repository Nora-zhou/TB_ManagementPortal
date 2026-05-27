const BASE = '/api/tasks'

async function handleResponse(res) {
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`HTTP ${res.status}: ${body}`)
  }
  if (res.status === 204) return null
  return res.json()
}

export function listTasks() {
  return fetch(`${BASE}/`).then(handleResponse)
}

export function createTask(payload) {
  return fetch(`${BASE}/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(handleResponse)
}

export function updateTask(id, payload) {
  return fetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(handleResponse)
}

export function deleteTask(id) {
  return fetch(`${BASE}/${id}`, { method: 'DELETE' }).then(handleResponse)
}
