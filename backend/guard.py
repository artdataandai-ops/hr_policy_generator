"""
guard — a central, per-agent scope guard.

Blocks *clearly* off-topic messages before they reach an agent (e.g. a "biriyani
recipe" sent to the Conversation Summary agent, or an RFP question sent to the HR
Hiring agent). Each agent's allowed scope + refusal text lives in ``guardrails.json``
(separate from agents.json). Classification is done by a single fast model — Groq
``llama-3.1-8b-instant`` called directly — reused for every agent by passing that
agent's scope in each call.

Design choices (see the plan):
  • Stateless + lenient — only block clearly/totally out-of-scope; allow greetings,
    clarifications, follow-ups, and anything plausibly related.
  • Fail-open — if GROQ_API_KEY is unset / the call errors / times out / returns
    garbage, allow the message through (a guard outage must never break chat).
  • Agents absent from guardrails.json (or with no scope) are not guarded.
"""
from __future__ import annotations
import os, re, logging

log = logging.getLogger("guard")

_GUARDRAILS_JSON = os.path.join(os.path.dirname(__file__), "guardrails.json")

# Groq (direct) — fast/cheap classifier. Fails open if the key is unset.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
GROQ_URL = os.getenv("GROQ_URL", "https://api.groq.com/openai/v1/chat/completions").strip()

_SYSTEM_PROMPT = (
    "You are a strict but lenient topic classifier for a customer-facing AI agent. "
    "You are given the agent's ALLOWED SCOPE, the CONVERSATION SO FAR (optional), and "
    "the LATEST USER MESSAGE. Judge whether the LATEST USER MESSAGE is in scope, taking "
    "the conversation so far into account. A short reply that answers the agent's "
    "previous question (e.g. a country, a name, a number, 'yes', 'India') is IN scope. "
    "Block ONLY messages that are clearly and totally outside the scope (e.g. recipes, "
    "general trivia, unrelated coding help). When in doubt, allow. "
    'Respond with ONLY JSON: {"in_scope": true} or {"in_scope": false}.'
)

# Greetings / pleasantries that never need a scope check.
_GREETING_RE = re.compile(
    r"^(hi|hii+|hey|hello|yo|hola|namaste|good\s*(morning|afternoon|evening)|"
    r"thanks?|thank\s*you|ty|ok(ay)?|cool|great|nice|got\s*it|sure|yes|no|"
    r"bye|goodbye|see\s*ya)[\s!.]*$",
    re.IGNORECASE,
)


def _load() -> dict:
    import json
    try:
        with open(_GUARDRAILS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # missing/broken file → guard disabled, never crash
        log.warning("guardrails.json could not be loaded (%s); scope guard disabled", e)
        return {}


_RULES = _load()
_SETTINGS = _RULES.get("_settings", {}) if isinstance(_RULES, dict) else {}
_ENABLED = bool(_SETTINGS.get("enabled", True))
_TIMEOUT = int(_SETTINGS.get("timeout", 20))


def _rule(slug: str) -> dict | None:
    r = _RULES.get(slug)
    return r if isinstance(r, dict) and r.get("scope") else None


def check_scope(slug: str, message: str, has_files: bool = False,
                context: str = "") -> tuple[bool, str | None]:
    """Return (allowed, refusal). allowed=True → proceed to the real agent.
    allowed=False → return ``refusal`` to the user without calling the agent.
    ``context`` is a compact transcript of recent turns so the guard judges
    follow-ups in context (a bare reply like "India" answering the agent's
    question stays in scope)."""
    if not _ENABLED:
        return True, None

    rule = _rule(slug)
    if not rule:  # agent not guarded (open-ended) or no scope configured
        return True, None

    text = (message or "").strip()
    # Prefilter — skip the LLM call for things that are obviously fine.
    if not text:
        return True, None          # file-only message: the file is the content
    if has_files:
        return True, None          # attachment present → let the agent handle it
    if len(text) < 3 or _GREETING_RE.match(text):
        return True, None

    if not GROQ_API_KEY:
        log.warning("GROQ_API_KEY not set; scope guard failing open for '%s'", slug)
        return True, None

    try:
        verdict = _classify(rule["scope"], text, context)
    except Exception as e:  # network/HTTP/timeout → fail open
        log.warning("scope guard call failed for '%s' (%s); allowing through", slug, e)
        return True, None

    if _is_out_of_scope(verdict):
        return False, rule.get("refusal") or _fallback_refusal(rule["scope"])
    return True, None  # in-scope, or anything we couldn't parse → allow (lenient)


def _classify(scope: str, message: str, context: str = "") -> str:
    """Ask Groq llama-3.1-8b-instant whether the latest message is in scope (in context).
    Returns raw text."""
    import requests
    convo = f"CONVERSATION SO FAR:\n{context.strip()}\n\n" if context and context.strip() else ""
    body = f"{convo}ALLOWED SCOPE: {scope}\n\nLATEST USER MESSAGE: {message}"
    r = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": body},
            ],
            "temperature": 0,
            "max_tokens": 20,
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _is_out_of_scope(verdict: str) -> bool:
    """Parse the guard reply. Only a confident 'false' blocks; anything else allows."""
    v = (verdict or "").strip().lower()
    if not v:
        return False
    try:
        m = re.search(r'"?in_scope"?\s*[:=]\s*(true|false)', v)
        if m:
            return m.group(1) == "false"
    except Exception:
        pass
    # No explicit field — block only if it clearly says out of scope and not in scope.
    if "out of scope" in v or "out-of-scope" in v:
        return True
    if re.search(r"\bfalse\b", v) and not re.search(r"\btrue\b", v):
        return True
    return False


def _fallback_refusal(scope: str) -> str:
    return (f"I can only help with {scope}. "
            "Please rephrase your request to stay on that topic.")
