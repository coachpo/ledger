# Ledger Agent Platform PRD

> Status: Live agent-platform product reference as of 2026-05-04 (`b4ac445`).

## Summary

Ledger ships a stateless, UI-driven agent platform beside the preserved portfolio, template, and report product areas. Users author YAML agents and workflows, grant tools through capabilities, connect MCP servers and model providers, define output schemas, launch workflows, and inspect persisted runs from the browser.

## Current Product Surfaces

- Agents: YAML manifest list, create/edit-as-version, archive, duplicate, and run-launch flows.
- Capabilities: canonical tool-key resources with `toolKeys` and read-only resolved `tools` metadata backed by the server-declared tool catalog.
- MCP servers: saved server configs, connection tests, exact pinned versions, frozen tool snapshots, and security boundaries.
- Model connections: saved OpenAI-family provider endpoints, encrypted secrets, secret-safe reads, and connection tests.
- Output schemas: schema composer, JSON schema editing, preview, validation, and runtime compilation.
- Workflows: YAML workflow manifests, versioning, launch metadata, launches, and run creation.
- Runs: list/detail, status, per-step output, final output, cost/timing totals, trace ids, reruns, and step replays.

## Goals

- Make platform resources authorable without code changes.
- Keep capabilities, model connections, MCP servers, and output schemas reusable across agents/workflows.
- Persist runs with enough detail for review and replay without requiring a live tracing product.
## Non-Goals

- Multi-tenant auth or public deployment hardening.
- Mid-run human approval loops.
- Retired Studio, Tryout, runtime-v2, orchestration, simulation, backtest, `/api/skills`, or `/skills*` compatibility.
- Raw HTTP model-provider integration paths in application code.

## Success Criteria

- A user can create a model connection, capability, output schema, agent, and workflow from the browser.
- A workflow launch creates a persisted run that can be inspected from the run monitor.
- Secret-bearing resources never expose raw secrets in read payloads or error messages.
- Retired skill terminology is absent from current-product routes and manifest guidance except when explicitly called out as rejected legacy input.
