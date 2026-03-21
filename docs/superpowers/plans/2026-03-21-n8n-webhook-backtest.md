# n8n Webhook Backtest Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the synchronous OpenAI LLM call loop in the backtest engine with an asynchronous n8n webhook + callback pattern where n8n owns all LLM logic and calls back to execute trades and advance cycles.

**Architecture:** The backtest engine currently runs a tight synchronous loop: for each cycle date it calls OpenAI directly, parses the response, executes trades, and advances. The new architecture splits this into: (1) backend builds prompts and fires a webhook to n8n with cycle context, (2) n8n does LLM work and calls back to the backend to upload reports and execute trades, (3) n8n calls a "cycle complete" endpoint which triggers the next cycle's webhook. The backend becomes a pure executor and state machine; n8n owns all decision-making logic.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript (frontend), n8n (external workflow orchestrator), PostgreSQL (state persistence)

---

## Architecture Overview

```
┌─────────────┐     POST webhook_url      ┌──────────┐
│   Backend    │ ──────────────────────── > │   n8n    │
│  (executor)  │                            │ (brain)  │
│              │ < ── POST /backtests/{id}/ │          │
│              │      cycles/{date}/report  │          │
│              │                            │          │
│              │ < ── POST /backtests/{id}/ │          │
│              │      cycles/{date}/trades  │          │
│              │                            │          │
│              │ < ── POST /backtests/{id}/ │          │
│              │      cycles/{date}/complete│          │
│              │                            │          │
│              │ ──── next cycle webhook ─> │          │
└─────────────┘                            └──────────┘
       ↑
       │ poll every 5s
┌──────┴──────┐
│  Frontend   │
│  (viewer)   │
└─────────────┘
```

### Per-Cycle Flow

1. Backend builds prompts, compiles template, persists a "prompt report" with the cycle context
2. Backend POSTs to n8n webhook URL with: backtest_id, cycle_date, report_slug, callback_base_url
3. Backend sets status to `AWAITING_CALLBACK`, starts timeout timer
4. n8n downloads the prompt report via existing report download API
5. n8n does its LLM/logic work (whatever workflow the user configures)
6. n8n POSTs back to `/api/v1/backtests/{id}/cycles/{date}/report` with the analysis report
7. n8n POSTs back to `/api/v1/backtests/{id}/cycles/{date}/trades` with trade decisions
8. n8n POSTs back to `/api/v1/backtests/{id}/cycles/{date}/complete` to signal cycle done
9. Backend executes trades, updates equity/progress, fires next cycle webhook (or completes)

### Status State Machine

```
PENDING -> RUNNING -> AWAITING_CALLBACK -> PROCESSING_CALLBACK -> RUNNING -> ... -> COMPLETED
                                      \-> (timeout) -> FAILED
                   \-> CANCELLED
```


## File Structure

### Files to CREATE

| File | Responsibility |
|------|---------------|
| `backend/app/api/backtest_callbacks.py` | New callback router: cycle report upload, cycle trade execution, cycle complete endpoints |
| `backend/app/schemas/backtest_callback.py` | Pydantic schemas for callback request/response payloads |
| `backend/app/services/backtest_cycle_service.py` | Cycle state machine: webhook dispatch, callback processing, timeout handling, cycle advancement |
| `backend/tests/test_backtest_callbacks_api.py` | API-level tests for all three callback endpoints |
| `backend/tests/test_backtest_cycle_service.py` | Unit tests for cycle state machine, webhook dispatch, timeout |

### Files to MODIFY (backend)

| File | What Changes |
|------|-------------|
| `backend/app/models/backtest.py` | Replace `llm_base_url`/`llm_api_key`/`llm_model` columns with `webhook_url`/`webhook_timeout`. Remove `llm_price_success_rate`. Add `current_cycle_status` column. |
| `backend/app/schemas/backtest.py` | Replace LLM fields in `BacktestCreate`/`BacktestRead` with webhook fields. Add new status values `AWAITING_CALLBACK`/`PROCESSING_CALLBACK`. Remove `AnalysisResponse`, `_analysis_response_schema()`. Keep `TradeDecision` (reused by callback). Remove `BacktestPriceMode.LLM_DECIDED`. |
| `backend/app/services/backtest_engine.py` | Gut the synchronous `run()` loop. Remove `_call_llm()`, `_analysis_response_schema()`, `openai_client` param. Replace with `run_cycle()` (single cycle) and `start()` (fires first webhook). Keep: `_build_prompts()`, `_apply_decisions()`, `_store_cycle_report()`, `_compute_results()`, `_update_progress()`, market data loading, benchmark loading, portfolio value calculation. |
| `backend/app/services/backtest_service.py` | Remove `_build_openai_client()`, `_DeterministicBacktestOpenAIClient`, `_DeterministicBacktestResponses`, `BACKTEST_TEST_MODE` env check. Replace `ThreadPoolExecutor` background launch with initial webhook dispatch. Keep: `create_backtest()`, `list_backtests()`, `cancel_backtest()`, `delete_backtest()`. |
| `backend/app/api/backtests.py` | No structural change, but the create response now returns webhook-based fields instead of LLM fields. |
| `backend/app/api/router.py` | Mount new `backtest_callbacks` router. |
| `backend/app/api/dependencies.py` | Add `get_backtest_cycle_service()` factory. |
| `backend/app/db/session.py` | Update `init_db()` startup repair: mark stale `AWAITING_CALLBACK` backtests as FAILED (same as current PENDING/RUNNING repair). |
| `backend/tests/test_backtest_engine.py` | Rewrite: remove all `_call_llm` / OpenAI mock tests. Add tests for `run_cycle()`, `start()`, webhook dispatch mock, single-cycle execution. |
| `backend/tests/test_backtests_api.py` | Update create payload to use `webhookUrl` instead of LLM fields. Update assertions. |

### Files to MODIFY (frontend)

| File | What Changes |
|------|-------------|
| `frontend/src/lib/types/backtest.ts` | Replace `llmBaseUrl`/`llmApiKey`/`llmModel`/`llmPriceSuccessRate` with `webhookUrl`/`webhookTimeout` in `BacktestRead` and `BacktestCreateInput`. Add `AWAITING_CALLBACK`/`PROCESSING_CALLBACK` to `BacktestStatus`. Remove `BacktestPriceMode` type (keep only `CLOSING_PRICE`). |
| `frontend/src/components/shared/form-schemas.ts` | Replace `llmBaseUrl`/`llmApiKey`/`llmModel` fields with `webhookUrl`/`webhookTimeout`. Remove `llmPriceSuccessRate` and `LLM_DECIDED` price mode. |
| `frontend/src/pages/backtests/config.tsx` | Replace LLM config form section with webhook URL + timeout fields. Remove price mode LLM_DECIDED option. |
| `frontend/src/pages/backtests/detail.tsx` | Show new granular statuses in progress display. |
| `frontend/src/components/backtests/backtest-status-badge.tsx` | Add badge variants for `AWAITING_CALLBACK` and `PROCESSING_CALLBACK`. |
| `frontend/src/hooks/use-backtests.ts` | Update `isRunningStatus()` to include `AWAITING_CALLBACK` and `PROCESSING_CALLBACK` for polling. |
| `frontend/e2e/backtests.spec.ts` | Update E2E to use webhook fields instead of LLM fields. Mock or stub n8n webhook for deterministic E2E. |

### Files to DELETE (nothing)

No files are deleted. The backtest engine file is heavily modified but retained.


---

## Webhook Payload Contract (Backend -> n8n)

```json
POST {webhook_url}
Content-Type: application/json

{
  "backtestId": 71,
  "cycleDate": "2026-01-02",
  "totalCycles": 20,
  "completedCycles": 3,
  "frequency": "DAILY",
  "portfolioName": "AAPL REAL TEST",
  "reportSlug": "backtest_71_20260102",
  "reportDownloadUrl": "/api/v1/reports/backtest_71_20260102/download",
  "callbackBaseUrl": "http://127.0.0.1:8000/api/v1/backtests/71/cycles/2026-01-02",
  "benchmarkSymbols": ["^GSPC"]
}
```

The `callbackBaseUrl` tells n8n where to POST back. n8n appends `/report`, `/trades`, or `/complete`.

## Callback Endpoint Contracts (n8n -> Backend)

### 1. Upload Cycle Report

```
POST /api/v1/backtests/{backtest_id}/cycles/{cycle_date}/report
Content-Type: application/json

{
  "name": "backtest_71_analysis_20260102",
  "content": "# Analysis\n\n## Overall Assessment\n...",
  "tags": ["backtest", "backtest_71"]
}

Response: 201 { "slug": "backtest_71_analysis_20260102" }
```

### 2. Execute Cycle Trades

```
POST /api/v1/backtests/{backtest_id}/cycles/{cycle_date}/trades
Content-Type: application/json

{
  "decisions": [
    {
      "symbol": "AAPL",
      "action": "BUY",
      "quantity": 10,
      "targetPrice": "185.50",
      "reasoning": "Strong earnings outlook"
    },
    {
      "symbol": "MSFT",
      "action": "HOLD",
      "reasoning": "Maintaining position"
    }
  ],
  "reportSlug": "backtest_71_analysis_20260102"
}

Response: 200 {
  "executed": [
    { "symbol": "AAPL", "action": "BUY", "executed": true, "executedPrice": "185.50" },
    { "symbol": "MSFT", "action": "HOLD", "executed": null }
  ]
}
```

### 3. Complete Cycle

```
POST /api/v1/backtests/{backtest_id}/cycles/{cycle_date}/complete

Response: 200 {
  "backtestId": 71,
  "status": "RUNNING",
  "completedCycles": 4,
  "totalCycles": 20,
  "nextCycleDate": "2026-01-03",
  "finished": false
}
```

If this was the last cycle, `finished: true` and `status: "COMPLETED"`.


---

## Task Breakdown

### Task 1: Database Model — Replace LLM columns with webhook columns

**Files:**
- Modify: `backend/app/models/backtest.py`
- Modify: `backend/app/db/session.py` (startup repair)

- [ ] **Step 1: Update Backtest model columns**

Replace in `backend/app/models/backtest.py`:
```python
# REMOVE these columns:
llm_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
llm_api_key: Mapped[str] = mapped_column(String(500), nullable=False)
llm_model: Mapped[str] = mapped_column(String(200), nullable=False)
llm_price_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)

# ADD these columns:
webhook_url: Mapped[str] = mapped_column(String(1000), nullable=False)
webhook_timeout: Mapped[int] = mapped_column(nullable=False, server_default="600")
current_cycle_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
```

Keep: `price_mode` (but only `CLOSING_PRICE` will be used now — `LLM_DECIDED` is removed from the enum later).

- [ ] **Step 2: Update init_db startup repair**

In `backend/app/db/session.py`, find the existing startup repair that marks stale PENDING/RUNNING backtests as FAILED. Add `AWAITING_CALLBACK` and `PROCESSING_CALLBACK` to the list of non-terminal statuses that get repaired on startup.

- [ ] **Step 3: Verify model compiles**

Run: `cd backend && uv run mypy app/models/backtest.py`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
cd backend && git add app/models/backtest.py app/db/session.py
git commit -m "refactor: replace LLM columns with webhook columns on backtest model"
```

---

### Task 2: Schemas — Replace LLM fields with webhook fields

**Files:**
- Modify: `backend/app/schemas/backtest.py`
- Create: `backend/app/schemas/backtest_callback.py`

- [ ] **Step 1: Update BacktestStatus enum**

Add to `BacktestStatus` in `backend/app/schemas/backtest.py`:
```python
class BacktestStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_CALLBACK = "AWAITING_CALLBACK"
    PROCESSING_CALLBACK = "PROCESSING_CALLBACK"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
```

- [ ] **Step 2: Remove LLM_DECIDED from BacktestPriceMode**

Either remove `BacktestPriceMode` entirely and hardcode `CLOSING_PRICE`, or keep the enum with only `CLOSING_PRICE`. Simplest: remove the enum, set `price_mode` as a constant in the create schema.

- [ ] **Step 3: Update BacktestCreate schema**

Replace LLM fields with webhook fields:
```python
# REMOVE:
llm_base_url: str = Field(min_length=1, max_length=500)
llm_api_key: str = Field(min_length=1, max_length=500)
llm_model: str = Field(min_length=1, max_length=200)
llm_price_success_rate: Decimal | None = None

# ADD:
webhook_url: str = Field(min_length=1, max_length=1000)
webhook_timeout: int = Field(default=600, ge=30, le=3600)
```

Remove `price_mode` field or hardcode it. Remove validators for removed fields.

- [ ] **Step 4: Update BacktestRead schema**

Replace LLM fields with webhook fields:
```python
# REMOVE:
llm_base_url: str
llm_api_key: str
llm_model: str
llm_price_success_rate: Decimal | None = None

# REMOVE the redact_llm_api_key validator

# ADD:
webhook_url: str
webhook_timeout: int
current_cycle_status: str | None = None
```

- [ ] **Step 5: Remove AnalysisResponse schema**

Remove `AnalysisResponse` class from `backend/app/schemas/backtest.py`. Keep `TradeDecision` — it will be reused by the callback trade endpoint.

- [ ] **Step 6: Create callback schemas**

Create `backend/app/schemas/backtest_callback.py`:
```python
from __future__ import annotations
from decimal import Decimal
from pydantic import Field
from app.schemas.backtest import TradeDecision
from app.schemas.common import CamelModel


class CycleReportUpload(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class CycleReportUploadResponse(CamelModel):
    slug: str


class CycleTradesRequest(CamelModel):
    decisions: list[TradeDecision]
    report_slug: str | None = None


class CycleTradeResult(CamelModel):
    symbol: str
    action: str
    executed: bool | None = None
    executed_price: str | None = None
    failure_reason: str | None = None


class CycleTradesResponse(CamelModel):
    executed: list[CycleTradeResult]


class CycleCompleteResponse(CamelModel):
    backtest_id: int
    status: str
    completed_cycles: int
    total_cycles: int
    next_cycle_date: str | None = None
    finished: bool
```

- [ ] **Step 7: Verify schemas compile**

Run: `cd backend && uv run mypy app/schemas/`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
cd backend && git add app/schemas/backtest.py app/schemas/backtest_callback.py
git commit -m "refactor: replace LLM schemas with webhook and callback schemas"
```


---

### Task 3: Backtest Cycle Service — Webhook dispatch and cycle state machine

**Files:**
- Create: `backend/app/services/backtest_cycle_service.py`
- Create: `backend/tests/test_backtest_cycle_service.py`

- [ ] **Step 1: Write failing test for webhook dispatch**

```python
# tests/test_backtest_cycle_service.py
def test_dispatch_webhook_sends_correct_payload():
    # Mock httpx.post, verify payload shape matches contract
    # Verify backtest status transitions to AWAITING_CALLBACK
    pass
```

- [ ] **Step 2: Implement BacktestCycleService**

Create `backend/app/services/backtest_cycle_service.py`:

```python
class BacktestCycleService:
    """Manages the async cycle state machine for webhook-based backtests."""

    def __init__(self, session: Session, session_factory: sessionmaker[Session]) -> None:
        self.session = session
        self.session_factory = session_factory

    def start_backtest(self, backtest_id: int) -> None:
        """Initialize backtest, build schedule, fire first cycle webhook."""
        # 1. Load backtest, build schedule, set total_cycles, status=RUNNING
        # 2. Call dispatch_cycle() for first cycle date

    def dispatch_cycle(self, backtest_id: int, cycle_date: date) -> None:
        """Build prompts, persist prompt report, POST webhook, set AWAITING_CALLBACK."""
        # 1. Use BacktestEngine to build prompts and store cycle report
        # 2. POST to backtest.webhook_url with cycle context
        # 3. Set current_cycle_status = AWAITING_CALLBACK
        # 4. Start timeout timer (threading.Timer or background task)

    def handle_report_callback(self, backtest_id: int, cycle_date: date, payload: CycleReportUpload) -> str:
        """n8n uploaded an analysis report. Persist it, return slug."""
        # Validate backtest is in AWAITING_CALLBACK or PROCESSING_CALLBACK
        # Create report via ReportService
        # Return slug

    def handle_trades_callback(self, backtest_id: int, cycle_date: date, payload: CycleTradesRequest) -> CycleTradesResponse:
        """n8n sent trade decisions. Execute them against the backtest portfolio."""
        # Validate backtest is in AWAITING_CALLBACK or PROCESSING_CALLBACK
        # Set current_cycle_status = PROCESSING_CALLBACK
        # Use BacktestEngine._apply_decisions() to execute trades
        # Return execution results

    def handle_cycle_complete(self, backtest_id: int, cycle_date: date) -> CycleCompleteResponse:
        """n8n signals cycle is done. Advance to next cycle or finish."""
        # 1. Update progress (completed_cycles++, current_cycle_date)
        # 2. Record equity point
        # 3. If more cycles: dispatch_cycle() for next date, return finished=false
        # 4. If last cycle: compute_results(), set COMPLETED, return finished=true

    def handle_timeout(self, backtest_id: int) -> None:
        """Webhook timed out. Try to retrieve result from n8n, else fail."""
        # If still AWAITING_CALLBACK after timeout:
        # Mark backtest as FAILED with timeout error message
```

- [ ] **Step 3: Write tests for callback handlers**

Test each handler: report upload, trade execution, cycle complete, timeout.
Test state validation: reject callbacks when backtest is not in expected status.
Test cycle advancement: verify next webhook fires after complete.
Test final cycle: verify results computation and COMPLETED status.

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/test_backtest_cycle_service.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/backtest_cycle_service.py tests/test_backtest_cycle_service.py
git commit -m "feat: add backtest cycle service with webhook dispatch and callback handlers"
```

---

### Task 4: Callback API Routes

**Files:**
- Create: `backend/app/api/backtest_callbacks.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/api/dependencies.py`
- Create: `backend/tests/test_backtest_callbacks_api.py`

- [ ] **Step 1: Write failing API test for cycle report upload**

```python
# tests/test_backtest_callbacks_api.py
def test_cycle_report_upload_creates_report(client, backtest_in_awaiting_callback):
    response = client.post(
        f"/api/v1/backtests/{backtest_id}/cycles/2026-01-02/report",
        json={"name": "analysis_report", "content": "# Analysis\n...", "tags": ["backtest"]}
    )
    assert response.status_code == 201
    assert "slug" in response.json()
```

- [ ] **Step 2: Implement callback routes**

Create `backend/app/api/backtest_callbacks.py`:
```python
router = APIRouter(prefix="/backtests/{backtest_id}/cycles/{cycle_date}", tags=["backtest-callbacks"])

@router.post("/report", response_model=CycleReportUploadResponse, status_code=201)
def upload_cycle_report(backtest_id: int, cycle_date: date, payload: CycleReportUpload, service: ...) -> CycleReportUploadResponse:
    slug = service.handle_report_callback(backtest_id, cycle_date, payload)
    return CycleReportUploadResponse(slug=slug)

@router.post("/trades", response_model=CycleTradesResponse)
def execute_cycle_trades(backtest_id: int, cycle_date: date, payload: CycleTradesRequest, service: ...) -> CycleTradesResponse:
    return service.handle_trades_callback(backtest_id, cycle_date, payload)

@router.post("/complete", response_model=CycleCompleteResponse)
def complete_cycle(backtest_id: int, cycle_date: date, service: ...) -> CycleCompleteResponse:
    return service.handle_cycle_complete(backtest_id, cycle_date)
```

- [ ] **Step 3: Mount router and add dependency**

In `backend/app/api/router.py`, add:
```python
from app.api.backtest_callbacks import router as backtest_callbacks_router
api_router.include_router(backtest_callbacks_router)
```

In `backend/app/api/dependencies.py`, add:
```python
def get_backtest_cycle_service(
    session: Annotated[Session, Depends(get_session)],
) -> BacktestCycleService:
    return BacktestCycleService(session, get_session_factory())
```

- [ ] **Step 4: Write full API test suite**

Test all three callback endpoints: report, trades, complete.
Test error cases: wrong status, invalid backtest_id, invalid cycle_date.
Test the full cycle flow: create backtest -> mock webhook -> report callback -> trades callback -> complete callback -> verify advancement.

- [ ] **Step 5: Run tests**

Run: `cd backend && uv run pytest tests/test_backtest_callbacks_api.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/api/backtest_callbacks.py app/api/router.py app/api/dependencies.py tests/test_backtest_callbacks_api.py
git commit -m "feat: add callback API routes for n8n cycle report, trades, and complete"
```


---

### Task 5: Refactor BacktestEngine — Remove LLM, keep cycle utilities

**Files:**
- Modify: `backend/app/services/backtest_engine.py`
- Modify: `backend/tests/test_backtest_engine.py`

- [ ] **Step 1: Remove all OpenAI/LLM code from engine**

Remove from `backend/app/services/backtest_engine.py`:
- Line 13: `from openai import OpenAI`
- Constructor param: `openai_client`
- Constructor assignment: `self.openai_client = openai_client`
- Method: `_call_llm()` (lines 342-363)
- Method: `_analysis_response_schema()` (lines 306-340)
- Method: `_build_cash_only_analysis()` (lines 410-418) — n8n handles this now
- Method: `_render_analysis_report()` (lines 975-985) — report rendering moves to n8n
- Import: `AnalysisResponse` from schemas (line 24, partial)

- [ ] **Step 2: Remove the synchronous run() loop**

Replace the current `run()` method (lines 93-183) with two focused methods:

```python
def initialize(self) -> tuple[list[date], dict[str, list[tuple[str, Decimal]]]]:
    """Build schedule, set RUNNING status, load benchmark history. Called once at backtest start."""
    backtest = self._refresh_backtest()
    schedule = self._build_schedule(backtest.start_date, backtest.end_date, backtest.frequency)
    with self.session_factory() as session:
        current = self._get_backtest(session)
        if current.status == BacktestStatus.CANCELLED.value:
            session.expunge(current)
            self.backtest = current
            return [], {}
        current.status = BacktestStatus.RUNNING.value
        current.error_message = None
        current.total_cycles = len(schedule)
        session.commit()
    benchmark_history = self._load_benchmark_history(schedule)
    return schedule, benchmark_history

def execute_cycle(self, cycle_date: date) -> dict[str, Any]:
    """Execute a single cycle: load market data, build prompts, store prompt report.
    Returns context dict for webhook dispatch. Does NOT call LLM."""
    symbols = self._portfolio_symbols()
    market_data = self._load_cycle_market_data(symbols, cycle_date)
    system_prompt, user_prompt = self._build_prompts(cycle_date)
    # Store the prompt as a report so n8n can download it
    prompt_report_slug = self._store_prompt_report(cycle_date, system_prompt, user_prompt)
    equity_value = self._portfolio_value(market_data, cycle_date)
    return {
        "cycle_date": cycle_date,
        "market_data": market_data,
        "prompt_report_slug": prompt_report_slug,
        "equity_value": equity_value,
    }

def finalize(self, equity_points, benchmark_history, trade_log) -> None:
    """Compute results and mark COMPLETED. Called after last cycle completes."""
    results = self._compute_results(
        equity_points=equity_points,
        benchmark_history=benchmark_history,
        trade_log=trade_log,
    )
    with self.session_factory() as session:
        current = self._get_backtest(session)
        if current.status != BacktestStatus.CANCELLED.value:
            current.results = results
            current.status = BacktestStatus.COMPLETED.value
        session.commit()
```

- [ ] **Step 3: Add _store_prompt_report() method**

```python
def _store_prompt_report(self, cycle_date: date, system_prompt: str, user_prompt: str) -> str:
    """Persist the compiled prompt as a downloadable report for n8n."""
    content = f"# Cycle Prompt ({cycle_date.isoformat()})\n\n## System\n{system_prompt}\n\n## User\n{user_prompt}"
    if self.session_factory is None:
        raise RuntimeError("Backtest engine requires a session factory")
    with self.session_factory() as session:
        service = ReportService(session)
        report = service.create_external_report(
            name=f"backtest_{self.backtest.id}_prompt_{cycle_date.strftime('%Y%m%d')}",
            slug=f"backtest_{self.backtest.id}_prompt_{cycle_date.strftime('%Y%m%d')}",
            content=content,
            metadata=ReportMetadata.model_validate({
                "tags": ["backtest", f"backtest_{self.backtest.id}", "prompt"],
                "analysis": {
                    "backtestId": self.backtest.id,
                    "cycleDate": cycle_date.isoformat(),
                    "reviewType": "backtest_prompt",
                },
            }),
        )
    return report.slug
```

- [ ] **Step 4: Keep _apply_decisions() and supporting methods**

These methods stay as-is (they are called by BacktestCycleService via the engine):
- `_apply_decisions()` — trade execution
- `_resolve_execution()` — price resolution (now only CLOSING_PRICE path)
- `_commission_value()` — commission calculation
- `_compute_results()` — final metrics
- `_update_progress()` — cycle counter
- `_portfolio_value()` — equity calculation
- `_build_prompts()` — template compilation
- `_build_schedule()` — NYSE calendar
- All market data loading methods
- All rendering methods (portfolio state, market context, benchmark context, prior reports)
- `_append_recent_activity()` — activity log
- `_mark_failed()` — error handling
- `_refresh_backtest()` — state reload

- [ ] **Step 5: Remove _resolve_execution LLM_DECIDED path**

In `_resolve_execution()`, remove the `LLM_DECIDED` branch (lines 566-573). Only keep the `CLOSING_PRICE` path:
```python
def _resolve_execution(self, decision: TradeDecision, row: dict[str, Decimal]) -> tuple[Decimal | None, bool, str | None]:
    return row["close"], True, None
```

- [ ] **Step 6: Update engine tests**

Rewrite `backend/tests/test_backtest_engine.py`:
- Remove: `test_call_llm_uses_responses_api_and_returns_analysis_response`
- Add: `test_initialize_sets_running_and_builds_schedule`
- Add: `test_execute_cycle_builds_prompts_and_stores_prompt_report`
- Add: `test_finalize_computes_results_and_marks_completed`
- Keep: all existing tests for schedule building, market data, benchmark loading, etc.

- [ ] **Step 7: Run tests**

Run: `cd backend && uv run pytest tests/test_backtest_engine.py -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
cd backend && git add app/services/backtest_engine.py tests/test_backtest_engine.py
git commit -m "refactor: remove LLM from backtest engine, add cycle-based execution methods"
```


---

### Task 6: Refactor BacktestService — Remove OpenAI client, wire webhook launch

**Files:**
- Modify: `backend/app/services/backtest_service.py`
- Modify: `backend/tests/test_backtests_api.py`

- [ ] **Step 1: Remove all OpenAI/deterministic client code**

Remove from `backend/app/services/backtest_service.py`:
- Class `_DeterministicBacktestResponses` (lines 228-275)
- Class `_DeterministicBacktestOpenAIClient` (lines 278-280)
- Method `_build_openai_client()` and all references to `BACKTEST_TEST_MODE`
- Import: `json` (only used by deterministic client)
- The `ThreadPoolExecutor` global `_BACKTEST_EXECUTOR` (line 62)
- The `_log_background_failure` callback

- [ ] **Step 2: Update create_backtest to use webhook launch**

Replace the current background thread launch with:
```python
def create_backtest(self, payload: BacktestCreate) -> BacktestRead:
    # ... existing portfolio/template/balance validation ...
    backtest = Backtest(
        # ... existing fields ...
        webhook_url=payload.webhook_url,
        webhook_timeout=payload.webhook_timeout,
        price_mode="CLOSING_PRICE",
        # Remove: llm_base_url, llm_api_key, llm_model, llm_price_success_rate
    )
    # ... existing persist logic ...

    # Launch first cycle via BacktestCycleService (in background thread)
    cycle_service = BacktestCycleService(self.session, self.session_factory)
    threading.Thread(
        target=cycle_service.start_backtest,
        args=(backtest.id,),
        daemon=True,
    ).start()

    return BacktestRead.model_validate(backtest)
```

- [ ] **Step 3: Update run_backtest for E2E test mode**

For E2E/Playwright tests, we need a deterministic mode. Instead of the old `_DeterministicBacktestOpenAIClient`, create a `BACKTEST_TEST_MODE` that uses a mock n8n server or skips the webhook and auto-completes cycles with fixed decisions.

Option: When `BACKTEST_TEST_MODE=1`, the cycle service skips the real webhook POST and instead directly calls `handle_trades_callback` and `handle_cycle_complete` with deterministic data. This keeps E2E tests fast and predictable.

- [ ] **Step 4: Update test_backtests_api.py**

Update create payload in tests:
```python
# REMOVE:
"llmBaseUrl": "http://test.example.com/v1",
"llmApiKey": "test-key",
"llmModel": "test-model",

# ADD:
"webhookUrl": "http://test.example.com/webhook",
"webhookTimeout": 600,
```

Update assertions to check webhook fields instead of LLM fields.

- [ ] **Step 5: Run full backend test suite**

Run: `cd backend && uv run pytest -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/services/backtest_service.py tests/test_backtests_api.py
git commit -m "refactor: replace OpenAI client with webhook launch in backtest service"
```

---

### Task 7: Frontend Types and Form — Replace LLM fields with webhook fields

**Files:**
- Modify: `frontend/src/lib/types/backtest.ts`
- Modify: `frontend/src/lib/types/backtest.test.ts`
- Modify: `frontend/src/components/shared/form-schemas.ts`

- [ ] **Step 1: Update BacktestStatus type**

In `frontend/src/lib/types/backtest.ts`:
```typescript
export type BacktestStatus =
  | "PENDING"
  | "RUNNING"
  | "AWAITING_CALLBACK"
  | "PROCESSING_CALLBACK"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";
```

- [ ] **Step 2: Update BacktestRead interface**

Replace LLM fields:
```typescript
// REMOVE:
llmBaseUrl: string;
llmApiKey: string;
llmModel: string;
llmPriceSuccessRate: string | null;

// ADD:
webhookUrl: string;
webhookTimeout: number;
currentCycleStatus: string | null;
```

- [ ] **Step 3: Update BacktestCreateInput interface**

Replace LLM fields:
```typescript
// REMOVE:
llmBaseUrl: string;
llmApiKey: string;
llmModel: string;
llmPriceSuccessRate?: string | null;

// ADD:
webhookUrl: string;
webhookTimeout?: number;
```

- [ ] **Step 4: Remove BacktestPriceMode or simplify**

Remove `LLM_DECIDED` from `BacktestPriceMode`. If only `CLOSING_PRICE` remains, consider removing the type entirely.

- [ ] **Step 5: Update form schema**

In `frontend/src/components/shared/form-schemas.ts`, replace:
```typescript
// REMOVE:
llmBaseUrl: requiredText("LLM base URL"),
llmApiKey: requiredText("LLM API key"),
llmModel: requiredText("LLM model"),
llmPriceSuccessRate: optionalText,

// ADD:
webhookUrl: requiredText("Webhook URL"),
webhookTimeout: numericText("Webhook timeout"),
```

Remove the `LLM_DECIDED` price mode validation in the superRefine block.

- [ ] **Step 6: Update backtest.test.ts**

Update any type tests that reference LLM fields.

- [ ] **Step 7: Run frontend checks**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: pass (config.tsx will have errors until Task 8)

- [ ] **Step 8: Commit**

```bash
cd frontend && git add src/lib/types/backtest.ts src/lib/types/backtest.test.ts src/components/shared/form-schemas.ts
git commit -m "refactor: replace LLM types with webhook types in frontend"
```


---

### Task 8: Frontend Config Page — Replace LLM form with webhook form

**Files:**
- Modify: `frontend/src/pages/backtests/config.tsx`

- [ ] **Step 1: Replace LLM form fields with webhook fields**

In `frontend/src/pages/backtests/config.tsx`:

Replace initial values:
```typescript
// REMOVE:
llmPriceSuccessRate: "",
llmBaseUrl: "",
llmApiKey: "",
llmModel: "",

// ADD:
webhookUrl: "",
webhookTimeout: "600",
```

Replace the submit handler mapping:
```typescript
// REMOVE:
llmBaseUrl: values.llmBaseUrl,
llmApiKey: values.llmApiKey,
llmModel: values.llmModel,
llmPriceSuccessRate: values.priceMode === "LLM_DECIDED" ? values.llmPriceSuccessRate : null,

// ADD:
webhookUrl: values.webhookUrl,
webhookTimeout: Number(values.webhookTimeout),
```

- [ ] **Step 2: Replace LLM form section in JSX**

Replace the "LLM Configuration" card section (approximately lines 370-400) with:
```tsx
<Label htmlFor="webhook-url">n8n Webhook URL</Label>
<Input
  id="webhook-url"
  placeholder="http://localhost:5678/webhook/backtest"
  value={values.webhookUrl}
  onChange={(event) => updateValue("webhookUrl", event.target.value)}
/>

<Label htmlFor="webhook-timeout">Webhook Timeout (seconds)</Label>
<Input
  id="webhook-timeout"
  type="number"
  placeholder="600"
  value={values.webhookTimeout}
  onChange={(event) => updateValue("webhookTimeout", event.target.value)}
/>
```

- [ ] **Step 3: Remove LLM_DECIDED price mode option**

Remove the price mode radio/select for `LLM_DECIDED`. Either remove the price mode selector entirely (hardcode CLOSING_PRICE) or keep it with only one option.

- [ ] **Step 4: Run frontend checks**

Run: `cd frontend && pnpm typecheck && pnpm lint && pnpm build`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/pages/backtests/config.tsx
git commit -m "refactor: replace LLM config form with webhook URL and timeout"
```

---

### Task 9: Frontend Detail Page — Granular status display

**Files:**
- Modify: `frontend/src/pages/backtests/detail.tsx`
- Modify: `frontend/src/components/backtests/backtest-status-badge.tsx`
- Modify: `frontend/src/hooks/use-backtests.ts`

- [ ] **Step 1: Update polling to include new statuses**

In `frontend/src/hooks/use-backtests.ts`:
```typescript
function isRunningStatus(status: BacktestStatus | undefined) {
  return (
    status === "PENDING" ||
    status === "RUNNING" ||
    status === "AWAITING_CALLBACK" ||
    status === "PROCESSING_CALLBACK"
  );
}
```

- [ ] **Step 2: Add badge variants for new statuses**

In `frontend/src/components/backtests/backtest-status-badge.tsx`, add:
- `AWAITING_CALLBACK` — yellow/amber badge, label "Awaiting n8n"
- `PROCESSING_CALLBACK` — blue badge, label "Processing"

- [ ] **Step 3: Update detail page progress display**

In `frontend/src/pages/backtests/detail.tsx`, show the `currentCycleStatus` when the backtest is active. For example, below the progress bar:
```tsx
{isRunning && backtest.currentCycleStatus && (
  <p className="text-xs text-muted-foreground mt-1">
    {backtest.currentCycleStatus === "AWAITING_CALLBACK"
      ? "Waiting for n8n response..."
      : backtest.currentCycleStatus === "PROCESSING_CALLBACK"
        ? "Processing callback..."
        : "Running..."}
  </p>
)}
```

- [ ] **Step 4: Run frontend checks**

Run: `cd frontend && pnpm typecheck && pnpm lint && pnpm build`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/hooks/use-backtests.ts src/components/backtests/backtest-status-badge.tsx src/pages/backtests/detail.tsx
git commit -m "feat: add granular backtest status display for webhook flow"
```

---

### Task 10: E2E Tests — Update for webhook flow

**Files:**
- Modify: `frontend/e2e/backtests.spec.ts`

- [ ] **Step 1: Update E2E backtest creation to use webhook fields**

Replace LLM field fills with webhook fields:
```typescript
// REMOVE:
await page.fill("#llm-base-url", "http://test.example.com/v1");
await page.fill("#llm-api-key", "test-key");
await page.fill("#llm-model", "test-model");

// ADD:
await page.fill("#webhook-url", "http://localhost:5678/webhook/test");
await page.fill("#webhook-timeout", "600");
```

- [ ] **Step 2: Update E2E deterministic mode**

The E2E tests run with `BACKTEST_TEST_MODE=1`. The backend test mode now needs to auto-complete cycles without a real n8n webhook. Verify the deterministic path works by checking that the backtest reaches COMPLETED status.

- [ ] **Step 3: Run E2E tests**

Run: `cd frontend && pnpm exec playwright install --with-deps chromium && pnpm test:e2e`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
cd frontend && git add e2e/backtests.spec.ts
git commit -m "test: update E2E tests for webhook-based backtest flow"
```

---

### Task 11: Full Validation and Cleanup

**Files:**
- All modified files

- [ ] **Step 1: Run full backend validation**

```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest -v
```
Expected: all pass

- [ ] **Step 2: Run full frontend validation**

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
pnpm test:run
pnpm test:e2e
```
Expected: all pass

- [ ] **Step 3: Clean up dead imports and unused code**

Search for any remaining references to:
- `OpenAI`, `openai`, `openai_client`
- `llm_base_url`, `llm_api_key`, `llm_model`, `llm_price_success_rate`
- `AnalysisResponse` (should only remain if still used by callback schemas)
- `_DeterministicBacktestOpenAIClient`, `_DeterministicBacktestResponses`
- `_analysis_response_schema`

Remove any orphaned references.

- [ ] **Step 4: Update AGENTS.md documentation**

Update `backend/app/services/AGENTS.md` to reflect the new webhook-based architecture.
Update `frontend/src/pages/backtests/AGENTS.md` to document the new status states.
Update root `AGENTS.md` backtest description.

- [ ] **Step 5: Final commit**

```bash
cd backend && git add -A && git commit -m "chore: clean up dead LLM references and update docs"
cd frontend && git add -A && git commit -m "chore: clean up dead LLM references and update docs"
```


---

## Migration Notes

### Database Migration

Since this is a development project without production data requiring migration, the simplest approach is:

1. Drop and recreate the `backtests` table (handled by `init_db()` since it creates tables)
2. If existing backtest data matters, write a one-time SQL migration:

```sql
ALTER TABLE backtests ADD COLUMN webhook_url VARCHAR(1000);
ALTER TABLE backtests ADD COLUMN webhook_timeout INTEGER DEFAULT 600;
ALTER TABLE backtests ADD COLUMN current_cycle_status VARCHAR(30);
ALTER TABLE backtests DROP COLUMN llm_base_url;
ALTER TABLE backtests DROP COLUMN llm_api_key;
ALTER TABLE backtests DROP COLUMN llm_model;
ALTER TABLE backtests DROP COLUMN llm_price_success_rate;
UPDATE backtests SET webhook_url = 'http://migrated-placeholder' WHERE webhook_url IS NULL;
ALTER TABLE backtests ALTER COLUMN webhook_url SET NOT NULL;
```

### Dependencies

- Add `httpx` to backend dependencies for webhook HTTP calls (or use `requests` if already present)
- Remove `openai` from backend dependencies (no longer needed)

Check current deps:
```bash
cd backend && grep -E "openai|httpx|requests" pyproject.toml
```

### n8n Workflow Setup (out of scope for this plan)

After this plan is implemented, the user needs to create an n8n workflow that:
1. Receives the webhook POST with backtest cycle context
2. Downloads the prompt report from the backend
3. Runs LLM logic (user-configured)
4. POSTs analysis report back to `/api/v1/backtests/{id}/cycles/{date}/report`
5. POSTs trade decisions back to `/api/v1/backtests/{id}/cycles/{date}/trades`
6. POSTs cycle complete to `/api/v1/backtests/{id}/cycles/{date}/complete`

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| n8n webhook unreachable | Configurable timeout (30-3600s), backtest marked FAILED with clear error |
| n8n calls back out of order (trades before report) | Both report and trades endpoints accept calls in any order; cycle complete is the only ordering gate |
| n8n calls back for wrong cycle date | Validate cycle_date matches backtest.current_cycle_date |
| Concurrent callbacks for same cycle | Use DB-level status checks to reject duplicate processing |
| Backend restart during AWAITING_CALLBACK | init_db() startup repair marks stale AWAITING_CALLBACK as FAILED |
| n8n sends malformed trade decisions | TradeDecision schema validation rejects bad payloads with 422 |

---

## Task Dependency Graph

```
Task 1 (Model) ─────┐
                     ├──> Task 3 (Cycle Service) ──> Task 4 (Callback API)
Task 2 (Schemas) ────┘                                      │
                                                             v
Task 5 (Engine Refactor) ──> Task 6 (Service Refactor) ──> Task 10 (E2E)
                                                             │
Task 7 (FE Types) ──> Task 8 (FE Config) ──> Task 9 (FE Detail) ──> Task 10 (E2E)
                                                                        │
                                                                        v
                                                                  Task 11 (Validation)
```

Tasks 1+2 can run in parallel. Tasks 7+8+9 can run in parallel with Tasks 5+6 (backend vs frontend).


---

## Addendum: Self-Review Findings

### Issue 1 (IMPORTANT): `backtest_test_mode` in Settings

`backend/app/core/config.py:15` defines `backtest_test_mode: bool = Field(default=False, alias="BACKTEST_TEST_MODE")`. This is consumed by `backtest_service.py` to swap in `_DeterministicBacktestOpenAIClient`. After the refactor, this setting must be repurposed to control deterministic webhook behavior (auto-complete cycles without real n8n) rather than removed entirely, because `frontend/scripts/start-playwright-backend.mjs:13` sets `BACKTEST_TEST_MODE=1` for E2E tests.

**Fix:** In Task 6, keep `backtest_test_mode` in Settings. In `BacktestCycleService.dispatch_cycle()`, when `settings.backtest_test_mode` is True, skip the real webhook POST and instead directly call `handle_trades_callback()` and `handle_cycle_complete()` with deterministic data (mirroring the old `_DeterministicBacktestOpenAIClient` behavior).

### Issue 2 (IMPORTANT): `price_mode` and `BacktestPriceMode` cleanup is incomplete

The plan says to remove `LLM_DECIDED` but doesn't fully trace the impact:
- `backend/app/schemas/backtest.py:206` — model_validator checks `price_mode == LLM_DECIDED` for `llm_price_success_rate` requirement
- `backend/app/services/backtest_engine.py:564-573` — `_resolve_execution()` has the `LLM_DECIDED` branch
- `frontend/src/pages/backtests/config.tsx:303-340` — price mode radio group with LLM_DECIDED option and conditional LLM price success rate field
- `frontend/src/pages/backtests/detail.test.tsx:37` — test fixture uses `priceMode`
- `frontend/src/lib/types/backtest.test.ts:24` — test fixture uses `priceMode`

**Fix:** Add to Task 2: remove the `model_validator` that checks `price_mode == LLM_DECIDED`. Add to Task 5: simplify `_resolve_execution()` to only return closing price. Add to Task 8: remove the entire price mode radio group and LLM price success rate field from config.tsx. Add to Task 7: update both test fixture files.

### Issue 3 (IMPORTANT): `httpx` is already a dependency

`backend/pyproject.toml` already has `httpx>=0.27,<1.0`. No new dependency needed for webhook HTTP calls. The plan's migration notes should note this.

**Fix:** In Migration Notes, change "Add httpx" to "httpx already present — use it for webhook calls."

### Issue 4 (IMPORTANT): `openai` dependency removal

`backend/pyproject.toml` has `openai>=1.76,<2.0`. After removing all OpenAI code, this dependency should be removed.

**Fix:** Add to Task 11: `cd backend && uv remove openai && uv sync`

### Issue 5 (MINOR): Missing files in Task 7

`frontend/src/pages/backtests/detail.test.tsx` has LLM fields in its test fixture (line 37+). This file needs updating alongside the type changes.

**Fix:** Add `frontend/src/pages/backtests/detail.test.tsx` to Task 7's file list.

### Issue 6 (MINOR): `config.tsx` list page test

`frontend/src/pages/backtests/config.test.tsx` and `frontend/src/pages/backtests/list.test.tsx` may reference LLM fields in test fixtures.

**Fix:** Add both test files to Task 8's file list. Grep for `llm` in those files during implementation.

### Issue 7 (MINOR): AGENTS.md updates

Multiple AGENTS.md files reference LLM config, OpenAI, and the synchronous backtest loop. These should be updated after implementation:
- `backend/AGENTS.md`
- `backend/app/services/AGENTS.md`
- `backend/app/schemas/AGENTS.md`
- `backend/app/models/AGENTS.md`
- `frontend/src/lib/types/AGENTS.md`
- `frontend/src/pages/backtests/AGENTS.md`
- `frontend/src/components/backtests/AGENTS.md`
- Root `AGENTS.md`

**Fix:** Add a Task 11 sub-step to regenerate or update AGENTS.md files after all code changes are complete.

