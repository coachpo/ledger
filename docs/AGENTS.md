# DOCS GUIDE

> Inherits `/AGENTS.md`. This file governs the live reference docs in `docs/`.
>
> Status: Docs consolidation reference for branch `main` at `154e3d8`.

## OVERVIEW

`docs/` has six canonical live owner documents: `prd.md`, `requirements.md`, `spec.md`, `data-model.md`, `test-plan.md`, and this `AGENTS.md`. Live code remains source of truth; these docs mirror the mounted browser/API surfaces and current persistence/runtime contracts, including package-first execution, backend-owned compatibility truth, platform-core memory, and finance-owned report history. Requirements companions under `docs/requirements/` and the `docs/architecture-audit/` workspace are evidence/context, not additional live owner docs.

Extension model: docs mirror the core app plus statically resident extensions; they should describe state-gated exposure, not marketplace installation or hot-loading.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative old paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or non-goal surfaces, not live acceptance paths.

Trusted single-user scope: Owner docs must frame auth, authorization, RBAC, login/session flows, user/account lifecycle, organizations, and multi-tenant account management as non-goals, not backlog items, unless the product scope is explicitly re-scoped.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK

| Task               | Location          | Notes                                                                                                                                           |
| ------------------ | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Product scope      | `prd.md`          | Goals, non-goals, product areas, success criteria, and package-first platform framing.                                                          |
| Requirements       | `requirements.md` | Functional/nonfunctional requirements and acceptance criteria.                                                                                  |
| Requirements evidence | `requirements/*.md` | Reverse-engineered requirements, traceability, and open-question baseline; context only, not live owner docs.                                |
| Technical behavior | `spec.md`         | Runtime topology, API conventions, Scheduled Tasks, backend/frontend architecture, validation gates, platform contracts, memory, and removed-surface boundaries. |
| Data model         | `data-model.md`   | Current tables, JSONB contracts, persistence boundaries, memory tables, and schema-repair rules.                                                |
| Test strategy      | `test-plan.md`    | Quality gates, coverage matrix, E2E ports, route-family coverage, and stale-claim guards.                                                       |
| Docs governance    | `AGENTS.md`       | Ownership rules, obsolete-content rules, anti-patterns, and consolidation policy.                                                               |
| Architecture audit | `architecture-audit/README.md` | Docs-only audit workspace; use as evidence and review history, not new product scope.                                               |

## CONTEXT WORKSPACES

`docs/requirements/` companion files and `docs/architecture-audit/` files may support audits, traceability, and reverse-engineered evidence. `docs/pending-design/` may keep research and upgrade-design notes that are not live contracts. Do not treat these workspaces, older root-doc references, or implementation sketches as canonical over the six owner docs or live code.

## CONVENTIONS

- Keep status lines aligned with the current branch and commit when refreshing docs.
- Keep removed surfaces only as explicit non-goals, out-of-scope items, or removed-route guardrails.
- Do not present Studio, Tryout, orchestration, runtime-v2, simulations, backtests, `/api/skills`, `/skills*`, or removed global authoring routes as live.
- `spec.md` owns consolidated route summaries, API conventions, runtime topology, backend/frontend behavior, and platform technical contracts.
- `requirements.md` owns testable functional and nonfunctional requirements.
- `prd.md` owns product framing and success criteria.
- `data-model.md` owns current persistence intent, not migration steps; `backend/app/db/` remains the schema-repair authority.
- `test-plan.md` owns expected validation scope, not implementation history.
- When documenting upgrades, keep platform-core behavior separate from extension-owned behavior.
- Document `/api/memory` and `/memory` as platform-core explicit-private-scope memory surfaces; keep runtime shared namespace grants server-derived and keep historical agent reports plus `signaldeck.reports.lookup` under finance/report ownership.
- Document Model Connection compatibility as backend-owned read/provenance truth; public writes may select `protocolProfile` but must not author capabilities, runtime policies, probe TTL, `apiStyle`, or `compatibilityProfile`.
- Document tool-call recovery as typed and narrow: only pre-dispatch parser/schema/argument validation failures can use the bounded model-feedback retry path.
- Document Scheduled Tasks as the package-first automation surface: `/api/schedules`, `/scheduled-tasks`, structured recurrence, scheduler materialization, fire history, and queued run provenance.
- Finance-specific examples must not silently rewrite shared platform contracts.
- PRD and requirements overlap is intentional: product framing lives in `prd.md`, testable requirements live in `requirements.md`.
- Keep `docs/requirements/` companions and `docs/architecture-audit/` files under this guide unless they become independent live-owner documentation trees.

## OBSOLETE CONTENT RULES

- Preserve the six canonical owner docs unless live code proves a file has no remaining owner.
- Keep root-level docs distilled to the six canonical owner files only; keep requirements companions and architecture-audit files from becoming duplicate owner docs.
- Merge stale live-surface claims into the correct owner file instead of duplicating details.
- Convert useful removed-surface material into explicit non-goals or removed-route guarantees.
- Delete obsolete passages that duplicate a live owner or contradict mounted routes, schemas, or tests.

## ANTI-PATTERNS

- Do not frame auth, authorization, RBAC, login/session flows, user/account lifecycle, organizations, or multi-tenant account management as backlog items unless the product scope is explicitly re-scoped.
- Do not add new docs for dead surfaces.
- Do not duplicate route tables across owner and reference docs without making `spec.md` the authoritative summary.
- Do not treat docs, old plans, or Alembic scaffolds as source of truth over live code.
- Do not move package-first platform details back into removed global authoring concepts.
- Do not add child `AGENTS.md` files under `docs/`; this file is the docs governance boundary.
- Do not leave stale branch/SHA status markers after refreshing docs.
- Do not re-expand research notes into duplicate route tables, data models, validation plans, or implementation checklists.
- Do not promote pending-design files or removed root docs as live contract sources after the six owner docs have been refreshed.
