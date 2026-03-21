# Backtest Module Design Spec

> Status: Historical design reference. Approved 2026-03-20, and much of it shipped by 2026-03-21 (`8fd7fee`), but this file still contains design-time detail that may drift from the live contract.

## Purpose

Add a backtest module to Ledger that simulates the self-reflection stock analysis loop over historical data. An LLM analyzes portfolio positions at configurable intervals, produces versioned reports, and executes simulated trades. Results are visualized with equity curves, drawdown charts, and benchmark comparisons.

This is an experimental simulation tool. No investment advice is provided.

## Architecture Overview

```
Frontend (Config + Poll + Results Dashboard)
    |
    | POST /backtests (create + launch)
    | GET  /backtests/{id} (poll status + results)
    v
Backend API (thin route handlers)
    |
    v
BacktestService (CRUD + thread launch)
    |
    v
BacktestEngine (ThreadPoolExecutor, dedicated DB session)
    |
    +-- Yahoo Finance (yfinance, parquet disk cache)
    +-- LLM (OpenAI SDK, custom base_url/api_key)
    +-- TradingOperationService (real trades on portfolio)
    +-- ReportService (store analysis as reports)
```

Key decisions:
- Background execution via in-process ThreadPoolExecutor (no Celery/Redis)
- Status tracked in `backtests` DB table (PENDING -> RUNNING -> COMPLETED/FAILED/CANCELLED)
- Frontend polls GET endpoint; stops when terminal status reached
- All trades go through existing TradingOperationService
- All analyses stored as real reports via existing reports infrastructure
- Market data cached to disk as parquet (one file per symbol)
- LLM config stored per-backtest, not globally

## Data Model

### New table: `backtests`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| portfolio_id | INTEGER FK -> portfolios.id | NOT NULL |
| name | VARCHAR(200) | NOT NULL |
| status | VARCHAR(20) | PENDING, RUNNING, COMPLETED, FAILED, CANCELLED |
| frequency | VARCHAR(10) | DAILY, WEEKLY, MONTHLY |
| start_date | DATE | NOT NULL |
| end_date | DATE | NOT NULL |
| current_cycle_date | DATE | NULL, progress indicator |
| total_cycles | INTEGER | NOT NULL |
| completed_cycles | INTEGER | DEFAULT 0 |
| template_id | INTEGER FK -> text_templates.id | NOT NULL |
| llm_base_url | VARCHAR(500) | NOT NULL |
| llm_api_key | VARCHAR(500) | NOT NULL, redacted in GET responses |
| llm_model | VARCHAR(200) | NOT NULL |
| price_mode | VARCHAR(20) | CLOSING_PRICE or LLM_DECIDED |
| llm_price_success_rate | NUMERIC(5,4) | NULL, only when LLM_DECIDED |
| commission_mode | VARCHAR(20) | FIXED, PERCENTAGE, ZERO |
| commission_value | NUMERIC(18,8) | DEFAULT 0 |
| benchmark_symbols | JSON | e.g. ["^GSPC", "^IXIC"] |
| results | JSON | NULL until COMPLETED |
| error_message | TEXT | NULL |
| created_at | TIMESTAMP | NOT NULL |
| updated_at | TIMESTAMP | NOT NULL |

Indexes: `ix_backtests_portfolio_id`, `ix_backtests_status`

### Reused tables

- `reports` -- each cycle stores analysis as a report with backtest metadata tags
- `trading_operations` -- BUY/SELL trades executed through existing service

Report metadata shape per cycle:
```json
{
  "tags": ["backtest", "backtest_42"],
  "analysis": {
    "backtestId": 42,
    "cycleDate": "2024-03-15",
    "reviewType": "backtest_daily"
  }
}
```

## API Design

### Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | /api/v1/backtests | List all backtests, newest first |
| POST | /api/v1/backtests | Create + launch backtest (returns PENDING, thread starts) |
| GET | /api/v1/backtests/{backtestId} | Get backtest with status, progress, and results |
| POST | /api/v1/backtests/{backtestId}/cancel | Request cancellation of running backtest |
| DELETE | /api/v1/backtests/{backtestId} | Delete (only if COMPLETED/FAILED/CANCELLED) |

### Create request

```json
{
  "name": "AAPL Daily Backtest 2024",
  "portfolioId": 5,
  "templateId": 12,
  "createTemplate": false,
  "templateName": null,
  "frequency": "DAILY",
  "startDate": "2024-01-02",
  "endDate": "2024-12-31",
  "llmBaseUrl": "http://localhost:11434/v1",
  "llmApiKey": "ollama",
  "llmModel": "qwen2.5:72b",
  "priceMode": "LLM_DECIDED",
  "llmPriceSuccessRate": "0.50",
  "commissionMode": "FIXED",
  "commissionValue": "1.00",
  "benchmarkSymbols": ["^GSPC", "^IXIC"]
}
```

When `createTemplate` is true and `templateId` is null, the backend creates a default analysis template first, stores its ID on the backtest row, then launches the simulation.

### Get response (running)

```json
{
  "id": 1,
  "name": "AAPL Daily Backtest 2024",
  "portfolioId": 5,
  "templateId": 12,
  "status": "RUNNING",
  "frequency": "DAILY",
  "startDate": "2024-01-02",
  "endDate": "2024-12-31",
  "currentCycleDate": "2024-06-15",
  "totalCycles": 252,
  "completedCycles": 115,
  "priceMode": "LLM_DECIDED",
  "llmPriceSuccessRate": "0.50",
  "commissionMode": "FIXED",
  "commissionValue": "1.00",
  "benchmarkSymbols": ["^GSPC", "^IXIC"],
  "results": null,
  "errorMessage": null,
  "createdAt": "2026-03-19T22:00:00Z",
  "updatedAt": "2026-03-19T22:35:00Z"
}
```

Note: `llmApiKey` is never returned in GET responses (redacted to "***").

### Get response (completed -- results populated)

The `results` JSON contains everything the frontend needs for charts:

```json
{
  "portfolio": {
    "startingValue": "100000.00",
    "endingValue": "118450.00",
    "totalReturn": "0.1845",
    "annualizedReturn": "0.1845",
    "maxDrawdown": "-0.0823",
    "sharpeRatio": "1.24",
    "totalTrades": 47,
    "winRate": "0.617",
    "totalCommission": "47.00"
  },
  "benchmarks": {
    "^GSPC": { "startingPrice": "4769.83", "endingPrice": "5881.63", "totalReturn": "0.2332" },
    "^IXIC": { "startingPrice": "15011.35", "endingPrice": "17685.94", "totalReturn": "0.1782" }
  },
  "equityCurve": [
    { "date": "2024-01-02", "value": "100000.00" }
  ],
  "benchmarkCurves": {
    "^GSPC": [{ "date": "2024-01-02", "value": "1.0000" }]
  },
  "drawdownCurve": [
    { "date": "2024-01-02", "value": "0.0000" }
  ],
  "trades": [
    {
      "cycleDate": "2024-01-15",
      "symbol": "AAPL",
      "side": "BUY",
      "quantity": "5",
      "requestedPrice": "185.50",
      "executedPrice": "184.40",
      "executed": true,
      "reportSlug": "backtest_1_aapl_daily_20240115"
    }
  ]
}
```

## Template System

### Two options in backtest config

1. **Use existing template** -- dropdown of stored templates
2. **Create default template** -- engine creates a stored template via existing template API, saved to `text_templates` table, editable in template editor for future runs

### Auto-created template content

The template contains LLM instructions only. The engine injects market data, portfolio state, and prior reports around it.

```markdown
# {{inputs.ticker}} Analysis ({{inputs.cycle_date}})

## Instructions
You are analyzing {{inputs.ticker}} for portfolio {{inputs.portfolio_name}}.
Analysis frequency: {{inputs.frequency}}.

CRITICAL: Today is {{inputs.cycle_date}}. Do NOT use any information
from after this date. If uncertain about timing, exclude it.

## Your Analysis
1. Assess the current business and market context
2. Review the prior analysis reports provided below
3. Identify what changed since last review
4. Decide: BUY, SELL, or HOLD for each position

## Response Format
Respond in this exact JSON:
{
  "overall_assessment": "brief portfolio summary",
  "decisions": [
    {
      "symbol": "TICKER",
      "action": "BUY|SELL|HOLD",
      "quantity": 5,
      "target_price": 185.50,
      "reasoning": "2-3 sentences"
    }
  ],
  "reflection": "what changed, what you got right/wrong"
}

This is an experimental simulation. No investment advice.
```

### How the engine composes the final LLM prompt

```
System message:
  - Date constraint (simulation date, no future info)
  - Simulation disclaimer

User message:
  - [Engine-injected] Portfolio state (cash, positions, values)
  - [Engine-injected] Market OHLCV data (last 30 trading days)
  - [Engine-injected] Benchmark performance since start
  - [Engine-injected] Prior N reports
  - [Template content compiled with inputs via existing template compiler]
```

The template compiler resolves `{{inputs.*}}` placeholders. The engine controls data injection.

## LLM Structured Response

```python
class TradeDecision(BaseModel):
    symbol: str
    action: Literal["BUY", "SELL", "HOLD"]
    quantity: int | None = None        # required for BUY/SELL
    target_price: float | None = None  # required for BUY/SELL
    reasoning: str

class AnalysisResponse(BaseModel):
    overall_assessment: str
    decisions: list[TradeDecision]
    reflection: str
```

Parsed via OpenAI SDK `beta.chat.completions.parse` with Pydantic model for structured output.

## Simulation Engine

### Cycle schedule generation

- DAILY: every NYSE trading day in range
- WEEKLY: last trading day of each week
- MONTHLY: last trading day of each month

Uses `exchange-calendars` library for NYSE calendar (holidays, half-days).

### Report context window per frequency

| Frequency | Prior reports fed to LLM |
|---|---|
| Daily | Last 1 report |
| Weekly | Last 5 reports |
| Monthly | That month's prior reports |

### Simulated execution time

All trades execute at 3:30 PM ET (30 min before market close), matching real-world analysis timing.

### Engine loop pseudocode

```
for cycle_date in trading_schedule:
    # 0. Check cancellation
    if backtest.status == CANCELLED: break

    # 1. Load market data up to cycle_date (disk-cached parquet)
    market_data = load_market_data(symbols, up_to=cycle_date)

    # 2. Load prior N reports from this backtest run
    prior_reports = load_prior_reports(backtest_id, frequency, cycle_date)

    # 3. Build prompt: engine-injected data + compiled template
    prompt = build_prompt(portfolio_state, market_data, prior_reports, cycle_date)

    # 4. Call LLM via OpenAI SDK
    response = call_llm(prompt) -> AnalysisResponse

    # 5. Store analysis as report (existing reports infrastructure)
    report = create_report(content, metadata with backtest tags)

    # 6. Execute trades
    for decision in response.decisions:
        if decision.action == "HOLD": continue

        # 6a. Determine execution price
        if price_mode == "CLOSING_PRICE":
            execution_price = day_data.close
            executed = True
        elif price_mode == "LLM_DECIDED":
            if day_data.low <= target <= day_data.high:
                executed = random.random() < llm_price_success_rate
                execution_price = target
            else:
                executed = False  # price outside day's range

        if not executed:
            log_failed_trade(decision)
            continue

        # 6b. Compute commission
        if commission_mode == "ZERO": commission = 0
        elif commission_mode == "FIXED": commission = commission_value
        elif commission_mode == "PERCENTAGE":
            commission = execution_price * quantity * commission_value

        # 6c. Execute via TradingOperationService
        try:
            trading_service.create_operation(portfolio_id, {
                side, symbol, balanceId, quantity, price, commission, executedAt
            })
        except ApiError:
            log_failed_trade(decision, reason=error)

    # 7. Update progress
    backtest.completed_cycles += 1
    backtest.current_cycle_date = cycle_date
    session.commit()

# 8. Compute performance metrics and store results
results = compute_results(backtest, benchmark_data)
backtest.results = results
backtest.status = "COMPLETED"
session.commit()
```

### Performance metrics computed after completion

- Total return: (ending_value - starting_value) / starting_value
- Annualized return: compound annual growth rate
- Max drawdown: largest peak-to-trough decline
- Sharpe ratio: (portfolio_return - risk_free_rate) / std_dev(daily_returns)
- Win rate: profitable trades / total trades
- Total trades: count of executed BUY + SELL
- Total commission: sum of all commissions
- Equity curve: daily portfolio value time series
- Benchmark curves: normalized benchmark returns
- Drawdown curve: running drawdown time series
- Trade log: every attempted trade with execution status

### Market data disk cache

```
backend/.cache/market_data/
  AAPL.parquet
  MSFT.parquet
  ^GSPC.parquet
  ^IXIC.parquet
```

- First fetch: download full history via yfinance, save as parquet
- Subsequent: read parquet, fetch only missing dates, append
- Cache dir configurable via env var, defaults to backend/.cache/market_data/

## Frontend UI

### Navigation

New sidebar entry: "Backtests" with FlaskConical or TrendingUp icon, placed after Reports.

### Routes

| Path | Component | Purpose |
|---|---|---|
| /backtests | BacktestListPage | Backtest inventory |
| /backtests/new | BacktestConfigPage | Create form (multi-section) |
| /backtests/:id | BacktestDetailPage | Progress + results dashboard |

### Page 1: Backtest List (/backtests)

Card list (same pattern as portfolio list page):
- Each card shows: name, status badge, portfolio, frequency, cycle count, date range
- RUNNING cards show progress bar (completedCycles / totalCycles)
- COMPLETED cards show total return vs benchmark
- FAILED cards show error message
- Actions: Open (all), Delete (terminal states only)
- Status badges: PENDING (gray), RUNNING (blue), COMPLETED (green), FAILED (red), CANCELLED (yellow)

### Page 2: Backtest Config (/backtests/new)

Multi-section form on one page:

1. **Backtest Name** -- text input
2. **Portfolio** -- radio: "Use existing" (dropdown) or "Create new" (inline portfolio create form with name, slug, currency, initial cash)
3. **Analysis Template** -- radio: "Use existing" (dropdown) or "Create default" (auto-creates editable template, optional name override)
4. **Simulation Settings** -- frequency radio (Daily/Weekly/Monthly), date range picker (start + end)
5. **Execution Settings** -- price mode radio (Closing Price / LLM Decided), success rate input (if LLM), commission radio (Zero/Fixed/Percentage) with value input
6. **LLM Configuration** -- base URL, API key (password field), model name
7. **Benchmarks** -- checkboxes: S&P 500, NASDAQ, Dow Jones (toggle lines on result charts)
8. **Validation summary** -- pre-launch checks (portfolio has balance/position, template selected, dates valid, LLM fields filled, at least one benchmark)

Pre-launch validation:
- Portfolio must have at least one balance or position
- Template must be selected or auto-create enabled
- Date range valid (start < end, both in the past)
- LLM fields filled (base_url, api_key, model)
- At least one benchmark selected

### Page 3: Backtest Detail (/backtests/:id)

**While RUNNING:**
- Status badge + Cancel button
- Progress bar (completedCycles / totalCycles percentage)
- Current simulation date
- Elapsed time
- Live activity feed of recent decisions (last 5-10)
- Frontend polls every 5 seconds, stops on terminal status

**When COMPLETED -- full results dashboard:**

Summary metrics (6 cards):
- Total Return, Max Drawdown, Sharpe Ratio
- Total Trades, Win Rate, Total Commission

Equity Curve chart (LineChart):
- Portfolio value over time
- Benchmark lines (toggled via checkboxes below chart)
- Checkboxes: Portfolio + each selected benchmark

Drawdown chart (AreaChart):
- Red fill below zero line
- Shows peak-to-trough declines over time

Trade Log table:
- Columns: Date, Symbol, Action, Qty, Price, Status
- Executed (checkmark) vs Failed (X with hover tooltip for reason)
- Sortable

Analysis Reports section:
- Links to individual report detail pages (/reports/backtest_1_...)

### Frontend polling

```typescript
useQuery({
  queryKey: queryKeys.backtests.detail(id),
  queryFn: () => backtestsApi.getBacktest(id),
  refetchInterval: (query) => {
    const status = query.state.data?.status;
    if (status === "RUNNING" || status === "PENDING") return 5000;
    return false;
  },
});
```

### Charting library

Recharts for:
- Equity curve: LineChart with multiple series
- Drawdown: AreaChart with red fill
- Benchmark toggles: checkboxes show/hide series

## File Structure

### Backend

```
backend/app/
  api/
    backtests.py              # route handlers
  models/
    backtest.py               # ORM model
  schemas/
    backtest.py               # Pydantic request/response schemas
  repositories/
    backtest.py               # query helpers
  services/
    backtest_service.py       # CRUD + launch thread
    backtest_engine.py        # simulation loop, LLM calls, trade execution
  .cache/
    market_data/              # parquet disk cache
```

### Frontend

```
frontend/src/
  lib/
    api/backtests.ts          # API request helpers
    types/backtest.ts         # wire types
  hooks/
    use-backtests.ts          # query + mutation hooks
  pages/
    backtests/
      list.tsx                # backtest inventory
      config.tsx              # create form (multi-section)
      detail.tsx              # progress + results dashboard
  components/
    backtests/
      backtest-status-badge.tsx    # status indicator
      equity-curve-chart.tsx       # line chart with benchmark toggles
      drawdown-chart.tsx           # area chart
      metrics-summary.tsx          # 6 metric cards
      trade-log-table.tsx          # sortable trade history
```

## New Dependencies

### Backend (pyproject.toml)

- `yfinance` -- Yahoo Finance historical data
- `openai` -- OpenAI-compatible LLM calls
- `pyarrow` -- parquet read/write for disk cache
- `exchange-calendars` -- NYSE trading day calendar

### Frontend (package.json)

- `recharts` -- charting library
- `date-fns` -- date utilities (likely already present)

## Portfolio Handling

- **Existing portfolio**: user selects from dropdown, backtest uses it directly
- **New portfolio**: config form creates a new portfolio (same flow as portfolio list page), user sets initial cash balance and/or positions
- **Validation**: portfolio must have at least one balance or position before backtest starts; refuse to start otherwise

## Error Handling

- LLM connection failure: mark backtest FAILED with error message
- LLM response parse failure: log warning, skip cycle, continue
- Trade execution failure (insufficient balance, oversell): log failed trade, continue
- Yahoo Finance rate limit: retry with exponential backoff, fail after 5 attempts
- Thread crash: catch all exceptions, mark FAILED, store error message

## Security Notes

- `llmApiKey` stored in DB but never returned in GET responses (redacted to "***")
- LLM config is per-backtest, not global
- No authentication on backtest endpoints (consistent with rest of app)

## Scope Exclusions

- No real-time scheduling (backtest is on-demand only)
- No multi-user isolation
- No horizontal scaling of backtest workers
- No investment advice or recommendations

## Spec Review Fixes (2026-03-20)

### Fix 1: Portfolio Isolation and Trade Attribution

Backtest trades must be distinguishable from manual trades. Add a nullable `backtest_id` foreign key to the existing `trading_operations` table:

```
trading_operations (existing table, add column)
  backtest_id  INTEGER FK -> backtests.id  NULL
```

This allows:
- Filtering backtest trades vs manual trades
- Cascade-deleting backtest trades when a backtest is deleted
- Reconstructing backtest trade history from the DB

On backtest delete: cascade-delete associated reports (filtered by `tag=backtest_{id}`) and trading operations (filtered by `backtest_id`).

### Fix 2: New Portfolio Creation Flow

The frontend orchestrates new portfolio creation separately:
1. User fills inline portfolio form (name, slug, currency, initial cash)
2. Frontend calls `POST /api/v1/portfolios` to create portfolio
3. Frontend calls `POST /api/v1/portfolios/{id}/balances` to create deposit balance
4. Frontend passes the new `portfolioId` to `POST /api/v1/backtests`

The backtest create API stays simple — it only accepts `portfolioId`. Portfolio creation is the frontend's responsibility using existing APIs.

### Fix 3: Balance Selection

The engine selects the deposit balance automatically:
- Query all balances for the portfolio where `operationType == "DEPOSIT"`
- If zero deposit balances: refuse to start, return validation error
- If one deposit balance: use it
- If multiple deposit balances: use the one with the largest `amount`

This is documented behavior, not a silent default. The backtest GET response includes `depositBalanceId` so the user can see which balance is being used.

Add to backtests table:
```
deposit_balance_id  INTEGER FK -> balances.id  NOT NULL
```

Resolved at backtest creation time and stored.

### Fix 4: Analysis Unit — Portfolio Level

The engine runs at portfolio level. Each cycle analyzes ALL positions in the portfolio. The LLM returns decisions for every symbol.

Updated default template content:

```markdown
# Portfolio Analysis ({{inputs.cycle_date}})

## Instructions
You are analyzing all positions in portfolio {{inputs.portfolio_name}}.
Analysis frequency: {{inputs.frequency}}.

CRITICAL: Today is {{inputs.cycle_date}}. Do NOT use any information
from after this date. If uncertain about timing, exclude it.

## Your Analysis
1. Assess the current business and market context for each position
2. Review the prior analysis reports provided below
3. Identify what changed since last review
4. Decide: BUY, SELL, or HOLD for each position
5. You may also suggest buying new symbols not currently held

## Response Format
Respond in this exact JSON:
{
  "overall_assessment": "brief portfolio summary",
  "decisions": [
    {
      "symbol": "TICKER",
      "action": "BUY|SELL|HOLD",
      "quantity": 5,
      "target_price": 185.50,
      "reasoning": "2-3 sentences"
    }
  ],
  "reflection": "what changed, what you got right/wrong"
}

This is an experimental simulation. No investment advice.
```

Report metadata per cycle:
```json
{
  "tags": ["backtest", "backtest_42"],
  "analysis": {
    "backtestId": 42,
    "cycleDate": "2024-03-15",
    "reviewType": "backtest_daily"
  }
}
```

### Fix 5: Running-State Activity Feed

Add `recentActivity` field to the backtests table and GET response:

```
recent_activity  JSON  NULL
```

Updated during each cycle by the engine (last 10 entries):
```json
[
  {
    "cycleDate": "2024-06-15",
    "decisions": [
      {"symbol": "AAPL", "action": "HOLD", "reasoning": "No material change"},
      {"symbol": "MSFT", "action": "BUY", "quantity": 3, "targetPrice": 420.50, "executed": true}
    ]
  }
]
```

This gives the frontend enough data to render the live activity feed during RUNNING state without querying reports.

### Fix 6: Crash Recovery

On app startup (in `create_app` lifespan or `init_db`):
- Query all backtests with status `RUNNING` or `PENDING`
- Mark them as `FAILED` with `error_message = "Process interrupted — backtest was running when the server restarted"`
- This is simple, predictable, and prevents orphaned rows

### Fix 7: LLM API — Use Responses Endpoint

The LLM integration uses the OpenAI Responses API (`/v1/responses`) instead of Chat Completions (`/v1/chat/completions`).

```python
from openai import OpenAI

client = OpenAI(base_url=llm_base_url, api_key=llm_api_key)

response = client.responses.create(
    model=llm_model,
    input=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ],
    text={
        "format": {
            "type": "json_schema",
            "schema": AnalysisResponse.model_json_schema()
        }
    }
)

# Parse structured output
import json
analysis = AnalysisResponse.model_validate(json.loads(response.output_text))
```

### Advisory Fixes

- **Sharpe ratio**: uses 0% risk-free rate as default
- **Win rate**: per-operation basis (sell price > average cost)
- **Commission percentage**: input is decimal fraction (0.001 = 0.1%)
- **Cache path**: `backend/.cache/market_data/` (outside `app/`)

### Updated Data Model (consolidated)

```
backtests
  id                      INTEGER PK
  portfolio_id            INTEGER FK -> portfolios.id NOT NULL
  deposit_balance_id      INTEGER FK -> balances.id NOT NULL        [NEW]
  name                    VARCHAR(200) NOT NULL
  status                  VARCHAR(20) NOT NULL
  frequency               VARCHAR(10) NOT NULL
  start_date              DATE NOT NULL
  end_date                DATE NOT NULL
  current_cycle_date      DATE NULL
  total_cycles            INTEGER NOT NULL
  completed_cycles        INTEGER DEFAULT 0
  template_id             INTEGER FK -> text_templates.id NOT NULL
  llm_base_url            VARCHAR(500) NOT NULL
  llm_api_key             VARCHAR(500) NOT NULL
  llm_model               VARCHAR(200) NOT NULL
  price_mode              VARCHAR(20) NOT NULL
  llm_price_success_rate  NUMERIC(5,4) NULL
  commission_mode         VARCHAR(20) NOT NULL
  commission_value        NUMERIC(18,8) DEFAULT 0
  benchmark_symbols       JSON NOT NULL
  recent_activity         JSON NULL                                  [NEW]
  results                 JSON NULL
  error_message           TEXT NULL
  created_at              TIMESTAMP NOT NULL
  updated_at              TIMESTAMP NOT NULL

trading_operations (existing, add column)
  backtest_id             INTEGER FK -> backtests.id NULL            [NEW]
```
