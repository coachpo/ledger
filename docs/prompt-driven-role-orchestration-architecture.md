# Prompt-Driven Role Orchestration Architecture

## Status

Proposed architecture direction for evolving Ledger's internal LangGraph integration toward prompt-driven spawning of user-defined roles.

## Goal

Support the user's original vision inside Ledger:

- roles are user-defined and editable
- each role owns its own system prompt
- an entry user prompt can cause the primary model to spawn one or many role instances
- child workers run inside Ledger's backend runtime
- the parent orchestrator gathers child outputs and produces the final result

This document describes the architecture shape that best matches that vision while fitting Ledger's current codebase.

## Research Summary

The strongest pattern across OpenCode, Oh-My-OpenAgent, Codex, and Claude Code is not raw prompt-only spawning. The common shape is:

1. a primary model session interprets the user request first
2. the primary session uses a delegation primitive such as a tool or function call
3. an internal orchestrator or session manager creates child workers
4. child workers return summaries or artifacts to the parent

The key conclusions from the research are:

- **OpenCode** already supports native agents, skills, commands, tools, MCP, and subagent spawning through a built-in task/session mechanism.
- **Oh-My-OpenAgent** is a plugin harness layered on top of OpenCode. It adds opinionated orchestration behavior, reusable specialist agents, hooks, tools, background session management, and loop control, but it does not replace OpenCode's core session/subagent primitive.
- **Codex** exposes delegation through explicit function tools such as `spawn_agent`, backed by an internal thread/agent controller.
- **Claude Code** uses an `Agent` tool for ordinary child delegation and a heavier team/task layer for more structured coordination.

### Architecture conclusion from research

If Ledger should match the user's vision as closely as possible, it should adopt this shape:

- **persistent control plane** for editable roles and saved orchestration configuration
- **ephemeral runtime plane** for primary-session reasoning, child-session spawning, and result aggregation
- **structured spawn requests** between the primary model and the orchestrator

Ledger should **not** rely on raw prompt text directly spawning agents with no runtime validation, and it should **not** externalize execution into another service.

## Current Ledger Seams

The current internal LangGraph implementation is already close to the right runtime boundary:

- `backend/app/services/backtest_cycle_service.py` owns execution lifecycle and is the correct execution owner.
- `backend/app/langgraph/runner.py` owns the internal graph execution boundary.
- `backend/app/langgraph/seeds.py` already models seeded agents and a seeded topology, but as fixed in-code definitions.
- `backend/app/models/backtest.py` and `backend/app/schemas/backtest.py` are the right places to attach run-level orchestration references.
- `backend/app/models/text_template.py` and `backend/app/services/text_template_service.py` show the established CRUD pattern for editable named entities.
- `backend/app/services/report_service.py` shows the established pattern for persisted run artifacts and metadata-rich outputs.

The main gap is that Ledger currently has a narrow fixed runtime, not a user-editable control plane plus a prompt-driven orchestrator.

## Target Architecture

### 1. Control Plane (persisted)

The control plane stores the user-owned definitions that can be edited over time.

#### Role Definition

Each role is a first-class persisted entity.

Recommended fields:

- `key` or stable identifier
- `name`
- `description`
- `system_prompt`
- `enabled`
- `category` or execution type
- `allowed_tools` or capability policy
- `model_override` when needed
- `version`
- timestamps

This entity is the Ledger-native equivalent of a reusable custom agent definition.

#### Optional Workflow / Topology Definition

Roles alone are required for the user's vision. Saved topologies are optional but strongly recommended once users want repeatable working groups independent of a single prompt.

Recommended fields:

- `key`
- `name`
- `description`
- ordered node definitions
- per-node role reference
- per-node spawn rules
- enabled flag
- version

This should be a second persisted entity only if Ledger needs reusable workflows beyond runtime prompt interpretation.

#### Run Snapshot

Each execution should persist a snapshot of the exact resolved role versions and orchestration choices used during that run.

This is required for reproducibility. Later prompt edits must not silently rewrite historical behavior.

### 2. Runtime Plane (ephemeral)

The runtime plane owns live orchestration and should stay in-process.

#### Primary Orchestrator Session

The primary session receives the entry prompt and runtime context, then decides whether and how to delegate.

It does **not** directly create arbitrary workers from free-form text. Instead, it emits structured spawn requests that the orchestrator validates.

#### Structured Spawn Request

The delegation boundary should use a structured request shape rather than raw prompt strings alone.

Recommended request fields:

- `role_key`
- `count`
- `task_prompt`
- `context_refs`
- `expected_output`
- `priority`
- optional `parent_step_id`

This is the Ledger equivalent of the delegation tools used by Codex, Claude Code, and OpenCode.

#### Child Worker Sessions

Each child worker is created from a validated role definition plus runtime task context.

Child workers should receive:

- the resolved role system prompt
- the delegated task prompt
- the scoped working context
- capability restrictions

Child workers return summarized results and artifact references to the primary session.

#### Aggregation Layer

The parent orchestrator gathers child outputs, handles partial failures, and produces the final analysis, report, and trade decisions.

This remains a Ledger-owned runtime responsibility, not a prompt convention.

## Execution Flow

The target runtime flow should be:

1. Ledger loads the entry prompt and current execution context.
2. Ledger resolves the active role registry and any optional saved topology.
3. The primary orchestrator session interprets the entry prompt.
4. The primary session emits one or more structured spawn requests.
5. Ledger validates each spawn request against the role registry, limits, and permissions.
6. Ledger creates child worker sessions for accepted requests.
7. Child workers execute in parallel where allowed.
8. Ledger aggregates child summaries/artifacts back into the primary session.
9. The primary session produces the final output.
10. Ledger persists run artifacts, delegation events, terminal outputs, and errors.

This preserves the user's desired behavior while keeping runtime control in Ledger instead of relying on unchecked prompt magic.

## Where This Fits in the Current Codebase

### `backend/app/services/backtest_cycle_service.py`

This should remain the execution owner. It should load the control-plane configuration, construct the runtime orchestrator, start the run, and persist final artifacts.

### `backend/app/langgraph/runner.py`

This should evolve from a fixed seeded graph into a registry-driven runtime boundary. The runner should consume resolved role/runtime specs instead of owning fixed role behavior.

### `backend/app/langgraph/seeds.py`

This should become the source of built-in defaults that can be represented through the same role/topology contract as user-defined entries.

### `backend/app/models/backtest.py` / `backend/app/schemas/backtest.py`

These should carry the run-level orchestration references and snapshot identifiers when backtests use prompt-driven orchestration.

### Template / Report CRUD patterns

`text_template` and `report` CRUD stacks should be treated as the implementation precedent for new editable orchestration entities.

## Persistence Rules

### Persist these

- role definitions
- optional workflow/topology definitions
- entry prompt
- resolved role versions used in the run
- spawn/delegation events
- child summaries
- artifact references
- final output
- terminal errors

### Keep these ephemeral unless a stricter audit need appears later

- live context windows
- scratchpads
- token-level reasoning
- in-flight child session state
- temporary routing heuristics

Ledger should persist definitions, events, and outputs first. It should not start by persisting every live runtime detail.

## Guardrails

Prompt-driven spawning must be governed by runtime rules, not just prompt instructions.

Required guardrails:

- max fan-out per run
- recursion depth limit
- disabled/missing role validation
- capability/tool restrictions per role
- timeout budget per child worker
- partial-failure handling policy
- deterministic snapshotting of resolved role versions

Without these guardrails, prompt-driven orchestration will quickly become expensive, slow, and difficult to debug.

## Non-Goals

This architecture should **not** do the following:

- externalize orchestration into a separate worker service
- let raw prompt text directly create arbitrary unvalidated roles
- make LangGraph graph state the system of record
- persist every token-level runtime detail by default

## Recommended Rollout

### Phase 1: Registry-first runtime

Introduce persisted role definitions and convert the current seeded roles into built-in registry entries.

The runtime still stays relatively narrow, but role prompts are no longer hardcoded.

### Phase 2: Prompt-driven spawning

Introduce the primary orchestrator session and structured spawn request boundary.

This is the first phase that truly matches the user's original vision.

### Phase 3: Optional reusable workflows

Add saved workflow/topology definitions only after role registry plus prompt-driven spawning are stable.

This avoids over-designing workflow persistence before the core orchestrator contract is proven.

## Why This Matches the Original Vision

This architecture satisfies the user's original goals because:

- roles are editable and persistent
- each role has its own system prompt
- the entry prompt can cause many role instances to be spawned
- Ledger, not an external service, owns orchestration
- the final result is gathered by a primary orchestrator session

It also matches the real pattern used by sophisticated coding agents more closely than a raw prompt-only model.

## Key Risks

### Reproducibility drift

If Ledger does not persist the exact resolved role versions used in a run, later prompt edits will make historical behavior hard to explain.

### Unbounded fan-out

If the runtime accepts unlimited prompt-driven spawning, cost and latency will grow uncontrollably.

### Over-persisted runtime state

If Ledger tries to store full live session state from the start, the system will become harder to reason about and evolve.

## References

- OpenCode agents: https://opencode.ai/docs/agents/
- OpenCode plugins: https://opencode.ai/docs/plugins/
- OpenCode skills: https://opencode.ai/docs/skills/
- OpenCode config: https://opencode.ai/docs/config/
- Oh-My-OpenAgent docs: https://ohmyopenagent.com/docs
- Codex subagents: https://developers.openai.com/codex/subagents
- Codex concepts: https://developers.openai.com/codex/concepts/subagents
- Claude Code sub-agents: https://code.claude.com/docs/en/sub-agents
- Claude Code agent teams: https://code.claude.com/docs/en/agent-teams
- Claude Code tools reference: https://code.claude.com/docs/en/tools-reference
