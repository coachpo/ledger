# Stock Analysis Test Plan

## Objective

Verify that the stock-analysis feature is correct, reproducible, and safe as a decision-support workflow. The plan covers backend behavior, frontend behavior, provider-integration boundaries, and end-to-end user flows across OpenAI, Anthropic, and Gemini.

## Acceptance Focus

- Prompt configuration and LLM config selection work from the frontend.
- Placeholder preview catches invalid inputs before provider execution.
- Conversations, runs, requests, responses, and versions persist locally.
- The review flow follows fresh analysis before comparison.
- Structured outputs render a usable action memo and reflection block.
- Historical runs stay stable after later template changes.

## Acceptance Traceability

- `AC-1` -> frontend run form, LLM config manager, prompt template manager, and preview-to-execution consistency tests
- `AC-2` -> backend run orchestration, persistence, and versioning tests
- `AC-3` -> periodic review integration and E2E comparison tests
- `AC-4` -> placeholder preview validation tests
- `AC-5` -> historical stability and replay tests
- `AC-6` -> structured output validation plus no-trade boundary tests

## Backend Tests

### 1. Portfolio Settings

- create default stock-analysis settings for a new portfolio
- enable and disable stock analysis
- reject new runs when `enabled=false`
- update default template and default LLM config

### 2. LLM Config CRUD

- create OpenAI Responses config
- create OpenAI Chat Completions config
- create Anthropic config
- create Gemini config
- reject missing `openaiEndpointMode` for OpenAI configs
- reject `openaiEndpointMode` for non-OpenAI configs
- mask secret values on reads
- disable referenced config instead of hard-delete

### 3. Prompt Template CRUD

- create template
- update template and increment revision
- archive unused template
- reject hard-delete of a template already referenced by requests

### 4. Placeholder Preview

- resolve current snapshot placeholders such as `{{stock.symbol}}` and `{{quote.currentPrice}}`
- resolve compare-step placeholders such as `{{freshAnalysis.thesis}}` when `freshAnalysisPayload` is supplied
- resolve history references such as `{{response:latest.outputText}}`
- resolve origin references such as `{{version:origin.summary}}`
- reject unknown namespace
- reject unknown path
- reject missing record id
- reject malformed UUID in explicit history reference
- reject `freshAnalysis.*` inside `fresh_analysis` templates
- reject compare-step preview that references `freshAnalysis.*` without a supplied `freshAnalysisPayload`
- reject cross-portfolio references
- reject same-portfolio different-symbol references
- reject null required values
- accept archived same-symbol conversation references when explicitly allowed
- render escaped literal braces correctly

### 5. Run Orchestration

- create `initial_review` run with two sequential request records
- verify step-two review request is self-contained and does not require `provider_previous_response_id`
- verify run status transitions: `queued -> running -> completed`
- verify `partial_failure` when step one succeeds and step two fails
- verify `failed` when step one fails before parsing

### 6. Response Parsing And Versioning

- accept valid structured `fresh_analysis` payload
- accept valid final structured payload
- reject invalid change classification enum
- reject missing action fields
- create version only after final parse success
- assign monotonically increasing `version_number`

### 7. Persistence And Replay

- persist context snapshot before provider execution
- persist rendered prompt snapshots and placeholder map
- persist `promptSource="ad_hoc"` when a run uses an edited one-off draft instead of a saved template
- persist raw provider payload even when parse fails
- confirm historical run remains unchanged after template revision updates
- confirm replay does not require provider retrieval to render local history

### 8. Provider Boundary

- verify OpenAI Responses payload uses `instructions` and `input`
- verify OpenAI Chat Completions payload uses `messages`
- verify Anthropic payload uses provider-appropriate prompt fields and message body
- verify Gemini payload uses `contents` plus structured-output generation config
- verify structured output schema is attached using each provider's supported request shape
- verify provider-native continuation is used only for allowed continuation steps
- verify no secret fields are stored in request payload snapshots

## Frontend Tests

### 1. Run Form

- load defaults from portfolio settings
- switch symbol and preserve valid defaults
- edit user note and review trigger
- select template and LLM config
- block submit when preview has validation errors

### 2. LLM Config Manager

- list provider configs with provider, model, and endpoint mode
- create new provider config
- edit provider config
- disable provider config
- mask secret state in the UI

### 3. Prompt Template Manager

- list templates and revisions
- create new template
- edit step-specific prompt text
- archive template
- surface placeholder help and preview results

### 4. Timeline And Viewer

- list conversations by symbol
- render run status badges
- expand request and response snapshots
- render final structured sections
- show parse failures without breaking the page

### 5. Query Cache Behavior

- invalidate stock-analysis queries after run creation
- refresh conversation timeline after completion
- preserve portfolio workspace data flow from existing queries

## Integration Tests

### 1. Preview-To-Execution Consistency

- preview a prompt
- submit the run
- verify stored rendered prompt matches preview output exactly

### 2. Fresh Then Compare

- verify step-one request excludes prior-version placeholders by default
- verify step-two request includes prior version references when configured
- verify final version stores both fresh and comparison sections

### 3. Historical Stability

- run review with template revision 1
- edit template to revision 2
- reload old run and confirm stored prompt snapshots still show revision 1 output

### 4. Local Authority Over Remote Retention

- simulate missing provider retrieval after completion
- verify the UI still renders from local request/response/version tables

### 5. Provider Matrix Coverage

- run one successful review with OpenAI Responses
- run one successful review with OpenAI Chat Completions
- run one successful review with Anthropic
- run one successful review with Gemini
- confirm all four provider paths normalize into the same viewer model and version format

### 6. Advisory Boundary

- verify that no stock-analysis API path triggers trading-operation creation or balance mutation

## End-To-End Scenarios

### Scenario A. Initial Review

1. Open portfolio analysis workspace.
2. Select a symbol.
3. Select an OpenAI Responses config.
4. Preview a saved prompt template.
5. Submit `initial_review`.
6. Confirm timeline shows two provider steps and one version snapshot.
7. Confirm final viewer shows action memo and reversal conditions.

### Scenario B. Periodic Review On Alternate Provider

1. Start from an existing conversation with an origin version.
2. Select an Anthropic or Gemini config.
3. Submit `periodic_review` with a new user note.
4. Confirm final output shows delta vs last and delta vs origin.
5. Confirm version count increments by one.

### Scenario C. Event Review With Parse Failure

1. Submit `event_review` using a supported provider config.
2. Simulate malformed structured output on step two.
3. Confirm run ends `partial_failure`.
4. Confirm no new version is created.
5. Confirm raw provider payload is still inspectable.

### Scenario D. Template Regression Guard

1. Run a review with template revision 3.
2. Archive that template and create revision 4.
3. Reload the earlier run.
4. Confirm the old run still renders its stored snapshots and parsed output.

### Scenario E. OpenAI Endpoint Mode Coverage

1. Run one review with an OpenAI Chat Completions config.
2. Run one review with an OpenAI Responses config.
3. Confirm both runs succeed and render the same structured viewer shape.
4. Confirm follow-up continuation metadata is only present for the Responses-backed path when explicitly used.

## Test Data Suggestions

- One portfolio with at least two balances and several positions.
- One symbol with trade history and price history.
- One symbol without prior version history to validate first-run behavior.
- One conversation with at least two prior versions to validate delta logic.

## Exit Criteria

- All backend contract and persistence tests pass.
- All frontend interaction tests pass.
- The E2E flows prove preview, run execution, version materialization, and historical replay.
- No scenario allows cross-portfolio placeholder leakage or silent parse failure.
