# Backend Extensions Guide

## Overview

Extensions are private Python wiring for bundled product capabilities, not a dynamic plugin system.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| Extension contract | `contract.py` | Static `Extension` dataclass fields. |
| Installed extensions | `registry.py` | Import-time uniqueness checks and provider merge. |
| Finance extension | `signaldeck_finance/` | API plus runtime tools. |
| Digital Oracle extension | `signaldeck_digital_oracle/` | Tool-only runtime extension. |
| Tool catalog types | `../agents/tool_catalog/` | Server-declared metadata shape. |
| Runtime registry | `../agents/runtime_tools/` | Runtime tool specs and dispatch. |

## Conventions

- Add capabilities by editing `INSTALLED_EXTENSIONS`; there is no filesystem/plugin discovery.
- Extension keys and canonical runtime tool keys are dotted lowercase names such as `signaldeck.finance`.
- OpenAI function names use the mechanical snake_case mapping from canonical tool keys.
- Each extension contributes only explicit API routers, tool declarations, runtime tool specs, provider factories, dependency surfaces, and package-private MCP ownership.
- `registry.py` must reject duplicate extension keys, server-declared tool keys, runtime spec keys, and package-private MCP tool keys at import time.
- Runtime access failures should use the project denial shape, including `agent_execution_access_denied`.

## Anti-Patterns

- Do not add user-installed plugins, marketplaces, or dynamic extension loading.
- Do not let extensions silently shadow another extension's tool keys.
- Do not expose package-private MCP config or runtime secrets through catalog metadata.
