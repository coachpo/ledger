FROM node:24-alpine AS frontend-builder

ARG BUILD_FRONTEND=true
ARG VITE_API_BASE_URL=/api/v1

WORKDIR /app

RUN apk add --no-cache libc6-compat curl \
    && corepack enable \
    && corepack prepare pnpm@10.30.1 --activate

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN if [ "$BUILD_FRONTEND" = "true" ]; then pnpm install --frozen-lockfile; fi

COPY frontend/ ./
RUN if [ "$BUILD_FRONTEND" = "true" ]; then \
      VITE_API_BASE_URL="$VITE_API_BASE_URL" pnpm run build; \
    else \
      mkdir -p /app/dist; \
      printf '%s\n' \
        '<!doctype html>' \
        '<html lang="en">' \
        '  <head>' \
        '    <meta charset="utf-8" />' \
        '    <meta name="viewport" content="width=device-width, initial-scale=1" />' \
        '    <title>SignalDeck</title>' \
        '  </head>' \
        '  <body>' \
        '    <main>' \
        '      <h1>SignalDeck</h1>' \
        '      <p>The frontend build was skipped for this image.</p>' \
        '    </main>' \
        '  </body>' \
        '</html>' \
        >/app/dist/index.html; \
    fi

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
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
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

ENTRYPOINT ["/entrypoint.sh"]
