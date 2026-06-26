# Deploying the AI Agents Portal

A self-contained two-container stack: a **frontend** (nginx serving the React SPA
*and* reverse-proxying the API) plus a **backend** (FastAPI proxy to the Lyzr v3
inference API). It is **stateless** — there is no database. Chat history lives in
the browser (`localStorage`); the only server-side state is the Lyzr API key and
the per-agent ids in `backend/.env`.

```
browser ──TLS :7777──► host nginx
        │  /ai-agents/ ──► frontend container (nginx :8080)  127.0.0.1:4778
        │                     ├── /ai-agents/        → static SPA
        │                     └── /ai-agents/api/    → backend container (Docker DNS)
        ▼
   backend container (gunicorn + uvicorn :8000)      127.0.0.1:4774
        │
        └──► Lyzr v3 inference API (agent-prod.studio.lyzr.ai)
```

- **frontend** runs nginx: it serves the Vite build under the `/ai-agents/` alias
  and proxies `/ai-agents/api/` to the backend over the internal Docker network.
- **backend** runs `main:app` (FastAPI) under gunicorn with uvicorn workers. It is
  a multi-tenant proxy: each agent in `backend/agents.json` is reached at its slug
  (`/ai-agents/hr-policy`, `/ai-agents/it-helpdesk`, …). It holds the shared Lyzr
  key and never exposes it to the browser.
- Both containers publish on **loopback only** (`127.0.0.1`); the host nginx
  terminates TLS on `:7777` and reverse-proxies `/ai-agents/` to the frontend on
  **4778**. The backend on **4774** is exposed for direct debugging only.

> This runs on the Linux server. From a Windows checkout, push to git and pull on
> the server (or `scp` the repo over), then run the steps below **on the server**.

---

## 1. Configure secrets

One env file — `backend/.env` — git-ignored, created on the server, never committed.

```bash
cp backend/.env.example backend/.env
```

Then edit `backend/.env` and set the Lyzr key plus the ids for each agent you want
live (see `backend/agents.json` for the full slug → env-var mapping):

```ini
LYZR_API_KEY=<your key>
LYZR_USER_ID=ai-agents@arttechgroup.demo

# slug "hr-policy" — manager + 3 sub-agents
LYZR_MANAGER_AGENT_ID=<HR Policy Generator manager id>
LYZR_REQUIREMENTS_AGENT_ID=<...>
LYZR_COMPLIANCE_AGENT_ID=<...>
LYZR_DRAFTING_AGENT_ID=<...>

# ...repeat for support-sentiment / hr-hiring / sales-enablement / rfp-proposal / it-helpdesk
```

An agent whose manager id is blank simply returns **503** ("not connected") — the
other agents keep working. Only `LYZR_API_KEY` + at least one agent's manager id
are required to get something live.

> **CORS is NOT needed for this Docker setup.** The SPA and API are served from the
> same origin (the host nginx), so browser requests are same-origin. Only set
> `CORS_ALLOWED_ORIGINS` if you host the frontend on a *different* origin (e.g.
> Cloudflare Pages — see "Alternative" below).

---

## 2. Deploy

```bash
./deploy.sh            # pull latest, build, start, health-check
./deploy.sh --no-pull  # build & start the current checkout (no git pull)
```

Or manually:

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

The app is then reachable locally at
**http://127.0.0.1:4778/ai-agents/** and its health at
**http://127.0.0.1:4778/ai-agents/healthz** (proxied to the backend), and publicly
via the host nginx at **https://ai.arttechgroup.com:7777/ai-agents/** once step 3
is applied.

---

## 3. Host nginx

Add the upstream + a single pass-through `location /ai-agents/` to the host nginx
config, then reload. The container nginx handles the static-vs-API split
internally, so the host only proxies one location. **Full instructions and the
exact blocks are in [NGINX-DEPLOY-GUIDE.md](NGINX-DEPLOY-GUIDE.md).**

```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## Common operations

```bash
docker compose -f docker-compose.prod.yml logs -f backend    # tail API logs
docker compose -f docker-compose.prod.yml logs -f frontend   # tail nginx logs
docker compose -f docker-compose.prod.yml ps                 # container status
docker compose -f docker-compose.prod.yml restart backend    # restart API only
docker compose -f docker-compose.prod.yml up -d --build       # rebuild + restart
docker compose -f docker-compose.prod.yml down               # stop the stack
```

## Notes

- **TLS** is terminated by the host nginx on `:7777`; the containers speak plain
  HTTP on loopback. No certs are mounted into the containers.
- **Workers**: the app is stateless (no in-memory store), so the 2 gunicorn
  workers are safe. Adjust `--workers` in `backend/Dockerfile` to taste.
- **Uploads**: the backend caps requests at 40 MB total / 15 MB per file; the
  container nginx allows 50 MB. If you raise the backend limits, bump
  `client_max_body_size` in `nginx.conf` (and the host nginx) to match.
- **Slow calls**: a manager agent fans out to several Lyzr sub-agents, so requests
  can take minutes. gunicorn (`--timeout 300`) and nginx (`proxy_read_timeout
  300s`) are aligned to allow for this.
- **No backups needed** — there is no database. Configuration (`backend/.env`) is
  the only state; keep it safe outside the repo.

---

## Alternative: frontend on Cloudflare Pages

If you'd rather host the SPA on Cloudflare Pages instead of the frontend
container, build the SPA pointing at the public API base and deploy only the
backend container behind the host nginx. In that case CORS **is** required:

1. Build the SPA with `VITE_API_BASE_URL=https://ai.arttechgroup.com:7777/ai-agents`
   (api.js appends `/api`). Make sure the Cloudflare project serves it under the
   matching base path and has an SPA fallback (`frontend/public/_redirects`).
2. Set `CORS_ALLOWED_ORIGINS=<your Pages origin>` in `backend/.env`.
3. Add a host-nginx `location /ai-agents/api/` that rewrites to the backend on
   4774. The self-contained Docker stack above is the recommended path; this is
   only for a split deployment.
