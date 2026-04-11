# BACKEND LANGGRAPH GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`.

## OVERVIEW
`app/langgraph/` owns Ledger's internal backtest-analysis orchestration. It replaces the old TradingAgents worker transport with an in-process LangGraph runner that takes a stored prompt report, analyzes held positions, renders an analysis report, and returns normalized `TradeDecision[]` values to the backtest cycle service. `seeds.py` now defines the seeded builtin handles, policies, and topology surfaces used by the runner.

## CONVENTIONS
- Keep LangGraph state minimal and execution-focused; Ledger services and models remain the system of record.
- Let `BacktestCycleService` own lifecycle, progress, and persistence. LangGraph should return results, not commit domain state directly.
- Read runtime configuration through `app.core.config.Settings`, not raw env vars.
- Use fakeable analyzer boundaries in tests; do not hit live model providers from unit tests.
- Application LLM calls in this directory must use official provider libraries, not raw HTTP. The current live path uses `ChatOpenAI` for compatibility-first parsing and the official `OpenAI` Python client for streamed Responses-mode calls.
- `BACKTEST_AGENT_API_MODE` selects the provider transport; `responses` mode currently streams `responses.create(..., stream=True)` with explicit `type:"message"` input items and `reasoning.effort="none"`.
- Supported topologies include `seeded_internal_backtest_v1` for the seeded internal path and `analyst_reviewer_v1` for the conservative review path, with the seeded builtin handles and policies living in `seeds.py`.

## ANTI-PATTERNS
- Do not move portfolio, trade, or report persistence into LangGraph nodes.
- Do not make LangGraph state the source of truth for backtest progress.
- Do not hardcode provider credentials or model endpoints in graph code.
- Do not replace official SDK calls with raw `httpx`/`requests` model requests in production code.
