# Backtest-First Prompt-Driven Orchestration Blueprint

## Status

Proposed implementation blueprint derived from `docs/prompt-driven-role-orchestration-architecture.md`.

This blueprint narrows the architecture into a backtest-first delivery slice while preserving the user's requirement that a backtest must accept a user-authored generic orchestration prompt so different orchestration patterns can be evaluated inside Ledger.

## Blueprint Acceptance Criteria

This blueprint is complete only if it does all of the following:

- keeps `BacktestService` and `BacktestCycleService` as the live lifecycle boundary
- keeps `app/langgraph/` as the in-process execution boundary rather than the persistence layer
- uses the existing template/report/backtest stacks as the implementation precedent for new orchestration entities
- treats the backtest template as the backtest entry prompt surface instead of inventing a second unrelated prompt surface
- supports evaluation of different orchestration patterns inside backtests without allowing raw prompt text to create arbitrary unvalidated roles
- labels unresolved scope forks explicitly instead of silently assuming them

## Scope

### In scope

- a backtest-first orchestration control plane
- a user-authored generic orchestration prompt inside the existing backtest flow
- persisted role definitions
- selectable orchestration patterns for backtest evaluation
- structured runtime spawning inside Ledger's backend process
- persisted run snapshots, delegation events, and child outputs

### Out of scope for this blueprint

- a fully generic orchestration product outside backtests
- a separate worker service or webhook-driven agent runtime
- direct prompt-only spawning with no runtime validation
- persisting token-level reasoning or full live LangGraph state as the system of record

## Why backtest-first is the right first slice

Ledger already has a real orchestration entry path for backtests:

- `backend/app/api/backtests.py` exposes the live creation/read/cancel/delete surface.
- `backend/app/services/backtest_service.py` validates the request, resolves the selected template, persists the backtest row, and launches `BacktestCycleService`.
- `backend/app/services/backtest_engine.py` compiles the selected template into the cycle prompt, persists the prompt report, and prepares market/portfolio context.
- `backend/app/services/backtest_cycle_service.py` loads the prompt report and invokes the internal LangGraph runner.
- `backend/app/langgraph/runner.py` already turns prompt-report input into report content plus normalized `TradeDecision[]` output.

That makes backtests the only current Ledger surface where a prompt-driven orchestrator can be introduced without inventing an unrelated product shell first.

## Repo Evidence Anchors

This blueprint is grounded in these current files:

- architecture direction: `docs/prompt-driven-role-orchestration-architecture.md`
- backtest lifecycle entry: `backend/app/api/backtests.py`, `backend/app/services/backtest_service.py`
- cycle execution owner: `backend/app/services/backtest_cycle_service.py`
- prompt construction and prompt-report persistence: `backend/app/services/backtest_engine.py`
- current fixed seeded runtime: `backend/app/langgraph/seeds.py`, `backend/app/langgraph/runner.py`
- editable named-entity precedent: `backend/app/models/text_template.py`, `backend/app/schemas/text_template.py`, `backend/app/services/text_template_service.py`, `backend/app/api/templates.py`
- artifact persistence precedent: `backend/app/models/report.py`, `backend/app/schemas/report.py`, `backend/app/services/report_service.py`, `backend/app/api/reports.py`, `backend/app/repositories/report.py`
- run-state precedent and redaction behavior: `backend/app/models/backtest.py`, `backend/app/schemas/backtest.py`, `backend/tests/test_backtests_api.py`
- runner and cycle regression coverage: `backend/tests/test_langgraph_runner.py`, `backend/tests/test_backtest_cycle_service.py`, `backend/tests/test_backtest_service.py`

## Current Prompt Ingress and Why It Matters

The current backtest prompt path already has the right shape for a generic orchestration prompt:

1. `BacktestCreate` stores `template_id` on the backtest row.
2. `BacktestEngine._build_prompts()` loads that `TextTemplate`.
3. `TemplateCompilerService.compile()` renders the template with backtest runtime inputs like `cycle_date`, `portfolio_name`, and `frequency`.
4. `BacktestEngine._store_prompt_report()` persists the resulting cycle prompt as a report.
5. `BacktestCycleService._run_internal_cycle()` loads that prompt report and passes it to the LangGraph runner.

### Blueprint decision

For the first orchestration slice, the user's generic orchestration prompt should be the selected backtest template body.

That means:

- no second free-text entry surface is required for v1
- the existing template editor remains the user-authored prompt surface
- each cycle already snapshots the resolved prompt through the persisted prompt report
- backtest runs can evaluate orchestration changes by varying template content and/or orchestration pattern selection

## Target v1 Product Shape

### User-facing behavior

In a backtest, the user should be able to:

- choose or author a template whose content acts as the entry orchestration prompt
- select an orchestration pattern for the run
- run the backtest and compare how different orchestration patterns behave against the same portfolio and market context

### Important limitation

The prompt may request delegation, but the runtime may only spawn roles that exist in the selected orchestration pattern and active role registry.

The prompt is the request surface, not the authority surface.

## Control Plane Design

The control plane should add two persisted orchestration entities and one run snapshot entity.

### 1. Role definition registry

This is the Ledger-native equivalent of a reusable subagent definition.

Recommended fields:

- `id`
- `key` - stable lookup key
- `name`
- `description`
- `system_prompt`
- `enabled`
- `built_in` - whether the row is Ledger-seeded
- `execution_mode` - worker / reviewer / synthesizer / orchestrator helper
- `allowed_tools` or capability policy payload
- `model_override` - optional
- `sort_order`
- `version`
- timestamps

### Why this shape fits Ledger

- It follows the editable named-entity pattern used by `TextTemplate`.
- It keeps mutable role configuration outside LangGraph runtime state.
- It gives the runtime a validated registry to resolve against before spawning workers.

### 2. Orchestration pattern registry

Backtest evaluation requires more than roles alone. The user needs a way to choose which orchestration pattern the run should use.

For v1, this should be a selectable pattern registry rather than a full arbitrary workflow editor.

Recommended fields:

- `id`
- `key`
- `name`
- `description`
- `built_in`
- `enabled`
- `orchestrator_prompt` - prompt or policy guidance for the primary coordinator
- `role_order` or referenced role list
- `spawn_policy` JSON payload
- `aggregation_policy` JSON payload
- `fan_out_limit`
- `depth_limit`
- `version`
- timestamps

### Why this is needed in v1

The architecture doc treated reusable workflows as optional later work, but the user's clarification adds a concrete first-slice need: backtests must support evaluation of different orchestration patterns. A selectable pattern registry is the smallest control-plane object that satisfies that requirement without jumping straight to a fully general workflow editor.

### 3. Run snapshot

Each backtest run must persist the exact orchestration configuration it used.

Recommended snapshot payload:

- selected orchestration pattern key and version
- resolved role keys and versions
- resolved orchestrator prompt
- selected backtest template id
- the template content hash or resolved prompt artifact reference
- runtime limits used for this run

### Storage recommendation

Use a dedicated orchestration snapshot record or dedicated snapshot JSON field, not `backtests.results._run_state`.

Rationale:

- `BacktestRead` already hides `_run_state` from API reads when it contains only internal execution state.
- the AGENTS guidance says LangGraph state should stay narrow and execution-focused
- run snapshot data is durable provenance, not transient progress bookkeeping

## Backtest Contract Changes

### Keep for v1

- `template_id` remains the entry prompt selector
- the selected template content becomes the user-authored generic orchestration prompt
- `BacktestService` remains the lifecycle entry and kickoff owner

### Add for v1

Recommended new backtest request field:

- `orchestration_pattern_key: str | None`

Behavior:

- if omitted, Ledger uses the default built-in backtest orchestration pattern
- if provided, the key must resolve to an enabled pattern
- the backtest row stores the chosen pattern reference for that run

### Do not add in v1

- a second separate free-text orchestration prompt field
- arbitrary role definitions inline on the backtest request
- direct runtime graph JSON in the API payload

The existing template surface is already the cleanest way to accept the user's generic orchestration prompt inside backtests.

## Runtime Plane Design

### Execution owner

`BacktestCycleService` remains the execution owner.

Its orchestration responsibilities should expand to:

- resolve the selected orchestration pattern
- resolve the active role registry
- create a deterministic snapshot for the run or cycle
- build the registry-driven runner
- persist delegation events and child outputs
- keep final trade/report persistence in the existing engine and report flows

### Runner boundary

`backend/app/langgraph/runner.py` should evolve from a fixed seeded graph into a registry-driven runtime boundary.

It should accept:

- the prompt report content
- the orchestration pattern snapshot
- the resolved role set
- runtime guardrails

It should return:

- final analysis content
- normalized trade decisions
- child summaries and event references needed by the persistence layer

### Keep out of the runner

- ORM writes
- direct mutation of backtest lifecycle fields
- ownership of long-lived orchestration definitions

## Recommended Runtime Pattern

Based on the current repo seams plus LangGraph and coding-agent research, the best-fit runtime shape is:

1. coordinator or supervisor node
2. structured spawn request boundary
3. role workers as subgraphs or bounded worker sessions
4. reducer-based aggregation of child outputs
5. synthesizer node that emits final report content and trade decisions

### Why this fits the evidence

- The architecture doc already prefers structured spawn requests over raw prompt-only spawning.
- LangGraph's best-fit official pattern is supervisor plus subgraphs plus `Send` fan-out for dynamic worker spawning.
- OpenCode, Claude Code, Codex, and Oh-My-OpenAgent all reinforce validated delegation, explicit session lineage, and parent-owned aggregation.

## Structured Spawn Request Contract

The primary orchestrator should never directly create arbitrary workers from free-form prompt text.

Recommended spawn request fields:

- `role_key`
- `task_prompt`
- `context_refs`
- `expected_output`
- `count`
- `priority`
- `parent_step_id`

### Validation rules

Every spawn request must be checked against:

- selected orchestration pattern
- enabled role registry
- max fan-out limit
- recursion or delegation depth limit
- allowed capability policy for the selected role
- per-run timeout budget

If validation fails, the orchestrator should receive a structured rejection result rather than an implicit no-op.

## How the Generic Orchestration Prompt Works in Backtest v1

### Prompt source

The backtest template is the generic orchestration prompt.

### Runtime prompt assembly

`BacktestEngine._build_prompts()` should keep building the cycle prompt out of:

- system date guardrails
- portfolio state
- market context
- benchmark context
- prior reports
- compiled template content

### Behavioral change

The compiled template content is no longer treated only as a fixed single-agent analysis instruction block.

Instead, it becomes the entry orchestration request that the primary coordinator interprets.

Examples of what the prompt may ask for:

- a single-pass conservative review
- analyst plus critic pattern
- fan-out symbol analysts with a final synthesizer
- risk-first review before decision writing

### Runtime limit

The prompt may request those patterns, but the runtime may only realize them through the selected orchestration pattern and validated role registry.

That gives the user a real generic prompt inside backtests while keeping Ledger in control of cost, safety, and reproducibility.

## Built-in v1 Orchestration Patterns

To satisfy the user's evaluation goal without requiring a full custom workflow editor in the first slice, v1 should ship with built-in patterns represented through the same pattern registry contract.

Recommended initial built-ins:

- `single_supervisor_v1` - coordinator interprets the prompt and produces final output with minimal delegation
- `analyst_reviewer_v1` - analyst worker plus risk/reviewer worker plus final synthesizer
- `fanout_symbols_v1` - coordinator fans out position-level analysis, aggregates, then synthesizes

### Why built-ins first

- the repo already uses built-in seeded definitions in `backend/app/langgraph/seeds.py`
- the user can compare patterns immediately inside backtests
- custom user-defined patterns can be deferred until the registry contracts prove stable

## Persistence Design

### Persisted definitions

- orchestration roles
- orchestration patterns

### Persisted per-run or per-cycle artifacts

- orchestration snapshot
- delegation events
- child summaries
- final synthesized report content
- final trade decisions
- terminal errors

### Existing Ledger precedents to reuse

- `TextTemplate` stack for editable registry rows
- `Report` stack for persisted prompt and analysis artifacts
- `Backtest` row for lifecycle ownership and top-level run reference
- `TradingOperation` style append-only persistence for event-like records if event tables are added

### Recommended artifact storage split

- keep prompt report and final cycle analysis report in the existing report system
- add dedicated orchestration event storage for spawn requests, worker outcomes, and validation failures
- keep transient progress bookkeeping in the current backtest `_run_state`

## Proposed Backend Surface Changes

### Models

Recommended additions:

- orchestration role model
- orchestration pattern model
- orchestration snapshot model or snapshot field
- orchestration event model

Recommended backtest model addition:

- selected orchestration pattern reference

### Schemas

Recommended additions:

- role create/update/read schemas
- pattern create/update/read schemas
- snapshot read schema if exposed through API

Recommended backtest schema addition:

- optional `orchestrationPatternKey` on `BacktestCreate`

### Services

Recommended additions:

- role registry service
- orchestration pattern service
- orchestration snapshot/event service

Recommended changes:

- `BacktestService` validates selected pattern key and stores the reference
- `BacktestCycleService` resolves the snapshot and records orchestration events

### API routes

Recommended additions:

- `/api/v1/orchestration/roles`
- `/api/v1/orchestration/patterns`

The existing `/api/v1/backtests` route remains the execution entry for v1.

## Guardrails

The runtime must enforce the following guardrails regardless of what the prompt requests:

- max fan-out per cycle
- recursion or delegation depth limit
- enabled-role validation
- selected-pattern validation
- capability restrictions per role
- timeout budget per child worker
- partial-failure handling policy
- deterministic snapshotting of the resolved role and pattern versions

These are not optional. They are what turn a prompt-driven backtest into a reproducible evaluation surface instead of prompt magic.

## Failure Handling Policy

### Validation failures

- do not crash the whole run by default
- record a structured orchestration event
- surface the failure back to the coordinator
- allow the coordinator to continue if the pattern policy permits degradation

### Worker failures

- record worker-level failure details
- apply pattern-defined partial-failure policy
- continue to final synthesis only if required minimum outputs were produced

### Terminal failures

- preserve existing backtest terminal failure behavior through `BacktestEngine._mark_failed()` and `BacktestCycleService`

## TDD and Verification Plan

Implementation should extend the existing test layers rather than creating a new disconnected test strategy.

### Schema and CRUD tests

Mirror the template/report pattern in `backend/tests/test_api.py` for:

- role CRUD
- pattern CRUD
- validation of disabled or missing pattern selection

### Backtest service tests

Extend `backend/tests/test_backtest_service.py` for:

- storing selected orchestration pattern references on create
- validating missing or disabled pattern keys before kickoff

### Cycle service tests

Extend `backend/tests/test_backtest_cycle_service.py` for:

- snapshot resolution
- structured spawn request validation
- event persistence
- partial-failure policy behavior

### Runner tests

Extend `backend/tests/test_langgraph_runner.py` for:

- registry-driven role resolution
- pattern selection
- `Send`-style fan-out aggregation semantics
- synthesis from child outputs

### Backtest API tests

Extend `backend/tests/test_backtests_api.py` for:

- `orchestrationPatternKey` serialization
- redaction rules for transient internal orchestration state
- exposure of durable orchestration snapshot references only when intended

## Recommended Rollout

### Phase 1 - Role and pattern registry, backtest-first

- add persisted role registry
- add built-in orchestration pattern registry
- keep current backtest template as the entry orchestration prompt
- add pattern selection to backtests
- evolve the runner to consume registry and pattern snapshots

### Phase 2 - Structured spawn requests and child artifact persistence

- implement validated spawn requests
- persist orchestration snapshots and delegation events
- add partial-failure and fan-out guardrails

### Phase 3 - Pattern expansion and optional custom workflow editing

- allow user-defined orchestration patterns if the built-in registry contract is stable
- consider broader non-backtest orchestration surfaces only after the backtest-first path is proven

## Open Questions

These should stay explicit until the next implementation-planning pass.

### 1. Pattern persistence depth

Should v1 patterns be built-in rows only, or should user-authored custom patterns be writable in v1?

Recommendation: built-in selectable patterns first, custom pattern authoring later.

### 2. Snapshot storage shape

Should snapshots live in dedicated tables, dedicated JSONB fields on `backtests`, or both?

Recommendation: durable snapshot/event storage should be separate from `_run_state`.

### 3. API surface breadth

Should the first slice expose orchestration CRUD in backend only, or also add frontend management UI immediately?

Recommendation: backend contracts first, frontend management UI after the runtime contract is stable.

### 4. Prompt/report metadata shape

Should prompt reports and final cycle analysis reports include orchestration pattern and role snapshot references in `ReportMetadata.analysis`?

Recommendation: yes, if done in a backwards-compatible way through metadata extension rather than top-level schema churn.

## Final Blueprint Decision

Backtest-first should mean:

- the user writes a generic orchestration prompt in the existing backtest template
- the user selects a built-in orchestration pattern for the run
- Ledger validates role spawning against a persisted role and pattern registry
- the runtime runs in `BacktestCycleService` plus `app/langgraph/`
- prompt reports and analysis reports remain normal Ledger reports
- durable orchestration provenance is stored separately from transient `_run_state`

That is the smallest Ledger-native slice that matches the architecture doc, preserves existing boundaries, and lets the user evaluate different orchestration patterns inside real backtests.
