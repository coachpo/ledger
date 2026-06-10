# Architecture Gap Summary

This summary records how the highest-value deviations from `02-current-architecture.md` and `02-current-architecture-diagrams.md` were resolved through the S2-S13 cleanup sequence. It is a live audit summary for the S14 handoff, not the final S15 conformance report.

## Resolved Deviations

1. Legacy and global authoring ballast is no longer treated as live architecture. S2 and S12 preserved removed-route absence, S4 kept package-local authoring semantics, and S13 removed live retired global authoring imports while keeping Workflow Packages as the only executable authoring root.

2. Startup repair is narrowed to current live table repair. S13 kept live PostgreSQL repair paths and changed retired global authoring tables to drop-only cleanup targets, with static tests rejecting retired-table DML and retired model-connection snapshot repair.

3. Workflow Package export now has a single secret-safe rule for private MCP request config. S5 classified private MCP `env`, `headers`, and `query` as secret-bearing authoring/runtime config and removed them from exports and browser-visible manifest reads.

4. Run finalization ownership was resolved by S6. Claimed execution now carries the queue lease owner into finalization and checks the active `running` claim before terminal persistence, preserving worker-owned execution without adding a second queue system.

## Aligned Areas

1. Route composition is aligned. `backend/app/main.py`, `backend/app/api/platform_router.py`, and `backend/app/api/router.py` keep platform `/api/*` routes separate from extension-owned `/api/v1/*` contributions.

2. Package-first launch queueing is aligned. Workflow Package launch, rerun, fork, and schedule-fire flows create queued run rows rather than executing packages inline.

3. Scheduled task materialization is aligned. Scheduled Tasks use structured recurrence, IANA timezones, backend rendering, fire rows, and queued run provenance.
4. Extension slim state and gating are aligned. `/api/extensions` exposes only `key`, `label`, and `enabled`, while frontend runtime helpers filter route, navigation, and tool visibility from backend extension state.

5. Digital Oracle is aligned as tool-only. It owns the three phase-1 tools and contributes no route, navigation, provider bundle, or lifecycle surface.

6. Frontend route and navigation gating are aligned. The live router keeps platform routes, Finance extension routes, removed-route NotFound behavior, and `/api/*` browser route absence covered.

7. CI quality gates are aligned. `.github/workflows/ci.yml` runs backend lint, format, type, and test checks; frontend lint, type, build, and unit checks; and Chromium E2E after quality jobs.

## S14 Handoff

S14 does not add product behavior. It checks API conventions, error envelopes, readiness, optional telemetry, and live docs. S15 owns the final conformance verdict and `99-final-conformance-report.md`.
