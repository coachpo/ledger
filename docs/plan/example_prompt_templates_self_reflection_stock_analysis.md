# Example Prompt Templates For Self-Reflection Stock Analysis

## Template 1: Initial Thesis With Reflection

### Use case tags
- initial review
- reflection
- two-step

### Fresh instructions
Produce a fresh stock analysis in strict JSON. Focus on business summary, current context, thesis, bear case, assumptions, valuation, risk, confidence, scorecard, and provisional action.

### Fresh input
Analyze `{{portfolio.name}}` position context for `{{position.AAPL}}` and `{{stock.AAPL}}`. Include key assumptions and a provisional action.

### Compare instructions
Compare the fresh analysis to prior versions. Return strict JSON with comparison, decision, and reflection.

### Compare input
Use the latest thesis `{{version:latest.decision.reason}}` and the fresh analysis payload. Explain delta vs last, delta vs origin, classify change items, decide whether to trade now, and include reflection fields for what got right, what was missed, possible biases, blank-page check, and next review watchpoints.

## Template 2: Event-Driven Review With Reflection

### Use case tags
- event review
- earnings
- reflection
- two-step

### Fresh instructions
Produce a fresh event-driven stock analysis in strict JSON. Emphasize the new fact pattern, valuation implications, risks, scorecard changes, and provisional action.

### Fresh input
Review the latest catalyst for `{{stock.MSFT}}` in portfolio `{{portfolio.name}}`. If a prior response matters, insert a concrete response placeholder such as `{{response.<UUID>}}` before execution.

### Compare instructions
Compare the fresh event analysis against the prior thesis and return strict JSON with comparison, decision, and reflection.

### Compare input
Determine whether the latest event is noise, a thesis update, or actionable. Include reversal conditions, explicit action level, possible biases, and next review watchpoints.
