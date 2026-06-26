"""
FastAPI backend for the HR Policy Generator Manager.

A thin, secure proxy in front of the Lyzr Manager Agent. It holds the Lyzr API key
(never exposed to the browser) and turns chat messages into agent calls.

Endpoints:
  GET  /              — health + whether the agent is configured
  GET  /api/agent     — agent metadata (name, description, suggested prompts, pipeline)
  POST /api/chat      — { message, session_id } → { response, orchestration, session_id }
"""
from __future__ import annotations
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except Exception:
    pass

import lyzr_client

app = FastAPI(title="HR Policy Generator Manager — backend", version="1.0")

# CORS — the React frontend is served from a different origin in dev (Vite :5173) and
# in prod (static host). CORS_ALLOWED_ORIGINS is a comma-separated env var.
_extra_origins = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"] + _extra_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"], allow_headers=["*"],
)

AGENT = {
    "name": lyzr_client.MANAGER["name"],
    "description": lyzr_client.MANAGER["desc"],
    "suggestions": [
        {"icon": "doc",  "text": "Generate an employee onboarding policy for new hires."},
        {"icon": "book", "text": "Develop a policy for personal use of company devices."},
        {"icon": "bolt", "text": "Create a policy on employee social media conduct, considering legal risks."},
        {"icon": "code", "text": "Draft a grievance procedure policy for a remote-first organization."},
    ],
    # The 3 specialized sub-agents the manager orchestrates (names/descriptions only — no ids leaked).
    "pipeline": lyzr_client._pipeline_meta(),
}


class ChatIn(BaseModel):
    message: str
    session_id: str | None = None
    agent_id: str | None = None  # optional: address a specific allowlisted agent (default: manager)


@app.get("/")
def health():
    return {"ok": True, "agent_configured": lyzr_client.is_configured(),
            "agent_name": AGENT["name"]}


@app.get("/api/agent")
def agent():
    return {**AGENT, "connected": lyzr_client.is_configured()}


@app.post("/api/chat")
def chat(body: ChatIn):
    msg = (body.message or "").strip()
    if not msg:
        raise HTTPException(400, "message is required")
    if len(msg) > 8000:
        raise HTTPException(413, "message too long (max 8000 chars)")

    session_id = (body.session_id or "").strip() or "hr-policy-default"
    if not lyzr_client.is_configured():
        raise HTTPException(
            503,
            "The HR Policy Generator Manager agent is not connected. "
            "Set LYZR_API_KEY and LYZR_MANAGER_AGENT_ID in backend/.env and restart.",
        )
    # Allowlist gate (kyc-kyb pattern): only forward to a known agent_id.
    agent_id = (body.agent_id or "").strip() or None
    if agent_id and not lyzr_client.is_allowed(agent_id):
        raise HTTPException(403, "Agent not allowed.")
    try:
        return lyzr_client.generate(msg, session_id, agent_id)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(502, f"Lyzr agent call failed: {e}")
