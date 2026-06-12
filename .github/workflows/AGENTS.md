# CI WORKFLOWS GUIDE

> Inherits `/AGENTS.md`. This file covers repository automation under `.github/workflows/`.

## OVERVIEW
`.github/workflows/` owns repository automation for version sync, backend/frontend quality gates, browser E2E, container image publishing, and cleanup. These workflows are operational guardrails for the current package-first platform and must stay aligned with the live backend/frontend toolchains and startup assumptions.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add CI tracks for auth, RBAC, tenant isolation, login/session flows, or account-management work unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Main CI gates | `ci.yml` | version sync, backend quality, frontend quality, and frontend E2E |
| Container publishing | `docker-images.yml` | GHCR image builds for backend/frontend on linux/arm64 |
| Retention cleanup | `cleanup.yml` | workflow-run retention and untagged container cleanup |

## CONVENTIONS
- `ci.yml` is the authoritative CI gate sequence: `version-sync`, `backend-quality`, `frontend-quality`, then `frontend-e2e`.
- Backend CI installs with `uv sync --frozen`; frontend CI installs with `pnpm install --frozen-lockfile`.
- Version-sync must keep `backend/VERSION` aligned with `backend/pyproject.toml` and `frontend/VERSION` aligned with `frontend/package.json`.
- Browser E2E uses Chromium only and depends on the dedicated backend/frontend startup helpers already encoded in the frontend project.
- Docker publishing stays scoped to backend/frontend images and linux/arm64 builds unless the repo explicitly broadens release policy.
- Cleanup must preserve a minimum recent-run history and only remove untagged package versions.

## ANTI-PATTERNS
- Do not add auth, RBAC, tenant-isolation, login/session, or account-management CI gates unless the product scope changes.
- Do not weaken frozen-install, lint, typecheck, build, or test gates without updating the documented validation contract.
- Do not add CI assumptions that diverge from the live toolchain versions in backend/frontend manifests.
- Do not turn cleanup workflows into destructive tagged-release deletion paths.
- Do not add deployment, secrets, or environment-specific release behavior here unless the repo explicitly adopts that operational surface.
