import React, { useEffect, useMemo, useRef, useState } from 'react'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { getAgent, sendChat } from './api.js'

marked.setOptions({ breaks: true, gfm: true })

/* ---------- tiny inline icons (line style, match the Lyzr playground) ---------- */
const Ico = {
  doc: <svg viewBox="0 0 24 24" className="i"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/></svg>,
  book: <svg viewBox="0 0 24 24" className="i"><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5"/></svg>,
  bolt: <svg viewBox="0 0 24 24" className="i"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>,
  code: <svg viewBox="0 0 24 24" className="i"><path d="m9 8-5 4 5 4M15 8l5 4-5 4"/></svg>,
  plus: <svg viewBox="0 0 24 24" className="i"><path d="M12 5v14M5 12h14"/></svg>,
  send: <svg viewBox="0 0 24 24" className="i"><path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/></svg>,
  clip: <svg viewBox="0 0 24 24" className="i"><path d="M21 11.5 12 20a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8"/></svg>,
  trash: <svg viewBox="0 0 24 24" className="i"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>,
  chev: <svg viewBox="0 0 24 24" className="i"><path d="m6 9 6 6 6-6"/></svg>,
  flow: <svg viewBox="0 0 24 24" className="i"><circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M8 6h8M6 8v3a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V8M12 13v3"/></svg>,
}

const ICON = (k) => Ico[k] || Ico.doc
const uid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
const titleFrom = (text) => {
  const t = text.trim().replace(/\s+/g, ' ')
  return t.length > 42 ? t.slice(0, 42) + '…' : t || 'New chat'
}

/* ---------- localStorage-backed session store ---------- */
const LS = 'hrpolicy.sessions.v1'
const loadSessions = () => {
  try { return JSON.parse(localStorage.getItem(LS)) || [] } catch { return [] }
}
const newSession = () => ({ id: uid(), title: 'New chat', messages: [], createdAt: Date.now() })

/* ---------- markdown → safe HTML ---------- */
function Markdown({ text }) {
  const html = useMemo(() => DOMPurify.sanitize(marked.parse(text || '')), [text])
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />
}

/* ---------- orchestration trace (the multi-agent view) ---------- */
function Trace({ steps, running }) {
  const [open, setOpen] = useState(running)
  useEffect(() => { if (running) setOpen(true) }, [running])
  if (!steps?.length) return null
  return (
    <div className={`trace ${running ? 'live' : ''}`}>
      <button className="trace-hd" onClick={() => setOpen((o) => !o)}>
        <span className="ti">{Ico.flow}</span>
        <span className="tt">{running ? 'Orchestrating sub-agents…' : `Orchestrated ${steps.length} sub-agent${steps.length > 1 ? 's' : ''}`}</span>
        <span className={`tc ${open ? 'up' : ''}`}>{Ico.chev}</span>
      </button>
      {open && (
        <ol className="trace-list">
          {steps.map((s, i) => (
            <li key={s.key || i} className={`trace-step ${running && i === steps._active ? 'doing' : running && i < (steps._active ?? 0) ? 'done' : running ? 'pending' : 'done'}`}>
              <span className="dot">{running && i >= (steps._active ?? 0) ? (i === steps._active ? <span className="spin" /> : i + 1) : '✓'}</span>
              <div className="trace-body">
                <div className="tn">{s.name}</div>
                {s.desc && <div className="td">{s.desc}</div>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

/* ---------- welcome / empty state ---------- */
function Welcome({ agent, onPick }) {
  return (
    <div className="welcome">
      <h1 className="w-title">Welcome to {agent?.name || 'HR Policy Generator Agent'}</h1>
      <p className="w-desc">{agent?.description}</p>
      {agent?.suggestions?.length > 0 && (
        <>
          <div className="w-try">Try asking</div>
          <div className="w-grid">
            {agent.suggestions.map((s, i) => (
              <button key={i} className="w-card" onClick={() => onPick(s.text)}>
                <span className="w-ico">{ICON(s.icon)}</span>
                <span className="w-txt">{s.text}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default function App() {
  const [agent, setAgent] = useState(null)
  const [sessions, setSessions] = useState(() => {
    const s = loadSessions()
    return s.length ? s : [newSession()]
  })
  const [activeId, setActiveId] = useState(() => {
    const s = loadSessions()
    return (s[0]?.id) || null
  })
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [activeStep, setActiveStep] = useState(0)
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')
  const scrollRef = useRef(null)
  const taRef = useRef(null)

  // ensure activeId points at a real session
  useEffect(() => {
    if (!activeId && sessions[0]) setActiveId(sessions[0].id)
  }, [activeId, sessions])

  useEffect(() => { getAgent().then(setAgent).catch(() => setAgent(null)) }, [])
  useEffect(() => { localStorage.setItem(LS, JSON.stringify(sessions)) }, [sessions])
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const active = sessions.find((s) => s.id === activeId) || sessions[0]
  const messages = active?.messages || []

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages.length, sending, activeStep])

  // animate the pipeline while waiting on the (non-streaming) manager response
  useEffect(() => {
    if (!sending) return
    const pipeLen = agent?.pipeline?.length || 3
    setActiveStep(0)
    const t = setInterval(() => setActiveStep((s) => Math.min(s + 1, pipeLen - 1)), 1400)
    return () => clearInterval(t)
  }, [sending, agent])

  function patchSession(id, fn) {
    setSessions((prev) => prev.map((s) => (s.id === id ? fn(s) : s)))
  }

  function startNewChat() {
    const s = newSession()
    setSessions((prev) => [s, ...prev])
    setActiveId(s.id)
    setInput('')
  }

  function deleteSession(id, e) {
    e.stopPropagation()
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== id)
      const finalNext = next.length ? next : [newSession()]
      if (id === activeId) setActiveId(finalNext[0].id)
      return finalNext
    })
  }

  async function submit(text) {
    const message = (text ?? input).trim()
    if (!message || sending || !active) return
    setInput('')

    const sid = active.id
    const userMsg = { role: 'user', content: message }
    patchSession(sid, (s) => ({
      ...s,
      title: s.messages.length === 0 ? titleFrom(message) : s.title,
      messages: [...s.messages, userMsg],
    }))
    setSending(true)
    setActiveStep(0)

    try {
      const res = await sendChat(message, sid)
      patchSession(sid, (s) => ({
        ...s,
        messages: [...s.messages, { role: 'assistant', content: res.response, orchestration: res.orchestration }],
      }))
    } catch (e) {
      patchSession(sid, (s) => ({
        ...s,
        messages: [...s.messages, { role: 'assistant', content: '', error: e.message || 'Request failed.' }],
      }))
    } finally {
      setSending(false)
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function autoGrow(e) {
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
    setInput(el.value)
  }

  const connected = agent?.connected
  const livePipeline = agent?.pipeline ? agent.pipeline.map((p) => ({ ...p })) : []
  livePipeline._active = activeStep

  return (
    <div className="app">
      {/* ---------- sidebar ---------- */}
      <aside className="sidebar">
        <div className="brand">
          <span className="dot">HR</span>
          <div className="brand-text">
            <div className="brand-name">HR Policy Generator</div>
            <div className="brand-desc">Manager Agent</div>
          </div>
        </div>

        <button className="new-chat" onClick={startNewChat}>
          <span className="i-wrap">{Ico.plus}</span> New Chat
        </button>

        <div className="sessions-lbl">Sessions</div>
        <div className="sessions">
          {sessions.map((s) => (
            <div key={s.id}
                 className={`session ${s.id === activeId ? 'active' : ''}`}
                 onClick={() => setActiveId(s.id)}>
              <span className="s-title">{s.title}</span>
              <button className="s-del" title="Delete session" onClick={(e) => deleteSession(s.id, e)}>{Ico.trash}</button>
            </div>
          ))}
        </div>

        <button className="theme-toggle" onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
                title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
          <span className="ico">{theme === 'dark' ? '☀' : '☾'}</span>
          {theme === 'dark' ? 'Light theme' : 'Dark theme'}
        </button>
        <div className="side-foot">Art Technology and Software</div>
      </aside>

      {/* ---------- chat panel ---------- */}
      <main className="chat">
        <header className="chat-top">
          <div className="ct-name">{agent?.name || 'HR Policy Generator Agent'}</div>
          <span className={`status ${connected ? 'on' : 'off'}`}>
            <span className="status-dot" />{connected ? 'Agent connected' : agent ? 'Agent not connected' : 'Connecting…'}
          </span>
        </header>

        <div className="scroll" ref={scrollRef}>
          {messages.length === 0 && !sending ? (
            <Welcome agent={agent} onPick={(t) => submit(t)} />
          ) : (
            <div className="thread">
              {messages.map((m, i) => (
                <div key={i} className={`msg ${m.role}`}>
                  <div className="avatar">{m.role === 'user' ? 'You' : 'HR'}</div>
                  <div className="bubble-wrap">
                    {m.role === 'assistant' && m.orchestration && <Trace steps={m.orchestration} running={false} />}
                    {m.error ? (
                      <div className="bubble err">{m.error}</div>
                    ) : (
                      <div className="bubble">
                        {m.role === 'assistant' ? <Markdown text={m.content} /> : <div className="utext">{m.content}</div>}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {sending && (
                <div className="msg assistant">
                  <div className="avatar">HR</div>
                  <div className="bubble-wrap">
                    <Trace steps={livePipeline} running={true} />
                    <div className="bubble thinking"><span className="spin" /> Generating policy…</div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {!connected && agent && (
          <div className="banner">
            ⚠ Agent not connected — set <code>LYZR_API_KEY</code> and <code>LYZR_AGENT_ID</code> in <code>backend/.env</code>, then restart the backend.
          </div>
        )}

        <div className="composer">
          <div className="composer-box">
            <button className="attach" title="Attach (coming soon)" disabled>{Ico.clip}</button>
            <textarea
              ref={taRef}
              className="ta"
              rows={1}
              value={input}
              placeholder="↑↓ to navigate chat history, Shift+Enter for newline"
              onChange={autoGrow}
              onKeyDown={onKeyDown}
              disabled={sending}
            />
            <button className="send" onClick={() => submit()} disabled={sending || !input.trim()} title="Send">
              {Ico.send}
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
