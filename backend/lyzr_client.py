"""
lyzr_client — calls the Lyzr **HR Policy Generator Manager** and its sub-agents.

Architecture (4 agents, mirroring the kyc-kyb multi-agent setup):
  • HR Policy Generator Manager  — the Manager Agent; orchestrates the 3 sub-agents.
  • Policy Requirements Agent     — identifies the policy type + specific requirements.
  • Compliance & Guidelines Agent — Perplexity-powered search for labor laws / best practices.
  • Policy Drafting Agent         — combines requirements + compliance into the final document.

The Manager orchestrates the sub-agents inside Lyzr Studio, so the chat's default target
is the manager. Like kyc-kyb, the proxy keeps the Lyzr API key server-side and validates
every requested agent_id against an allowlist before forwarding (so a specific sub-agent
can be addressed directly when needed, but nothing outside the allowlist).

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

LYZR_API_KEY = os.getenv("LYZR_API_KEY", "").strip()
# v3 inference endpoint (current Lyzr Studio API) — same as kyc-kyb's LYZR_BASE_URL.
LYZR_API_URL = os.getenv("LYZR_BASE_URL", os.getenv("LYZR_API_URL",
              "https://agent-prod.studio.lyzr.ai/v3/inference/chat/")).strip()
LYZR_USER_ID = os.getenv("LYZR_USER_ID", "hr-policy@arttechgroup.demo").strip()

# The Manager Agent — the default chat target. (Legacy LYZR_AGENT_ID still honored.)
MANAGER_AGENT_ID = os.getenv("LYZR_MANAGER_AGENT_ID", os.getenv("LYZR_AGENT_ID", "")).strip()

# Specialized sub-agents the manager orchestrates. IDs feed the allowlist + the trace.
PIPELINE = [
    {"key": "requirements", "name": "Policy Requirements Agent",
     "agent_id": os.getenv("LYZR_REQUIREMENTS_AGENT_ID", "").strip(),
     "desc": "Interacts with the user to identify the policy type (leave, workplace conduct, "
             "remote work/WFH, etc.) and any specific requirements."},
    {"key": "compliance", "name": "Compliance & Guidelines Agent",
     "agent_id": os.getenv("LYZR_COMPLIANCE_AGENT_ID", "").strip(),
     "desc": "Uses Perplexity-powered search to retrieve current compliance requirements, "
             "labor laws, and best practices related to the requested policy."},
    {"key": "drafting", "name": "Policy Drafting Agent",
     "agent_id": os.getenv("LYZR_DRAFTING_AGENT_ID", "").strip(),
     "desc": "Generates the final HR policy by combining user requirements and compliance "
             "guidelines into a professional, clear, and compliant HR document."},
]

MANAGER = {
    "key": "manager", "name": "HR Policy Generator Agent", "agent_id": MANAGER_AGENT_ID,
    "desc": "Coordinates the creation of HR policies by orchestrating specialized sub-agents. "
            "Ensures the workflow captures user requirements, validates compliance guidelines, "
            "and produces a finalized HR policy document.",
}


def _allowlist() -> set[str]:
    """Agent ids the proxy may forward to. Explicit LYZR_ALLOWED_AGENTS wins; otherwise the
    4 configured ids (manager + sub-agents). Mirrors kyc-kyb's LYZR_ALLOWED_AGENTS."""
    explicit = [a.strip() for a in os.getenv("LYZR_ALLOWED_AGENTS", "").split(",") if a.strip()]
    if explicit:
        return set(explicit)
    return {a for a in [MANAGER_AGENT_ID, *(p["agent_id"] for p in PIPELINE)] if a}


def is_configured() -> bool:
    return bool(LYZR_API_KEY and MANAGER_AGENT_ID)


def is_allowed(agent_id: str) -> bool:
    return agent_id in _allowlist()


def generate(message: str, session_id: str, agent_id: str | None = None) -> dict:
    """Call an agent (default: the manager). Returns {response, orchestration, session_id}.
    Raises on a disallowed agent_id or any network/HTTP error so the caller surfaces it."""
    if not is_configured():
        raise RuntimeError("Lyzr agent not configured (set LYZR_API_KEY and LYZR_MANAGER_AGENT_ID in backend/.env).")

    target = (agent_id or MANAGER_AGENT_ID).strip()
    if not is_allowed(target):
        raise PermissionError(f"agent_id '{target}' is not in the allowlist (LYZR_ALLOWED_AGENTS).")

    import requests
    r = requests.post(
        LYZR_API_URL,
        headers={"x-api-key": LYZR_API_KEY, "Content-Type": "application/json"},
        json={
            "user_id": LYZR_USER_ID,
            "agent_id": target,
            "session_id": session_id,
            "message": message,
        },
        timeout=180,  # the manager fans out to several sub-agents — give them room.
    )
    r.raise_for_status()
    data = r.json()

    resp = data.get("response", data.get("message", data.get("answer", "")))
    text = resp if isinstance(resp, str) else json.dumps(resp, indent=2)

    return {
        "response": _clean(text),
        "orchestration": _extract_orchestration(data),
        "session_id": session_id,
    }


def _clean(text: str) -> str:
    """Strip a leading/trailing ```...``` fence the agent sometimes wraps prose in."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    return t.strip()


def _pipeline_meta() -> list[dict]:
    """The sub-agent trace shown in the UI (names + descriptions, no ids leaked)."""
    return [{"key": p["key"], "name": p["name"], "desc": p["desc"]} for p in PIPELINE]


def _extract_orchestration(data: dict) -> list[dict]:
    """Best-effort: surface real sub-agent activity if the manager reports it, else the known
    pipeline. Lyzr manager responses may expose sub-agent runs under varying keys
    (module_outputs / agents / tool_calls / steps) — we probe them defensively and fall back to
    the static PIPELINE so the trace always renders."""
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
    return _pipeline_meta()
