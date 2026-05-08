# Ledger Agent Platform UI Spec

> Status: Live package-first UI reference as of 2026-05-08.

## Shell And Navigation

The sidebar exposes Workflow Packages, Model Connections, and Runs beside the preserved Dashboard, Portfolios, Templates, and Reports routes. `frontend/src/routes.ts` is the route source of truth and `frontend/src/components/layout.tsx` owns shell labels and breadcrumbs.

## Shared Page Patterns

- List pages provide create actions, status/version badges, and archive/delete actions where supported.
- Editors use forms and hooks, not direct fetch calls from view code.
- Validation appears as inline alerts, field feedback, toasts, and backend error-envelope messages.
- Full-height authoring pages preserve the layout pattern used by template and package editors.

## Platform Pages

- Workflow Packages: package list, package editor tabs, package-local agents, output schemas, capability profiles, private MCP configs, workflow graph authoring, preflight, launch, import, and no-secret export flows.
- Model Connections: provider/base URL/model/key editor, global live binding selection, secret-safe edit flow, and connection test feedback.
- Runs: list, detail, package provenance, per-step cards, final output, trace ids, reruns, and step replay actions.
- Tools: read-only global metadata shown where package capability profiles select server-declared tool keys.

## Removed Route Notes

The UI no longer registers `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, or `/workflows*`. Those paths render not-found behavior instead of compatibility redirects.
