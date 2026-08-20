# Runs UI Guide

## Overview

Run routes are evidence-oriented inspection surfaces for queued/running/completed executions, immutable package snapshots, operation evidence, failures, outputs, and reruns.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| List route | `list.tsx` | Run filters, status, and navigation. |
| Detail route | `detail.tsx` | Main inspection workspace. |
| Detail helpers and sections | `detail-helpers.ts`, `detail-http-operations.test.tsx`, `detail-sections.exports.test.ts` | Payload, runtime, HTTP evidence, and output inspection helpers/tests. |
| Tab state | `detail-tabs.ts` | URL-safe tab parsing. |
| Inspection state | `inspection-state.ts` | Target resolution for step/tool/operation panes. |
| Rerun dialog | `rerun-dialog.tsx` | Rerun draft edits from frozen snapshot. |

## Conventions

- Treat run data as immutable evidence. Reruns derive from frozen snapshots, not current package definitions.
- Poll only active runs and keep polling conditional.
- Keep tab and inspection target state URL-safe so deep links restore the same evidence pane.
- Show package provenance and compiled plan safely; private MCP `env`, `headers`, and `query` values stay redacted.
- Cancel queued runs immediately; running runs stop cooperatively at step boundaries.
- Rerun edits are limited to root launch parameters exposed by the rerun draft.
- Delete removes one run, not source package/schedule state.

## Anti-Patterns

- Do not render raw tool/provider exception traces or secret-bearing payloads.
- Do not infer run state from UI labels when API status/progress fields exist.
- Do not collapse HTTP operation evidence into agent step evidence; both are first-class.
