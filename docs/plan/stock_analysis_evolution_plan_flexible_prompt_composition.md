# Stock Analysis Evolution Plan: From Rigid Two-Step to Flexible Prompt Composition

**Generated:** 2026-03-14
**Status:** Verified by Oracle
**Scope:** Gap analysis + implementation plan for flexible prompt composition system

---

## SECTION 1: GAP SUMMARY TABLE

| Gap ID | Title | Severity | Complexity | Dependencies |
|--------|-------|----------|------------|--------------|
| GAP-1 | Rigid Two-Step Workflow vs. Flexible Prompt Composition | Critical | L | GAP-7, GAP-8 |
| GAP-2 | No Snippet Entity | Medium | M | None |
| GAP-3 | Limited Placeholder System | Critical | L | GAP-2 |
| GAP-4 | No Async Status Tracking / Polling | High | M | None |
| GAP-5 | No Prompt Composition UI | High | L | GAP-1, GAP-3, GAP-4 |
| GAP-6 | Conversation Model Mismatch | Low | S | GAP-3 (no work needed) |
| GAP-7 | Template Structure Mismatch | High | M | None |
| GAP-8 | Gateway Schema Coupling | High | M | GAP-1 |
| GAP-9 | Version Materialization Coupling | - | - | ELIMINATED (see Addendum 2) |

---

## SECTION 2: PER-GAP IMPLEMENTATION APPROACH

### GAP-1: Rigid Two-Step Workflow -> Flexible Prompt Composition

**Data model changes:**
- Add `mode` column to `StockAnalysisRun`: `"single_prompt"` | `"two_step_workflow"` (default `"single_prompt"`, CHECK constraint). Existing rows backfill to `"two_step_workflow"`.
- Add `step` value `"single"` to `StockAnalysisRequest` CHECK constraint (currently only `fresh_analysis`, `compare_decide_reflect`, `follow_up`).
- SQLite upgrade function in `session.py` to add the column and widen the constraint.

**Backend service changes:**
- Split `execute_run_workflow()` into a dispatcher that checks `run.mode`:
  - `"single_prompt"` -> new `execute_single_prompt()` function: one request, one response, no version.
  - `"two_step_workflow"` -> existing logic extracted into `execute_two_step_workflow()`.
- `StockAnalysisRunCreate` schema gains `mode` field (default `"single_prompt"`).
- New `StockAnalysisRunCreate` fields: `instructions_text` and `input_text` for direct prompt content (used in single-prompt mode).

**Frontend changes:**
- Run form gains a mode toggle (single prompt vs. two-step workflow).
- Single-prompt mode shows the prompt editor; two-step mode shows the existing template selector.

**Preserve:**
- Entire existing two-step flow as `"two_step_workflow"` mode - zero behavioral change for existing runs.
- All existing run/request/response/version relationships.
- `partial_failure` semantics for two-step mode.

---

### GAP-2: No Snippet Entity

**Data model changes:**
- New table `user_snippets`: `id` (UUID PK), `name` (String 120, unique), `content` (Text), `description` (Text nullable), `created_at`, `updated_at`.
- No portfolio FK - snippets are global like LLM configs and templates.

**Backend service changes:**
- New `UserSnippetService` with CRUD (create, list, get, update, delete).
- New `UserSnippetRepository`.
- New schemas: `UserSnippetCreate`, `UserSnippetUpdate`, `UserSnippetRead`.
- New API router at `/api/v1/stock-analysis/snippets` with full CRUD.
- Wire into `dependencies.py`.

**Frontend changes:**
- New snippet management section on the stock-analysis inputs page (`/stock-analysis/inputs`).
- Snippet CRUD dialog (name, content, description).
- Snippet list with edit/delete.

**Preserve:**
- Existing inputs page layout - snippets become a third section alongside configs and templates.

---

### GAP-3: Limited Placeholder System -> Dynamic Entity References

**Data model changes:**
- None. The context snapshot (JSON column on `StockAnalysisRun`) already stores arbitrary dicts. Dynamic references just produce richer snapshots.

**Backend service changes:**
- New `PlaceholderDiscoveryService` that scans template text for `{{...}}` tokens and classifies them:
  - `stock.<ticker>` -> fetch quote/position data for that ticker
  - `position.<ticker>` -> fetch position for that ticker in the portfolio
  - `response.<uuid>` -> fetch `StockAnalysisResponse` by ID, include `output_text`
  - `snippet.<uuid>` -> fetch `UserSnippet` by ID, include `content`
  - Existing namespaces (`portfolio`, `run`, `userNote`, `quote`, `history`, `freshAnalysis`, `version:*`) -> unchanged
- Refactor `AnalysisContextService.build_context_snapshot()` to accept discovered references and fetch entities dynamically.
- `render_template()` stays the same - it already resolves `{{namespace.path}}` against a context dict. The change is in what gets put into the context dict.
- Update prompt preview to use the same discovery + dynamic fetch path.

**Frontend changes:**
- Placeholder insertion toolbar in the prompt editor (GAP-5) - shows available namespaces and lets users pick entities.
- Autocomplete for `{{stock.` (ticker search), `{{response.` (recent responses), `{{snippet.` (snippet list).

**Preserve:**
- Existing `render_template()` regex engine - it works fine.
- Existing snapshot namespaces - they become the "default" context, dynamic references add to them.
- Existing prompt preview endpoint contract - just richer context.

---

### GAP-4: No Async Status Tracking / Polling

**Data model changes:**
- None. `StockAnalysisRun.status` already has the right states (`queued`, `running`, `completed`, `partial_failure`, `failed`).

**Backend service changes:**
- Refactor `execute_run` API endpoint: instead of calling `execute_run_workflow()` synchronously, use FastAPI `BackgroundTasks` to enqueue execution. Return the run immediately with status `"running"`.
- The background task gets its own `Session` from the session factory (not the request-scoped session).
- Existing `GET /runs/{run_id}` endpoint used for polling (no new endpoint needed).

**Frontend changes:**
- `executeRunMutation` changes: after `POST .../execute` returns, start polling `GET .../runs/{runId}` every 2s until status is terminal.
- Use TanStack Query's `refetchInterval` on the run query, conditional on `status === "running"`.
- Show a progress indicator on the run card while polling.
- Toast on completion/failure.

**Preserve:**
- All existing run status semantics.
- The create-then-execute two-call pattern (create returns `queued`, execute transitions to `running` and returns immediately).

---

### GAP-5: No Prompt Composition UI

**Data model changes:**
- None.

**Backend service changes:**
- None beyond what GAP-1 and GAP-3 provide. The prompt preview endpoint already exists.

**Frontend changes:**
- New `PromptComposer` component with:
  - Mode selector (single prompt / two-step workflow).
  - Template selector dropdown that loads template content into the editor.
  - Two text areas: instructions and input (or single combined area for simple mode).
  - Placeholder insertion toolbar (powered by GAP-3 frontend work).
  - "Preview" button that calls the prompt preview endpoint and shows rendered output in a side panel.
  - "Execute" button that submits the composed prompt.
- Replace the current `ConversationRunForm` with `PromptComposer` (or wrap it - the existing form fields like run type, LLM config, review trigger, user note remain as metadata alongside the prompt editor).
- The existing form becomes a collapsible "metadata" section above the prompt editor.

**Preserve:**
- Existing run form metadata fields (run type, LLM config, review trigger, user note, compare to origin).
- Existing prompt preview API contract.

---

### GAP-6: Conversation Model - No Change Needed

Conversations stay per-symbol. Cross-symbol references are handled by GAP-3's dynamic placeholder resolution. See Addendum 6 for the full design rationale.

---

### GAP-7: Template Structure Mismatch

**Data model changes:**
- Add two new nullable columns to `PromptTemplate`: `instructions_template` (Text), `input_template` (Text).
- Add `template_mode` column: `"single"` | `"two_step"` (default `"two_step"`, CHECK constraint).
- Existing 4 columns (`fresh_instructions_template`, `fresh_input_template`, `compare_instructions_template`, `compare_input_template`) remain NOT NULL - single-mode templates store `""` as sentinel (see Addendum 5).
- SQLite upgrade to add columns.

**Backend service changes:**
- `PromptTemplateService` create/update validates: if `template_mode = "single"`, require `instructions_template` + `input_template`; if `"two_step"`, require the 4 existing fields.
- Schema changes: `PromptTemplateCreate`/`PromptTemplateUpdate` gain the new fields.
- `PromptTemplateRead` exposes all fields; frontend decides which to show based on `template_mode`.

**Frontend changes:**
- Template dialog gains a mode toggle.
- Single mode shows 2 fields; two-step mode shows 4 fields (existing behavior).
- Template list shows mode badge.

**Preserve:**
- All existing templates remain valid as `template_mode = "two_step"`.
- Revision increment logic unchanged.
- Archive-on-delete semantics unchanged.

---

### GAP-8: Gateway Schema Coupling

**Data model changes:**
- None.

**Backend service changes:**
- `LlmGatewayService._schema_for_step()` currently hard-fails on unknown steps. Refactor to:
  - Known steps (`fresh_analysis`, `compare_decide_reflect`) -> return existing schemas.
  - Step `"single"` or `"follow_up"` -> return `None` (no structured output enforcement).
- All provider adapters (`submit_request`, `build_request_payload`) accept `response_schema: dict | None`. When `None`, omit the JSON schema constraint from the provider call (plain text response).
- Each provider adapter needs a code path for schema-free requests:
  - OpenAI responses/chat: omit `response_format` parameter.
  - Anthropic: omit tool/JSON mode.
  - Gemini: omit `response_schema`.

**Frontend changes:**
- None directly. This is backend plumbing.

**Preserve:**
- Existing schema enforcement for two-step workflow steps.
- All provider adapter contracts - just add a `None` code path.

---

### GAP-9: Version Materialization Coupling - ELIMINATED

Per Addendum 2, single-prompt runs do NOT create versions. The `StockAnalysisVersion` table stays exactly as-is. No schema changes needed.

---

## SECTION 3: WAVE-BASED TASK GRAPH

### Wave 0: Foundation - Schema & Infrastructure (no feature changes, all tests pass)

| Task ID | Description | Gap(s) | Depends On | Category | Skills | Effort |
|---------|-------------|--------|------------|----------|--------|--------|
| W0-T1 | SQLite upgrade: add `mode` to `stock_analysis_runs`, widen `step` CHECK on `stock_analysis_requests` (table-recreate pattern), add columns to `prompt_templates` (`instructions_template`, `input_template`, `template_mode`) | GAP-1, GAP-7 | - | quick | - | S |
| W0-T2 | SQLite upgrade: add `user_snippets` table | GAP-2 | - | quick | - | S |
| W0-T3 | Update ORM models: `StockAnalysisRun.mode`, `StockAnalysisRequest.step` constraint, `PromptTemplate` new columns + `template_mode`, new `UserSnippet` model | GAP-1,2,7 | W0-T1, W0-T2 | quick | - | M |
| W0-T4 | Update Pydantic schemas: `StockAnalysisRunCreate.mode`, `StockAnalysisRunCreate.instructions_text/input_text`, `PromptTemplateCreate/Update/Read` new fields, `UserSnippetCreate/Update/Read` | GAP-1,2,7 | W0-T3 | quick | - | M |
| W0-T5 | Backend tests: write failing tests for new schema fields, new model constraints, new snippet CRUD, single-prompt run creation, template mode validation. All tests RED at this point except existing ones which must stay GREEN. | ALL | W0-T4 | quick | - | M |

**Commit strategy for Wave 0:**
1. `feat(db): add schema upgrades for flexible prompts and snippets` - W0-T1 + W0-T2
2. `feat(models): add mode/step/template/snippet ORM changes` - W0-T3
3. `feat(schemas): add pydantic schemas for flexible prompt system` - W0-T4
4. `test: add red tests for flexible prompt system` - W0-T5

---

### Wave 1: Backend Core Services (parallel tracks, no frontend yet)

| Task ID | Description | Gap(s) | Depends On | Category | Skills | Effort |
|---------|-------------|--------|------------|----------|--------|--------|
| W1-T1 | `UserSnippetService` + `UserSnippetRepository` + CRUD API router at `/api/v1/stock-analysis/snippets`. Wire into `dependencies.py`. Tests GREEN for snippet CRUD. | GAP-2 | W0-T5 | quick | - | M |
| W1-T2 | `PlaceholderDiscoveryService`: scan template text, classify references (`stock.<ticker>`, `position.<ticker>`, `response.<uuid>`, `snippet.<uuid>`, existing namespaces). Unit tests for discovery logic. | GAP-3 | W0-T5 | quick | - | M |
| W1-T3 | Refactor `AnalysisContextService.build_context_snapshot()` to accept discovered dynamic references and fetch entities. Integrate `PlaceholderDiscoveryService`. Update prompt preview to use new path. Existing placeholder tests stay GREEN, new dynamic reference tests go GREEN. | GAP-3 | W1-T2 | unspecified-high | - | L |
| W1-T4 | Refactor `PromptTemplateService` to validate `template_mode`. Single-mode templates require `instructions_template` + `input_template`; two-step requires existing 4 fields. Update create/update/read. Tests GREEN. | GAP-7 | W0-T5 | quick | - | M |
| W1-T5 | Refactor `LlmGatewayService._schema_for_step()` to return `None` for `"single"` and `"follow_up"` steps. Update all 4 provider adapters to handle `response_schema=None` (omit structured output). Tests GREEN for schema-free requests. | GAP-8 | W0-T5 | unspecified-high | - | M |
| W1-T6 | Refactor `execute_run` endpoint to use `BackgroundTasks`. Background task gets own session. Tests GREEN for async execution. | GAP-4 | W0-T5 | unspecified-high | - | M |

**Commit strategy for Wave 1:**
1. `feat(api): add user snippet CRUD service and endpoints` - W1-T1
2. `feat(context): add placeholder discovery service` - W1-T2
3. `feat(context): integrate dynamic entity references into context builder` - W1-T3
4. `feat(templates): support single-mode and two-step-mode templates` - W1-T4
5. `feat(gateway): support schema-free LLM requests for flexible prompts` - W1-T5
6. `feat(api): async run execution with background tasks` - W1-T6

---

### Wave 2: Backend Execution Paths (depends on Wave 1 core services)

| Task ID | Description | Gap(s) | Depends On | Category | Skills | Effort |
|---------|-------------|--------|------------|----------|--------|--------|
| W2-T1 | Implement `execute_single_prompt()` in executor: single request, single response, no version. Wire into `execute_run_workflow()` dispatcher based on `run.mode`. Tests GREEN for single-prompt execution. | GAP-1 | W1-T3, W1-T5, W1-T6 | unspecified-high | - | L |
| W2-T2 | Extract existing two-step logic into `execute_two_step_workflow()`. Ensure existing tests stay GREEN. The dispatcher calls this when `mode = "two_step_workflow"`. | GAP-1 | W1-T3, W1-T5, W1-T6 | quick | - | M |
| W2-T3 | Integration tests: full single-prompt lifecycle (create run -> execute async -> poll status -> verify response saved). Full two-step lifecycle still passes. Cross-mode tests. | GAP-1,4,8 | W2-T1, W2-T2 | quick | - | M |

**Commit strategy for Wave 2:**
1. `feat(executor): implement single-prompt execution path` - W2-T1
2. `refactor(executor): extract two-step workflow into dedicated function` - W2-T2
3. `test: integration tests for single-prompt and two-step lifecycle` - W2-T3

---

### Wave 3: Frontend Foundation (parallel with late Wave 2, no new UI yet)

| Task ID | Description | Gap(s) | Depends On | Category | Skills | Effort |
|---------|-------------|--------|------------|----------|--------|--------|
| W3-T1 | Update `api-types.ts` and `api.ts`: add snippet CRUD functions, add `mode` to run types, add `templateMode` to template types, add run status polling endpoint, add response summary endpoint. | ALL | W1-T1, W1-T4, W1-T6 | quick | - | M |
| W3-T2 | Update `query-keys.ts`: add `snippets`, `snippet` keys. Add polling-aware run query key. | GAP-2, GAP-4 | W3-T1 | quick | - | S |
| W3-T3 | Implement async run polling in `use-stock-analysis-mutations.ts`: after execute returns, poll run status every 2s using `refetchInterval` until terminal. Toast on completion/failure. | GAP-4 | W3-T1, W3-T2 | quick | - | M |
| W3-T4 | Frontend Vitest: add tests for new API types, query key structure, polling logic (mock timers). | GAP-2, GAP-4 | W3-T1, W3-T2, W3-T3 | quick | - | S |

**Commit strategy for Wave 3:**
1. `feat(frontend): update API types and client for flexible prompt system` - W3-T1 + W3-T2
2. `feat(frontend): implement async run polling` - W3-T3
3. `test(frontend): add unit tests for new API types and polling` - W3-T4

---

### Wave 4: Frontend UI - Snippet Management & Template Mode

| Task ID | Description | Gap(s) | Depends On | Category | Skills | Effort |
|---------|-------------|--------|------------|----------|--------|--------|
| W4-T1 | Snippet management UI on inputs page: snippet list, create/edit/delete dialog, content editor. Wire to snippet CRUD API. | GAP-2 | W3-T1, W3-T2 | visual-engineering | frontend-ui-ux | M |
| W4-T2 | Template dialog: add mode toggle (single / two-step). Single mode shows 2 fields, two-step mode shows 4 fields. Validation per mode. Template list shows mode badge. | GAP-7 | W3-T1 | visual-engineering | frontend-ui-ux | M |
| W4-T3 | Run history: show run `mode` badge, show progress indicator for `running` status during polling. | GAP-1, GAP-4 | W3-T3 | visual-engineering | frontend-ui-ux | S |

**Commit strategy for Wave 4:**
1. `feat(frontend): add snippet management UI to inputs page` - W4-T1
2. `feat(frontend): support single-mode and two-step-mode templates in dialog` - W4-T2
3. `feat(frontend): show run mode badge and polling progress indicator` - W4-T3

---

### Wave 5: Frontend UI - Prompt Composer (the big one)

| Task ID | Description | Gap(s) | Depends On | Category | Skills | Effort |
|---------|-------------|--------|------------|----------|--------|--------|
| W5-T1 | `PromptComposer` component shell: mode selector (single / two-step), template selector dropdown that loads content into editor, instructions + input text areas, metadata section (run type, LLM config, review trigger, user note, compare to origin). | GAP-1, GAP-5 | W4-T2, W4-T3 | visual-engineering | frontend-ui-ux | L |
| W5-T2 | Placeholder insertion toolbar with entity pickers: ResponsePicker (popover, conversation-scoped), SnippetPicker (popover, global), StockPicker (combobox with portfolio symbols + free-text), PositionPicker (portfolio symbols only). Inserts `{{namespace.<entity>}}` at cursor position. | GAP-3, GAP-5 | W4-T1, W3-T1 | visual-engineering | frontend-ui-ux | L |
| W5-T3 | Prompt preview panel: "Preview" button calls prompt preview endpoint, shows rendered instructions + input in a read-only side panel, shows placeholder resolution results and any warnings/errors. | GAP-5 | W5-T1, W5-T2 | visual-engineering | frontend-ui-ux | M |
| W5-T4 | Wire `PromptComposer` into `conversation-detail-card.tsx`: replace current `ConversationRunForm` with `PromptComposer`. Single-prompt mode sends `instructions_text` + `input_text` directly; two-step mode sends `promptTemplateId` + optional overrides (existing behavior). Both modes go through async execute + polling. | GAP-1, GAP-5 | W5-T1, W5-T2, W5-T3, W3-T3 | visual-engineering | frontend-ui-ux | M |
| W5-T5 | Template-to-editor loading: when user selects a template in the composer, populate the text areas with the template's content (single-mode: `instructionsTemplate` + `inputTemplate`; two-step: the 4 fields). User can then edit freely before submitting. "Reset to template" button restores original. | GAP-5, GAP-7 | W5-T1 | visual-engineering | frontend-ui-ux | S |
| W5-T6 | Backend: add `GET /responses` summary endpoint + `StockAnalysisResponseSummary` schema + service method + repository query (supports ResponsePicker). | GAP-4 | W1-T1 | quick | - | S |

**Commit strategy for Wave 5:**
1. `feat(frontend): add PromptComposer component shell with mode selector` - W5-T1
2. `feat(frontend): add placeholder insertion toolbar with entity pickers` - W5-T2
3. `feat(frontend): add prompt preview panel to composer` - W5-T3
4. `feat(frontend): wire PromptComposer into conversation detail, replace run form` - W5-T4
5. `feat(frontend): template-to-editor loading with reset capability` - W5-T5
6. `feat(api): add response summary endpoint for picker` - W5-T6

---

### Wave 6: Integration, E2E & Cleanup

| Task ID | Description | Gap(s) | Depends On | Category | Skills | Effort |
|---------|-------------|--------|------------|----------|--------|--------|
| W6-T1 | Backend integration tests: full lifecycle - create snippet -> create single-mode template referencing snippet -> create conversation -> compose prompt with `{{snippet.<id>}}` + `{{stock.MSFT}}` -> execute single-prompt async -> poll -> verify response saved, context snapshot contains resolved dynamic references. | ALL | W2-T3, W1-T1 | quick | - | M |
| W6-T2 | Backend integration tests: two-step workflow still works identically - existing `test_stock_analysis.py` tests pass without modification. Run full existing test suite, fix any regressions. | ALL | W2-T3 | quick | - | M |
| W6-T3 | Backend integration tests: edge cases - single-prompt with unstructured response (no version created, response saved as raw text), snippet referenced but deleted (graceful error), response reference to non-existent ID (validation error), async execution failure (run marked failed). | GAP-1,2,3,4 | W6-T1 | quick | - | M |
| W6-T4 | Frontend Vitest: PromptComposer unit tests - mode toggle, template loading, placeholder insertion at cursor, preview call, form submission shape for both modes. | GAP-1,5 | W5-T4 | quick | - | M |
| W6-T5 | Playwright E2E: navigate to stock-analysis workspace -> create conversation -> open prompt composer -> select single-prompt mode -> type prompt with placeholder -> preview -> execute -> verify polling shows completion -> verify run appears in history. | ALL | W5-T4, W6-T2 | unspecified-high | - | L |
| W6-T6 | Update all AGENTS.md files: root, backend, backend/services, backend/services/stock_analysis, backend/models, backend/schemas, backend/api, frontend, frontend/src/lib, frontend/src/components/portfolios, frontend/src/components/portfolios/stock-analysis-workspace. Reflect new entities, modes, async execution, and placeholder system. | ALL | W6-T5 | quick | - | M |
| W6-T7 | Update `docs/`: spec.md, api-design.md, data-model.md, requirements.md to reflect the new flexible prompt system, snippets, async execution. | ALL | W6-T5 | quick | - | S |

**Commit strategy for Wave 6:**
1. `test(backend): integration tests for single-prompt lifecycle with dynamic references` - W6-T1
2. `test(backend): verify two-step workflow backward compatibility` - W6-T2
3. `test(backend): edge case tests for flexible prompt system` - W6-T3
4. `test(frontend): PromptComposer unit tests` - W6-T4
5. `test(e2e): Playwright test for single-prompt workflow` - W6-T5
6. `docs: update AGENTS.md files for flexible prompt system` - W6-T6
7. `docs: update spec, api-design, data-model, requirements` - W6-T7

---

## SECTION 4: RISK ASSESSMENT

### Risk 1: Existing Test Breakage from Schema Changes
**Probability**: High
**Impact**: High
**Mitigation**: Wave 0 schema changes must be strictly additive - new columns with defaults, relaxed constraints (NOT NULL -> nullable), widened CHECK constraints. Never remove or rename existing columns. The SQLite upgrade function must handle the "table already has the new columns" case idempotently. Run the full existing test suite after every Wave 0 commit. The W0-T5 red tests must be in separate test functions, not modifications of existing ones.

### Risk 2: Async Execution Session Management
**Probability**: Medium
**Impact**: High
**Mitigation**: The background task must create its own `Session` from `get_session_factory()()` and close it in a `try/finally`. It must NOT share the request-scoped session (which closes when the HTTP response is sent). The background task must handle its own `commit()/rollback()` and catch all exceptions to ensure the run is marked `failed` even on unexpected errors. Test this with a fake gateway that raises mid-execution.

### Risk 3: Placeholder Syntax Ambiguity
**Probability**: Medium
**Impact**: Medium
**Mitigation**: Disambiguation happens by namespace (see Addendum 1). `stock`, `position` -> identifier is a ticker. `response`, `snippet` -> identifier is a UUID. `portfolio`, `run`, `userNote`, `quote`, `history`, `freshAnalysis`, `version:*` -> existing field-path behavior. Document the namespace registry in `context.py` with a comment block.

### Risk 4: Provider Adapter Schema-Free Path Untested
**Probability**: Medium
**Impact**: Medium
**Mitigation**: Each of the 4 provider adapters (OpenAI chat, OpenAI responses, Anthropic, Gemini) needs a `response_schema=None` code path. W1-T5 must include per-provider unit tests with mocked SDK calls for both schema and schema-free paths.

### Risk 5: Frontend Prompt Composer Complexity
**Probability**: Medium
**Impact**: Low (UX degradation, not data loss)
**Mitigation**: Build incrementally. W5-T1 is the shell with plain text areas - this alone is a usable MVP. W5-T2 (placeholder toolbar) and W5-T3 (preview panel) are additive enhancements. If the toolbar proves too complex, users can still type `{{stock.AAPL}}` manually - the backend resolves it regardless. Ship the shell first, iterate on the toolbar.

---

## SECTION 5: KEY DESIGN DECISIONS

### Decision 1: Placeholder Namespace Registry - Static Registry
Hardcode known namespaces in `PlaceholderDiscoveryService`, each with a resolver function. There are only ~13 namespaces. A plugin system adds abstraction without value at this scale. The registry is a dict in `context.py` mapping namespace strings to resolver callables. Adding a namespace is a 5-line change.

### Decision 2: Async Execution - FastAPI BackgroundTasks
The app is single-user, SQLite-backed, no horizontal scaling requirement. BackgroundTasks is the simplest path that unblocks the frontend. The background task gets its own session, commits/rollbacks independently, and marks the run terminal on any exception. If scaling needs arise later, the execution function is already decoupled from the HTTP handler and can be moved to a task queue with minimal changes.

### Decision 3: Template Model - Extend Existing Table
Extend existing `PromptTemplate` table with new columns + `template_mode` discriminator. Single table, two modes. This preserves all existing FK references from runs, settings, and the frontend. The cost is 3 new nullable columns - acceptable.

### Decision 4: Single-Prompt Version Semantics - Non-Versioned
Single-prompt runs do NOT create versions. Responses are always saved in `StockAnalysisResponse`. The version timeline shows only two-step workflow results. This keeps the version concept clean and meaningful. See Addendum 2.

### Decision 5: Backward Compatibility - Additive Migration with Backfill
The schema changes are additive (new columns with defaults). Existing runs get `mode = "two_step_workflow"` via column default. Existing templates get `template_mode = "two_step"` via column default. The executor dispatcher routes based on `mode`, so old runs continue to use the old execution path with zero behavioral change. No feature flags needed.

---

## ADDENDUM 1: Placeholder Contract Specification

**Canonical syntax**: `{{namespace.identifier}}`

**Namespace registry** (exhaustive - no other namespaces are valid):

| Namespace | Identifier Type | Example | Resolution | Scope |
|-----------|----------------|---------|------------|-------|
| `portfolio` | field path | `{{portfolio.name}}` | Current portfolio snapshot field | Current portfolio |
| `stock` | TICKER | `{{stock.AAPL}}` | Fetch quote data for any ticker | Global |
| `position` | TICKER | `{{position.AAPL}}` | Fetch position data for ticker | Current portfolio |
| `quote` | field path | `{{quote.summary}}` | Conversation symbol's quote (legacy) | Current portfolio |
| `history` | field path | `{{history.priceSummary}}` | Conversation symbol's history (legacy) | Current portfolio |
| `run` | field path | `{{run.runType}}` | Current run metadata | Current run |
| `userNote` | field path | `{{userNote.text}}` | Current run's user note | Current run |
| `response` | UUID | `{{response.a1b2c3...}}` | Previous response's `output_text` | Current portfolio |
| `snippet` | UUID | `{{snippet.d4e5f6...}}` | User snippet's `content` | Global |
| `freshAnalysis` | field path | `{{freshAnalysis.thesis}}` | Step-1 parsed output (two-step only) | Current run |
| `version:latest` | field path | `{{version:latest.action}}` | Latest version in conversation | Current conversation |
| `version:origin` | field path | `{{version:origin.action}}` | First version in conversation | Current conversation |

**Case normalization rules:**
- Tickers in `stock` and `position`: uppercased by `PlaceholderDiscoveryService` before resolution (uses existing `normalize_symbol()`).
- UUIDs in `response` and `snippet`: lowercased, validated as UUID format before fetch. Invalid format -> validation error, not silent failure.
- Field paths: case-sensitive, must match the camelCase keys in the context dict exactly.
- Namespace names: case-sensitive, must match the table above exactly.

**Cross-portfolio constraints:**
- `position.<TICKER>` resolves only within the current portfolio. If the portfolio has no position in that ticker, resolves to a zero-quantity stub (same as current behavior for the conversation symbol).
- `response.<UUID>` resolves only within the current portfolio. The response must belong to a request -> run -> conversation chain where `conversation.portfolio_id` matches. Violation -> validation error `"Response does not belong to this portfolio"`.
- `snippet.<UUID>` and `stock.<TICKER>` are global - no portfolio constraint.

**Nested resolution: PROHIBITED.** Snippet content is inserted as literal text. If a snippet's `content` field contains `{{...}}` tokens, they appear verbatim in the rendered prompt. The resolver makes exactly one pass. This is enforced by design - `render_template()` is called once, and snippet content is injected as a pre-resolved string value, not as template text.

**Unknown namespace or unresolvable identifier:** Raises `validation_error` with field-level detail. The placeholder is NOT silently left in the output. This matches current behavior (`context.py:229-230`).

**Escaping:** `\\{{` and `\\}}` produce literal braces. Already implemented (`context.py:237`).

---

## ADDENDUM 2: Single-Prompt Version Semantics

**Decision: Single-prompt runs do NOT create versions. Ever.**

Rationale: Versions are the structured, comparable artifacts of the self-reflection workflow. They require `fresh_analysis`, `comparison`, `decision`, and `reflection` - all four sections - to be meaningful for the version timeline, scoring, and action tracking. A single-prompt response has none of this structure guaranteed.

**What happens to single-prompt responses:**
- The response is always saved in `StockAnalysisResponse` with `output_text`, `raw_response`, token counts, and `parse_status = "pending"`.
- No parsing is attempted. `parse_status` stays `"pending"` (we don't know what schema to parse against - the user wrote a free-form prompt).
- The response is visible in run history via `GET /runs/{runId}` -> `requests[0].response.outputText`.
- The run completes with `status = "completed"` (success) or `status = "failed"` (provider error).
- There is no `partial_failure` for single-prompt runs - it either works or it doesn't.

**Consequence: GAP-9 is eliminated.** No schema changes to `StockAnalysisVersion`. No `version_type` column. No nullable `comparison`/`decision`/`reflection`. The version table stays exactly as-is.

**`StockAnalysisVersion` - no changes from current schema:**

```text
conversation_id, run_id, version_number, symbol, action,
confidence_score, fresh_analysis, comparison, decision, reflection, created_at
```

All columns remain NOT NULL (except `confidence_score` which is already nullable).

---

## ADDENDUM 3: Async Execution API Contract

**Endpoint behavior:**

```text
POST /api/v1/portfolios/{portfolioId}/stock-analysis/conversations/{conversationId}/runs
  -> Creates run with status "queued". Returns StockAnalysisRunRead. No execution.

POST /api/v1/portfolios/{portfolioId}/stock-analysis/runs/{runId}/execute
  -> Precondition: run.status == "queued". If not -> 409 {"code": "run_not_queued"}.
  -> Transitions run to status "running", commits.
  -> Enqueues execution via FastAPI BackgroundTasks.
  -> Returns StockAnalysisRunRead with status "running" IMMEDIATELY.
  -> Background task runs with its own Session.

GET /api/v1/portfolios/{portfolioId}/stock-analysis/runs/{runId}
  -> Returns current StockAnalysisRunRead (already exists). Used for polling.
```

**Background task contract:**

```python
def _execute_run_background(run_id: UUID, portfolio_id: UUID) -> None:
    session = get_session_factory()()          # own session, NOT request-scoped
    try:
        service = build_stock_analysis_service(session)
        service.execute_run_internal(portfolio_id, run_id)
    except Exception:
        logger.exception("Background run %s failed", run_id)
        _mark_run_failed(session, run_id)
    finally:
        session.close()
```

**Duplicate execute prevention:**
1. The execute endpoint checks `run.status == "queued"` inside a transaction. If not queued, returns 409. This is the primary guard.
2. The background task re-checks `run.status == "running"` at the start. If the status is not `"running"`, it exits silently.
3. There is no optimistic locking or row-level lock - SQLite serializes writes, and the status check + transition is atomic within a single `commit()`.

**Frontend polling contract:**

```typescript
// In use-stock-analysis-mutations.ts, after execute returns:
const { data: run } = useQuery({
  queryKey: queryKeys.stockAnalysisRun(portfolioId, runId),
  queryFn: () => api.getStockAnalysisRun(portfolioId, runId),
  refetchInterval: (query) => {
    const status = query.state.data?.status
    if (status === "running" || status === "queued") return 2000
    return false  // stop polling
  },
  enabled: !!runId,
})
```

**Terminal states** (polling stops): `completed`, `partial_failure`, `failed`.
**Non-terminal states** (polling continues): `queued`, `running`.

**Timeout:** No server-side timeout. If a provider call hangs, the background task hangs. The frontend shows "running" indefinitely. Future enhancement: add a `started_at` timestamp and a reaper that marks stale runs as `failed` after 5 minutes. Out of scope for this plan.

---

## ADDENDUM 4: Response Picker & Snippet Picker API + UX

**New API endpoint for response browsing:**

```text
GET /api/v1/portfolios/{portfolioId}/stock-analysis/responses
  Query params:
    conversationId (optional) - filter to a specific conversation
    limit (optional, default 20, max 50)
  Returns: list of StockAnalysisResponseSummary
```

**`StockAnalysisResponseSummary` schema:**

```python
class StockAnalysisResponseSummary(CamelModel):
    id: UUID
    request_id: UUID
    run_id: UUID
    conversation_id: UUID
    symbol: str                    # from conversation
    step: str                      # from request
    output_text_preview: str       # first 200 chars of output_text, or "" if null
    created_at: datetime
```

**Backend implementation:** New `list_responses_for_portfolio()` method on `StockAnalysisService`. Joins `responses -> requests -> runs -> conversations` filtered by `portfolio_id`. Orders by `response.created_at DESC`. The `output_text_preview` is computed in the mapper (truncate to 200 chars + "...").

**Snippet list endpoint** (already planned in W1-T1):

```text
GET /api/v1/stock-analysis/snippets
  Returns: list of UserSnippetRead (id, name, content, description, createdAt, updatedAt)
```

**Frontend picker components:**

**ResponsePicker** (popover triggered from placeholder toolbar):
- Fetches `GET .../responses?conversationId={current}` for conversation-scoped responses, or without filter for all portfolio responses.
- Shows a scrollable list: each row shows `symbol · step · preview · date`.
- Clicking a row inserts `{{response.<id>}}` at the cursor position in the active text area.
- Search/filter input at the top filters by symbol or preview text (client-side).

**SnippetPicker** (popover triggered from placeholder toolbar):
- Fetches `GET /stock-analysis/snippets`.
- Shows a scrollable list: each row shows `name · description`.
- Clicking a row inserts `{{snippet.<id>}}` at the cursor position.
- Search/filter input filters by name (client-side).

**StockPicker** (combobox triggered from placeholder toolbar):
- Populated from `usePortfolioWorkspace().dashboard.assetRows` (portfolio symbols) plus a free-text input for arbitrary tickers.
- Selecting inserts `{{stock.<TICKER>}}`.
- A toggle switches between "stock reference" (`{{stock.X}}`) and "position reference" (`{{position.X}}`). Position picker only shows portfolio symbols (no free-text).

**Cursor insertion mechanism:** Each text area in the PromptComposer tracks cursor position via `onSelect` / `selectionStart`. Picker insertion calls a shared `insertAtCursor(textareaRef, text)` utility that splices the placeholder at the cursor position and updates React state.

---

## ADDENDUM 5: Migration Plan - Concrete Defaults & Backfills

**Principle:** All schema changes are additive. New columns have defaults. Existing data is valid without manual backfill. `Base.metadata.create_all()` handles new databases. `upgrade_sqlite_stock_analysis()` handles existing databases.

**`stock_analysis_runs` - add `mode` column:**

```python
# In upgrade_sqlite_stock_analysis():
if "stock_analysis_runs" in table_names:
    run_columns = {c["name"] for c in inspector.get_columns("stock_analysis_runs")}
    if "mode" not in run_columns:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE stock_analysis_runs "
                "ADD COLUMN mode VARCHAR(32) NOT NULL DEFAULT 'two_step_workflow'"
            )
```

- Default `'two_step_workflow'` means all existing runs are automatically classified correctly.
- New single-prompt runs will be created with `mode='single_prompt'` by the service layer.
- No data migration needed.

**`prompt_templates` - add `template_mode`, `instructions_template`, `input_template`:**

```python
if "prompt_templates" in table_names:
    tmpl_columns = {c["name"] for c in inspector.get_columns("prompt_templates")}
    if "template_mode" not in tmpl_columns:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE prompt_templates "
                "ADD COLUMN template_mode VARCHAR(20) NOT NULL DEFAULT 'two_step'"
            )
            conn.exec_driver_sql(
                "ALTER TABLE prompt_templates "
                "ADD COLUMN instructions_template TEXT"
            )
            conn.exec_driver_sql(
                "ALTER TABLE prompt_templates "
                "ADD COLUMN input_template TEXT"
            )
```

- Default `'two_step'` means all existing templates are classified correctly.
- `instructions_template` and `input_template` are NULL for existing templates - correct because two-step templates use the 4 existing fields.
- The existing 4 fields remain NOT NULL. For new single-mode templates, the service layer sets them to empty string `""` (they're unused but the column constraint requires a value).

**`stock_analysis_requests` - widen `step` CHECK constraint:**

SQLite cannot ALTER CHECK constraints. Use the table-recreate pattern (proven in `upgrade_sqlite_trading_operations`):

```python
if "stock_analysis_requests" in table_names:
    table_sql = _get_sqlite_table_sql(engine, "stock_analysis_requests")
    if "'single'" not in table_sql.lower():
        # Recreate table with widened CHECK:
        # step IN ('fresh_analysis', 'compare_decide_reflect', 'follow_up', 'single')
        _recreate_stock_analysis_requests_table(engine)
```

The recreate function follows the same `PRAGMA foreign_keys=OFF -> rename -> create -> INSERT INTO ... SELECT -> DROP legacy -> recreate indexes -> PRAGMA foreign_keys=ON` pattern.

**`user_snippets` - new table:**

No migration needed - `Base.metadata.create_all()` creates missing tables automatically.

**`stock_analysis_versions` - NO CHANGES** (per Addendum 2).

**Tolerant reads:** All Pydantic read schemas use `Optional` / default values for new fields:
- `StockAnalysisRunRead.mode: str = "two_step_workflow"`
- `PromptTemplateRead.template_mode: str = "two_step"`
- `PromptTemplateRead.instructions_template: str | None = None`
- `PromptTemplateRead.input_template: str | None = None`

---

## ADDENDUM 6: Conversations Are Single-Symbol by Design

**Decision: YES. Conversations remain single-symbol. This is a deliberate, permanent design choice.**

A `StockAnalysisConversation` represents an ongoing analysis thread for one stock within one portfolio. The `symbol` column is NOT NULL, and the unique constraint on `(portfolio_id, symbol, is_archived=false)` ensures one active conversation per stock per portfolio.

**What "single-symbol" means in practice:**

- The conversation's `symbol` is the **primary analysis subject**. It determines which position, quote, and history data populate the default `{{position.*}}`, `{{quote.*}}`, and `{{history.*}}` placeholders.
- The version timeline for a conversation tracks the evolving thesis on that one stock.
- Run history within a conversation is the chronological record of analysis for that stock.

**Cross-symbol references are auxiliary data, not identity:**

- `{{stock.MSFT}}` in a conversation about AAPL fetches MSFT quote data as supplementary context (e.g., for competitive comparison). It does NOT make the conversation about MSFT.
- `{{position.MSFT}}` fetches the portfolio's MSFT position data. Same - auxiliary context.
- These auxiliary references are recorded in the `context_snapshot` and `placeholder_snapshot` for audit, but they don't affect conversation identity, version numbering, or timeline filtering.

**Frontend implications:**
- Conversation list filters by symbol - unchanged.
- Creating a conversation requires a symbol - unchanged.
- The prompt composer can reference any ticker via the stock/position pickers - new capability, no model change.
- The version timeline shows versions for the conversation's symbol - unchanged.
