# Frontend UI/UX Design & Phased Upgrade Plan: Self-Reflection Stock Analysis Loop

**Generated:** 2026-03-14
**Scope:** Frontend UI/UX gap analysis against the self-reflection stock analysis vision, plus phased upgrade plan
**Prerequisite:** `stock_analysis_evolution_plan_flexible_prompt_composition.md` (backend plan, substantially implemented)

---

## SECTION 1: CURRENT STATE ASSESSMENT

The backend evolution plan (Waves 0–6) has been **substantially implemented** on both backend and frontend. The following capabilities are live today:

| Capability | Status | Location |
|---|---|---|
| PromptComposer (single + two-step modes) | Built | `prompt-composer.tsx` (826 lines) |
| Snippet CRUD (global) | Built | `snippet/snippet-section.tsx`, `snippet-dialog.tsx`, `snippet-list-item.tsx` |
| Template mode toggle (single / two-step) | Built | `prompt-template/prompt-template-dialog.tsx` |
| Placeholder insertion (stock, position, response, snippet) | Built | `prompt-composer.tsx` lines 509–565 |
| Snippet picker (CommandDialog) | Built | `prompt-composer.tsx` lines 674–700 |
| Response picker (CommandDialog) | Built | `prompt-composer.tsx` lines 702–730 |
| Prompt preview (rendered instructions + input + placeholders) | Built | `prompt-composer.tsx` lines 337–375, 646–672 |
| Async run execution + 2s polling | Built | `use-stock-analysis-queries.ts` lines 63–68, `use-stock-analysis-mutations.ts` lines 64–92 |
| Run status toasts (completed / failed / partial) | Built | `use-stock-analysis-workspace.ts` lines 113–140 |
| Run history timeline (collapsible, nested requests/responses) | Built | `conversation-run-history.tsx` (293 lines) |
| Mode badge on runs | Built | `conversation-run-history.tsx` line 102 |
| Running indicator (animated pulse badge) | Built | `conversation-run-history.tsx` lines 104–108 |
| Template-to-editor hydration + reset | Built | `prompt-composer.tsx` lines 177–293 |
| Settings card (enable, defaults, compare-to-origin) | Built | `settings-card.tsx` |
| Conversation list (symbol filter, archive, create) | Built | `conversations-card.tsx` |
| Version timeline (latest versions by symbol) | Built | `timeline-card.tsx` |
| Inputs page (configs + templates + snippets tabs) | Built | `stock-analysis-inputs-page.tsx` |

### Component Tree (Current)

```text
StockAnalysisWorkspace
├── SettingsCard
├── Grid (2-column on XL)
│   ├── SharedInputsCard (quick links to /stock-analysis/inputs)
│   ├── ConversationsCard (symbol filter, archive, create)
│   ├── ConversationDetailCard
│   │   ├── Metric tiles (symbol, runs, versions, latest action)
│   │   ├── Title editor
│   │   ├── PromptComposer
│   │   │   ├── Mode tabs (Single Prompt | Two-Step Workflow)
│   │   │   ├── Metadata fields (LLM config, template, run type, trigger, note)
│   │   │   ├── Placeholder insertion toolbar
│   │   │   ├── Mode-specific textareas (2 or 4 fields)
│   │   │   ├── Preview panel
│   │   │   └── Execute + Compare-to-origin controls
│   │   └── ConversationRunHistory (collapsible run cards)
│   └── TimelineCard (version list)
```

---

## SECTION 2: GAP ANALYSIS — CURRENT UI vs. SELF-REFLECTION VISION

The self-reflection document (`self_reflection_stock_analysis_loop.md`) describes a **living thesis management and decision framework**. The current UI implements the mechanical prompt-and-execute layer well, but several higher-order UX concepts from the vision are missing or underdeveloped.

| Gap ID | Title | Severity | Current State | Vision |
|---|---|---|---|---|
| UX-1 | Response reading experience | High | Raw code panes (`CodePane`) showing `outputText` and `parsedPayload` as monospace text | Structured, readable response cards with sections (thesis, valuation, risk, action) rendered as formatted content |
| UX-2 | Version comparison view | High | Version timeline shows a flat list of version numbers with collapsible raw data | Side-by-side or diff-style comparison between any two versions showing what changed in facts, interpretation, thesis, valuation, risk, confidence, action |
| UX-3 | Confidence & scoring visualization | Medium | `confidenceScore` exists on versions but is only shown as a number in the collapsed card | Trend chart showing confidence/score evolution over time per conversation; sparkline in conversation list |
| UX-4 | Action stance tracking | Medium | `latestAction` shown as a single metric tile on conversation detail | Action history timeline showing stance changes (buy → hold → trim) with dates and reasons; visual indicator of drift |
| UX-5 | Review cadence & trigger management | Low | `reviewTrigger` is a free-text input per run; `runType` is a select | Suggested next review date, overdue indicators, cadence configuration per conversation (daily/weekly/monthly), trigger dashboard |
| UX-6 | Reflection layer UI | Medium | No explicit reflection UI; reflection is embedded in LLM response text if the prompt asks for it | Dedicated reflection section in run results that surfaces what was right, what was missed, bias indicators; reflection log view |
| UX-7 | Cross-version drift detection | Medium | No automated comparison; user must manually read old and new versions | Automated delta summary between current run and (a) previous run, (b) origin version; change classification badges (noise / thesis update / actionable) |
| UX-8 | Prompt template guidance | Low | Template selector is a dropdown; user must know which template to pick | Template cards with descriptions, use-case tags, and preview of what the template produces; recommended template based on run type |
| UX-9 | Workspace layout density | Medium | Single-column conversation detail with PromptComposer and history stacked vertically; lots of scrolling | Resizable panels or tabbed layout within conversation detail to reduce scrolling; composer and history side-by-side on wide screens |
| UX-10 | Run result quick summary | Medium | Must expand collapsible run card and read nested request/response to understand outcome | One-line summary on the collapsed run card showing key output (action stance, confidence, thesis change indicator) |

---

## SECTION 3: UI/UX DESIGN PROPOSALS

### UX-1: Structured Response Cards

**Problem:** LLM responses are displayed as raw monospace text in `CodePane`. For two-step workflow runs that return structured JSON (parsed via `parsedPayload`), this wastes the structured data.

**Design:**

Replace `CodePane` for parsed responses with a `StructuredResponseCard` component:

```text
StructuredResponseCard
├── Header: action badge (BUY/HOLD/SELL) + confidence score pill + symbol
├── Sections (collapsible):
│   ├── Thesis (rendered markdown)
│   ├── Valuation (key metrics in a mini-table: bear/base/bull/current/margin)
│   ├── Risk Assessment (bullet list with severity badges)
│   ├── Comparison (if two-step: what changed, classified as noise/update/actionable)
│   ├── Decision (action + reason + reversal conditions)
│   └── Reflection (what was right, what was missed, bias flags)
├── Footer: token counts, provider, timestamp
└── Fallback: CodePane for unparsed or single-prompt responses
```

**Rendering rules:**
- If `parseStatus === "parsed_success"` and `parsedPayload` is non-null → render `StructuredResponseCard`
- If `parseStatus !== "parsed_success"` or single-prompt mode → render existing `CodePane` with `outputText`
- Always keep a "View raw" toggle that switches to the current `CodePane` view

**Components to create:**
- `structured-response-card.tsx` — main card with section rendering
- `response-section.tsx` — collapsible section with markdown rendering (reuse a lightweight markdown renderer or `dangerouslySetInnerHTML` with sanitization)

**Components to modify:**
- `conversation-run-history.tsx` — replace the response `CodePane` block (lines 224–276) with conditional rendering

---

### UX-2: Version Comparison View

**Problem:** The version timeline (`timeline-card.tsx`) shows versions as a flat list. The self-reflection vision requires structured comparison between versions to detect drift, validate assumptions, and make better decisions.

**Design:**

Add a `VersionComparisonPanel` accessible from the timeline card:

```text
TimelineCard (enhanced)
├── Version list (existing)
│   └── Each version row gains a "Compare" checkbox
├── Compare button (enabled when exactly 2 versions selected)
└── VersionComparisonPanel (slide-out sheet or inline expansion)
    ├── Header: "Version N vs Version M" with dates
    ├── Side-by-side sections:
    │   ├── Action: [BUY] → [HOLD] (with change indicator)
    │   ├── Confidence: 4.2 → 3.8 (with delta and direction arrow)
    │   ├── Fresh Analysis diff (text diff or section-by-section)
    │   ├── Comparison section (from version M's two-step output)
    │   ├── Decision section diff
    │   └── Reflection section diff
    ├── Change summary:
    │   ├── Classification badges: [New Fact] [Changed Interpretation] [Noise]
    │   └── One-line delta: "Thesis weakened: confidence dropped, action changed from BUY to HOLD"
    └── Close button
```

**Implementation approach:**
- Use the existing `Sheet` component for the comparison panel (slides in from the right)
- Version data is already fetched via `versionsQuery`; comparison is pure frontend logic (no new API needed)
- Text diffing: use a lightweight diff library (e.g., `diff` npm package) or simple section-by-section comparison
- The comparison panel reads two `StockAnalysisVersionRead` objects and renders their fields side-by-side

**Components to create:**
- `version-comparison-panel.tsx` — Sheet-based comparison view
- `version-diff-section.tsx` — side-by-side section renderer with change highlighting

**Components to modify:**
- `timeline-card.tsx` — add selection state and compare button

---

### UX-3: Confidence & Scoring Visualization

**Problem:** Confidence scores exist on versions but are displayed as plain numbers. The self-reflection vision emphasizes tracking score evolution to detect gradual thesis deterioration.

**Design:**

Add a `ConfidenceTrendChart` to the conversation detail card:

```text
ConversationDetailCard (enhanced metric tiles area)
├── Existing tiles: Symbol, Runs, Versions, Latest Action
├── New tile: Confidence Trend (sparkline showing score over versions)
└── Expandable: Full chart view with version markers on x-axis
```

**Implementation:**
- Use the existing `Chart` component (Recharts wrapper) from `components/ui/chart.tsx`
- Data source: `versions` array from `versionsQuery`, mapped to `[{ versionNumber, confidenceScore, createdAt }]`
- Sparkline in the metric tile area (small, inline)
- Click to expand into a full-width chart below the tiles
- Chart shows confidence score on y-axis, version number on x-axis, with action-change markers

**Components to create:**
- `confidence-trend-chart.tsx` — Recharts line chart with version markers

**Components to modify:**
- `conversation-detail-card.tsx` — add chart below metric tiles

---

### UX-9: Workspace Layout Density

**Problem:** The conversation detail card stacks PromptComposer (large) and run history (large) vertically, requiring significant scrolling. On wide screens, this wastes horizontal space.

**Design:**

Introduce a tabbed or split layout within `ConversationDetailCard`:

```text
ConversationDetailCard (enhanced)
├── Header: title, archive, metric tiles, confidence chart
└── Tabs or resizable split:
    ├── Tab "Compose" → PromptComposer
    ├── Tab "History" → ConversationRunHistory
    └── Tab "Compare" → VersionComparisonPanel (when versions exist)
```

**Alternative (wide-screen split):**
On `2xl` breakpoints, show composer and history side-by-side:

```text
ConversationDetailCard
├── Header area (full width)
└── 2xl:grid-cols-2 / default:stacked
    ├── Left: PromptComposer
    └── Right: ConversationRunHistory (scrollable)
```

**Recommendation:** Start with tabs (simpler, works on all screen sizes). The tab approach also naturally accommodates the comparison view as a third tab.

**Components to modify:**
- `conversation-detail-card.tsx` — wrap PromptComposer and ConversationRunHistory in `Tabs`

---

### UX-10: Run Result Quick Summary

**Problem:** Collapsed run cards show run type, status, provider, mode, and timestamps — but not the actual outcome. Users must expand every run to find the action/confidence.

**Design:**

Add a one-line summary to the collapsed run header:

```text
Run card header (enhanced)
├── Existing: run type title, status badge, provider badge, mode badge
├── New: outcome summary line (only for completed runs with parsed responses)
│   └── Example: "→ HOLD · Confidence 3.8 · Thesis unchanged"
│   └── Example: "→ BUY · Confidence 4.5 · New: margin expansion thesis"
│   └── Example: "Response saved (unparsed)" for single-prompt
└── Existing: created/completed timestamps
```

**Implementation:**
- Extract action + confidence from the last response's `parsedPayload` (if `parseStatus === "parsed_success"`)
- For single-prompt runs: show truncated `outputText` preview (first 80 chars)
- For failed runs: show error summary
- This is pure frontend rendering logic — no API changes

**Components to modify:**
- `conversation-run-history.tsx` — add summary line in the collapsible trigger area (around line 89)

---

### UX-7: Cross-Version Drift Detection (Automated Delta)

**Problem:** Users must manually compare versions to detect thesis drift. The self-reflection vision emphasizes that gradual drift is one of the most dangerous failure modes.

**Design:**

Add a `DriftIndicator` to the conversation list and detail view:

```text
ConversationsCard (enhanced)
├── Each conversation row gains:
│   ├── Existing: symbol, title, run count, status
│   └── New: drift indicator (colored dot or badge)
│       ├── Green: thesis stable (action unchanged across last 3 versions)
│       ├── Yellow: thesis evolving (confidence changed >0.5 or action changed once)
│       └── Red: thesis deteriorating (confidence dropped >1.0 or action downgraded 2+ levels)

ConversationDetailCard (enhanced)
├── New: DriftSummaryBanner (below metric tiles, above tabs)
│   └── "Thesis drift detected: confidence dropped from 4.2 to 3.1 over 4 versions. Action changed from BUY to HOLD."
│   └── Only shown when drift thresholds are crossed
```

**Implementation:**
- Drift calculation is pure frontend logic on the `versions` array
- Compare `versions[0]` (latest) against `versions[versions.length - 1]` (origin) and `versions[1]` (previous)
- Thresholds are hardcoded initially; could become configurable per-conversation later

**Components to create:**
- `drift-indicator.tsx` — small badge/dot component with tooltip
- `drift-summary-banner.tsx` — alert-style banner for conversation detail

**Components to modify:**
- `conversations-card.tsx` — add drift indicator to conversation rows
- `conversation-detail-card.tsx` — add drift banner

---

### UX-6: Reflection Layer UI

**Problem:** The self-reflection vision's most valuable output is the reflection log — what was right, what was missed, recurring biases. Currently, reflection is buried in LLM response text.

**Design:**

This is a **prompt design + UI display** problem. The reflection layer requires:

1. **Prompt templates that explicitly request reflection sections** — this is a content/template authoring task, not a code change. Ship example templates that include reflection prompts.

2. **UI to surface reflection from parsed responses:**

```text
ConversationDetailCard → History tab → Expanded run → Response
├── StructuredResponseCard (from UX-1)
│   └── Reflection section (always last, visually distinct)
│       ├── "What I got right" (from parsed payload)
│       ├── "What I missed" (from parsed payload)
│       ├── "Bias indicators" (from parsed payload)
│       └── "Would I still believe this from a blank page?" (from parsed payload)
```

3. **Reflection log view** (future enhancement):

```text
ConversationDetailCard → new "Reflections" tab
├── Aggregated reflection sections from all completed runs
├── Sorted newest first
├── Searchable by keyword
└── Pattern detection: "You've mentioned 'overconfidence in management' in 3 of 5 reflections"
```

**Phase 1:** Ship example prompt templates with reflection sections + render reflection in `StructuredResponseCard`.
**Phase 2:** Aggregated reflection log tab.

---

## SECTION 4: PHASED UPGRADE PLAN

### Phase 1: Response Readability (High impact, low risk)

| Task | Description | Components | Effort |
|---|---|---|---|
| P1-T1 | Create `StructuredResponseCard` for parsed two-step responses | New: `structured-response-card.tsx`, `response-section.tsx` | M |
| P1-T2 | Add "View raw" toggle to switch between structured and CodePane views | Modify: `conversation-run-history.tsx` | S |
| P1-T3 | Add run outcome summary to collapsed run headers | Modify: `conversation-run-history.tsx` | S |
| P1-T4 | Ship 2 example prompt templates with explicit reflection sections | New: seed data or documentation | S |

**Commit strategy:**
1. `feat(frontend): add structured response card for parsed LLM responses`
2. `feat(frontend): add run outcome summary to collapsed run headers`
3. `docs: add example prompt templates with reflection sections`

---

### Phase 2: Workspace Layout & Navigation (Medium impact, low risk)

| Task | Description | Components | Effort |
|---|---|---|---|
| P2-T1 | Wrap PromptComposer + RunHistory in Tabs inside ConversationDetailCard | Modify: `conversation-detail-card.tsx` | S |
| P2-T2 | Add confidence trend sparkline to conversation metric tiles | New: `confidence-trend-chart.tsx`; Modify: `conversation-detail-card.tsx` | M |
| P2-T3 | Add drift indicator badge to conversation list rows | New: `drift-indicator.tsx`; Modify: `conversations-card.tsx` | S |
| P2-T4 | Add drift summary banner to conversation detail | New: `drift-summary-banner.tsx`; Modify: `conversation-detail-card.tsx` | S |

**Commit strategy:**
1. `feat(frontend): tabbed layout for compose/history/compare in conversation detail`
2. `feat(frontend): confidence trend sparkline on conversation detail`
3. `feat(frontend): drift indicator on conversation list and detail`

---

### Phase 3: Version Comparison (High impact, medium risk)

| Task | Description | Components | Effort |
|---|---|---|---|
| P3-T1 | Add version selection checkboxes and compare button to timeline card | Modify: `timeline-card.tsx` | S |
| P3-T2 | Create `VersionComparisonPanel` as a Sheet with side-by-side sections | New: `version-comparison-panel.tsx`, `version-diff-section.tsx` | L |
| P3-T3 | Add change classification badges (noise / thesis update / actionable) | New: classification logic in a utility; badges in comparison panel | M |
| P3-T4 | Wire comparison panel as third tab in conversation detail | Modify: `conversation-detail-card.tsx` | S |

**Commit strategy:**
1. `feat(frontend): version selection and compare button on timeline card`
2. `feat(frontend): version comparison panel with side-by-side diff`
3. `feat(frontend): wire comparison panel into conversation detail tabs`

---

### Phase 4: Reflection & Learning Layer (Medium impact, medium effort)

| Task | Description | Components | Effort |
|---|---|---|---|
| P4-T1 | Render reflection section distinctly in StructuredResponseCard | Modify: `structured-response-card.tsx` | S |
| P4-T2 | Create aggregated reflection log tab in conversation detail | New: `reflection-log-tab.tsx` | M |
| P4-T3 | Add pattern detection for recurring reflection themes | New: utility function for keyword frequency analysis | M |
| P4-T4 | Add action history timeline showing stance changes over time | New: `action-history-timeline.tsx` | M |

**Commit strategy:**
1. `feat(frontend): distinct reflection section in structured response card`
2. `feat(frontend): aggregated reflection log tab`
3. `feat(frontend): action history timeline with stance change tracking`

---

### Phase 5: Polish & Guidance (Low impact, low risk)

| Task | Description | Components | Effort |
|---|---|---|---|
| P5-T1 | Template cards with descriptions and use-case tags in PromptComposer | Modify: `prompt-composer.tsx` template selector | M |
| P5-T2 | Recommended template suggestion based on run type | Modify: `prompt-composer.tsx` | S |
| P5-T3 | Review cadence configuration per conversation (next review date, overdue indicator) | New: cadence fields on conversation; Modify: `conversations-card.tsx` | M |
| P5-T4 | Placeholder insertion autocomplete (type `{{` to trigger inline suggestions) | Modify: `prompt-composer.tsx` textarea handling | L |

**Commit strategy:**
1. `feat(frontend): template cards with descriptions in prompt composer`
2. `feat(frontend): review cadence tracking on conversations`
3. `feat(frontend): inline placeholder autocomplete in prompt textareas`

---

## SECTION 5: DEPENDENCY GRAPH

```text
Phase 1 (Response Readability)
  ├── P1-T1: StructuredResponseCard ──────────────────┐
  ├── P1-T2: View raw toggle (depends on P1-T1) ──────┤
  ├── P1-T3: Run outcome summary (independent) ───────┤
  └── P1-T4: Example templates (independent) ─────────┘
                                                       │
Phase 2 (Layout & Navigation)                          │
  ├── P2-T1: Tabbed layout (independent) ──────────────┤
  ├── P2-T2: Confidence chart (independent) ───────────┤
  ├── P2-T3: Drift indicator (independent) ────────────┤
  └── P2-T4: Drift banner (depends on P2-T3 logic) ───┘
                                                       │
Phase 3 (Version Comparison)                           │
  ├── P3-T1: Version selection (independent) ──────────┤
  ├── P3-T2: Comparison panel (depends on P3-T1) ─────┤
  ├── P3-T3: Change classification (depends on P3-T2) ─┤
  └── P3-T4: Wire into tabs (depends on P2-T1, P3-T2) ┘
                                                       │
Phase 4 (Reflection Layer)                             │
  ├── P4-T1: Reflection in response card (depends P1-T1)
  ├── P4-T2: Reflection log tab (depends on P2-T1) ───┤
  ├── P4-T3: Pattern detection (depends on P4-T2) ────┤
  └── P4-T4: Action history (independent) ────────────┘
                                                       │
Phase 5 (Polish)                                       │
  └── All tasks independent of each other ─────────────┘
```

**Phases 1 and 2 can run in parallel.** Phase 3 depends on Phase 2 (tabbed layout). Phase 4 depends on Phase 1 (structured response card) and Phase 2 (tabs). Phase 5 is independent and can be interleaved.

---

## SECTION 6: WHAT DOES NOT NEED TO CHANGE

The following are already well-implemented and should be preserved as-is:

- **PromptComposer core** — mode tabs, template hydration, placeholder insertion, preview, execute flow
- **Snippet/Response/Position/Stock pickers** — CommandDialog pattern works well
- **Run creation + execution mutation flow** — create-then-execute two-call pattern with async polling
- **Settings card** — enable/disable, default config/template, compare-to-origin
- **Inputs page** — three-tab layout for configs, templates, snippets with consistent CRUD patterns
- **Conversation CRUD** — symbol filter, archive toggle, create flow, auto-selection
- **Query orchestration** — sorting, polling, invalidation patterns in hooks

---

## SECTION 7: RISK ASSESSMENT

### Risk 1: StructuredResponseCard Parsing Fragility
**Probability:** Medium
**Impact:** Medium
**Mitigation:** Always fall back to `CodePane` when `parseStatus !== "parsed_success"`. The structured card is an enhancement, not a replacement. Keep the "View raw" toggle permanently available.

### Risk 2: Version Comparison Complexity
**Probability:** Medium
**Impact:** Low (UX degradation, not data loss)
**Mitigation:** Start with simple field-by-field comparison (action, confidence, thesis text). Text diffing is a Phase 3 enhancement — ship the side-by-side view first without character-level diffs.

### Risk 3: Drift Detection False Positives
**Probability:** Medium
**Impact:** Low
**Mitigation:** Use conservative thresholds. Only flag drift when confidence drops >1.0 or action changes by 2+ levels. Show drift as informational (yellow/red dot), not as a blocking alert.

### Risk 4: Layout Change Disruption
**Probability:** Low
**Impact:** Medium
**Mitigation:** The tabbed layout (P2-T1) preserves all existing content — it just reorganizes it. Default to the "Compose" tab so the first-load experience is identical to today. Run history moves to a tab but is one click away.

### Risk 5: Recharts Bundle Size
**Probability:** Low
**Impact:** Low
**Mitigation:** Recharts is already in the bundle (used by `chart.tsx`, chunked separately in `vite.config.ts`). The confidence sparkline adds no new dependencies.

---

## SECTION 8: BACKEND REQUIREMENTS

Most of this plan is **frontend-only**. The following are the only backend touchpoints:

| Task | Backend Change | Effort |
|---|---|---|
| P5-T3 (Review cadence) | Add `nextReviewDate` nullable column to `StockAnalysisConversation`; update schema + API | S |
| None of the other tasks | No backend changes — all data already available via existing APIs | - |

The version comparison, drift detection, confidence charting, structured response rendering, and reflection aggregation are all computed from data already returned by existing endpoints (`GET /runs`, `GET /versions`, response `parsedPayload`).

---

## SECTION 9: CATEGORY + SKILL ASSIGNMENTS

| Task | Category | Skills | Notes |
|---|---|---|---|
| P1-T1, P1-T2 | `visual-engineering` | `frontend-ui-ux` | New component with markdown rendering |
| P1-T3 | `quick` | — | Small modification to existing component |
| P2-T1 | `quick` | — | Wrap existing components in Tabs |
| P2-T2 | `visual-engineering` | `frontend-ui-ux` | Recharts sparkline integration |
| P2-T3, P2-T4 | `quick` | — | Small badge + banner components |
| P3-T1 | `quick` | — | Checkbox state in timeline card |
| P3-T2 | `visual-engineering` | `frontend-ui-ux` | Sheet-based comparison layout |
| P3-T3 | `unspecified-low` | — | Classification logic utility |
| P4-T2 | `visual-engineering` | `frontend-ui-ux` | Aggregated reflection view |
| P4-T4 | `visual-engineering` | `frontend-ui-ux` | Action history timeline |
| P5-T4 | `deep` | — | Inline autocomplete is complex textarea handling |

---

That's the complete plan. The key insight is that the mechanical prompt composition infrastructure is already solid — the upgrade opportunity is in **making the self-reflection loop's outputs more readable, comparable, and actionable** through better response rendering, version comparison, drift detection, and reflection surfacing.
