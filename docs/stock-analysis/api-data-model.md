# Stock Analysis API And Data Model

## Overview

This document defines the API surface and relational model for the stock-analysis feature. The design follows existing Ledger conventions:

- base path `/api/v1`
- UUID ids
- camelCase JSON externally
- decimal-safe values serialized as strings
- portfolio-scoped nested resources

## Enums

- `LlmProvider = "openai" | "anthropic" | "gemini"`
- `OpenAiEndpointMode = "chat_completions" | "responses"`
- `StockAnalysisRunType = "initial_review" | "periodic_review" | "event_review" | "manual_follow_up"`
- `StockAnalysisRunStatus = "queued" | "running" | "completed" | "partial_failure" | "failed"`
- `StockAnalysisRequestStep = "fresh_analysis" | "compare_decide_reflect" | "follow_up"`
- `StockAnalysisResponseParseStatus = "pending" | "parsed_success" | "parsed_failure"`
- `StockAnalysisAction = "buy" | "add" | "hold" | "trim" | "sell" | "avoid" | "watch" | "no_action"`
- `StockAnalysisChangeClass = "new_fact" | "changed_interpretation" | "corrected_mistake" | "noise" | "thesis_strengthening" | "thesis_weakening" | "thesis_breaking"`

## Tables

### portfolio_stock_analysis_settings

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | No | Primary key |
| portfolio_id | uuid | No | FK to `portfolios.id`, unique |
| enabled | boolean | No | Enable stock analysis for this portfolio |
| default_prompt_template_id | uuid | Yes | FK to `prompt_templates.id` |
| default_llm_config_id | uuid | Yes | FK to `llm_configs.id` |
| compare_to_origin | boolean | No | Whether runs compute delta vs origin by default |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Unique: `portfolio_id`
- FK: `portfolio_id -> portfolios.id ON DELETE CASCADE`
- FK: `default_prompt_template_id -> prompt_templates.id ON DELETE SET NULL`
- FK: `default_llm_config_id -> llm_configs.id ON DELETE SET NULL`

### llm_configs

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | No | Primary key |
| provider | varchar(20) | No | `openai`, `anthropic`, or `gemini` |
| display_name | varchar(120) | No | User-facing config label |
| model | varchar(80) | No | Provider model id |
| openai_endpoint_mode | varchar(32) | Yes | `chat_completions` or `responses`; null for non-OpenAI configs |
| base_url | text | Yes | Optional provider base URL override |
| api_key_secret | text | No | Encrypted or server-managed secret; write-only in API reads |
| enabled | boolean | No | Available for new runs |
| default_generation_settings | jsonb | Yes | Optional provider-neutral defaults such as temperature or max output tokens |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Unique: `display_name`
- Check: `provider IN ('openai', 'anthropic', 'gemini')`
- Check: `openai_endpoint_mode IS NOT NULL` when `provider='openai'`
- Check: `openai_endpoint_mode IS NULL` when `provider!='openai'`

Lifecycle rules:

- Configs referenced by any run cannot be hard-deleted in MVP.
- Referenced configs are disabled instead.

### prompt_templates

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | No | Primary key |
| name | varchar(120) | No | User-facing template name |
| description | text | Yes | Optional description |
| revision | integer | No | Monotonic template revision |
| status | varchar(20) | No | `active` or `archived` |
| fresh_instructions_template | text | No | Step-1 instructions template |
| fresh_input_template | text | No | Step-1 input template |
| compare_instructions_template | text | No | Step-2 instructions template |
| compare_input_template | text | No | Step-2 input template |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Unique: `(name, revision)`
- Check: `status IN ('active', 'archived')`

Lifecycle rules:

- Templates that have been used by any request cannot be hard-deleted in MVP.
- Used templates transition to `archived` instead.

### stock_analysis_conversations

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | No | Primary key |
| portfolio_id | uuid | No | FK to `portfolios.id` |
| symbol | varchar(32) | No | Uppercase ticker symbol |
| title | varchar(160) | Yes | Optional user-facing title |
| latest_version_id | uuid | Yes | FK to `stock_analysis_versions.id` |
| is_archived | boolean | No | Soft archive flag |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- FK: `portfolio_id -> portfolios.id ON DELETE CASCADE`
- Unique recommended index: `(portfolio_id, symbol, is_archived)` for active-conversation lookups

### stock_analysis_runs

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | No | Primary key |
| conversation_id | uuid | No | FK to `stock_analysis_conversations.id` |
| run_type | varchar(32) | No | Review type enum |
| status | varchar(32) | No | Run lifecycle status |
| llm_config_id | uuid | Yes | FK to `llm_configs.id` |
| provider | varchar(20) | No | Provider used for the run |
| review_trigger | text | Yes | User-entered or derived trigger summary |
| user_note | text | Yes | Optional note supplied in run form |
| model | varchar(80) | No | Provider model id used for the run |
| provider_endpoint | varchar(32) | Yes | Endpoint family, for example `responses`, `chat_completions`, `messages`, or `generate_content` |
| prompt_template_id | uuid | Yes | Source template id when used |
| prompt_template_revision | integer | Yes | Source revision when used |
| context_snapshot | jsonb | No | Frozen snapshot used for rendering and replay |
| compare_to_origin | boolean | No | Whether origin comparison was requested |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |
| completed_at | timestamptz | Yes | Final completion time |

Constraints:

- FK: `llm_config_id -> llm_configs.id ON DELETE SET NULL`
- FK: `conversation_id -> stock_analysis_conversations.id ON DELETE CASCADE`
- FK: `prompt_template_id -> prompt_templates.id ON DELETE SET NULL`

### stock_analysis_requests

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | No | Primary key |
| run_id | uuid | No | FK to `stock_analysis_runs.id` |
| step | varchar(40) | No | Step enum |
| step_index | integer | No | Execution order |
| status | varchar(32) | No | `queued`, `running`, `completed`, `failed` |
| prompt_source | varchar(20) | No | `saved_template` or `ad_hoc` |
| provider_previous_response_id | varchar(128) | Yes | Previous provider continuation id when supported |
| instructions_snapshot | text | No | Final rendered instructions |
| input_snapshot | text | No | Final rendered input |
| placeholder_snapshot | jsonb | No | Resolved placeholder map |
| request_payload | jsonb | No | Outbound provider payload without secrets |
| submitted_at | timestamptz | Yes | Time sent to provider |
| completed_at | timestamptz | Yes | Time provider call completed |
| error_code | varchar(80) | Yes | Provider or parse error code |
| error_message | text | Yes | Human-readable error message |
| created_at | timestamptz | No | Creation timestamp |

Constraints:

- FK: `run_id -> stock_analysis_runs.id ON DELETE CASCADE`
- Unique: `(run_id, step_index)`

### stock_analysis_responses

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | No | Primary key |
| request_id | uuid | No | FK to `stock_analysis_requests.id`, unique |
| provider | varchar(20) | No | Denormalized provider for response-id scoping and lookup |
| provider_response_id | varchar(128) | Yes | Provider-issued response or message id when present |
| provider_request_id | varchar(128) | Yes | Provider-issued request id or trace id when present |
| output_text | text | Yes | Raw output text helper |
| raw_response | jsonb | No | Full provider payload |
| parsed_payload | jsonb | Yes | Validated normalized payload |
| parse_status | varchar(32) | No | Parse lifecycle |
| input_tokens | integer | Yes | Usage tracking |
| output_tokens | integer | Yes | Usage tracking |
| reasoning_tokens | integer | Yes | Usage tracking when available |
| created_at | timestamptz | No | Creation timestamp |

Constraints:

- FK: `request_id -> stock_analysis_requests.id ON DELETE CASCADE`
- Unique: `request_id`
- Recommended index: `(provider, provider_response_id)`

### stock_analysis_versions

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | No | Primary key |
| conversation_id | uuid | No | FK to `stock_analysis_conversations.id` |
| run_id | uuid | No | FK to `stock_analysis_runs.id`, unique |
| version_number | integer | No | Monotonic per conversation |
| symbol | varchar(32) | No | Denormalized symbol for list/filter queries |
| action | varchar(20) | No | Final action enum |
| confidence_score | integer | Yes | Standardized confidence score |
| fresh_analysis | jsonb | No | Final fresh-analysis section |
| comparison | jsonb | No | Final comparison section |
| decision | jsonb | No | Final decision section |
| reflection | jsonb | No | Final reflection section |
| created_at | timestamptz | No | Version timestamp |

Constraints:

- FK: `conversation_id -> stock_analysis_conversations.id ON DELETE CASCADE`
- FK: `run_id -> stock_analysis_runs.id ON DELETE CASCADE`
- Unique: `(conversation_id, version_number)`

## API Routes

### LLM Configs

- `GET /api/v1/stock-analysis/llm-configs`
- `POST /api/v1/stock-analysis/llm-configs`
- `GET /api/v1/stock-analysis/llm-configs/{configId}`
- `PATCH /api/v1/stock-analysis/llm-configs/{configId}`
- `DELETE /api/v1/stock-analysis/llm-configs/{configId}`

DELETE semantics:

- Hard-delete when the config has never been referenced by a run.
- Disable instead of hard-delete when the config is already referenced.

### Prompt Templates

- `GET /api/v1/stock-analysis/prompt-templates`
- `POST /api/v1/stock-analysis/prompt-templates`
- `GET /api/v1/stock-analysis/prompt-templates/{templateId}`
- `PATCH /api/v1/stock-analysis/prompt-templates/{templateId}`
- `DELETE /api/v1/stock-analysis/prompt-templates/{templateId}`
- `POST /api/v1/stock-analysis/prompt-templates/preview`

DELETE semantics:

- Hard-delete when the template has never been referenced by a request.
- Archive instead of hard-delete when the template is already referenced.

### Portfolio Settings

- `GET /api/v1/portfolios/{portfolioId}/stock-analysis/settings`
- `PATCH /api/v1/portfolios/{portfolioId}/stock-analysis/settings`

### Conversations And Runs

- `GET /api/v1/portfolios/{portfolioId}/stock-analysis/conversations?symbol=AAPL&includeArchived=false`
- `POST /api/v1/portfolios/{portfolioId}/stock-analysis/conversations`
- `GET /api/v1/portfolios/{portfolioId}/stock-analysis/conversations/{conversationId}`
- `PATCH /api/v1/portfolios/{portfolioId}/stock-analysis/conversations/{conversationId}`
- `GET /api/v1/portfolios/{portfolioId}/stock-analysis/conversations/{conversationId}/runs`
- `POST /api/v1/portfolios/{portfolioId}/stock-analysis/conversations/{conversationId}/runs`
- `GET /api/v1/portfolios/{portfolioId}/stock-analysis/runs/{runId}`
- `GET /api/v1/portfolios/{portfolioId}/stock-analysis/versions?symbol=AAPL`
- `GET /api/v1/portfolios/{portfolioId}/stock-analysis/versions/{versionId}`

## Request And Response Shapes To Define

- `LlmProvider`
- `OpenAiEndpointMode`
- `LlmConfigRead`
- `LlmConfigWrite`
- `LlmConfigUpdate`
- `PortfolioStockAnalysisSettingsRead`
- `PortfolioStockAnalysisSettingsUpdate`
- `PromptTemplateRead`
- `PromptTemplateWrite`
- `PromptTemplateUpdate`
- `PromptTemplatePreviewRequest`
- `PromptTemplatePreviewResponse`
- `StockAnalysisConversationRead`
- `StockAnalysisConversationWrite`
- `StockAnalysisConversationUpdate`
- `StockAnalysisRunCreate`
- `StockAnalysisRunRead`
- `StockAnalysisRequestRead`
- `StockAnalysisResponseRead`
- `StockAnalysisVersionRead`

## Validation Rules

- `portfolioId`, `conversationId`, `runId`, `templateId`, and `versionId` are UUIDs.
- `configId` is a UUID.
- `provider` must be one of the allowed enums.
- `symbol` is normalized to uppercase.
- `runType` must be one of the allowed enums.
- `promptSource` must be `saved_template` or `ad_hoc`.
- `model` must match a server-side allowlist for the selected provider.
- OpenAI configs must provide `openaiEndpointMode`; non-OpenAI configs must not.
- A run cannot start when portfolio settings have `enabled=false`.
- A run cannot start when the selected LLM config is disabled.
- `providerPreviousResponseId` is allowed only for `follow_up` requests and only when the selected provider endpoint supports native continuation.
- A run cannot use an archived template unless it is a historical replay or read-only preview.
- A preview or run must fail when any placeholder resolves outside the active portfolio.
- A version is created only when the final response parse status is `parsed_success`.

## Lifecycle And Deletion Rules

- Settings update in place.
- LLM configs are disabled instead of hard-deleted once referenced by runs.
- Prompt templates are archived instead of hard-deleted once used.
- Conversations are archived instead of deleted in MVP.
- Runs, requests, responses, and versions are immutable after creation.
- Historical snapshots remain readable after later template edits.

### Continue, Retry, Replay

- `continue` means creating a new follow-up request or run in the same local conversation; earlier rows remain immutable.
- `retry` always creates a new run id and new request ids, even if the user is retrying the same prompt after a failure.
- `replay` is read-only and renders stored snapshots without requiring a new provider call.

## Provider-Specific Persistence Notes

- Persist `provider_response_id` on every response when present.
- Persist `provider_request_id` when the provider exposes a request or trace id.
- Persist `provider_previous_response_id` only when follow-up continuation explicitly uses provider-native chaining. In MVP, that is OpenAI Responses only.
- Do not persist secrets or authorization headers in request payload snapshots.
- Do not require provider retrieval APIs for local history rendering.
- Treat local rows as authoritative when provider retention expires or remote retrieval fails.
