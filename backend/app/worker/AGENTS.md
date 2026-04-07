# BACKEND WORKER GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers `app/worker/`.

## OVERVIEW
`app/worker/` hosts the separate FastAPI worker used by live webhook backtests. It accepts dispatch payloads from Ledger, returns an immediate accepted response, downloads prompt reports, runs TradingAgents analysis through an adapter, uploads an analysis report, and posts trade plus completion callbacks back into the main backend.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Worker entrypoint | `main.py` | FastAPI app, `/health`, `/api/v1/trading-agents/dispatch`, dependency wiring |
| Async dispatch flow | `service.py` | background thread kickoff, prompt-report download, analysis report upload, trade + complete callbacks |
| TradingAgents integration | `trading_agents_adapter.py` | protocol, live adapter, lazy graph construction, env overrides, decision coercion |
| Worker payloads | `schemas.py` | dispatch request plus accepted/completed response DTOs |
| Backend callback contract | `../api/backtest_callbacks.py`, `../schemas/backtest_callback.py` | worker posts `/report`, `/trades`, and `/complete` callbacks here |
| Regression coverage | `../../tests/test_trading_agents_worker.py`, `../../tests/test_trading_agents_worker_integration.py` | unit coverage plus end-to-end callback/report flow |

## CONVENTIONS
- `main.py` defines a separate FastAPI app and process; the worker does not share the main backend's request-scoped DB session.
- `dispatch_async()` returns `202 Accepted` immediately, starts `_run_dispatch()` on a daemon thread, and that helper calls `handle_dispatch()`.
- `BacktestWebhookWorkerService` downloads the prompt report from `reportDownloadUrl`, extracts held positions from the markdown payload, renders an analysis report, uploads it to `{callbackBaseUrl}/report`, then posts trades to `/trades` and completion to `/complete`.
- BUY / OVERWEIGHT decisions become a fixed quantity `1`, SELL / UNDERWEIGHT decisions sell the full held quantity only when it is integral, and unsupported fractional sells degrade to HOLD with an explanatory note.
- `LiveTradingAgentsAdapter` lazily imports the TradingAgents graph and honors `TRADINGAGENTS_LLM_PROVIDER`, `TRADINGAGENTS_BACKEND_URL`, `TRADINGAGENTS_QUICK_THINK_LLM`, and `TRADINGAGENTS_DEEP_THINK_LLM` overrides.
- Worker payloads use `CamelModel` DTOs from `schemas.py`; keep the callback-facing contract aligned with backend callback routes and tests.

## ANTI-PATTERNS
- Do not move worker orchestration into `app/services/`; this folder owns the separate process boundary.
- Do not block the dispatch route on full analysis work; the accepted response is intentionally asynchronous.
- Do not change report-upload or callback payload shapes without updating backend callback routes, worker schemas, and worker tests together.
- Do not assume fractional SELL handling is supported in phase 1.
- Do not hardcode TradingAgents configuration outside `trading_agents_adapter.py`.

## VALIDATION
```bash
cd backend
uv run pytest tests/test_trading_agents_worker.py tests/test_trading_agents_worker_integration.py
```

## NOTES
- `main.py` exposes `/health` and `/api/v1/trading-agents/dispatch` and is also wired as the `ledger-backend-worker` script entry in `backend/pyproject.toml`.
- `service.py` tags uploaded analysis reports with `tradingagents` and `phase1` and logs failures inside the background thread instead of surfacing them synchronously at the dispatch route.
- `trading_agents_adapter.py` raises a runtime error when the TradingAgents package is unavailable; keep that failure mode explicit instead of silently skipping analysis.
