# LLM Stock Analysis Loop Documentation Set

## Summary

Create a new documentation package under `docs/stock-analysis/` that specifies an MVP for manual LLM-driven analysis with two independent analysis modes:

- **portfolio analysis** for the entire portfolio
- **stock analysis** for one specific symbol in a portfolio

Users can enable either mode or both for each portfolio. The design will follow the self-reflection loop in `docs/playbook/self_reflection_stock_analysis_loop.md`: fresh analysis first, then saved versioning, structured comparison, action decision, and reflection.

The MVP uses existing portfolio data, quote/history context, and user notes. It stores LLM configs and prompt templates in the database, persists every conversation/request/response, supports OpenAI, Google Gemini, and Anthropic models, supports parallel backend dispatch to multiple LLM targets in one run, and requires structured JSON responses so comparison and decision-support views are machine-readable.

## Deliverables

- `docs/stock-analysis/prd.md`: product goals, target user, success criteria, non-goals, core flows, enablement rules, and rollout boundaries.
- `docs/stock-analysis/spec.md`: end-to-end functional design for backend, frontend, analysis scopes, session lifecycle, concurrent execution flow, persistence, failure handling, and UI states.
- `docs/stock-analysis/api-data-model.md`: REST endpoints, request/response shapes, entities, validation rules, concurrency controls, lifecycle constraints, and deletion/update behavior.
- `docs/stock-analysis/prompt-template-spec.md`: placeholder syntax, supported namespaces, scope-aware rendering rules, preview behavior, and prompt snapshot/versioning rules.
- `docs/stock-analysis/scope-matrix.md`: portfolio-vs-stock capability matrix for prompts, placeholders, outputs, UI entry points, and comparison behavior.
- `docs/stock-analysis/test-plan.md`: backend, frontend, integration, and E2E scenarios tied to acceptance criteria.

## Key Design Decisions

- **Analysis scopes:** support `portfolio` and `stock` as first-class scopes. Portfolio scope analyzes allocation, concentration, cash, diversification, recent portfolio behavior, and trade posture. Stock scope analyzes one symbol's thesis, valuation, risk, triggers, and action stance.
- **Feature enablement:** add per-portfolio analysis settings with `enablePortfolioAnalysis` and `enableStockAnalysis`. Users can turn on either mode or both. Disabled modes are hidden in the UI and rejected by the backend for new runs.
- **Conversation scope:** an `AnalysisConversation` belongs to one portfolio and one scope. `symbol` is required for `stock` scope and must be null for `portfolio` scope.
- **Run types:** define `initial_review`, `periodic_review`, `event_review`, `compare_only`, and `reflection_only`. Each run becomes one persisted request/response pair inside a conversation.
- **LLM management:** add full CRUD for `LlmConfig` records with provider (`openai`, `google`, or `anthropic`), display name, model id, base URL, API key secret, enabled flag, optional default generation settings, and a per-model concurrency cap. OpenAI configs must also declare an endpoint mode so the backend can call either `chat/completions` or `/responses`. Custom base URL and API key handling must work consistently across all three providers. API keys are stored server-side and returned masked on reads.
- **Concurrent backend dispatch:** a single analysis run can issue multiple LLM calls simultaneously. Each request carries a `globalMaxConcurrency` plus provider-aware dispatch counts such as `openai=3, google=2, anthropic=0`, `openai=1, google=1, anthropic=1`, or `openai=0, google=3, anthropic=2`. A count of `0` disables that provider for the run without removing the config.
- **Concurrency enforcement:** effective parallelism is limited by both the request's `globalMaxConcurrency` and each model's configured cap. The backend must queue or reject excess dispatch slots deterministically instead of silently exceeding limits.
- **Prompt management:** add full CRUD for reusable `PromptTemplate` records. Each template declares scope support: `portfolio`, `stock`, or `both`. Every analysis request stores the exact template snapshot, resolved placeholders, selected LLM id, and execution parameters used for that run.
- **Request fan-out persistence:** keep one parent `AnalysisRequest` per user-triggered run, then persist one child dispatch record per outbound LLM call. Each dispatch records the target provider, target model, dispatch index, queued/running/succeeded/failed status, timing, error state, and linked response payload. This allows a request like `OpenAI x3 + Gemini x2 + Anthropic x1` to produce six independently traceable results.
- **Placeholder system:** use a curated token format such as `{{namespace.path}}` and `{{namespace:id.path}}`. Support shared namespaces like `portfolio.*`, `conversation.*`, `request.*`, `response.*`, `last.request.*`, `last.response.*`, and `user_notes.*`, plus scope-specific namespaces such as `portfolio_summary.*`, `positions.*`, `balances.*`, `stock.*`, `quote.*`, and `history.*`. Invalid or scope-incompatible placeholders fail preview and execution before the provider call.
- **Prompt preview:** require a backend preview endpoint that resolves placeholders without calling the LLM and returns rendered text, referenced records, and validation errors. Preview must explain when a template is incompatible with the selected scope.
- **Structured output contract:** use a shared JSON envelope with `scope`, `summary`, `comparison`, `decision`, and `reflection`, plus a scope-specific body. Portfolio runs return portfolio-level insights and actions. Stock runs return thesis, valuation, risk, scorecard, trigger evaluation, and reversal conditions.
- **Versioning and comparison:** each response records `deltaVsLast` and optional `deltaVsOrigin`. Change items are classified as `new_fact`, `changed_interpretation`, `corrected_mistake`, `noise`, `thesis_strengthening`, `thesis_weakening`, or `thesis_breaking`. Portfolio scope compares portfolio posture over time; stock scope compares thesis evolution for the selected symbol.
- **Persistence model:** define entities for `PortfolioAnalysisSettings`, `LlmConfig`, `PromptTemplate`, `AnalysisConversation`, `AnalysisRequest`, `AnalysisDispatch`, `AnalysisResponse`, and a request-time context snapshot. Responses are immutable after creation except for parse-status metadata.
- **API surface:** add CRUD endpoints for LLMs and prompt templates, read/update endpoints for portfolio analysis settings, and conversation/run endpoints under portfolio scope. Conversation listing must support filtering by `scope` and `symbol`, and run execution must accept concurrency planning across OpenAI, Google, and Anthropic targets. LLM CRUD must expose the OpenAI endpoint mode so configs can choose `chat_completions` or `responses`.
- **Frontend functions:** add UI for LLM manager, prompt template manager, portfolio analysis settings, conversation lists filtered by scope, create-session dialogs, run-analysis forms, prompt preview, request/response timelines, structured review viewers, concurrency controls, and comparison/action panels. The run form should let users set the overall max concurrency and per-provider or per-config dispatch counts for OpenAI, Google, and Anthropic.
- **Advisory boundary:** document clearly that outputs are decision support only, never automatic trade execution, and never a substitute for user judgment.

## Public APIs / Types To Specify

- `AnalysisScope = "portfolio" | "stock"`
- `PortfolioAnalysisSettingsRead/Update`
- `LlmConfigRead/Write/Update`
- `OpenAiEndpointMode = "chat_completions" | "responses"`
- `PromptTemplateRead/Write/Update`
- `AnalysisConversationRead/Write/Update`
- `AnalysisDispatchPlan`
- `AnalysisProvider = "openai" | "google" | "anthropic"`
- `PromptPreviewRequest/Response`
- `AnalysisRequestCreate`
- `AnalysisRequestRead`
- `AnalysisDispatchRead`
- `AnalysisResponseRead`
- `AnalysisComparisonRead`
- New route groups for `/api/v1/llms`, `/api/v1/prompt-templates`, `/api/v1/portfolios/{portfolioId}/analysis-settings`, and `/api/v1/portfolios/{portfolioId}/analysis-conversations`

## Test Plan

- **Backend CRUD:** create, update, delete, and list LLM configs and prompt templates; verify masked secret reads, secret replacement, provider-specific validation for OpenAI, Google, and Anthropic records, OpenAI endpoint-mode validation for `chat_completions` and `responses`, and delete constraints when records are in use.
- **Analysis settings:** enable only portfolio analysis, enable only stock analysis, enable both, disable both, and verify backend enforcement plus frontend visibility rules.
- **Concurrency controls:** verify `globalMaxConcurrency`, per-model caps, `0`-count disable behavior, and example fan-out plans such as `OpenAI x3 + Gemini x2 + Anthropic x0`, `OpenAI x1 + Gemini x1 + Anthropic x1`, `OpenAI x0 + Gemini x3 + Anthropic x2`, and `OpenAI x3 + Gemini x0 + Anthropic x1`.
- **Placeholder resolution:** validate shared placeholders, scope-specific placeholders, explicit request/response references, cross-portfolio access rejection, and stock-only placeholder rejection in portfolio scope.
- **Execution flow:** persist requests before provider calls, create one dispatch record per outbound call, execute eligible dispatches concurrently across OpenAI, Google, and Anthropic, support both OpenAI `chat/completions` and `/responses` request/response shapes, persist raw and normalized responses after success, and handle parse failures, provider HTTP errors, timeouts, partial failures, and duplicate submission rules.
- **Conversation behavior:** create and run portfolio-scope conversations, create and run stock-scope conversations, filter history by scope, compare against original thesis/posture, and preserve historical snapshots after later edits to templates or LLM configs.
- **Structured response validation:** accept valid portfolio JSON and valid stock JSON; reject malformed JSON, wrong scope payloads, missing required sections, invalid enums, and incomplete action fields.
- **Frontend UX:** validate template compatibility, preview rendering, mode enablement toggles, portfolio-analysis entry flow, stock-analysis entry flow, overall concurrency input, OpenAI/Google/Anthropic dispatch inputs, OpenAI endpoint-mode selection where relevant, grouped dispatch results, timeline rendering, comparison summaries, and degraded error states without losing history.
- **E2E scenarios:** enable both modes, run a portfolio analysis with concurrent OpenAI, Google, and Anthropic dispatches, run a stock analysis with one provider disabled by `0` count, inspect grouped dispatch results plus saved action memo and reflection, and verify all requests, dispatches, and responses remain accessible after reload.

## Assumptions And Defaults

- Single-user, auth-less application; LLM configs and templates are app-global, while conversations and analysis settings are portfolio-scoped.
- No new external research, news, or filing ingestion in MVP beyond existing app context and user-supplied notes.
- Manual execution only; no scheduling or automatic loop chaining in the first release, but one manual run may fan out to multiple concurrent LLM calls.
- Structured JSON is mandatory for provider responses in MVP.
- OpenAI, Google, and Anthropic are all first-class providers in MVP, each using the same CRUD, secret-handling, preview, dispatch, and persistence lifecycle.
- OpenAI support includes both `chat/completions` and `/responses`, selected per LLM config rather than hardcoded globally.
- Portfolio analysis and stock analysis keep separate conversation histories. Cross-scope referencing is allowed only through explicit placeholders or referenced conversation ids, not through implicit synchronization.
- Concurrency settings are explicit per run. The backend must never exceed the smaller of the request's global limit and each model's configured cap.
- Documentation should be implementation-ready and should remove ambiguity about how the two analysis modes coexist in the same product.
