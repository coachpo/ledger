# Self-Reflection Stock Analysis Loop

> Status: Strategy/process reference. The current Ledger codebase provides template-backed report history, report filters, external report creation, dynamic report selectors, and an experimental backtest module for historical simulation, but it still does not run general-purpose scheduling or autonomous analysis automation internally.

## Purpose

This document describes a structured, versioned approach to stock analysis designed to improve decision quality over time. The core idea is simple:

- analyze a stock repeatedly over time,
- save each analysis as a versioned record,
- compare the newest version with earlier versions,
- identify what truly changed,
- and translate those changes into better investment actions.

The point of this process is **not** to produce more reports. The point is to produce a **better decision system**.

A good self-reflection loop helps answer questions such as:

- What did I believe before?
- What do I believe now?
- What changed in the business, valuation, or risk profile?
- What did I miss previously?
- Am I reacting to real change or just market noise?
- Do I need to buy, add, hold, trim, sell, or do nothing?

This process is especially useful because markets are dynamic, narratives drift, and memory is unreliable. Without a structured loop, investors often rewrite their own history, overweight recent price moves, or convince themselves that nothing important has changed when the thesis has in fact deteriorated.

---

## Core Philosophy

The foundation of this approach is that stock analysis should be treated as a **versioned reasoning process**, not a one-time opinion.

A traditional approach often looks like this:

1. Analyze a stock.
2. Write a report.
3. Make a decision.
4. Revisit only when something dramatic happens.

That approach loses too much information between reviews. It makes it hard to know:

- which assumptions mattered,
- which assumptions were wrong,
- which changes were visible early,
- and whether later decisions were based on evidence or emotion.

The self-reflection loop changes that by introducing four principles:

### 1. Every thesis must be explicit

Your view should not live only in your head. It must be written down in a consistent structure so it can be checked later.

### 2. Every revision must be comparable

Later versions must be comparable with earlier versions. Otherwise you create a sequence of documents that feel thoughtful but do not actually reveal what changed.

### 3. Facts, interpretation, and action must be separated

A new fact is not the same as a new conclusion. A new conclusion is not the same as a trading action. The process must distinguish these clearly.

### 4. Reflection must be part of the process

The goal is not only to update the stock view. The goal is also to update the **quality of the analyst**. Each cycle should teach you something about your own blind spots, biases, and recurring mistakes.

---

## What Problem This Solves

This process is designed to reduce several common investing errors.

### Anchoring to the initial thesis

Investors often become attached to their first view of a company. Later evidence is forced into that original frame instead of being assessed honestly.

### Narrative drift

Over time, the reason for holding a stock changes subtly without being acknowledged. A stock bought for value becomes a “long-term quality compounder.” A speculative trade becomes a “core conviction position.” Versioning exposes this drift.

### Price-led reasoning

Many investors unknowingly change their analysis because the stock moved, not because the business changed. The loop forces a distinction between price change and thesis change.

### Hindsight bias

After an event, it is easy to believe you “already knew” the risk or opportunity. Saved prior versions reveal whether that is true.

### Overreaction to noise

Not every headline or market move deserves action. The process introduces structured thresholds so that updates do not automatically become trades.

### Underreaction to fundamental change

Sometimes the price does not move much, but the business quality, management credibility, or risk profile changes materially. This process helps catch those cases earlier.

---

## High-Level Process Overview

At a high level, the loop works like this:

1. Create an initial analysis and save it as Version 1.
2. On each later review date, perform a fresh analysis.
3. Save the new version.
4. Compare the new version against earlier versions.
5. Identify what changed in facts, interpretation, valuation, risk, and confidence.
6. Decide whether the change is noise, a thesis update, or an actionable event.
7. Record the action or non-action along with the reason.
8. Reflect on mistakes, omissions, and bias.

Over time, this creates a living record of:

- the company,
- the thesis,
- the valuation,
- the decision rules,
- and your own learning process.

---

## Recommended Review Cadence

The original idea proposed daily analysis. That can work in some situations, but the best cadence depends on the type of stock and the investment style.

### When daily review makes sense

Daily review may be useful when:

- the stock is catalyst-heavy,
- the company is in the middle of major uncertainty,
- earnings or regulatory events are pending,
- the position is part of a short-term strategy,
- or the stock is unusually news-sensitive.

### When daily review is too frequent

For many long-term investments, daily full-thesis rewriting is excessive. It increases the chance of reacting to noise and gives minor developments too much narrative weight.

### Better default rhythm

A stronger operating model is often:

- **daily news capture**,
- **weekly thesis review**,
- **monthly deep rewrite**,
- and **event-driven updates** after major developments.

### Suggested cadence structure

A practical model is:

#### Daily

Record any relevant new facts, price moves, market reactions, and notable developments. Keep this lightweight.

#### Weekly

Review whether any new information changed the business case, valuation, or risk assessment. Update only what changed.

#### Monthly or quarterly

Rebuild the thesis more deeply. Revisit assumptions, scorecards, valuation methods, and position sizing logic.

#### Event-driven

Trigger an immediate review when a major event happens, such as:

- earnings release,
- guidance change,
- management turnover,
- debt refinancing issue,
- major acquisition or divestiture,
- regulatory action,
- structural competitive change,
- or a large price move relative to fair value.

---

## The Most Important Rule: Analyze First, Compare Later

One of the most valuable improvements to the original idea is this:

> On each review date, perform a fresh analysis before reading the older reports.

This reduces self-copying and anchoring.

A weak workflow is:

1. open yesterday’s report,
2. update a few lines,
3. call it a new analysis.

That workflow tends to preserve previous framing and discourages independent reassessment.

A stronger workflow is:

1. perform the new analysis from current evidence,
2. write the new conclusions,
3. then compare against prior versions,
4. and only then identify what changed.

This sequence helps answer a critical question:

- **Would I still reach this conclusion if I had not seen my earlier report?**

That question protects against intellectual inertia.

---

## Detailed Workflow

## Phase 1: Universe Selection or Review Trigger

Before each cycle, clarify why this stock is being reviewed now.

Typical triggers include:

- scheduled review date,
- major news event,
- earnings release,
- large price move,
- portfolio rebalance,
- or appearance of a new opportunity.

This phase should answer:

- Why am I looking at this stock today?
- Is this a routine review or an exceptional review?
- What kind of action might reasonably result from this review?

This is important because it sets the context. Reviews triggered by price dislocation may focus more on valuation. Reviews triggered by business developments may focus more on thesis integrity.

---

## Phase 2: Fresh Analysis Snapshot

Create a clean assessment of the stock based on current information.

This should include the following sections.

### 2.1 Business Summary

Summarize the company in a concise but precise way:

- what it sells,
- how it makes money,
- key segments,
- customer base,
- geographic mix,
- and major profit drivers.

The goal is to anchor analysis in the business, not the stock chart.

### 2.2 Current Context

Record the current state of the company and market context:

- current price,
- approximate market capitalization,
- basic valuation multiples,
- recent operating performance,
- recent news,
- and broad sector context.

### 2.3 Investment Thesis

Write the current thesis in plain language:

- Why might this stock outperform?
- What is the source of expected return?
- Is the case based on quality, growth, value, turnaround, special situation, cyclicality, or another driver?

The thesis should not be vague. A clear thesis usually includes:

- the core reason the market may be mispricing the stock,
- the mechanism by which value should be realized,
- and the timeline or catalyst path.

### 2.4 Bear Case

State clearly why the thesis could fail:

- deteriorating economics,
- competition,
- leverage,
- weak capital allocation,
- regulation,
- customer concentration,
- valuation compression,
- or management quality concerns.

### 2.5 Key Assumptions

List the assumptions supporting the thesis. These should be testable whenever possible.

Examples:

- revenue can grow above industry average,
- margins can expand by a defined amount,
- customer retention remains stable,
- debt remains manageable,
- management capital allocation stays disciplined,
- or valuation rerates toward a certain range.

### 2.6 Valuation View

Document the current estimate of value using one or more methods:

- discounted cash flow,
- earnings multiple,
- EV/EBITDA,
- sum-of-the-parts,
- asset-based valuation,
- historical range comparison,
- or peer comparison.

Record:

- base case fair value,
- bull case fair value,
- bear case fair value,
- margin of safety,
- and expected return relative to current price.

### 2.7 Risk Assessment

Identify the main risks and classify them if useful:

- business risk,
- financial risk,
- valuation risk,
- governance risk,
- macro risk,
- regulatory risk,
- execution risk.

### 2.8 Confidence Level

Assign a confidence level to the thesis. This can be numeric or descriptive, but it should be standardized across all reviews.

### 2.9 Provisional Action Stance

End the fresh analysis with a tentative stance before comparing with history:

- buy,
- add,
- hold,
- trim,
- sell,
- avoid,
- or watch.

This is only provisional. Final action comes after comparison and trigger evaluation.

---

## Phase 3: Save the Version

Each review should be saved as a versioned snapshot.

A version should contain:

- date,
- ticker,
- review trigger,
- review type,
- thesis summary,
- valuation summary,
- risk summary,
- confidence score,
- and provisional stance.

### Why versioning matters

Without preserved versions, the process becomes memory-dependent. Memory is highly unreliable in investing because belief updating often happens gradually and unconsciously.

Versioning turns judgment into an inspectable process.

---

## Phase 4: Structured Comparison Against Prior Versions

After the new version is saved, compare it with earlier versions.

This is where the loop becomes genuinely reflective.

### Comparison dimensions

Each new version should be compared across these dimensions:

- facts,
- interpretation,
- thesis strength,
- valuation,
- risk,
- confidence,
- and action stance.

### Questions to ask during comparison

- What new facts appeared since the last review?
- Which prior assumptions were confirmed?
- Which prior assumptions weakened?
- Which assumptions were invalidated?
- Did valuation change, or did only the stock price change?
- Did the business improve, deteriorate, or stay effectively the same?
- Did management quality or credibility change?
- Did competitive position change?
- Did I identify anything today that I should have seen earlier?
- Am I more or less confident now?
- What exactly explains that confidence change?

### Change classification

Every observed difference should be labeled as one of the following:

- **new fact**
- **changed interpretation**
- **corrected mistake**
- **noise**
- **thesis-strengthening event**
- **thesis-weakening event**
- **thesis-breaking event**

This classification is essential. It prevents all updates from being treated equally.

---

## Phase 5: Determine Whether the Change Matters

Not every change deserves the same response. This phase converts comparison into practical judgment.

A useful framework is to classify the review result into three levels.

### Level 1: Noise

These are changes that should be recorded but usually do not justify thesis revision or trading action.

Examples:

- normal daily price movement,
- commentary with no operational substance,
- small analyst estimate revisions,
- macro chatter without stock-specific impact,
- or superficial news flow.

Question to ask:

- Did this change intrinsic value, thesis probability, or downside risk?

If the answer is no, treat it as noise.

### Level 2: Thesis Update

These are changes that alter your understanding of the stock but may not cross an action threshold.

Examples:

- slightly lower growth expectations,
- moderate margin compression,
- somewhat weaker capital allocation,
- a product delay,
- or a risk becoming more probable but not yet thesis-breaking.

Question to ask:

- Did this change my estimate or confidence without crossing a buy/sell boundary?

If yes, revise the thesis, valuation, or confidence, but do not automatically trade.

### Level 3: Actionable Change

These are changes that justify a portfolio action.

Examples:

- price moving deeply below buy range while thesis remains intact,
- price moving above fair value with limited future return,
- earnings showing the thesis was wrong,
- balance sheet risk becoming unacceptable,
- management credibility breaking,
- moat deterioration,
- regulatory change altering economics,
- or capital allocation becoming destructive.

Question to ask:

- Did one of my predefined action thresholds get crossed?

If yes, the review should lead to an action decision.

---

## Deliverables of the Process

The process should produce several specific outputs. The deliverable is not just a report; it is a **decision-support system** composed of multiple parts.

## 1. Current Thesis File

This is the latest, consolidated view of the stock. It should answer:

- What is the company?
- Why is it attractive or unattractive?
- What is the fair value range?
- What are the key assumptions?
- What are the major risks?
- What is the current stance?

This file represents the current state of belief.

## 2. Version History

This is the archive of all prior analyses. It exists so that belief changes can be traced over time.

Each version should preserve:

- the thesis at that point in time,
- the valuation at that point in time,
- the risks identified then,
- the confidence level then,
- and the recommended action then.

## 3. Change Log

This is a structured record of what changed between versions.

It should include:

- new facts,
- changed interpretation,
- corrected errors,
- strengthened or weakened thesis elements,
- changes in fair value,
- changes in risk,
- and changes in confidence.

The change log helps prevent self-deception.

## 4. Trigger Dashboard

This is a checklist of predefined action thresholds.

Typical trigger categories include:

- valuation triggers,
- operating performance triggers,
- balance sheet triggers,
- governance triggers,
- competitive position triggers,
- and portfolio risk triggers.

This dashboard answers:

- Has something crossed a boundary that requires action?

## 5. Action Memo

Each review should end with a short action memo stating:

- no action,
- buy,
- add,
- hold,
- trim,
- sell,
- avoid,
- or watch.

It must also state:

- why,
- what changed,
- and what would reverse that action.

## 6. Reflection Log

This is the self-improvement layer.

It should capture:

- what you got right,
- what you missed,
- whether you were too optimistic or pessimistic,
- whether price movement influenced reasoning too much,
- and whether the latest conclusion would still hold if you had not seen the prior report.

---

## What the Final Deliverable Should Look Like in Practice

The most useful output after each review cycle is a compact decision summary.

A practical one-page review output can be structured like this:

### Review Summary

- **Date:**
- **Ticker:**
- **Review trigger:**
- **Current stance:** Buy / Add / Hold / Trim / Sell / Avoid / Watch

### 1. What changed since last review

A short list of the most important changes.

### 2. Did the thesis change?

State whether the thesis changed:

- not at all,
- slightly,
- materially,
- or completely.

Explain why.

### 3. Did fair value change?

State whether fair value changed:

- no,
- up,
- down.

Explain why.

### 4. Did risk change?

State whether risk is:

- lower,
- unchanged,
- higher.

Explain why.

### 5. Action

State the action:

- no action,
- buy,
- add,
- hold,
- trim,
- sell.

### 6. Reason for action

Write one focused paragraph explaining the action.

### 7. Reversal conditions

State the specific conditions that would cause you to change this view.

This structure makes each review operational rather than merely descriptive.

---

## Distinguishing the Types of Change That Matter

A central part of the process is learning to separate three very different situations.

## A. Price changed, thesis unchanged

This is often a valuation event rather than a business event.

Example:

- the company is operating as expected,
- the thesis remains intact,
- but the stock falls 20%.

Possible implication:

- the stock may become more attractive,
- and a buy or add decision may be justified.

## B. Thesis changed, price unchanged

This is often more dangerous than it looks.

Example:

- revenue quality weakens,
- margins become less durable,
- management credibility slips,
- but the price has not yet reacted meaningfully.

Possible implication:

- intrinsic value may be lower,
- future risk may be higher,
- and a trim or sell decision may be justified even without a dramatic price move.

## C. Both price and thesis changed

This is the most important case. The job is to determine whether the price moved more than the fundamentals, less than the fundamentals, or in the wrong direction entirely.

This requires integrated judgment rather than formulaic reaction.

---

## Action Framework

Actions should never be based solely on the existence of new information. They should be based on whether predefined conditions have been crossed.

## Buy Triggers

A buy decision is strongest when both conditions are true:

1. the stock offers sufficient expected return relative to current price,
2. and the thesis remains intact or improves.

Typical buy criteria may include:

- price materially below base-case fair value,
- expected return above hurdle rate,
- acceptable downside,
- no major thesis break,
- confidence at or above minimum threshold,
- and position size still within portfolio rules.

## Add Triggers

An add decision should be more demanding than a simple buy if the stock is already owned.

Typical add criteria may include:

- thesis intact,
- new evidence strengthening conviction,
- deeper discount to value,
- attractive risk/reward,
- and room within position sizing limits.

## Hold Triggers

A hold decision is appropriate when:

- thesis remains intact,
- valuation is roughly fair,
- no major risk change has occurred,
- and there is no clearly superior alternative requiring capital redeployment.

## Trim Triggers

A trim decision is appropriate when:

- upside becomes limited relative to fair value,
- the position becomes too large in the portfolio,
- risk/reward worsens,
- or the stock remains good but no longer especially attractive.

## Sell Triggers

A sell decision is justified when one or more of the following occur:

- the thesis is broken,
- key assumptions are invalidated,
- governance trust is damaged,
- balance sheet risk becomes unacceptable,
- expected return becomes unattractive,
- better opportunities clearly dominate,
- or price moves far enough above fair value to make future return poor.

## Watch / Avoid

Not every stock should lead to immediate capital allocation. A watch or avoid label is useful when:

- the business is interesting but too expensive,
- the thesis is plausible but confidence is low,
- uncertainty is too high,
- or the company fails basic quality or governance requirements.

---

## How to Know Whether a Situation Has Changed Enough to Act

This is one of the most important questions in the entire process.

A practical answer is:

> Act only when at least one of the following changes materially:
>
> - intrinsic value,
> - probability of the thesis being right,
> - downside risk,
> - expected return,
> - or portfolio risk.

If none of these changed materially, action is usually not required.

### Decision boundary questions

At the end of each review, ask these questions explicitly:

- Has intrinsic value changed enough to alter expected return materially?
- Has the probability of my thesis being correct risen or fallen meaningfully?
- Has downside risk increased to an unacceptable level?
- Has position size become inconsistent with current conviction or risk?
- Is there a superior use of capital elsewhere?

If the answer to all of these is no, the default action is often **no action**.

---

## Recommended Scoring System

A scoring framework adds discipline and makes change easier to quantify.

The purpose of scoring is not to replace judgment. It is to make judgment more explicit and more comparable over time.

### Suggested scoring categories

Score each category on a fixed scale such as 1 to 5.

- business quality
- management trust
- competitive strength
- growth durability
- margin durability
- balance sheet strength
- capital allocation quality
- valuation attractiveness
- downside risk
- overall conviction

### Why scoring helps

Scoring can reveal situations where the narrative sounds unchanged but the underlying judgment has deteriorated. For example:

- management trust drops from 4 to 2,
- balance sheet strength drops from 4 to 3,
- valuation attractiveness drops from 5 to 2,
- but the written conclusion still says “high conviction.”

That mismatch is exactly the kind of inconsistency the loop should expose.

### Scoring rules

To make scoring useful:

- define what each score means,
- apply the same scale every time,
- document why a score changed,
- and never change the scoring logic casually.

### Example 1-to-5 interpretation

#### 5

Excellent, clearly supportive of the thesis.

#### 4

Strong, with minor caveats.

#### 3

Mixed or average.

#### 2

Weak, concerning, or unstable.

#### 1

Very poor or thesis-threatening.

---

## Reflection Layer: The Analyst Improvement Loop

This is the part that transforms a stock review process into a self-reflection system.

Each review should end with a reflection block. This should not be long, but it should be honest and specific.

### Reflection questions

- What did I get right?
- What did I miss previously?
- What did I underestimate?
- What did I overestimate?
- Was I influenced too much by recent price movement?
- Was I too attached to the original thesis?
- Did I confuse management narrative with evidence?
- Would I reach the same conclusion if I started from a blank page today?
- What recurring weakness in my analysis does this case reveal?

### Why this matters

Most investors review stocks. Fewer review their own thinking. Fewer still do it systematically. Over time, the reflection log becomes a dataset about your own judgment patterns.

It may reveal recurring tendencies such as:

- overconfidence in management,
- underweighting balance sheet risk,
- overreacting to price volatility,
- staying too long in deteriorating theses,
- selling too early when valuation normalizes,
- or failing to distinguish cyclical weakness from structural decline.

That learning is one of the highest-value outputs of the entire process.

---

## Recommended Document Structure for Each Stock

A well-organized system matters. The structure below works well for maintaining one stock over time.

## Folder / file concept

For each stock, maintain:

- a master thesis file,
- versioned reports,
- a change log,
- a trigger dashboard,
- and a reflection log.

### Example structure

```text
/STOCKS/
  /TICKER/
    master_thesis.md
    trigger_dashboard.md
    reflection_log.md
    /versions/
      2026-03-10_v1.md
      2026-03-17_v2.md
      2026-03-24_v3.md
    /change_logs/
      2026-03-17_vs_2026-03-10.md
      2026-03-24_vs_2026-03-17.md
```

This is only one example. The exact implementation can vary, but the principle is consistent: preserve history and make comparison easy.

---

## Suggested Template for the Master Thesis File

```markdown
# [Ticker] Master Thesis

## Current stance
Buy / Add / Hold / Trim / Sell / Avoid / Watch

## Business summary

## Current thesis

## Why the market may be wrong

## Key assumptions
1.
2.
3.
4.
5.

## Bull case

## Bear case

## Key risks

## Valuation summary
- Bear case:
- Base case:
- Bull case:
- Current price:
- Margin of safety:

## Scorecard
- Business quality:
- Management trust:
- Competitive strength:
- Growth durability:
- Margin durability:
- Balance sheet strength:
- Capital allocation quality:
- Valuation attractiveness:
- Downside risk:
- Overall conviction:

## Current action view

## What would change my mind
```

---

## Suggested Template for Each Versioned Review

```markdown
# [Ticker] Review - [Date]

## Review metadata
- Review type:
- Review trigger:
- Prior version compared:

## Fresh analysis
### Business summary

### Current context

### Thesis

### Bear case

### Key assumptions
1.
2.
3.
4.
5.

### Valuation
- Bear case:
- Base case:
- Bull case:
- Current price:
- Expected return:

### Risk assessment

### Confidence level

### Provisional stance

## Comparison with prior versions
### New facts

### Changed interpretation

### Corrected mistakes

### Noise

### Thesis strengthening signals

### Thesis weakening signals

### Thesis breaking signals

## What changed overall?
- Thesis:
- Fair value:
- Risk:
- Confidence:

## Action decision
- Action:
- Reason:
- What would reverse this decision:

## Reflection
- What I got right:
- What I missed:
- Where I may be biased:
- Would I still believe this from a blank page:
```

---

## Suggested Template for the Trigger Dashboard

```markdown
# [Ticker] Trigger Dashboard

## Buy triggers
- Price below [range] while thesis intact
- Expected return above [threshold]
- No balance sheet deterioration
- Confidence score at or above [threshold]

## Add triggers
- Existing thesis intact
- New evidence strengthens conviction
- Position size below [limit]
- Risk/reward improved

## Hold triggers
- Thesis intact
- Fair value approximately matches price
- No material deterioration

## Trim triggers
- Price above fair value range
- Position size exceeds [limit]
- Upside meaningfully reduced

## Sell triggers
- Thesis broken
- Assumption [X] invalidated
- Management credibility breaks
- Debt/risk becomes unacceptable
- Better capital allocation alternatives dominate

## Event-driven review triggers
- Earnings release
- Guidance cut or raise
- Management change
- Major acquisition/divestiture
- Credit event
- Regulatory action
- Large price move
```

---

## Comparison Logic Across Multiple Days or Versions

The original idea described Day 1, Day 2, Day 3, Day 4 comparisons. That logic is useful, but it should be made more systematic.

### Day 1

Create the first full thesis.

### Day 2

Create a second full or partial review, depending on cadence and event significance.

### Day 3

Create the third review and compare not only with Day 2, but also with Day 1.

This matters because short-term changes can obscure longer-term drift. For example:

- Day 2 may look similar to Day 3,
- but Day 3 may be materially weaker than Day 1.

### Day 4 and beyond

Compare the latest version with:

- the immediately prior version,
- the original thesis,
- and any major turning-point versions.

### Why compare against multiple points

A stock story often changes slowly. Sequential comparisons may miss cumulative deterioration or cumulative improvement.

For that reason, each review should include:

- **delta vs last review**,
- **delta vs original thesis**,
- and, when relevant, **delta vs last major event**.

This captures both recent movement and long-horizon drift.

---

## Notable Operating Principles

The following points are especially important and should be treated as rules of the system.

## 1. Do not confuse report production with insight

A long report is not inherently useful. The value of the process lies in better judgment, not more words.

## 2. Separate facts from interpretation

For example:

- “Revenue growth slowed from 20% to 12%” is a fact.
- “The growth engine is weakening” is an interpretation.
- “Sell the stock” is an action.

These are three different layers and must not be collapsed into one statement.

## 3. Define what counts as “new”

Not every new data point matters. A relevant new fact is one that changes intrinsic value, thesis probability, or downside risk.

## 4. Make non-action explicit

“No action” is a valid action. It should still be recorded with a reason.

## 5. Record what would change your mind

A thesis without falsification conditions is too vague. Every review should state what evidence would strengthen, weaken, or break the thesis.

## 6. Use consistent language and scales

Changing terminology every week makes comparison harder. The structure and rating scales should remain stable.

## 7. Allow for genuine thesis reversal

The process should not be optimized to preserve continuity. It should be optimized to detect truth. Sometimes the right conclusion is that the original thesis was wrong.

## 8. Do not let price alone drive conviction

Price movement matters because it affects expected return, not because it automatically validates or invalidates the thesis.

## 9. Use event-driven deep reviews for major developments

Not all review cycles need the same depth. A quiet period can justify a light review. A major earnings miss or regulatory event may justify a full rewrite.

## 10. Reflection is mandatory, not optional

Without reflection, the process becomes reporting. With reflection, it becomes learning.

---

## Common Failure Modes

A good process should also identify how it can fail.

### Failure Mode 1: Daily rewriting with no real new information

This creates the illusion of rigor while amplifying noise.

### Failure Mode 2: Copying prior reports forward

This preserves old assumptions by inertia.

### Failure Mode 3: No predefined action thresholds

Without thresholds, every review depends too much on mood.

### Failure Mode 4: Excessive complexity

A system that is too detailed to maintain will be abandoned. The process should be detailed enough to be rigorous, but simple enough to sustain.

### Failure Mode 5: Score inflation

If most categories always score 4 or 5, the scoring system loses informational value.

### Failure Mode 6: Treating all risks as equal

The system should distinguish between manageable noise and thesis-breaking deterioration.

### Failure Mode 7: Reflecting only on the stock, not the analyst

The greatest value often comes from identifying your own recurring analytical errors.

---

## Implementation Guidance

A practical implementation should aim for consistency, not perfection.

### Start simple

Begin with:

- one master thesis,
- one versioned review template,
- one change log,
- and one trigger dashboard.

You can add more sophistication later.

### Be explicit about your investing horizon

Action thresholds should depend on the intended holding period and strategy style. A long-term quality investor and a short-term catalyst investor should not use identical thresholds.

### Standardize the review process

Use the same structure every time so comparisons are reliable.

### Preserve raw prior versions

Do not overwrite old files. Historical accuracy is one of the main assets of the process.

### Keep the action memo short

The analysis can be detailed, but the action conclusion should be direct and operational.

### Review the reflection log periodically

Every few months, review not only the stocks but also the pattern of your own judgments.

---

## Example End-of-Review Decision Logic

A useful closing decision framework is:

1. What changed in the business?
2. What changed in valuation?
3. What changed in risk?
4. What changed in confidence?
5. Did any predefined trigger fire?
6. If not, why is no action still correct?

This logic helps ensure that every review ends with a disciplined decision rather than an ambiguous summary.

---

## The Ultimate Objective of the System

The ultimate objective of this system is not to predict every stock move correctly. No process can do that consistently.

The real objective is to build a reliable mechanism for:

- preserving your reasoning,
- updating it honestly,
- distinguishing noise from signal,
- taking action only when justified,
- and continuously improving your judgment.

A strong self-reflection stock analysis loop should make you better at three things over time:

1. identifying what matters,
2. knowing when it matters enough to act,
3. and recognizing how your own thinking changes under uncertainty.

That is why the best description of this process is not “a reporting workflow.” It is a **living thesis management and decision framework**.

---

## Summary

A strong self-reflection stock analysis loop should include:

- a repeatable workflow,
- versioned analysis records,
- structured comparisons,
- explicit action thresholds,
- a clear set of deliverables,
- a scoring framework,
- and a mandatory reflection layer.

The process works best when it produces not just documents, but decisions with traceable reasoning.

The simplest guiding rule is:

> Take action only when intrinsic value, thesis probability, downside risk, expected return, or portfolio risk has changed materially.

Everything else should be recorded, interpreted, and learned from—but not automatically traded.
