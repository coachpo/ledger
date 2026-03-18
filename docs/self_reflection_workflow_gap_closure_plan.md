# Self-Reflection Workflow Gap Closure Plan

## Purpose

Define a focused implementation plan that closes the gaps between Ledger's current template/report system and the self-reflection stock analysis workflow described in `docs/self_reflection_stock_analysis_loop.md`.

This plan treats Ledger as:

- a prompt-generation system driven by templates plus live portfolio data,
- a report store for generated analysis output,
- and a queryable report history that can feed later prompt cycles.

This plan does **not** turn Ledger into the automation engine itself. External automation and manual human triggers remain responsible for deciding when to run each review cycle.

## Confirmed Decisions

The following inputs are fixed for this plan:

- Workflow execution may be triggered by external automation or by a human manually.
- Reports keep an extensible `metadata` JSON structure; the system may standardize a small queryable subset without restricting additional keys.
- The target placeholder direction includes at least:
  - `{{reports.latest}}`
  - `{{reports.latest("AAPL")}}`
  - `{{reports[0]}}`
  - `{{reports.by_tag("weekly_review").latest}}`
- Selected report `content` must compile inline through the placeholder system.
- Missing optional data should be skipped rather than becoming a hard blocker for the workflow.

## Current Gaps

Ledger already provides strong portfolio inputs, template compilation, and persisted markdown reports, but it still misses the following workflow-critical capabilities:

1. Reports cannot be selected relatively by recency or index.
2. Reports cannot be filtered by queryable workflow metadata such as ticker or review type.
3. Compiled reports do not currently accept workflow metadata at creation time.
4. Automation-friendly report creation is weak because the current create paths are template-compile and multipart markdown upload only.
5. The placeholder browser shows exact report names, but not dynamic query patterns.
6. The report list API does not support filtered retrieval for workflow tooling.

## Success Criteria

After this plan is implemented, Ledger is sufficient for the intended role if all of the following are true:

- A template can reference the latest relevant prior report without hardcoding a timestamped report name.
- External automation can create a new report and attach structured workflow metadata in one request.
- A human can still create and browse reports through the existing UI without losing current behavior.
- Missing prior reports or missing optional metadata do not break prompt generation.
- The report history remains point-in-time and traceable, even if report content stays editable in the first release.

## Recommended Target Design

## 1. Keep `metadata` JSONB, but standardize a queryable subset

Keep the existing `reports.metadata` JSONB column as the extensibility mechanism. Do not replace it with rigid workflow-specific columns.

Add a documented canonical subset used by selectors and automation:

```json
{
  "author": "optional existing field",
  "description": "optional existing field",
  "tags": ["weekly_review", "reflection"],
  "analysis": {
    "ticker": "AAPL",
    "portfolioSlug": "core_us",
    "reviewType": "weekly_review",
    "trigger": "manual",
    "reviewDate": "2026-03-18",
    "versionGroup": "aapl_core_loop"
  }
}
```

Recommended rules:

- `tags` remains the lightweight cross-cutting grouping mechanism.
- `analysis.ticker` is the canonical field used by `reports.latest("AAPL")`.
- `analysis.reviewType` is the canonical field for workflow classification.
- `analysis.portfolioSlug` links a report back to the relevant portfolio context.
- `analysis.trigger` stores whether the run was manual, scheduled, or event-driven.
- Additional keys remain allowed and ignored by selectors unless explicitly supported later.

This gives the workflow a stable query contract without losing JSON extensibility.

## 1a. Make the metadata contract extensible in code, not just in storage

Keeping JSONB is not enough by itself because the current request/response schema is strict.

The implementation plan must explicitly loosen the metadata type contract so unknown metadata keys can round-trip safely while the canonical queryable subset stays documented.

Recommended rules:

- Backend request validation must accept additional metadata keys beyond the canonical subset.
- Backend read schemas must preserve unknown metadata keys instead of dropping them.
- Frontend report types must allow the canonical keys while still carrying unknown metadata through reads.
- Selector logic must only depend on the documented canonical subset.

This keeps the storage model extensible in practice, not only in theory.

## 2. Extend report creation for automation and compiled snapshots

Ledger needs a create path that can persist report content plus metadata in a single request, without requiring file upload.

Recommended API changes:

- Extend `POST /api/v1/reports/compile/{templateId}` to accept an optional JSON body with metadata.
- Add `POST /api/v1/reports` for direct JSON report creation by automation or manual tools.
- Keep `POST /api/v1/reports/upload` for browser-based markdown file upload.

Recommended JSON create contract:

```json
{
  "name": "optional explicit name",
  "slug": "optional explicit slug",
  "source": "external",
  "content": "# AAPL Weekly Review\n...",
  "metadata": {
    "tags": ["weekly_review"],
    "analysis": {
      "ticker": "AAPL",
      "portfolioSlug": "core_us",
      "reviewType": "weekly_review",
      "trigger": "manual",
      "reviewDate": "2026-03-18"
    }
  }
}
```

Notes:

- `source` should expand from `compiled | uploaded` to `compiled | uploaded | external`.
- Creation-time metadata should be allowed for both compiled and direct-created reports.
- Report metadata should stay immutable after creation in the first implementation so report snapshots remain trustworthy.
- Report content may remain editable in the first implementation; if strict auditability becomes mandatory later, that should be handled by a separate read-only or version-on-edit policy.
- Canonical metadata values should be normalized at creation time:
  - `analysis.ticker` -> uppercase
  - `analysis.portfolioSlug` -> existing portfolio slug format
  - `analysis.reviewType` and `tags` -> documented normalized casing

## 3. Introduce a report-selector pipeline inside the template compiler

The current `reports.<name>` path resolver should evolve into a selector pipeline that still supports exact-name references for backward compatibility.

Recommended selector semantics:

- `{{reports.latest}}`
  - newest report globally by `created_at DESC`
- `{{reports.latest("AAPL")}}`
  - newest report where `metadata.analysis.ticker == "AAPL"`
- `{{reports[0]}}`
  - newest global report, zero-based newest-first indexing
- `{{reports.by_tag("weekly_review").latest}}`
  - newest report whose `metadata.tags` contains `weekly_review`

Recommended field access after selection:

- `{{reports.latest.name}}`
- `{{reports.latest.slug}}`
- `{{reports.latest.created_at}}`
- `{{reports.latest.content}}`
- `{{reports.by_tag("weekly_review").latest.content}}`
- `{{reports[0].content}}`

Recommended selector compatibility rules:

- Recency ordering must be stable everywhere selectors use it: `created_at DESC, id DESC`.
- Reserved dynamic selector keywords should include at least `latest` and `by_tag(...)`.
- Add an explicit exact-name escape hatch such as `{{reports.by_name("...")}}` so reports whose names collide with reserved selector keywords still remain addressable.
- Keep existing `{{reports.<name>}}` behavior for currently supported exact-name paths that do not collide with reserved selector syntax.
- Defer generic nested metadata rendering such as `{{reports.latest.metadata}}` from the first release unless a precise output format is defined.

Recommended result behavior:

- If the selector is valid but no report matches, render an empty string.
- If the selector syntax is malformed, keep the current explicit sentinel behavior.
- If `.content` is selected, compile the referenced report inline with existing cycle detection.

This preserves the current safety model while meeting the "skip unavailable data" requirement.

## 4. Add filtered report retrieval to the API

Templates are not the only consumer. External workflow tooling will also need filtered list access.

Recommended `GET /api/v1/reports` query parameters:

- `ticker`
- `tag`
- `reviewType`
- `portfolioSlug`
- `source`
- `limit`
- `offset`

Recommended behavior:

- Default order remains newest first.
- Filters are optional and combinable.
- List filtering uses the canonical metadata subset only.
- Unknown or absent metadata values simply exclude the report from the filtered result.

This makes Ledger usable as the storage layer behind external automation without requiring clients to fetch and filter the full report history locally.

## 5. Update the placeholder browser and report UX

The template editor should expose the new selector patterns explicitly instead of forcing users to guess the syntax.

Recommended frontend changes:

- Keep existing exact-name report insertion for backward compatibility.
- Add a new "Dynamic report selectors" section in the placeholder reference panel.
- Include clickable examples for:
  - `{{reports.latest}}`
  - `{{reports.latest("AAPL")}}`
  - `{{reports[0]}}`
  - `{{reports.by_tag("weekly_review").latest}}`
- Show the canonical metadata keys required for selector-based matching.
- Update report create/generate flows to let users attach metadata when relevant.

The goal is to make the system understandable from the UI, not only from backend documentation.

## Implementation Phases

## Phase 1. Data Contract And Persistence Foundation

Primary goal: make reports carry stable workflow metadata and source values.

Backend touchpoints:

- `backend/app/models/report.py`
- `backend/app/schemas/report.py`
- `backend/app/services/report_service.py`
- `backend/app/api/reports.py`
- `backend/app/db/session.py`
- `frontend/src/lib/types/report.ts`
- `backend/tests/test_api.py`
- `docs/data-model.md`
- `docs/api-design.md`
- `docs/requirements.md`
- `docs/spec.md`

Tasks:

- Expand report `source` semantics to include `external`.
- Add request schemas for creation metadata on compile and direct-create flows.
- Update schema typing so unknown metadata keys can round-trip safely.
- Preserve metadata immutability after creation.
- Add DB migration logic for any new enum-like constraints or indexes.

Exit condition:

- Both compiled and direct-created reports can persist the canonical workflow metadata subset at creation time.

## Phase 2. Queryable Report Retrieval

Primary goal: expose filtered report access for automation and UI growth.

Backend touchpoints:

- `backend/app/repositories/report.py`
- `backend/app/services/report_service.py`
- `backend/app/api/reports.py`
- `backend/app/schemas/report.py`
- `backend/tests/test_api.py`
- `docs/api-design.md`
- `docs/spec.md`

Tasks:

- Add repository query methods for filter combinations and newest-first selection.
- Add `GET /reports` query params for the canonical metadata subset.
- Add optional pagination controls.
- Keep current unfiltered behavior as the default.

Exit condition:

- External tooling can request only the relevant report subset without downloading all reports.

## Phase 3. Template Compiler Selector Grammar

Primary goal: let templates reference prior reports dynamically.

Backend touchpoints:

- `backend/app/services/template_compiler_service.py`
- `backend/app/repositories/report.py`
- `backend/app/services/report_service.py`
- `backend/tests/test_api.py`
- `docs/spec.md`

Tasks:

- Introduce a parser/resolver path for dynamic `reports` selectors.
- Preserve exact-name support for `{{reports.<name>}}` and `{{reports.<name>.content}}`.
- Support the first selector set:
  - `.latest`
  - `.latest("TICKER")`
  - `[index]`
  - `.by_tag("tag").latest`
- Support scalar field access and `.content` after selector resolution.
- Preserve cycle detection for inline compiled content.
- Return empty output for valid no-match selectors.

Exit condition:

- A template can reference prior reports without hardcoded timestamped names.

## Phase 4. Frontend Authoring And Workflow UX

Primary goal: make the new capability usable from the UI.

Frontend touchpoints:

- `frontend/src/pages/templates/editor.tsx`
- `frontend/src/lib/types/text-template.ts`
- `frontend/src/lib/types/report.ts`
- `frontend/src/lib/api/reports.ts`
- `frontend/src/hooks/use-reports.ts`
- `frontend/src/pages/reports/list.tsx`
- `frontend/src/pages/reports/detail.tsx`
- `frontend/e2e/reports.spec.ts`
- related frontend test files as needed

Tasks:

- Add selector examples and metadata guidance to the placeholder browser.
- Add metadata entry fields where compiled reports or externally created reports are initiated from the UI.
- Add minimal metadata visibility on report list/detail views so users can verify why a report matched a selector.
- Surface filtered report browsing if the existing reports page becomes too noisy for version history.

Exit condition:

- Users can discover and use the new selector model without reading backend code.

## Phase 5. Verification, Backward Compatibility, And Rollout

Primary goal: land the feature without breaking current templates or report flows.

Required backend test additions:

- compile report with metadata
- direct JSON report create
- filtered report list by tag, ticker, review type, and source
- `{{reports.latest}}`
- `{{reports.latest("AAPL")}}`
- `{{reports[0]}}`
- `{{reports.by_tag("weekly_review").latest}}`
- `.content` inline compilation through all supported selectors
- no-match selectors render empty output
- malformed selectors still render explicit sentinel text
- backward-compatible exact-name placeholders still pass

Required frontend test additions:

- placeholder browser shows dynamic selector examples
- metadata entry survives report creation flow
- end-to-end generation and reuse of selector-driven templates

Rollout order:

1. persistence and create contracts
2. filtered retrieval
3. placeholder selector grammar
4. frontend affordances
5. docs refresh

## Recommended Database Strategy

Keep `reports.metadata` in JSONB and add indexes that support the new read patterns.

Recommended first pass:

- add a GIN index on `metadata`
- add a btree index on `created_at DESC`

Recommended follow-up only if query volume proves it necessary:

- expression index for `metadata -> 'analysis' ->> 'ticker'`
- expression index for `metadata -> 'analysis' ->> 'reviewType'`

This keeps the first implementation flexible and avoids prematurely freezing the metadata shape.

## Backward Compatibility Rules

- Existing exact-name placeholders must keep working unchanged.
- Existing uploaded-report metadata (`author`, `description`, `tags`) must remain valid.
- Existing report detail and download flows must remain slug-based.
- Existing templates that do not use dynamic selectors must not change output.

## What This Plan Deliberately Does Not Add

- no internal scheduler
- no autonomous orchestration engine
- no stock-analysis chat/session domain model inside Ledger
- no hard requirement that every report carries every workflow metadata key
- no hard failure when optional prior reports are missing

Those concerns remain outside Ledger's responsibility based on the stated role of the application.

## Final Recommendation

Implement the plan in the phase order above and keep the first release narrow:

- standardize a small queryable metadata subset,
- allow automation-friendly report creation,
- add the initial report selector grammar,
- and preserve exact-name compatibility.

That scope is enough to make Ledger a reliable prompt-input and report-history layer for the self-reflection stock analysis loop, while leaving orchestration, scheduling, and model execution outside the app.
