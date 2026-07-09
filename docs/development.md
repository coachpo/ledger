# Development

This is the durable owner for repo toolchain, dependency holds, and validation
commands. Product behavior lives in `docs/product.md`; persistence details live
in `docs/data-model.md`.

## Toolchain

| Surface | Version / command | Notes |
| --- | --- | --- |
| Backend CI Python | 3.13 | `.github/workflows/ci.yml` via `astral-sh/setup-uv@v7`. |
| Backend Docker Python | 3.14 | `backend/Dockerfile` and the root local/demo `Dockerfile`. |
| Frontend CI Node | 24 | `.github/workflows/ci.yml` via `actions/setup-node@v6`. |
| Frontend Docker Node | 26 | `frontend/Dockerfile` and root local/demo frontend build stage. |
| uv | 0.9.8 | CI and Dockerfiles use the same uv release. |
| pnpm | 10.30.1 | `frontend/package.json` package manager and Docker global install. |

Node 26 images install pnpm with `npm install -g pnpm@10.30.1`. Do not switch
those Dockerfiles back to `corepack enable`.

## Dependency Holds

Backend FastAPI is intentionally capped in `backend/pyproject.toml`:

```toml
"fastapi>=0.136.3,<0.137"
```

Reason: FastAPI 0.137 changes included-router route shape. With current
Logfire 4.37.0, `opentelemetry-instrumentation-fastapi` remains below 0.64b0
because Logfire still requires `opentelemetry-sdk<1.43.0`. That older
instrumentation can crash on partial route matches such as a POST to a GET-only
route.

Lift the cap only after PyPI Logfire metadata allows `opentelemetry-sdk>=1.43`
and the lock resolves `opentelemetry-instrumentation-fastapi>=0.64b0`.

```bash
curl -s https://pypi.org/pypi/logfire/json | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(d['info']['version'])
print([r for r in d['info'].get('requires_dist') or [] if 'opentelemetry-sdk' in r])"
```

Frontend React Hooks lint uses `eslint-plugin-react-hooks` recommended rules
without local downgrades. `react-hooks/set-state-in-effect` must stay at the
recommended severity; run lint with zero warnings before relaxing code review.

## Local Stack

Use the root launcher for the local/demo stack:

```bash
./start.sh
docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml down -v
```

`start.sh` exposes only `http://localhost:${APP_PORT:-8080}`. The root image is
local/demo only. Production uses the split backend, scheduler, and frontend
images documented in `README.md`.

## Validation

Install dependencies before quality gates:

```bash
(cd backend && uv sync)
(cd frontend && pnpm install)
```

Backend quality, matching CI:

```bash
(cd backend && uv run ruff check app tests)
(cd backend && uv run black --check app tests)
(cd backend && uv run isort --check-only app tests)
(cd backend && uv run mypy app)
(cd backend && uv run pytest)
```

Frontend quality, matching CI:

```bash
(cd frontend && pnpm lint)
(cd frontend && pnpm typecheck)
(cd frontend && pnpm build)
(cd frontend && pnpm test:run)
(cd frontend && pnpm exec playwright install --with-deps chromium)
(cd frontend && pnpm test:e2e)
```

Finish with:

```bash
git diff --check
```

## Docker Images

`.github/workflows/docker-images.yml` builds only:

- `backend/Dockerfile`
- `frontend/Dockerfile`

It does not build the root local/demo Dockerfile. Run this manually when the
root image changes:

```bash
docker build .
```
