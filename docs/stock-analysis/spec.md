# Stock Analysis Technical Specification

## Overview

This specification defines a stock-analysis feature for Ledger that follows the self-reflection loop in `docs/playbook/self_reflection_stock_analysis_loop.md`. The application supports OpenAI, Anthropic, and Gemini, keeps credentials server-side, and stores local history as the source of truth. OpenAI support includes both `chat/completions` and `responses`.

The feature is stock-scoped, not portfolio-wide. Each analysis conversation belongs to exactly one portfolio and one symbol.

## Architecture

### Frontend

- Reuse the existing portfolio analysis route in `frontend/src/components/portfolios/portfolio-analysis-page.tsx`.
- Add a stock-analysis workspace to that route instead of creating a disconnected feature shell.
- Keep API contracts in `frontend/src/lib/api.ts` and query keys in `frontend/src/lib/query-keys.ts`.
- Keep portfolio-specific form types in `frontend/src/components/portfolios/model.ts`.

### Backend

- Add thin FastAPI routers under `backend/app/api/`.
- Keep orchestration in services under `backend/app/services/`.
- Add repositories under `backend/app/repositories/` and SQLAlchemy models under `backend/app/models/`.
- Add Pydantic contracts under `backend/app/schemas/`.
- Extend `backend/app/api/dependencies.py` for new services and the LLM provider client boundary.

### Provider Boundary

- Use app-owned `LlmConfig` records with `provider in {openai, anthropic, gemini}`.
- Support OpenAI configs with `endpointMode in {chat_completions, responses}`.
- Support Anthropic via the Messages API and Gemini via `generateContent`.
- Render templates into a provider-neutral `instructions` plus `input` pair, then transform those values into provider-specific payloads at execution time.
- Use provider-native structured JSON controls where available and enforce the same final JSON contract with local parser validation for every provider.
- Keep canonical review requests self-contained. Use provider-native continuation identifiers only for optional `manual_follow_up` continuation, not for review-bearing runs. In MVP, only OpenAI Responses uses `previous_response_id`.
- Do not rely on provider-side conversation, thread, or history objects in MVP. The app keeps its own conversation model in the database.
- Treat remote response storage or retrieval as optional debugging support, never as the source of truth.

### Common Provider Abstraction

- OpenAI Chat Completions maps rendered prompts into `messages` with structured response-format configuration.
- OpenAI Responses maps rendered prompts into `instructions` plus `input`, with optional `previous_response_id` for allowed follow-up continuation.
- Anthropic maps rendered prompts into top-level `system` plus `messages`.
- Gemini maps rendered prompts into `contents` plus generation config for structured JSON output.
- The product abstraction remains the same across providers: one selected LLM config per run, one canonical rendered prompt snapshot, one normalized response model, and one local audit trail.

## Explicit Scope Boundaries

- This feature is stock-only, not portfolio-analysis mode plus stock-analysis mode.
- This feature supports multiple providers, but each run uses one selected LLM config at a time.
- This feature uses no provider fan-out and no provider concurrency planning in MVP.
- This feature does not rely on provider-side conversation or thread objects; app-owned conversations remain the product abstraction.

## Core Design Decisions

### 1. App-Level Conversations Are Authoritative

The application must persist its own conversations, runs, requests, responses, and versions because:

- Provider-side retention is not the same as product history requirements.
- Placeholder resolution must work against app-owned records.
- The user needs stable history even after provider-side retention windows change.

### Source Of Truth Rules

- Local database records are the source of truth for UI rendering, placeholder resolution, historical replay, and audits.
- Provider response records are auxiliary debugging artifacts linked by `provider` plus `providerResponseId` when available.
- If provider state expires or becomes unreachable, the feature must continue to work from local request, response, and version snapshots.

### 2. Review Runs Are Two-Step By Default

To respect "analyze first, compare later," each review-bearing run executes two provider requests through the selected LLM config:

1. `fresh_analysis`
2. `compare_decide_reflect`

The first step receives current stock context only. It must not receive prior thesis text by default. The second step is built from local persisted data, not provider-side chained memory. It may reference:

- the parsed result from step one
- the latest prior version summary
- the original version summary, when configured
- the user note and trigger metadata

### 3. Prompt Configuration Is Frontend-Driven But Server-Validated

The frontend can:

- select a saved template
- edit a run-time draft
- preview rendered instructions and input

The backend remains responsible for:

- placeholder validation
- prompt rendering
- request snapshot persistence
- request payload assembly

### 4. Structured Outputs Are Mandatory

Free-form text alone is insufficient for versioning and comparisons. The backend requires schema-valid JSON for successful parsing. Raw text is still persisted for debugging, but the run is only marked `parsed_success` when the JSON contract validates.

## Functional Workflow

### Phase 0. Preconditions

- Portfolio stock analysis is enabled for the active portfolio.
- The selected symbol exists in the portfolio or is otherwise explicitly allowed for analysis.
- A prompt template or ad hoc draft is present.
- The selected LLM config is enabled and has valid server-side credentials.

### Phase 1. Conversation Selection Or Creation

- The user picks a symbol in the portfolio analysis UI.
- The app loads or creates a conversation for `(portfolioId, symbol)`.
- The timeline view shows prior runs and version snapshots for that conversation.

### Phase 2. Context Snapshot Build

Before any provider call, the backend creates a request-time snapshot that includes:

- portfolio metadata
- stock symbol and position summary
- current delayed quote and recent price history
- trade history summary from simulated operations
- latest prior version summary and origin version summary, if applicable
- run trigger, run type, and user note

The snapshot is immutable once saved.

### Phase 3. Prompt Preview

The preview endpoint resolves placeholders without calling any provider. It returns:

- rendered `instructions`
- rendered `input`
- placeholder value map
- referenced record metadata
- validation errors and warnings

Execution is blocked when preview validation would fail.

### Phase 4. Fresh Analysis Request

The backend persists a request record before calling the selected provider.

The `fresh_analysis` step uses:

- step-specific instructions template
- step-specific input template
- the current context snapshot
- provider-specific request assembly derived from the selected LLM config
- no prior thesis text unless the template explicitly references it and the run type allows it

The output schema returns:

- business summary
- current context
- thesis
- bear case
- key assumptions
- valuation view
- risk assessment
- confidence
- scorecard
- provisional stance

### Phase 5. Compare, Decide, Reflect Request

After step one succeeds, the backend issues a second self-contained provider request.

The second request receives:

- the parsed fresh-analysis output
- prior version summaries chosen by the backend
- run metadata and thresholds

The compare-step prompt may reference that current-run payload through the `freshAnalysis.*` placeholder namespace defined in `docs/stock-analysis/prompt-template-spec.md`.

It does not depend on provider-side conversation objects or continuation identifiers in the canonical review flow.

The output schema returns:

- change items with classifications
- thesis delta vs last and optional vs origin
- risk, fair-value, and confidence changes
- final action memo
- reversal conditions
- reflection notes

### Phase 6. Version Materialization

If the run type is review-bearing and the final structured response validates, the backend creates a version snapshot record. That version is queryable without reparsing old raw payloads.

### Phase 7. Timeline Rendering

The frontend renders:

- run status and metadata
- request/response snapshots
- parse success or failure
- final structured panels
- version deltas

## Run Types

- `initial_review`: first formal thesis for the symbol
- `periodic_review`: scheduled or routine follow-up
- `event_review`: triggered by a notable event or price move
- `manual_follow_up`: ad hoc user question inside the conversation; may skip version materialization unless promoted by the user later

## Structured Response Contract

The final assembled review model must separate the following sections:

- `freshAnalysis`
- `comparison`
- `decision`
- `reflection`

### `freshAnalysis`

- `businessSummary`
- `currentContext`
- `thesis`
- `bearCase`
- `keyAssumptions[]`
- `valuation`
- `riskAssessment`
- `confidence`
- `scorecard`
- `provisionalAction`

### `comparison`

- `deltaVsLast`
- `deltaVsOrigin`
- `changeItems[]`
- `thesisChange`
- `fairValueChange`
- `riskChange`
- `confidenceChange`

Each `changeItem` must use one of:

- `new_fact`
- `changed_interpretation`
- `corrected_mistake`
- `noise`
- `thesis_strengthening`
- `thesis_weakening`
- `thesis_breaking`

### `decision`

- `action`
- `actionLevel`
- `reason`
- `reversalConditions[]`
- `shouldTradeNow`

Allowed actions:

- `buy`
- `add`
- `hold`
- `trim`
- `sell`
- `avoid`
- `watch`
- `no_action`

### `reflection`

- `whatGotRight`
- `whatWasMissed`
- `possibleBiases`
- `blankPageCheck`
- `nextReviewWatchpoints[]`

## Placeholder And Prompt Behavior

- Placeholder grammar and namespaces are defined in `docs/stock-analysis/prompt-template-spec.md`.
- Rendering is single-pass only.
- Missing or unauthorized references fail preview and execution.
- Historical runs persist the exact rendered prompt and resolved placeholder map.

## Frontend Specification

### Stock Analysis Workspace

- Add a dedicated LLM-review launch surface to `portfolio-analysis-page.tsx` as the authoritative stock-analysis workspace for MVP.
- Let the user choose a symbol, template, LLM config, run type, and optional note.
- Show preview before submit.

### LLM Config Manager

- Provide CRUD and enable/disable flows for OpenAI, Anthropic, and Gemini configs.
- Show provider, model, endpoint mode, base URL override, and masked secret state.
- Expose OpenAI endpoint-mode selection only when provider is `openai`.

### Prompt Template Manager

- Provide template CRUD and archive flows.
- Provide separate editing surfaces for the two default steps.
- Show placeholder reference help.

### Timeline And Viewer

- Show conversations filtered by symbol.
- Show run rows with status badges.
- Expand into request, response, and version details.
- Keep parse failures visible instead of dropping them silently.

## Backend Specification

### New Modules

- `stock_analysis` router/service/repositories/models/schemas
- `llm_configs` router/service/repositories/models/schemas
- `prompt_templates` router/service/repositories/models/schemas
- `analysis_context_service`
- `llm_gateway_service`
- provider adapters for OpenAI Chat Completions, OpenAI Responses, Anthropic Messages, and Gemini generateContent

### Provider Request Rules

- Use provider-specific model ids from server-defined allowlists.
- Keep API key and base URL server-side only.
- OpenAI configs must declare an endpoint mode and the gateway must route to the matching adapter.
- OpenAI Chat Completions requests must carry the structured-output schema using the chat endpoint's response-format controls.
- OpenAI Responses requests must carry the structured-output schema using the responses endpoint's structured text-format controls.
- Anthropic requests must use the provider's supported structured-output mechanism when available, otherwise the same strict JSON contract must still be enforced by local parser validation.
- Gemini requests must attach structured JSON generation config for the final response contract.
- Store outbound payload snapshots without secrets.
- Persist canonical rendered prompts plus provider-specific payload snapshots.
- Persist provider-issued response identifiers and usage fields when present, plus raw payload and parsed payload.
- Optionally retrieve remote request or response artifacts only for providers or endpoints that support it, but never require that for normal UI rendering.

## Failure Handling

### Preview Failures

- Invalid placeholder
- Missing referenced record
- Cross-portfolio reference
- Template/step mismatch

Preview failures return validation errors and stop execution.

### Provider Failures

- provider HTTP error
- timeout
- malformed response
- missing required structured fields

Provider failures persist failed request and response metadata so the timeline remains truthful.

### Partial Success

If step one succeeds and step two fails:

- keep both request records
- keep step-one parsed output
- mark the run `partial_failure`
- do not materialize a new version

## Persistence Rules

- Conversations are app-level and local.
- Runs, requests, responses, context snapshots, prompt snapshots, and versions are immutable after creation except for status and parse metadata transitions during execution.
- Versions are never edited in place.
- Template edits must not mutate historical request snapshots.
- Archived templates remain readable through historical snapshots but are unavailable for new runs.

### Lifecycle Matrix

| Event | Local behavior | Provider behavior | Notes |
|---|---|---|---|
| create run | create conversation if needed, persist run and context snapshot first | none yet | local first |
| submit review step | persist request record before outbound call | create one provider request using selected config | request snapshot excludes secrets |
| continue follow-up | create new request in same conversation | may use provider-native continuation only when supported | OpenAI Responses only in MVP |
| retry failed review | create a new run and new request rows | create new remote ids when the provider returns them | do not mutate failed history |
| replay old run | render from local snapshots only | optional retrieval for debug when supported | replay is read-only |
| archive conversation | hide from default new-run lists, keep history | none | no destructive delete in MVP |
| template archive | keep historical references valid | none | archive instead of delete once used |
| remote retention expiry | no local change | remote retrieval may fail | local history still renders |

## Security And Advisory Boundary

- Outputs are decision support only.
- The feature never calls any trade-execution path.
- The backend must reject cross-portfolio placeholder references even in this auth-less app.
- Prompt transparency is required: the user can inspect the rendered prompt used for each request.

## Explicit MVP Exclusions

- provider-side conversation or thread objects as the source of truth
- multi-provider fan-out for a single run
- external news or filing tools
- auto-scheduling
- autonomous loop chaining without user initiation
- trade execution based on model output
