**Scope**

- The feature set covers portfolio management for simulated or manual investing records.
- Core modules inferred from the screenshots are: `Portfolio Overview`, `Add Trade`, `Transaction History`, `P&L Analysis`, `Asset Analysis`, and `Asset Detail`.
- The web version should preserve the same information architecture and workflows as mobile, while adapting layout and interaction patterns for larger screens.

**1. Portfolio Overview**

- The system shall display a top-level portfolio summary for the selected account/portfolio.
- The summary shall include at minimum: `total market value`, `today's reference P&L`, `floating P&L`, `floating P&L rate`, `cumulative P&L`, and `cumulative P&L rate`.
- The user shall be able to switch between portfolios/accounts from a visible selector near the top of the page.
- The user shall be able to show/hide sensitive financial amounts via an eye icon or equivalent toggle.
- The page shall provide quick actions for at least: `Add Trade`, `Historical Holdings`, `Transaction History`, and optionally `Bank/Securities Transfer`.
- The system shall group holdings by market or asset region, such as `A-shares`, `US stocks`, `HK stocks`.
- For each market group, the system shall display aggregate metrics such as `market value`, `floating P&L`, and `cumulative P&L`.
- The user shall be able to expand/collapse each market group.
- Within each expanded group, the system shall display an itemized holdings list.
- Each holding row shall include at minimum: `asset name`, `ticker/code`, `market value`, `quantity`, `current price`, `cost basis`, `cumulative P&L`, and `P&L rate`.
- Positive and negative values shall be visually differentiated using color.

**2. Add Trade**

- The system shall provide an `Add Trade` entry point from the portfolio overview and/or main navigation.
- The trade form shall support multiple trade types, at minimum: `Buy`, `Sell`, `Dividend/Corporate Action`, and `Stock Split/Reverse Split`.
- The user shall be able to choose or confirm the target portfolio/account before submitting the trade.
- The user shall be able to search and select a security by `name`, `ticker/code`, or phonetic input.
- The trade form shall display the latest market price when available.
- The user shall be able to set the transaction date.
- The form shall allow entry of `price` and `quantity`.
- The form shall provide increment/decrement controls for numeric fields such as price and quantity.
- The form shall support commission input, including a commission rate type selector.
- The form shall support tax input, including a tax rate type selector.
- The form shall allow a free-text note with a character limit.
- The form shall provide an optional share-to-social toggle or equivalent integration switch if that feature is included in product scope.
- The submit button shall remain disabled until required fields are valid.
- On successful submission, the system shall update both holdings and transaction history immediately or after refresh.
- For sell operations, the system shall validate that sell quantity does not exceed available holdings unless short-selling is explicitly supported.
- For dividend/corporate action entries, the form shall adapt fields so only relevant inputs are shown.
- For stock split entries, the form shall capture the split ratio and apply it to holdings calculations.

**3. Transaction History**

- The system shall provide a `Transaction History` page accessible from navigation and from the overview page.
- Transaction records shall be grouped by month.
- Each month section shall be expandable/collapsible.
- The system shall display an empty state such as `No transactions this month` when a month has no records.
- Each transaction row shall display at minimum: `asset name`, `transaction type/action`, `price`, `quantity`, `transaction amount`, and `date`.
- Transaction actions shall be clearly labeled, for example `Buy`, `Sell`, `Dividend`, `Split`.
- The system shall support chronological browsing across multiple months and years.
- The history view shall preserve grouping and visual hierarchy in both desktop and mobile web layouts.
- The user shall be able to navigate from a transaction record to related asset details if supported.

**4. P&L Analysis**

- The system shall provide a dedicated `P&L Analysis` page.
- The page shall support filtering by market or asset type, such as `HK`, `US`, `A-share`, `Funds`, `Futures`.
- The page shall support date filtering, including an `All Dates` option and narrower date ranges.
- The page shall display an aggregate cumulative P&L number for the selected filters.
- The page shall display summary metrics including at minimum: `total profit`, `total loss`, and `win rate`.
- The page shall display a ranking section for `Top Profit` and `Top Loss`.
- The user shall be able to switch between top profit and top loss views.
- Each ranked item shall display at minimum: `rank`, `asset name`, `ticker`, and `P&L amount`.
- The page shall show the number of securities included in the analysis and the last update date when relevant.
- The page shall include explanatory notes where calculation timing or exchange-rate timing may cause minor discrepancies.

**5. Asset Analysis**

- The system shall provide an `Asset Analysis` page focused on overall account composition and trends.
- The page shall support multiple tabs or sections, at minimum: `Asset Analysis`, `P&L Analysis`, and `New Stock/Subscribed IPO Analysis` if applicable.
- The asset overview section shall display total assets in the selected currency.
- The user shall be able to switch the analysis mode between `by asset class` and `by currency`.
- The page shall visualize asset composition using a chart, such as a donut, ring, or semicircle chart.
- The composition chart shall show percentage allocation for major categories such as `cash` and `stocks`.
- The page shall provide a trend analysis section with date presets, at minimum: `last 1 week`, `last 1 month`, and `year to date`.
- The page shall provide advanced filter options for the trend section.
- The page shall display a returns trend chart with benchmark comparisons.
- The user shall be able to view cumulative return and return-rate metrics for the selected period.
- The chart legend shall identify each benchmark or index line.
- The selected benchmark comparison method shall be visible, such as time-weighted return.
- The page shall also support an `asset net value trend` chart, including beginning value, ending value, and current-day gain/loss.

**6. Calendar / Monthly Performance View**

- The system shall provide a monthly performance calendar view.
- The user shall be able to switch between `month` and `year` modes.
- The user shall be able to select the displayed month/year.
- Each day cell in month view shall show the daily profit/loss amount and daily return rate where data exists.
- Positive and negative daily values shall be color coded.
- The system shall display aggregate metrics for the selected month, including monthly return amount and return rate.
- The page shall include a chart below the calendar to visualize daily performance distribution or trend.

**7. Asset Detail**

- The system shall provide a detailed page for a single asset or holding.
- The asset detail page shall display current total market value in the relevant currency.
- The page shall display `total assets`, `cash`, and `principal/cost` if applicable for that asset or sub-account.
- The page shall display key performance metrics such as `floating P&L`, `floating P&L rate`, `cumulative P&L`, and `cumulative P&L rate`.
- The page shall include a return trend chart.
- The user shall be able to switch chart ranges, such as `1 month`, `3 months`, `1 year`, `3 years`, and `all`.
- The trend chart shall compare the asset/account against at least one benchmark index.
- The selected range shall update summary percentages for both the portfolio and benchmark.
- The page shall preserve readable values and labels across different currencies.

**8. Navigation and Information Architecture**

- The system shall organize features into clear top-level areas equivalent to the mobile app’s account/investment section.
- The web version shall replace bottom-tab mobile navigation with a desktop-appropriate pattern such as left navigation, top tabs, or both.
- The user shall be able to move easily between `Overview`, `Add Trade`, `History`, `Analysis`, and `Detail`.
- Tabs and segmented controls shall indicate active state clearly.

**9. Responsive Web Adaptation**

- The web UI shall support desktop, tablet, and mobile web breakpoints.
- On desktop, dense data views shall prefer tables and multi-column layouts.
- On smaller screens, the UI shall collapse into stacked cards or simplified lists similar to the mobile screenshots.
- Charts, filters, and forms shall remain usable without horizontal overflow at supported breakpoints.
- Important actions such as `Add` or `Submit` shall remain visible and accessible on smaller screens.

**10. Interaction Requirements**

- Expand/collapse sections shall animate or update clearly enough for users to understand state changes.
- Filters, tabs, and date ranges shall update visible data immediately after selection or after an explicit apply action.
- Numeric values shall be formatted consistently by market and currency.
- The system shall distinguish informational text, disabled states, and active states through consistent contrast and hierarchy.
- Form inputs shall validate inline and show clear error messaging.
- Hover states should exist for web, while click/tap behavior should remain primary.

**11. Data and Display Rules**

- The system shall support multiple currencies such as `CNY`, `USD`, and `HKD`.
- The system shall display market-specific asset codes and names.
- The system shall support benchmark/index comparisons for at least major market indices.
- Dates shall be displayed in a localized, consistent format.
- Monetary values shall be rounded and formatted according to product rules while preserving precision where needed for calculations.
- P&L values shall be computed consistently across overview, analysis, and detail pages.

**12. Empty, Loading, and Error States**

- The system shall show meaningful empty states for no holdings, no transactions, and no analysis data.
- The system shall provide loading placeholders or spinners for charts, holdings tables, and transaction lists.
- If market data is unavailable, the UI shall indicate that the latest price or benchmark data is not available.
- If filters return no results, the system shall show a no-data state rather than a blank area.

**13. Visual/UX Requirements**

- The UI shall use a dark theme as the default visual style if following the reference direction.
- The design shall emphasize a high-density financial dashboard style with strong typographic hierarchy.
- Profit/loss colors shall remain consistent across all pages and charts.
- Key KPIs shall be visually prominent and easy to scan.
- Secondary labels, timestamps, and hints shall be lower contrast but still readable.
- Cards, sections, and tables shall use subtle dividers and spacing to preserve structure without visual clutter.

**14. Recommended Web Enhancements**

- The web version should support sticky filters or sticky page headers for long analytical pages.
- The holdings and transaction tables should support sorting by major numeric columns.
- The history and ranking views should support pagination or lazy loading for large data sets.
- The charts should support hover tooltips, legends, and export or screenshot actions if needed.
- Search should support keyboard navigation and recent selections for faster trade entry.

**15. Assumptions from the Screenshots**

- This appears to be a manual or simulated portfolio tracking workflow rather than a live brokerage-only flow.
- Holdings, transactions, P&L analysis, and asset analysis are tightly connected and should use the same underlying transaction ledger.
- Multi-market and multi-currency support are core requirements, not optional enhancements.
