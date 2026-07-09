# Docs Guide

## Overview

Docs describe the current implemented SignalDeck product, data model, development workflow, and extension-writing contract.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| Product behavior | `product.md` | Current routes, APIs, operations, validation. |
| Persistence contract | `data-model.md` | Tables, snapshots, schedule/run provenance, rebuild strategy. |
| Toolchain and holds | `development.md` | Python/Node/uv/pnpm versions, FastAPI cap, validation. |
| Extension guidance | `writing-extensions.md` | Static backend extension writing contract. |
| Active handover | `handover-deps-follow-up.md` | Temporary dependency follow-up state only. |

## Conventions

- Document implemented behavior, not roadmap or deprecated surfaces.
- Keep product scope aligned with the root guide: trusted single-user, no marketplace, no runtime-v2, no auth/RBAC product surface beyond optional API token.
- Update `README.md` when adding or removing durable docs.
- Handover docs must include current status, unlock conditions, and concrete validation commands.
- Delete or fold stale docs once their follow-up work is complete.
- Use relative links from docs to code or sibling docs.

## Anti-Patterns

- Do not preserve compatibility docs for removed product shapes.
- Do not describe secret values, provider credentials, or production deployment shortcuts as visible product behavior.
- Do not let docs imply the root local/demo Docker image is a supported production artifact.
