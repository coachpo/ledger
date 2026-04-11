# Ledger Orchestration Product PRD

## Status

Draft proposed product direction for making orchestration a first-class Ledger surface rather than a backtest-only hidden capability.

## Related Documents

- Technical design: `docs/ledger-orchestration-product-design.md`
- Implementation spec: `docs/ledger-orchestration-product-spec.md`

This PRD is intended to stand on its own as a primary product reference. Historical architecture and implementation docs may remain useful context, but this document does not depend on them to define the target product shape.

## Product Thesis

Ledger should treat orchestration as a first-class product surface with its own discoverable UI, explicit control plane, and internal-first execution model.

Backtests should remain an important orchestration consumer, but they should no longer be the only way the feature makes sense to a user, nor should the primary orchestration flow be shaped around legacy callback compatibility.

## Problem Statement

Ledger currently contains real orchestration capability, but the user experience is internally inconsistent.

Observed current-state problems:

- orchestration role and character pages exist in the router but are not reachable by click from the root shell
- the template editor supports execution-time `@mentions`, but the management surfaces for those targets are not discoverable from the same workflow
- backtest creation claims internal LangGraph is the default path while still requiring legacy callback fields in the primary launch flow
- users must understand implementation history to understand product behavior

This creates avoidable friction in adoption, QA, onboarding, and future roadmap decisions.

## Why Now

Ledger already has the underlying runtime, control-plane entities, authoring surfaces, and validation patterns needed to support orchestration as a product area. The remaining gaps are mostly product-shape and contract-shape gaps, not proof-of-concept gaps.

Continuing to preserve backward compatibility in the primary flow will increase UX debt, documentation debt, and engineering cost because every new orchestration improvement must still explain or accommodate the legacy callback path and hidden navigation model.

## Target Users

### Primary user

An operator, analyst, or developer using Ledger to define reusable orchestration behavior and compare how different orchestration patterns perform during portfolio analysis and backtests.

### Secondary user

An internal maintainer or QA engineer who needs a discoverable, testable orchestration surface without relying on hidden routes or undocumented assumptions.

## Jobs To Be Done

Users should be able to:

- discover orchestration from the root application shell
- create and manage reusable roles and characters without direct URL knowledge
- author templates that call built-ins and characters with `@mentions`
- launch internal backtests using orchestration without supplying legacy callback details
- understand whether a selected orchestration pattern is built-in-only or character-enabled
- inspect backtest outcomes and failure states with orchestration behavior reflected clearly

## Product Goals

1. Make orchestration reachable and understandable from the root Ledger UI.
2. Make internal execution the actual default, not just the copy default.
3. Keep orchestration configuration app-wide and reusable across backtests.
4. Preserve the existing backend execution ownership boundaries.
5. Reduce permanent backward-compatibility burden in the primary product flow.

## Non-Goals

- building a generic multi-tenant orchestration platform
- adding arbitrary pattern CRUD in this stage
- externalizing execution into a separate worker service
- exposing token-level reasoning or internal runtime state as a product surface
- redesigning reports, portfolios, or the broader shell beyond what orchestration discoverability requires

## Core Product Requirements

### 1. Discoverable orchestration area

Ledger MUST expose orchestration through the root UI so users can reach orchestration management by click from the application shell.

At minimum, the user must be able to reach:

- orchestration landing or entry point
- role management
- character management

### 2. Internal-first backtest launch

The normal backtest creation path MUST launch internal orchestration runs without requiring user-supplied legacy callback fields.

If a legacy callback mode is retained temporarily, it MUST be framed as an explicit compatibility path rather than the default mental model.

The migration target is an explicit mode split:

- **Internal** is the default launch path and does not require callback fields.
- **Legacy callback** is opt-in compatibility behavior and may require callback fields only while the migration window remains open.

### 3. Reusable orchestration control plane

Roles and characters MUST remain app-wide, versioned, and manageable through first-class product surfaces. Users should not have to create inline orchestration definitions inside backtest requests.

### 4. Authoring continuity

Templates MUST remain the prompt-authoring surface for orchestration prompts. `@mentions` remain execution-time semantics, not template-compile semantics.

### 5. Backtest as orchestration consumer

Backtests remain a core orchestration consumer and comparison surface. The product should allow users to evaluate different orchestration patterns against the same portfolio and template inputs without creating a second competing authoring model.

## User Journeys

### Journey A — Configure orchestration

1. User opens Ledger.
2. User clicks an orchestration entry from the root shell.
3. User creates or edits a role.
4. User creates or edits a character based on that role.
5. User leaves with stable, reusable orchestration targets available to template authoring.

### Journey B — Author an orchestration-aware template

1. User opens Templates from the root shell.
2. User opens the editor.
3. User uses mention assistance and placeholder reference together.
4. User saves a template containing valid `@mention` text.

### Journey C — Launch an internal orchestration backtest

1. User opens Backtests from the root shell.
2. User opens New Backtest.
3. User chooses an orchestration pattern, a portfolio, and a template.
4. User launches the run without being forced through legacy callback input for the default path.
5. User sees the result/failure surface with orchestration-specific behavior reflected clearly.

## Success Metrics

### Product metrics

- percentage of orchestration-related sessions that begin from a clickable root-shell path rather than direct URL navigation
- percentage of internal backtests launched without legacy callback mode
- adoption of character-enabled orchestration patterns compared with built-in-only patterns

### Quality metrics

- zero hidden-route dependencies in primary orchestration workflows
- zero user-facing contradictions between backtest copy and actual validation behavior
- stable orchestration E2E coverage for management, authoring, launch, and failure flows

## Rollout Strategy

### Phase 1 — First-class product shape

- add orchestration discoverability in the root UI
- make backtest launch internal-first in both copy and validation
- keep current control-plane/runtime boundaries intact

### Phase 2 — Compatibility contraction

- move any retained callback path behind explicit legacy mode
- stop documenting callback compatibility as the default experience
- keep compatibility only long enough to migrate remaining consumers

### Phase 3 — Remove primary-flow compatibility debt

- make internal orchestration the only primary path in product docs and UI
- retire or isolate the compatibility path if it is no longer materially used

## Risks

### Risk: overexposing an advanced feature

Making orchestration discoverable can increase shell complexity.

Mitigation: present orchestration as a first-class but bounded workspace, not as a sprawling parallel product.

### Risk: migration complexity

Removing callback requirements from the primary flow can affect backend contracts and tests.

Mitigation: treat compatibility as a scheduled migration layer rather than permanent architecture.

### Risk: split mental models

If documentation and product shape diverge again, users will lose trust in the system.

Mitigation: keep the PRD, design, and spec synchronized and reviewable.

## Acceptance Criteria

This PRD is acceptable only if it:

- clearly frames orchestration as a first-class product surface
- defines the root-shell discoverability requirement explicitly
- defines internal-first backtest launch as a product requirement
- treats long-term backward compatibility as migration debt, not target shape
- preserves templates as the authoring surface and backtests as an orchestration consumer
- defines measurable outcomes distinct from implementation details
