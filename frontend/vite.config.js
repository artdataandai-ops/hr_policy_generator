import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frontend talks only to the backend via /api (proxied to FastAPI on :8000).
// The Lyzr key lives in the backend, never here.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
})
