# Ledger Agent Platform UI Spec

> Status: Live UI reference as of 2026-05-04 (`b4ac445`).

## Shell And Navigation

The sidebar exposes Agents, Capabilities, MCP Servers, Model Connections, Output Schemas, Workflows, and Runs beside the preserved Dashboard, Portfolios, Templates, and Reports routes. `frontend/src/routes.ts` is the route source of truth and `frontend/src/components/layout.tsx` owns shell labels and breadcrumbs.

## Shared Page Patterns

- List pages provide create actions, status/version badges, and archive/delete actions where supported.
- Editors use forms and hooks, not direct fetch calls from view code.
- Validation appears as inline alerts, field feedback, toasts, and backend error-envelope messages.
- Full-height authoring pages preserve the layout pattern used by template and workflow editors.

## Platform Pages

- Agents: YAML manifest editor, duplicate/archive actions, run-launch flow.
- Capabilities: `toolGrants` authoring and activation state.
- MCP servers: config editor and connection test feedback.
- Model connections: provider/base URL/model/key editor, secret-safe edit flow, and connection test feedback.
- Output schemas: builder, JSON schema, and preview tabs.
- Workflows: YAML manifest editor, launch metadata, Run now, and version-aware launch flow.
- Runs: list, detail, per-step cards, final output, trace ids, reruns, and step replay actions.
