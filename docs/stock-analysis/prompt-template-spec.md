# Prompt Template Specification

## Overview

Prompt templates let the frontend configure how Ledger asks the selected LLM provider for stock-analysis output. Templates are step-aware, portfolio-safe, and replayable across OpenAI, Anthropic, and Gemini.

Each template contains two step definitions:

- `fresh_analysis`
- `compare_decide_reflect`

Each step definition contains:

- `instructionsTemplate`
- `inputTemplate`

## Design Goals

- Keep templates editable from the frontend.
- Support placeholders for live stock context and persisted history.
- Prevent silent hidden-state behavior.
- Preserve exact rendered prompts for historical replay.
- Keep the grammar simple enough for non-engineering users.

## Provider Rendering Model

Templates stay provider-neutral. The renderer always produces the same two canonical strings:

- `instructions`
- `input`

Provider adapters then map those strings into provider-specific payloads:

- OpenAI `responses` -> top-level `instructions` plus `input`
- OpenAI `chat/completions` -> `messages` with system/user mapping
- Anthropic Messages -> top-level `system` plus `messages`
- Gemini `generateContent` -> `contents` plus structured-output generation config

This means template preview is provider-agnostic, while request execution still persists the exact provider payload actually sent.

## Supported Token Set

The grammar is intentionally curated, not arbitrary. Templates may use only documented namespaces and paths. In practice, the preferred tokens are compact summaries rather than deep object traversal, for example:

- `{{portfolio.summary}}`
- `{{stock.summary}}`
- `{{quote.summary}}`
- `{{history.priceSummary}}`
- `{{freshAnalysis.thesis}}`
- `{{version:latest.summary}}`
- `{{version:origin.summary}}`
- `{{response:latest.outputText}}`
- `{{userNote.text}}`

## Grammar

### Scalar Or Simple Path

```text
{{namespace.path}}
```

Examples:

- `{{stock.symbol}}`
- `{{quote.currentPrice}}`
- `{{position.averageCost}}`
- `{{run.reviewTrigger}}`

### Explicit Record Reference

```text
{{namespace:identifier.path}}
```

Examples:

- `{{conversation:current.id}}`
- `{{conversation:2b4c....title}}`
- `{{request:latest.inputSnapshot}}`
- `{{response:latest.outputText}}`
- `{{version:origin.decision.action}}`

## Namespaces

### Current Snapshot Namespaces

- `portfolio.*`
- `stock.*`
- `position.*`
- `quote.*`
- `history.*`
- `freshAnalysis.*` (compare step only)
- `run.*`
- `userNote.*`

Examples:

- `{{portfolio.name}}`
- `{{stock.symbol}}`
- `{{position.quantity}}`
- `{{quote.currentPrice}}`
- `{{history.priceSummary}}`
- `{{freshAnalysis.thesis}}`
- `{{userNote.text}}`

### Persistence And Lineage Namespaces

- `conversation:*`
- `request:*`
- `response:*`
- `version:*`

Reserved identifiers:

- `current`
- `latest`
- `origin`

Examples:

- `{{conversation:current.id}}`
- `{{request:latest.instructionsSnapshot}}`
- `{{response:latest.outputText}}`
- `{{version:origin.freshAnalysis.thesis}}`

## Convenience Aliases

The renderer should normalize a few user-friendly aliases to the canonical grammar:

- `{{last.request.*}}` -> `{{request:latest.*}}`
- `{{last.response.*}}` -> `{{response:latest.*}}`
- `{{last.conversation.*}}` -> `{{conversation:current.*}}`

This keeps the system compatible with the examples in the user request without making the grammar inconsistent.

## Resolution Rules

### General Rules

- Resolution is single-pass only.
- No conditionals, loops, filters, or code execution in MVP.
- All placeholder resolution happens on the backend.
- Template text is stored as plain text.

### Access Rules

- A placeholder may only resolve records inside the active portfolio.
- Cross-portfolio references fail validation.
- `conversation:*`, `request:*`, `response:*`, and `version:*` must all belong to the active conversation or to another archived/live conversation for the same `(portfolioId, symbol)` when explicitly referenced.
- Cross-symbol historical references are rejected in MVP even inside the same portfolio.
- `freshAnalysis.*` is available only to the `compare_decide_reflect` step and must resolve from the current run's parsed step-one payload, not from historical records.

### Serialization Rules

- Scalars resolve to plain text.
- Objects resolve to pretty JSON text.
- Arrays resolve to pretty JSON text unless a preformatted summary field exists.
- Null values fail validation by default.

### Escaping Literal Braces

- Use `\{{` for a literal `{{`.
- Use `\}}` for a literal `}}`.
- The renderer must unescape these only after placeholder scanning completes.

### Recommended Summary Fields

To avoid noisy prompts, the snapshot builder should expose compact summary fields such as:

- `history.priceSummary`
- `history.tradeSummary`
- `version:latest.summary`
- `version:origin.summary`

These reduce the need for templates to pull raw arrays.

## Preview API Behavior

The preview endpoint accepts either:

- a saved template id plus step
- or an ad hoc template draft plus step

The request also includes:

- `portfolioId`
- `symbol`
- optional `llmConfigId`
- optional `conversationId`
- optional `freshAnalysisPayload` when previewing `compare_decide_reflect`
- optional `runType`
- optional `reviewTrigger`
- optional `userNote`

The response returns:

- `renderedInstructions`
- `renderedInput`
- `placeholderValues`
- `referencedRecords`
- `warnings[]`
- `errors[]`

### Preview-Execution Parity Rule

- Preview and execution must use the same backend renderer and the same placeholder resolver version.
- If a preview is tied to a selected LLM config, execution must use the same provider adapter family unless the user explicitly changes configs and re-previews.
- A prompt that previews successfully with the same request payload must render identically at execution time unless the underlying snapshot inputs changed.
- Execution must persist the exact snapshot used so later history does not depend on live record changes.

## Snapshot And Versioning Rules

- Every request stores the exact rendered `instructions` and `input` that were sent.
- Every request stores the provider-specific outbound payload snapshot that was assembled from those rendered fields.
- Every request stores the resolved placeholder map used to build those texts.
- Historical requests never re-render from the latest template revision.
- Template updates increment `revision`.
- If a user edits a template into a one-off run draft, the request snapshot stores `promptSource="ad_hoc"` plus the rendered prompt.

## Step-Specific Guidance

### `fresh_analysis`

- Should default to current stock context only.
- Should not auto-reference `version:latest.*` or `response:latest.*`.
- Must reject `freshAnalysis.*` references because this step is the producer of that payload.
- Should ask for a provisional stance only.

### `compare_decide_reflect`

- May reference `version:latest.*`, `version:origin.*`, and `freshAnalysis.*` from the current run's parsed step-one payload.
- Should classify change types explicitly.
- Should output the final action memo and reflection block.

## Failure Cases

Preview and execution must fail for:

- unknown namespace
- unknown path
- missing referenced record
- missing `freshAnalysisPayload` when previewing `compare_decide_reflect` and the template references `freshAnalysis.*`
- deleted or archived record that is not allowed for reference
- archived or unauthorized record outside scope
- null value for required placeholder
- recursive placeholder expansion attempt

## Edge-Case Matrix

| Case | Preview result | Execution result | Notes |
|---|---|---|---|
| invalid UUID in `{{response:{id}.path}}` | fail | fail | validation error |
| unknown historical id | fail | fail | no provider call |
| unresolved or null value | fail by default | fail | deterministic behavior |
| literal braces escaped with `\{{` | pass | pass | render literal braces |
| cross-portfolio reference | fail | fail | security boundary |
| same-portfolio, different-symbol history reference | fail | fail | stock-only scope |
| archived same-symbol conversation reference | pass | pass | read-only historical access allowed |
| preview succeeds, live record later changes | pass | run uses new snapshot if re-rendered | historical runs still use stored snapshots |

## Example Template Fragments

### Fresh Analysis Input

```text
Review {{stock.symbol}} in portfolio {{portfolio.name}}.

Current context:
{{stock.summary}}

Quote context:
{{quote.summary}}

Price history:
{{history.priceSummary}}

User note:
{{userNote.text}}

Do not compare against prior versions in this step. Produce only the fresh analysis output.
```

### Compare And Decide Input

```text
Use the fresh analysis you just produced.

Latest prior version summary:
{{version:latest.summary}}

Origin version summary:
{{version:origin.summary}}

Classify what changed, determine whether the change matters, produce the final action memo, and add a reflection block.
```
