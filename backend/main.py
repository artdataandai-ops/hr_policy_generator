"""
FastAPI backend for the multi-agent Lyzr portal apps.

A thin, secure, multi-tenant proxy in front of a registry of Lyzr Manager Agents
(see agents.json). It holds the shared Lyzr API key (never exposed to the browser)
and turns chat messages into agent calls, routed by a per-agent ``slug``.

Endpoints:
  GET  /                    — health + how many agents are configured
  GET  /api/agents          — index of all agents [{slug, name, short, connected}]
  GET  /api/{slug}/agent    — one agent's metadata (name, description, suggestions, pipeline)
  POST /api/{slug}/chat     — { message, session_id } → { response, orchestration, session_id }
"""
from __future__ import annotations
import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except Exception:
    pass

import lyzr_client
import file_extract

# Uploaded files: keep individual files and the combined payload bounded.
MAX_FILE_BYTES = 15 * 1024 * 1024   # 15 MB per file
MAX_TOTAL_BYTES = 40 * 1024 * 1024  # 40 MB per request

app = FastAPI(title="Lyzr Agents Portal — backend", version="2.0")

# CORS — the React frontend is served from a different origin in dev (Vite :5173) and
# in prod (static host). CORS_ALLOWED_ORIGINS is a comma-separated env var.
_extra_origins = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"] + _extra_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/")
def health():
    slugs = lyzr_client.get_slugs()
    configured = [s for s in slugs if lyzr_client.is_configured(s)]
    return {"ok": True, "agents": len(slugs), "agents_configured": len(configured)}


@app.get("/api/agents")
def agents_index():
    """Index for the portal / landing grid — one row per registered agent."""
    out = []
    for slug in lyzr_client.get_slugs():
        meta = lyzr_client.get_meta(slug)
        out.append({
            "slug": slug,
            "name": meta["name"],
            "short": meta["short"],
            "connected": lyzr_client.is_configured(slug),
        })
    return out


@app.get("/api/{slug}/agent")
def agent(slug: str):
    if not lyzr_client.has_slug(slug):
        raise HTTPException(404, f"Unknown agent '{slug}'.")
    return {**lyzr_client.get_meta(slug), "slug": slug,
            "connected": lyzr_client.is_configured(slug)}


@app.post("/api/{slug}/chat")
async def chat(
    slug: str,
    message: str = Form(""),
    session_id: str | None = Form(None),
    agent_id: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
):
    """Chat with an agent. multipart/form-data so the user can attach files.
    Documents are extracted to text and folded into the message; images are passed
    through as base64 for multimodal agents."""
    if not lyzr_client.has_slug(slug):
        raise HTTPException(404, f"Unknown agent '{slug}'.")

    # Read + extract attachments (if any).
    extracted, total = [], 0
    for f in files or []:
        data = await f.read()
        if not data:
            continue
        total += len(data)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(413, f"file '{f.filename}' exceeds the 15 MB limit")
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(413, "attachments exceed the 40 MB total limit")
        extracted.append(file_extract.extract(f.filename, data, f.content_type))

    user_msg = (message or "").strip()
    if not user_msg and not extracted:
        raise HTTPException(400, "message or at least one file is required")
    if len(user_msg) > 8000:
        raise HTTPException(413, "message too long (max 8000 chars)")

    # Combine the text with extracted document text; collect image parts separately.
    final_msg, images = file_extract.build_message(user_msg, extracted)

    session = (session_id or "").strip() or f"{slug}-default"
    if not lyzr_client.is_configured(slug):
        raise HTTPException(
            503,
            f"The '{slug}' agent is not connected. "
            f"Set LYZR_API_KEY and this agent's manager id in backend/.env and restart.",
        )
    # Allowlist gate (kyc-kyb pattern): only forward to an agent_id known to this slug.
    target = (agent_id or "").strip() or None
    if target and not lyzr_client.is_allowed(slug, target):
        raise HTTPException(403, "Agent not allowed.")
    try:
        return lyzr_client.generate(slug, final_msg, session, target, images=images)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(502, f"Lyzr agent call failed: {e}")
