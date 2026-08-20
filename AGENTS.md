# SignalDeck Agent Guide

**Generated:** 2026-07-09T19:21:48Z
**Commit:** 9c00b8ff
**Branch:** main
**Code map:** codebase-memory project `home-qing-Documents-projects-ledger`

## Overview

SignalDeck is a trusted single-user mini-Jenkins for LLM agents: YAML Workflow Packages define multi-agent pipelines, manual or scheduled launches enqueue runs, and operators inspect run evidence, outputs, templates, and reports.
Prefer clean current architecture over compatibility shims, legacy stubs, or speculative compatibility paths.

## Communication

- Do not send optional progress commentary; report required results, blockers, and final status.
- Do not revert, overwrite, or stage user changes you did not make.

## Structure

| Path | Purpose |
| --- | --- |
| `backend/` | FastAPI, SQLAlchemy, runtime tools, static extensions, scheduler worker, pytest. |
| `frontend/` | React 19, Vite 8, TanStack Query, shadcn/Radix UI, Vitest, Playwright. |
| `docs/` | Canonical product, architecture, development, data-model, and extension-writing docs. |
| `demo/` | Grounded Workflow Package YAML examples. |
| `.github/workflows/` | CI gates and split backend/frontend Docker image publishing. |
| `start.sh`, `Dockerfile`, `docker-compose.yml` | Local/demo combined stack only. |

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| Backend API/runtime changes | `backend/app/` | Child guide covers API/data/runtime boundaries. |
| Backend route contracts | `backend/app/api/` | Two API roots, extension mounting, literal route order. |
| Backend orchestration | `backend/app/services/` | Run queue, scheduler, parser/compiler, model gateways. |
| Bundled tool surfaces | `backend/app/extensions/` | Static extension contract and per-extension guides. |
| Backend tests | `backend/tests/` | Real PostgreSQL fixture and fake provider patterns. |
| Frontend app work | `frontend/` | Child guide covers design system, hooks, route conventions. |
| Package authoring UI | `frontend/src/pages/workflow-packages/` | Manifest editor, import/export, preflight, launch. |
| Schedule UI | `frontend/src/pages/scheduled-tasks/` | Recurrence, timezone, run-now, fire history. |
| Run evidence UI | `frontend/src/pages/runs/` | Immutable snapshots, inspection state, rerun lineage. |
| Schema/value helpers | `frontend/src/lib/platform-authoring/` | Pure codecs and diagnostics shared by authoring surfaces. |
| Browser workflows | `frontend/e2e/` | Cross-stack Playwright setup and API seeding. |

## Code Map

| Symbol | Type | Location | Role |
| --- | --- | --- | --- |
| `create_app` | function | `backend/app/main.py` | FastAPI setup, middleware, health/readiness, routers. |
| `RunService` | class | `backend/app/services/run_service.py` | Central run launch/execution/projection orchestration. |
| `WorkflowPackageService` | class | `backend/app/services/workflow_package_service.py` | Package CRUD, snapshots, manifest import/export. |
| `WorkflowPackageScheduleService` | class | `backend/app/services/workflow_package_schedule_service.py` | Schedule lifecycle, preview, run-now, fire materialization. |
| `CamelModel` | class | `backend/app/schemas/common.py` | External camelCase API schema contract. |
| `ApiError` | class | `backend/app/core/errors.py` | Error envelope source. |
| `Extension` | class | `backend/app/extensions/contract.py` | Static extension contribution contract. |
| `queryKeys` | const | `frontend/src/lib/query-keys.ts` | Canonical TanStack Query key registry. |
| `WorkflowPackageEditorPage` | component | `frontend/src/pages/workflow-packages/editor.tsx` | Package authoring workspace. |
| `SchemaForm` | component | `frontend/src/components/platform-authoring/generated-form/schema-form.tsx` | Schema-backed runtime input form. |

## Current Product Shape

- Workflow Packages are the only agent-workflow authoring root; package-local agents, output schemas, capability profiles, private MCP configs, HTTP operation nodes, and workflow graphs live in package YAML artifacts.
- Scheduled Tasks target Workflow Packages, use structured recurrence plus IANA timezones, and materialize due fires into ordinary queued runs.
- Model Connections are global encrypted provider/model bindings; Tools are read-only server-declared metadata at `/api/tools`.
- Runs store immutable package snapshots, inputs, per-step evidence, operation evidence, queue/progress state, retry/failure metadata, rerun lineage, and final outputs.
- `signaldeck.finance` is a static backend extension for templates, reports, finance providers, and finance runtime tools.
- `signaldeck.digital_oracle` is a static tool-only backend extension.
- Templates and Reports remain preserved product surfaces under `/api/v1` and browser routes `/templates` and `/reports`.

## Conventions

- Before changing code, read the applicable canonical docs linked in the managed navigation block, then apply the nearest subtree guide.
- Backend JSON is camelCase externally and snake_case internally; `CamelModel` owns aliases and request validation.
- Error envelopes are `{code, message, details[]}` and unsafe error detail keys are filtered before browser reads.
- Money, quantities, and market values cross the API as strings.
- Secret values must never appear in reads, exports, run details, logs, diagnostics, API error details, or metadata.
- Schema changes require DB rebuild; there is no migration framework. `backend/app/db/` uses `create_all`, bundled seeds, and startup recovery.
- Workflow Package parser owns source YAML safety and graph semantic validation before compile.
- Workflow Package compiler output must stay deterministic: sorted compiled sections, canonical JSON hashes, and no secret leakage.
- Package schemas are closed by default; do not add `additionalProperties`, `allowAdditionalProperties`, or `patternProperties`.
- Preflight intentionally projects different warning/blocker levels for validation, launch metadata, and strict readiness.
- Demo Workflow Package YAML is contract material; update parser/compiler/preflight tests and locked hashes when changing it.
- Frontend data fetching goes through feature hooks plus `queryKeys`; shared components stay presentational.
- Docker production artifacts are the split backend and frontend images; the root combined image is local/demo only.

## Anti-Patterns

- Do not add auth/RBAC, multi-tenant accounts, plugin marketplace, Studio, Tryout, orchestration, runtime-v2, memory, fork, portfolio, simulations, or backtests unless explicitly re-scoped.
- Do not introduce compatibility shims for removed product shapes.
- Do not reintroduce `corepack enable` in Node 26 Dockerfiles; use the pinned global pnpm install.
- Do not lift the FastAPI `<0.137` cap until Logfire allows `opentelemetry-sdk>=1.43` and FastAPI instrumentation resolves to `>=0.64b0`.

## Commands

```bash
(cd backend && uv sync)
(cd frontend && pnpm install)
(cd backend && uv run ruff check app tests && uv run black --check app tests && uv run isort --check-only app tests && uv run mypy app && uv run pytest)
(cd frontend && pnpm lint)
(cd frontend && pnpm typecheck)
(cd frontend && pnpm build)
(cd frontend && pnpm test:run)
(cd frontend && pnpm exec playwright install --with-deps chromium && pnpm test:e2e)
git diff --check
```

## Local Stack

```bash
./start.sh
docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml down -v
```

`start.sh` is the authoritative local/demo launcher and exposes only `http://localhost:${APP_PORT:-8080}`.
Set `SIGNALDECK_API_TOKEN` or use an authenticated reverse proxy before exposing SignalDeck outside a trusted network.

<!-- write-project-docs:document-navigation:start -->
## 项目文档导航

执行相关任务前，根据任务范围读取以下权威文档：

- [项目状态](STATUS.md)
- [文档索引](docs/README.md)
- [产品说明](docs/产品说明.md)
- [架构说明](docs/架构说明.md)
- [开发规范](docs/开发规范.md)
- [源代码规模与职责规则](docs/源代码规模与职责规则.md)
- [贡献指南](CONTRIBUTING.md)

实现、审查或验证工程变更时，结合 `STATUS.md` 和产品说明理解当前事实与交付意图，并读取贡献指南中实际存在的[当前迭代策略](CONTRIBUTING.md#当前迭代策略)。只消费与任务相关的本轮必做项、不可降低边界和重新推导条件；不要把明确暂缓或未被当前风险触发的事项自行扩大为工作。用户的新要求、活动 Goal、可达风险、硬性项目规则/不变量或有证据支持的审查发现一旦触发相关工作，暂缓描述不得压制它。该派生策略不扩大用户授权，MVP 快速验证开关也不定义或覆盖它；源事实变化或摘要漂移时不得沿用旧策略。

## 项目文档内容边界

本项目不需要为完善文档而引入流程或行政管理。

- 除非用户明确要求并提供可验证依据，不新增审批、汇报、会议、排期、人员治理、发布治理、提交管理、业务 KPI/SLO 或类似内容。
- 不为上述主题创建文档、章节、占位符或“待确认”项。
- 已有且经验证的开发、测试、构建和部署命令仍按对应权威文档记录；本区块不改变产品、架构或工程事实。
<!-- write-project-docs:document-navigation:end -->
