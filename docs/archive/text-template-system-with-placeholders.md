# Text Template System With Placeholders

> Archive Status: Historical v1 design reference. The live system still supports this foundation, but it now also includes metric placeholders (`total_value`, `unrealized_pnl`, `market_value`, `unrealized_pnl_percent`) and the `reports` placeholder root described in later archive documents.

## Overview

This archive captures the design decisions behind Ledger's text template system as implemented today. The live feature supports stored text templates, server-side placeholder compilation, placeholder browsing, and a dedicated editor route with inline preview.

## Product Goals

- Support multiple stored text templates with full CRUD.
- Allow templates to embed portfolio data through `{{...}}` placeholder syntax.
- Compile placeholders into final article text on demand.
- Expose enough placeholder reference information in the frontend so users can author templates without memorizing the syntax.

## Core Decisions

### Portfolio Identification

- Templates resolve portfolios by portfolio `slug`.
- Portfolio `slug` is a user-provided unique identifier.
- Placeholder paths use the slug instead of numeric ids or display names.

### Balance Model Exposure

- Templates expose a singular portfolio balance surface.
- The template compiler derives the available balance from recorded balance rows.
- The placeholder contract does not expose a list of balances for template authors.

### Placeholder Root

- The root namespace is `portfolios`.
- `{{portfolios}}` renders all portfolios as sectioned output.
- `{{portfolios.*}}` is not part of the contract.

### Output Format

- Templates are free-form markdown text with inline placeholders.
- Compilation returns markdown-compatible text.
- The frontend editor shows the compiled result as inline preview.

## Placeholder Contract

### Portfolio Placeholders

- `portfolios`
- `portfolios.<slug>`
- `portfolios.<slug>.name`
- `portfolios.<slug>.description`
- `portfolios.<slug>.base_currency`
- `portfolios.<slug>.position_count`
- `portfolios.<slug>.balance_count`
- `portfolios.<slug>.created_at`
- `portfolios.<slug>.updated_at`

### Balance Placeholders

- `portfolios.<slug>.balance`
- `portfolios.<slug>.balance.label`
- `portfolios.<slug>.balance.amount`
- `portfolios.<slug>.balance.operation_type`
- `portfolios.<slug>.balance.currency`

### Position Placeholders

- `portfolios.<slug>.positions`
- `portfolios.<slug>.positions.<SYMBOL>`
- `portfolios.<slug>.positions.<SYMBOL>.quantity`
- `portfolios.<slug>.positions.<SYMBOL>.average_cost`
- `portfolios.<slug>.positions.<SYMBOL>.currency`
- `portfolios.<slug>.positions.<SYMBOL>.name`

## Rendering Rules

### Portfolio Rendering

- `{{portfolios}}` renders all portfolios as sectioned blocks.
- `{{portfolios.<slug>}}` renders a portfolio summary block.
- Scalar portfolio fields resolve to plain string output.

### Balance Rendering

- `{{portfolios.<slug>.balance}}` renders the formatted available balance line.
- Balance field placeholders resolve to plain scalar values.

### Position Rendering

- `{{portfolios.<slug>.positions}}` renders a bullet list of all positions.
- `{{portfolios.<slug>.positions.<SYMBOL>}}` renders a single formatted position line.
- Position field placeholders resolve to plain scalar values.

### Error Handling

- Unknown portfolio slug returns an inline unknown-portfolio marker.
- Unknown field path returns an inline unknown-field marker.
- Empty collections render a graceful empty-state line instead of hard failure.

## Backend Design

### Data Model

- `Portfolio` gains a unique `slug` field.
- `TextTemplate` stores:
  - `id`
  - `name`
  - `content`
  - `created_at`
  - `updated_at`

### Services

- `TextTemplateService` owns CRUD for stored templates.
- `TemplateCompilerService` owns placeholder parsing, resolution, and formatted output.

### API Surface

- `GET /api/v1/templates`
- `POST /api/v1/templates`
- `GET /api/v1/templates/{template_id}`
- `PATCH /api/v1/templates/{template_id}`
- `DELETE /api/v1/templates/{template_id}`
- `GET /api/v1/templates/{template_id}/compile`
- `POST /api/v1/templates/compile`
- `GET /api/v1/templates/placeholders`

### Supporting Contracts

- Stored-template compile returns `{ id, name, compiled }`.
- Inline compile returns `{ compiled }`.
- Placeholder browsing returns portfolio slugs plus available position symbols so the frontend can build concrete reference items.

## Frontend Design

### Route Model

- `/templates` lists stored templates.
- `/templates/new` opens the dedicated editor for creation.
- `/templates/:templateId/edit` opens the dedicated editor for updates.

### Template List

- Lists templates with lightweight metadata.
- Supports navigation into the editor route.
- Supports delete flow.

### Template Editor

- Uses a dedicated full-height route.
- Provides inline name editing, template content editing, and save actions.
- Compiles preview inline through debounced API requests.
- Exposes a placeholder reference panel with both generic placeholder groups and concrete portfolio/position examples.
- Supports click-to-insert placeholder authoring.

## Implementation Outcome

### Backend Foundations

- `Portfolio` now includes a unique `slug` used by placeholder paths.
- `TextTemplate` stores `id`, `name`, `content`, `created_at`, and `updated_at`.
- Template CRUD, inline compile, stored compile, and placeholder-tree endpoints are live.

### Frontend Template Surface

- The frontend exposes `/templates`, `/templates/new`, and `/templates/:templateId/edit`.
- Template API bindings and TanStack Query hooks back the list and editor flows.
- The editor compiles preview inline through debounced API requests.
- The placeholder reference panel exposes both generic contract entries and concrete portfolio/position examples.

### UX Hardening

- Templates are first-class navigation entries in the main shell.
- The dedicated editor route uses a full-height layout.
- Shared shadcn-based primitives are reused across the template flows.

## Acceptance Criteria

- Users can create, update, list, and delete multiple templates.
- Users can author templates with markdown and `{{...}}` placeholders.
- Stored templates compile correctly against live backend data.
- Unsaved editor content can be previewed through inline compile.
- The editor exposes placeholder reference help without leaving the page.
- Portfolio placeholders use slug-based addressing.

## Archive Notes

- This document captures the agreed design record for the text template system after the feature definition stabilized.
- It is archived under `docs/archive/` so the live top-level docs can stay focused on current product behavior.
