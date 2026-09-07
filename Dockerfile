# Multi-stage build (ticket 02, skillproof-deployment spec): a Node stage
# builds the gitignored frontend/dist, a Python stage runs the existing
# FastAPI app, which serves that build directly via main.py's single-origin
# FRONTEND_DIST logic (ADR-0006) — unmodified by this Dockerfile.

FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim AS backend
# Unbuffered stdout so `docker logs` (and the CI smoke test's failure dump)
# shows output immediately instead of buffered on process exit.
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Non-root app user: without this the whole process (app code, every
# dependency, the sentence-transformers model loader) ran as root, so any
# future code-execution bug would hand an attacker root in the container
# instead of an unprivileged account. Fixed UID/GID and --home /app (no
# --create-home — WORKDIR already exists and gets chown'd below) keep this
# reproducible across builds.
RUN groupadd --system --gid 1001 appuser \
    && useradd --system --uid 1001 --gid appuser --no-create-home --home /app appuser

# Editable install so skillproof.main's __file__-relative FRONTEND_DIST
# lookup (parent.parent.parent of src/skillproof/main.py) still resolves to
# /app/frontend/dist, exactly as it does in local dev — a normal `pip
# install .` would instead copy the package into site-packages and break it.
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# appuser needs to write the SQLite fallback DB (skillproof.db, WORKDIR-
# relative) and, on first real request, the sentence-transformers model
# cache under its HOME (=/app) — both land somewhere under /app.
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
# python's stdlib urllib is already in python:3.13-slim, so this needs no
# extra package (unlike curl). urlopen raises on a non-2xx status, which
# exits non-zero on its own — no explicit status check needed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT:-8000}/health', timeout=3)"
# `exec` replaces the shell with uvicorn so uvicorn becomes PID 1 and
# actually receives Railway's redeploy SIGTERM (a bare `sh -c "uvicorn ..."`
# leaves `sh` as PID 1, which does not forward the signal — verified: the
# container previously always hit the platform's SIGKILL grace period
# instead of uvicorn draining in-flight requests). --timeout-graceful-
# shutdown bounds that drain so a stuck one can't block a deploy forever.
# --proxy-headers/--forwarded-allow-ips so request.client.host reflects the
# real visitor's IP behind Railway's proxy instead of the proxy's own hop
# address (Railway's proxy address isn't a fixed, knowable IP to allowlist).
CMD ["sh", "-c", "exec uvicorn skillproof.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 30"]
