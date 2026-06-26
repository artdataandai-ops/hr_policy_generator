#!/usr/bin/env bash
#
# AI Agents Portal production deploy (frontend + backend; no database).
#
#   host nginx (TLS :7777) ──/ai-agents/──► 127.0.0.1:4778 ──► frontend nginx
#                                              └─/ai-agents/api/─► backend :8000 (127.0.0.1:4774)
#   Public entrypoint: https://ai.arttechgroup.com:7777/ai-agents/
#   Local health:      http://127.0.0.1:4778/ai-agents/healthz
#
# Usage:
#   ./deploy.sh           # pull latest, build, (re)start, health-check
#   ./deploy.sh --no-pull # build & start the current checkout (no git pull)
#
set -euo pipefail

cd "$(dirname "$0")"

COMPOSE_FILE="docker-compose.prod.yml"
HEALTH_URL="http://127.0.0.1:4778/ai-agents/healthz"

PULL=1
for arg in "$@"; do
  case "$arg" in
    --no-pull) PULL=0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

# docker compose v2 (plugin) preferred, fall back to legacy docker-compose.
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  echo "❌ Docker Compose not found. Install Docker first." >&2
  exit 1
fi
COMPOSE="$COMPOSE -f $COMPOSE_FILE"

# App secrets — injected at runtime via env_file, never baked into the image.
if [ ! -f backend/.env ]; then
  echo "❌ backend/.env is missing. Create it from backend/.env.example and set:" >&2
  echo "     LYZR_API_KEY=<your key>" >&2
  echo "     LYZR_MANAGER_AGENT_ID + each agent's ids (see backend/agents.json)" >&2
  echo "   Without LYZR_API_KEY + an agent's manager id, that agent returns 503." >&2
  exit 1
fi

if [ "$PULL" -eq 1 ] && [ -d .git ]; then
  echo "▶ Pulling latest changes..."
  git pull --ff-only
fi

echo "▶ Building images (backend + frontend)..."
$COMPOSE build

echo "▶ Starting stack..."
$COMPOSE up -d

echo "▶ Waiting for the app to come up..."
ok=0
for i in $(seq 1 30); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" || true)"
  if [ "$code" = "200" ]; then ok=1; break; fi
  sleep 2
done

echo
$COMPOSE ps
echo
if [ "$ok" -eq 1 ]; then
  echo "✅ Deploy complete — ${HEALTH_URL} (local, 200) | https://ai.arttechgroup.com:7777/ai-agents/ (public)"
else
  echo "⚠️  Stack started but health check did not return 200 in time."
  echo "   Check logs:  $COMPOSE logs -f"
  exit 1
fi
