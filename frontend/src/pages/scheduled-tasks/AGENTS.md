# Scheduled Tasks UI Guide

## Overview

Scheduled Task routes own recurrence authoring, timezone-aware previews, schedule detail, fire history, run-now, and stale Workflow Package handling.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| List route | `list.tsx` | Inventory view and schedule status actions. |
| Editor route | `editor.tsx` | Create/edit form and recurrence payloads. |
| Detail route | `detail.tsx` | Preview, fire history, run-now, linked runs, stale guards. |
| Recurrence helpers | `pickers.tsx`, `time-zones.ts` | Timezone and recurrence inputs. |
| Tests | `editor.test.tsx` | Authoring payload and route behavior. |

## Conventions

- Recurrence is structured: `interval`, `daily`, `weekly`, or `monthly` plus IANA timezone.
- Preview is safe and does not persist schedule state.
- Runtime input templates are seeded from Workflow Package schemas and may reference `schedule`, `fire`, `window`, `lastRun`, and `vars`.
- Stale/missing Workflow Package state must block unsafe edits or run-now actions with explicit user feedback.
- Run-now creates an ordinary queued run and should invalidate schedule detail, fire history, runs, and linked package views.
- Deleting a schedule removes future automation and schedule-owned fire rows; existing runs stay visible through run-owned schedule provenance.

## Anti-Patterns

- Do not treat local browser timezone as the persisted schedule timezone.
- Do not mutate recurrence preview data into saved schedule state by side effect.
- Do not hide overlap/misfire policy consequences from detail or editor flows.
