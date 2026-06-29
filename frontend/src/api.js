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

// Index of all registered agents — for a landing grid / portal.
export const getAgents = () => j('/agents')

// One agent's metadata, addressed by slug (the first URL path segment).
export const getAgent = (slug) => j(`/${slug}/agent`)

// Chat with optional file attachments. Always multipart/form-data so the backend
// can extract document text / pass images through. Don't set Content-Type — the
// browser adds the multipart boundary itself.
export const sendChat = (slug, message, sessionId, files = [], context = '') => {
  const fd = new FormData()
  fd.append('message', message ?? '')
  if (sessionId) fd.append('session_id', sessionId)
  if (context) fd.append('context', context)        // recent turns → lets the scope guard judge follow-ups in context
  for (const f of files) fd.append('files', f, f.name)
  return j(`/${slug}/chat`, { method: 'POST', body: fd })
}
