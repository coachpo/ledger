# Architecture Audit Workspace

This directory is a repo-local audit workspace for turning the current requirement baseline into code-reviewable checks. It is documentation-only and does not define new product scope.

## Documents

1. `00-contract-baseline.md` records the in-scope boundaries, out-of-scope boundaries, non-negotiable architecture rules, and legacy paths to delete rather than preserve.
2. `01-audit-checklist.md` turns that baseline into executable checks grouped by backend, runtime, extension, frontend, API, persistence, tests, and CI evidence.

## Authoritative Inputs

The audit starts from these requirement files:

- `docs/requirements/reverse-requirements.md`
- `docs/requirements/traceability-matrix.md`
- `docs/requirements/open-questions.md`

If those paths ever move, locate equivalent content first and record the actual paths before updating this workspace. In the current baseline, all three files exist and `open-questions.md` says no true open questions remain.

## How To Use

1. Read `00-contract-baseline.md` first. Treat it as the audit contract.
2. Execute `01-audit-checklist.md` group by group against the cited code and tests.
3. Mark each checklist item as pass, fail, or `needs code evidence`.
4. When evidence is missing, do not preserve old behavior by default. Record `needs code evidence` and prefer direct replacement unless a requirement explicitly names the old path as a live contract.
5. Keep findings tied to concrete files, symbols, routes, schemas, models, tests, or CI jobs.

## Scope Rules

- Only files under `docs/architecture-audit/` belong to this workspace.
- Do not edit implementation files while performing this audit pass.
- Do not propose compatibility shims for unreleased or non-contract paths.
- Keep platform-core behavior separate from Finance and Digital Oracle extension ownership.
- Keep Digital Oracle tool-only unless a future requirement explicitly creates a route or nav contract.
