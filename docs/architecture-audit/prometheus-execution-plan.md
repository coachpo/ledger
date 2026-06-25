# Prometheus Execution Plan

## TL;DR

Atlas executes the architecture cleanup as a current-contract-only sequence from S2 through S15. S2 locks route/API and audit-board coordination before any later cleanup, and every later slice remains blocked until S2 evidence passes review.

Prometheus review is evidence-based. Atlas writes source, docs, tests, and `.omo/evidence/slice-sXX/` artifacts; Prometheus reviews those artifacts and should not edit source files.

The cleanup favors deletion and direct replacement over compatibility. Do not add redirects, aliases, dual DTOs, old-path wrappers, hidden legacy routes, feature flags for removed behavior, or migration ballast for unreleased retired surfaces.

## Slice Mapping S2-S15

| Requested slice | Existing audit source | Execution decision |
| --- | --- | --- |
| S2 | Existing S02 plus S01 contract hardening | Route/API cleanup, removed-surface absence preservation, and audit board sync. |
| S3 | Existing S03 | Backend API/application/domain/ports/infrastructure boundary cleanup. |
| S4 | Existing S04 | Workflow Package manifest and package-local resource cleanup. |
| S5 | Existing S04A plus S05 | Export trust boundary, launch, preflight, runtime inputs, and queued run creation. |
| S6 | Existing S06 | Worker-owned runtime execution and run evidence persistence. |
| S7 | Existing S07 | Scheduled Tasks recurrence, fire materialization, preview, and run-now queueing. |
| S8 | Existing S08 plus HTTP operation tests | Model connections, secrets, and fail-closed HTTP operation safety. |
| S9 | Existing S09 | Read-only tool catalog and separate grant-aware runtime dispatch. |
| S10 | Existing S10 | Platform-core explicit-scope memory. |
| S11 | Existing S11 | Extension boundaries, Finance isolation, and Digital Oracle tool-only behavior. |
| S12 | Existing S12 | Frontend package-first route tree and UX cleanup. |
| S13 | Existing S13 | Current-contract persistence and startup repair cleanup. |
| S14 | Existing S14 | API conventions, browser-safe errors, observability, and docs cleanup. |
| S15 | Missing in current board | Final conformance review and `99-final-conformance-report.md`. |

## Dependency Matrix

S2 blocks all later slices. S3 blocks S4 through S13. S4 blocks S5. S5 blocks S6 and S7. S6 blocks S7 and S15. S8 blocks S15. S9 blocks S11 and S15. S10 blocks S15. S11 blocks S12, S13, and S15. S12 blocks S15. S13 blocks S14 and S15. S14 blocks S15.

Execution waves:

1. Wave 1: S2 only.
2. Wave 2: S3, then S4 and S5 after S3 is green.
3. Wave 3: S6, then S7 after queue/run semantics are stable.
4. Wave 4: S8, S9, S10, and S11 only where file scopes do not overlap; otherwise numeric order.
5. Wave 5: S12 after backend route, extension, tool, and memory contracts are stable.
6. Wave 6: S13 after S2, S3, and S11 prove retired imports are absent.
7. Wave 7: S14 followed by S15 final conformance.

## Per-Slice Evidence Rules

Each implementation slice must create `.omo/evidence/slice-sXX/` and write command output there. The required minimum bundle is `report.md`, `changed-files.txt`, and one or more command-output text files named for the surface being verified.
Every slice report must include these sections: goal, files inspected, files changed, legacy/non-contract code deleted, tests added/changed/deleted, commands run, results, remaining risk, and requested Prometheus verdict.

Command evidence must include exact commands and raw stdout/stderr. Diff evidence must come from `git diff --name-only` and, where useful, `git diff --stat`. If a tool is unavailable, record the exact failure and the fallback used.

Prometheus review input after every slice is the slice report plus changed-files evidence and command-output evidence. Do not mark a slice complete from intent alone.

## S2 Acceptance Commands

Backend route/API command:

```bash
cd backend && uv run pytest tests/test_workflow_package_openapi.py tests/test_api.py
```

Frontend route command:

```bash
cd frontend && pnpm test:run -- --run src/routes.test.tsx
```

S2 acceptance requires removed backend routes to return 404 and stay absent from OpenAPI, removed frontend routes to render the product NotFound page, and live finance/platform routes to remain registered. S2 also requires the execution board to use requested S2-S15 labels, with S2 marked only `Pending` or `In Progress` until independent review.

## Prometheus Review Checklist

1. No non-contract legacy path is preserved or introduced.
2. No compatibility shim, alias, duplicate route, dual model, or migration ballast is added.
3. Clean architecture dependency direction is maintained for touched code.
4. No speculative auth, tenancy, user, migration, marketplace, plugin, SLA, compliance, i18n, or accessibility framework is added.
5. Workflow Packages remain the only executable authoring root.
6. Launches queue runs; worker/runtime owns execution.
7. Secrets and error details remain browser-safe and log-safe.
8. Tests prove live behavior and removed behavior absence.
9. Docs describe current behavior only.
10. Changes are direct, maintainable, and current-contract-only.

## Final Wave Summary

After S14, S15 reruns the architecture checklist, classifies every gap as closed, obsolete, intentionally deferred, or failed, and creates `docs/architecture-audit/99-final-conformance-report.md`.

The final wave must run independent review for plan compliance, code quality, real manual QA, and scope fidelity. Final evidence must include backend quality and tests, frontend lint/type/build/unit tests, Playwright E2E or a precise environment blocker, the final conformance report, and a consolidated risk/verdict summary.

S15 must not introduce new product behavior. It may edit only tests or docs when final verification reveals incorrect documentation or missing verification.
