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
  systemPrompt: Return a market analysis report for the supplied ticker and date.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      ticker:
        type: string
      asOfDate:
        type: string
    required: [ticker, asOfDate]
  outputSchema: tradingagents_analyst_report@1
  capabilities:
    - ledger_market_data@1
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
  systemPrompt: Return a social sentiment report for the supplied ticker and date.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      ticker:
        type: string
      asOfDate:
        type: string
    required: [ticker, asOfDate]
  outputSchema: tradingagents_analyst_report@1
  capabilities:
    - ledger_news@1
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
  systemPrompt: Return a news report for the supplied ticker and date.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      ticker:
        type: string
      asOfDate:
        type: string
    required: [ticker, asOfDate]
  outputSchema: tradingagents_analyst_report@1
  capabilities:
    - ledger_news@1
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
  systemPrompt: Return a fundamentals report for the supplied ticker and date.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      ticker:
        type: string
      asOfDate:
        type: string
    required: [ticker, asOfDate]
  outputSchema: tradingagents_analyst_report@1
  capabilities:
    - ledger_fundamentals@1
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
  systemPrompt: Accept priorState and return nextState for the bullish debate turn.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      priorState:
        type: object
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
  systemPrompt: Accept priorState and return nextState for the bearish debate turn.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      priorState:
        type: object
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
  systemPrompt: Produce full investment debate state or a final research plan.
  inputSchema:
    type: object
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
      portfolioId:
        type: string
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
  systemPrompt: Accept priorState and return nextState for the aggressive risk turn.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      priorState:
        type: object
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
  systemPrompt: Accept risk inputs or priorState and return full risk state.
  inputSchema:
    type: object
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
  systemPrompt: Accept priorState and return nextState for the conservative risk turn.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      priorState:
        type: object
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
    asOfDate:
      type: string
    portfolioId:
      type: string
    initialInvestmentDebateState:
      type: object
    initialRiskDebateState:
      type: object
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
