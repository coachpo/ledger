# Compiled Reports Design

> Archive Status: Fully implemented with follow-on refinements. Live code uses slug-based report routes, persists `source` and `metadata`, and keeps this document as the original design record rather than the primary contract. Specific route tables, schema snippets, and id-based examples below are superseded by `docs/api-design.md` and `docs/data-model.md`.

## Overview

A new "Reports" feature that persists compiled template output as standalone, immutable-by-default deliverables. Reports are created by compiling a stored template against live portfolio data at a point in time. Once created, reports have no backward link to the source template — they are independent documents.

Users can browse, read, lightly edit, download, and delete reports from a dedicated "Reports" sidebar tab.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Sidebar tab name | **Reports** | Short, distinct from "Templates", describes compiled output |
| Template relationship | No FK, no backward link | Reports are deliverables; orphaned on template deletion |
| Multiple compilations | Yes | Same template can produce many reports over time |
| Editing scope | Post-compile text only | `{{...}}` treated as literal text, no re-compilation |
| Deletion | Hard delete | No soft-delete or archive |
| Creation trigger | Both Reports tab and Template editor | Two entry points for convenience |
| Download format | Markdown `.md` | Single format |
| Reading view | Rendered markdown | GitHub-style preview |
| Storage | Database | Consistent with existing `TextTemplate` pattern |
| Naming | Auto-generated, unique, includes datetime + source template name | See naming section below |

## Report Naming Convention

### Format

```
{normalized_source_template_name}_{YYYYMMDD}_{HHmmss}
```

### Rules

- Source template name is normalized: lowercased, whitespace and special characters replaced with underscores, consecutive underscores collapsed, leading/trailing underscores stripped.
- Datetime is UTC at the moment of compilation.
- The full name must be unique (enforced by DB constraint).
- If a collision occurs (two compiles of the same template within the same second), append a `_2`, `_3`, etc. suffix.
- Max length: 200 characters (template name portion truncated if needed to fit within limit after datetime suffix).

### Examples

| Source Template Name | Report Name |
|---|---|
| Monthly Report | `monthly_report_20260317_143052` |
| Q1 Summary | `q1_summary_20260317_143052` |
| My Portfolio — March | `my_portfolio_march_20260317_143052` |

### Download Filename

The download endpoint returns the report name with `.md` extension:

```
monthly_report_20260317_143052.md
```

## Data Model

### New Table: `reports`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `Integer` | PK, autoincrement | From `IdMixin` |
| `name` | `String(200)` | NOT NULL, UNIQUE | Auto-generated at creation |
| `content` | `Text` | NOT NULL | Compiled markdown content |
| `created_at` | `DateTime(tz)` | NOT NULL | From `TimestampMixin` |
| `updated_at` | `DateTime(tz)` | NOT NULL | From `TimestampMixin` |

### ORM Model

```python
# backend/app/models/report.py

class Report(IdMixin, TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("name", name="uq_reports_name"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
```

No FK to `text_templates`. The source template name is baked into the report name at creation time.

## Backend API

### New Router: `/api/v1/reports`

All endpoints live in `backend/app/api/reports.py` and are mounted in `router.py`.

| Method | Path | Description | Request Body | Response |
|---|---|---|---|---|
| `GET` | `/reports` | List all reports | — | `list[ReportRead]` |
| `GET` | `/reports/{report_id}` | Get single report | — | `ReportRead` |
| `POST` | `/reports/compile/{template_id}` | Compile template → create report | — | `ReportRead` (201) |
| `PATCH` | `/reports/{report_id}` | Update report content | `ReportUpdate` | `ReportRead` |
| `DELETE` | `/reports/{report_id}` | Delete report | — | 204 |
| `GET` | `/reports/{report_id}/download` | Download as `.md` file | — | `text/markdown` file response |

### Compile Endpoint Detail

`POST /reports/compile/{template_id}`:

1. Fetch the template by ID (404 if not found).
2. Compile the template content via `TemplateCompilerService.compile()`.
3. Generate the report name from the template name + current UTC datetime.
4. Ensure name uniqueness (append suffix if collision).
5. Persist the `Report` row with the compiled content.
6. Return `ReportRead`.

### Download Endpoint Detail

`GET /reports/{report_id}/download`:

1. Fetch the report by ID (404 if not found).
2. Return a `Response` with:
   - `content-type: text/markdown; charset=utf-8`
   - `content-disposition: attachment; filename="{report.name}.md"`
   - Body: `report.content`

### Schemas

```python
# backend/app/schemas/report.py

class ReportRead(CamelModel):
    id: int
    name: str
    content: str
    created_at: datetime
    updated_at: datetime

class ReportUpdate(CamelModel):
    content: str | None = Field(default=None, min_length=1)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("Content is required")
        return value

    @model_validator(mode="after")
    def validate_payload(self) -> ReportUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "content" in self.model_fields_set and self.content is None:
            raise ValueError("Content is required")
        return self
```

Note: `ReportUpdate` only exposes `content`. The `name` field is immutable after creation — it's an auto-generated identifier, not user-editable.

## Backend Service

### New Service: `ReportService`

```python
# backend/app/services/report_service.py

class ReportService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ReportRepository(session)

    def list_reports(self) -> list[ReportRead]: ...
    def get_report(self, report_id: int) -> ReportRead: ...
    def get_report_model(self, report_id: int) -> Report: ...
    def create_from_template(
        self,
        template: TextTemplate,
        compiled_content: str,
    ) -> ReportRead: ...
    def update_report(self, report_id: int, payload: ReportUpdate) -> ReportRead: ...
    def delete_report(self, report_id: int) -> None: ...
```

`create_from_template` owns the name generation logic:
1. Normalize the template name.
2. Format the UTC datetime.
3. Combine into `{normalized_name}_{datetime}`.
4. Check uniqueness via `repository.get_by_name()`.
5. If collision, append `_2`, `_3`, etc.
6. Persist and return.

### New Repository: `ReportRepository`

```python
# backend/app/repositories/report.py

class ReportRepository(BaseRepository[Report]):
    model = Report

    def list_all(self) -> list[Report]:
        statement = select(self.model).order_by(self.model.created_at.desc())
        return self._list(statement)

    def get_by_name(self, name: str) -> Report | None:
        statement = select(self.model).where(self.model.name == name)
        return self._get_by_statement(statement)
```

### Dependency Wiring

```python
# In backend/app/api/dependencies.py

def get_report_service(
    session: Annotated[Session, Depends(get_session)],
) -> ReportService:
    return ReportService(session)
```

The compile endpoint also needs `TextTemplateService` and `TemplateCompilerService` injected — these are already wired.

## Frontend

### New Sidebar Tab

In `frontend/src/components/layout.tsx`:

```typescript
import { ClipboardList } from "lucide-react";

const navItems: NavItem[] = [
  { icon: LayoutDashboard, label: "Dashboard", to: "/" },
  { icon: Briefcase, label: "Portfolios", to: "/portfolios" },
  { icon: FileText, label: "Templates", to: "/templates" },
  { icon: ClipboardList, label: "Reports", to: "/reports" },
];
```

Add breadcrumb cases in `getPageMeta()`:
- `/reports` → `{ section: "Reports", title: "Reports" }`
- `/reports/:reportId` → `{ section: "Reports", sectionHref: "/reports", title: "Report Detail" }`

### New Routes

In `frontend/src/routes.ts`:

```typescript
{ path: "reports", Component: ReportListPage },
{ path: "reports/:reportId", Component: ReportDetailPage },
```

### Types

```typescript
// frontend/src/lib/types/report.ts

export interface ReportRead {
  id: number;
  name: string;
  content: string;
  createdAt: string;
  updatedAt: string;
}

export interface ReportUpdateInput {
  content?: string;
}
```

### API Client

```typescript
// frontend/src/lib/api/reports.ts

function reportPath(reportId: IdParam): string {
  return `/reports/${toPathSegment(reportId)}`;
}

export function listReports(signal?: AbortSignal): Promise<ReportRead[]>
export function getReport(reportId: IdParam, signal?: AbortSignal): Promise<ReportRead>
export function compileReport(templateId: IdParam, signal?: AbortSignal): Promise<ReportRead>
export function updateReport(reportId: IdParam, input: ReportUpdateInput, signal?: AbortSignal): Promise<ReportRead>
export function deleteReport(reportId: IdParam, signal?: AbortSignal): Promise<void>
export function downloadReport(reportId: IdParam): string  // returns URL for direct download

export const reportsApi = { list, get, compile, update, delete, downloadUrl } as const;
```

The `compileReport` function calls `POST /reports/compile/{templateId}`.

The `downloadReport` function returns the URL string `/reports/{reportId}/download` for use in an `<a>` tag or `window.open()` — the browser handles the file download natively via the `Content-Disposition: attachment` header.

### Query Keys

```typescript
// In frontend/src/lib/query-keys.ts

const reportsQueryKeys = {
  all: [...apiRoot, "reports"] as const,
  list: () => [...apiRoot, "reports", "list"] as const,
  detail: (reportId: IdParam) =>
    [...apiRoot, "reports", "detail", normalizeId(reportId)] as const,
} as const;
```

Added to the exported `queryKeys` object.

### Hooks

```typescript
// frontend/src/hooks/use-reports.ts

export function useReports()                    // useQuery → list
export function useReport(reportId)             // useQuery → detail, gated with enabled
export function useCompileReport()              // useMutation → compile, invalidates list
export function useUpdateReport()               // useMutation → update, invalidates list
export function useDeleteReport()               // useMutation → delete, invalidates list
```

All mutations invalidate `queryKeys.reports.list()` on success.

### Pages

#### Report List Page (`frontend/src/pages/reports/list.tsx`)

- Fetches list via `useReports()`.
- Renders cards with report name and creation timestamp.
- Each card has a dropdown with: View, Download, Delete.
- "Generate Report" button opens a dialog to pick a stored template, then calls `useCompileReport()`.
- Delete uses `ConfirmDeleteDialog` (same pattern as template list).
- Clicking a report navigates to `/reports/{reportId}`.

#### Report Detail Page (`frontend/src/pages/reports/detail.tsx`)

- Fetches report via `useReport(reportId)`.
- Two-mode view:
  - **Read mode** (default): Renders `report.content` as markdown using a markdown renderer component.
  - **Edit mode**: Plain textarea for the compiled content. No placeholder syntax support. Save calls `useUpdateReport()`.
- Header shows report name (read-only) and creation date.
- Action buttons: Download (`.md`), Edit/Save toggle, Back to list.

### Template Editor Integration

In `frontend/src/pages/templates/editor.tsx`, add a "Generate Report" button alongside the existing save button. When clicked:

1. Call `useCompileReport()` with the current template ID.
2. On success, show a toast with the report name and a link to the new report.
3. Optionally navigate to the report detail page.

This only works for saved templates (button disabled for unsaved/new templates).

## File Touchpoints

### Backend (new files)

- `backend/app/models/report.py` — ORM model
- `backend/app/repositories/report.py` — repository
- `backend/app/services/report_service.py` — service with name generation
- `backend/app/schemas/report.py` — Pydantic schemas
- `backend/app/api/reports.py` — API router

### Backend (modified files)

- `backend/app/models/__init__.py` — add `Report` import
- `backend/app/api/router.py` — mount reports router
- `backend/app/api/dependencies.py` — add `get_report_service()`
- `backend/tests/test_api.py` — report CRUD, compile, download, name uniqueness tests

### Frontend (new files)

- `frontend/src/lib/types/report.ts` — TypeScript types
- `frontend/src/lib/api/reports.ts` — API client functions
- `frontend/src/hooks/use-reports.ts` — TanStack Query hooks
- `frontend/src/pages/reports/list.tsx` — report list page
- `frontend/src/pages/reports/detail.tsx` — report detail/read/edit page

### Frontend (modified files)

- `frontend/src/lib/api-types.ts` — add `report` re-export
- `frontend/src/lib/api.ts` — add `reportsApi` to barrel
- `frontend/src/lib/query-keys.ts` — add `reportsQueryKeys`
- `frontend/src/routes.ts` — add report routes
- `frontend/src/components/layout.tsx` — add Reports nav item + breadcrumbs
- `frontend/src/pages/templates/editor.tsx` — add "Generate Report" button

## Test Plan

### Backend

- **CRUD**: Create report via compile, list, get, update content, delete.
- **Compile**: Compile a template with placeholders, verify report content matches expected compiled output.
- **Name generation**: Verify format `{normalized_name}_{datetime}`, uniqueness suffix on collision.
- **Name immutability**: Verify PATCH does not accept `name` field.
- **Download**: Verify response content-type, content-disposition header, and body content.
- **404s**: Compile with nonexistent template ID, get/update/delete nonexistent report ID.
- **Validation**: Empty content on update, empty payload on update.

### Frontend

- **Unit tests**: Hook behavior, query key structure.
- **E2E (Playwright)**: Navigate to Reports tab, generate a report from a template, verify it appears in the list, open detail view, verify rendered markdown, edit content, download file, delete report.

## Risks

- Report content is a snapshot — if the user expects it to auto-update when portfolio data changes, that's a misunderstanding. The UI should make the "point-in-time snapshot" nature clear.
- Large compiled templates could produce large `content` values in the DB. PostgreSQL `Text` type handles this fine, but list queries should avoid returning full content if the list grows large. Consider a `list_all` that excludes `content` in a future optimization.
- The name generation relies on second-precision UTC timestamps. Under extreme concurrency (multiple compiles of the same template within the same second), the suffix logic handles collisions, but this is an edge case worth testing.

## Execution Order

1. Backend model + repository + model registration in `__init__.py`.
2. Backend schemas.
3. Backend service with name generation logic.
4. Backend API router + dependency wiring + router mounting.
5. Backend tests.
6. Frontend types.
7. Frontend API client + barrel exports.
8. Frontend query keys.
9. Frontend hooks.
10. Frontend report list page.
11. Frontend report detail page.
12. Frontend route + sidebar + breadcrumb wiring.
13. Frontend template editor "Generate Report" button.
14. Frontend E2E tests.
