# Host Nginx Configuration for the AI Agents Portal

> **This file documents changes the server owner must make to the HOST nginx
> config on `ai.arttechgroup.com`. These changes are NOT applied automatically.**
>
> **IMPORTANT**: This is a separate, self-contained project. It does NOT share any
> infrastructure with the `/scheme-compliance/` (port 4769) or
> `/scheme-compliance-art/` (ports 4771 + 4772) projects. Do NOT modify or remove
> those blocks — they belong to different projects and must stay as-is.

## Architecture

```
browser ──TLS :7777──► host nginx ──► frontend (nginx) :8080 ──/api──► backend (FastAPI) :8000
                                      127.0.0.1:4778                   127.0.0.1:4774
                                                                       (internal via Docker network)
```

The host nginx sends **all** `/ai-agents/` traffic to the frontend container on
port 4778. The container's own nginx handles the static-vs-API split internally,
proxying `/ai-agents/api/` to the backend via Docker DNS.

Port assignments (both are new, project-specific):
- **4778** — frontend (container nginx: SPA + API proxy)
- **4774** — backend (FastAPI via gunicorn/uvicorn; not directly needed by host nginx)

Public URL: `https://ai.arttechgroup.com:7777/ai-agents/`

---

## 1. Add upstream (in the upstream block at the top of the config)

```nginx
upstream ai_agents_frontend {
    server 127.0.0.1:4778;
}
```

> The host does NOT need a separate backend upstream. The container nginx handles
> API routing internally. Port 4774 is exposed on loopback for direct debugging
> only.

---

## 2. Add trailing-slash redirect (in the redirect block)

```nginx
location = /ai-agents {
    return 301 /ai-agents/;
}
```

---

## 3. Add location block (in the server block, e.g. after the scheme-compliance-art section)

```nginx
# ==================== AI AGENTS PORTAL ====================
location /ai-agents/ {
    proxy_pass http://ai_agents_frontend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade           $http_upgrade;
    proxy_set_header Connection        'upgrade';
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_cache_bypass $http_upgrade;
    client_max_body_size 50M;            # large file uploads (docs, résumés, RFPs)
    proxy_read_timeout 300s;             # Lyzr manager fan-out can be slow
    proxy_send_timeout 300s;
}
```

> This is a **single pass-through block** — no rewrite needed. The container nginx
> receives the full `/ai-agents/...` path and routes it (static assets vs API)
> internally. This matches the scheme-compliance-art pattern.

---

## What NOT to change

The following existing blocks belong to **separate** projects and must **NOT** be
modified or removed:

```nginx
# Belongs to the /scheme-compliance/ project (port 4769)
upstream scheme_compliance_backend { server 127.0.0.1:4769; }
location /scheme-compliance/api/ { ... }

# Belongs to the /scheme-compliance-art/ project (ports 4771 + 4772)
upstream scheme_compliance_art_frontend { server 127.0.0.1:4771; }
location /scheme-compliance-art/ { ... }
```

These projects coexist under different path prefixes:
- `/scheme-compliance/`      — original project (4769)
- `/scheme-compliance-art/`  — second project (4771 + 4772)
- `/ai-agents/`              — this project (4778 + 4774)

---

## Verification

After applying the changes and reloading nginx (`sudo nginx -t && sudo systemctl reload nginx`):

```bash
# Frontend (should return HTML with /ai-agents/ asset paths)
curl -k https://ai.arttechgroup.com:7777/ai-agents/

# A specific agent deep link (SPA fallback should still return the app HTML)
curl -k https://ai.arttechgroup.com:7777/ai-agents/hr-policy

# API health (proxied through container nginx to the backend)
curl -k https://ai.arttechgroup.com:7777/ai-agents/healthz

# Agents index (JSON list of registered agents)
curl -k https://ai.arttechgroup.com:7777/ai-agents/api/agents

# Confirm the OTHER projects still work (must be unaffected)
curl -k https://ai.arttechgroup.com:7777/scheme-compliance/api/health
curl -k https://ai.arttechgroup.com:7777/scheme-compliance-art/api/health
```
