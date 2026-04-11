# Ledger Orchestration Product Spec

## Status

Draft implementation spec for the next-stage Ledger orchestration product surface.

## Related Documents

- Product requirements: `docs/ledger-orchestration-product-prd.md`
- Design: `docs/ledger-orchestration-product-design.md`

This spec is intended to be self-contained for implementation. Historical orchestration docs may remain useful context, but the implementation contract for the next-stage product surface is defined here.

## Summary

This spec defines the product-facing contracts required to make orchestration a first-class, discoverable Ledger surface while keeping the existing backend execution boundaries intact.

## Scope

### In scope

- orchestration discoverability from the root shell
- orchestration management reachability for roles and characters
- internal-first backtest launch contract
- explicit compatibility-mode treatment for any retained legacy callback path
- role and character management fields required by the shipped backend contract
- orchestration-aware launch, authoring, and result flows that remain testable end to end

### Out of scope

- arbitrary orchestration pattern CRUD
- non-backtest execution products beyond the orchestration workspace and its current consumers
- worker-service externalization
- template compile-time mention execution

## Normative Terms

The key words MUST, SHOULD, and MAY are to be interpreted as described in RFC 2119.

## Source-of-Truth Boundaries

- `BacktestService` MUST remain lifecycle entry and kickoff owner.
- `BacktestEngine` MUST remain prompt construction owner.
- `BacktestCycleService` MUST remain execution-time orchestration owner.
- `backend/app/langgraph/runner.py` MUST remain execution-focused and persistence-free.
- templates MUST remain the prompt authoring surface.

## UI Reachability Requirements

### Root shell

The root application shell MUST expose an orchestration entry reachable by click from the main workspace navigation.

The orchestration entry MUST allow the user to reach:

- role management
- character management

The app MUST NOT require direct URL knowledge to access shipped orchestration management surfaces.

### Orchestration management surfaces

The roles and characters list pages MUST expose:

- create
- edit
- delete

The role and character editor pages MUST expose:

- enabled state
- the immutable identifier field in read-only or locked form after creation

## Authoring Requirements

### Template editor

The template editor MUST:

- preserve literal `@mention` text in the editor body
- preserve literal `@mention` text in inline compile preview
- expose mention assistance alongside placeholder assistance

Mention assistance MUST insert raw `@handle` author text, not canonical IDs and not placeholder syntax.

## Backtest Launch Requirements

### Backtest create request contract

The next-stage backtest-create contract MUST distinguish the primary internal path from temporary compatibility behavior.

#### Internal-first contract

The default request shape MUST be equivalent to:

- `name`
- `portfolioId`
- `templateId`
- `orchestrationPatternKey`
- `frequency`
- `priceMode`
- `startDate`
- `endDate`
- `commissionMode`
- `commissionValue`
- `benchmarkSymbols[]`
- `launchMode = "internal"` (default if omitted)

For `launchMode = "internal"`:

- callback fields MUST NOT be required
- the UI MUST NOT block submission on missing callback fields
- the backend MAY accept deprecated callback fields during migration, but MUST ignore them for validation and execution

#### Temporary compatibility contract

If a temporary migration path is still needed, the same endpoint MAY additionally accept:

- `launchMode = "legacy_callback"`
- `webhookUrl`
- `webhookTimeout`

For `launchMode = "legacy_callback"`:

- `webhookUrl` MUST be required
- `webhookTimeout` MUST be required
- the UI MUST label the mode as compatibility or legacy behavior

### Primary path

The standard backtest launch flow MUST be internal-first.

For the primary launch path, the user MUST be able to launch an orchestration backtest without supplying legacy callback input.

### Compatibility path

If legacy callback compatibility is retained during migration:

- it MUST be explicitly labeled as compatibility or legacy mode
- it MUST NOT be presented as the default mental model
- it MAY remain backend-accepted temporarily
- it MUST be removable after the migration window

### Backtest config copy

Backtest config copy MUST accurately distinguish built-in-only patterns from character-enabled patterns.

## Backend Contract Requirements

### Control-plane fields

Role reads MUST include:

- `key`
- `name`
- `description`
- `systemPrompt`
- `enabled`
- `version`

Character reads MUST include:

- `handle`
- `displayName`
- `description`
- `roleKey`
- `promptAppend`
- `enabled`
- `version`

### Validation

Role names MUST be unique.

Role keys MUST be unique and immutable.

Character handles MUST be unique, normalized, and immutable after creation.

### Mention catalog

The mention catalog endpoint MUST expose author-facing handles separately from canonical target IDs.

The response MUST support UI authoring assistance without leaking invalid author text such as `@builtin:librarian`.

## Runtime Requirements

### Prompt authority

`full_user_prompt` MUST remain the authoritative runtime input once execution-time orchestration is resolved.

`prompt_report` remains audit-oriented and MUST NOT become the execution authority again.

### Mention artifacts

Pre-run mentioned-target artifacts MUST be generated from real prompt/context inputs, not only seeded descriptions or metadata-only summaries.

Character-target artifact generation MUST use:

- role `system_prompt`
- character `prompt_append`
- `compiled_entry_prompt_body`
- `execution_context_body`

### Snapshot persistence

Per-cycle orchestration snapshots MUST remain separate from `backtests.results` and MUST preserve exact provenance for the cycle.

## Migration Rules

### Product migration target

The intended end state is **not** permanent backward compatibility in the primary flow.

### Temporary migration allowance

During migration only:

- backend contracts MAY temporarily accept compatibility-era fields
- the UI MAY expose compatibility controls only as explicit advanced or legacy mode
- tests MUST distinguish target behavior from temporary migration allowances

### Completion condition for migration

The migration is complete when:

- orchestration is reachable by click from the root shell
- internal backtest launches do not require callback input
- compatibility wording is no longer necessary in the primary user journey

## Test Plan

### Backend

Backend coverage MUST prove:

- unique role names
- immutable role keys and character handles
- authoritative `full_user_prompt`
- correct mention catalog/public handle contract
- correct per-cycle snapshot persistence

### Frontend

Frontend coverage MUST prove:

- click reachability to orchestration management
- role and character CRUD surfaces including enabled controls
- literal mention insertion and preview behavior
- backtest config copy and internal-first validation behavior

### E2E

E2E coverage MUST prove:

- click path from root shell into orchestration-related workflows
- orchestration-aware backtest launch
- successful orchestration run completion
- clear orchestration failure messaging

## Rollback and Compatibility Notes

If the shell-discoverability or internal-first launch changes introduce instability, the product MAY temporarily fall back to a reduced visible surface, but the project MUST treat that as rollback of an incomplete migration rather than evidence that the older hidden/compatibility-heavy shape is the target.

## Acceptance Criteria

This spec is acceptable only if it:

- makes orchestration discoverability testable
- makes internal-first launch behavior testable
- states the compatibility stance explicitly
- stays aligned with current backend ownership boundaries
- gives frontend, backend, and E2E implementers enough detail to build without guessing
