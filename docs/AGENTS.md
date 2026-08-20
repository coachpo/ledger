# Docs Guide

## Overview

Docs describe the implemented SignalDeck product, current architecture, data model, development workflow, and static extension contract. Canonical product and engineering rules are written in Chinese; this local guide keeps the existing English agent-facing wording while pointing to the selected canonical paths.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| Documentation index | `README.md` | Canonical document map and authority boundaries. |
| Product behavior | `产品说明.md` | Current scope, routes, APIs, operations, requirements, and acceptance. |
| Architecture | `架构说明.md` | Current components, boundaries, data flow, deployment model, and exceptions. |
| Development rules | `开发规范.md` | Project-specific implementation rules and links to shared validation. |
| Persistence contract | `data-model.md` | Tables, snapshots, schedule/run provenance, and rebuild strategy. |
| Extension guidance | `writing-extensions.md` | Static backend extension writing contract. |
| Active handover | `handover-deps-follow-up.md` | Dependency follow-up state, unlock conditions, and validation commands. |

## Conventions

- Document implemented behavior, not roadmap or deprecated surfaces.
- Keep product scope aligned with [`../STATUS.md`](../STATUS.md) and [`产品说明.md`](产品说明.md): trusted single-user, local/intranet development use, no marketplace, no runtime-v2, and no auth/RBAC product surface beyond the optional API token.
- Update the root [`README.md`](../README.md) and [`README.md`](README.md) when adding or removing durable docs or changing the document map.
- Handover docs must include current status, unlock conditions, and concrete validation commands.
- Use relative links from docs to code or sibling docs.

## Anti-Patterns

- Do not preserve compatibility docs for removed product shapes.
- Do not describe secret values, provider credentials, or production deployment shortcuts as visible product behavior.
- Do not let docs imply the root local/demo Docker image is a supported production artifact.
- Do not introduce a second canonical document path or recreate unselected bilingual variants without an explicit migration decision.
