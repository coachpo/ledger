# Stock Analysis Function Design

## Overview

This document maps the self-reflection stock-analysis workflow onto repo-shaped application functions. It is a planning artifact only; names are chosen to fit Ledger's existing backend router/service/repository/model split and frontend `api.ts` plus query-key conventions. The design assumes a shared stock-analysis product abstraction with provider-specific adapters for OpenAI, Anthropic, and Gemini.

## Workflow Mapping

| Self-reflection phase | Application responsibility | Primary functions |
|---|---|---|
| Trigger selection | Start or continue a review for one symbol | `create_stock_analysis_run`, `prepareStockAnalysisRunDraft` |
| Fresh analysis | Build blank-slate current-context review | `build_context_snapshot`, `render_step_template`, `submit_fresh_analysis_request` |
| Save version candidate | Persist immutable request and response artifacts | `create_request_record`, `save_response_payload` |
| Comparison | Compare new view to last and origin versions | `submit_compare_decide_reflect_request`, `load_version_references` |
| Determine action | Materialize action memo and reversal conditions | `parse_final_structured_response`, `materialize_version_snapshot` |
| Reflection | Record analyst-learning notes | `parse_final_structured_response`, `buildReviewViewerModel` |

## Backend Functions

### API Layer

#### `backend/app/api/stock_analysis.py`

- `list_stock_analysis_conversations(portfolio_id, symbol=None, include_archived=False)`
- `create_stock_analysis_conversation(portfolio_id, payload)`
- `update_stock_analysis_conversation(portfolio_id, conversation_id, payload)`
- `list_stock_analysis_runs(portfolio_id, conversation_id)`
- `create_stock_analysis_run(portfolio_id, conversation_id, payload)`
- `get_stock_analysis_run(portfolio_id, run_id)`
- `list_stock_analysis_versions(portfolio_id, symbol=None)`
- `get_stock_analysis_version(portfolio_id, version_id)`

#### `backend/app/api/prompt_templates.py`

- `list_prompt_templates()`
- `create_prompt_template(payload)`
- `get_prompt_template(template_id)`
- `update_prompt_template(template_id, payload)`
- `delete_prompt_template(template_id)` - hard-delete only when unused; otherwise archive
- `preview_prompt_template(payload)`

#### `backend/app/api/llm_configs.py`

- `list_llm_configs()`
- `create_llm_config(payload)`
- `get_llm_config(config_id)`
- `update_llm_config(config_id, payload)`
- `delete_llm_config(config_id)` - hard-delete only when unused; otherwise disable

#### `backend/app/api/analysis_settings.py`

- `get_portfolio_stock_analysis_settings(portfolio_id)`
- `update_portfolio_stock_analysis_settings(portfolio_id, payload)`

### Service Layer

#### `backend/app/services/stock_analysis_service.py`

- `create_conversation(portfolio_id, payload)`
- `list_conversations(portfolio_id, symbol=None, include_archived=False)`
- `create_run(portfolio_id, conversation_id, payload)`
- `execute_run(run_id)`
- `get_run(portfolio_id, run_id)`
- `list_versions(portfolio_id, symbol=None)`

Responsibility:

- Orchestrate the end-to-end run lifecycle.
- Own transaction boundaries around run creation, request creation, response persistence, and version materialization.

#### `backend/app/services/analysis_context_service.py`

- `build_context_snapshot(portfolio_id, symbol, run_payload)`
- `load_position_context(portfolio_id, symbol)`
- `load_quote_context(portfolio_id, symbol)`
- `load_history_context(portfolio_id, symbol)`
- `load_trade_summary(portfolio_id, symbol)`
- `load_version_references(conversation_id, compare_to_origin)`
- `build_prompt_context(snapshot, references)`

Responsibility:

- Convert portfolio, position, quote, history, trade, and version data into a compact prompt-safe snapshot.

#### `backend/app/services/prompt_template_service.py`

- `list_templates()`
- `create_template(payload)`
- `update_template(template_id, payload)`
- `archive_template(template_id)`
- `validate_template(step_template)`
- `render_step_template(step, template_source, context)`
- `preview_render(payload)`
- `snapshot_template(template, step)`

Responsibility:

- Validate template grammar.
- Resolve placeholders.
- Resolve `freshAnalysis.*` only from the current run's parsed step-one payload for compare-step rendering.
- Return rendered prompt text plus placeholder metadata.

#### `backend/app/services/llm_config_service.py`

- `list_configs()`
- `create_config(payload)`
- `update_config(config_id, payload)`
- `disable_config(config_id)`
- `validate_config(payload)`

Responsibility:

- Own provider-specific config validation rules.
- Keep secret-handling server-side and return masked read models.

#### `backend/app/services/llm_gateway_service.py`

- `submit_fresh_analysis_request(run, rendered_prompt)`
- `submit_compare_decide_reflect_request(run, rendered_prompt)`
- `submit_follow_up_request(run, rendered_prompt, provider_context=None)`
- `retrieve_remote_artifact(provider, provider_response_id)`
- `build_provider_request_payload(run, rendered_prompt, response_schema)`

Responsibility:

- Select the correct provider adapter from the run's LLM config.
- Keep provider request assembly in one place.
- Normalize provider identifiers, usage fields, and payload shapes into the app's common persistence model.
- Strip secrets from persisted payload snapshots.

#### `backend/app/services/providers/openai_chat_service.py`

- `create_chat_completion(config, rendered_prompt, response_schema)`

#### `backend/app/services/providers/openai_responses_service.py`

- `create_response(config, rendered_prompt, response_schema, previous_response_id=None)`
- `retrieve_response(provider_response_id)`
- `list_response_input_items(provider_response_id)`

#### `backend/app/services/providers/anthropic_messages_service.py`

- `create_message(config, rendered_prompt, response_schema)`

#### `backend/app/services/providers/gemini_generate_content_service.py`

- `generate_content(config, rendered_prompt, response_schema)`

#### `backend/app/services/stock_analysis_parser_service.py`

- `parse_fresh_analysis_payload(raw_response)`
- `parse_final_structured_response(raw_response)`
- `validate_change_classes(parsed_payload)`
- `validate_action_fields(parsed_payload)`

Responsibility:

- Validate strict structured outputs.
- Normalize provider payloads into app DTOs.

#### `backend/app/services/stock_analysis_version_service.py`

- `materialize_version_snapshot(run, final_payload)`
- `assign_next_version_number(conversation_id)`
- `build_version_summary(version)`
- `promote_follow_up_to_version(run_id)`

Responsibility:

- Create queryable version records from successful final responses.

### Repository Layer

#### Planned repositories

- `StockAnalysisConversationRepository`
- `StockAnalysisRunRepository`
- `StockAnalysisRequestRepository`
- `StockAnalysisResponseRepository`
- `StockAnalysisVersionRepository`
- `LlmConfigRepository`
- `PromptTemplateRepository`
- `PortfolioStockAnalysisSettingsRepository`

Each repository should follow the existing repo pattern:

- constructed with `Session`
- thin CRUD/select helpers only
- no business rules

### Schema Layer

#### Planned schema modules

- `app/schemas/stock_analysis.py`
- `app/schemas/llm_config.py`
- `app/schemas/prompt_template.py`
- `app/schemas/analysis_settings.py`

Suggested contract models:

- `LlmConfigRead/Write/Update`
- `StockAnalysisConversationRead/Write/Update`
- `StockAnalysisRunCreate/Read`
- `StockAnalysisRequestRead`
- `StockAnalysisResponseRead`
- `StockAnalysisVersionRead`
- `PromptTemplateRead/Write/Update`
- `PromptTemplatePreviewRequest/Response`
- `PortfolioStockAnalysisSettingsRead/Update`

## Frontend Functions

### API Client Additions (`frontend/src/lib/api.ts`)

- `listLlmConfigs()`
- `createLlmConfig(input)`
- `updateLlmConfig(configId, input)`
- `deleteLlmConfig(configId)`
- `getStockAnalysisSettings(portfolioId)`
- `updateStockAnalysisSettings(portfolioId, input)`
- `listPromptTemplates()`
- `createPromptTemplate(input)`
- `updatePromptTemplate(templateId, input)`
- `deletePromptTemplate(templateId)`
- `previewPromptTemplate(input)`
- `listStockAnalysisConversations(portfolioId, filters)`
- `createStockAnalysisConversation(portfolioId, input)`
- `updateStockAnalysisConversation(portfolioId, conversationId, input)`
- `listStockAnalysisRuns(portfolioId, conversationId)`
- `createStockAnalysisRun(portfolioId, conversationId, input)`
- `getStockAnalysisRun(portfolioId, runId)`
- `listStockAnalysisVersions(portfolioId, filters)`
- `getStockAnalysisVersion(portfolioId, versionId)`

### Query Keys (`frontend/src/lib/query-keys.ts`)

- `stockAnalysisLlmConfigs()`
- `stockAnalysisSettings(portfolioId)`
- `stockAnalysisTemplates()`
- `stockAnalysisConversations(portfolioId, symbol?)`
- `stockAnalysisConversation(portfolioId, conversationId)`
- `stockAnalysisRuns(portfolioId, conversationId)`
- `stockAnalysisRun(portfolioId, runId)`
- `stockAnalysisVersions(portfolioId, symbol?)`
- `stockAnalysisVersion(portfolioId, versionId)`

### Feature Hooks

#### `frontend/src/components/portfolios/use-stock-analysis-data.ts`

- `useStockAnalysisData(portfolioId, symbol)`

Responsibility:

- Load settings, LLM configs, conversations, runs, and versions for the selected symbol.
- Reuse `usePortfolioWorkspaceData` context instead of duplicating portfolio, position, or quote fetches.

#### `frontend/src/components/portfolios/use-prompt-preview.ts`

- `usePromptPreview()`

Responsibility:

- Manage preview loading, validation errors, and warning display.

### UI Components

- `StockAnalysisPanel`
- `StockAnalysisConversationList`
- `StockAnalysisRunForm`
- `LlmConfigManager`
- `PromptTemplateManager`
- `PromptPreviewDialog`
- `StockAnalysisTimeline`
- `StockAnalysisReviewViewer`
- `ActionMemoCard`

### Container-Level Functions

#### `prepareStockAnalysisRunDraft(portfolioId, symbol)`

- Seed the run form from portfolio settings, the active symbol, and the default LLM config.

#### `previewStockAnalysisPrompt(draft)`

- Call the backend preview endpoint and surface placeholder errors before submit.
- When previewing `compare_decide_reflect`, include the parsed step-one payload if the template references `freshAnalysis.*`.

#### `submitStockAnalysisRun(draft)`

- Create or reuse the conversation, submit the run, and invalidate stock-analysis query keys.

#### `buildReviewViewerModel(run)`

- Convert the parsed payload into stable viewer sections.

## Function-Level Rules

### Rules That Preserve The Playbook

- `submit_fresh_analysis_request` must not inject prior thesis history unless the run type is `manual_follow_up` and the user explicitly requests it.
- `submit_compare_decide_reflect_request` must only run after step one succeeds and must build its input from local parsed step-one data, not provider-side chained memory.
- `submit_follow_up_request` may use provider-native continuation only when the selected provider supports it. In MVP, that is OpenAI Responses only.
- `materialize_version_snapshot` must only run when the final parsed payload is valid.
- `preview_render` and `render_step_template` must use the same renderer so preview matches execution.

### Rules That Preserve Auditability

- `create_run` must persist the context snapshot before the first provider call.
- `create_run` must snapshot the selected provider, model, and endpoint before the first provider call.
- `create_request_record` must persist whether the prompt came from a saved template or an ad hoc draft.
- `create_request_record` must happen before each provider call.
- `save_response_payload` must keep raw provider payload even on parse failure.
- Frontend viewer functions must read from persisted run data, not reconstruct results client-side.

## Recommended File Additions

### Backend

- `backend/app/api/stock_analysis.py`
- `backend/app/api/llm_configs.py`
- `backend/app/api/prompt_templates.py`
- `backend/app/api/analysis_settings.py`
- `backend/app/services/stock_analysis_service.py`
- `backend/app/services/llm_config_service.py`
- `backend/app/services/analysis_context_service.py`
- `backend/app/services/prompt_template_service.py`
- `backend/app/services/llm_gateway_service.py`
- `backend/app/services/providers/openai_chat_service.py`
- `backend/app/services/providers/openai_responses_service.py`
- `backend/app/services/providers/anthropic_messages_service.py`
- `backend/app/services/providers/gemini_generate_content_service.py`
- `backend/app/services/stock_analysis_parser_service.py`
- `backend/app/services/stock_analysis_version_service.py`

### Frontend

- `frontend/src/components/portfolios/use-stock-analysis-data.ts`
- `frontend/src/components/portfolios/stock-analysis-panel.tsx`
- `frontend/src/components/portfolios/stock-analysis-run-form.tsx`
- `frontend/src/components/portfolios/stock-analysis-timeline.tsx`
- `frontend/src/components/portfolios/stock-analysis-review-viewer.tsx`
- `frontend/src/components/portfolios/llm-config-manager.tsx`
- `frontend/src/components/portfolios/prompt-template-manager.tsx`

These names are intentionally aligned with the rest of the repo so the future implementation can follow existing conventions instead of inventing a new architecture.
