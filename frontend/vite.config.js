import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frontend talks only to the backend via /api. The Lyzr key lives in the
// backend, never here.
//
// Routing is path-based: each agent is reached at /<slug> (e.g. /hr-policy,
// /it-helpdesk) on this one SPA. In production the app is mounted under the
// `/ai-agents/` prefix on the host nginx, so the BUILD sets base:'/ai-agents/'
// and <BrowserRouter> derives its basename from import.meta.env.BASE_URL.
// Dev stays at '/', so the local server still serves /hr-policy directly.
//
// API: in dev, /api is proxied to FastAPI on :8000 (below). In the prod build,
// VITE_API_BASE_URL=/ai-agents is baked in (see the frontend Dockerfile) and
// api.js appends /api — so the SPA calls /ai-agents/api/*, which the container
// nginx reverse-proxies to the backend service.
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/ai-agents/' : '/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
}))
