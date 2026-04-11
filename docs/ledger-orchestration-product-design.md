# Ledger Orchestration Product Design

## Status

Draft technical design for evolving Ledger from a backtest-first orchestration slice into a first-class orchestration product surface.

## Related Documents

- Product requirements: `docs/ledger-orchestration-product-prd.md`
- Implementation spec: `docs/ledger-orchestration-product-spec.md`

This design is intended to be self-contained and primary for the next-stage product direction. Older architecture and backtest-first docs may remain as historical context, but the target system shape is defined here.

## Goal

Define the target system shape that makes orchestration discoverable, internally coherent, and implementation-ready without violating Ledger’s existing runtime ownership boundaries.

## Current-State Gap Analysis

### What already exists

- persisted orchestration roles and characters
- mention assistance in the template editor
- orchestration pattern selection in backtests
- execution-time mention parsing/resolution in the backtest runtime
- per-cycle orchestration snapshot persistence

### What is still structurally wrong

- orchestration is implemented but not productized in the root UI
- the backtest launch path still carries legacy callback compatibility in the primary flow
- the product model is still implicitly “backtests first, orchestration second” even where orchestration already has standalone surfaces
- users must reason about historical compatibility decisions rather than a clean current mental model

## Design Principles

1. **First-class discoverability** — shipped orchestration surfaces must be reachable by click from the root shell.
2. **Internal-first execution** — internal LangGraph is the real primary path, not a compatibility overlay.
3. **Backtest remains a consumer, not the sole frame** — orchestration is broader than one launch form, even if backtests remain the main execution workflow today.
4. **Preserve runtime ownership boundaries** — `BacktestService`, `BacktestEngine`, `BacktestCycleService`, and `runner.py` keep their responsibilities.
5. **Compatibility is transitional** — if retained, it must be explicit and temporary.

## Target Product Shape

### 1. Orchestration becomes a root-level workspace

The application shell should expose orchestration as a discoverable top-level entry. That entry may lead to an overview page or directly to the roles/characters surfaces, but it cannot remain hidden behind direct route knowledge.

Minimum target surface:

- root-shell orchestration entry
- orchestration overview or management hub
- role management
- character management

### 2. Templates remain the orchestration authoring surface

Templates remain the place where users write orchestration prompts. Mention assistance stays inside the template editor because that is where authoring happens.

This avoids splitting orchestration intent across two competing prompt surfaces.

### 3. Backtests consume orchestration through a clean launch contract

The backtest configuration page remains the launch surface, but its default path becomes unambiguously internal. Legacy callback compatibility, if still supported, becomes an advanced compatibility mode rather than a required or default-form input path.

The recommended migration bridge is a single explicit launch-mode split in the request and UI:

- `internal` — default, callback fields absent and not required
- `legacy_callback` — explicit compatibility mode, callback fields present and required only for that mode

### 4. Runtime artifact generation remains backend-owned

The runtime remains in-process and backend-owned:

- `BacktestService` owns lifecycle entry and kickoff
- `BacktestEngine` owns prompt bundle construction
- `BacktestCycleService` owns orchestration-time resolution, pre-run artifact generation, and snapshot persistence orchestration
- `runner.py` remains execution-focused and persistence-free

## System Boundaries

### Control plane

Owns persisted orchestration definitions and management APIs.

Components:

- orchestration role model/service/API
- orchestration character model/service/API
- mention catalog API for authoring assistance

### Authoring plane

Owns user-authored template content and mention assistance.

Components:

- template list/editor pages
- placeholder reference and mention assistance
- inline preview that remains literal for `@mentions`

### Launch plane

Owns backtest initiation and orchestration-pattern selection.

Components:

- backtest config page
- backtest creation request contract
- validation rules for internal vs compatibility launch modes

### Execution plane

Owns cycle-time prompt preparation, mention resolution, pre-run artifacts, runner invocation, and snapshot provenance.

Components:

- `BacktestEngine`
- `BacktestCycleService`
- `backend/app/langgraph/runner.py`
- `backtest_orchestration_snapshots`

## UX Architecture

### Root-shell discoverability

The shell should expose orchestration next to the existing operational areas instead of requiring hidden routes. The design intent is not to create a new parallel product shell, but to acknowledge orchestration as a real workspace.

### Backtest launch model

The UI should make a single truth visible:

- internal LangGraph is the standard launch path
- legacy callback, if retained, is advanced compatibility

That truth must appear in copy, validation, and request shape consistently.

### Failure-state clarity

Backtest detail should continue surfacing orchestration-related failures in user-visible terms. Runtime errors remain backend-authored, but the surface must stay understandable at the page level.

## Migration Strategy

### Recommended target

The target shape is **not** permanent backward compatibility.

The preferred migration strategy is:

1. expose orchestration in the shell
2. move callback compatibility out of the default flow
3. keep backend acceptance temporarily if required
4. remove callback compatibility from the primary product contract after migration

### Why this is better

Permanent compatibility keeps the app in a contradictory state. A short compatibility window preserves delivery safety without allowing migration code to define the product model.

## Risks and Tradeoffs

### Tradeoff: simpler product shape vs migration cost

Removing compatibility from the primary flow produces a much cleaner application, but requires coordinated frontend, backend, and documentation changes.

### Tradeoff: root nav discoverability vs shell simplicity

Adding orchestration to the shell increases visible surface area, but hiding shipped functionality is worse for UX, QA, and support.

### Tradeoff: keep backtests central vs overfit the whole product to backtests

Backtests remain a strong execution consumer, but they should no longer be the only conceptual entry point for orchestration.

## ADR-Style Decisions

### Decision 1 — Orchestration is a first-class workspace

**Decision:** expose orchestration from the root shell.

**Why:** current hidden-route behavior makes the product internally inconsistent and blocks click-only workflows.

### Decision 2 — Internal execution is the primary flow

**Decision:** internal LangGraph execution defines the primary backtest launch path.

**Why:** it matches the actual architecture direction and reduces user confusion.

### Decision 3 — Compatibility is migration, not architecture

**Decision:** retain callback compatibility only as an explicit migration layer if needed.

**Why:** compatibility code should not own the long-term mental model.

## Acceptance Criteria

This design is acceptable only if it:

- maps current repo seams to a cleaner target product shape
- keeps execution ownership with existing backend services and runner boundaries
- defines orchestration discoverability as a shell-level concern
- defines internal-first launch as both a UX and contract concern
- provides a migration path away from primary-flow backward compatibility
- avoids pushing code-level API/schema detail that belongs in the spec
