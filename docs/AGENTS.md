# DOCS GUIDE

> Inherits `/AGENTS.md`. This file governs the live reference docs in `docs/`.

## OVERVIEW
`docs/` is the live product, requirements, spec, API, data-model, test, platform, run-input, and memory reference set. Live code remains source of truth; docs mirror the mounted browser/API surfaces and current persistence/runtime contracts.

The application is under active development and has no users at the moment; future upgrade, migration, and compatibility design must account for that and should not preserve speculative legacy paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Product scope | `prd.md` | goals, non-goals, product areas, package-first platform framing |
| Requirements | `requirements.md` | functional/nonfunctional requirements and acceptance criteria |
| Technical behavior | `spec.md` | runtime topology, backend/frontend architecture, validation gates |
| API contracts | `api-design.md` | route families, request/response conventions, removed-route guarantees |
| Data model | `data-model.md` | current tables, JSONB contracts, schema-repair boundaries |
| Test strategy | `test-plan.md` | quality gates, E2E ports, route-family coverage |
| Run input help | `run-input-schema-helptext.md` | supported schema display metadata and unsupported help mechanisms |
| Platform reference | `ledger-agent-platform.md` | Workflow Packages, Model Connections, Tools, Runs, retired-platform boundaries |
| Memory design | `ledger-memory-layer-design.md` | report-backed phase-1 memory services, metadata, runtime tool boundaries |

## CONVENTIONS
- Keep each status line aligned with the current root AGENTS commit and branch metadata.
- Keep retired surfaces only as explicit non-goals, out-of-scope items, or removed-route guardrails.
- Do not present Studio, Tryout, orchestration, runtime-v2, simulations, backtests, `/api/skills`, `/skills*`, or retired global authoring routes as live.
- `api-design.md` owns preserved API route tables and platform endpoint summaries.
- `ledger-agent-platform.md` owns package-first platform contracts and retired-platform boundaries.
- `data-model.md` documents current persistence intent, not migration steps; `backend/app/db/` remains the schema-repair authority.
- `test-plan.md` records expected validation scope, not implementation history.
- PRD and requirements overlap is intentional: product framing lives in `prd.md`, testable requirements live in `requirements.md`.

## OBSOLETE CONTENT RULES
- No docs files currently need deletion.
- Preserve the current nine-file docs set unless live code proves a file has no remaining owner.
- Merge stale live-surface claims into the correct owner file instead of duplicating details.
- Convert useful retired-surface material into explicit non-goals or removed-route guarantees.
- Delete obsolete passages that duplicate a live owner or contradict mounted routes, schemas, or tests.

## ANTI-PATTERNS
- Do not add new docs for dead surfaces.
- Do not duplicate route tables outside `api-design.md` and `ledger-agent-platform.md`.
- Do not treat docs, old plans, or Alembic scaffolds as source of truth over live code.
- Do not move package-first platform details back into retired global authoring concepts.
- Do not add child `AGENTS.md` files under `docs/`; this file is the docs governance boundary.
- Do not leave stale branch/SHA status markers after refreshing docs.
