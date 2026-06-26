// Dev: VITE_API_BASE_URL unset → '/api', proxied to FastAPI :8000 (see vite.config.js).
// Prod build: VITE_API_BASE_URL points at the backend behind the edge (baked in at build time).
const BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '') + '/api'

async function j(path, opts) {
  const r = await fetch(`${BASE}${path}`, opts)
  if (!r.ok) {
    let detail = `${r.status}`
    try { detail = (await r.json()).detail || detail } catch { /* non-JSON error */ }
    throw new Error(detail)
  }
  return r.json()
}

export const getAgent = () => j('/agent')

export const sendChat = (message, sessionId) =>
  j('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
  })
