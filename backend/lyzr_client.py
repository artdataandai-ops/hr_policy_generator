"""
lyzr_client — calls Lyzr **Manager Agents** (and their sub-agents) for a registry
of agent apps, all sharing one Lyzr API key.

This module is multi-tenant: every agent app is a slug-keyed entry in
``agents.json`` (display metadata + the env-var names that hold its Lyzr ids).
At import time we build a ``REGISTRY`` mapping ``slug -> {meta, manager_id,
pipeline, allowlist}`` by resolving each ``*_env`` name via ``os.getenv``. The
shared API key / inference url / user id stay server-side and never reach the
browser.

Each entry's Manager Agent orchestrates its sub-agents inside Lyzr Studio, so the
default chat target for a slug is its manager. Like kyc-kyb, the proxy validates
every requested agent_id against that slug's allowlist before forwarding (so a
specific sub-agent can be addressed directly, but nothing outside the allowlist).

Agent input  = the user's chat message.
Agent output = { response: markdown, orchestration: [...sub-agent trace], session_id }.
"""
from __future__ import annotations
import os, json, re

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except Exception:
    pass

# ── Shared (workspace-wide) config ────────────────────────────────────────────
LYZR_API_KEY = os.getenv("LYZR_API_KEY", "").strip()
# v3 inference endpoint (current Lyzr Studio API) — same as kyc-kyb's LYZR_BASE_URL.
LYZR_API_URL = os.getenv("LYZR_BASE_URL", os.getenv("LYZR_API_URL",
              "https://agent-prod.studio.lyzr.ai/v3/inference/chat/")).strip()
LYZR_USER_ID = os.getenv("LYZR_USER_ID", "agents@arttechgroup.demo").strip()

_AGENTS_JSON = os.path.join(os.path.dirname(__file__), "agents.json")

# Default Lyzr read timeout (seconds). A manager fanning out to several sub-agents
# needs room; agents.json can raise this per agent via a "timeout" field.
DEFAULT_TIMEOUT = int(os.getenv("LYZR_TIMEOUT", "180"))


def _build_registry() -> dict:
    """Load agents.json and resolve each agent's ids from the named env vars.

    Returns slug -> {
      "meta":      display metadata (ids stripped),  # safe to send to the browser
      "manager_id": resolved id (may be "" if the env var is unset/blank),
      "pipeline":  [{key, name, desc, agent_id}, ...],
      "allowlist": {manager_id, *sub_ids} - {""},
    }
    """
    with open(_AGENTS_JSON, "r", encoding="utf-8") as f:
        raw = json.load(f)

    registry: dict = {}
    for slug, cfg in raw.items():
        manager_id = os.getenv(cfg.get("manager_env", ""), "").strip()

        pipeline = []
        for p in cfg.get("pipeline", []) or []:
            pipeline.append({
                "key": p["key"],
                "name": p["name"],
                "desc": p.get("desc", ""),
                "agent_id": os.getenv(p.get("agent_env", ""), "").strip(),
            })

        meta = {
            "name": cfg["name"],
            "short": cfg.get("short", ""),
            "brand_name": cfg.get("brand_name", cfg["name"]),
            "subtitle": cfg.get("subtitle", ""),
            "description": cfg.get("description", ""),
            "suggestions": cfg.get("suggestions", []),
            # pipeline for the UI trace — names/descriptions only, no ids leaked.
            "pipeline": [{"key": p["key"], "name": p["name"], "desc": p["desc"]} for p in pipeline],
        }

        allowlist = {a for a in [manager_id, *(p["agent_id"] for p in pipeline)] if a}

        registry[slug] = {
            "meta": meta,
            "manager_id": manager_id,
            "pipeline": pipeline,
            "allowlist": allowlist,
            # Per-agent Lyzr read timeout (seconds). Long-running agents (e.g. autonomous
            # plan/execute/evaluate loops) can override this in agents.json.
            "timeout": int(cfg.get("timeout", DEFAULT_TIMEOUT)),
        }
    return registry


REGISTRY = _build_registry()

# Optional global escape hatch (kyc-kyb pattern): if set, these ids are allowed for
# every slug in addition to its own derived ids. Leave blank to use per-slug ids only.
_GLOBAL_ALLOWED = {a.strip() for a in os.getenv("LYZR_ALLOWED_AGENTS", "").split(",") if a.strip()}


# ── Public, slug-aware helpers ────────────────────────────────────────────────
def get_slugs() -> list[str]:
    return list(REGISTRY.keys())


def has_slug(slug: str) -> bool:
    return slug in REGISTRY


def get_meta(slug: str) -> dict:
    """Display metadata for a slug (no ids). Raises KeyError on unknown slug."""
    return REGISTRY[slug]["meta"]


def is_configured(slug: str) -> bool:
    """True when the shared key is set AND this slug's manager id is set."""
    return bool(LYZR_API_KEY and REGISTRY.get(slug, {}).get("manager_id"))


def _allowlist(slug: str) -> set[str]:
    return REGISTRY[slug]["allowlist"] | _GLOBAL_ALLOWED


def is_allowed(slug: str, agent_id: str) -> bool:
    return agent_id in _allowlist(slug)


def pipeline_meta(slug: str) -> list[dict]:
    """The sub-agent trace shown in the UI (names + descriptions, no ids leaked)."""
    return REGISTRY[slug]["meta"]["pipeline"]


def generate(slug: str, message: str, session_id: str, agent_id: str | None = None,
             images: list[dict] | None = None) -> dict:
    """Call an agent for ``slug`` (default target: that slug's manager).
    Returns {response, orchestration, session_id}. Raises on a disallowed agent_id
    or any network/HTTP error so the caller surfaces it.

    Document attachments are extracted to text upstream and folded into ``message``.
    ``images`` (optional) is a list of {"name", "data_uri"} that we attach as an
    OpenAI-style ``content`` array (the shape kyc-kyb uses) for multimodal agents."""
    if not has_slug(slug):
        raise KeyError(f"unknown agent slug '{slug}'")
    if not is_configured(slug):
        raise RuntimeError(
            f"Lyzr agent '{slug}' not configured (set LYZR_API_KEY and its manager id in backend/.env)."
        )

    target = (agent_id or REGISTRY[slug]["manager_id"]).strip()
    if not is_allowed(slug, target):
        raise PermissionError(f"agent_id '{target}' is not in the allowlist for '{slug}'.")

    payload = {
        "user_id": LYZR_USER_ID,
        "agent_id": target,
        "session_id": session_id,
        "message": message,
    }
    if images:
        # Multimodal shape: a content array with the text plus each image as a data URI.
        payload["content"] = [{"type": "text", "text": message}] + [
            {"type": "image_url", "image_url": {"url": img["data_uri"]}} for img in images
        ]

    import requests
    r = requests.post(
        LYZR_API_URL,
        headers={"x-api-key": LYZR_API_KEY, "Content-Type": "application/json"},
        json=payload,
        timeout=REGISTRY[slug]["timeout"],  # per-agent; long-running agents raise it in agents.json.
    )
    r.raise_for_status()
    data = r.json()

    resp = data.get("response", data.get("message", data.get("answer", "")))
    text = resp if isinstance(resp, str) else json.dumps(resp, indent=2)

    return {
        "response": _clean(text),
        "orchestration": _extract_orchestration(slug, data),
        "session_id": session_id,
    }


def _clean(text: str) -> str:
    """Strip a leading/trailing ```...``` fence the agent sometimes wraps prose in."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    return t.strip()


def _extract_orchestration(slug: str, data: dict) -> list[dict]:
    """Best-effort: surface real sub-agent activity if the manager reports it, else the
    known pipeline. Lyzr manager responses may expose sub-agent runs under varying keys
    (module_outputs / agents / tool_calls / steps) — we probe them defensively and fall
    back to the slug's static pipeline so the trace always renders."""
    for key in ("module_outputs", "agents", "sub_agents", "steps", "tool_calls", "agent_outputs"):
        raw = data.get(key)
        items = list(raw.values()) if isinstance(raw, dict) else (raw if isinstance(raw, list) else None)
        if not items:
            continue
        trace = []
        for i, it in enumerate(items):
            if isinstance(it, dict):
                name = it.get("agent_name") or it.get("name") or it.get("agent") or it.get("tool") or f"Sub-agent {i + 1}"
                detail = it.get("output") or it.get("response") or it.get("description") or it.get("result") or ""
                trace.append({"key": f"agent-{i}", "name": str(name),
                              "desc": str(detail)[:280], "live": True})
            elif isinstance(it, str):
                trace.append({"key": f"agent-{i}", "name": it[:60], "desc": "", "live": True})
        if trace:
            return trace
    return pipeline_meta(slug)
