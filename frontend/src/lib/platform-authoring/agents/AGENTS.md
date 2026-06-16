# FRONTEND PLATFORM AUTHORING AGENTS LIB GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, `/frontend/src/lib/AGENTS.md`, and `/frontend/src/lib/platform-authoring/AGENTS.md`.

## OVERVIEW
`agents/` owns package-local agent manifest parsing, formatting, outline extraction, and diagnostics for the Workflow Package editor. These helpers describe agents inside package artifacts only; they are not global agent authoring routes.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Agent manifest helpers | `manifest.ts` | parse/format/outline/diagnostic helpers for package-local agents |
| Coverage | `manifest.test.ts` | manifest round-trips and unsupported YAML behavior |

## CONVENTIONS
- Keep package-local agent refs and diagnostics aligned with backend package manifest parser behavior.
- Reject unsupported YAML features consistently with package/workflow manifest helpers.
- Formatting helpers should preserve user-authored intent while emitting backend-compatible package artifacts.
- Agent prompts, model bindings, and tool grants stay package-private draft data until saved through package APIs.

## ANTI-PATTERNS
- Do not reintroduce standalone `/agents*` frontend or API contracts from this folder.
- Do not fetch model connections, tools, or package data here; callers pass current context in.
- Do not add compatibility paths for retired global agent ids.

## VALIDATION
```bash
cd frontend
pnpm test:run src/lib/platform-authoring/agents/manifest.test.ts
```

## NOTES
- This folder stays intentionally small; expand this guide only when package-local agent authoring gains more helpers.
