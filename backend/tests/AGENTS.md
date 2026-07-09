# Backend Tests Guide

## Overview

Backend tests are integration-heavy product contract tests over real PostgreSQL, FastAPI, SQLAlchemy services, runtime tools, and fake providers.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| DB/app fixtures | `conftest.py` | Disposable PostgreSQL DB, app/client fixtures, settings reset. |
| Fake OpenAI server | `fake_openai_provider.py` | OpenAI-compatible local test server. |
| Shared fixtures | `fixtures/` | Manifest/provider/runtime case builders. |
| API route tests | `test_api.py`, `test_*_api.py` | Public route and contract behavior. |
| Runtime tool tests | `test_runtime_tools*.py`, `test_*oracle*_tools.py` | Tool grants and redaction. |
| Workflow package tests | `test_workflow_package_*.py` | Parser/compiler/export/run contracts. |

## Conventions

- Tests require PostgreSQL. If `TEST_DATABASE_URL` or `DATABASE_URL` is unset, `conftest.py` manages a local `pgvector/pgvector:pg16` Docker container.
- Each test database is disposable and named with a UUID; fixtures reset DB/settings caches around use.
- The autouse fixture clears `SIGNALDECK_API_TOKEN`; auth tests set it explicitly.
- Prefer `response.status_code == expected, response.json()` for API failures.
- Serialize public API models with `model_dump(mode="json", by_alias=True)`.
- Use `httpx.MockTransport`, fake providers, or the fake OpenAI server for provider/network paths.
- Public route presence tests should inspect `app.openapi()["paths"]`, not FastAPI private route internals.
- Keep fixture manifests grounded in supported Workflow Package YAML; no future product surfaces.

## Anti-Patterns

- Do not depend on SQLite behavior.
- Do not call real external providers in tests.
- Do not assert secret ciphertext, plaintext, or unsafe error details.
