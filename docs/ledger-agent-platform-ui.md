# Ledger Agent Platform — UI Spec

## 1. Scope
Current shipped UI summary for Ledger's agent-platform routes. This file describes the routed experience that exists in the repository today.

## 2. Shell and navigation
- The main sidebar exposes Agents, Skills, MCP Servers, Output Schemas, Workflows, and Runs alongside the preserved portfolio, template, and report routes.
- `frontend/src/routes.ts` is the route source of truth and `frontend/src/components/layout.tsx` owns sidebar labels and breadcrumbs.
- The template editor remains a special full-height route inside the main shell.

## 3. Shared page patterns
- Platform list screens are route-backed pages with create actions, version/status badges, and lifecycle actions such as archive where supported.
- Editors stay form-driven and hook-backed instead of calling APIs directly from view code.
- Success and failure feedback is surfaced with toasts, inline alerts, and route-level empty/loading states.

## 4. Output schema editor
- The shipped editor exposes Builder, JSON Schema, and Preview tabs.
- Builder and raw JSON views stay synchronized through one shared schema shape.
- Validation errors are surfaced before save so the UI does not need to guess at backend failures.

## 5. Workflow authoring
- The workflow editor is a routed wizard with Input, Steps, Output, and Review sections.
- Step authoring uses explicit per-field wiring from workflow input or prior-step slots.
- Saving creates a new immutable workflow version and Run now launches the current workflow through the platform API.

## 6. Run monitor
- The runs list shows recent runs with workflow identity, status, timing, and cost summaries.
- The run detail page renders per-step accordions, per-agent cards, final output, and trace-linkage details from persisted `traceId` and `traceSpanId` data when present.
- Failure states are shown inline rather than depending on a legacy runtime console.

## 7. Stock-analysis reference flow
- The shipped browser flow provisions platform resources through the current routes and launches runs from the workflow UI.
- The reference flow is documented as a normal platform workflow, not as a separate runtime or hidden compatibility surface.

## 8. Out-of-scope surfaces
- This UI spec does not describe retired Studio, Tryout, orchestration, or runtime-v2 routes.
- This UI spec does not assume older placeholder pages or unused route artifacts that are not wired into `frontend/src/routes.ts`.
