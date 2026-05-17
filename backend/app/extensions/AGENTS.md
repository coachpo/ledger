# BACKEND EXTENSIONS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file covers bundled backend extension infrastructure.

## OVERVIEW
`app/extensions/` owns first-party extension registration, private registrar wiring, and extension-owned composition roots. The current bundled extension is `signaldeck.finance`, which owns preserved finance `/api/v1` routers, finance provider factories, runtime tool specs/executors, and report-backed memory hooks.

Future upgrade work must preserve the boundary between generic extension infrastructure in this folder and finance-owned behavior in `signaldeck_finance/`. Move behavior across that seam only when the shared platform contract is explicit and the registries, docs, and tests move with it.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

## CHILD DOCS
- `signaldeck_finance/AGENTS.md` — bundled `signaldeck.finance` ownership, route registrations, provider factories, tool specs, and report-backed memory hooks

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Bundled registry | `registry.py` | extension identity, initial enabled seed, and private registrar references |
| Extension package exports | `__init__.py` | bundled extension registry exports |
| Finance extension | `signaldeck_finance/AGENTS.md` | current first-party finance workspace extension |
| Service state/filtering | `../services/extension_service.py` | persisted slim state plus ToolCatalog/runtime registry filtering |
| API state | `../api/extensions.py` | `/api/extensions` list/toggle route family |
| DB state | `../models/extension.py`, `../db/upgrades.py` | `extension_states` persistence and default bundled-extension seeding |

## CONVENTIONS
- Extension definitions are private registry wiring; behavior is supplied through explicit registrars and service-layer filtering.
- `ExtensionService` is the authority for persisted state, `/api/extensions` toggles, and enabled ToolCatalog/runtime views.
- Public extension state stays slim: `key`, `label`, and `enabled` only. Keep registrar paths, owner keys, scaffold details, and plugin-manifest-style fields private.

## ANTI-PATTERNS
- Do not import extension-owned dependencies directly from generic platform services when `ExtensionService` should filter by enabled state.
- Do not add plugin marketplace, install, or remove semantics to bundled extension state in phase 1.
- Do not expose registry/scaffold metadata through `/api/extensions`, `/api/tools`, OpenAPI, run dependency records, or docs.
- Do not migrate finance-owned routing, provider, or runtime-tool behavior into generic extension infrastructure without first defining the shared platform contract.
