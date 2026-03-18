# Text Template Report Placeholder Plan

## Overview

This document plans the addition of a `reports` placeholder root to Ledger's text template system. Templates will be able to embed compiled report content and metadata, enabling master documents that compose multiple reports into a single output.

Report content is re-compiled at inclusion time — any `{{portfolios...}}` placeholders inside the report content are resolved against live data, and nested `{{reports...}}` references are followed recursively with cycle detection.

## Prerequisites

This plan depends on:
- The compiled reports feature described in `docs/archive/compiled-reports-design.md` (Report model, CRUD, compile endpoint).
- The existing placeholder system described in `docs/archive/text-template-system-with-placeholders.md`.
- The metric placeholders described in `docs/archive/text-template-placeholder-metrics-upgrade-plan.md`.

## Scope

- Add a new `reports` root namespace as a sibling to `portfolios`.
- Support report identification by unique report name.
- Support re-compilation of report content at inclusion time.
- Implement cycle detection to prevent infinite recursion.
- Preserve all existing placeholder paths and behavior.
- Keep compile responses as markdown-compatible strings.

## Contract Decisions

### Naming

- Use the existing snake_case placeholder contract style.
- Reports are addressed by their unique `name` field (e.g., `monthly_report_20260317_143052`).
- The `reports` root is a peer to `portfolios`, not nested under it.

### Re-Compilation Behavior

- When `{{reports.<name>.content}}` is resolved, the stored report content is re-compiled through the same placeholder engine.
- This means `{{portfolios...}}` placeholders inside the report content are resolved against current live data.
- `{{reports...}}` placeholders inside the report content are also resolved recursively.
- Cycle detection prevents infinite loops (see Cycle Detection section).

### Missing Report Behavior

- Unknown report names render an inline sentinel: `[Unknown report: <name>]`.
- This matches the existing `[Unknown portfolio: <slug>]` pattern.

## New Placeholder Contract

### Report Placeholders

- `reports` — renders a metadata list of all reports (names and created_at timestamps).
- `reports.<name>` — renders the metadata of a single report.
- `reports.<name>.content` — re-compiles and renders the full report content.
- `reports.<name>.name` — renders the report name as a plain string.
- `reports.<name>.created_at` — renders the report creation timestamp.

### Path Summary

| Path | Output |
|---|---|
| `{{reports}}` | Metadata list of all reports |
| `{{reports.<name>}}` | Single report metadata block |
| `{{reports.<name>.content}}` | Full re-compiled report content |
| `{{reports.<name>.name}}` | Report name string |
| `{{reports.<name>.created_at}}` | Report creation timestamp |

## Rendering Rules

### All Reports List

`{{reports}}` renders a bullet list of all reports with metadata:

```
- **monthly_report_20260317_143052** (2026-03-17T14:30:52Z)
- **q1_summary_20260315_091000** (2026-03-15T09:10:00Z)
```

If no reports exist: `*(no reports)*`

Reports are listed in reverse chronological order (newest first), matching the `ReportRepository.list_all()` ordering.

### Single Report Metadata

`{{reports.<name>}}` renders:

```
**monthly_report_20260317_143052** (2026-03-17T14:30:52Z)
```

### Report Content

`{{reports.<name>.content}}` takes the stored `report.content` string and passes it through the compiler's `compile()` pipeline. The output replaces the placeholder with the fully resolved content.

### Scalar Fields

- `{{reports.<name>.name}}` → `monthly_report_20260317_143052`
- `{{reports.<name>.created_at}}` → `2026-03-17T14:30:52Z`

Both use the existing `_format_value()` method.

## Cycle Detection

### Problem

Reports can be edited post-compile. A user could insert `{{reports.report_b.content}}` into Report A, and `{{reports.report_a.content}}` into Report B. Compiling a template that includes either would loop infinitely.

### Solution

Track a set of report names currently being resolved in the compile call. Before re-compiling a report's content, check if its name is already in the set. If so, render a sentinel instead of recursing.

### Implementation

- Add a `_report_resolve_stack: set[str]` instance variable on `TemplateCompilerService`, initialized to an empty set at the start of each `compile()` call (alongside the existing `_quote_cache` reset).
- Before re-compiling report content in `_resolve_report_content()`:
  1. Check if `report.name` is in `_report_resolve_stack`.
  2. If yes → return `[Circular report reference: <name>]`.
  3. If no → add `report.name` to the stack, re-compile, then remove it from the stack.
- This is a standard DFS cycle detection pattern. It handles:
  - Direct self-reference: Report A includes `{{reports.report_a.content}}`.
  - Indirect cycles: A → B → A.
  - Deep chains: A → B → C → D (no cycle, all resolve normally).
  - Diamond patterns: A → B, A → C, B → D, C → D (D is compiled twice but no cycle).

### Sentinel

```
[Circular report reference: monthly_report_20260317_143052]
```

This is visible in the compiled output so the user can identify and fix the cycle.

## Backend Changes

### Template Compiler Service

#### New Dependencies

- `TemplateCompilerService` needs access to `ReportRepository` to resolve report names.
- Add `ReportRepository` construction in `__init__`, using the existing `session`.

#### New Instance State

- `_report_resolve_stack: set[str]` — reset to empty set at the start of each `compile()` call.

#### Path Dispatch Integration

The compiler's `_resolve()` method currently checks `parts[0] != "portfolios"` and returns `[Unknown root: ...]` for anything else. This changes to:

```python
def _resolve(self, path: str) -> str:
    parts = [p.strip() for p in path.split(".")]
    if not parts:
        return "[Unknown root: ]"

    root = parts[0]

    if root == "portfolios":
        return self._resolve_portfolios(parts)

    if root == "reports":
        return self._resolve_reports(parts)

    return f"[Unknown root: {root}]"
```

The existing portfolio resolution logic moves into `_resolve_portfolios(parts)` (a rename/extract of the current code after the root check).

#### New Report Resolution Methods

```python
_REPORT_SCALAR_FIELDS = frozenset({"name", "created_at"})

def _resolve_reports(self, parts: list[str]) -> str:
    """Dispatch for the reports root."""
    if len(parts) == 1:
        return self._render_all_reports()

    name = parts[1]
    report = self.report_repo.get_by_name(name)
    if report is None:
        return f"[Unknown report: {name}]"

    if len(parts) == 2:
        return self._render_report_metadata(report)

    field = parts[2]

    if field == "content":
        return self._resolve_report_content(report)

    if field in _REPORT_SCALAR_FIELDS:
        return self._format_value(getattr(report, field, None))

    return f"[Unknown report field: {field}]"

def _render_all_reports(self) -> str:
    """Render metadata list of all reports."""
    reports = self.report_repo.list_all()
    if not reports:
        return "*(no reports)*"
    lines: list[str] = []
    for report in reports:
        lines.append(f"- {self._render_report_metadata(report)}")
    return "\n".join(lines)

def _render_report_metadata(self, report: Report) -> str:
    """Render a single report's metadata line."""
    created = self._format_value(report.created_at)
    return f"**{report.name}** ({created})"

def _resolve_report_content(self, report: Report) -> str:
    """Re-compile report content with cycle detection."""
    if report.name in self._report_resolve_stack:
        return f"[Circular report reference: {report.name}]"

    self._report_resolve_stack.add(report.name)
    try:
        # Re-compile through the same placeholder engine.
        # This resolves portfolios.*, reports.*, etc. inside the report content.
        compiled = _PLACEHOLDER_RE.sub(
            lambda match: self._resolve(match.group(1).strip()),
            report.content,
        )
        return compiled
    finally:
        self._report_resolve_stack.discard(report.name)
```

Note: `_resolve_report_content` does NOT call `self.compile()` because `compile()` resets `_quote_cache` and `_report_resolve_stack`. Instead, it directly uses `_PLACEHOLDER_RE.sub()` with `self._resolve()`, which preserves the compile-call state.

#### Refactoring _resolve()

The current `_resolve()` method handles both root detection and portfolio dispatch inline. Extract the portfolio logic into `_resolve_portfolios()`:

```python
def _resolve(self, path: str) -> str:
    parts = [p.strip() for p in path.split(".")]
    if not parts:
        return "[Unknown root: ]"

    root = parts[0]

    if root == "portfolios":
        return self._resolve_portfolios(parts)

    if root == "reports":
        return self._resolve_reports(parts)

    return f"[Unknown root: {root}]"

def _resolve_portfolios(self, parts: list[str]) -> str:
    """All existing portfolio resolution logic, unchanged."""
    if len(parts) == 1:
        return self._render_all_portfolios()

    slug = parts[1]
    portfolio = self.portfolio_repo.get_by_slug(slug)
    if portfolio is None:
        return f"[Unknown portfolio: {slug}]"

    if len(parts) == 2:
        return self._render_portfolio_summary(portfolio)

    field = parts[2]

    if field in _PORTFOLIO_SCALAR_FIELDS:
        return self._get_portfolio_scalar(portfolio, field)

    if field in _PORTFOLIO_METRIC_FIELDS:
        return self._resolve_portfolio_metric(portfolio, field)

    if field == "balance":
        return self._resolve_balance(portfolio, parts[3:])

    if field == "positions":
        return self._resolve_positions(portfolio, parts[3:])

    return f"[Unknown field: {field}]"
```

This is a pure extract-method refactoring — no behavior change for portfolio placeholders.

### Placeholder Tree

The `get_placeholder_tree()` method currently returns `{"portfolios": [...]}`. Extend it to also return report names:

```python
def get_placeholder_tree(self) -> dict[str, list[dict[str, object]]]:
    portfolios = self.portfolio_repo.list_all()
    portfolio_result: list[dict[str, object]] = []
    for portfolio in portfolios:
        positions = self.position_repo.list_for_portfolio(portfolio.id)
        portfolio_result.append(
            {
                "slug": portfolio.slug,
                "name": portfolio.name,
                "base_currency": portfolio.base_currency,
                "positions": [{"symbol": p.symbol, "name": p.name} for p in positions],
            }
        )

    reports = self.report_repo.list_all()
    report_result: list[dict[str, object]] = []
    for report in reports:
        report_result.append(
            {
                "name": report.name,
                "created_at": report.created_at,
            }
        )

    return {"portfolios": portfolio_result, "reports": report_result}
```

### Schemas

#### PlaceholderTree Backend Schema

Update `backend/app/schemas/text_template.py`:

```python
class PlaceholderReportRead(CamelModel):
    name: str
    created_at: datetime

class PlaceholderTreeRead(CamelModel):
    portfolios: list[PlaceholderPortfolioRead]
    reports: list[PlaceholderReportRead]
```

## Frontend Changes

### Types

Update `frontend/src/lib/types/text-template.ts`:

```typescript
export interface PlaceholderReport {
  name: string;
  createdAt: string;
}

export interface PlaceholderTree {
  portfolios: PlaceholderPortfolio[];
  reports: PlaceholderReport[];
}
```

### Placeholder Browser

The editor's placeholder reference panel in `frontend/src/pages/templates/editor.tsx` needs two additions:

#### 1. New Hardcoded Report Group

Add a new `PlaceholderGroup` for the report schema-level fields alongside the existing Portfolio, Balance, and Position groups:

```
Report Placeholders:
- reports                           → List all reports
- reports.<name>                    → Report metadata
- reports.<name>.content            → Full report content (re-compiled)
- reports.<name>.name               → Report name
- reports.<name>.created_at         → Report creation date
```

#### 2. Dynamic Report Shortcuts

In the dynamic section that currently renders per-portfolio concrete slug/symbol shortcuts, add a new section for concrete report names from the placeholder tree:

For each report in `tree.reports`, render clickable shortcuts:
- `reports.<actual_name>`
- `reports.<actual_name>.content`

This lets users click to insert a real report reference without typing the name.

## Test Plan

### Backend API Coverage

Extend `backend/tests/test_api.py` with template compile assertions for all new report placeholders.

#### Setup

- Create a report via the compile endpoint before running report placeholder tests.
- The report will contain compiled content from a template with known portfolio data.

#### Assertions

- `{{reports}}` renders a bullet list with the created report's metadata.
- `{{reports.<name>}}` renders the report's metadata line.
- `{{reports.<name>.content}}` re-compiles and renders the report content with live portfolio data resolved.
- `{{reports.<name>.name}}` renders the report name string.
- `{{reports.<name>.created_at}}` renders the creation timestamp.
- `{{reports.nonexistent_report}}` renders `[Unknown report: nonexistent_report]`.
- `{{reports.<name>.unknown_field}}` renders `[Unknown report field: unknown_field]`.

#### Cycle Detection Tests

- Create Report A with content `{{reports.<report_b_name>.content}}`.
- Create Report B with content `{{reports.<report_a_name>.content}}`.
- Compile a template with `{{reports.<report_a_name>.content}}`.
- Assert the output contains `[Circular report reference: <report_a_name>]` or `[Circular report reference: <report_b_name>]` (whichever closes the cycle).

- Create Report C with content `{{reports.<report_c_name>.content}}` (self-reference).
- Compile a template with `{{reports.<report_c_name>.content}}`.
- Assert the output contains `[Circular report reference: <report_c_name>]`.

#### Re-Compilation Tests

- Create a report from a template that contains `{{portfolios.<slug>.name}}`.
- Edit the report content to add another `{{portfolios.<slug>.total_value}}` placeholder.
- Compile a template with `{{reports.<name>.content}}`.
- Assert both placeholders in the report content are resolved against live data.

#### Placeholder Tree Tests

- Assert `GET /templates/placeholders` returns a `reports` array with the created report's name and created_at.

#### Regression

- All existing portfolio placeholder tests must pass unchanged.
- The `_resolve_portfolios()` extract-method refactoring must not change any existing behavior.

### Frontend

- Verify the placeholder browser shows the new Report group with schema-level entries.
- Verify the dynamic section shows concrete report name shortcuts.
- Verify click-to-insert works for report placeholders.

## File Touchpoints

### Backend (modified files)

- `backend/app/services/template_compiler_service.py` — new `reports` root dispatch, `_resolve_reports()`, `_resolve_report_content()` with cycle detection, `_render_report_metadata()`, `_render_all_reports()`, `_report_resolve_stack`, `ReportRepository` import, `_resolve_portfolios()` extract, updated `get_placeholder_tree()`
- `backend/app/schemas/text_template.py` — new `PlaceholderReportRead` schema, updated `PlaceholderTreeRead`
- `backend/tests/test_api.py` — report placeholder compile tests, cycle detection tests, re-compilation tests, placeholder tree tests

### Frontend (modified files)

- `frontend/src/lib/types/text-template.ts` — new `PlaceholderReport` interface, updated `PlaceholderTree`
- `frontend/src/pages/templates/editor.tsx` — new Report `PlaceholderGroup`, dynamic report name shortcuts

## Risks

- Re-compilation of report content means compile time grows with the size and number of embedded reports. For a master document embedding many large reports, this could be slow. Acceptable for v1 given the expected report count.
- Cycle detection uses an in-memory set scoped to a single `compile()` call. This is safe for single-threaded request handling but would need review if compilation ever becomes async or parallelized.
- The `_resolve_report_content()` method bypasses `compile()` to avoid resetting state. This coupling to the internal `_PLACEHOLDER_RE.sub()` pattern must be maintained if the compile pipeline changes.
- Editing a report to add `{{reports...}}` placeholders creates implicit dependencies between reports. There is no UI to visualize these dependencies — the cycle detection sentinel is the only feedback mechanism.
- The placeholder tree now includes reports, which means the tree response grows with the number of reports. This is fine for moderate report counts but could become a concern at scale.

## Execution Order

1. Extract `_resolve_portfolios()` from `_resolve()` — pure refactoring, no behavior change.
2. Add `ReportRepository` to `TemplateCompilerService.__init__()`.
3. Add `_report_resolve_stack` initialization in `compile()`.
4. Add `_REPORT_SCALAR_FIELDS` frozenset.
5. Implement `_resolve_reports()`, `_render_all_reports()`, `_render_report_metadata()`, `_resolve_report_content()` with cycle detection.
6. Update `_resolve()` to dispatch to `_resolve_reports()` for the `reports` root.
7. Update `get_placeholder_tree()` to include reports.
8. Update `PlaceholderTreeRead` and add `PlaceholderReportRead` schema.
9. Add backend tests for all report placeholder paths, cycle detection, re-compilation, and placeholder tree.
10. Update frontend `PlaceholderTree` type and `PlaceholderReport` interface.
11. Add Report `PlaceholderGroup` and dynamic report shortcuts to the template editor.

## Notes

- The `metadata` alias is removed — `{{reports.<name>}}` is the only way to render report metadata. This keeps the contract minimal.
- Report names contain underscores and digits but no dots, so they are unambiguous in dot-separated placeholder paths.
- The cycle detection sentinel is intentionally visible in output. Silent suppression would hide authoring errors.
