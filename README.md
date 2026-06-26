# HR Policy Generator Manager

A standalone chat interface for the **HR Policy Generator Manager** — a Lyzr *Manager
Agent* that coordinates specialized sub-agents (requirements capture → compliance
validation → policy document generation) to produce finalized HR policy documents.

Same tech stack and visual theme as the `vss110` reconciliation app:

- **Frontend** — React 18 + Vite, plain CSS theme tokens (dark default + light toggle,
  Lyzr gold `#FEC422` accent), markdown rendering via `marked` + `DOMPurify`.
- **Backend** — FastAPI. Holds the Lyzr API key server-side (never exposed to the
  browser) and proxies chat to the Lyzr **v3 inference** endpoint.

The UI is a Lyzr-style chat: a sessions sidebar (`New Chat` + per-session history kept
in `localStorage`), a welcome screen with suggested prompts, and an **orchestration
trace** under each answer showing which sub-agents the manager ran.

```
hr_policy_generator_manager/
├── backend/                 # FastAPI proxy → Lyzr v3 inference
│   ├── main.py              #   GET /  ·  GET /api/agent  ·  POST /api/chat
│   ├── lyzr_client.py       #   Lyzr call + orchestration-trace extraction
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/                # React + Vite chat UI
│   └── src/{App.jsx, api.js, styles.css, main.jsx}
└── docker-compose.yml
```

## 1. Configure the agents

Four agents are created in Lyzr Studio — one **Manager** + three **sub-agents**:

| Role | Agent | Does |
|------|-------|------|
| Manager | **HR Policy Generator Manager** | Orchestrates the sub-agents |
| Sub-agent | **Policy Requirements Agent** | Identifies policy type & specific requirements |
| Sub-agent | **Compliance & Guidelines Agent** | Perplexity-powered search for labor laws / best practices |
| Sub-agent | **Policy Drafting Agent** | Combines requirements + compliance into the final document |

```bash
cd backend
cp .env.example .env          # then edit:
#   LYZR_API_KEY=<your key>
#   LYZR_MANAGER_AGENT_ID=<the HR Policy Generator Manager id>
#   LYZR_REQUIREMENTS_AGENT_ID=<Policy Requirements Agent id>
#   LYZR_COMPLIANCE_AGENT_ID=<Compliance & Guidelines Agent id>
#   LYZR_DRAFTING_AGENT_ID=<Policy Drafting Agent id>
```

The chat's default target is the **manager**, which orchestrates the three sub-agents
internally inside Lyzr. Following the kyc-kyb pattern, the proxy validates every
requested `agent_id` against an allowlist (`LYZR_ALLOWED_AGENTS`, auto-derived from the
four ids above) before forwarding — so a specific sub-agent can be addressed directly,
but nothing outside the allowlist.

Without `LYZR_API_KEY` + `LYZR_MANAGER_AGENT_ID`, `POST /api/chat` returns `503` and the
UI shows an "Agent not connected" banner — the agents *are* the intelligence; there is no
local fallback.

## 2. Run the backend (FastAPI on :8000)

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate    # Windows (PowerShell: .venv\Scripts\Activate.ps1)
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## 3. Run the frontend (Vite on :5173)

```bash
cd frontend
npm install
npm run dev        # proxies /api → http://localhost:8000
```

Open http://localhost:5173.

## Production

- **Backend**: `docker compose up -d --build` (binds `127.0.0.1:8000`; put it behind your
  edge nginx). Set `CORS_ALLOWED_ORIGINS` in `backend/.env` to the deployed frontend origin.
- **Frontend**: `npm run build` → static `dist/`. Set `VITE_API_BASE_URL` (e.g.
  `frontend/.env.production`) to the backend's public base URL so `/api/*` resolves there.

## API

| Method | Path          | Body / returns |
|--------|---------------|----------------|
| GET    | `/`           | health + `agent_configured` |
| GET    | `/api/agent`  | manager name, description, suggested prompts, sub-agent pipeline, `connected` |
| POST   | `/api/chat`   | `{ message, session_id, agent_id? }` → `{ response (markdown), orchestration[], session_id }` |

`agent_id` is optional and defaults to the manager; if supplied it must be in the
allowlist (else `403`). The `orchestration` array drives the multi-agent trace in the UI.
If the live Lyzr response exposes per-sub-agent activity it is surfaced verbatim;
otherwise the manager's known pipeline (Policy Requirements → Compliance & Guidelines →
Policy Drafting) is shown.
