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

# Editable install so skillproof.main's __file__-relative FRONTEND_DIST
# lookup (parent.parent.parent of src/skillproof/main.py) still resolves to
# /app/frontend/dist, exactly as it does in local dev — a normal `pip
# install .` would instead copy the package into site-packages and break it.
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8000
CMD ["sh", "-c", "uvicorn skillproof.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
