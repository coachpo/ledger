# Ledger Agent Platform v2 PRD

## Metadata

Status: Draft
Supersedes: previous contents of `docs/ledger-agent-platform-product-prd.md`
References: `docs/ledger-orchestration-product-prd.md`, `docs/ledger-orchestration-product-design.md`, `docs/ledger-orchestration-product-spec.md`, `docs/orchestration-demo-runbook.md`, `backend/app/services/backtest_service.py`, `backend/app/services/backtest_cycle_service.py`, `backend/app/services/orchestration_service.py`, `backend/app/langgraph/seeds.py`, `backend/app/langgraph/runner.py`, `backend/app/models/backtest_orchestration_snapshot.py`
Source of truth notes: shipped behavior is defined by live backend and frontend code. This PRD defines the BC-breaking v2 target while explicitly naming the shipped baseline and the already-present v2-adjacent code that must be treated as migration input.

## Product summary

Ledger Agent Platform v2 turns Ledger from a backtest-owned orchestration feature into a runtime-first agent platform. The generic runtime owns execution, runs, traces, approvals, and capability resolution. Backtests become one caller of that runtime rather than the owner of orchestration itself. Roles and characters remain useful authoring and compatibility surfaces, but they no longer define the runtime contract.

## Terminology lock

Agent spec: a versioned executable definition for one agent, including instructions, model policy, default capabilities, and optional persona references.

Workflow spec: a versioned execution graph that defines steps, handoffs, step-level capability ceilings, and final output contract.

Persona profile: a non-executable authoring profile that carries role-like, character-like, or builtin prompt fragments, display metadata, handles, and default capability hints. It is the long-term landing zone for current roles, characters, and builtin mention targets.

Capability registry: the backend-owned catalog of tools, connectors, bundles, and approval policies. It has two sources: seeded immutable entries and managed entries.

Run: one execution instance owned by the generic runtime.

Trace: the ordered record of runtime events, including steps, tool calls, approvals, warnings, and outputs.

Approval policy: the saved rule on a capability or workflow step that determines whether approval is required.

Approval status: the runtime state of one approval request, such as pending, approved, denied, or expired.

Approval trace: the persisted audit trail of approval-related runtime events.

Tryout: a fast execution flow for validating an agent spec or workflow spec against sample inputs. Tryouts are ephemeral by default and retained for 24 hours unless explicitly persisted.

Studio: the authoring and inspection surface for specs, persona profiles, capabilities, runs, traces, and approvals.

## Current baseline

Shipped today:

1. `BacktestService -> BacktestCycleService -> BacktestEngine -> BacktestLangGraphRunner` owns live execution.
2. `OrchestrationService` owns role/character CRUD, mention-catalog assembly, and orchestration validation.
3. Templates keep `@mentions` literal in preview; mention resolution happens only inside backtest execution.
4. `backtest_orchestration_snapshots` stores cycle-level prompt, mention, capability, trace, and approval audit data.
5. Legacy callback is retained as a compatibility surface.

Already-present v2-adjacent code that must be treated as migration input:

1. `backend/app/langgraph/seeds.py` already defines seeded agents, topologies, mention policies, tool-enabled patterns, seeded tools, seeded capability bundles, and placeholder MCP connectors.
2. `BacktestCycleService` already performs deterministic capability resolution, bundle expansion, and initial snapshot capture before runner execution, then fills trace and final approval artifacts after runner execution or tool failure.
3. Roles and characters already expose optional `capabilityBundleKeys` and already influence execution through mention resolution, enabled-role gating, version capture, and bundle expansion.
4. `backtest_orchestration_snapshots` already persists `execution_mode`, resolved versions, `tool_call_trace`, and `approval_trace`.

## Problem

Ledger’s current orchestration design is useful, but it is centered on backtest lifecycle rather than on generic execution. That makes core runtime concepts such as tryout, run inspection, approvals, and reusable workflow definitions feel bolted on instead of first-class. It also makes the current contract harder to evolve because execution semantics, backtest semantics, and prompt-authoring semantics are too tightly coupled.

## Product thesis

Ledger should have one in-process backend runtime for agent execution. That runtime should serve backtests, tryout, and future Studio actions through one run model, one trace model, one approval model, and one capability registry. The runtime should reuse current LangGraph-backed execution adapters, but it should stop being owned by the backtest lifecycle.

## Goals

1. Make execution runtime-first, with a generic runtime service as the owner of runs, traces, approvals, and capability resolution.
2. Make backtests one caller of that runtime instead of the orchestration owner.
3. Add first-class agent specs and workflow specs with versioning and explicit lifecycle states.
4. Add a first-class capability registry with seeded immutable entries and managed entries.
5. Add first-class tryout and Studio surfaces.
6. Migrate roles and characters into persona-profile semantics without turning them into arbitrary code containers.
7. Preserve Ledger services, models, and repositories as the system of record.

## Non-goals

1. No public marketplace for arbitrary external connectors.
2. No user-authored executable code in roles, characters, persona profiles, or specs.
3. No second worker/runtime as the recommended design.
4. No raw HTTP model-call paths in application code.
5. No movement of portfolio, trade, or report persistence into LangGraph nodes.

## BC-breaking decisions

1. The core execution abstraction changes from `orchestrationPatternKey` and backtest-owned cycle orchestration to `workflowSpecKey` plus runtime-owned runs.
2. Backtests no longer own the execution graph or trace model.
3. Raw `@handle` mentions stop being the persisted runtime contract. They remain authoring shorthand only during migration.
4. Roles and characters stop being runtime-defining entities. Their long-term role is authoring compatibility through persona profiles.
5. Capability selection becomes registry- and workflow-driven, not pattern-driven.

## Current-to-v2 mapping

| Current surface | Shipped meaning | v2 destination |
|---|---|---|
| `orchestrationPatternKey` | selects seeded backtest topology/policy | replaced by `workflowSpecKey` plus optional `workflowSpecVersion` |
| `seeded_internal_backtest_v1` | seeded baseline pattern key | seeded immutable workflow spec with the same key |
| `analyst_reviewer_v1` | seeded reviewer pattern key | seeded immutable workflow spec with the same key |
| `seeded_internal_backtest_tool_enabled_v1` | seeded tool-enabled pattern key | seeded immutable workflow spec with the same key |
| `analyst_reviewer_tool_enabled_v1` | seeded reviewer tool-enabled pattern key | seeded immutable workflow spec with the same key |
| seeded agents in `seeds.py` | implicit internal agent order | migrate into seeded immutable agent specs |
| role rows | shared prompt/config layer | migrate into persona profiles of kind `role_template` |
| character rows | mentionable prompt/config layer with handle | migrate into persona profiles of kind `character_profile` |
| builtin handles `@librarian`, `@explore` | seeded mention targets with bundle refs | migrate into persona profiles of kind `builtin_profile` with identical handles |
| role/character `enabled` flags | catalog and mention eligibility gates | migrate into persona-profile `enabled` parity plus parent-role gating |
| `launchMode` | compatibility transport class | retained as compatibility transport metadata |
| execution path owner | implicit in current services | becomes explicit `executionOwner` pinned per backtest |
| `@handle` mentions in templates | literal authoring shorthand resolved at runtime | compatibility shorthand compiled into explicit persona/profile refs before execution |
| `capabilityBundleKeys` on roles/characters | declarative bundle refs affecting execution | migrate into persona-profile default capability hints |
| seeded bundle keys `builtin.librarian_context`, `builtin.explore_context` | seeded bundle refs | migrate into seeded immutable capability entries with the same keys |
| seeded connector ids `ledger.mcp.market_data`, `ledger.mcp.company_filings` | placeholder connector refs | migrate into seeded immutable capability entries with the same keys |
| `backtest_orchestration_snapshots` | per-cycle compatibility audit store | migration mirror of generic runtime traces for backtest callers until cutover completes |

## Core workflows

### 1. Studio authoring

1. Author or edit agent specs, workflow specs, and persona profiles.
2. Inspect seeded and managed capability entries.
3. View version history and activation status.

### 2. Tryout

1. Choose an agent spec or workflow spec.
2. Provide sample inputs and optional persona-profile references.
3. Execute once.
4. Inspect persisted final output, failure details, trace, approvals, and capability usage without creating a backtest.

### 3. Backtest execution

1. Backtest prepares portfolio, date, benchmark, template, and report context.
2. Backtest submits one runtime execution request per cycle.
3. Runtime returns report markdown, normalized trade decisions, and trace artifacts for that cycle.
4. Backtest continues report and trade lifecycle using runtime output.

### 4. Approval and audit review

1. Review approval-required steps and decisions.
2. Inspect trace history by run, caller, workflow spec, or capability.
3. Use one audit model across tryout and backtests.

## Product surface targets

Recommended frontend route families:

1. `/studio`
2. `/studio/agents`
3. `/studio/workflows`
4. `/studio/personas`
5. `/studio/capabilities`
6. `/studio/runs/:runId`
7. `/tryout`

`/orchestration/*` remains available during migration, but it becomes a compatibility authoring surface rather than the target abstraction.

## Rollout intent

1. Ship runtime tables and APIs first, with seeded workflow and agent specs mirroring the current seeded patterns and seeded agents.
2. Ship Studio and tryout next.
3. Migrate internal-launch backtests after runtime parity is proven.
4. Keep `launchMode=legacy_callback` on the retained legacy callback compatibility ingress throughout the rollback window.
5. Keep reversible mappings for existing pattern keys and seeded handles throughout the rollback window.
6. Retire backtest-owned execution assumptions only after explicit cutover gates pass.
7. Preserve the current omitted-selector default to `seeded_internal_backtest_v1` throughout the rollback window.

## Migration gates

1. Seeded workflow specs exist for all currently supported pattern keys.
2. Runtime traces can represent the same capability, approval, and version information currently stored on `backtest_orchestration_snapshots`.
3. Backtest execution through the runtime preserves per-cycle report creation, trade behavior, and `_run_state` redaction semantics.
4. Builtin handles, role/character capability refs, and seeded bundles have explicit v2 homes.
5. Tryout can execute without a backtest row while producing the same trace model.

## Success criteria

1. A spec can be authored, validated, executed, and traced without backtest ownership.
2. A backtest can call the runtime one cycle at a time and expose the same run and trace model.
3. Current seeded pattern behavior can be mapped into seeded workflow specs without behavioral ambiguity.
4. The doc set clearly distinguishes shipped baseline, v2-adjacent code, and the BC-breaking target.

## Risks and open questions

1. The runtime contract must be more concrete than the current backtest path, not less.
2. Migration must not erase the meaning of current roles, characters, mentions, or snapshots before replacements are available.
3. The registry split between seeded immutable and managed mutable entries must remain clear in product and implementation language.
4. Approval pause/resume and tryout persistence must be explicit runtime behaviors, not implied future work.
