# Stock Analysis PRD

## Product Summary

Add a stock-analysis workflow to Ledger that uses configurable LLM providers - OpenAI, Anthropic, and Gemini - to turn existing portfolio context into structured, versioned review opinions. OpenAI support includes both `chat/completions` and `responses`. The feature helps a single trusted user decide whether to buy, add, hold, trim, sell, avoid, or watch a stock without automating trades.

## Problem Statement

Ledger already stores positions, balances, trading history, delayed quotes, and market history, but it does not preserve an explicit stock thesis over time. That makes it hard to answer basic investing questions with discipline:

- What did I believe before?
- What do I believe now?
- What changed in the business, valuation, or risk profile?
- Did my view change because of facts or because of price movement?
- What action, if any, should follow?

The self-reflection playbook in `docs/playbook/self_reflection_stock_analysis_loop.md` solves that with a strict pattern: analyze first, compare later, classify changes, decide whether action is justified, and record reflection. This feature turns that pattern into an application workflow.

## Target User

- A single operator using Ledger in a trusted environment.
- A user already maintaining portfolios, positions, balances, and simulated trades manually.
- A user who wants decision support, traceability, and version history rather than auto-generated trade execution.

## Goals

- Let the user request a structured stock analysis for one symbol in one portfolio.
- Let the user configure reusable LLM configs from the frontend and choose among supported providers per run.
- Keep the prompt configurable from the frontend, with reusable templates and run-time draft editing.
- Support placeholders that inject current stock context and prior conversation/request/response/version references.
- Persist conversations, runs, requests, responses, and versioned review outputs in the local database.
- Preserve the self-reflection rule: fresh analysis must happen before comparison with prior versions.
- Return machine-readable outputs that separate fresh analysis, comparison, decision, and reflection.

## Non-Goals

- Automatic trade execution or broker integration.
- Portfolio-wide autonomous analysis loops in MVP.
- External news, filing, or research ingestion beyond existing app context and the user note supplied at run time.
- Authentication, scheduling, notifications, or alerting.
- Free-form chat as the primary UX. The primary unit is a review run with persisted structure.

## Scope Exclusions

The broader playbook in `docs/playbook/llm-stock-analysis-loop-documentation-set.md` is not the MVP scope for this folder. The stock-analysis design here explicitly excludes:

- portfolio-scope LLM analysis as a first-class mode
- multi-provider dispatch or provider fan-out within one run
- automatic provider routing or model benchmarking
- provider secret management in the frontend

## Core User Stories

- As a user, I want to configure and preview a stock-analysis prompt from the frontend so I can control how the LLM reasons.
- As a user, I want placeholders like current price, prior response, or prior version summary so prompts can adapt without manual copy-paste.
- As a user, I want to choose a configured provider/model pair for a run, including OpenAI Chat Completions, OpenAI Responses, Anthropic, or Gemini.
- As a user, I want an initial stock review saved as a durable version so later reviews can compare against it.
- As a user, I want a later review to first analyze the current stock from fresh context and only then compare against older versions.
- As a user, I want every conversation, request, and response saved so I can inspect what was asked, what context was used, and what the model returned.
- As a user, I want the final result to include an explicit action memo and reversal conditions so the output is operational.

## MVP Features

### 1. LLM Config Management

- Create, edit, disable, and list reusable LLM configs.
- Support `openai`, `anthropic`, and `gemini` as first-class providers.
- Support OpenAI endpoint selection per config: `chat_completions` or `responses`.
- Store provider credentials server-side only and return masked secret state on reads.

### 2. Prompt Template Management

- Create, edit, archive, and list reusable stock-analysis prompt templates.
- Store separate step templates for `fresh_analysis` and `compare_decide_reflect`.
- Let the user preview rendered prompts before execution.
- Let the user start from a saved template and edit a one-off draft for a specific run.

### 3. Portfolio-Scoped Stock Analysis Settings

- Enable or disable stock analysis per portfolio.
- Store per-portfolio defaults such as default template, default LLM config, and default comparison behavior.

### 4. Stock Analysis Conversations

- Create a conversation per `(portfolio, symbol)`.
- Show a timeline of runs, requests, responses, and final version snapshots.
- Keep app conversations local to the database; do not rely on provider-side conversation objects for history.

### 5. Versioned Review Runs

- Support `initial_review`, `periodic_review`, `event_review`, and `manual_follow_up` run types.
- For review runs, execute two sequential provider calls through the selected LLM config:
  1. `fresh_analysis`
  2. `compare_decide_reflect`
- Persist a version snapshot from the final structured result when the run is review-bearing.

### 6. Structured Decision Output

- The final result must include:
  - fresh analysis
  - change classification
  - decision/action stance
  - reversal conditions
  - reflection notes
- The output is advisory only and never triggers trades.

## User Experience Principles

- Analyze first, compare later.
- Make non-action explicit.
- Show the rendered prompt and referenced records so the user understands what the LLM saw.
- Preserve history; do not overwrite prior versions.
- Prefer structured summaries over long free-form chat transcripts.
- Treat malformed or partial AI output as recoverable application state, not invisible failure.

## Key Screens

### Stock Analysis Workspace

- Lives inside the existing portfolio analysis surface.
- Lets the user pick a symbol, choose a template and LLM config, preview the prompt, and start a run.

### LLM Config Manager

- Lists configured providers, models, endpoint modes, and enabled state.
- Creates and edits OpenAI, Anthropic, and Gemini configs without exposing secrets back to the client.

### Prompt Template Manager

- Lists templates and revisions.
- Edits `fresh_analysis` and `compare_decide_reflect` step templates separately.
- Shows placeholder help and preview output.

### Conversation Timeline

- Shows each run with trigger, provider, model, endpoint, status, and final stance.
- Expands into request snapshots, response snapshots, parse status, and version details.

### Structured Review Viewer

- Renders fresh analysis, comparison, action memo, and reflection as distinct panels.
- Highlights delta vs last version and delta vs origin when available.

## Success Criteria

- A user can configure an LLM config and template, preview the prompt, and submit a stock review from the frontend without editing code.
- A user can run an `initial_review` and later a `periodic_review` for the same symbol and see an explicit structured delta.
- Every run persists local conversation, request, response, and version records even if provider-side retention later expires or remote retrieval is unavailable.
- Invalid placeholders are caught before provider execution.
- Historical runs remain readable after templates change.
- The final output gives a clear action stance plus reversal conditions.

## Acceptance Criteria

- `AC-1` A user can create or edit an LLM config and prompt template in the frontend, preview its rendered prompt for a selected stock, and submit a run successfully.
- `AC-2` A submitted `initial_review` persists a conversation, run, provider-aware request records, response records, and a version snapshot in the local database.
- `AC-3` A later `periodic_review` for the same symbol produces a structured delta vs the last version and, when enabled, vs the origin version.
- `AC-4` Invalid placeholders, unauthorized references, or missing referenced records are rejected before the provider call.
- `AC-5` Historical runs continue to display their original rendered prompts and parsed outputs after later template edits or prompt archival.
- `AC-6` Final outputs always remain advisory, include an explicit action stance, and never trigger Ledger trade execution.

## Risks And Mitigations

- Prompt brittleness can make results unstable; mitigate with template revisions, prompt preview, and stored snapshots.
- Anchoring can distort later reviews; mitigate with a fixed two-step workflow that forbids prior-version context in the fresh-analysis step.
- Provider contract differences can create drift; mitigate with provider-specific request builders and a shared normalized response model.
- Vendor-side retention can expire; mitigate by making the local database authoritative for history.
- Structured output can fail to parse; mitigate with strict schema validation, persisted raw payloads, and explicit parse status.
- Placeholder misuse can leak the wrong context; mitigate with curated namespaces, same-portfolio access rules, and preview validation.

## Release-Ready Definition

- Portfolio-scoped stock analysis can be enabled and configured.
- LLM configs for OpenAI, Anthropic, and Gemini are editable from the frontend, with OpenAI endpoint mode selection.
- Prompt templates are editable from the frontend and previewable with placeholders.
- Review runs persist conversations, requests, responses, and version snapshots.
- The workflow follows fresh analysis before comparison.
- Final responses are machine-readable and advisory only.
- Historical artifacts remain queryable after later prompt edits.
