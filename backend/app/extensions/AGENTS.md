# BACKEND EXTENSIONS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file covers bundled backend extension infrastructure.

## OVERVIEW
`app/extensions/` owns first-party extension registration, contribution metadata, and extension-owned composition roots. The current bundled extension is `signaldeck.finance`, which contributes preserved finance `/api/v1` routers, finance provider factories, runtime tool specs/executors, docs ownership metadata, and report-backed memory hooks.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

## CHILD DOCS
- `signaldeck_finance/AGENTS.md` — bundled `signaldeck.finance` ownership, route registrations, provider factories, tool specs, and report-backed memory hooks

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Bundled registry | `registry.py` | extension definitions, contribution categories, registrar references, and default state |
| Extension package exports | `__init__.py` | public extension registry exports |
| Finance extension | `signaldeck_finance/AGENTS.md` | current first-party finance workspace extension |
| Service state/filtering | `../services/extension_service.py` | persisted state, contribution reads, ToolCatalog/runtime registry filtering |
| API state | `../api/extensions.py` | `/api/extensions` list/toggle route family |
| DB state | `../models/extension.py`, `../db/upgrades.py` | `extension_states` persistence and default bundled-extension seeding |

## CONVENTIONS
- Extension definitions are registry metadata; behavior is supplied through explicit registrars and service-layer filtering.
- `ExtensionService` is the authority for persisted state and enabled contribution views.
- New contribution categories must update registry types, schemas, service filtering, API projections, frontend contracts, and tests together.

## ANTI-PATTERNS
- Do not import extension-owned dependencies directly from generic platform services when `ExtensionService` should filter by enabled state.
- Do not add plugin marketplace, install, or remove semantics to bundled extension state in phase 1.
