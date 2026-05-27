export async function triggerSnapshot(payload) {
  const resp = await fetch('/api/snapshots', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}

export async function fetchSnapshots(productId) {
  const resp = await fetch(`/api/products/${productId}/snapshots`)
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
  return resp.json()
}
