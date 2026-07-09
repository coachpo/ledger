FROM node:26-alpine AS frontend-builder

ARG VITE_API_BASE_URL=/api/v1

WORKDIR /app

RUN apk add --no-cache libc6-compat curl \
    && corepack enable \
    && corepack prepare pnpm@10.30.1 --activate

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN VITE_API_BASE_URL="$VITE_API_BASE_URL" pnpm run build

FROM python:3.13-slim AS backend-builder

COPY --from=ghcr.io/astral-sh/uv:0.9.8 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app

FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="SignalDeck local/demo combined image" \
      org.opencontainers.image.description="Local/demo-only combined SignalDeck app; not a supported production artifact." \
      io.signaldeck.support="local-demo-only" \
      io.signaldeck.production-artifact="false"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    SIGNALDECK_RUNTIME_MODE=local \
    SIGNALDECK_ROOT_IMAGE_SCOPE=local-demo-only \
    PORT=8080 \
    BACKEND_PORT=8000 \
    RUN_SCHEDULER=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx supervisor gettext-base ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/conf.d/default.conf /etc/nginx/sites-enabled/default
WORKDIR /app

COPY --from=backend-builder /app /app
COPY --from=frontend-builder /app/dist /usr/share/nginx/html
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf

RUN chmod +x /entrypoint.sh \
    && mkdir -p /etc/supervisor/conf.d /var/log/supervisor /run/nginx \
    && chown -R www-data:www-data /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, sys, urllib.request; port = os.environ.get('PORT', '8080'); url = f'http://127.0.0.1:{port}/ready'; sys.exit(0 if urllib.request.urlopen(url, timeout=3).status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
