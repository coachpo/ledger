# Workflow Packages UI Guide

## Overview

This route family owns Workflow Package list, import, authoring, validation, secret bindings, preflight, export, and launch flows.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| List route | `list.tsx` | Inventory shell and package launch/navigation actions. |
| Import route | `import-page.tsx` | YAML import and validation projection. |
| Editor route | `editor.tsx`, `editor-sections.tsx` | Package manifest authoring workspace. |
| Launch route | `launch.tsx` | Schema-backed inputs, JSON mode, preflight, run launch. |
| Shared editor data | `editor-sections.shared.ts` | Cross-section constants and helpers. |
| Tests | `*.test.tsx`, `*.test.ts` | Editor, import, preflight, launch, secret-binding contracts. |

## Conventions

- Workflow Packages are the only executable authoring root; do not introduce alternate agent workflow builders.
- Schema-backed form mode is canonical for launch inputs. JSON mode must validate/apply back before preflight or launch.
- Editor state should preserve package-local agents, output schemas, capability profiles, private MCP configs, HTTP operation nodes, and graph nodes.
- Diagnostics should focus the relevant editor field only when that field is still being edited.
- Secret Binding UI exposes key, presence, and timestamps only; values are write-only.
- Manifest import/export must omit raw secrets, DB ids, run history, and inline private MCP values.
- Use platform-authoring helpers for schema/value/resource-ref behavior; keep path token handling consistent with generated forms.
- Launch mutations invalidate package launch/preflight scopes and linked run views.

## Anti-Patterns

- Do not add `spec.skills`, YAML aliases/anchors, merge keys, unknown manifest fields, or raw database ids.
- Do not bypass preflight before launch.
- Do not store or echo private MCP `env`, `headers`, or `query` values in browser-visible state.
