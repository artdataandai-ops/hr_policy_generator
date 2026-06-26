import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import App from './App.jsx'
import { getAgents } from './api.js'
import './styles.css'

const DEFAULT_SLUG = 'hr-policy'

// Root (no slug) → send the user to the first registered agent. The external portal
// is the real landing page, so this is just a sane fallback when the app is hit directly.
function DefaultRedirect() {
  const [slug, setSlug] = useState(null)
  useEffect(() => {
    let alive = true
    getAgents()
      .then((list) => { if (alive) setSlug(list?.[0]?.slug || DEFAULT_SLUG) })
      .catch(() => { if (alive) setSlug(DEFAULT_SLUG) })
    return () => { alive = false }
  }, [])
  if (!slug) return null
  return <Navigate to={`/${slug}`} replace />
}

// Mount App keyed by slug so switching agents cleanly remounts component state
// (each agent gets its own independent session history).
function AgentRoute() {
  const { slug } = useParams()
  return <App key={slug} slug={slug} />
}

createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<DefaultRedirect />} />
      <Route path="/:slug" element={<AgentRoute />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  </BrowserRouter>
)
