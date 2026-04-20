# Ledger Agent Platform — PRD

## 1. Summary
A stateless, UI-driven agent platform that replaces the current orchestration (roles / characters / FrozenExecutionSnapshot / custom runtime). Users create **agents** and compose them into **workflows** entirely from the browser, without code changes. First use case: stock analysis yielding a typed `TradingDecision` (buy / sell / hold).

## 2. Problem
The existing orchestration stack mixes session-heavy abstractions (roles, characters, persona projection, frozen snapshots, custom execution adapters) with a thin LangGraph-like runtime. It is complex to extend, hard to reason about, and requires code changes to add or re-wire an agent. Output contracts are untyped. There is no first-class MCP or skill reuse.

## 3. Vision
Agents are stateless functions: `(input, config) → typed output`. Each run is a pure invocation with a typed schema, tool/skill/MCP access, and a trace. Workflows are explicit, versioned, inspectable DAGs of steps assembled in the UI. Everything else — session state, persona projection, custom adapters — is removed.

## 4. Users
- **Builder** — assembles agents and workflows, authors prompts and output schemas.
- **Operator** — triggers runs, reviews outputs, inspects traces.
- **Developer** — adds new skills, MCP integrations, and primitives to the platform.

## 5. Goals (measurable)
- **G1** Stateless runtime: zero persisted agent session state between runs.
- **G2** 100% of agent and workflow authoring is available in the UI (no code edits required to add, edit, or compose).
- **G3** Agents, skills, MCP servers, and output schemas are reusable first-class entities with CRUD + versioning.
- **G4** Every run produces a typed output validated against a runtime Pydantic model and persists trace-linkage metadata when available.
- **G5** Workflows support N parallel agents per step with freestyle input wiring from prior-step slots.
- **G6** Stock-analysis reference workflow runs end-to-end and returns a `TradingDecision` within the configured budget.

## 6. Non-goals
- Multi-tenant auth / access control.
- Mid-run human-in-the-loop approvals.
- Code-level workflow authoring.
- Cross-run memory or agent sessions.
- Loops and conditional branches in workflows (v1).
- Per-step model overrides.
- Backward compatibility with the orchestration v1 / v2 stack.

## 7. Success metrics
- Time to add a new agent end-to-end (prompt + schema + skills + tested run): **< 10 min** with no code edits.
- Time to assemble and run a new workflow from existing agents: **< 5 min**.
- Stock-analysis reference workflow: reproducible run, cost within budget cap, and trace linkage visible from persisted run data.

## 8. Scope (v1)
- Agent CRUD, versioning, test panel.
- Skill, MCP server, and output-schema CRUD and registry.
- Workflow wizard: input → steps (N parallel agents) → final output, with freestyle wiring.
- Run trigger, run history, run detail with per-step drill-down.
- Deletion of all orchestration v1 / v2 code paths.

## 9. Reference use case: stock analysis
Input: `{ticker, horizon_days}`.
Step 1 (parallel): `financials_analyst`, `news_analyst`, `market_analyst`, `industry_analyst`, `economy_analyst`, `price_analyst`, `position_reader`, `history_reader`.
Step 2: `decision_synthesizer` wires all eight slots → `TradingDecision {action, confidence, rationale, price_targets, risks}`.

## 10. Risks
- **R1** Runtime integration drift — mitigation: keep the execution boundary thin and preserve typed run persistence independent of any single internal implementation detail.
- **R2** Output-schema flexibility vs. Pydantic compatibility — mitigation: Hybrid form-builder + JSON Schema with validation; reject unsupported shapes.
- **R3** Cost runaway on multi-agent workflows — mitigation: per-agent `max_tool_rounds` and `budget_usd`, per-run aggregate cap.
- **R4** Trace-linkage drift — mitigation: store minimal trace pointers plus outputs in the local `runs` table so run review does not depend on a single external tracing surface.

## 11. Open questions (resolved)
- OQ-1 Schema editor → **Hybrid form-builder + JSON Schema with shared registry**.
- OQ-2 Parallel agents per step → **yes (v1)**.
- OQ-3 Loops / conditionals → **no (v1)**.
- OQ-4 Per-step model override → **no (inherit from agent config)**.

## 12. Related documents
- `ledger-agent-platform-spec.md` — functional and non-functional requirements.
- `ledger-agent-platform-design.md` — technical architecture and data model.
- `ledger-agent-platform-ui.md` — UI spec with shadcn component mapping.
- `ledger-agent-platform-migration.md` — deletion and migration plan.
