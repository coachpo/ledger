# Self-Reflection Template Workflow Guide

> Status: Current practical guide for running a minimal self-reflection stock-analysis loop in live Ledger. Verified locally on 2026-03-21 against the `start.sh` stack and the shipped template/report workflow; the separate backtest module is live but not required for this template-driven loop.

## Purpose

This guide explains how to use Ledger's existing template and report system to simulate a versioned self-reflection stock-analysis loop.

The workflow does not add scheduling or automation inside Ledger. Instead, it uses:

- a saved text template,
- runtime compile inputs,
- live portfolio data,
- report metadata,
- and dynamic report selectors.

## What This Workflow Exercises

The minimum loop relies on the following live capabilities:

- `POST /api/v1/templates` for storing the template
- `POST /api/v1/templates/{templateId}/compile` for preview with runtime inputs
- `POST /api/v1/reports/compile/{templateId}` for saving a compiled versioned report
- `{{portfolios.by_slug(inputs.portfolio_slug)...}}` for portfolio-scoped data
- `{{portfolios.by_slug(inputs.portfolio_slug).positions.by_symbol(inputs.ticker)...}}` for symbol-scoped holdings
- `{{reports.by_tag(inputs.analysis_tag).latest...}}` for the most recent prior report in one reflection series

## Prerequisites

Before using the template, make sure all of the following are true:

1. The app is running via `./start.sh`.
2. You have at least one portfolio.
3. That portfolio has at least one position for the ticker you want to review.
4. You choose a stable reflection-series tag and keep reusing it across versions.

Recommended stable identifiers for one report series:

- `ticker`: the stock under review, such as `AAPL`
- `portfolio_slug`: the portfolio context, such as `core_us`
- `analysis_tag`: a series identifier, such as `aapl_core_weekly`
- `reviewType`: an analysis category, such as `weekly_review`

## Minimal Chinese Template

Save the following template as a stored Ledger template:

```md
# {{inputs.ticker}} 复盘（{{inputs.review_date}}）

- 触发原因：{{inputs.trigger}}
- 组合：{{portfolios.by_slug(inputs.portfolio_slug).name}}
- 当前持仓：{{portfolios.by_slug(inputs.portfolio_slug).positions.by_symbol(inputs.ticker).quantity}} 股
- 上一版报告：{{reports.by_tag(inputs.analysis_tag).latest.name}}

## 1. 当前判断
- 结论：{{inputs.current_stance}}
- 变化：{{inputs.change_summary}}

## 2. 行动
- 动作：{{inputs.action}}
- 原因：{{inputs.action_reason}}

## 3. 反思
{{inputs.reflection}}

## 4. 上一版摘要
{{reports.by_tag(inputs.analysis_tag).latest.content}}
```

This is intentionally small. It covers the five essential layers of the workflow:

- current review metadata,
- current judgment,
- action,
- reflection,
- and prior-version carry-forward.

## Step-by-Step Workflow

### 1. Start the local stack

Run:

```bash
./start.sh
```

Expected local URLs:

- backend: `http://127.0.0.1:28000`
- frontend: `http://127.0.0.1:25173`

### 2. Prepare one portfolio context

Create or reuse a portfolio that contains the ticker you want to review.

For the template above to compile successfully, the following placeholder path must resolve:

```text
portfolios.by_slug(inputs.portfolio_slug).positions.by_symbol(inputs.ticker).quantity
```

That means:

- `portfolio_slug` must match a real portfolio slug
- `ticker` must match a real position symbol in that portfolio

### 3. Create and save the template

UI path:

1. Open `/templates`.
2. Click `New Template`.
3. Paste the Chinese template.
4. Save it.

API path:

```http
POST /api/v1/templates
```

Example body:

```json
{
  "name": "AAPL Reflection Loop CN Minimal",
  "content": "# {{inputs.ticker}} 复盘（{{inputs.review_date}}）\n\n- 触发原因：{{inputs.trigger}}\n- 组合：{{portfolios.by_slug(inputs.portfolio_slug).name}}\n- 当前持仓：{{portfolios.by_slug(inputs.portfolio_slug).positions.by_symbol(inputs.ticker).quantity}} 股\n- 上一版报告：{{reports.by_tag(inputs.analysis_tag).latest.name}}\n\n## 1. 当前判断\n- 结论：{{inputs.current_stance}}\n- 变化：{{inputs.change_summary}}\n\n## 2. 行动\n- 动作：{{inputs.action}}\n- 原因：{{inputs.action_reason}}\n\n## 3. 反思\n{{inputs.reflection}}\n\n## 4. 上一版摘要\n{{reports.by_tag(inputs.analysis_tag).latest.content}}"
}
```

### 4. Preview the first run

Before creating a report, compile the stored template with runtime inputs.

API path:

```http
POST /api/v1/templates/{templateId}/compile
```

Example first-run body:

```json
{
  "inputs": {
    "ticker": "AAPL",
    "review_date": "2026-03-19",
    "trigger": "首次建模",
    "portfolio_slug": "aapl_loop_demo",
    "analysis_tag": "aapl_loop_min",
    "current_stance": "观察",
    "change_summary": "先建立基线版本，后续只比较真正变化。",
    "action": "不动",
    "action_reason": "先记录初始判断，不急于调整仓位。",
    "reflection": "先从空白页写判断，再回看历史版本，避免被旧叙事绑架。"
  }
}
```

Expected result on the first run:

- current sections compile normally
- `上一版报告` is blank
- `上一版摘要` is blank

This is correct behavior. At this point there is no prior report with the matching tag.

### 5. Generate version 1

After preview succeeds, generate the first saved report.

UI paths:

- `/reports` -> `Generate Report`
- or saved template editor -> `Generate Report`

API path:

```http
POST /api/v1/reports/compile/{templateId}
```

Example first-report body:

```json
{
  "inputs": {
    "ticker": "AAPL",
    "review_date": "2026-03-19",
    "trigger": "首次建模",
    "portfolio_slug": "aapl_loop_demo",
    "analysis_tag": "aapl_loop_min",
    "current_stance": "观察",
    "change_summary": "先建立基线版本，后续只比较真正变化。",
    "action": "不动",
    "action_reason": "先记录初始判断，不急于调整仓位。",
    "reflection": "先从空白页写判断，再回看历史版本，避免被旧叙事绑架。"
  },
  "metadata": {
    "tags": ["aapl_loop_min"],
    "description": "AAPL 最小复盘流程演示：第 1 版",
    "analysis": {
      "ticker": "AAPL",
      "portfolioSlug": "aapl_loop_demo",
      "reviewType": "weekly_review",
      "trigger": "首次建模",
      "reviewDate": "2026-03-19",
      "versionGroup": "aapl_loop_min"
    }
  }
}
```

Important rule:

- The same series identifier must appear in both `inputs.analysis_tag` and `metadata.tags`.

If you change the tag between runs, the next version will not find the previous report.

### 6. Generate version 2

Create the next report with updated inputs but the same series tag.

Example second-report body:

```json
{
  "inputs": {
    "ticker": "AAPL",
    "review_date": "2026-03-26",
    "trigger": "周度复盘",
    "portfolio_slug": "aapl_loop_demo",
    "analysis_tag": "aapl_loop_min",
    "current_stance": "继续持有",
    "change_summary": "本周没有出现 thesis-breaking 事件，只把上周基线与本周事实做差异记录。",
    "action": "持有",
    "action_reason": "逻辑未破坏，暂时没有新的买卖触发条件。",
    "reflection": "价格波动不等于逻辑变化；先确认事实变化，再决定是否行动。"
  },
  "metadata": {
    "tags": ["aapl_loop_min"],
    "description": "AAPL 最小复盘流程演示：第 2 版",
    "analysis": {
      "ticker": "AAPL",
      "portfolioSlug": "aapl_loop_demo",
      "reviewType": "weekly_review",
      "trigger": "周度复盘",
      "reviewDate": "2026-03-26",
      "versionGroup": "aapl_loop_min"
    }
  }
}
```

Expected result on the second run:

- `上一版报告` resolves to the first report name
- `上一版摘要` resolves to the first report body

This is the minimum viable self-reflection loop:

1. write a fresh current view
2. save a point-in-time version
3. let the next version pull that saved history

### 7. Review the reports in the frontend

After generating reports:

1. Open `/reports`.
2. Confirm multiple compiled reports exist for the same series.
3. Open `/reports/:slug` for the latest report.
4. Confirm the rendered markdown includes the prior version under `上一版摘要`.

## Why the First Run Is Blank

The first run does not find a previous report because report compilation happens before the new report is saved.

That means:

- `reports.by_tag(inputs.analysis_tag).latest.name` has no matching prior report yet
- valid no-match dynamic selectors resolve to an empty string

This is expected and should be treated as the baseline version, not as a failure.

## Operational Rules

For reliable behavior, follow these rules every time:

1. Keep `analysis_tag` unique per reflection series.
2. Keep `analysis_tag` stable across versions of the same series.
3. Keep `ticker` and `portfolioSlug` consistent when comparing the same thesis stream.
4. Save the template before trying to generate a report from it.

Good tag examples:

- `aapl_core_weekly`
- `msft_growth_monthly`
- `tsla_event_driven`

## Caveats

This minimal template is correct for a practical demo, but it has important limits.

### 1. Previous-report blanks are silent

If `analysis_tag`, `ticker`, or `portfolio_slug` is wrong, you may also see blank previous sections.

Blank previous sections can mean either:

- this is the first run
- or the selector inputs do not match the intended report series

### 2. `latest.content` grows over time

`{{reports.by_tag(inputs.analysis_tag).latest.content}}` embeds the full previous report body.

That means each new report can carry forward the full prior chain. This is acceptable for a minimal two-step or short-run workflow, but it can become large across many iterations.

### 3. Edited historical reports can affect later compiles

Report `content` is re-compiled when selected through `.content`.

If an old report is edited to include template placeholders later, those placeholders can resolve again during future compiles. Circular report references are guarded with explicit sentinel text, but this is still a workflow concern.

## Safer Long-Run Variant

If the workflow becomes a recurring production process, consider keeping the previous report name but replacing the embedded full body with a manual summary input.

For example:

```md
- 上一版报告：{{reports.by_tag(inputs.analysis_tag).latest.name}}

## 4. 上一版摘要
{{inputs.previous_summary}}
```

This keeps the comparison structure while preventing nested full-report growth.

## Verified Local Example

The workflow in this guide was verified locally with the following demo objects:

- portfolio slug: `aapl_loop_demo`
- template name: `AAPL Reflection Loop CN Minimal`
- series tag: `aapl_loop_min`
- generated reports:
  - `aapl_reflection_loop_cn_minimal_20260319_131249`
  - `aapl_reflection_loop_cn_minimal_20260319_131259`

The second report successfully rendered the first report name and full prior report body through `reports.by_tag(inputs.analysis_tag).latest.*`.
