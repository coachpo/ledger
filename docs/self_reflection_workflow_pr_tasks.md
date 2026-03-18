# Self-Reflection Workflow PR Tasks

> Status: Historical PR breakdown. The report-contract, filtering, selector, and frontend authoring foundations described here are substantially shipped; treat this file as rollout history plus a source of follow-up hardening ideas.

## Purpose

Break `docs/self_reflection_workflow_gap_closure_plan.md` into PR-sized implementation tasks that can be reviewed and shipped incrementally.

## PR-1 Report Contract Foundation

Scope:

- add extensible report metadata support in backend schemas and frontend wire types
- add `external` as a valid report source
- add direct JSON report creation
- add compile-time metadata input for report generation
- update core docs to match the new contract

Acceptance criteria:

- `POST /api/v1/reports` creates an `external` report from JSON
- `POST /api/v1/reports/compile/{templateId}` accepts optional metadata input
- unknown metadata keys round-trip through read responses
- existing upload, update, download, and exact-name placeholder behavior still works

## PR-2 Queryable Report Retrieval

Scope:

- extend `GET /api/v1/reports` with filter parameters for canonical workflow metadata
- add repository support for combined filters and stable newest-first ordering
- document the list-query contract

Acceptance criteria:

- report list can be filtered by canonical workflow fields without client-side full-list scanning
- default ordering is stable and documented as newest first
- unfiltered list behavior remains backward compatible

## PR-3 Dynamic Report Selectors In Templates

Scope:

- extend the report placeholder grammar to support dynamic selection
- implement the first selector set: `latest`, `latest("TICKER")`, `[index]`, and `by_tag("tag").latest`
- preserve exact-name placeholders and cycle detection

Acceptance criteria:

- templates can reference prior reports without hardcoded timestamped names
- valid no-match selectors render empty output
- malformed selectors render explicit sentinel output
- existing `{{reports.<name>}}` placeholders still compile

## PR-4 Frontend Authoring Support

Scope:

- expose dynamic selector examples in the template editor
- show minimal report metadata context in the reports UI
- keep current report list/detail flows working with the expanded report contract

Acceptance criteria:

- the placeholder browser shows dynamic selector examples
- report list/detail views remain type-safe with `external` sources and extensible metadata
- no existing generate, upload, edit, download, or delete flow regresses

## PR-5 Workflow Hardening And Follow-up Coverage

Scope:

- add missing backend and frontend regression coverage across the new workflow surface
- tighten edge-case handling for metadata normalization, selector collisions, and compatibility rules
- refresh docs after implementation settles

Acceptance criteria:

- backend tests cover creation, retrieval, and selector edge cases
- frontend tests cover new compatibility behavior and placeholder guidance
- docs match shipped behavior, not planned behavior only

## Recommended Merge Order

1. PR-1 Report Contract Foundation
2. PR-2 Queryable Report Retrieval
3. PR-3 Dynamic Report Selectors In Templates
4. PR-4 Frontend Authoring Support
5. PR-5 Workflow Hardening And Follow-up Coverage
