# FRONTEND TEMPLATE PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/templates/` contains the template inventory route and the full-height template editor. This is the frontend entry point for template CRUD, live compile preview, placeholder browsing, runtime inputs, markdown formatting, and template-driven report generation.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Template inventory | `list.tsx` | list/delete/open flows |
| Template editor | `editor.tsx` | save/update, debounced preview, placeholder insertion, runtime inputs, generate report |
| Editor support components | `../../components/templates/AGENTS.md` | placeholder browser and inline runtime-input controls |
| Shared generation dialog | `../../components/forms/generate-report-dialog.tsx` | saved-template report generation with runtime inputs |
| Template hooks | `../../hooks/use-templates.ts` | list/detail CRUD, inline compile, placeholder tree |
| Report generation shortcut | `../../hooks/use-reports.ts` | create compiled report from saved template |
| Runtime-input helpers | `../../lib/runtime-inputs.ts` | row helpers and trimmed input-map conversion |
| Markdown formatting | `../../lib/markdown-format.ts` | editor format action |

## CONVENTIONS
- The editor keeps local `name`/`content` state, builds `runtimeInputs` from editable rows, and debounces both content and runtime-input changes by 500 ms; the hook does not own that timing.
- The placeholder browser mixes static reference groups with live backend data from `GET /templates/placeholders`; click-to-insert always writes `{{path}}` into the textarea.
- Report generation is only enabled for saved templates because the backend compile endpoint requires a stored template id; the dialog is locked to the current template when launched from the editor.
- `buildRuntimeInputs()` trims blank keys/values before preview compile or report generation, so incomplete rows stay UI-only until filled.
- Dynamic report selectors such as `reports.latest("TICKER")`, `reports[index]`, and `reports.by_tag("tag").latest` are backend-authored behavior; valid no-match selectors render empty output, while malformed selectors render explicit sentinel text.

## ANTI-PATTERNS
- Do not save on every keystroke; preview and persistence are intentionally separate flows.
- Do not hard-code the live placeholder tree in the UI beyond the documented static guidance groups.
- Do not fork runtime-input row behavior between the editor and generation dialog; both flows rely on the same `runtime-inputs.ts` helpers.
- Do not move report-generation logic out of the editor/list routes into generic shared components; it depends on template-route state and navigation.
