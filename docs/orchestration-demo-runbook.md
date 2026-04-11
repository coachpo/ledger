# Ledger Orchestration Demo Runbook

## Purpose

This runbook captures the current local demo flow for Ledger orchestration. It begins by resetting the container-managed database, uses `./start.sh` as the canonical launcher, and then stays inside the UI after the first root load.

## What this demo covers

- orchestration role and character CRUD
- portfolio creation with an initial deposit balance
- template creation with mention assistance and literal handles
- internal backtest launch with orchestration pattern selection
- backtest result review
- generated report review from the Reports surface

## Preconditions

- Docker and `docker compose` are available
- `uv` and `pnpm` are installed
- the repository root is the working directory

## Runtime provider config

Ledger uses runtime provider settings for live LangGraph-backed backtests. For live model-backed backtests, make sure a model ID is available, and provide an API key and base URL when your provider requires them:

```bash
export BACKTEST_AGENT_MODEL="<model-id>"
export BACKTEST_AGENT_BASE_URL="<openai-compatible-base-url>"
export BACKTEST_AGENT_API_KEY="<your-api-key>"
```

These are runtime settings, not checked-in secrets.

## Runtime provider proof

You can also verify that the running backend inherited your current runtime provider settings.

One concrete local check is to inspect the environment of the backend process currently listening on the selected backend port.

```bash
pid=$(lsof -tiTCP:<backend-port> -sTCP:LISTEN | head -n 1)
ps eww -p "$pid"
```

Expected output includes your current values for:

- `BACKTEST_AGENT_MODEL=...`
- `BACKTEST_AGENT_BASE_URL=...`
- `BACKTEST_AGENT_API_KEY=...`

The current code seam for that runtime config is:

- `backend/app/core/config.py`
- `backend/app/services/backtest_cycle_service.py`
- `backend/app/langgraph/runner.py`

## Clean reset

From the repo root, reset the container-managed database with:

```bash
cd backend
docker compose down -v
```

This removes the local PostgreSQL volume for the container-managed database.

Important caveat: `./start.sh` can reuse an already reachable PostgreSQL endpoint on port `25432` instead of starting the container-managed database. If you need a guaranteed clean demo state, make sure the database `./start.sh` will actually use is the one you reset.

Also make sure `./start.sh` is not reusing an already healthy Ledger backend on the selected backend port unless that reused backend is pointed at the reset database.

## Start the stack

From the repo root:

```bash
./start.sh
```

`start.sh` is the canonical local launcher. It reuses a healthy backend when one is already listening, falls back to alternate ports when the requested ones are occupied, and wires the frontend to the selected backend base URL.

Expected local endpoints are usually:

- frontend, `http://127.0.0.1:25173`
- backend health, `http://127.0.0.1:28000/health`

## Demo flow

Only the initial root load uses a URL. After that, use clicks and form input only.

### 1. Open the app shell

Open the frontend URL printed by `./start.sh`.

Expected starting state:

- assuming the app is using the reset database, dashboard counts are zero or empty
- there are no portfolios, templates, backtests, roles, or characters yet

### 2. Create an orchestration role

Click `Orchestration`, then `Manage Roles`, then `Create Role`.

Fill:

- Key: `macro_research_role`
- Name: `Macro Research`
- Description: `Investigates macro drivers and external context for orchestration runs.`
- System Prompt: `Research macro drivers, market regime changes, and benchmark context before the cycle decision is made.`

Save the role.

Expected result:

- success toast
- the route changes to `/orchestration/roles/<id>/edit`

### 3. Create an orchestration character

Click `Orchestration`, then `Manage Characters`, then `Create Character`.

Fill:

- Handle: `market_researcher`
- Name: `Market Researcher`
- Role: `Macro Research`
- Description: `Summarizes the macro regime for the final orchestration prompt.`
- Prompt Append: `Focus on macro drivers, benchmark regime shifts, and the most important risk signal.`

Save the character.

Expected result:

- success toast
- the route changes to `/orchestration/characters/<id>/edit`

### 4. Create and fund a portfolio

Click `Portfolios`, then `New Portfolio`.

Fill:

- Name: `Demo Portfolio`
- Slug: `demo_portfolio`
- Description: `Fresh demo portfolio for the orchestration workflow walkthrough.`
- Base Currency: `USD`

Save the portfolio.

Then click `Balances`, then `Add Balance`.

Fill:

- Operation Type: `DEPOSIT`
- Label: `Initial Cash`
- Amount: `25000`

Save the balance.

Expected result:

- the balance list shows `Initial Cash`
- portfolio cash and total value move off zero

### 5. Add a position

Stay on the portfolio detail page, open `Positions`, then `Add Position`.

Fill:

- Symbol: `AAPL`
- Name: `Apple` or the UI autofill result
- Quantity: `10`
- Average Cost: `180`

Save the position.

Expected result:

- `AAPL` appears in the positions table
- the portfolio now has nonzero exposure for backtest review

### 6. Create an orchestration-aware template

Click `Templates`, then `New Template`.

Fill the template name:

- `Demo Orchestration Template`

Use mention assistance to insert the literal handles:

- `@librarian`
- `@market_researcher`

Use the portfolio placeholder browser to insert:

- `portfolios.demo_portfolio`

Then type this body in the editor:

```markdown

# Demo orchestration brief

Use the portfolio context above to explain the current setup. Ask @librarian for relevant context and then ask @market_researcher to summarize the macro picture before producing the final recommendation.
```

Save the template.

Expected result:

- the route changes to `/templates/<id>/edit`
- preview expands the portfolio placeholder
- the mention text stays literal in the editor body

### 7. Launch the backtest

Click `Backtests`, then `New Backtest`.

Fill or select:

- Backtest Name: `Demo Orchestration Backtest With Position`
- Launch Mode: `Internal`
- Orchestration Pattern: `Analyst Reviewer v1`
- Portfolio: `Demo Portfolio`
- Template: `Demo Orchestration Template`
- Frequency: `Monthly`
- Start Date: `2024-01-02`
- End Date: `2024-03-29`
- Benchmark: `S&P 500`

Launch the backtest.

Expected result:

- the route changes to `/backtests/<id>`
- status eventually becomes `COMPLETED`

### 8. Review the completed result

On the backtest detail page, verify:

- the status badge shows `COMPLETED`
- the metrics summary is visible
- `LangGraph Decision Summary` is visible
- latest cycle decisions are visible when the final cycle still has generated decisions

### 9. Open the generated report

Use either of these current paths:

- if the backtest detail page shows an `Analysis Reports` section, click one of the generated report links there
- or click `Reports` and open the new `backtest_<id>_<date>` report created by the completed run

The `Analysis Reports` section is conditional. It only appears when the completed backtest trade log contains report-linked trade entries.

Expected result:

- the route changes to `/reports/<generated-backtest-report-slug>`
- the report detail shows `LangGraph Analysis`
- the report body includes the run topology and cycle analysis content for the positions held in that report's cycle

## Validation notes

This runbook is grounded in the current live app plus the shipped route, API, and E2E coverage around orchestration navigation, backtest orchestration behavior, and report flows.

## Known rerun caveats

- `start.sh` may reuse an already healthy backend or fall back to alternate ports when the requested ports are occupied.
- stale Playwright servers can hide app changes, so clean restarts are more reliable for reruns.
- use Playwright checkbox-specific actions for benchmark selection during browser automation reruns.
- the README and backend docs still mention `PUBLIC_BASE_URL` in a few places, but the current internal backtest path does not require it.
