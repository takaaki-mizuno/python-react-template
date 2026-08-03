FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN mkdir -p /app/backend && npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS backend-base

WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./

FROM backend-base AS backend-dev

RUN uv sync --frozen --group dev --no-install-project

FROM backend-base AS runtime

RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev
COPY --from=frontend-builder /app/backend/static ./static

CMD ["uv", "run", "python", "manage.py", "serve", "--host", "0.0.0.0", "--port", "8000", "--no-reload"]
