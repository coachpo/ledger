# Architecture Gap Register

This register continues the audit sequence from `00-contract-baseline.md`, `01-audit-checklist.md`, `02-current-architecture.md`, and `02-current-architecture-diagrams.md`. It records the architecture cleanup gaps and their current resolution status after S13, before the S15 final conformance report.

Severity scale:

| Severity | Meaning |
| --- | --- |
| P1 | Blocked the clean package-first architecture or carried notable security or runtime risk. |
| P2 | Material cleanup or precision issue that needed proof before final conformance. |
| P3 | Lower-risk cleanup that could follow higher-priority gaps. |

| ID | Area | Resolution status | Current live contract | Evidence |
| --- | --- | --- | --- | --- |
| GAP-001 | Legacy and global authoring ballast | Closed by S2, S4, S12, and S13 cleanup. | Workflow Packages are the only executable authoring root. Global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration-v2, and runtime-v2 are removed surfaces, not compatibility aliases or hidden routes. Package-private agents, output schemas, capability profiles, MCP configs, and workflow graphs live inside package artifacts. | S13 evidence records retired metadata bootstrap removal, live retired import quarantine, package-local output-schema validation, package-private MCP runtime behavior, and `test_current_backend_app_modules_do_not_import_retired_global_authoring_modules`. S2 and S12 evidence record removed-route and NotFound behavior. |
| GAP-002 | Startup repair and migration ballast for retired surfaces | Closed by S13 cleanup. | `backend/app/db/upgrades.py` remains the current PostgreSQL repair authority for live tables and live invariants only. Retired global authoring tables are drop-only cleanup targets, not backfill or repair targets. | S13 evidence records removal of retired metadata bootstrap, retired-table DML rejection, and `test_s13_retired_global_authoring_tables_are_drop_only_upgrade_targets`. |
| GAP-003 | Workflow Package export precision and secret-adjacent MCP fields | Closed by S5 cleanup. | Private MCP `env`, `headers`, and `query` are secret-bearing authoring/runtime config. Package exports and browser-visible reads omit those fields, along with database ids, run history, package secret binding rows, and raw package secret values. | S5 evidence records the export allowlist in `workflow_package_export.py`, backend export/security tests, and frontend export-preview coverage proving MCP env/header/query values are absent. |
| GAP-004 | Run finalization lease and status precision | Closed by S6 cleanup. | Queue ownership now keeps terminal writes tied to the active claim. Claimed execution rechecks `running` status plus matching `lease_owner` before result persistence and terminal finalization. | S6 evidence records passing runtime tests and the lease-owner terminal-write fix in `RunService.execute_claimed_run` and scheduler integration. |

## Register Notes

The register no longer recommends compatibility aliases, wrappers, or shims for removed global authoring surfaces. The S2-S13 cleanup favors current package-first architecture over preserving draft paths.

The remaining S14 and S15 work is verification and documentation alignment. S15 owns the final closed/deferred/obsolete classification report, route summary, command evidence, and final verdict.
