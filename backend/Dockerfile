# AI Agents Portal (HR Policy Generator + more) — backend image.
# Build context is the backend/ directory (see docker-compose.prod.yml).
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Deps first for layer caching. gunicorn is the production process manager;
# uvicorn[standard] (in requirements.txt) provides the ASGI worker class.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . ./

EXPOSE 8000

# The app is stateless (no in-memory store — chat history lives in the browser),
# so multiple workers are safe. The 300s timeout covers slow Lyzr manager fan-out
# calls (the Lyzr client itself uses a 180s per-call timeout). The app object is
# `app` in main.py at the package root → main:app.
CMD ["gunicorn", "main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--timeout", "300", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
