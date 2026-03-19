# Backtest Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved backtest module that runs portfolio-level historical simulations, stores per-cycle analysis reports, executes attributed simulated trades, and exposes pollable results plus charts in the frontend.

**Architecture:** Keep the backend on existing Ledger seams: thin `/api/v1/backtests` routes delegate to `BacktestService`, which validates the request, persists a `backtests` row, and launches a background `BacktestEngine` job backed by a dedicated SQLAlchemy session. The engine owns schedule generation, parquet-backed market data loading, OpenAI Responses API parsing, trade execution through `TradingOperationService`, report creation through `ReportService`, and terminal result aggregation, while the frontend consumes the persisted state via typed API modules, TanStack Query polling, and Recharts-based dashboard components.

**Tech Stack:** FastAPI, SQLAlchemy 2, Pydantic v2 `CamelModel`, PostgreSQL init-time schema upgrades, `openai`, `yfinance`, `pyarrow`, `exchange-calendars`, React 19, Vite, TanStack Query, `react-hook-form`, `zod`, shadcn/ui, Recharts, Vitest, Playwright.

---

## Source of Truth

- Approved spec: `docs/superpowers/specs/2026-03-20-backtest-module-design.md`
- Mandatory review fixes to preserve verbatim: Fix 1 (trade attribution), Fix 2 (new portfolio flow lives in frontend), Fix 3 (largest deposit balance selection + `depositBalanceId`), Fix 4 (portfolio-level analysis), Fix 5 (`recentActivity`), Fix 6 (crash recovery), Fix 7 (OpenAI Responses API).
- Backend dependency note: `backend/pyproject.toml` must add `yfinance`, `openai`, `pyarrow`, and `exchange-calendars`.
- Frontend dependency note: `frontend/package.json` already contains `recharts` and `date-fns`, so this plan does not add new frontend packages unless install metadata needs refreshing.

## Required Workflow

- Use `@test-driven-development` on every code task: write the failing test first, run it, implement the minimum code, rerun the targeted test, then commit.
- Use `@verification-before-completion` before marking the feature done: backend tests, frontend lint/typecheck/build/test, and clean LSP diagnostics on changed files.
- Keep route handlers thin, keep business rules in services, and reuse existing report/trading infrastructure instead of creating backtest-only duplicates.

## File Map

### Backend
- Create: `backend/app/models/backtest.py` - persistent backtest configuration, progress, recent activity, and final results.
- Modify: `backend/app/models/__init__.py` - register `Backtest` so `init_db()` creates the table.
- Modify: `backend/app/models/portfolio.py` - add `backtests` relationship for cascade-delete and service lookups.
- Modify: `backend/app/models/trading_operation.py` - add nullable `backtest_id` for attribution and cascade delete.
- Create: `backend/app/schemas/backtest.py` - request/response schemas, status/frequency enums, result DTOs, and Responses API parse models.
- Create: `backend/app/repositories/backtest.py` - newest-first listing, interrupted-run lookup, status transitions, and terminal-state guards.
- Modify: `backend/app/repositories/report.py` - query/delete reports by `backtest_<id>` tag for cleanup and context windows.
- Modify: `backend/app/repositories/trading_operation.py` - query/delete operations by `backtest_id`.
- Modify: `backend/app/repositories/balance.py` - add deposit-balance lookup helpers for selection logic.
- Create: `backend/app/services/backtest_service.py` - create/list/get/cancel/delete workflows, deposit-balance resolution, default-template creation, background launch.
- Create: `backend/app/services/backtest_engine.py` - schedule generation, parquet cache, Responses API, simulated trades, recent activity, and metrics.
- Modify: `backend/app/services/trading_operation_service.py` - allow internal backtest attribution without changing the public trading API contract.
- Modify: `backend/app/core/config.py` - add market-data cache path setting.
- Modify: `backend/app/db/session.py` - init-time schema upgrade for `trading_operations.backtest_id` and startup crash recovery.
- Create: `backend/app/api/backtests.py` - thin route handlers for list/create/get/cancel/delete.
- Modify: `backend/app/api/dependencies.py` - wire `BacktestService` and required factories.
- Modify: `backend/app/api/router.py` - mount the new router.
- Modify: `backend/pyproject.toml` - add backend runtime dependencies.

### Frontend
- Create: `frontend/src/lib/types/backtest.ts` - wire types for requests, status, recent activity, metrics, curves, and trades.
- Create: `frontend/src/lib/api/backtests.ts` - request helpers for list/create/get/cancel/delete.
- Modify: `frontend/src/lib/api.ts` - export the new API module.
- Modify: `frontend/src/lib/api-types.ts` - export backtest types.
- Modify: `frontend/src/lib/query-keys.ts` - add canonical backtest list/detail keys.
- Create: `frontend/src/hooks/use-backtests.ts` - list/detail/polling plus create/cancel/delete mutations.
- Modify: `frontend/src/routes.ts` - add `/backtests`, `/backtests/new`, `/backtests/:id`.
- Modify: `frontend/src/components/layout.tsx` - add sidebar nav item, icon, and breadcrumb labels.
- Modify: `frontend/src/components/shared/form-schemas.ts` - add backtest config form schema.
- Create: `frontend/src/pages/backtests/list.tsx` - inventory page with status cards, progress, delete action.
- Create: `frontend/src/pages/backtests/config.tsx` - create form with existing/new portfolio flow and validation summary.
- Create: `frontend/src/pages/backtests/detail.tsx` - running-state polling view plus completed dashboard.
- Create: `frontend/src/components/backtests/backtest-status-badge.tsx` - consistent badge colors.
- Create: `frontend/src/components/backtests/metrics-summary.tsx` - six KPI cards.
- Create: `frontend/src/components/backtests/trade-log-table.tsx` - sortable trade log.
- Create: `frontend/src/components/backtests/equity-curve-chart.tsx` - portfolio + benchmark lines with toggles.
- Create: `frontend/src/components/backtests/drawdown-chart.tsx` - drawdown area chart.
- No change planned: `frontend/package.json` already includes `recharts` and `date-fns`.

### Tests
- Create: `backend/tests/test_backtests_api.py` - API, service-level behavior, schema upgrade, crash recovery, and cleanup regression coverage.
- Create: `backend/tests/test_backtest_engine.py` - schedule generation, prompt composition, cache behavior, trade execution, recent activity, and metrics.
- Modify: `frontend/src/lib/api.test.ts` - request helper coverage for `backtestsApi`.
- Modify: `frontend/src/lib/query-keys.test.ts` - backtest key normalization + polling key stability.
- Create: `frontend/src/pages/backtests/list.test.tsx` - navigation and inventory rendering.
- Create: `frontend/src/pages/backtests/config.test.tsx` - validation and new-portfolio orchestration.
- Create: `frontend/src/pages/backtests/detail.test.tsx` - polling and terminal-state rendering.
- Create: `frontend/src/components/backtests/equity-curve-chart.test.tsx` - toggle behavior and chart labels.
- Create: `frontend/e2e/backtests.spec.ts` - end-to-end create/poll/results/delete flow.

## Phase 1: Backend Data Layer

Spec anchors: "Data Model", "Updated Data Model (consolidated)", Fix 1, Fix 3, Fix 5.

### Task 1: Add the `Backtest` ORM model and register it

**Files:**
- Create: `backend/app/models/backtest.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/portfolio.py`
- Test: `backend/tests/test_backtests_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_init_db_creates_backtests_table(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("backtests")}
        assert {
            "portfolio_id",
            "deposit_balance_id",
            "status",
            "frequency",
            "benchmark_symbols",
            "recent_activity",
            "results",
        } <= columns
    finally:
        engine.dispose()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_init_db_creates_backtests_table -v`  
Expected: FAIL with `NoSuchTableError` or missing `backtests` columns.

- [ ] **Step 3: Write minimal implementation**

```python
class Backtest(IdMixin, TimestampMixin, Base):
    __tablename__ = "backtests"
    __table_args__ = (
        Index("ix_backtests_portfolio_id", "portfolio_id"),
        Index("ix_backtests_status", "status"),
    )

    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    deposit_balance_id: Mapped[int] = mapped_column(
        ForeignKey("balances.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    frequency: Mapped[str] = mapped_column(String(10), nullable=False)
    benchmark_symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    recent_activity: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    results: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="backtests")
```

Also add `Backtest` to `backend/app/models/__init__.py` and `Portfolio.backtests` in `backend/app/models/portfolio.py`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_init_db_creates_backtests_table -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/backtest.py backend/app/models/__init__.py backend/app/models/portfolio.py backend/tests/test_backtests_api.py
git commit -m "feat: add backtest persistence model"
```

### Task 2: Add `trading_operations.backtest_id` and init-time schema upgrade

**Files:**
- Modify: `backend/app/models/trading_operation.py`
- Modify: `backend/app/db/session.py`
- Modify: `backend/app/repositories/trading_operation.py`
- Test: `backend/tests/test_backtests_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_init_db_upgrades_trading_operations_with_backtest_id(database_url: str) -> None:
    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE portfolios (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    slug VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    base_currency VARCHAR(3) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE trading_operations (
                    id SERIAL PRIMARY KEY,
                    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                    balance_id INTEGER NULL,
                    balance_label VARCHAR(60) NOT NULL,
                    symbol VARCHAR(32) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    quantity NUMERIC(20, 8),
                    price NUMERIC(20, 8),
                    commission NUMERIC(20, 4) NOT NULL DEFAULT 0,
                    currency VARCHAR(3) NOT NULL,
                    dividend_amount NUMERIC(20, 4),
                    split_ratio NUMERIC(10, 6),
                    executed_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

        init_db(database_url)
        columns = {column["name"] for column in inspect(engine).get_columns("trading_operations")}
        assert "backtest_id" in columns
    finally:
        engine.dispose()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_init_db_upgrades_trading_operations_with_backtest_id -v`  
Expected: FAIL because `backtest_id` is absent after `init_db()`.

- [ ] **Step 3: Write minimal implementation**

```python
backtest_id: Mapped[int | None] = mapped_column(
    ForeignKey("backtests.id", ondelete="CASCADE"), nullable=True
)

if "trading_operations" in table_names:
    columns = {column["name"] for column in inspector.get_columns("trading_operations")}
    if "backtest_id" not in columns:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE trading_operations "
                "ADD COLUMN backtest_id INTEGER REFERENCES backtests(id) ON DELETE CASCADE"
            )
```

Also add `list_for_backtest()` / `delete_for_backtest()` helpers in `backend/app/repositories/trading_operation.py`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_init_db_upgrades_trading_operations_with_backtest_id -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/trading_operation.py backend/app/db/session.py backend/app/repositories/trading_operation.py backend/tests/test_backtests_api.py
git commit -m "feat: attribute trading operations to backtests"
```

### Task 3: Add backtest request/response schemas and structured LLM DTOs

**Files:**
- Create: `backend/app/schemas/backtest.py`
- Test: `backend/tests/test_backtests_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_backtest_get_redacts_llm_api_key(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    balance = create_balance(client, str(portfolio["id"]))
    template = create_template(client, name="Backtest Template", content="# Backtest")

    response = client.post(
        "/api/v1/backtests",
        json={
            "name": "Daily Backtest",
            "portfolioId": portfolio["id"],
            "templateId": template["id"],
            "createTemplate": False,
            "frequency": "DAILY",
            "startDate": "2024-01-02",
            "endDate": "2024-03-29",
            "llmBaseUrl": "http://localhost:11434/v1",
            "llmApiKey": "secret-token",
            "llmModel": "qwen2.5:72b",
            "priceMode": "CLOSING_PRICE",
            "commissionMode": "ZERO",
            "commissionValue": "0",
            "benchmarkSymbols": ["^GSPC"],
        },
    )
    assert response.status_code == 201
    assert response.json()["llmApiKey"] == "***"
    assert response.json()["depositBalanceId"] == balance["id"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_backtest_get_redacts_llm_api_key -v`  
Expected: FAIL because the endpoint/schema does not exist yet or the field is not redacted.

- [ ] **Step 3: Write minimal implementation**

```python
class BacktestCreate(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    portfolio_id: int
    template_id: int | None = None
    create_template: bool = False
    template_name: str | None = None
    frequency: Literal["DAILY", "WEEKLY", "MONTHLY"]
    start_date: date
    end_date: date
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    price_mode: Literal["CLOSING_PRICE", "LLM_DECIDED"]
    llm_price_success_rate: Decimal | None = None
    commission_mode: Literal["FIXED", "PERCENTAGE", "ZERO"]
    commission_value: Decimal = Decimal("0")
    benchmark_symbols: list[str]

class BacktestRead(CamelModel):
    id: int
    deposit_balance_id: int
    llm_api_key: str = "***"
    recent_activity: list[RecentActivityEntry] | None = None
    results: BacktestResults | None = None
```

Also define `TradeDecision`, `AnalysisResponse`, `RecentActivityEntry`, `BacktestResults`, `BacktestTradeLogEntry`, and validators for past-only date ranges, benchmark non-emptiness, LLM success rate, and commission percentage fraction.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_backtest_get_redacts_llm_api_key -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/backtest.py backend/tests/test_backtests_api.py
git commit -m "feat: add backtest API schemas"
```

### Task 4: Add repository support for backtests, backtest-tagged reports, and cleanup queries

**Files:**
- Create: `backend/app/repositories/backtest.py`
- Modify: `backend/app/repositories/report.py`
- Modify: `backend/app/repositories/balance.py`
- Test: `backend/tests/test_backtests_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_backtest_repository_lists_newest_first(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        repo = BacktestRepository(session)
        first = Backtest(
            portfolio_id=1,
            deposit_balance_id=10,
            name="First",
            status="PENDING",
            frequency="DAILY",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 31),
            total_cycles=21,
            completed_cycles=0,
            template_id=11,
            llm_base_url="http://localhost:11434/v1",
            llm_api_key="ollama",
            llm_model="qwen2.5:72b",
            price_mode="CLOSING_PRICE",
            commission_mode="ZERO",
            commission_value=Decimal("0"),
            benchmark_symbols=["^GSPC"],
        )
        second = Backtest(
            portfolio_id=1,
            deposit_balance_id=10,
            name="Second",
            status="RUNNING",
            frequency="WEEKLY",
            start_date=date(2024, 2, 1),
            end_date=date(2024, 3, 29),
            total_cycles=9,
            completed_cycles=1,
            template_id=11,
            llm_base_url="http://localhost:11434/v1",
            llm_api_key="ollama",
            llm_model="qwen2.5:72b",
            price_mode="CLOSING_PRICE",
            commission_mode="ZERO",
            commission_value=Decimal("0"),
            benchmark_symbols=["^GSPC"],
        )
        session.add_all([first, second])
        session.commit()

        ordered = repo.list_all()
        assert ordered[0].id == second.id
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_backtest_repository_lists_newest_first -v`  
Expected: FAIL with `ModuleNotFoundError` or missing repository methods.

- [ ] **Step 3: Write minimal implementation**

```python
class BacktestRepository(BaseRepository[Backtest]):
    model = Backtest

    def list_all(self) -> list[Backtest]:
        statement = select(self.model).order_by(self.model.created_at.desc(), self.model.id.desc())
        return self._list(statement)

    def list_interrupted(self) -> list[Backtest]:
        statement = select(self.model).where(self.model.status.in_(("PENDING", "RUNNING")))
        return self._list(statement)
```

Add `BalanceRepository.list_deposit_balances_for_portfolio()` and `ReportRepository.list_for_backtest_tag(tag: str)` / `delete_for_backtest_tag(tag: str)` so service and engine code stay query-centric.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_backtest_repository_lists_newest_first -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/backtest.py backend/app/repositories/report.py backend/app/repositories/balance.py backend/tests/test_backtests_api.py
git commit -m "feat: add backtest repository helpers"
```

## Phase 2: Backend Services

Spec anchors: "BacktestService (CRUD + thread launch)", Fix 2, Fix 3, Fix 4.

### Task 5: Create backtests and launch the background engine

**Files:**
- Create: `backend/app/services/backtest_service.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_backtests_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_create_backtest_returns_pending_and_submits_engine(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    submitted: list[int] = []

    class DummyFuture:
        def add_done_callback(self, _callback):
            return None

    monkeypatch.setattr(
        "app.services.backtest_service._BACKTEST_EXECUTOR.submit",
        lambda fn, backtest_id: submitted.append(backtest_id) or DummyFuture(),
    )

    portfolio = create_portfolio(client)
    create_balance(client, str(portfolio["id"]), amount="10000.00")
    template = create_template(client, name="Backtest Template", content="# Template")

    response = client.post(
        "/api/v1/backtests",
        json={
            "name": "Daily Backtest",
            "portfolioId": portfolio["id"],
            "templateId": template["id"],
            "createTemplate": False,
            "frequency": "DAILY",
            "startDate": "2024-01-02",
            "endDate": "2024-03-29",
            "llmBaseUrl": "http://localhost:11434/v1",
            "llmApiKey": "ollama",
            "llmModel": "qwen2.5:72b",
            "priceMode": "CLOSING_PRICE",
            "commissionMode": "ZERO",
            "commissionValue": "0",
            "benchmarkSymbols": ["^GSPC"],
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "PENDING"
    assert submitted == [response.json()["id"]]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_create_backtest_returns_pending_and_submits_engine -v`  
Expected: FAIL because `BacktestService` and the endpoint do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
_BACKTEST_EXECUTOR = ThreadPoolExecutor(thread_name_prefix="backtest")

class BacktestService:
    def __init__(self, session: Session, session_factory: sessionmaker[Session]) -> None:
        self.session = session
        self.session_factory = session_factory
        self.repository = BacktestRepository(session)
        self.portfolio_service = PortfolioService(session)
        self.template_service = TextTemplateService(session)

    def create_backtest(self, payload: BacktestCreate) -> BacktestRead:
        backtest = Backtest(
            portfolio_id=payload.portfolio_id,
            deposit_balance_id=deposit_balance.id,
            name=payload.name,
            status="PENDING",
            frequency=payload.frequency,
            start_date=payload.start_date,
            end_date=payload.end_date,
            total_cycles=0,
            completed_cycles=0,
            template_id=template_id,
            llm_base_url=payload.llm_base_url,
            llm_api_key=payload.llm_api_key,
            llm_model=payload.llm_model,
            price_mode=payload.price_mode,
            llm_price_success_rate=payload.llm_price_success_rate,
            commission_mode=payload.commission_mode,
            commission_value=payload.commission_value,
            benchmark_symbols=payload.benchmark_symbols,
        )
        self.repository.add(backtest)
        self.session.commit()
        self.session.refresh(backtest)
        _BACKTEST_EXECUTOR.submit(self.run_backtest, backtest.id)
        return BacktestRead.model_validate(backtest)
```

Add `market_data_cache_dir` to `backend/app/core/config.py` with default `backend/.cache/market_data`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_create_backtest_returns_pending_and_submits_engine -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/backtest_service.py backend/app/core/config.py backend/tests/test_backtests_api.py
git commit -m "feat: launch backtests from service layer"
```

### Task 6: Resolve and persist the deposit balance at create time

**Files:**
- Modify: `backend/app/services/backtest_service.py`
- Test: `backend/tests/test_backtests_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_create_backtest_uses_largest_deposit_balance(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    smaller = create_balance(client, str(portfolio["id"]), label="Cash A", amount="1000.00")
    larger = create_balance(client, str(portfolio["id"]), label="Cash B", amount="2500.00")
    create_balance(
        client,
        str(portfolio["id"]),
        label="Taxes",
        amount="300.00",
        operation_type="WITHDRAWAL",
    )
    template = create_template(client, name="Backtest Template", content="# Template")

    response = client.post(
        "/api/v1/backtests",
        json={
            "name": "Balance Selection Backtest",
            "portfolioId": portfolio["id"],
            "templateId": template["id"],
            "createTemplate": False,
            "frequency": "DAILY",
            "startDate": "2024-01-02",
            "endDate": "2024-03-29",
            "llmBaseUrl": "http://localhost:11434/v1",
            "llmApiKey": "ollama",
            "llmModel": "qwen2.5:72b",
            "priceMode": "CLOSING_PRICE",
            "commissionMode": "ZERO",
            "commissionValue": "0",
            "benchmarkSymbols": ["^GSPC"],
        },
    )
    assert response.status_code == 201
    assert response.json()["depositBalanceId"] == larger["id"]
    assert response.json()["depositBalanceId"] != smaller["id"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_create_backtest_uses_largest_deposit_balance -v`  
Expected: FAIL because balance selection is missing or wrong.

- [ ] **Step 3: Write minimal implementation**

```python
def _resolve_deposit_balance(self, portfolio_id: int) -> Balance:
    balances = self.balance_repository.list_deposit_balances_for_portfolio(portfolio_id)
    if not balances:
        raise business_rule_error(
            "missing_deposit_balance",
            "Backtests require at least one deposit balance",
        )
    return max(balances, key=lambda balance: balance.amount)
```

Store `deposit_balance_id` on the `Backtest` row before the first commit and include it on `BacktestRead`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_create_backtest_uses_largest_deposit_balance -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/backtest_service.py backend/tests/test_backtests_api.py
git commit -m "feat: persist the selected deposit balance on backtests"
```

### Task 7: Support default-template creation and request validation

**Files:**
- Modify: `backend/app/services/backtest_service.py`
- Modify: `backend/app/schemas/backtest.py`
- Test: `backend/tests/test_backtests_api.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_create_backtest_can_auto_create_default_template(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    create_balance(client, str(portfolio["id"]), amount="5000.00")

    response = client.post(
        "/api/v1/backtests",
        json={
            "name": "Monthly Backtest",
            "portfolioId": portfolio["id"],
            "templateId": None,
            "createTemplate": True,
            "templateName": "Portfolio Backtest Default",
            "frequency": "MONTHLY",
            "startDate": "2024-01-02",
            "endDate": "2024-12-31",
            "llmBaseUrl": "http://localhost:11434/v1",
            "llmApiKey": "ollama",
            "llmModel": "qwen2.5:72b",
            "priceMode": "LLM_DECIDED",
            "llmPriceSuccessRate": "0.50",
            "commissionMode": "FIXED",
            "commissionValue": "1.00",
            "benchmarkSymbols": ["^GSPC", "^IXIC"],
        },
    )
    assert response.status_code == 201
    assert response.json()["templateId"] is not None

def test_create_backtest_rejects_missing_template_selection(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    create_balance(client, str(portfolio["id"]), amount="5000.00")

    response = client.post(
        "/api/v1/backtests",
        json={
            "name": "Invalid Backtest",
            "portfolioId": portfolio["id"],
            "templateId": None,
            "createTemplate": False,
            "frequency": "MONTHLY",
            "startDate": "2024-01-02",
            "endDate": "2024-12-31",
            "llmBaseUrl": "http://localhost:11434/v1",
            "llmApiKey": "ollama",
            "llmModel": "qwen2.5:72b",
            "priceMode": "CLOSING_PRICE",
            "commissionMode": "ZERO",
            "commissionValue": "0",
            "benchmarkSymbols": ["^GSPC"],
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "missing_template"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_backtests_api.py -k "auto_create_default_template or missing_template_selection" -v`  
Expected: FAIL because template auto-creation and validation are missing.

- [ ] **Step 3: Write minimal implementation**

```python
_DEFAULT_BACKTEST_TEMPLATE = """# Portfolio Analysis ({{inputs.cycle_date}})

## Instructions
You are analyzing all positions in portfolio {{inputs.portfolio_name}}.
Analysis frequency: {{inputs.frequency}}.

CRITICAL: Today is {{inputs.cycle_date}}. Do NOT use any information from after this date.

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
"""

def _resolve_template_id(self, payload: BacktestCreate) -> int:
    if payload.template_id is not None:
        return payload.template_id
    if not payload.create_template:
        raise business_rule_error("missing_template", "Select a template or enable default template creation")
    created = self.template_service.create_template(
        TextTemplateCreate(
            name=payload.template_name or f"{payload.name} Backtest Template",
            content=_DEFAULT_BACKTEST_TEMPLATE,
        )
    )
    return created.id
```

Keep the default template at portfolio level exactly as written in spec Fix 4.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_backtests_api.py -k "auto_create_default_template or missing_template_selection" -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/backtest_service.py backend/app/schemas/backtest.py backend/tests/test_backtests_api.py
git commit -m "feat: support default backtest template creation"
```

### Task 8: Enforce cancel/delete lifecycle rules and cascade cleanup

**Files:**
- Modify: `backend/app/services/backtest_service.py`
- Modify: `backend/app/repositories/report.py`
- Modify: `backend/app/repositories/trading_operation.py`
- Test: `backend/tests/test_backtests_api.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_cancel_backtest_marks_running_job_cancelled(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    create_balance(client, str(portfolio["id"]), amount="10000.00")
    template = create_template(client, name="Cancel Template", content="# Cancel")
    create_response = client.post(
        "/api/v1/backtests",
        json={
            "name": "Cancelable Backtest",
            "portfolioId": portfolio["id"],
            "templateId": template["id"],
            "createTemplate": False,
            "frequency": "DAILY",
            "startDate": "2024-01-02",
            "endDate": "2024-03-29",
            "llmBaseUrl": "http://localhost:11434/v1",
            "llmApiKey": "ollama",
            "llmModel": "qwen2.5:72b",
            "priceMode": "CLOSING_PRICE",
            "commissionMode": "ZERO",
            "commissionValue": "0",
            "benchmarkSymbols": ["^GSPC"],
        },
    )
    backtest_id = create_response.json()["id"]
    cancel_response = client.post(f"/api/v1/backtests/{backtest_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "CANCELLED"

def test_delete_backtest_requires_terminal_state_and_cleans_reports_and_trades(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    portfolio = create_portfolio(client)
    balance = create_balance(client, str(portfolio["id"]), amount="10000.00")
    template = create_template(client, name="Cleanup Template", content="# Cleanup")
    create_response = client.post(
        "/api/v1/backtests",
        json={
            "name": "Cleanup Backtest",
            "portfolioId": portfolio["id"],
            "templateId": template["id"],
            "createTemplate": False,
            "frequency": "DAILY",
            "startDate": "2024-01-02",
            "endDate": "2024-03-29",
            "llmBaseUrl": "http://localhost:11434/v1",
            "llmApiKey": "ollama",
            "llmModel": "qwen2.5:72b",
            "priceMode": "CLOSING_PRICE",
            "commissionMode": "ZERO",
            "commissionValue": "0",
            "benchmarkSymbols": ["^GSPC"],
        },
    )
    completed_backtest = create_response.json()

    with session_factory() as session:
        backtest = session.get(Backtest, completed_backtest["id"])
        backtest.status = "COMPLETED"
        session.add(
            TradingOperation(
                portfolio_id=portfolio["id"],
                balance_id=balance["id"],
                backtest_id=completed_backtest["id"],
                balance_label="Initial Cash",
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("5"),
                price=Decimal("184.40"),
                commission=Decimal("0"),
                currency="USD",
                executed_at=datetime(2024, 1, 15, 20, 30, tzinfo=UTC),
            )
        )
        session.add(
            Report(
                name="backtest_42_20240115",
                slug="backtest_42_20240115",
                source="external",
                content="# Backtest report",
                metadata_={"tags": ["backtest", f"backtest_{completed_backtest['id']}"]},
            )
        )
        session.commit()

    delete_response = client.delete(f"/api/v1/backtests/{completed_backtest['id']}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/v1/backtests/{completed_backtest['id']}").status_code == 404
    with session_factory() as session:
        assert session.scalar(
            select(func.count(TradingOperation.id)).where(
                TradingOperation.backtest_id == completed_backtest["id"]
            )
        ) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_backtests_api.py -k "cancel_backtest or cleans_reports_and_trades" -v`  
Expected: FAIL because cancel/delete rules are not implemented.

- [ ] **Step 3: Write minimal implementation**

```python
def cancel_backtest(self, backtest_id: int) -> BacktestRead:
    backtest = self.get_backtest_model(backtest_id)
    if backtest.status not in {"PENDING", "RUNNING"}:
        raise business_rule_error("invalid_backtest_state", "Only pending or running backtests can be cancelled")
    backtest.status = "CANCELLED"
    self.session.commit()
    self.session.refresh(backtest)
    return BacktestRead.model_validate(backtest)

def delete_backtest(self, backtest_id: int) -> None:
    backtest = self.get_backtest_model(backtest_id)
    if backtest.status not in {"COMPLETED", "FAILED", "CANCELLED"}:
        raise business_rule_error("invalid_backtest_state", "Only terminal backtests can be deleted")
    self.report_repository.delete_for_backtest_tag(f"backtest_{backtest.id}")
    self.trading_operation_repository.delete_for_backtest(backtest.id)
    self.repository.delete(backtest)
    self.session.commit()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_backtests_api.py -k "cancel_backtest or cleans_reports_and_trades" -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/backtest_service.py backend/app/repositories/report.py backend/app/repositories/trading_operation.py backend/tests/test_backtests_api.py
git commit -m "feat: support backtest cancellation and cleanup"
```

## Phase 3: Backend Engine

Spec anchors: "Simulation Engine", "Cycle schedule generation", "Market data disk cache", Fix 4, Fix 5, Fix 7, advisory fixes.

### Task 9: Generate trading schedules and prior-report context windows

**Files:**
- Create: `backend/app/services/backtest_engine.py`
- Test: `backend/tests/test_backtest_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_generate_schedule_uses_nyse_trading_days_for_each_frequency() -> None:
    engine = BacktestEngine(
        backtest=SimpleNamespace(frequency="DAILY"),
        session_factory=None,
        settings=SimpleNamespace(market_data_cache_dir="backend/.cache/market_data"),
        openai_client=None,
        quote_provider=None,
        rng=random.Random(7),
    )
    assert engine._build_schedule(date(2024, 1, 2), date(2024, 1, 10), "DAILY") == [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 8),
        date(2024, 1, 9),
        date(2024, 1, 10),
    ]

def test_prior_report_window_matches_frequency_rules() -> None:
    engine = BacktestEngine(
        backtest=SimpleNamespace(frequency="DAILY"),
        session_factory=None,
        settings=SimpleNamespace(market_data_cache_dir="backend/.cache/market_data"),
        openai_client=None,
        quote_provider=None,
        rng=random.Random(7),
    )
    assert engine._prior_report_limit("DAILY") == 1
    assert engine._prior_report_limit("WEEKLY") == 5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_backtest_engine.py -k "generate_schedule or prior_report_window" -v`  
Expected: FAIL with missing `BacktestEngine`.

- [ ] **Step 3: Write minimal implementation**

```python
_CALENDAR = exchange_calendars.get_calendar("XNYS")

def _build_schedule(self, start_date: date, end_date: date, frequency: str) -> list[date]:
    sessions = _CALENDAR.sessions_in_range(pd.Timestamp(start_date), pd.Timestamp(end_date))
    trading_days = [session.date() for session in sessions]
    if frequency == "DAILY":
        return trading_days
    if frequency == "WEEKLY":
        return _last_sessions_per_period(trading_days, period="week")
    return _last_sessions_per_period(trading_days, period="month")

def _prior_report_limit(self, frequency: str) -> int | None:
    return {"DAILY": 1, "WEEKLY": 5, "MONTHLY": None}[frequency]
```

Use the spec’s monthly rule by selecting only same-month prior reports when frequency is `MONTHLY`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_backtest_engine.py -k "generate_schedule or prior_report_window" -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/backtest_engine.py backend/tests/test_backtest_engine.py
git commit -m "feat: generate backtest schedules from the NYSE calendar"
```

### Task 10: Add parquet-backed market data caching and backend dependencies

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/services/backtest_engine.py`
- Test: `backend/tests/test_backtest_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_market_data_cache_writes_and_reuses_parquet(tmp_path: Path) -> None:
    engine = BacktestEngine(
        cache_dir=tmp_path,
        quote_provider=FakeHistoryProvider(
            history_rows=[
                {"date": "2024-01-02", "open": 183.0, "high": 186.0, "low": 182.5, "close": 185.2, "volume": 1000},
                {"date": "2024-01-03", "open": 185.1, "high": 187.0, "low": 184.2, "close": 186.4, "volume": 1200},
            ]
        ),
    )
    first = engine._load_symbol_history("AAPL", date(2024, 1, 2), date(2024, 3, 31))
    second = engine._load_symbol_history("AAPL", date(2024, 1, 2), date(2024, 3, 31))

    assert (tmp_path / "AAPL.parquet").exists()
    assert second.equals(first)
    assert engine.quote_provider.fetch_history_calls == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_backtest_engine.py::test_market_data_cache_writes_and_reuses_parquet -v`  
Expected: FAIL because the cache layer and dependencies are missing.

- [ ] **Step 3: Write minimal implementation**

```toml
dependencies = [
  "fastapi>=0.115,<1.0",
  "httpx>=0.27,<1.0",
  "psycopg[binary]>=3.2,<4.0",
  "pydantic-settings>=2.3,<3.0",
  "python-multipart>=0.0.9,<1.0",
  "sqlalchemy>=2.0,<3.0",
  "uvicorn[standard]>=0.30,<1.0",
  "exchange-calendars>=4.7,<5.0",
  "openai>=1.76,<2.0",
  "pyarrow>=19.0,<20.0",
  "yfinance>=0.2.54,<0.3.0",
]
```

```python
market_data_cache_dir: str = Field(
    default="backend/.cache/market_data",
    alias="MARKET_DATA_CACHE_DIR",
)

def _load_symbol_history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
    cache_path = Path(self.settings.market_data_cache_dir) / f"{symbol}.parquet"
    if cache_path.exists():
        cached = pd.read_parquet(cache_path)
        if cached.index.max().date() >= end:
            return cached.loc[str(start):str(end)]
    fetched = self._download_history(symbol, start, end)
    fetched.to_parquet(cache_path)
    return fetched
```

Also implement the "append only missing dates" branch instead of always refetching full history.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_backtest_engine.py::test_market_data_cache_writes_and_reuses_parquet -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/app/core/config.py backend/app/services/backtest_engine.py backend/tests/test_backtest_engine.py
git commit -m "feat: cache backtest market data to parquet"
```

### Task 11: Build the portfolio-level prompt and parse Responses API output

**Files:**
- Modify: `backend/app/services/backtest_engine.py`
- Test: `backend/tests/test_backtest_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_call_llm_uses_responses_api_and_returns_analysis_response(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return type("Response", (), {"output_text": json.dumps({
                "overall_assessment": "Portfolio remains concentrated in mega-cap tech.",
                "decisions": [{"symbol": "AAPL", "action": "HOLD", "reasoning": "No material change."}],
                "reflection": "Prior thesis still holds."
            })})()

    engine = BacktestEngine(
        backtest=SimpleNamespace(llm_model="qwen2.5:72b"),
        session_factory=None,
        settings=SimpleNamespace(market_data_cache_dir="backend/.cache/market_data"),
        openai_client=type("Client", (), {"responses": FakeResponses()})(),
        quote_provider=None,
        rng=random.Random(7),
    )
    analysis = engine._call_llm(system_prompt="system", user_prompt="user")
    assert analysis.decisions[0].symbol == "AAPL"
    assert captured["text"]["format"]["type"] == "json_schema"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_backtest_engine.py::test_call_llm_uses_responses_api_and_returns_analysis_response -v`  
Expected: FAIL because the Responses API integration does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def _call_llm(self, *, system_prompt: str, user_prompt: str) -> AnalysisResponse:
    response = self.openai_client.responses.create(
        model=self.backtest.llm_model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        text={
            "format": {
                "type": "json_schema",
                "schema": AnalysisResponse.model_json_schema(),
            }
        },
    )
    return AnalysisResponse.model_validate(json.loads(response.output_text))
```

Also make the prompt builder portfolio-level: include all positions, cash, 30 trading days of OHLCV per symbol, benchmark performance, and prior reports tagged `backtest_<id>`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_backtest_engine.py::test_call_llm_uses_responses_api_and_returns_analysis_response -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/backtest_engine.py backend/tests/test_backtest_engine.py
git commit -m "feat: call the LLM through the Responses API"
```

### Task 12: Execute trades through `TradingOperationService` and update `recentActivity`

**Files:**
- Modify: `backend/app/services/backtest_engine.py`
- Modify: `backend/app/services/trading_operation_service.py`
- Test: `backend/tests/test_backtest_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_executed_trades_are_attributed_to_backtest_and_recent_activity_is_trimmed() -> None:
    engine = build_engine(
        backtest_id=42,
        portfolio_id=7,
        deposit_balance_id=3,
        price_mode="LLM_DECIDED",
        llm_price_success_rate=Decimal("1.0"),
    )
    engine._apply_decisions(
        cycle_date=date(2024, 6, 15),
        decisions=[TradeDecision(symbol="AAPL", action="BUY", quantity=3, target_price=184.4, reasoning="Thesis improved.")],
        market_data={
            "AAPL": {
                "open": Decimal("183.50"),
                "high": Decimal("185.00"),
                "low": Decimal("183.25"),
                "close": Decimal("184.40"),
                "volume": 1000000,
            }
        },
    )
    operations = trading_operation_repo.list_for_backtest(engine.backtest.id)
    assert operations[0].backtest_id == engine.backtest.id
    assert len(engine._refresh_backtest().recent_activity) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_backtest_engine.py::test_executed_trades_are_attributed_to_backtest_and_recent_activity_is_trimmed -v`  
Expected: FAIL because trade attribution and recent activity are missing.

- [ ] **Step 3: Write minimal implementation**

```python
result = self.trading_service.create_operation(
    self.backtest.portfolio_id,
    BuyOperationCreate(
        balance_id=self.backtest.deposit_balance_id,
        symbol=decision.symbol,
        quantity=Decimal(decision.quantity),
        price=execution_price,
        commission=commission,
        executed_at=self._cycle_execution_time(cycle_date),
        side="BUY",
    ),
    backtest_id=self.backtest.id,
)

activity_entry = {
    "cycleDate": cycle_date.isoformat(),
    "decisions": decision_summaries,
}
self.backtest.recent_activity = (self.backtest.recent_activity or [])[-9:] + [activity_entry]
```

Change `TradingOperationService.create_operation(self, portfolio_id: int, payload: TradingOperationCreate, backtest_id: int | None = None)` so internal callers can persist the FK without exposing it on the public HTTP contract.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_backtest_engine.py::test_executed_trades_are_attributed_to_backtest_and_recent_activity_is_trimmed -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/backtest_engine.py backend/app/services/trading_operation_service.py backend/tests/test_backtest_engine.py
git commit -m "feat: execute attributed backtest trades and record recent activity"
```

### Task 13: Compute final metrics, curves, and trade log payloads

**Files:**
- Modify: `backend/app/services/backtest_engine.py`
- Test: `backend/tests/test_backtest_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_compute_results_returns_spec_metrics_payload() -> None:
    engine = build_engine(backtest_id=42, portfolio_id=7, deposit_balance_id=3)
    results = engine._compute_results(
        equity_points=[("2024-01-02", Decimal("100000")), ("2024-12-31", Decimal("118450"))],
        benchmark_history={"^GSPC": [("2024-01-02", Decimal("4769.83")), ("2024-12-31", Decimal("5881.63"))]},
        trade_log=[
            {
                "cycleDate": "2024-01-15",
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": "5",
                "requestedPrice": "185.50",
                "executedPrice": "184.40",
                "executed": True,
                "reportSlug": "backtest_42_20240115",
            }
        ],
    )
    assert results["portfolio"]["totalReturn"] == "0.1845"
    assert results["portfolio"]["sharpeRatio"] is not None
    assert results["drawdownCurve"][0]["value"] == "0.0000"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_backtest_engine.py::test_compute_results_returns_spec_metrics_payload -v`  
Expected: FAIL because result assembly is incomplete.

- [ ] **Step 3: Write minimal implementation**

```python
def _compute_results(
    self,
    *,
    equity_points: list[tuple[str, Decimal]],
    benchmark_history: dict[str, list[tuple[str, Decimal]]],
    trade_log: list[dict[str, Any]],
) -> dict[str, Any]:
    total_return = (ending_value - starting_value) / starting_value
    annualized_return = ((ending_value / starting_value) ** (Decimal("365") / Decimal(day_count))) - 1
    max_drawdown, drawdown_curve = self._drawdown_metrics(equity_curve)
    sharpe_ratio = self._sharpe_ratio(daily_returns, risk_free_rate=Decimal("0"))
    win_rate = self._win_rate(executed_sell_operations)
    return {
        "portfolio": {
            "startingValue": decimal_to_string(starting_value),
            "endingValue": decimal_to_string(ending_value),
            "totalReturn": decimal_to_string(total_return, places=4),
            "annualizedReturn": decimal_to_string(annualized_return, places=4),
            "maxDrawdown": decimal_to_string(max_drawdown, places=4),
            "sharpeRatio": decimal_to_string(sharpe_ratio, places=2),
        },
        "benchmarks": benchmark_summary,
        "equityCurve": equity_curve,
        "benchmarkCurves": benchmark_curves,
        "drawdownCurve": drawdown_curve,
        "trades": trade_log,
    }
```

Honor the advisory fixes exactly: 0% risk-free rate, win rate based on profitable sell operations, and commission percentage treated as a decimal fraction.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_backtest_engine.py::test_compute_results_returns_spec_metrics_payload -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/backtest_engine.py backend/tests/test_backtest_engine.py
git commit -m "feat: persist backtest result metrics and curves"
```

## Phase 4: Backend API

Spec anchors: "API Design", "Endpoints", Fix 6.

### Task 14: Wire dependencies and expose thin `/api/v1/backtests` routes

**Files:**
- Create: `backend/app/api/backtests.py`
- Modify: `backend/app/api/dependencies.py`
- Modify: `backend/app/api/router.py`
- Test: `backend/tests/test_backtests_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_backtest_routes_support_list_get_cancel_and_delete(client: TestClient) -> None:
    list_response = client.get("/api/v1/backtests")
    assert list_response.status_code == 200
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_backtest_routes_support_list_get_cancel_and_delete -v`  
Expected: FAIL with 404 because the router is not mounted.

- [ ] **Step 3: Write minimal implementation**

```python
router = APIRouter(prefix="/backtests", tags=["backtests"])

@router.get("", response_model=list[BacktestRead])
def list_backtests(service: Annotated[BacktestService, Depends(get_backtest_service)]) -> list[BacktestRead]:
    return service.list_backtests()

@router.post("", response_model=BacktestRead, status_code=status.HTTP_201_CREATED)
def create_backtest(payload: BacktestCreate, service: Annotated[BacktestService, Depends(get_backtest_service)]) -> BacktestRead:
    return service.create_backtest(payload)
```

Also add `POST /{backtest_id}/cancel` and `DELETE /{backtest_id}`, then mount the router in `backend/app/api/router.py` and add `get_backtest_service()` in `backend/app/api/dependencies.py`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_backtest_routes_support_list_get_cancel_and_delete -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/backtests.py backend/app/api/dependencies.py backend/app/api/router.py backend/tests/test_backtests_api.py
git commit -m "feat: expose backtest REST endpoints"
```

### Task 15: Mark interrupted backtests FAILED during `init_db()`

**Files:**
- Modify: `backend/app/db/session.py`
- Test: `backend/tests/test_backtests_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_init_db_marks_interrupted_backtests_failed(database_url: str) -> None:
    init_db(database_url)
    session_factory = get_session_factory(database_url)

    with session_factory() as session:
        session.add(
            Backtest(
                portfolio_id=1,
                deposit_balance_id=1,
                name="Interrupted",
                status="RUNNING",
                frequency="DAILY",
                start_date=date(2024, 1, 2),
                end_date=date(2024, 1, 31),
                total_cycles=21,
                completed_cycles=7,
                template_id=1,
                llm_base_url="http://localhost:11434/v1",
                llm_api_key="ollama",
                llm_model="qwen2.5:72b",
                price_mode="CLOSING_PRICE",
                commission_mode="ZERO",
                commission_value=Decimal("0"),
                benchmark_symbols=["^GSPC"],
            )
        )
        session.commit()

    init_db(database_url)

    with session_factory() as session:
        backtest = session.scalar(select(Backtest).where(Backtest.name == "Interrupted"))
        assert backtest.status == "FAILED"
        assert "Process interrupted" in backtest.error_message
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_init_db_marks_interrupted_backtests_failed -v`  
Expected: FAIL because `init_db()` currently does not mutate interrupted runs.

- [ ] **Step 3: Write minimal implementation**

```python
def mark_interrupted_backtests_failed(database_url: str | None = None) -> None:
    session = get_session_factory(database_url)()
    try:
        interrupted = list(
            session.scalars(
                select(Backtest).where(Backtest.status.in_(("PENDING", "RUNNING")))
            )
        )
        for backtest in interrupted:
            backtest.status = "FAILED"
            backtest.error_message = (
                "Process interrupted - backtest was running when the server restarted"
            )
        session.commit()
    finally:
        session.close()

def init_db(database_url: str | None = None) -> None:
    __import__("app.models")
    engine = get_engine(database_url)
    validate_supported_database_engine(engine)
    validate_supported_id_schema(engine)
    Base.metadata.create_all(bind=engine)
    upgrade_legacy_schema(engine)
    mark_interrupted_backtests_failed(database_url)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_backtests_api.py::test_init_db_marks_interrupted_backtests_failed -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/session.py backend/tests/test_backtests_api.py
git commit -m "fix: fail interrupted backtests on startup"
```

## Phase 5: Frontend Foundation

Spec anchors: "Routes", "Frontend polling", "Charting library", Fix 2.

### Task 16: Add backtest wire types, API helpers, and barrel exports

**Files:**
- Create: `frontend/src/lib/types/backtest.ts`
- Create: `frontend/src/lib/api/backtests.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/api-types.ts`
- Modify: `frontend/src/lib/api.test.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
it("sends a successful GET request for listBacktests", async () => {
  const { listBacktests } = await loadApiModule();
  fetchMock.mockResolvedValueOnce(jsonResponse([{ id: 1, name: "Daily Backtest", status: "RUNNING" }], 200));

  await expect(listBacktests()).resolves.toHaveLength(1);

  const { url } = getLastFetchCall(fetchMock);
  expect(url).toBe(`${DEFAULT_API_BASE_URL}/backtests`);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && pnpm test:run src/lib/api.test.ts --reporter=verbose`  
Expected: FAIL because `listBacktests` and `backtestsApi` are undefined.

- [ ] **Step 3: Write minimal implementation**

```typescript
export interface BacktestRead {
  id: number;
  portfolioId: number;
  depositBalanceId: number;
  name: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  frequency: "DAILY" | "WEEKLY" | "MONTHLY";
  llmApiKey: "***";
  recentActivity: BacktestRecentActivityEntry[] | null;
  results: BacktestResults | null;
}
```

```typescript
export function listBacktests(signal?: AbortSignal): Promise<BacktestRead[]> {
  return request<BacktestRead[]>("/backtests", { signal });
}
```

Also export the new module from `frontend/src/lib/api.ts` and `frontend/src/lib/api-types.ts`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && pnpm test:run src/lib/api.test.ts --reporter=verbose`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types/backtest.ts frontend/src/lib/api/backtests.ts frontend/src/lib/api.ts frontend/src/lib/api-types.ts frontend/src/lib/api.test.ts
git commit -m "feat: add frontend backtest API contract"
```

### Task 17: Add canonical backtest query keys and polling hooks

**Files:**
- Modify: `frontend/src/lib/query-keys.ts`
- Modify: `frontend/src/lib/query-keys.test.ts`
- Create: `frontend/src/hooks/use-backtests.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
it("normalizes backtest ids to the same detail key", () => {
  expect(queryKeys.backtests.detail("7")).toEqual(queryKeys.backtests.detail(7));
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && pnpm test:run src/lib/query-keys.test.ts --reporter=verbose`  
Expected: FAIL because `queryKeys.backtests` is missing.

- [ ] **Step 3: Write minimal implementation**

```typescript
const backtestsQueryKeys = {
  all: [...apiRoot, "backtests"] as const,
  detail: (backtestId: IdParam) =>
    [...apiRoot, "backtests", "detail", normalizeId(backtestId)] as const,
  list: () => [...apiRoot, "backtests", "list"] as const,
} as const;

export function useBacktest(backtestId: IdParam | undefined) {
  const resolvedId = backtestId ?? "";
  return useQuery({
    queryKey: queryKeys.backtests.detail(resolvedId),
    queryFn: ({ signal }) => getBacktest(resolvedId, signal),
    enabled: Boolean(backtestId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "PENDING" || status === "RUNNING" ? 5000 : false;
    },
  });
}
```

Also add `useBacktests()`, `useCreateBacktest()`, `useCancelBacktest()`, and `useDeleteBacktest()` with standard list/detail invalidation.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && pnpm test:run src/lib/query-keys.test.ts --reporter=verbose`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/query-keys.ts frontend/src/lib/query-keys.test.ts frontend/src/hooks/use-backtests.ts
git commit -m "feat: add backtest query keys and polling hooks"
```

## Phase 6: Frontend Pages

Spec anchors: "Navigation", "Page 1: Backtest List", "Page 2: Backtest Config", "Page 3: Backtest Detail", Fix 2.

### Task 18: Add routes, sidebar navigation, breadcrumbs, and the backtest list page

**Files:**
- Modify: `frontend/src/routes.ts`
- Modify: `frontend/src/components/layout.tsx`
- Create: `frontend/src/pages/backtests/list.tsx`
- Test: `frontend/src/pages/backtests/list.test.tsx`

- [ ] **Step 1: Write the failing route test**

```typescript
it("renders the Backtests navigation entry after Reports", async () => {
  render(<MemoryRouter initialEntries={["/"]}><Layout /></MemoryRouter>);
  const links = screen.getAllByRole("link");
  expect(links.map((link) => link.textContent)).toContain("Backtests");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test:run src/pages/backtests/list.test.tsx --reporter=verbose`  
Expected: FAIL because the route and nav item do not exist.

- [ ] **Step 3: Write minimal implementation**

```tsx
const navItems: NavItem[] = [
  { icon: LayoutDashboard, label: "Dashboard", to: "/" },
  { icon: Briefcase, label: "Portfolios", to: "/portfolios" },
  { icon: FileText, label: "Templates", to: "/templates" },
  { icon: ClipboardList, label: "Reports", to: "/reports" },
  { icon: TrendingUp, label: "Backtests", to: "/backtests" },
];
```

```tsx
{ path: "backtests", Component: BacktestListPage },
{ path: "backtests/new", Component: BacktestConfigPage },
{ path: "backtests/:backtestId", Component: BacktestDetailPage },
```

Build the list page as a card inventory: status badge, date range, progress bar for running items, delete action only for terminal states, and completed-summary teaser using `results.portfolio.totalReturn`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && pnpm test:run src/pages/backtests/list.test.tsx --reporter=verbose`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes.ts frontend/src/components/layout.tsx frontend/src/pages/backtests/list.tsx frontend/src/pages/backtests/list.test.tsx
git commit -m "feat: add backtest navigation and inventory page"
```

### Task 19: Add the backtest config form for existing portfolios and templates

**Files:**
- Modify: `frontend/src/components/shared/form-schemas.ts`
- Create: `frontend/src/pages/backtests/config.tsx`
- Test: `frontend/src/pages/backtests/config.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
it("blocks submit when the validation summary is incomplete", async () => {
  render(<BacktestConfigPage />);
  await userEvent.click(screen.getByRole("button", { name: /launch backtest/i }));
  expect(screen.getByText(/select a template or create a default one/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test:run src/pages/backtests/config.test.tsx --reporter=verbose`  
Expected: FAIL because the page and schema do not exist.

- [ ] **Step 3: Write minimal implementation**

```typescript
export const backtestCreateFormSchema = z.object({
  name: requiredText("Backtest name"),
  portfolioMode: z.enum(["existing", "new"]),
  portfolioId: z.string(),
  createTemplate: z.boolean(),
  templateId: z.string(),
  templateName: z.string(),
  frequency: z.enum(["DAILY", "WEEKLY", "MONTHLY"]),
  startDate: requiredText("Start date"),
  endDate: requiredText("End date"),
  priceMode: z.enum(["CLOSING_PRICE", "LLM_DECIDED"]),
  llmPriceSuccessRate: z.string(),
  commissionMode: z.enum(["ZERO", "FIXED", "PERCENTAGE"]),
  commissionValue: z.string(),
  llmBaseUrl: requiredText("LLM base URL"),
  llmApiKey: requiredText("LLM API key"),
  llmModel: requiredText("LLM model"),
  benchmarkSymbols: z.array(z.string()).min(1, "Select at least one benchmark"),
});
```

In `config.tsx`, use existing hooks for portfolios/templates to populate dropdowns, show the validation summary, and submit directly to `useCreateBacktest()` when `portfolioMode === "existing"`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && pnpm test:run src/pages/backtests/config.test.tsx --reporter=verbose`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/form-schemas.ts frontend/src/pages/backtests/config.tsx frontend/src/pages/backtests/config.test.tsx
git commit -m "feat: add backtest configuration form"
```

### Task 20: Orchestrate the inline "create new portfolio" flow before `POST /backtests`

**Files:**
- Modify: `frontend/src/pages/backtests/config.tsx`
- Test: `frontend/src/pages/backtests/config.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
it("creates a portfolio and deposit balance before launching a backtest", async () => {
  createPortfolioMock.mockResolvedValue({
    id: 12,
    name: "Sandbox",
    slug: "sandbox",
    description: null,
    baseCurrency: "USD",
    positionCount: 0,
    balanceCount: 0,
    createdAt: "2026-03-20T10:00:00Z",
    updatedAt: "2026-03-20T10:00:00Z",
  });
  createBalanceMock.mockResolvedValue({
    id: 55,
    portfolioId: 12,
    label: "Initial Cash",
    amount: "25000.00",
    currency: "USD",
    operationType: "DEPOSIT",
    hasTradingOperations: false,
    createdAt: "2026-03-20T10:01:00Z",
    updatedAt: "2026-03-20T10:01:00Z",
  });

  render(<BacktestConfigPage />);
  await userEvent.click(screen.getByLabelText(/create new/i));
  await userEvent.type(screen.getByLabelText(/^name$/i), "Sandbox");
  await userEvent.type(screen.getByLabelText(/^slug$/i), "sandbox");
  await userEvent.type(screen.getByLabelText(/initial cash/i), "25000");
  await userEvent.click(screen.getByRole("button", { name: /launch backtest/i }));

  expect(createPortfolioMock).toHaveBeenCalled();
  expect(createBalanceMock).toHaveBeenCalledWith(12, expect.objectContaining({
    label: "Initial Cash",
    operationType: "DEPOSIT",
  }));
  expect(createBacktestMock).toHaveBeenCalledWith(expect.objectContaining({ portfolioId: 12 }));
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test:run src/pages/backtests/config.test.tsx --reporter=verbose`  
Expected: FAIL because the inline new-portfolio flow is not wired.

- [ ] **Step 3: Write minimal implementation**

```tsx
if (values.portfolioMode === "new") {
  const portfolio = await createPortfolioMutation.mutateAsync({
    name: values.newPortfolioName,
    slug: values.newPortfolioSlug,
    description: null,
    baseCurrency: values.newPortfolioCurrency,
  });
  await createBalanceMutation.mutateAsync({
    portfolioId: portfolio.id,
    data: {
      label: "Initial Cash",
      amount: values.newPortfolioInitialCash,
      operationType: "DEPOSIT",
    },
  });
  portfolioId = portfolio.id;
}
await createBacktestMutation.mutateAsync({ ...payload, portfolioId });
```

Do not add portfolio fields to the backtest API request; keep Fix 2 exactly as designed.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && pnpm test:run src/pages/backtests/config.test.tsx --reporter=verbose`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/backtests/config.tsx frontend/src/pages/backtests/config.test.tsx
git commit -m "feat: support inline portfolio creation for backtests"
```

### Task 21: Build the running-state detail page with polling, cancel, and activity feed

**Files:**
- Create: `frontend/src/pages/backtests/detail.tsx`
- Create: `frontend/src/components/backtests/backtest-status-badge.tsx`
- Modify: `frontend/src/hooks/use-backtests.ts`
- Test: `frontend/src/pages/backtests/detail.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
it("polls while a backtest is running and shows recent activity", async () => {
  render(<BacktestDetailPage />);
  expect(await screen.findByText(/current simulation date/i)).toBeInTheDocument();
  expect(screen.getByText(/AAPL/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /cancel/i })).toBeEnabled();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test:run src/pages/backtests/detail.test.tsx --reporter=verbose`  
Expected: FAIL because the detail page and running-state UI are missing.

- [ ] **Step 3: Write minimal implementation**

```tsx
if (backtest.status === "RUNNING" || backtest.status === "PENDING") {
  return (
    <div className="space-y-4 p-4">
      <BacktestStatusBadge status={backtest.status} />
      <Progress value={(backtest.completedCycles / backtest.totalCycles) * 100} />
      <Button onClick={() => cancelMutation.mutate(backtest.id)}>Cancel</Button>
      <Card>
        <CardContent>
          {(backtest.recentActivity ?? []).map((entry) => (
            <div key={entry.cycleDate}>{entry.cycleDate}</div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
```

Also show elapsed time from `createdAt`, current cycle date, and the last 5-10 recent activity decisions.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && pnpm test:run src/pages/backtests/detail.test.tsx --reporter=verbose`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/backtests/detail.tsx frontend/src/components/backtests/backtest-status-badge.tsx frontend/src/pages/backtests/detail.test.tsx
git commit -m "feat: add running backtest detail view"
```

## Phase 7: Frontend Charts

Spec anchors: "Summary metrics", "Equity Curve chart", "Drawdown chart", "Trade Log table".

### Task 22: Add reusable results components for metrics and trade log

**Files:**
- Create: `frontend/src/components/backtests/metrics-summary.tsx`
- Create: `frontend/src/components/backtests/trade-log-table.tsx`
- Modify: `frontend/src/pages/backtests/detail.tsx`
- Test: `frontend/src/pages/backtests/detail.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
it("renders completed backtest summary metrics and trade rows", async () => {
  render(<BacktestDetailPage />);
  expect(await screen.findByText(/total return/i)).toBeInTheDocument();
  expect(screen.getByText(/max drawdown/i)).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: /symbol/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test:run src/pages/backtests/detail.test.tsx --reporter=verbose`  
Expected: FAIL because the completed dashboard components do not exist.

- [ ] **Step 3: Write minimal implementation**

```tsx
export function MetricsSummary({ portfolio }: { portfolio: BacktestPortfolioResults }) {
  return (
    <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
      <MetricCard label="Total Return" value={formatPercent(portfolio.totalReturn)} />
      <MetricCard label="Max Drawdown" value={formatPercent(portfolio.maxDrawdown)} />
      <MetricCard label="Sharpe Ratio" value={formatDecimal(portfolio.sharpeRatio ?? "0", 2)} />
      <MetricCard label="Total Trades" value={String(portfolio.totalTrades)} />
      <MetricCard label="Win Rate" value={formatPercent(portfolio.winRate)} />
      <MetricCard label="Total Commission" value={formatCurrency(portfolio.totalCommission)} />
    </div>
  );
}
```

```tsx
export function TradeLogTable({ trades }: { trades: BacktestTradeLogEntry[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Symbol</TableHead>
          <TableHead>Action</TableHead>
          <TableHead>Qty</TableHead>
          <TableHead>Price</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {trades.map((trade) => (
          <TableRow key={`${trade.cycleDate}-${trade.symbol}`}>
            <TableCell>{trade.cycleDate}</TableCell>
            <TableCell>{trade.symbol}</TableCell>
            <TableCell>{trade.side}</TableCell>
            <TableCell>{trade.quantity ?? "-"}</TableCell>
            <TableCell>{trade.executedPrice ?? trade.requestedPrice}</TableCell>
            <TableCell>{trade.executed ? "Executed" : trade.failureReason ?? "Failed"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && pnpm test:run src/pages/backtests/detail.test.tsx --reporter=verbose`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/backtests/metrics-summary.tsx frontend/src/components/backtests/trade-log-table.tsx frontend/src/pages/backtests/detail.tsx frontend/src/pages/backtests/detail.test.tsx
git commit -m "feat: add backtest metrics and trade log components"
```

### Task 23: Add equity/drawdown charts and benchmark toggles

**Files:**
- Create: `frontend/src/components/backtests/equity-curve-chart.tsx`
- Create: `frontend/src/components/backtests/drawdown-chart.tsx`
- Create: `frontend/src/components/backtests/equity-curve-chart.test.tsx`
- Modify: `frontend/src/pages/backtests/detail.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
it("toggles benchmark lines without hiding the portfolio curve", async () => {
  render(
    <EquityCurveChart
      curve={[{ date: "2024-01-02", value: "100000.00" }]}
      benchmarkCurves={{ "^GSPC": [{ date: "2024-01-02", value: "1.0000" }] }}
      selectedBenchmarks={["^GSPC"]}
    />
  );

  expect(screen.getByLabelText(/portfolio/i)).toBeChecked();
  expect(screen.getByLabelText(/\^GSPC/i)).toBeChecked();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test:run src/components/backtests/equity-curve-chart.test.tsx --reporter=verbose`  
Expected: FAIL because the chart components do not exist.

- [ ] **Step 3: Write minimal implementation**

```tsx
export function EquityCurveChart(props: EquityCurveChartProps) {
  const [visibleSeries, setVisibleSeries] = useState<Record<string, boolean>>({
    portfolio: true,
    ...Object.fromEntries(props.selectedBenchmarks.map((symbol) => [symbol, true])),
  });

  return (
    <>
      <ChartContainer
        config={{
          portfolio: { label: "Portfolio", color: "#0f766e" },
          "^GSPC": { label: "S&P 500", color: "#2563eb" },
          "^IXIC": { label: "NASDAQ", color: "#7c3aed" },
          "^DJI": { label: "Dow Jones", color: "#ea580c" },
        }}
      >
        <LineChart data={mergedSeries}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="date" />
          <YAxis />
          <ChartTooltip content={<ChartTooltipContent />} />
          {visibleSeries.portfolio ? <Line dataKey="portfolio" stroke="var(--color-portfolio)" /> : null}
          {props.selectedBenchmarks.map((symbol) =>
            visibleSeries[symbol] ? <Line key={symbol} dataKey={symbol} stroke={`var(--color-${symbol})`} /> : null
          )}
        </LineChart>
      </ChartContainer>
      <div className="flex flex-wrap gap-3">
        <Checkbox checked={visibleSeries.portfolio} aria-label="Portfolio" />
        {props.selectedBenchmarks.map((symbol) => (
          <Checkbox key={symbol} checked={visibleSeries[symbol]} aria-label={symbol} />
        ))}
      </div>
    </>
  );
}
```

Use `AreaChart` in `DrawdownChart` with a red fill below zero, leveraging `frontend/src/components/ui/chart.tsx`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && pnpm test:run src/components/backtests/equity-curve-chart.test.tsx --reporter=verbose`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/backtests/equity-curve-chart.tsx frontend/src/components/backtests/drawdown-chart.tsx frontend/src/components/backtests/equity-curve-chart.test.tsx frontend/src/pages/backtests/detail.tsx
git commit -m "feat: visualize backtest equity and drawdown curves"
```

## Phase 8: Integration Testing

Spec anchors: backend lifecycle coverage, frontend poll/results flow, crash recovery, delete cleanup.

### Task 24: Expand backend regression coverage across the full backtest lifecycle

**Files:**
- Modify: `backend/tests/test_backtests_api.py`
- Modify: `backend/tests/test_backtest_engine.py`

- [ ] **Step 1: Write the failing integration tests**

```python
def test_backtest_create_get_cancel_delete_flow(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    create_balance(client, str(portfolio["id"]), amount="10000.00")
    template = create_template(client, name="Lifecycle Template", content="# Lifecycle")
    create_response = client.post(
        "/api/v1/backtests",
        json={
            "name": "Lifecycle Backtest",
            "portfolioId": portfolio["id"],
            "templateId": template["id"],
            "createTemplate": False,
            "frequency": "DAILY",
            "startDate": "2024-01-02",
            "endDate": "2024-03-29",
            "llmBaseUrl": "http://localhost:11434/v1",
            "llmApiKey": "ollama",
            "llmModel": "qwen2.5:72b",
            "priceMode": "CLOSING_PRICE",
            "commissionMode": "ZERO",
            "commissionValue": "0",
            "benchmarkSymbols": ["^GSPC"],
        },
    )
    backtest_id = create_response.json()["id"]
    assert client.get("/api/v1/backtests").status_code == 200
    assert client.post(f"/api/v1/backtests/{backtest_id}/cancel").json()["status"] == "CANCELLED"
    assert client.delete(f"/api/v1/backtests/{backtest_id}").status_code == 204

def test_backtest_engine_marks_failed_on_llm_connection_error(session_factory: sessionmaker[Session]) -> None:
    engine = build_engine(backtest_id=42, portfolio_id=7, deposit_balance_id=3, llm_error=RuntimeError("Connection refused"))
    refreshed = engine.run_once_for_test()
    assert refreshed.status == "FAILED"
    assert "connection" in refreshed.error_message.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_backtests_api.py tests/test_backtest_engine.py -v`  
Expected: FAIL until any missing cleanup, failure, or crash-recovery paths are implemented.

- [ ] **Step 3: Finish the missing production gaps**

```python
except Exception as exc:
    backtest.status = "FAILED"
    backtest.error_message = str(exc)
    session.commit()
    raise
```

Add the last missing service/engine edge cases required by these tests: LLM failure handling, parse failure skip/continue, failed trade logging, and delete cleanup.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_backtests_api.py tests/test_backtest_engine.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_backtests_api.py backend/tests/test_backtest_engine.py backend/app/services/backtest_service.py backend/app/services/backtest_engine.py
git commit -m "test: cover the backtest lifecycle end to end"
```

### Task 25: Add frontend E2E coverage and run the final verification sweep

**Files:**
- Create: `frontend/e2e/backtests.spec.ts`
- Modify: `frontend/src/pages/backtests/detail.test.tsx`

- [ ] **Step 1: Write the failing E2E scenario**

```typescript
test("create a backtest, poll until terminal state, and view results", async ({ page, request }) => {
  await page.goto("/backtests");
  await page.getByRole("link", { name: /backtests/i }).click();
  await page.getByRole("button", { name: /new backtest/i }).click();
  await page.getByLabel("Backtest name").fill("E2E Backtest");
  await page.getByLabel(/use existing/i).click();
  await page.getByRole("combobox", { name: /portfolio/i }).click();
  await page.getByRole("option", { name: /core portfolio/i }).click();
  await page.getByRole("combobox", { name: /template/i }).click();
  await page.getByRole("option", { name: /backtest template/i }).click();
  await page.getByRole("button", { name: /launch backtest/i }).click();
  await page.waitForURL(/\/backtests\/\d+$/);
  await expect(page.getByText(/current simulation date|total return/i)).toBeVisible();
  await page.getByRole("button", { name: /delete/i }).click();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test:e2e --grep Backtests`  
Expected: FAIL because the route, orchestration, or dashboard is incomplete.

- [ ] **Step 3: Finish the missing UI gaps and verification glue**

```tsx
toast.success(`Backtest "${created.name}" launched`);
navigate(`/backtests/${created.id}`);
```

Add the last missing page behavior needed for the E2E path: success toasts, redirect after create, completed-state rendering, delete action, and report links.

- [ ] **Step 4: Run the full validation suite**

Run:
- `cd backend && uv run pytest tests/test_backtests_api.py tests/test_backtest_engine.py -v`
- `cd frontend && pnpm lint`
- `cd frontend && pnpm typecheck`
- `cd frontend && pnpm test:run`
- `cd frontend && pnpm build`
- `cd frontend && pnpm test:e2e --grep Backtests`

Expected: all PASS with no lint/type errors.

- [ ] **Step 5: Run diagnostics and commit**

Tool checks:
- `lsp_diagnostics` on `backend/app/services/backtest_service.py`
- `lsp_diagnostics` on `backend/app/services/backtest_engine.py`
- `lsp_diagnostics` on `frontend/src/pages/backtests/detail.tsx`
- `lsp_diagnostics` on `frontend/src/components/backtests/equity-curve-chart.tsx`

Expected: no errors on changed files.

```bash
git add frontend/e2e/backtests.spec.ts frontend/src/pages/backtests/detail.test.tsx frontend/src/pages/backtests/* frontend/src/components/backtests/*
git commit -m "feat: deliver the backtest dashboard workflow"
```

## Final Verification Checklist

- [ ] `backend/pyproject.toml` includes `openai`, `yfinance`, `pyarrow`, and `exchange-calendars`.
- [ ] `frontend/package.json` still contains `recharts` and `date-fns`; no accidental dependency regressions.
- [ ] `POST /api/v1/backtests` only accepts a `portfolioId` for portfolio selection; new portfolio creation stays in frontend orchestration.
- [ ] `GET /api/v1/backtests/{id}` redacts `llmApiKey` to `***`.
- [ ] Backtest trades persist `backtest_id` and are cascade-deleted with the backtest.
- [ ] Reports created by the engine carry `tags: ["backtest", "backtest_<id>"]` and `analysis.backtestId` / `analysis.cycleDate`.
- [ ] `recentActivity` never grows beyond the last 10 cycle entries.
- [ ] `init_db()` marks interrupted `PENDING`/`RUNNING` backtests as `FAILED`.
- [ ] Backend targeted tests pass.
- [ ] Frontend lint, typecheck, unit tests, build, and Playwright backtest flow pass.
- [ ] LSP diagnostics are clean on every changed backend/frontend file.
