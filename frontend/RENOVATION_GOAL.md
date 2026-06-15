Renovate the entire management Web UI into a polished Apple-inspired interface on top of the existing universal design-system foundation, without changing business behavior, routes, API contracts, auth logic, permissions, data models, or user workflows. Continue until the app has a consistent Apple-inspired visual language, shared components are reused everywhere practical, documentation is updated, obsolete visual patterns are removed or deprecated, and build/typecheck/lint/tests pass or remaining failures are documented.

Context:
The previous refactor foundation is already done. The project should already have or be moving toward a universal design language, shared tokens, shared components, and common layout/component patterns. Build on that foundation instead of starting over.

Design direction:
Create an Apple-inspired management UI based on the spirit of Apple Human Interface Guidelines: clarity, simplicity, content-first hierarchy, generous spacing, precise alignment, restrained color, soft depth, elegant typography, accessible interactions, and high perceived polish. Use Apple HIG principles as inspiration, but do not copy Apple proprietary assets, icons, screenshots, product UI, exact native components, or brand identity. The result should feel premium, calm, minimal, and coherent, while still being appropriate for a professional admin/management web application.

Important style principles:

- Use one clean visual language across the whole app.
- Prefer content-first layout with subtle chrome.
- Use generous but practical spacing.
- Use consistent radius, shadow, border, surface, typography, and interaction states.
- Use a restrained neutral palette with one primary accent color and consistent semantic colors.
- Prefer soft cards, grouped sections, clear toolbars, refined tables, elegant forms, and clean page headers.
- Avoid colorful randomness, heavy borders, cluttered panels, inconsistent button styles, mixed icon sets, excessive gradients, excessive glassmorphism, and decorative animations.
- Use subtle depth only where it improves hierarchy.
- Keep the UI fast and readable for dense management workflows.
- Do not sacrifice data density where the product needs tables, filters, forms, and operational dashboards.

Initial audit:
Before editing, inspect the current state of the repository:

- Read existing design-system docs, UI_REFACTOR_PLAN.md, DESIGN_SYSTEM.md, AGENTS.md, component folders, style/token files, layout components, page templates, and package scripts.
- Identify which pages/components are still visually inconsistent.
- Identify duplicated visual patterns that survived the previous foundation refactor.
- Identify all styling systems currently used.
- Identify pages with tables, forms, filters, modals, drawers, cards, dashboards, settings pages, detail pages, auth pages, empty states, loading states, and error states.
- Update or create APPLE_STYLE_RENOVATION_PLAN.md with:
  - current visual problems
  - Apple-inspired target language
  - token changes
  - component changes
  - migration order
  - risky pages
  - validation commands
  - before/after checklist
  - deprecated visual patterns

Use ui-ux-pro-max skill:
Use the ui-ux-pro-max skill for:

- visual audit
- UX consistency review
- page hierarchy decisions
- component polish
- accessibility checks
- responsive behavior review
- final visual QA checklist

Token system:
Refine the existing token system instead of creating a parallel one. Add or adjust tokens for:

- background surfaces
- elevated surfaces
- grouped surfaces
- primary text
- secondary text
- tertiary text
- border/subtle separator
- primary accent
- hover/active/focus states
- success/warning/error/info states
- radius scale
- shadow/elevation scale
- spacing scale
- typography scale
- table density
- form control height
- sidebar width
- page max width
- modal/drawer width
- transition duration/easing

Typography:

- Use a system-font stack suitable for an Apple-inspired web UI, such as system UI fonts.
- Do not bundle or redistribute Apple fonts.
- Standardize heading, body, label, caption, table, code, and numeric styles.
- Ensure typography is readable, calm, and consistent.
- Use font weight and spacing rather than color noise to create hierarchy.

Layout renovation:
Unify the app around polished management layouts:

- AppShell
- Sidebar
- TopBar or Toolbar
- PageHeader
- Breadcrumbs if already used or needed
- Page actions
- Content containers
- Section groups
- Cards
- Detail views
- Settings pages
- Auth pages
- Dashboard pages

Layout rules:

- Use consistent page margins and content width.
- Align page titles, actions, filters, and tables consistently.
- Avoid random page-specific layout hacks.
- Make the sidebar/top navigation feel refined and calm.
- Use subtle separators and surface changes instead of heavy boxes.
- Ensure responsive behavior is graceful on laptop, desktop, tablet, and narrow widths.

Component renovation:
Upgrade existing shared components to the Apple-inspired language and migrate pages to them. Focus especially on:

- Button
- IconButton
- Input
- Textarea
- Select
- Checkbox
- Radio
- Switch
- FormField
- SearchBar
- FilterBar
- Toolbar
- DataTable
- Pagination
- Tabs
- Modal
- Drawer
- ConfirmDialog
- Dropdown/Menu
- Badge
- StatusBadge
- Alert
- Toast/Notification
- EmptyState
- LoadingState
- Spinner
- Skeleton
- ErrorState
- Card
- Section
- PageHeader
- AppShell
- Sidebar
- TopNav
- Breadcrumbs
- Date/time display wrappers
- Upload components if present

Buttons:

- Standardize primary, secondary, tertiary/ghost, destructive, link, and icon button styles.
- Use consistent height, radius, spacing, disabled state, loading state, focus ring, hover state, and active state.
- Remove one-off button colors and sizes unless there is a documented product reason.

Forms:

- Standardize field height, label placement, helper text, error text, disabled state, readonly state, validation state, spacing, and grouping.
- Forms should feel clean, calm, and precise.
- Required fields, errors, and disabled states must be obvious but not visually noisy.
- Preserve all form behavior and validation logic.

Tables:

- Create or refine a universal DataTable pattern.
- Standardize header style, row height, hover state, selected state, empty state, loading state, error state, pagination, sorting, filters, bulk actions, row actions, and status badges.
- Keep tables efficient for management workflows.
- Do not over-cardify dense data tables.
- Use subtle separators and clean alignment.
- Numeric values, dates, statuses, and actions should align consistently.

Filters and toolbars:

- Standardize search, filters, date ranges, tabs, segmented controls if present, reset actions, and export/actions.
- Toolbars should be clear, compact, and visually balanced.
- Avoid inconsistent filter layouts across pages.

Modals and drawers:

- Standardize width, header, body, footer, actions, close behavior, spacing, overlay, focus trapping if applicable, and keyboard interaction.
- Confirm dialogs should be concise and consistent.
- Destructive actions should have a clear but restrained visual treatment.

States:
Standardize:

- loading states
- skeleton states
- empty states
- error states
- permission/unauthorized states
- no-search-results states
- offline/network failure states if present
- success/error toasts
- disabled states

Icons:

- Use one icon system consistently.
- Remove mixed icon libraries when practical.
- Use consistent icon size, stroke weight, alignment, and color.
- Do not use Apple proprietary icons or SF Symbols unless the project is explicitly licensed/allowed to do so.

Motion:

- Use restrained transitions for hover, focus, disclosure, modal/drawer entry, and loading feedback.
- Avoid distracting animation.
- Respect reduced-motion preferences where applicable.

Accessibility:
Ensure:

- visible focus states
- keyboard navigation
- semantic buttons/links
- proper labels
- aria attributes where needed
- sufficient contrast
- readable text sizes
- accessible modals/drawers
- no interaction available only by hover
- reduced-motion support where relevant

Implementation rules:

- Build on the existing universal component foundation.
- Prefer modifying shared components and tokens over page-specific edits.
- Migrate pages to shared components rather than styling each page separately.
- Remove hard-coded colors, random margins, random typography, one-off shadows, one-off radius values, and inconsistent layout hacks.
- Do not introduce a new UI library, CSS framework, icon library, animation library, or major dependency unless absolutely necessary and documented in APPLE_STYLE_RENOVATION_PLAN.md.
- Do not perform a full rewrite.
- Do not change business logic.
- Do not change API calls.
- Do not change route names.
- Do not change auth or permission behavior.
- Do not change i18n keys unless unavoidable.
- Do not break tests.
- Keep commits/changes conceptually grouped by tokens, shared components, layout, then page migration.

Migration order:

1. Audit and write APPLE_STYLE_RENOVATION_PLAN.md.
2. Refine design tokens and global styles.
3. Renovate AppShell, navigation, page layout, and page header.
4. Renovate primitive components: Button, inputs, badges, cards, tabs, alerts.
5. Renovate complex components: DataTable, filters, forms, modals, drawers, empty/loading/error states.
6. Migrate high-traffic pages first.
7. Migrate remaining pages by pattern.
8. Remove or deprecate obsolete styles/components.
9. Update documentation.
10. Run full validation and produce final report.

Documentation:
Update or create:

- DESIGN_SYSTEM.md
- APPLE_STYLE_RENOVATION_PLAN.md
- COMPONENT_USAGE.md or equivalent if the project already has docs
- Deprecated component/style mapping

Documentation must include:

- Apple-inspired visual principles used in this project
- token list
- layout rules
- component usage examples
- table rules
- form rules
- modal/drawer rules
- status/empty/loading/error state rules
- accessibility rules
- anti-patterns to avoid
- deprecated components/styles and replacements

Validation:
Discover available commands from package.json, lockfiles, framework config, and repo docs. Run the appropriate commands after meaningful checkpoints:

- install/dependency check if needed
- format
- lint
- typecheck
- unit tests
- component tests
- build
- Storybook build if available
- e2e or Playwright tests if available and reasonably configured

If visual/browser tooling is available:

- launch the app
- inspect representative pages
- verify layout consistency
- verify responsive states
- verify modals/drawers/forms/tables
- capture or describe visual QA findings
- fix issues discovered during review

Completion condition:
Stop only when:

- The whole Web UI follows one Apple-inspired design language.
- Shared tokens define the visual system.
- Shared components are the default for common UI.
- Major pages have consistent layout, spacing, typography, color, buttons, forms, tables, filters, modals, loading states, empty states, and error states.
- Hard-coded visual one-offs are removed or reduced to documented exceptions.
- Obsolete styles/components are removed or marked deprecated.
- Documentation is updated.
- Build succeeds.
- Lint/typecheck/tests pass, or any remaining failures are clearly documented as pre-existing or blocked with exact reasons.

Final report:
When finished, provide:

- summary of visual renovation
- files changed
- tokens changed
- components changed
- pages migrated
- obsolete/deprecated components or styles
- validation commands run and results
- accessibility notes
- responsive QA notes
- known risks
- remaining recommended visual QA steps
