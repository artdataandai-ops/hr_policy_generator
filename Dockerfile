# --- AI Agents Portal frontend: build the React SPA, serve via nginx ---
# Build context is the PROJECT ROOT (see docker-compose.prod.yml: `build: .`).
FROM node:20-alpine AS build

WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .

# Vite base is set to /ai-agents/ for `build` (see vite.config.js); BrowserRouter's
# basename derives from it. VITE_API_BASE_URL is baked into the SPA at build time —
# api.js appends /api, so the SPA calls /ai-agents/api/*, which the container nginx
# reverse-proxies to the backend service. (Do NOT include /api here.)
ENV VITE_API_BASE_URL=/ai-agents
RUN npm run build

FROM nginx:alpine
# nginx serves the SPA on :8080 and reverse-proxies /ai-agents/api/ -> backend:8000.
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Vite outputs to dist/; serve it under the /ai-agents/ alias.
COPY --from=build /app/dist /usr/share/nginx/html/ai-agents

EXPOSE 8080
