# FRONTEND RETIRED GLOBAL AUTHORING PAGES GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This tree is archive-only cutover context.

## OVERVIEW
`retired/global-authoring/src/pages/` preserves removed standalone authoring pages for agents, capabilities, MCP servers, output schemas, and workflows. The live app does not route these pages; Workflow Packages, global Model Connections, global Tools, and Runs own the current package-first surfaces.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

## STRUCTURE
```text
retired/global-authoring/src/pages/
├── agents/          # retired standalone agent inventory/editor
├── capabilities/    # retired capability inventory/editor
├── mcp-servers/     # retired MCP inventory/editor
├── output-schemas/  # retired output schema editor
└── workflows/       # retired workflow inventory/editor/launch
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Archived standalone agent authoring | `agents/` | cutover context only; live authoring moved inside Workflow Packages |
| Archived capability, MCP, schema, and workflow UIs | `capabilities/`, `mcp-servers/`, `output-schemas/`, `workflows/` | consult only for removed behavior, not live ownership |

## CONVENTIONS
- Treat this tree as archive-only reference material.
- Read it only to understand removed flows, old tests, or cutover history.
- When upgrade design touches an archived concept, decide whether it belongs in Workflow Packages, global Model Connections, global Tools, Runs, or an extension-owned surface before reviving anything.

## ANTI-PATTERNS
- Do not route, import, or document these pages as live surfaces.
- Do not resurrect standalone global authoring UI from this tree without a new product decision.
- Do not copy archive-specific hooks, payload shapes, or assumptions into live package-first code without revalidating contracts.
