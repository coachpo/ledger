# Ledger Backtest AI Workflow Runbook

> Status: Success-path runbook for the current Ledger + n8n native AI Agent flow. Verified locally against a freshly reset `start.sh` stack, the live n8n instance on `192.168.1.222:8091`, and the final completed run `backtest 1`.

## Purpose

This runbook keeps only the current working path for running Ledger backtests through **n8n native AI support**.

It covers:

- how to start Ledger with LAN-reachable callback URLs,
- which n8n workflow, portfolio, and template form the current known good path,
- how the native AI Agent path works,
- how to launch the Jan-Feb 2026 backtest,
- and how to verify success from Ledger, n8n, reports, and stored trades.

## Current Known Good Architecture

The current production runner in n8n is:

- workflow name: `Ledger Tech Seven Ultrabacktest AI Agent Native v4`
- workflow id: `R9J5fXNwIbNvaG5A`
- webhook path: `/webhook/ledger-tech-seven-ultrabacktest-ai-agent-native-v4`

The working LLM path is:

1. Ledger sends a webhook to the n8n workflow.
2. n8n downloads the cycle prompt report from Ledger.
3. The native `AI Agent` node analyzes the cycle using the connected `OpenAI Chat Model` node.
4. The `OpenAI Chat Model` node uses:
   - model `gpt-5.4-mini`
   - reasoning effort `low`
   - Responses API enabled
   - built-in `Web Search` enabled with `High` context size
5. A native n8n JS step normalizes the agent output, filters invalid/future-dated sources, builds Ledger callback payloads, and submits them.
6. n8n uploads the analysis report to Ledger.
7. n8n submits trade decisions to Ledger.
8. n8n completes the cycle.

## Important n8n Usage Point

Use the **n8n-native AI Agent + OpenAI Chat Model** path to analyze the cycle.

This is the preferred success path because:

- n8n already supports the required agent/model/tooling flow natively in the UI,
- web search is configured directly on the native OpenAI Chat Model node,
- and no external Python helper is needed in the execution path.

Practical note:

- n8n Code nodes in this environment still cannot import the `openai` module directly, but that does **not** matter for the current success path because model calls are handled by the native AI nodes, not by custom Python.

## Prerequisites

Before running anything, make sure all of the following are true:

1. Docker is running locally.
2. `uv` and `pnpm` are installed.
3. Python 3.13 is available locally.
4. The n8n instance is reachable at `http://192.168.1.222:8091/`.
5. The OpenAI-compatible provider is reachable at `http://192.168.1.222:8087/v1`.

## Start Ledger With LAN-Reachable URLs

Run Ledger with a public base URL that n8n can reach from another machine:

```bash
env UV_PYTHON=/opt/homebrew/bin/python3.13 \
  BACKEND_HOST=0.0.0.0 \
  BACKEND_PUBLIC_HOST=192.168.1.231 \
  PUBLIC_BASE_URL=http://192.168.1.231:28000 \
  bash ./start.sh
```

Expected checks:

```bash
curl http://127.0.0.1:28000/health
curl http://192.168.1.231:28000/health
```

Both should return:

```json
{"status":"ok"}
```

## n8n Native AI Configuration

The verified native configuration lives in the n8n UI workflow `Ledger Tech Seven Ultrabacktest AI Agent Native v4`.

Key node-level settings:

- `AI Agent`
  - used as the cycle analyzer
  - receives the compacted prompt report text
- `OpenAI Chat Model`
  - model id: `gpt-5.4-mini`
  - `Use Responses API`: enabled
  - built-in `Web Search`: enabled
  - `Search Context Size`: `High`
  - `Reasoning Effort`: `Low`
- native n8n JS step
  - normalizes the AI output into valid Ledger callback payloads
  - removes invalid or future-dated sources
  - calls Ledger `/report`, `/trades`, and `/complete`

## Prepare the Portfolio Context

The current verified portfolio used for the final success path is:

- portfolio id: `1`
- portfolio slug: `tech_seven_investor_native_agent_fresh`
- deposit balance: `10000 USD`
- seeded symbols: `AAPL`, `MSFT`, `GOOGL`, `AMZN`, `META`, `NVDA`, `TSLA`

The seeded holdings were created as BUY operations at 2025-12-31 closes so the backtest starts from a realistic held portfolio state.

## Prepare the Backtest Template

The current verified template used for the final success path is:

- template id: `1`
- template name: `Tech Seven Self-Reflection Daily Backtest Template Native Agent Fresh`

This template requires the analysis workflow to cover:

- company news,
- stock performance,
- market data,
- economy status,
- industry status,
- other relevant information,
- and dated sources that are not later than the cycle date.

## Launch the Backtest

Create a new full-session backtest pointing at the native n8n AI-agent webhook path:

```json
{
  "name": "Tech Seven Ultrabacktest Jan-Feb 2026 native agent fresh",
  "portfolioId": 1,
  "templateId": 1,
  "createTemplate": false,
  "templateName": null,
  "frequency": "DAILY",
  "startDate": "2026-01-01",
  "endDate": "2026-02-28",
  "webhookUrl": "http://192.168.1.222:8091/webhook/ledger-tech-seven-ultrabacktest-ai-agent-native-v4",
  "webhookTimeout": 600,
  "priceMode": "CLOSING_PRICE",
  "commissionMode": "ZERO",
  "commissionValue": "0",
  "benchmarkSymbols": ["^GSPC", "^NDX"]
}
```

API path:

```http
POST /api/v1/backtests
```

## Verify Success

### Ledger side

Check the backtest row:

```bash
curl http://127.0.0.1:28000/api/v1/backtests/1
```

Success signals:

- `status = COMPLETED`
- `completedCycles = 39`
- `totalCycles = 39`
- `errorMessage = null`

### n8n side

Use the n8n REST API to inspect the final workflow executions:

```bash
python3 - <<'PY'
import json, requests

s = requests.Session()
s.post(
    'http://192.168.1.222:8091/rest/login',
    json={'emailOrLdapLoginId': 'holdon365@msn.cn', 'password': 'Liqing@7788'},
    timeout=30,
).raise_for_status()

resp = s.get(
    'http://192.168.1.222:8091/rest/executions?limit=20',
    headers={'Accept': 'application/json'},
    timeout=30,
)
resp.raise_for_status()

results = [
    {
        'id': row['id'],
        'status': row['status'],
        'createdAt': row['createdAt'],
        'stoppedAt': row.get('stoppedAt'),
    }
    for row in resp.json()['data']['results']
    if row['workflowId'] == 'R9J5fXNwIbNvaG5A'
]

print(json.dumps(results, indent=2))
PY
```

Success signals:

- executions belong to workflow `R9J5fXNwIbNvaG5A`
- recent execution statuses are `success`

### Report evidence

Check that `backtest_analysis` reports were stored:

```bash
python3 - <<'PY'
import json, requests

reports = requests.get(
    'http://127.0.0.1:28000/api/v1/reports?tag=backtest_1',
    timeout=30,
).json()

analysis = [
    row for row in reports
    if row.get('metadata', {}).get('analysis', {}).get('reviewType') == 'backtest_analysis'
]

print(json.dumps({'analysisCount': len(analysis), 'latest': analysis[0] if analysis else None}, indent=2)[:6000])
PY
```

Success signals:

- `analysisCount = 39`
- latest report includes dated sections for company news, stock performance, market data, economy status, industry status, reflection, and sources

### Trade evidence

Verify that backtest trades were actually written into the portfolio:

```bash
python3 - <<'PY'
import json, requests

ops = requests.get(
    'http://127.0.0.1:28000/api/v1/portfolios/1/trading-operations',
    timeout=30,
).json()

print(json.dumps({'count': len(ops), 'latest': ops[:10]}, indent=2)[:6000])
PY
```

Success signals:

- count is greater than the 7 seeded trades
- later rows show simulated BUY/SELL operations created during the backtest

### Whole-run source-date audit

Check that every cited source in the stored analysis reports is dated on or before its cycle date:

```bash
python3 - <<'PY'
import json, re, requests
from datetime import datetime

base = 'http://127.0.0.1:28000/api/v1'
reports = requests.get(f'{base}/reports?tag=backtest_1', timeout=30).json()
analysis = [
    row for row in reports
    if row.get('metadata', {}).get('analysis', {}).get('reviewType') == 'backtest_analysis'
]

violations = []
for report in analysis:
    cycle_date = report['metadata']['analysis']['cycleDate']
    content = requests.get(f"{base}/reports/{report['slug']}/download", timeout=20).text
    for line in content.splitlines():
        if line.startswith('- ['):
            match = re.search(r'\(([^)]+)\)$', line)
            if not match:
                violations.append({'slug': report['slug'], 'reason': 'missing trailing date'})
                continue
            raw = match.group(1)
            iso = re.search(r'\d{4}-\d{2}-\d{2}', raw)
            if not iso:
                violations.append({'slug': report['slug'], 'reason': 'unparseable or missing date'})
                continue
            source_dt = datetime.strptime(iso.group(0), '%Y-%m-%d').date()
            cycle_dt = datetime.strptime(cycle_date, '%Y-%m-%d').date()
            if source_dt > cycle_dt:
                violations.append({'slug': report['slug'], 'reason': f'{source_dt}>{cycle_dt}'})

print(json.dumps({'analysisCount': len(analysis), 'violationCount': len(violations)}, indent=2))
PY
```

Success signals:

- `analysisCount = 39`
- `violationCount = 0`

## Current Verified Result

At the time of writing, the following has been verified locally:

- native n8n AI Agent path is active and working
- workflow `R9J5fXNwIbNvaG5A` is the current success-path workflow
- template `1` was created and used for the final run
- portfolio `1` was created and used for the final run
- backtest `1` completed the full Jan-Feb 2026 window
- 39 analysis reports were stored
- simulated BUY/SELL trades were executed through Ledger's API during the run
- the full report set passed a whole-run source-date audit with zero violations
