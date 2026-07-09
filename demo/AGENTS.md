# Demo Workflow Package Guide

## Overview

Demo YAML files are canonical, grounded Workflow Package examples that double as readable product contracts.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| Finance advisory demo | `tradingagents_advisory_research.yaml` | Finance tools, reports, private MCP example. |
| Digital Oracle demo | `digital_oracle_researcher.yaml` | Tool-only oracle research workflow. |
| Import/runtime tests | `../backend/tests/` | Demo manifests are used as package contract fixtures. |

## Conventions

- Use `signaldeck.workflowPackage/v1` manifests only.
- Keep examples grounded in currently supported package fields: inputs, package-local agents, output schemas, capability profiles, private MCP configs, HTTP nodes, and workflow graphs.
- Reference Model Connections by stable global key and runtime tools by canonical owner-qualified key.
- Secret references use `${{ secrets.<key> }}` only in HTTP request fields.
- Do not include raw database ids, run ids, secret values, or machine-local endpoints.
- Demo manifests should be useful for import tests and smoke flows; keep names and descriptions operator-readable.
- Keep demo topology realistic: sequence, fanout, loop, HTTP, and synthesis examples should match compiler/preflight support.
- Demo YAML hashes may be locked in tests, so changing manifests can require expected hash updates.
- Treat descriptions as operator-facing copy, not marketing pages.

## Anti-Patterns

- Do not add examples for Studio, Tryout, runtime-v2, workflow memory, forks, portfolio accounting, broker execution, simulations, or backtests.
- Do not rely on YAML aliases, anchors, merge keys, unsupported tags, or duplicate keys.
