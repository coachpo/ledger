# Ledger Agent Platform PRD

> Status: Live package-first platform product reference as of 2026-05-08.

## Summary

Ledger ships a UI-driven, package-first agent platform beside the preserved portfolio, template, and report product areas. Users author Workflow Packages, bind them to global Model Connections, reference global read-only Tools, launch package runs, and inspect persisted Runs from the browser.

## Current Product Surfaces

- Workflow Packages: `ledger.workflowPackage/v1` YAML authoring, package-local agents, output schemas, capability profiles, private MCP configs, workflow graphs, validation, preflight, import, export, and launch flows.
- Model Connections: global OpenAI-family provider endpoints, encrypted secrets, secret-safe reads, live binding resolution by key, and connection tests.
- Tools: global read-only server-declared metadata from `/api/tools`, referenced by package-local capability profiles through `toolKeys`.
- Runs: global list/detail, package provenance, per-step output, final output, token/timing totals, trace ids, reruns, and step replays.
- Preserved product areas: portfolios, templates, and reports remain live beside the platform.

## Goals
- Make package-local platform resources authorable without code changes.
- Keep Model Connections global so provider credentials remain live bindings outside package exports.
- Keep Tools global and read-only so packages reference server-declared capabilities without storing tool definitions.
- Persist Runs with enough package provenance and detail for review and replay without requiring a live tracing product.

## Non-Goals

- Multi-tenant auth or public deployment hardening.
- Mid-run human approval loops.
- Compatibility aliases or redirects for `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, or `/workflows*`.
- TradingAgents-specific platform features. TradingAgents is ordinary smoke/demo package data.
- Raw HTTP model-provider integration paths in application code.

## Success Criteria

- A user can create a Workflow Package from YAML, validate it, preflight it, export it without secrets or database ids, and launch it.
- A user can create a global Model Connection and use its stable key as a live package binding.
- A user can inspect read-only global Tools and package run provenance.
- Secret-bearing resources never expose raw secrets in package exports, read payloads, run provenance, or error messages.
