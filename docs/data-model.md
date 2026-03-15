# Data Model Design

## Overview

Ledger uses a relational schema centered on isolated portfolios. Portfolio-owned entities store current balances, aggregate positions, simulated operations, and stock-analysis history. Global analysis entities store reusable prompt templates and user snippets. Local database rows remain the source of truth for analysis history, replay, and auditability.

## Entity Relationship Summary

- One `portfolio` has many `balances`.
- One `portfolio` has many `positions`.
- One `portfolio` has many `trading_operations`.
- One `portfolio` has one `portfolio_stock_analysis_settings` row.
- One `portfolio` has many `stock_analysis_conversations`.
- One `stock_analysis_conversation` has many `stock_analysis_runs`.
- One `stock_analysis_run` has many `stock_analysis_requests`.
- One `stock_analysis_request` has at most one `stock_analysis_response`.
- One `stock_analysis_run` has at most one `stock_analysis_version`.
- `prompt_templates` and `user_snippets` are app-global reference tables.
- `market_quotes` are shared quote cache rows keyed by symbol and provider.

## Tables

### portfolios

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| name | varchar(100) | No | User-facing portfolio name |
| description | text | Yes | Optional description |
| base_currency | char(3) | No | ISO 4217 code |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Primary key: `id`

Indexes:

- Index on `name`

### balances

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| portfolio_id | integer | No | FK to `portfolios.id` |
| label | varchar(60) | No | Example: `Cash`, `Reserve` |
| amount | numeric(20, 4) | No | Decimal-safe cash amount |
| currency | char(3) | No | Must match portfolio base currency |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Primary key: `id`
- Foreign key: `portfolio_id -> portfolios.id` with `ON DELETE CASCADE`
- Unique: `(portfolio_id, label)`
- Check: `amount >= 0`

Indexes:

- Index on `(portfolio_id, label)`

### positions

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| portfolio_id | integer | No | FK to `portfolios.id` |
| symbol | varchar(32) | No | Uppercase ticker symbol |
| name | varchar(120) | Yes | Optional display name |
| quantity | numeric(20, 8) | No | Aggregate units held |
| average_cost | numeric(20, 8) | No | Aggregate average cost basis |
| currency | char(3) | No | Must match portfolio base currency |
| last_source | varchar(16) | No | `manual`, `csv`, or `simulation` |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Primary key: `id`
- Foreign key: `portfolio_id -> portfolios.id` with `ON DELETE CASCADE`
- Unique: `(portfolio_id, symbol)`
- Check: `quantity > 0`
- Check: `average_cost >= 0`

Indexes:

- Unique index on `(portfolio_id, symbol)`

### trading_operations

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| portfolio_id | integer | No | FK to `portfolios.id` |
| balance_id | integer | Yes | FK to `balances.id`, nullable for preserved history |
| balance_label | varchar(60) | No | Snapshot of selected balance label |
| symbol | varchar(32) | No | Uppercase ticker symbol |
| side | varchar(10) | No | `BUY`, `SELL`, `DIVIDEND`, or `SPLIT` |
| quantity | numeric(20, 8) | Yes | Used for `BUY` and `SELL` |
| price | numeric(20, 8) | Yes | Used for `BUY` and `SELL` |
| commission | numeric(20, 4) | No | Absolute fee amount |
| currency | char(3) | No | Must match portfolio base currency |
| dividend_amount | numeric(20, 4) | Yes | Used for `DIVIDEND` |
| split_ratio | numeric(10, 6) | Yes | Used for `SPLIT` |
| executed_at | timestamptz | No | User-provided execution timestamp |
| created_at | timestamptz | No | Persistence timestamp |

Constraints:

- Primary key: `id`
- Foreign key: `portfolio_id -> portfolios.id` with `ON DELETE CASCADE`
- Foreign key: `balance_id -> balances.id` with `ON DELETE SET NULL`
- Check: `side IN ('BUY', 'SELL', 'DIVIDEND', 'SPLIT')`
- Check: `quantity > 0` when populated for trade operations
- Check: `price >= 0` when populated for trade operations
- Check: `commission >= 0`

Indexes:

- Index on `(portfolio_id, executed_at)`
- Index on `(portfolio_id, symbol)`

### market_quotes

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| symbol | varchar(32) | No | Uppercase ticker symbol |
| provider | varchar(50) | No | Public datasource identifier |
| price | numeric(20, 8) | No | Latest delayed price |
| currency | char(3) | No | Quote currency |
| as_of | timestamptz | Yes | Provider quote timestamp when available |
| fetched_at | timestamptz | No | Local cache fetch time |
| is_stale | boolean | No | Staleness indicator |

Constraints:

- Primary key: `id`
- Unique: `(provider, symbol, as_of)`

Indexes:

- Index on `(symbol, fetched_at desc)`
- Index on `(provider, symbol)`

### portfolio_stock_analysis_settings

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| portfolio_id | integer | No | FK to `portfolios.id`, unique |
| enabled | boolean | No | Enables stock analysis for this portfolio |
| default_prompt_template_id | integer | Yes | FK to `prompt_templates.id` |
| compare_to_origin | boolean | No | Default comparison against origin version |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Primary key: `id`
- Unique: `portfolio_id`
- Foreign key: `portfolio_id -> portfolios.id` with `ON DELETE CASCADE`
- Foreign key: `default_prompt_template_id -> prompt_templates.id` with `ON DELETE SET NULL`

Indexes:

- Unique index on `portfolio_id`

### prompt_templates

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| provider | varchar(20) | No | `openai`, `anthropic`, or `gemini` |
| display_name | varchar(120) | No | User-facing label |
| model | varchar(80) | No | Provider model id |
| openai_endpoint_mode | varchar(32) | Yes | Required only for OpenAI configs |
| base_url | text | Yes | Optional provider base URL override |
| api_key_secret | text | No | Server-managed secret |
| enabled | boolean | No | Available for new runs |
| default_generation_settings | jsonb | Yes | Optional provider-neutral defaults |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Primary key: `id`
- Unique: `display_name`
- Check: `provider IN ('openai', 'anthropic', 'gemini')`
- Check: `openai_endpoint_mode IS NOT NULL` when `provider = 'openai'`
- Check: `openai_endpoint_mode IS NULL` when `provider != 'openai'`

Indexes:

- Unique index on `display_name`

### prompt_templates

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| name | varchar(120) | No | User-facing template name |
| description | text | Yes | Optional description |
| revision | integer | No | Monotonic template revision |
| status | varchar(20) | No | `active` or `archived` |
| template_mode | varchar(20) | No | `single` or `two_step` |
| instructions_template | text | Yes | Single-prompt instructions template |
| input_template | text | Yes | Single-prompt input template |
| fresh_instructions_template | text | No | Step-one instructions template |
| fresh_input_template | text | No | Step-one input template |
| compare_instructions_template | text | No | Step-two instructions template |
| compare_input_template | text | No | Step-two input template |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Primary key: `id`
- Unique: `(name, revision)`
- Check: `status IN ('active', 'archived')`

Indexes:

- Unique index on `(name, revision)`

### stock_analysis_conversations

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| portfolio_id | integer | No | FK to `portfolios.id` |
| symbol | varchar(32) | No | Uppercase ticker symbol |
| title | varchar(160) | Yes | Optional user-facing title |
| is_archived | boolean | No | Soft archive flag |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Primary key: `id`
- Foreign key: `portfolio_id -> portfolios.id` with `ON DELETE CASCADE`

Indexes:

- Index on `(portfolio_id, symbol, is_archived)` for active-conversation lookup

### stock_analysis_runs

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| conversation_id | integer | No | FK to `stock_analysis_conversations.id` |
| mode | varchar(32) | No | `single_prompt` or `two_step_workflow` |
| run_type | varchar(32) | No | `initial_review`, `periodic_review`, `event_review`, or `manual_follow_up` |
| status | varchar(32) | No | `queued`, `running`, `completed`, `partial_failure`, or `failed` |
| provider | varchar(20) | No | Provider captured at run time |
| model | varchar(80) | No | Model captured at run time |
| provider_endpoint | varchar(32) | Yes | Example: `responses`, `chat_completions`, `messages`, or `generate_content` |
| review_trigger | text | Yes | Optional trigger summary |
| user_note | text | Yes | Optional user note |
| prompt_template_id | integer | Yes | FK to `prompt_templates.id` |
| prompt_template_revision | integer | Yes | Template revision captured at run time |
| context_snapshot | jsonb | No | Frozen context snapshot |
| compare_to_origin | boolean | No | Whether origin comparison was requested |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |
| completed_at | timestamptz | Yes | Final completion time |

Constraints:

- Primary key: `id`
- Foreign key: `conversation_id -> stock_analysis_conversations.id` with `ON DELETE CASCADE`
- Foreign key: `prompt_template_id -> prompt_templates.id` with `ON DELETE SET NULL`
- Check: `run_type IN ('initial_review', 'periodic_review', 'event_review', 'manual_follow_up')`
- Check: `status IN ('queued', 'running', 'completed', 'partial_failure', 'failed')`

Indexes:

- Index on `conversation_id`

### stock_analysis_requests

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| run_id | integer | No | FK to `stock_analysis_runs.id` |
| step | varchar(40) | No | `fresh_analysis`, `compare_decide_reflect`, `follow_up`, or `single` |
| step_index | integer | No | Execution order within the run |
| status | varchar(32) | No | Request lifecycle status |
| prompt_source | varchar(20) | No | `saved_template` or `ad_hoc` |
| provider_previous_response_id | varchar(128) | Yes | Optional provider continuation hint captured from the prior step when supported |
| instructions_snapshot | text | No | Rendered instructions sent to the provider |
| input_snapshot | text | No | Rendered input sent to the provider |
| placeholder_snapshot | jsonb | No | Resolved placeholder map |
| request_payload | jsonb | No | Outbound provider payload without secrets |
| submitted_at | timestamptz | Yes | Provider submission time |
| completed_at | timestamptz | Yes | Provider completion time |
| error_code | varchar(80) | Yes | Provider or parse error code |
| error_message | text | Yes | Human-readable failure message |
| created_at | timestamptz | No | Persistence timestamp |

Constraints:

- Primary key: `id`
- Foreign key: `run_id -> stock_analysis_runs.id` with `ON DELETE CASCADE`
- Check: `step IN ('fresh_analysis', 'compare_decide_reflect', 'follow_up', 'single')`
- Unique: `(run_id, step_index)`

Indexes:

- Unique index on `(run_id, step_index)`

### user_snippets

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| name | varchar(120) | No | Unique snippet name |
| snippet_alias | varchar(80) | No | Unique readable alias used in placeholders such as `{{user.snippet.hello_snippets}}` |
| content | text | No | Reusable prompt body |
| description | text | Yes | Optional label |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Primary key: `id`
- Unique: `name`
- Unique: `snippet_alias`

Indexes:

- Unique index on `name`
- Unique index on `snippet_alias`

### stock_analysis_responses

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| request_id | integer | No | FK to `stock_analysis_requests.id`, unique |
| provider | varchar(20) | No | Provider denormalized for lookup |
| provider_response_id | varchar(128) | Yes | Provider-issued response id |
| provider_request_id | varchar(128) | Yes | Provider-issued request or trace id |
| output_text | text | Yes | Raw output text helper |
| raw_response | jsonb | Yes | Full provider payload |
| parsed_payload | jsonb | Yes | Validated normalized payload |
| parse_status | varchar(32) | No | `pending`, `parsed_success`, or `parsed_failure` |
| input_tokens | integer | Yes | Usage tracking |
| output_tokens | integer | Yes | Usage tracking |
| reasoning_tokens | integer | Yes | Usage tracking when available |
| created_at | timestamptz | No | Persistence timestamp |

Constraints:

- Primary key: `id`
- Foreign key: `request_id -> stock_analysis_requests.id` with `ON DELETE CASCADE`
- Unique: `request_id`
- Check: `parse_status IN ('pending', 'parsed_success', 'parsed_failure')`

Indexes:

- Unique index on `request_id`
- Index on `(provider, provider_response_id)`

### stock_analysis_versions

| Column | Type | Null | Notes |
|---|---|---|---|
| id | integer | No | Primary key |
| conversation_id | integer | No | FK to `stock_analysis_conversations.id` |
| run_id | integer | No | FK to `stock_analysis_runs.id`, unique |
| version_number | integer | No | Monotonic per conversation |
| symbol | varchar(32) | No | Denormalized symbol for filtering |
| action | varchar(20) | No | Final action enum |
| confidence_score | integer | Yes | Standardized confidence score |
| fresh_analysis | jsonb | No | Structured fresh-analysis section |
| comparison | jsonb | No | Structured comparison section |
| decision | jsonb | No | Structured decision section |
| reflection | jsonb | No | Structured reflection section |
| created_at | timestamptz | No | Version timestamp |

Constraints:

- Primary key: `id`
- Foreign key: `conversation_id -> stock_analysis_conversations.id` with `ON DELETE CASCADE`
- Foreign key: `run_id -> stock_analysis_runs.id` with `ON DELETE CASCADE`
- Unique: `(conversation_id, version_number)`
- Unique: `run_id`
- Check: `action IN ('buy', 'add', 'hold', 'trim', 'sell', 'avoid', 'watch', 'no_action')`

Indexes:

- Unique index on `(conversation_id, version_number)`
- Index on `symbol`
- Unique index on `run_id`

## Derived Values

- Portfolio cash total = sum of `balances.amount` for the portfolio.
- Position market value is calculated at read time when quote currency matches the portfolio base currency.
- Market history series are fetched on demand and are not persisted as first-class rows in the current release.
- Stock-analysis viewer panels are assembled from stored version sections and request/response snapshots rather than recomputing from raw provider text.

## Data Integrity Rules

- All portfolio-owned tables must enforce portfolio isolation through `portfolio_id`.
- Balances, positions, and simulated operations use the portfolio base currency in the current release.
- Trading operations must update balances and positions in one transaction.
- CSV import commit must update positions in one transaction.
- Stock-analysis context must be snapped before the first provider call of a run.
- Requests, responses, and versions must not be mutated after creation except for in-flight status and parse metadata.
- A version row may only be created when the final response parse status is `parsed_success`.

## Suggested Enums

- `positions.last_source`: `manual`, `csv`, `simulation`
- `trading_operations.side`: `BUY`, `SELL`, `DIVIDEND`, `SPLIT`
- `stock_analysis_runs.run_type`: `initial_review`, `periodic_review`, `event_review`, `manual_follow_up`
- `stock_analysis_runs.status`: `queued`, `running`, `completed`, `partial_failure`, `failed`
- `stock_analysis_responses.parse_status`: `pending`, `parsed_success`, `parsed_failure`

## Lifecycle And Persistence Notes

- Trading operations remain append-only for auditability of simulated actions.
- Current balances and positions are authoritative after manual edits, CSV imports, and simulated operations.
- Market quotes are cache rows and may be refreshed or cleaned up without affecting portfolio records.
- Prompt templates used by historical requests archive instead of hard-deleting.
- Conversations archive instead of deleting in the current release.
- `retry` creates a new run id and new request rows.
- `replay` is read-only and uses stored snapshots.
- Provider-side retention expiry does not invalidate local history.
