const BASE = '/api/sub-orders'

export async function importSubOrders(file, store) {
  const form = new FormData()
  form.append('file', file)
  form.append('store', String(store))
  const resp = await fetch(`${BASE}/import`, { method: 'POST', body: form })
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}
