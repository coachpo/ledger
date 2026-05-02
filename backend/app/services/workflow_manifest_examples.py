from __future__ import annotations

TRADINGAGENTS_AGENT_MANIFEST_SOURCES: dict[str, str] = {
    "market_analyst": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: market_analyst
  name: Market Analyst
  description: Produces a market technical report for the fixed TradingAgents workflow.
spec:
  modelConnection: primary_openai
  systemPrompt: >
    Call granted quote, history, OHLCV, and indicator tools instead of inventing
    market prices. Disclose tool warnings or empty payloads as data quality or
    provider limitations in the market analysis report for the supplied ticker
    and date.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      ticker:
        type: string
        title: Ticker
        description: Ticker symbol to research, such as AAPL.
      asOfDate:
        type: string
        title: As of date
        description: Date used for the analysis snapshot.
    required: [ticker, asOfDate]
  outputSchema: tradingagents_analyst_report@1
  capabilities:
    - tradingagents_market_data@1
  budgetUsd: "0.25"
""",
    "social_analyst": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: social_analyst
  name: Social Analyst
  description: Produces a social sentiment report for the fixed TradingAgents workflow.
spec:
  modelConnection: primary_openai
  systemPrompt: >
    Call granted news tools instead of inventing articles, then synthesize
    social sentiment only from returned news. Disclose tool warnings, empty
    payloads, and that no direct social feed or social sentiment tool exists.
    Return a social sentiment report for the supplied ticker and date.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      ticker:
        type: string
        title: Ticker
        description: Ticker symbol to research, such as AAPL.
      asOfDate:
        type: string
        title: As of date
        description: Date used for the analysis snapshot.
    required: [ticker, asOfDate]
  outputSchema: tradingagents_analyst_report@1
  capabilities:
    - tradingagents_news@1
  budgetUsd: "0.25"
""",
    "news_analyst": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: news_analyst
  name: News Analyst
  description: Produces a news report for the fixed TradingAgents workflow.
spec:
  modelConnection: primary_openai
  systemPrompt: >
    Call granted company and global/query news tools instead of inventing
    articles. Disclose warnings or empty payloads as data quality or provider
    limitations in the news report for the supplied ticker and date.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      ticker:
        type: string
        title: Ticker
        description: Ticker symbol to research, such as AAPL.
      asOfDate:
        type: string
        title: As of date
        description: Date used for the analysis snapshot.
    required: [ticker, asOfDate]
  outputSchema: tradingagents_analyst_report@1
  capabilities:
    - tradingagents_news@1
  budgetUsd: "0.25"
""",
    "fundamentals_analyst": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: fundamentals_analyst
  name: Fundamentals Analyst
  description: Produces a fundamentals report for the fixed TradingAgents workflow.
spec:
  modelConnection: primary_openai
  systemPrompt: >
    Call granted fundamentals and statement tools instead of inventing metrics
    or filings. Disclose warnings or empty payloads as data quality or provider
    limitations in the fundamentals report for the supplied ticker and date.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      ticker:
        type: string
        title: Ticker
        description: Ticker symbol to research, such as AAPL.
      asOfDate:
        type: string
        title: As of date
        description: Date used for the analysis snapshot.
    required: [ticker, asOfDate]
  outputSchema: tradingagents_analyst_report@1
  capabilities:
    - tradingagents_fundamentals@1
  budgetUsd: "0.25"
""",
    "bull_researcher": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: bull_researcher
  name: Bull Researcher
  description: Advances the bullish side of a bounded investment debate.
spec:
  modelConnection: primary_openai
  systemPrompt: >
    Return JSON with exactly one top-level key, nextState, containing the complete
    updated investment debate state. Do not include priorState or return patches.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      priorState:
        type: object
        title: Prior debate state
        description: Current debate state passed into this turn.
    required: [priorState]
  outputSchema: tradingagents_investment_debate_transition@1
  capabilities:
    - ledger_reports@1
  budgetUsd: "0.30"
""",
    "bear_researcher": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: bear_researcher
  name: Bear Researcher
  description: Advances the bearish side of a bounded investment debate.
spec:
  modelConnection: primary_openai
  systemPrompt: >
    Return JSON with exactly one top-level key, nextState, containing the complete
    updated investment debate state. Do not include priorState or return patches.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      priorState:
        type: object
        title: Prior debate state
        description: Current debate state passed into this turn.
    required: [priorState]
  outputSchema: tradingagents_investment_debate_transition@1
  capabilities:
    - ledger_reports@1
  budgetUsd: "0.30"
""",
    "research_manager": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: research_manager
  name: Research Manager
  description: Seeds and summarizes the fixed investment debate.
spec:
  modelConnection: primary_openai
  systemPrompt: >
    Produce full investment debate state or a final research plan.
  inputSchema:
    type: object
    title: Research manager input
    description: Flexible state bundle for the research manager turn.
    additionalProperties: true
  outputSchema: tradingagents_research_plan@1
  capabilities:
    - ledger_reports@1
  budgetUsd: "0.35"
""",
    "trader": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: trader
  name: Trader
  description: Converts a research plan into a concrete trader proposal.
spec:
  modelConnection: primary_openai
  systemPrompt: Return a trader proposal from the research plan and portfolio context.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      researchPlan:
        type: object
        title: Research plan
        description: Research manager output used for the trader proposal.
      portfolioId:
        type: string
        title: Portfolio ID
        description: Portfolio identifier used for position context.
    required: [researchPlan, portfolioId]
  outputSchema: tradingagents_trader_proposal@1
  capabilities:
    - ledger_positions@1
  budgetUsd: "0.30"
""",
    "aggressive_risk_analyst": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: aggressive_risk_analyst
  name: Aggressive Risk Analyst
  description: Advances the aggressive side of a bounded risk debate.
spec:
  modelConnection: primary_openai
  systemPrompt: >
    Return JSON with exactly one top-level key, nextState, containing the complete
    updated risk debate state. Do not include priorState or return patches.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      priorState:
        type: object
        title: Prior debate state
        description: Current debate state passed into this turn.
    required: [priorState]
  outputSchema: tradingagents_risk_debate_transition@1
  capabilities:
    - ledger_reports@1
  budgetUsd: "0.25"
""",
    "neutral_risk_analyst": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: neutral_risk_analyst
  name: Neutral Risk Analyst
  description: Seeds or advances the neutral side of a bounded risk debate.
spec:
  modelConnection: primary_openai
  systemPrompt: >
    Return JSON with exactly one top-level key, nextState, containing the complete
    updated risk debate state. Do not include priorState or return patches.
  inputSchema:
    type: object
    title: Neutral risk input
    description: Flexible state bundle for the neutral risk turn.
    additionalProperties: true
  outputSchema: tradingagents_risk_debate_transition@1
  capabilities:
    - ledger_reports@1
  budgetUsd: "0.25"
""",
    "conservative_risk_analyst": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: conservative_risk_analyst
  name: Conservative Risk Analyst
  description: Advances the conservative side of a bounded risk debate.
spec:
  modelConnection: primary_openai
  systemPrompt: >
    Return JSON with exactly one top-level key, nextState, containing the complete
    updated risk debate state. Do not include priorState or return patches.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      priorState:
        type: object
        title: Prior debate state
        description: Current debate state passed into this turn.
    required: [priorState]
  outputSchema: tradingagents_risk_debate_transition@1
  capabilities:
    - ledger_reports@1
  budgetUsd: "0.25"
""",
    "portfolio_manager": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: portfolio_manager
  name: Portfolio Manager
  description: Produces the final portfolio decision from the risk debate state.
spec:
  modelConnection: primary_openai
  systemPrompt: Return the final portfolio decision.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      riskState:
        type: object
        title: Risk debate state
        description: Final risk debate state used for the portfolio decision.
    required: [riskState]
  outputSchema: tradingagents_portfolio_decision@1
  capabilities:
    - ledger_reports@1
  budgetUsd: "0.35"
""",
}

TRADINGAGENTS_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE = """apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: tradingagents_fixed_unrolled_review
  name: TradingAgents Fixed Unrolled Review
  description: >
    Fixed Ledger approximation of the TradingAgents analyst, debate, trader,
    risk, and portfolio-manager topology.
inputSchema:
  type: object
  additionalProperties: false
  properties:
    ticker:
      type: string
      title: Ticker
      description: Ticker symbol to research, such as AAPL.
    asOfDate:
      type: string
      title: As of date
      description: Date used for the analysis snapshot.
    portfolioId:
      type: string
      title: Portfolio ID
      description: Portfolio identifier used for position context.
    initialInvestmentDebateState:
      type: object
      title: Initial investment debate state
      description: Seed state for the first investment debate turn.
    initialRiskDebateState:
      type: object
      title: Initial risk debate state
      description: Seed state for the first risk debate turn.
  required: [ticker, asOfDate, portfolioId, initialInvestmentDebateState, initialRiskDebateState]
steps:
  - id: analyst_fanout
    agents:
      - slot: market_report
        uses: market_analyst@1
        with:
          ticker: ${{ inputs.ticker }}
          asOfDate: ${{ inputs.asOfDate }}
      - slot: social_sentiment_report
        uses: social_analyst@1
        with:
          ticker: ${{ inputs.ticker }}
          asOfDate: ${{ inputs.asOfDate }}
      - slot: news_report
        uses: news_analyst@1
        with:
          ticker: ${{ inputs.ticker }}
          asOfDate: ${{ inputs.asOfDate }}
      - slot: fundamentals_report
        uses: fundamentals_analyst@1
        with:
          ticker: ${{ inputs.ticker }}
          asOfDate: ${{ inputs.asOfDate }}
  - id: bull_research_round_1
    agents:
      - slot: bull
        uses: bull_researcher@1
        with:
          priorState: ${{ inputs.initialInvestmentDebateState }}
          marketReport: ${{ steps.analyst_fanout.outputs.market_report }}
          socialSentimentReport: ${{ steps.analyst_fanout.outputs.social_sentiment_report }}
          newsReport: ${{ steps.analyst_fanout.outputs.news_report }}
          fundamentalsReport: ${{ steps.analyst_fanout.outputs.fundamentals_report }}
  - id: bear_research_round_1
    agents:
      - slot: bear
        uses: bear_researcher@1
        with:
          priorState: ${{ steps.bull_research_round_1.outputs.bull.nextState }}
  - id: bull_research_round_2
    agents:
      - slot: bull
        uses: bull_researcher@1
        with:
          priorState: ${{ steps.bear_research_round_1.outputs.bear.nextState }}
  - id: bear_research_round_2
    agents:
      - slot: bear
        uses: bear_researcher@1
        with:
          priorState: ${{ steps.bull_research_round_2.outputs.bull.nextState }}
  - id: research_manager
    agents:
      - slot: research_plan
        uses: research_manager@1
        with:
          debateState: ${{ steps.bear_research_round_2.outputs.bear.nextState }}
          ticker: ${{ inputs.ticker }}
  - id: trader
    agents:
      - slot: trader_proposal
        uses: trader@1
        with:
          researchPlan: ${{ steps.research_manager.outputs.research_plan }}
          portfolioId: ${{ inputs.portfolioId }}
  - id: aggressive_risk_round_1
    agents:
      - slot: aggressive
        uses: aggressive_risk_analyst@1
        with:
          priorState: ${{ inputs.initialRiskDebateState }}
          researchPlan: ${{ steps.research_manager.outputs.research_plan }}
          traderProposal: ${{ steps.trader.outputs.trader_proposal }}
  - id: neutral_risk_round_1
    agents:
      - slot: neutral
        uses: neutral_risk_analyst@1
        with:
          priorState: ${{ steps.aggressive_risk_round_1.outputs.aggressive.nextState }}
  - id: conservative_risk_round_1
    agents:
      - slot: conservative
        uses: conservative_risk_analyst@1
        with:
          priorState: ${{ steps.neutral_risk_round_1.outputs.neutral.nextState }}
  - id: portfolio_manager
    agents:
      - slot: decision
        uses: portfolio_manager@1
        with:
          riskState: ${{ steps.conservative_risk_round_1.outputs.conservative.nextState }}
output:
  from: ${{ steps.portfolio_manager.outputs.decision }}
"""

__all__ = [
    "TRADINGAGENTS_AGENT_MANIFEST_SOURCES",
    "TRADINGAGENTS_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE",
]
