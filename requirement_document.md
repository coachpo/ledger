# Software Requirements Specification (SRS)

## Portfolio Management and Decision-Support Application

Version: Draft 1.0
Format: Markdown
Target scope: Single user, single IBKR account, import-based portfolio analytics and decision support

---

## 1. Introduction

### 1.1 Purpose

This document specifies the software requirements for a portfolio management application that imports Interactive Brokers (IBKR) statements, reconstructs account history, visualizes holdings and transactions, overlays trades on TradingView charts, computes portfolio analytics, and supports what-if simulations for investment decisions.

### 1.2 Scope

The application is intended for:

- one user,
- one brokerage account,
- IBKR statement imports only,
- portfolio analysis and decision support,
- no broker-side order execution.

The application shall use uploaded IBKR statements as the accounting source of truth. It shall use TradingView libraries for charting and technical-analysis presentation, subject to licensing and datafeed constraints. IBKR supports downloadable/customizable statements and custom date-range reporting in multiple formats, which fits the chosen import-only scope. TradingView’s charting libraries are hosted by the integrator and connected to data through a datafeed API, while widgets are TradingView-hosted; TradingView also states that Advanced Charts and Trading Platform libraries are not provided for personal/hobby/testing use and are licensed for public web projects/applications. ([Interactive Brokers][1])

### 1.3 Product objective

The product shall provide a unified environment to:

- ingest and normalize broker statement data,
- track portfolio and account changes over time,
- visualize trades in market context,
- summarize current holdings and account finances,
- combine holdings with technical indicators,
- support historical counterfactual simulations.

### 1.4 Basis from sample statement

The provided IBKR CSV sample demonstrates that the application must handle at least:

- statement metadata,
- net asset value summaries,
- change in NAV,
- open positions,
- mark-to-market performance,
- realized and unrealized performance,
- cash report,
- trades,
- deposits and withdrawals,
- interest,
- financial instrument information.

The sample also shows:

- fractional share quantities,
- statement-period summary rows,
- event-level rows,
- instrument reference data including Conid,
- cash and performance data that must be separated from trade-event storage.

---

## 2. Intended user

### 2.1 Primary user

The primary and only supported user is the account owner who wants to monitor portfolio status, review historical activity, and test alternative trade decisions.

### 2.2 User goals

The user shall be able to:

- import IBKR statements safely,
- avoid duplicate data even when statements overlap,
- inspect holdings and account balances,
- review trade history on charts,
- understand realized and unrealized performance,
- evaluate alternative buy/sell scenarios,
- view technical indicators together with holdings.

---

## 3. Definitions

### 3.1 Terms

**Canonical event**
A normalized transaction-like record stored once, even if present in multiple overlapping statements.

**Snapshot record**
A statement-period summary row such as NAV, cash summary, or open positions at period end.

**Overlap**
A condition in which two or more imported statements cover the same date range partially or fully.

**Deduplication**
The process of identifying logically identical records across imports and preventing double counting.

**Cost basis method**
The accounting rule used to determine which acquisition lots are closed on a sale.

**Scenario layer**
A separate simulation workspace that modifies hypothetical outcomes without altering imported historical truth.

**Instrument mapping**
The process of mapping an IBKR instrument to the symbol and metadata needed for chart display.

---

## 4. System context and external dependencies

### 4.1 External systems

The application depends on:

- uploaded IBKR statements,
- TradingView charting libraries,
- a market-data/datafeed layer compatible with TradingView libraries,
- application storage for normalized data and raw files.

### 4.2 TradingView integration model

The application shall use TradingView libraries rather than widgets.

The SRS assumes use of the TradingView Advanced Charts library for chart rendering, indicators, studies, and trade overlays. TradingView documents that libraries are hosted by the integrator and connected to market data through either the built-in UDF adapter or a custom Datafeed API implementation. The documentation also shows APIs for drawings, studies, and execution-style buy/sell arrows. ([TradingView][2])

### 4.3 Critical dependency constraint

TradingView explicitly states that Advanced Charts and Trading Platform libraries are not provided for personal use, hobbies, studies, or testing, and are licensed for public web projects/applications. Because this product is intended for one user, this is a licensing and delivery risk that must be resolved before implementation. ([TradingView][2])

### 4.4 Data retrieval constraint

This SRS treats TradingView primarily as a charting-library integration, not as an assured backend market-data provider. The TradingView documentation states that the library itself does not provide market data and must be connected to your own data source or a third-party provider through the datafeed layer. Therefore, any requirement to persist historical bars, compute backend indicators, or power simulations from chart data shall depend on a separately approved market-data source unless the final TradingView agreement explicitly grants broader rights. This is an architectural inference from the library/datafeed model. ([TradingView][3])

---

## 5. High-level product behavior

The system shall:

- import one or more IBKR CSV statements,
- normalize statement data into structured records,
- deduplicate overlapping imports,
- maintain a time-aware account history,
- present dashboards and holdings summaries,
- render chart views with transaction overlays,
- display technical indicator context,
- support scenario simulations,
- preserve traceability from normalized records back to original source files and rows.

---

## 6. Functional requirements

## 6.1 Statement import and ingestion

### FR-IMP-001

The system shall allow the user to upload IBKR monthly statements and IBKR custom-period statements in CSV format.

### FR-IMP-002

The system shall extract statement metadata, including:

- statement title,
- statement period,
- generation timestamp,
- account identifier,
- base currency,
- account type where present.

### FR-IMP-003

The system shall preserve each uploaded raw statement file.

### FR-IMP-004

The system shall assign each uploaded file an import batch identifier.

### FR-IMP-005

The system shall validate statement structure before committing normalized data.

### FR-IMP-006

The system shall reject or quarantine malformed files while preserving an import error log.

### FR-IMP-007

The system shall parse, where present, the following sections or their equivalents:

- Account Information
- Net Asset Value
- Change in NAV
- Open Positions
- Cash Report
- Trades
- Deposits & Withdrawals
- Interest
- Realized & Unrealized Performance Summary
- Mark-to-Market Performance Summary
- Financial Instrument Information

### FR-IMP-008

The system shall support fractional quantities and decimal monetary values without forced rounding during ingestion.

### FR-IMP-009

The system shall support repeated imports of the same file without duplicating normalized records.

### FR-IMP-010

The system shall surface import status as one of:

- completed,
- completed with warnings,
- failed.

---

## 6.2 Deduplication and overlap handling

### FR-DUP-001

The system shall detect whether a newly uploaded statement overlaps with one or more previously imported statements.

### FR-DUP-002

The system shall deduplicate transactional records across overlapping statement imports.

### FR-DUP-003

The system shall distinguish transactional/event records from summary/snapshot records.

### FR-DUP-004

The system shall never aggregate overlapping summary/snapshot rows as if they were additive events.

### FR-DUP-005

The system shall store one canonical copy of each logical transaction-like event.

### FR-DUP-006

The system shall preserve source references from all contributing files for each canonical event.

### FR-DUP-007

The system shall support file-level deduplication using a file checksum or equivalent file identity mechanism.

### FR-DUP-008

The system shall support record-level deduplication even when overlapping files are not byte-identical.

### FR-DUP-009

The system shall create a dedup fingerprint for each normalized event using the most stable available fields.

### FR-DUP-010

For trade events, the fingerprint should prefer:

- account id,
- event type,
- asset category,
- Conid when available, otherwise symbol,
- trade datetime,
- quantity,
- price,
- proceeds,
- commission/fee,
- currency,
- discriminator/code.

### FR-DUP-011

For cash movements, interest, or other account events, the fingerprint should prefer:

- account id,
- event type,
- date or settle date,
- currency,
- amount,
- description,
- source section.

### FR-DUP-012

If two records appear to refer to the same event but differ slightly, the system shall:

- keep one canonical event,
- preserve both source rows,
- flag a data conflict,
- prevent silent double counting.

---

## 6.3 Data normalization

### FR-NORM-001

The system shall normalize imported data into structured entities rather than storing all content only as raw statement rows.

### FR-NORM-002

The system shall map instrument reference data from the statement to normalized instrument records.

### FR-NORM-003

The system shall prefer IBKR Conid as the primary instrument identifier when available.

### FR-NORM-004

The system shall store symbol, description, exchange, security identifier, and type where present.

### FR-NORM-005

The system shall normalize all dates and datetimes into a consistent internal timezone strategy.

### FR-NORM-006

The system shall preserve both native currency amounts and base-currency-relevant values where present in the statement.

---

## 6.4 Portfolio activity tracking

### FR-ACT-001

The system shall display position changes over time for each holding.

### FR-ACT-002

The system shall display account balance changes over time.

### FR-ACT-003

The system shall display account events including:

- deposits,
- withdrawals,
- interest,
- commissions,
- fees,
- corporate actions when derivable,
- other transaction-related activities.

### FR-ACT-004

The system shall provide a chronological activity feed.

### FR-ACT-005

The system shall allow the user to filter activity by:

- date range,
- instrument,
- event type,
- section origin.

### FR-ACT-006

The system shall allow drill-down from summary metrics to the underlying normalized events.

---

## 6.5 TradingView chart integration

### FR-TV-001

The system shall integrate TradingView libraries rather than widgets.

### FR-TV-002

The system shall render an interactive chart for a selected instrument.

### FR-TV-003

The system shall map imported IBKR instruments to chart symbols needed by the TradingView integration layer.

### FR-TV-004

The system shall support a symbol-mapping workflow for unresolved or ambiguous instruments.

### FR-TV-005

The system shall display buy and sell transactions as visual markers on the corresponding chart.

### FR-TV-006

Each trade marker shall expose:

- side,
- quantity,
- date/time,
- execution price,
- fees where applicable.

### FR-TV-007

The system shall distinguish buys and sells visually.

### FR-TV-008

The system shall support multiple markers for the same symbol over time.

### FR-TV-009

The system shall support chart zooming to a selected transaction window.

### FR-TV-010

The system shall allow technical studies to be displayed on the chart.

### FR-TV-011

The system shall allow indicator selection and configuration from the UI.

### FR-TV-012

The system shall support chart-side rendering of common indicators, including at minimum:

- MACD,
- MA7,
- additional moving averages,
- Ichimoku Cloud.

### FR-TV-013

If the licensed TradingView library or approved datafeed cannot support a requested symbol or study, the system shall display a clear fallback or unavailable state.

---

## 6.6 Technical indicators and portfolio enrichment

### FR-IND-001

The system shall present technical indicators in both chart context and holdings context.

### FR-IND-002

The system shall support, at minimum for MVP:

- SMA 7,
- SMA 20,
- SMA 50,
- SMA 200,
- EMA 7,
- EMA 20,
- MACD,
- RSI 14,
- Ichimoku Cloud,
- Bollinger Bands,
- volume and volume average.

### FR-IND-003

The system shall allow the user to configure which indicators are visible.

### FR-IND-004

The system shall display a technical snapshot for each supported current holding.

### FR-IND-005

The holdings technical snapshot should include derived states such as:

- above/below MA7,
- MACD bullish/bearish crossover,
- RSI overbought/oversold/neutral,
- above/in/below Ichimoku cloud.

### FR-IND-006

The system shall support time-aware indicator context for historical trade review where historical indicator data is available.

### FR-IND-007

The system shall clearly label whether an indicator value is:

- chart-only,
- computed and stored,
- current snapshot,
- historical snapshot,
- unavailable.

---

## 6.7 Holdings summary

### FR-HOLD-001

The system shall provide a detailed holding summary for each current holding.

### FR-HOLD-002

Each holding summary shall include at minimum:

- symbol,
- instrument name,
- quantity,
- current price,
- market value,
- cost basis,
- average purchase price,
- unrealized P/L,
- unrealized P/L percent,
- realized P/L where relevant,
- total P/L,
- portfolio weight,
- currency,
- last market-data update timestamp.

### FR-HOLD-003

The system shall support sorting and filtering the holdings table.

### FR-HOLD-004

The system shall allow the user to open a holding from the table into a detailed view with trade history and chart.

---

## 6.8 Account financial summary

### FR-FIN-001

The system shall provide an account-level financial summary.

### FR-FIN-002

The financial summary shall include, where available:

- cash balance,
- net asset value,
- market value of positions,
- available funds,
- buying power if available,
- margin information,
- realized P/L,
- unrealized P/L,
- total deposits,
- total withdrawals,
- fees and commissions,
- interest,
- dividends if present,
- base currency.

### FR-FIN-003

The system shall clearly indicate when a displayed value is:

- imported from statement,
- derived by the application,
- estimated from market data,
- hypothetical from simulation.

### FR-FIN-004

The system shall allow the user to inspect the source statement rows behind a displayed financial metric where traceable.

---

## 6.9 Analytics and dashboards

### FR-AN-001

The system shall provide a dashboard summarizing current account status.

### FR-AN-002

The dashboard shall provide visualizations for:

- portfolio value over time,
- cash vs invested value over time,
- realized vs unrealized P/L over time,
- deposits and withdrawals over time,
- current allocation by holding,
- recent activity timeline.

### FR-AN-003

The system should provide additional analytics including:

- buy vs sell distribution,
- trade count over time,
- turnover,
- best and worst contributors,
- open position concentration.

### FR-AN-004

The system shall support custom date-range filtering for analytics.

### FR-AN-005

The system shall preserve historical state sufficiently to reconstruct portfolio snapshots for a selected date.

---

## 6.10 Simulation and what-if analysis

### FR-SIM-001

The system shall support hypothetical simulations on top of imported history.

### FR-SIM-002

The system shall not modify canonical imported history when running simulations.

### FR-SIM-003

The system shall support at minimum the following scenario types:

- what if a buy had not occurred,
- what if a sell had not occurred,
- what if a trade had happened at a different date,
- what if a trade had happened at a different price,
- what if a trade had used a different quantity.

### FR-SIM-004

The system shall allow manual user editing of hypothetical:

- trade date,
- trade price,
- trade quantity.

### FR-SIM-005

The system shall include fees in simulations by default.

### FR-SIM-006

The system shall include slippage in simulations by default.

### FR-SIM-007

The system shall allow slippage configuration as either:

- fixed amount,
- basis points,
- disabled.

### FR-SIM-008

The system shall exclude taxes from MVP simulations.

### FR-SIM-009

The system shall include dividends and other relevant income events in simulations when the required data is available.

### FR-SIM-010

The system shall show, for each simulation:

- hypothetical current position,
- hypothetical market value,
- hypothetical realized/unrealized P/L,
- difference versus actual,
- cash impact,
- income difference where relevant.

### FR-SIM-011

The system shall allow the user to compare actual and hypothetical outcomes side by side.

---

## 6.11 Cost basis and accounting configuration

### FR-ACC-001

The system shall support a user-configurable cost basis method.

### FR-ACC-002

The MVP shall support:

- FIFO,
- Average Cost.

### FR-ACC-003

FIFO shall be the default method.

### FR-ACC-004

The system shall support fractional lots.

### FR-ACC-005

Partial sells shall reduce open lots according to the selected cost basis method.

### FR-ACC-006

The system shall preserve a lot-depletion audit trail for realized P/L calculations.

### FR-ACC-007

The system shall treat buy-side fees as basis adjustments and sell-side fees as proceeds reductions for app-calculated analytics.

### FR-ACC-008

The system shall clearly distinguish broker-reported P/L from app-calculated P/L when the configured cost basis method differs from broker reporting.

---

## 6.12 Corporate actions

### FR-CA-001

The system shall support explicit normalized handling of corporate actions when they can be derived from imported data.

### FR-CA-002

Supported event types should include:

- stock split,
- reverse split,
- ticker change,
- merger,
- spin-off,
- cash in lieu.

### FR-CA-003

Corporate actions shall be stored as explicit events and not only as silent rewrites of positions.

### FR-CA-004

If a corporate action cannot be resolved confidently from imported data, the system shall flag it for review.

---

## 6.13 Search, filters, and exports

### FR-UX-001

The system shall support filtering by date range across major views.

### FR-UX-002

The system shall support searching by symbol and instrument name.

### FR-UX-003

The system shall support filtering by event type.

### FR-UX-004

The system shall support CSV export for tabular data views.

### FR-UX-005

The system should support XLSX export for multi-sheet reports.

### FR-UX-006

The system should support PNG export for chart snapshots.

---

## 7. Data model requirements

## 7.1 Core entities

The application shall maintain at minimum the following entities:

- User
- BrokerageAccount
- RawImportFile
- ImportBatch
- StatementMetadata
- SourceRow
- Instrument
- InstrumentMapping
- CanonicalEvent
- TradeEvent
- CashEvent
- InterestEvent
- FeeEvent
- CorporateActionEvent
- SnapshotRecord
- PositionLot
- PositionSnapshot
- CashSnapshot
- AccountSnapshot
- IndicatorSnapshot
- SimulationScenario
- SimulationTradeOverride
- SimulationResult
- ReconciliationIssue

## 7.2 Entity expectations

### 7.2.1 RawImportFile

Shall store:

- file checksum,
- original filename,
- upload timestamp,
- parse status,
- preserved raw payload location.

### 7.2.2 ImportBatch

Shall store:

- account id,
- import timestamp,
- statement period start/end,
- overlap flag,
- import summary,
- warning count,
- error count.

### 7.2.3 Instrument

Shall store where available:

- Conid,
- symbol,
- description,
- exchange,
- security id,
- underlying,
- multiplier,
- type,
- currency.

### 7.2.4 CanonicalEvent

Shall store:

- event id,
- event type,
- event fingerprint,
- effective date/time,
- normalized monetary fields,
- normalized quantity fields,
- linked instrument when applicable,
- linked source rows,
- dedup status.

### 7.2.5 SnapshotRecord

Shall store:

- snapshot type,
- statement date/period,
- metric name,
- metric value,
- currency,
- source linkage.

### 7.2.6 PositionLot

Shall store:

- acquisition event,
- open quantity,
- original quantity,
- unit cost,
- total basis,
- open/closed status,
- depletion history.

### 7.2.7 IndicatorSnapshot

Shall store:

- symbol/instrument,
- timestamp,
- timeframe,
- indicator name,
- indicator parameters,
- value payload,
- value source,
- availability status.

### 7.2.8 SimulationScenario

Shall store:

- scenario id,
- base dataset version,
- scenario assumptions,
- user overrides,
- comparison results.

---

## 8. Business rules

### BR-001

Imported IBKR statements are the accounting source of truth for actual history.

### BR-002

Overlapping statements shall be merged through deduplication, not stacked additively.

### BR-003

Statement summary rows shall be treated as snapshots or reconciliation references, not as additive transactions.

### BR-004

Transaction-like rows shall be converted into canonical events.

### BR-005

A canonical event may have multiple source-row references across overlapping imports.

### BR-006

Conid shall be preferred over symbol when identifying instruments.

### BR-007

If Conid is absent, symbol plus additional metadata may be used for identification.

### BR-008

Fractional quantities shall be preserved exactly at import precision.

### BR-009

The default cost basis method shall be FIFO.

### BR-010

The selected cost basis method shall affect app-calculated analytics and simulations but shall not overwrite imported broker-reported values.

### BR-011

Buy fees shall increase app-calculated cost basis.

### BR-012

Sell fees shall reduce app-calculated proceeds.

### BR-013

Taxes are out of scope for MVP simulation results.

### BR-014

Dividends and other income shall be included in simulations when relevant data is present.

### BR-015

Actual history shall be immutable after import, except for administrative corrections or reprocessing.

### BR-016

All derived metrics shall be traceable either to canonical events, snapshots, or market/indicator data inputs.

### BR-017

When symbol mapping to chart data fails, the position remains valid in accounting views even if no chart is available.

### BR-018

If indicator data is unavailable for a holding, the portfolio summary shall show unavailable rather than a fabricated value.

---

## 9. Non-functional requirements

## 9.1 Accuracy and reconciliation

### NFR-ACC-001

The system shall preserve sufficient data lineage to reconcile displayed values back to imported statements.

### NFR-ACC-002

The system shall distinguish imported values from derived values and hypothetical values.

### NFR-ACC-003

The system shall not silently modify historical event data during deduplication.

### NFR-ACC-004

The system shall log data conflicts discovered during overlap handling.

## 9.2 Performance

### NFR-PERF-001

Typical statement imports shall complete within a reasonable interactive time for single-account usage.

### NFR-PERF-002

Core dashboards and holdings views shall load fast enough for interactive use after import processing is complete.

### NFR-PERF-003

Filtering and sorting of holdings and activities shall remain responsive on typical single-user datasets.

## 9.3 Reliability

### NFR-REL-001

A failed import shall not corrupt previously imported data.

### NFR-REL-002

Import processing shall be transactional or recoverable.

### NFR-REL-003

The system shall support deterministic reprocessing from preserved raw files.

## 9.4 Security and privacy

### NFR-SEC-001

Uploaded statements and derived financial data shall be stored securely.

### NFR-SEC-002

Access shall be restricted to the single authorized user.

### NFR-SEC-003

Sensitive account identifiers and financial data shall be protected in logs and diagnostics.

## 9.5 Maintainability

### NFR-MNT-001

Parser logic, normalization logic, dedup logic, analytics logic, simulation logic, and chart integration logic shall be modular.

### NFR-MNT-002

New statement parsers or revised section handlers shall be testable independently.

### NFR-MNT-003

Indicator and symbol-mapping logic shall be configurable rather than hard-coded where practical.

## 9.6 Auditability

### NFR-AUD-001

The system shall preserve raw source files and source-row references.

### NFR-AUD-002

The system shall log imports, dedup actions, conflicts, and simulation runs.

## 9.7 Usability

### NFR-UX-001

The application shall present financial information in a form understandable without reading raw broker statements.

### NFR-UX-002

The application shall surface warnings, unavailable data states, and reconciliation issues clearly.

---

## 10. Acceptance criteria

## 10.1 Import and parsing

### AC-IMP-001

Given a valid IBKR monthly CSV statement, when the user uploads it, then the system imports statement metadata, trades, cash movements, positions, and summaries successfully.

### AC-IMP-002

Given a valid IBKR custom-period CSV statement, when the user uploads it, then the system imports it using the same normalization model as monthly statements.

### AC-IMP-003

Given a malformed or unsupported CSV, when the user uploads it, then the system marks the import as failed and reports the reason.

## 10.2 Overlap and deduplication

### AC-DUP-001

Given two statements with overlapping periods containing the same trade rows, when both are imported, then the trade appears only once in canonical events.

### AC-DUP-002

Given two overlapping statements containing the same deposit row, when both are imported, then the deposit appears only once in canonical events.

### AC-DUP-003

Given two overlapping statements containing the same period-end NAV summary, when both are imported, then the NAV summary is not double counted as account activity.

### AC-DUP-004

Given duplicate raw file uploads, when the same file is imported twice, then no duplicate canonical events are created.

## 10.3 Portfolio views

### AC-HOLD-001

Given imported holdings data, when the user opens the holdings view, then each holding shows quantity, market value, cost basis, average price, and P/L metrics.

### AC-FIN-001

Given imported account summaries, when the user opens the financial summary, then cash, NAV, and related account metrics are shown with value-source labeling.

### AC-ACT-001

Given imported transactional history, when the user opens the activity timeline, then trades, deposits, withdrawals, interest, and other events appear in chronological order.

## 10.4 Charting and indicators

### AC-TV-001

Given a mapped symbol and available chart data, when the user opens the chart, then buy and sell markers are displayed at the corresponding historical points.

### AC-TV-002

Given a supported holding and available indicator data, when the user opens the holdings view, then configured technical indicator snapshots appear for that holding.

### AC-TV-003

Given a symbol that cannot be mapped to chart data, when the user opens the chart view, then the system shows a clear unavailable state without breaking portfolio accounting views.

## 10.5 Simulations

### AC-SIM-001

Given an imported sell event, when the user runs a “what if I had not sold” simulation, then the system shows hypothetical current position and hypothetical value without altering actual history.

### AC-SIM-002

Given an imported buy event, when the user changes hypothetical trade date, price, or quantity, then the simulation recalculates scenario outputs accordingly.

### AC-SIM-003

Given fees and slippage enabled, when the user runs a simulation, then the resulting hypothetical P/L includes both effects.

---

## 11. Recommended MVP boundary

The MVP should include:

- IBKR CSV import,
- raw file preservation,
- overlap detection and deduplication,
- canonical trade/cash/interest event normalization,
- holdings summary,
- financial summary,
- activity timeline,
- TradingView chart integration using libraries,
- buy/sell trade overlays,
- configurable common indicators,
- basic scenario analysis for skipped or modified trades.

The MVP should not require:

- multi-account support,
- tax engine,
- order placement,
- portfolio benchmark engine,
- advanced risk analytics,
- multi-user authorization.

---

## 12. Out of scope

The following are out of scope for this version:

- multiple users,
- multiple brokerage accounts,
- direct IBKR API sync,
- portfolio rebalancing automation,
- broker order routing,
- tax-lot filing and tax reports,
- options/futures-specific advanced analytics unless added later,
- social features,
- mobile app requirements.

---

## 13. Risks and implementation notes

### 13.1 TradingView licensing risk

The chosen “use libraries” direction depends on obtaining and maintaining an appropriate TradingView library license compatible with the intended deployment model. ([TradingView][2])

### 13.2 Market-data dependency risk

Because the library expects a datafeed rather than bundling market data itself, backend persistence of bars and indicators requires a separately approved market-data path. ([TradingView][3])

### 13.3 Parsing variability risk

IBKR statement layouts may vary by section selection, date range, language, or account configuration; parser design should therefore be section-aware and tolerant of optional sections. IBKR’s reporting tooling supports customizable/custom reports and multiple output formats, which makes variability likely. ([Interactive Brokers][4])

### 13.4 Reconciliation risk

App-calculated analytics may differ from broker-reported summaries if:

- cost basis method differs,
- fees are allocated differently,
- market data source differs from statement close values,
- indicator histories come from a separate source.

---

## 14. Recommended next document after this SRS

The next useful artifact would be a **system design specification** covering:

- parser architecture,
- dedup algorithm,
- normalized schema,
- import pipeline,
- symbol-mapping workflow,
- TradingView datafeed architecture,
- simulation engine design,
- UI screen map.

[1]: https://www.interactivebrokers.com/en/whyib/reporting.php?utm_source=chatgpt.com "Comprehensive Reporting | Interactive Brokers LLC"
[2]: https://www.tradingview.com/free-charting-libraries/?utm_source=chatgpt.com "Free Charting Library by TradingView"
[3]: https://www.tradingview.com/charting-library-docs/latest/connecting_data/?utm_source=chatgpt.com "Connecting data | Advanced Charts Documentation"
[4]: https://www.interactivebrokers.com/campus/trading-lessons/client-portal-reporting/?utm_source=chatgpt.com "Reporting Tools | Trading Lesson | Traders' Academy"
