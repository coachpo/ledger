# Ledger Backtest AI Workflow Runbook

> Status: Success-path runbook for the current Ledger + n8n streamed backtest flow. Verified locally against the `start.sh` stack, the local streaming helper on `28180`, the live n8n instance on `192.168.1.222:8091`, and the final completed run `backtest 59`.

## Purpose

This runbook keeps only the working path for running Ledger backtests through n8n with the current streamed OpenAI-client helper setup.

It covers:

- how to start Ledger with LAN-reachable callback URLs,
- how to run the local streamed helper,
- which portfolio, template, and n8n workflow form the current known good path,
- how to launch the Jan-Feb 2026 backtest,
- and how to verify success from Ledger, n8n, reports, and stored trades.

## Current Known Good Architecture

The current production runner in n8n is:

- workflow name: `Ledger Tech Seven Ultrabacktest AI Stream Mini v4`
- workflow id: `ZsRHdRBH9BJi7Avx`
- webhook path: `/webhook/ledger-tech-seven-ultrabacktest-ai-stream-mini-v4`

The current working LLM path is:

1. Ledger sends a webhook to the n8n workflow.
2. n8n downloads the cycle prompt report from Ledger.
3. n8n posts the compacted cycle context to the local helper at `http://192.168.1.231:28180/analyze`.
4. The helper uses the Python OpenAI client with `responses.stream(...)`.
5. The helper calls the OpenAI-compatible provider at `http://192.168.1.222:8087/v1`.
6. The helper returns parsed JSON back to n8n.
7. n8n uploads the analysis report to Ledger.
8. n8n submits trade decisions to Ledger.
9. n8n completes the cycle.

Current model settings in the helper:

- model: `gpt-5.4-mini`
- reasoning effort: `low`
- web search: enabled

Important implementation detail:

- n8n's Code node cannot load the `openai` module directly in this environment, so the streamed Python helper is part of the success path, not a fallback.

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

## Start the Local Stream Helper

Run the helper from the repo root:

```bash
python3 backtest_ai_stream_helper.py
```

Expected startup output:

```text
Backtest AI stream helper listening on 0.0.0.0:28180
```

Optional functional check:

```bash
python3 - <<'PY'
import requests, json

payload = {
    "portfolio_context": "# Cycle Prompt (2026-01-02)\n\n## System\nToday is 2026-01-02. Do not use information from after this date.\n\n## User\nPortfolio state:\nBalances:\n- Initial Cash: 7404.3900 USD (DEPOSIT)\nPositions:\n- AAPL: 1.00000000 shares @ 271.85998500 USD\n- AMZN: 1.00000000 shares @ 230.82000700 USD\n- GOOGL: 1.00000000 shares @ 313.00000000 USD\n- META: 1.00000000 shares @ 660.09002700 USD\n- MSFT: 1.00000000 shares @ 483.61999500 USD\n- NVDA: 1.00000000 shares @ 186.50000000 USD\n- TSLA: 1.00000000 shares @ 449.72000100 USD"
}

resp = requests.post("http://127.0.0.1:28180/analyze", json=payload, timeout=120)
print(resp.status_code)
print(json.dumps(resp.json(), indent=2)[:4000])
PY
```

## Prepare the Portfolio Context

The current verified portfolio used for the final success path is:

- portfolio id: `5`
- portfolio slug: `tech_seven_investor_stream_oracle_final`
- deposit balance: `10000 USD`
- seeded symbols: `AAPL`, `MSFT`, `GOOGL`, `AMZN`, `META`, `NVDA`, `TSLA`

The seeded holdings were created as BUY operations at 2025-12-31 closes so the backtest starts from a realistic held portfolio state.

## Prepare the Backtest Template

The current verified template used for the final success path is:

- template id: `4`
- template name: `Tech Seven Self-Reflection Daily Backtest Template Stream Final`

This template requires the analysis workflow to cover:

- company news,
- stock performance,
- market data,
- economy status,
- industry status,
- other relevant information,
- and dated sources that are not later than the cycle date.

## Launch the Backtest

Create a new full-session backtest pointing at the streamed n8n webhook path:

```json
{
  "name": "Tech Seven Ultrabacktest Jan-Feb 2026 stream final",
  "portfolioId": 5,
  "templateId": 4,
  "createTemplate": false,
  "templateName": null,
  "frequency": "DAILY",
  "startDate": "2026-01-01",
  "endDate": "2026-02-28",
  "webhookUrl": "http://192.168.1.222:8091/webhook/ledger-tech-seven-ultrabacktest-ai-stream-mini-v4",
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
curl http://127.0.0.1:28000/api/v1/backtests/59
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
    if row['workflowId'] == 'ZsRHdRBH9BJi7Avx'
]

print(json.dumps(results, indent=2))
PY
```

Success signals:

- executions belong to workflow `ZsRHdRBH9BJi7Avx`
- recent execution statuses are `success`

### Report evidence

Check that `backtest_analysis` reports were stored:

```bash
python3 - <<'PY'
import json, requests

reports = requests.get(
    'http://127.0.0.1:28000/api/v1/reports?tag=backtest_59',
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
    'http://127.0.0.1:28000/api/v1/portfolios/5/trading-operations',
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
reports = requests.get(f'{base}/reports?tag=backtest_59', timeout=30).json()
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

- streamed helper path is active and working
- n8n workflow `ZsRHdRBH9BJi7Avx` is the current success-path workflow
- template `4` was created and used for the final run
- portfolio `5` was created and used for the final run
- backtest `59` completed the full Jan-Feb 2026 window
- 39 analysis reports were stored
- simulated BUY/SELL trades were executed through Ledger's API during the run
- the full report set passed a whole-run source-date audit with zero violations
