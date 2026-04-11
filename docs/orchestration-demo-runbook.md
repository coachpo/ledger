# Ledger Orchestration Demo Runbook

## Purpose

This runbook documents how to reset Ledger to a clean local state, start it from `./start.sh`, and demonstrate the full orchestration workflow by interacting only through the UI after the initial root load.

## Scope

The demonstrated workflow covers:

- clean reset of application data
- backend startup with an OpenAI-compatible LLM configuration
- creation of orchestration roles and characters
- creation of a demo portfolio and funding balance
- creation of an orchestration-aware template using mention assistance
- launch of an orchestration backtest
- inspection of a completed backtest result
- inspection of a generated report from the completed backtest

## Preconditions

- Colima or another Docker-compatible daemon is running and reachable by the `docker` CLI
- `uv`, `pnpm`, and `docker compose` are available
- the repo root is the working directory

## LLM Configuration

Ledger reads its internal backtest model settings from backend environment variables.

Set these before starting the app:

```bash
export BACKTEST_AGENT_MODEL="gpt-5.4-mini"
export BACKTEST_AGENT_BASE_URL="http://192.168.1.222:8087/v1"
export BACKTEST_AGENT_API_KEY="<your-api-key>"
```

Do **not** save real API keys in committed files.

## Clean Reset

From the repo root:

```bash
cd backend
docker compose down -v
cd ..
```

This removes the local PostgreSQL volume used by Ledger and returns the backend collections to an empty state.

## Startup

From the repo root:

```bash
./start.sh
```

Expected ready state:

- frontend at `http://127.0.0.1:25173`
- backend health endpoint returns `{"status":"ok"}` at `http://127.0.0.1:28000/health`

## Runtime LLM Proof

The running backend process should include the provided model settings in its process environment.

One concrete verification command is:

```bash
pid=$(lsof -tiTCP:28000 -sTCP:LISTEN | head -n 1)
ps eww -p "$pid"
```

Expected output includes:

- `BACKTEST_AGENT_MODEL=gpt-5.4-mini`
- `BACKTEST_AGENT_BASE_URL=http://192.168.1.222:8087/v1`
- `BACKTEST_AGENT_API_KEY=...`

Code seam proving the runtime uses those variables:

- `backend/app/core/config.py`
- `backend/app/services/backtest_cycle_service.py`
- `backend/app/langgraph/runner.py`

## Demonstration Flow

Only the initial root load uses a URL. After that, navigate by clicks and form input only.

### 1. Load the root shell

Open `http://127.0.0.1:25173/`.

Expected clean state:

- dashboard counts are zero
- no portfolios
- no templates
- no backtests
- no roles or characters

### 2. Create a role

Click:

- `Orchestration`
- `Manage Roles`
- `Create Role`

Fill:

- Key: `macro_research_role`
- Name: `Macro Research`
- Description: `Investigates macro drivers and external context for orchestration runs.`
- System Prompt: `Research macro drivers, market regime changes, and benchmark context before the cycle decision is made.`

Save the role.

Expected result:

- success toast
- route changes to `/orchestration/roles/<id>/edit`

### 3. Create a character

Click:

- `Orchestration`
- `Manage Characters`
- `Create Character`

Fill:

- Handle: `market_researcher`
- Name: `Market Researcher`
- Role: `Macro Research`
- Description: `Summarizes the macro regime for the final orchestration prompt.`
- Prompt Append: `Focus on macro drivers, benchmark regime shifts, and the most important risk signal.`

Save the character.

Expected result:

- success toast
- route changes to `/orchestration/characters/<id>/edit`

### 4. Create and fund a portfolio

Click:

- `Portfolios`
- `New Portfolio`

Fill:

- Name: `Demo Portfolio`
- Slug: `demo_portfolio`
- Description: `Fresh demo portfolio for the orchestration workflow walkthrough.`
- Base Currency: `USD`

Save the portfolio.

Expected result:

- route changes to `/portfolios/<id>`

Then click:

- `Balances`
- `Add Balance`

Fill:

- Operation Type: `DEPOSIT`
- Label: `Initial Cash`
- Amount: `25000`

Save the balance.

Expected result:

- balance list shows `Initial Cash`
- portfolio total value and cash balances update from zero

### 5. Add a position for a nontrivial backtest

On the same portfolio detail page, stay on `Positions` and click `Add Position`.

Fill:

- Symbol: `AAPL`
- Name: `Apple` (the UI may auto-fill this to `Apple Inc.`)
- Quantity: `10`
- Average Cost: `180`

Save the position.

Expected result:

- positions table shows `AAPL`
- total value and unrealized P&L are no longer zero

### 6. Create an orchestration-aware template

Click:

- `Templates`
- `New Template`

Fill:

- Template name: `Demo Orchestration Template`

Open `Mention Assistance` and click:

- `@librarian`
- `@market_researcher`

Open the `Demo Portfolio 1` placeholder section and click:

- `portfolios.demo_portfolio`

Then continue typing in the editor body:

```markdown

# Demo orchestration brief

Use the portfolio context above to explain the current setup. Ask @librarian for relevant context and then ask @market_researcher to summarize the macro picture before producing the final recommendation.
```

Save the template.

Expected result:

- route changes to `/templates/<id>/edit`
- preview shows the portfolio placeholder expanded
- mention text remains literal (`@librarian`, `@market_researcher`)

### 7. Launch the orchestration backtest

Click:

- `Backtests`
- `New Backtest`

Fill/select:

- Backtest Name: `Demo Orchestration Backtest With Position`
- Launch Mode: `Internal` (default)
- Orchestration Pattern: `Analyst Reviewer v1`
- Portfolio: `Demo Portfolio`
- Template: `Demo Orchestration Template`
- Frequency: `Monthly`
- Start Date: `2024-01-02`
- End Date: `2024-03-29`
- Benchmark: `S&P 500`

Then click `Launch Backtest`.

Expected result:

- route changes to `/backtests/<id>`
- status eventually becomes `COMPLETED`

### 8. Verify the completed result

On the backtest detail page, verify:

- status badge shows `COMPLETED`
- metrics summary is visible
- `LangGraph Decision Summary` is visible
- latest cycle decisions are present for the populated portfolio run

### 9. Open the generated report

Click:

- `Reports`
- open the report card `backtest_2_20240328`

Expected result:

- route changes to `/reports/backtest_2_20240328`
- report detail shows `LangGraph Analysis`
- report body includes the run topology and the `AAPL` analysis summary

## Demo Evidence Summary

This runbook was validated against a real local demo with the following successful outcomes:

- one role created
- one character created
- one funded portfolio created
- one orchestration-aware template created
- one populated orchestration backtest completed successfully
- one generated report opened successfully from the Reports surface
- running backend process confirmed to include the provided `BACKTEST_AGENT_*` environment variables

## Issues Encountered During Demo

### Environment / startup

1. `start.sh` can partially succeed when Docker is unreachable: the frontend may start even while the database path fails.
2. Colima/Docker context mismatches can make `docker compose` fail until the local Docker context is corrected.

### UI / product

3. The role create route initially got stuck on `Loading role details...` until the create-mode loading logic was corrected.
4. The character create route shared the same create-mode loading problem and needed the same fix.
5. After creating a balance, the balance dialog showed success but did not always disappear immediately; closing or waiting for rerender resolved it.
6. Position symbol lookup can auto-fill the company name mid-entry, which makes browser automation sensitive to input ordering.

### Browser automation / rerun caveats

7. Long-lived dev servers can become stale; for reliable reruns, restart the stack cleanly rather than trusting an old Vite process.
8. Browser-native date controls and benchmark checkboxes were more reliable with Playwright than with Chrome DevTools in this repo.
9. Playwright reruns should avoid stale `4173`/`8001` server reuse; clean server startup produced stable orchestration and backtest E2E results.
10. The benchmark checkbox accepted Playwright's checkbox-specific interaction (`setChecked`) more reliably than generic click paths.

## Rerun Recommendation

For future reruns, prefer:

1. clean reset with `docker compose down -v`
2. fresh `./start.sh`
3. Playwright for the full click/input walkthrough once the root page is loaded

This combination produced the most stable end-to-end results in practice.
