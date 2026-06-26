import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frontend talks only to the backend via /api (proxied to FastAPI on :8000).
// The Lyzr key lives in the backend, never here.
//
// Routing is path-based: each agent is reached at /<slug> (e.g. /hr-policy,
// /cold-email) on this one SPA. `base` stays the default '/' because the slug is a
// runtime route, not a build-time base. The Vite dev server already serves
// index.html for /<slug> deep links; production needs the SPA fallback in
// public/_redirects (or the host equivalent).
// Only if you mount the app under a sub-path (e.g. example.com/agents/) set
// base:'/agents/' here AND basename="/agents" on <BrowserRouter>.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
})
