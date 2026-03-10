**PRD Priorities**

- `P0` = must-have for first usable release; without these, the core portfolio workflow is incomplete
- `P1` = important for parity with the reference experience; can ship after MVP if needed
- `P2` = enhancement/polish; improves usability, insight, and delight but not required for initial launch

**Product Goal**

- Build a web-based portfolio tracking and trading-record UI that replicates the core workflows shown in the screenshots: viewing holdings, adding transactions, browsing transaction history, and analyzing asset/P&L performance across multiple markets and currencies.

**Target User**

- Retail investor or simulator user who manually records trades and wants to monitor holdings, profits/losses, and performance trends.

**Core Modules**

- `Portfolio Overview`
- `Add Trade`
- `Transaction History`
- `P&L Analysis`
- `Asset Analysis`
- `Asset Detail`

**P0 Requirements**

- **Navigation and structure**
- The system shall provide top-level access to `Overview`, `Add Trade`, `Transaction History`, and `Analysis`.
- The web UI shall adapt mobile flows into desktop-friendly navigation such as top tabs, left rail, or page tabs.
- The system shall support responsive layouts for desktop and mobile web.

- **Portfolio/account selection**
- The user shall be able to switch between portfolios/accounts from a visible selector.
- The selected portfolio/account shall drive all displayed holdings, trades, and analysis data.

- **Portfolio Overview**
- The system shall display top summary KPIs: `total market value`, `today’s P&L`, `floating P&L`, `floating P&L rate`, `cumulative P&L`, and `cumulative P&L rate`.
- The user shall be able to hide/show sensitive amounts with a visibility toggle.
- The page shall show grouped holdings by market or asset region, such as `A-share`, `US`, `HK`.
- Each market group shall show aggregate metrics: `market value`, `floating P&L`, and `cumulative P&L`.
- Each market group shall support expand/collapse behavior.
- Each holding row shall display `asset name`, `ticker/code`, `market value`, `quantity`, `current price`, `cost`, `cumulative P&L`, and `P&L rate`.
- Positive and negative values shall use consistent semantic colors.

- **Add Trade**
- The system shall provide trade entry for at least `Buy`, `Sell`, `Dividend/Corporate Action`, and `Split`.
- The user shall be able to search/select a security by `name`, `ticker`, or code.
- The form shall include required inputs: `transaction type`, `security`, `date`, `price`, and `quantity`.
- The form shall support commission and tax inputs.
- The form shall support an optional note field.
- The form shall validate required fields before submission.
- The submit action shall create a transaction record and update holdings.
- For sell actions, the system shall prevent selling more than the available quantity unless short positions are explicitly supported.
- The form shall dynamically adapt fields based on transaction type.

- **Transaction History**
- The system shall display transaction records grouped by month.
- Each month section shall be expandable/collapsible.
- Each record shall show `asset name`, `action type`, `price`, `quantity`, `transaction amount`, and `date`.
- The UI shall show a clear empty state for months with no records.
- The history page shall support browsing across multiple months/years.

- **Basic P&L Analysis**
- The system shall provide an analysis page that shows cumulative P&L for the selected scope.
- The user shall be able to filter analysis by market/asset type.
- The page shall show summary metrics: `total profit`, `total loss`, and `win rate`.
- The page shall display ranked securities for `top gains` and `top losses`.
- Each ranked item shall show `asset name`, `ticker`, and `P&L amount`.

- **Basic Asset Analysis**
- The system shall provide an asset composition view.
- The page shall show total assets in the selected currency.
- The page shall visualize asset composition by category, at minimum `cash` and `stocks`.
- The page shall show category percentages.
- The page shall support switching between at least one analysis mode, such as `by asset class`.

- **Asset Detail**
- The system shall provide a detail page for a selected asset/holding.
- The page shall show `current market value`, `floating P&L`, `floating P&L rate`, `cumulative P&L`, and `cumulative P&L rate`.
- The page shall include a return trend chart for the asset/account over time.

- **Charts and filters**
- The system shall support date-range selection for charts, at minimum `1M`, `3M`, `YTD`, and `All` or equivalent.
- Charts shall display hover or tap tooltips on web-supported devices.
- The system shall update chart data when filters change.

- **Data formatting**
- The system shall support multiple currencies, at minimum `CNY`, `USD`, and `HKD`.
- Monetary values, percentages, and dates shall be formatted consistently.
- Market-specific codes and names shall be shown correctly.

- **States and validation**
- The system shall provide loading, empty, and error states for all major modules.
- The system shall show inline validation messages for trade form errors.
- The system shall disable actions when required data is missing or invalid.

**P1 Requirements**

- **Advanced Asset Analysis**
- The user shall be able to switch analysis dimensions between `asset class` and `currency`.
- The system shall provide a trend analysis section with selectable periods such as `1W`, `1M`, and `YTD`.
- The page shall display cumulative return and return-rate metrics for the selected period.
- The system shall compare user performance against benchmark indices.

- **Benchmark comparison**
- Charts shall support multiple benchmark lines, such as `HS300`, `S&P 500`, `Nasdaq`, `Hang Seng`, or configured regional equivalents.
- The legend shall clearly map colors to benchmarks.
- The selected benchmark comparison method shall be visible.

- **Enhanced P&L Analysis**
- The user shall be able to filter by date range, including `all dates`.
- The page shall display security count and last update timestamp where relevant.
- The UI shall support toggling between `Top Profit` and `Top Loss`.

- **Calendar / Monthly performance**
- The system shall provide a monthly calendar view showing daily P&L amount and return rate.
- The calendar shall support switching between `month` and `year`.
- The selected month shall display aggregate monthly return and return rate.
- The page shall include a supporting bar or trend chart below the calendar.

- **Historical holdings**
- The system shall provide a historical holdings view or archived position view.
- The user shall be able to inspect closed or previous positions separately from active holdings.

- **Table usability**
- Holdings and transaction tables shall support sorting on major numeric columns.
- Large lists shall support pagination, virtual scroll, or lazy loading.
- The system should support quick navigation from holdings to asset detail and from asset detail to history.

- **Trade-entry usability**
- Numeric stepper controls shall be available for price and quantity.
- The form should display latest price as a reference if market data is available.
- The system should show a lightweight pre-submit summary for the trade impact.

- **Responsive polish**
- On desktop, dense data shall use tables and multi-column panels.
- On mobile web, the layout shall fall back to stacked cards and simplified lists similar to the screenshot behavior.
- Key actions like submit and filter apply should remain visible in long pages, preferably via sticky controls.

**P2 Requirements**

- **Social/share features**
- The trade form may support an optional “share to social/community” toggle.
- Analysis pages may support sharing/exporting charts or metrics.

- **Customization**
- The user may customize visible benchmarks, preferred currency, or default market tab.
- The user may reorder holdings or market groups by preference.

- **Advanced interactions**
- The system may support saved filter presets for analysis pages.
- The system may support keyboard shortcuts for search and trade entry.
- The system may support collapsible side panels or resizable chart/table sections on desktop.

- **Data exploration**
- Users may drill down from ranked P&L items into transaction-level explanations.
- Users may view additional derived metrics such as average holding period, realized vs unrealized P&L split, and asset allocation changes over time.

- **Export and reporting**
- The system may support CSV/PDF export for holdings, transactions, and analysis summaries.
- The system may support printable account/asset detail views.

- **Visual enhancements**
- The system may include subtle motion for expand/collapse, chart loading, and state transitions.
- The system may provide theme adjustments or light-mode support if product strategy requires it.

**Non-Functional UX Requirements**

- **Consistency**
- Profit/loss colors, metric labels, and numeric formatting shall remain consistent across all pages.
- Tabs, segmented controls, and expand/collapse patterns shall behave consistently.

- **Performance**
- Overview and history pages should load key visible content quickly enough to feel immediate in standard browser conditions.
- Charts should progressively render without blocking the rest of the page.

- **Accessibility**
- Text contrast shall remain readable in dark theme.
- Interactive elements shall have clear focus states on web.
- Key flows such as trade entry and navigation should be keyboard accessible.

- **Trust and clarity**
- The UI shall show when data is delayed, reference-only, or non-real-time.
- The UI shall show clear explanatory text where calculations may differ due to timing, exchange rate, or settlement rules.

**Recommended MVP Cut**

- `P0` only = usable first release
- Best first public release = all `P0` + benchmark comparison, calendar, sorting, and historical holdings from `P1`

**Suggested PRD Epics**

- `Epic 1` Portfolio Overview
- `Epic 2` Add Trade Workflow
- `Epic 3` Transaction History
- `Epic 4` P&L Analysis
- `Epic 5` Asset Analysis
- `Epic 6` Asset Detail
- `Epic 7` Responsive Web and Shared UX States
