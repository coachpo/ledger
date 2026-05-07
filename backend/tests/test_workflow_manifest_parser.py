from __future__ import annotations

import re
from typing import Literal, cast

import pytest
from pydantic import Field, StrictInt, ValidationError, field_validator

from app.schemas.common import CamelModel
from app.schemas.workflow_manifest import WorkflowManifest, WorkflowManifestDiagnostic
from app.services.agent_manifest_parser import parse_agent_manifest
from app.services.workflow_manifest_parser import parse_workflow_manifest

GENERIC_PLATFORM_MODEL_CONNECTION_SETUP: dict[str, str] = {
    "key": "platform_graph_local_gpt54_mini",
    "baseUrl": "http://192.168.1.222:8087/v1",
    "modelId": "gpt-5.4-mini",
    "reasoningEffort": "medium",
    "apiStyle": "responses",
}

GENERIC_PLATFORM_AGENT_MANIFEST_SOURCES: dict[str, str] = {
    "market_analyst": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: market_analyst
  name: Market Analyst
  description: Produces a market technical report for the fixed Platform Graph Demo workflow.
spec:
  modelConnection: platform_graph_local_gpt54_mini
  systemPrompt: >
    Call granted Ledger market data, quote, history, OHLCV, and indicator tools
    instead of inventing market prices or indicator values. Disclose tool
    warnings, empty payloads, stale data, and missing provider coverage as data
    quality or provider limitations. Return the complete structured market
    analyst report for the supplied ticker and date; do not return partial
    patches.
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
  outputSchema: platform_graph_analyst_report@1
  capabilities:
    - platform_graph_market_data@1
  budgetUsd: "0.25"
""",
    "social_analyst": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: social_analyst
  name: Social Analyst
  description: Produces a social sentiment report for the fixed Platform Graph Demo workflow.
spec:
  modelConnection: platform_graph_local_gpt54_mini
  systemPrompt: >
    Call granted Ledger news tools instead of inventing articles, posts, or
    sentiment readings, then synthesize social sentiment only from returned news
    and insider-data payloads. Disclose tool warnings, empty payloads, stale or
    missing provider coverage, and that no direct social feed or social sentiment
    tool exists. Return the complete structured social sentiment analyst report
    for the supplied ticker and date; do not return partial patches.
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
  outputSchema: platform_graph_analyst_report@1
  capabilities:
    - platform_graph_news@1
  budgetUsd: "0.25"
""",
    "news_analyst": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: news_analyst
  name: News Analyst
  description: Produces a news report for the fixed Platform Graph Demo workflow.
spec:
  modelConnection: platform_graph_local_gpt54_mini
  systemPrompt: >
    Call granted Ledger company, global, query news, and insider-data tools
    instead of inventing articles or events. Disclose warnings, empty payloads,
    stale data, and missing provider coverage as data quality or provider
    limitations. Return the complete structured news analyst report for the
    supplied ticker and date; do not return partial patches.
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
  outputSchema: platform_graph_analyst_report@1
  capabilities:
    - platform_graph_news@1
  budgetUsd: "0.25"
""",
    "fundamentals_analyst": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: fundamentals_analyst
  name: Fundamentals Analyst
  description: Produces a fundamentals report for the fixed Platform Graph Demo workflow.
spec:
  modelConnection: platform_graph_local_gpt54_mini
  systemPrompt: >
    Call granted Ledger fundamentals and statement-data tools instead of
    inventing metrics or filings. Treat returned statements and ratios as the
    only source for fundamentals. Disclose warnings, empty payloads, stale data,
    and missing provider coverage as data quality or
    provider limitations. Return the complete structured fundamentals analyst
    report for the supplied ticker and date; do not return partial patches.
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
  outputSchema: platform_graph_analyst_report@1
  capabilities:
    - platform_graph_fundamentals@1
  budgetUsd: "0.25"
""",
    "bull_researcher": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: bull_researcher
  name: Bull Researcher
  description: Advances the bullish side of a bounded investment debate.
spec:
  modelConnection: platform_graph_local_gpt54_mini
  systemPrompt: >
    Call granted Ledger report lookup tools when stored research context is
    needed instead of inventing prior reports. Disclose unavailable reports or
    missing provider data. Return JSON with exactly one top-level key, nextState,
    containing the complete updated investment debate state, including
    analystReports, bullCase, bearCase, and debateHistory. Do not include
    priorState or return partial patches.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      priorState:
        type: object
        title: Prior debate state
        description: Current debate state passed into this turn.
        additionalProperties: true
      marketReport:
        type: object
        title: Market report
        description: Structured output from the market analyst.
        additionalProperties: true
      socialSentimentReport:
        type: object
        title: Social sentiment report
        description: Structured output from the social analyst.
        additionalProperties: true
      newsReport:
        type: object
        title: News report
        description: Structured output from the news analyst.
        additionalProperties: true
      fundamentalsReport:
        type: object
        title: Fundamentals report
        description: Structured output from the fundamentals analyst.
        additionalProperties: true
    required: [priorState]
  outputSchema: platform_graph_investment_debate_transition@1
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
  modelConnection: platform_graph_local_gpt54_mini
  systemPrompt: >
    Call granted Ledger report lookup tools when stored research context is
    needed instead of inventing prior reports. Disclose unavailable reports or
    missing provider data. Return JSON with exactly one top-level key, nextState,
    containing the complete updated investment debate state, including
    analystReports, bullCase, bearCase, and debateHistory. Do not include
    priorState or return partial patches.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      priorState:
        type: object
        title: Prior debate state
        description: Current debate state passed into this turn.
        additionalProperties: true
    required: [priorState]
  outputSchema: platform_graph_investment_debate_transition@1
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
  modelConnection: platform_graph_local_gpt54_mini
  systemPrompt: >
    Call granted Ledger report lookup tools when stored context is needed, and
    disclose unavailable reports or missing provider data. Produce a complete
    research plan with recommendation, thesis, and debateSummary from the full
    debate state. Do not return debate-state patches, omit required fields, or
    present live trading instructions.
  inputSchema:
    type: object
    title: Research manager input
    description: Debate state and ticker context for the research manager turn.
    additionalProperties: false
    properties:
      debateState:
        type: object
        title: Debate state
        description: Complete investment debate state after the bounded rounds.
        additionalProperties: true
      ticker:
        type: string
        title: Ticker
        description: Ticker symbol under review.
    required: [debateState, ticker]
  outputSchema: platform_graph_research_plan@1
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
  modelConnection: platform_graph_local_gpt54_mini
  systemPrompt: >
    Call granted Ledger positions tools to inspect portfolio exposure instead of
    assuming holdings. Disclose missing portfolio data or unavailable positions
    lookup results. Return a complete trader proposal with action, rationale, and
    sizingNotes from the research plan and portfolio context. Keep the proposal
    research-only; do not place orders or imply live execution.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      researchPlan:
        type: object
        title: Research plan
        description: Research manager output used for the trader proposal.
        additionalProperties: true
      portfolioId:
        type: string
        title: Portfolio ID
        description: Portfolio identifier used for position context.
    required: [researchPlan, portfolioId]
  outputSchema: platform_graph_trader_proposal@1
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
  modelConnection: platform_graph_local_gpt54_mini
  systemPrompt: >
    Call granted Ledger report lookup tools when stored context is needed, and
    disclose unavailable reports or missing provider data. Return JSON with
    exactly one top-level key, nextState, containing the complete updated risk
    debate state, including researchPlan, traderProposal, aggressiveCase,
    neutralCase, conservativeCase, and debateHistory. Do not include priorState
    or return partial patches.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      priorState:
        type: object
        title: Prior debate state
        description: Current debate state passed into this turn.
        additionalProperties: true
      researchPlan:
        type: object
        title: Research plan
        description: Research manager output used for the risk debate.
        additionalProperties: true
      traderProposal:
        type: object
        title: Trader proposal
        description: Trader output used for the risk debate.
        additionalProperties: true
    required: [priorState, researchPlan, traderProposal]
  outputSchema: platform_graph_risk_debate_transition@1
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
  modelConnection: platform_graph_local_gpt54_mini
  systemPrompt: >
    Call granted Ledger report lookup tools when stored context is needed, and
    disclose unavailable reports or missing provider data. Return JSON with
    exactly one top-level key, nextState, containing the complete updated risk
    debate state, including researchPlan, traderProposal, aggressiveCase,
    neutralCase, conservativeCase, and debateHistory. Do not include priorState
    or return partial patches.
  inputSchema:
    type: object
    title: Neutral risk input
    description: Prior risk debate state for the neutral risk turn.
    additionalProperties: false
    properties:
      priorState:
        type: object
        title: Prior debate state
        description: Current debate state passed into this turn.
        additionalProperties: true
    required: [priorState]
  outputSchema: platform_graph_risk_debate_transition@1
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
  modelConnection: platform_graph_local_gpt54_mini
  systemPrompt: >
    Call granted Ledger report lookup tools when stored context is needed, and
    disclose unavailable reports or missing provider data. Return JSON with
    exactly one top-level key, nextState, containing the complete updated risk
    debate state, including researchPlan, traderProposal, aggressiveCase,
    neutralCase, conservativeCase, and debateHistory. Do not include priorState
    or return partial patches.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      priorState:
        type: object
        title: Prior debate state
        description: Current debate state passed into this turn.
        additionalProperties: true
    required: [priorState]
  outputSchema: platform_graph_risk_debate_transition@1
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
  modelConnection: platform_graph_local_gpt54_mini
  systemPrompt: >
    Call granted Ledger report lookup tools when stored context is needed, and
    disclose unavailable reports or missing provider data. Return the complete
    portfolio decision with action, rationale, riskSummary, and executionPlan
    from the final risk debate state. Keep the result research-only; do not
    place orders or imply live execution.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      riskState:
        type: object
        title: Risk debate state
        description: Final risk debate state used for the portfolio decision.
        additionalProperties: true
    required: [riskState]
  outputSchema: platform_graph_portfolio_decision@1
  capabilities:
    - ledger_reports@1
    - platform_graph_memory@1
  budgetUsd: "0.35"
""",
}

GENERIC_PLATFORM_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE = """apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: platform_graph_fixed_unrolled_review
  name: Platform Graph Demo Fixed Unrolled Review
  description: >
    Fixed Ledger approximation of the Platform Graph Demo analyst, debate, trader,
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

GENERIC_PLATFORM_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE = (
    "apiVersion: ledger.workflow/v1\n"
    """kind: Workflow
metadata:
  key: platform_graph_strict_sequential_review
  name: Platform Graph Demo Strict Sequential Review
  description: >
    Strict v1 Ledger approximation of the Platform Graph Demo topology with each
    analyst represented as an ordered single-agent step before debate, trader,
    risk, and portfolio-manager stages.
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
      additionalProperties: true
    initialRiskDebateState:
      type: object
      title: Initial risk debate state
      description: Seed state for the first risk debate turn.
      additionalProperties: true
  required: [ticker, asOfDate, portfolioId, initialInvestmentDebateState, initialRiskDebateState]
steps:
  - id: market_analysis
    agents:
      - slot: market_report
        uses: market_analyst@1
        with:
          ticker: ${{ inputs.ticker }}
          asOfDate: ${{ inputs.asOfDate }}
  - id: social_analysis
    agents:
      - slot: social_sentiment_report
        uses: social_analyst@1
        with:
          ticker: ${{ inputs.ticker }}
          asOfDate: ${{ inputs.asOfDate }}
  - id: news_analysis
    agents:
      - slot: news_report
        uses: news_analyst@1
        with:
          ticker: ${{ inputs.ticker }}
          asOfDate: ${{ inputs.asOfDate }}
  - id: fundamentals_analysis
    agents:
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
          marketReport: ${{ steps.market_analysis.outputs.market_report }}
          socialSentimentReport: ${{ steps.social_analysis.outputs.social_sentiment_report }}
          newsReport: ${{ steps.news_analysis.outputs.news_report }}
          fundamentalsReport: ${{ steps.fundamentals_analysis.outputs.fundamentals_report }}
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
)

GENERIC_PLATFORM_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE = (
    GENERIC_PLATFORM_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE.replace(
        """key: platform_graph_fixed_unrolled_review
  name: Platform Graph Demo Fixed Unrolled Review
  description: >
    Fixed Ledger approximation of the Platform Graph Demo analyst, debate, trader,
    risk, and portfolio-manager topology.""",
        """key: platform_graph_practical_fanout_review
  name: Platform Graph Demo Practical Fanout Review
  description: >
    Practical v1 Ledger approximation of the Platform Graph Demo topology with
    analysts running concurrently inside one multi-agent step before ordered
    debate, trader, risk, and portfolio-manager stages.""",
        1,
    )
    .replace(
        """      description: Seed state for the first investment debate turn.
""",
        """      description: Seed state for the first investment debate turn.
      additionalProperties: true
""",
        1,
    )
    .replace(
        """      description: Seed state for the first risk debate turn.
""",
        """      description: Seed state for the first risk debate turn.
      additionalProperties: true
""",
        1,
    )
)

GENERIC_PLATFORM_V2_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE = (
    "apiVersion: ledger.workflow/v2\n"
    """kind: Workflow
metadata:
  key: platform_graph_v2_strict_sequential_review
  name: Platform Graph Demo V2 Strict Sequential Review
  description: >
    Platform Graph Demo v2 template with analysts evaluated as a strict ordered chain,
    bounded investment and risk debate loops, trader review, portfolio decision,
    and post-run memory.
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
    portfolioSlug:
      type: string
      title: Portfolio slug
      description: Optional portfolio slug stored with the memory artifact.
    horizonDays:
      type: integer
      title: Horizon days
      description: Optional horizon stored with the memory artifact.
    benchmarkSymbol:
      type: string
      title: Benchmark symbol
      description: Optional benchmark symbol for later memory resolution.
    initialInvestmentDebateState:
      type: object
      title: Initial investment debate state
      description: Seed state for the bounded investment debate loop.
      additionalProperties: true
    initialRiskDebateState:
      type: object
      title: Initial risk debate state
      description: Seed state for the bounded risk debate loop.
      additionalProperties: true
  required: [ticker, asOfDate, portfolioId, initialInvestmentDebateState, initialRiskDebateState]
flow:
  kind: sequence
  id: platform_graph_review
  nodes:
    - kind: step
      id: market_analysis
      slot: market_report
      uses: market_analyst@1
      with:
        ticker: ${{ inputs.ticker }}
        asOfDate: ${{ inputs.asOfDate }}
    - kind: step
      id: social_analysis
      slot: social_sentiment_report
      uses: social_analyst@1
      with:
        ticker: ${{ inputs.ticker }}
        asOfDate: ${{ inputs.asOfDate }}
    - kind: step
      id: news_analysis
      slot: news_report
      uses: news_analyst@1
      with:
        ticker: ${{ inputs.ticker }}
        asOfDate: ${{ inputs.asOfDate }}
    - kind: step
      id: fundamentals_analysis
      slot: fundamentals_report
      uses: fundamentals_analyst@1
      with:
        ticker: ${{ inputs.ticker }}
        asOfDate: ${{ inputs.asOfDate }}
    - kind: loop
      id: investment_debate_loop
      maxIterations: 2
      state:
        initialState: ${{ inputs.initialInvestmentDebateState }}
      sequence:
        kind: sequence
        id: investment_debate_round
        nodes:
          - kind: step
            id: bull_research
            slot: bull
            uses: bull_researcher@1
            with:
              priorState: ${{ inputs.initialInvestmentDebateState }}
              marketReport: ${{ nodes.market_analysis.outputs.market_report }}
              socialSentimentReport: ${{ nodes.social_analysis.outputs.social_sentiment_report }}
              newsReport: ${{ nodes.news_analysis.outputs.news_report }}
              fundamentalsReport: ${{ nodes.fundamentals_analysis.outputs.fundamentals_report }}
          - kind: step
            id: bear_research
            slot: bear
            uses: bear_researcher@1
            with:
              priorState: ${{ nodes.bull_research.outputs.bull.nextState }}
    - kind: step
      id: research_manager
      slot: research_plan
      uses: research_manager@1
      with:
        debateState: ${{ nodes.investment_debate_loop.outputs.bear.nextState }}
        ticker: ${{ inputs.ticker }}
    - kind: step
      id: trader
      slot: trader_proposal
      uses: trader@1
      with:
        researchPlan: ${{ nodes.research_manager.outputs.research_plan }}
        portfolioId: ${{ inputs.portfolioId }}
    - kind: loop
      id: risk_debate_loop
      maxIterations: 2
      state:
        initialState: ${{ inputs.initialRiskDebateState }}
      sequence:
        kind: sequence
        id: risk_debate_round
        nodes:
          - kind: step
            id: aggressive_risk
            slot: aggressive
            uses: aggressive_risk_analyst@1
            with:
              priorState: ${{ inputs.initialRiskDebateState }}
              researchPlan: ${{ nodes.research_manager.outputs.research_plan }}
              traderProposal: ${{ nodes.trader.outputs.trader_proposal }}
          - kind: step
            id: neutral_risk
            slot: neutral
            uses: neutral_risk_analyst@1
            with:
              priorState: ${{ nodes.aggressive_risk.outputs.aggressive.nextState }}
          - kind: step
            id: conservative_risk
            slot: conservative
            uses: conservative_risk_analyst@1
            with:
              priorState: ${{ nodes.neutral_risk.outputs.neutral.nextState }}
    - kind: step
      id: portfolio_manager
      slot: decision
      uses: portfolio_manager@1
      with:
        riskState: ${{ nodes.risk_debate_loop.outputs.conservative.nextState }}
output:
  from: ${{ nodes.platform_graph_review.outputs.decision }}
postRunMemory:
  enabled: true
  source:
    ticker: ${{ inputs.ticker }}
    action: ${{ nodes.portfolio_manager.outputs.decision.action }}
    rationale: ${{ nodes.portfolio_manager.outputs.decision.rationale }}
    riskSummary: ${{ nodes.portfolio_manager.outputs.decision.riskSummary }}
    executionPlan: ${{ nodes.portfolio_manager.outputs.decision.executionPlan }}
    portfolioSlug: ${{ inputs.portfolioSlug }}
    horizonDays: ${{ inputs.horizonDays }}
    decisionSummary: ${{ nodes.portfolio_manager.outputs.decision.rationale }}
  benchmarkSymbol: ${{ inputs.benchmarkSymbol }}
"""
)

GENERIC_PLATFORM_V2_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE = (
    "apiVersion: ledger.workflow/v2\n"
    """kind: Workflow
metadata:
  key: platform_graph_v2_practical_fanout_review
  name: Platform Graph Demo V2 Practical Fanout Review
  description: >
    Platform Graph Demo v2 template with analyst roles fanning out concurrently before
    bounded investment and risk debate loops, trader review, portfolio decision,
    and post-run memory.
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
    portfolioSlug:
      type: string
      title: Portfolio slug
      description: Optional portfolio slug stored with the memory artifact.
    horizonDays:
      type: integer
      title: Horizon days
      description: Optional horizon stored with the memory artifact.
    benchmarkSymbol:
      type: string
      title: Benchmark symbol
      description: Optional benchmark symbol for later memory resolution.
    initialInvestmentDebateState:
      type: object
      title: Initial investment debate state
      description: Seed state for the bounded investment debate loop.
      additionalProperties: true
    initialRiskDebateState:
      type: object
      title: Initial risk debate state
      description: Seed state for the bounded risk debate loop.
      additionalProperties: true
  required: [ticker, asOfDate, portfolioId, initialInvestmentDebateState, initialRiskDebateState]
flow:
  kind: sequence
  id: platform_graph_review
  nodes:
    - kind: fanout
      id: analyst_fanout
      branches:
        - id: market
          node:
            kind: step
            id: market_analysis
            slot: market_report
            uses: market_analyst@1
            with:
              ticker: ${{ inputs.ticker }}
              asOfDate: ${{ inputs.asOfDate }}
        - id: social
          node:
            kind: step
            id: social_analysis
            slot: social_sentiment_report
            uses: social_analyst@1
            with:
              ticker: ${{ inputs.ticker }}
              asOfDate: ${{ inputs.asOfDate }}
        - id: news
          node:
            kind: step
            id: news_analysis
            slot: news_report
            uses: news_analyst@1
            with:
              ticker: ${{ inputs.ticker }}
              asOfDate: ${{ inputs.asOfDate }}
        - id: fundamentals
          node:
            kind: step
            id: fundamentals_analysis
            slot: fundamentals_report
            uses: fundamentals_analyst@1
            with:
              ticker: ${{ inputs.ticker }}
              asOfDate: ${{ inputs.asOfDate }}
    - kind: loop
      id: investment_debate_loop
      maxIterations: 2
      state:
        initialState: ${{ inputs.initialInvestmentDebateState }}
      sequence:
        kind: sequence
        id: investment_debate_round
        nodes:
          - kind: step
            id: bull_research
            slot: bull
            uses: bull_researcher@1
            with:
              priorState: ${{ inputs.initialInvestmentDebateState }}
              marketReport: ${{ nodes.analyst_fanout.outputs.market_report }}
              socialSentimentReport: ${{ nodes.analyst_fanout.outputs.social_sentiment_report }}
              newsReport: ${{ nodes.analyst_fanout.outputs.news_report }}
              fundamentalsReport: ${{ nodes.analyst_fanout.outputs.fundamentals_report }}
          - kind: step
            id: bear_research
            slot: bear
            uses: bear_researcher@1
            with:
              priorState: ${{ nodes.bull_research.outputs.bull.nextState }}
    - kind: step
      id: research_manager
      slot: research_plan
      uses: research_manager@1
      with:
        debateState: ${{ nodes.investment_debate_loop.outputs.bear.nextState }}
        ticker: ${{ inputs.ticker }}
    - kind: step
      id: trader
      slot: trader_proposal
      uses: trader@1
      with:
        researchPlan: ${{ nodes.research_manager.outputs.research_plan }}
        portfolioId: ${{ inputs.portfolioId }}
    - kind: loop
      id: risk_debate_loop
      maxIterations: 2
      state:
        initialState: ${{ inputs.initialRiskDebateState }}
      sequence:
        kind: sequence
        id: risk_debate_round
        nodes:
          - kind: step
            id: aggressive_risk
            slot: aggressive
            uses: aggressive_risk_analyst@1
            with:
              priorState: ${{ inputs.initialRiskDebateState }}
              researchPlan: ${{ nodes.research_manager.outputs.research_plan }}
              traderProposal: ${{ nodes.trader.outputs.trader_proposal }}
          - kind: step
            id: neutral_risk
            slot: neutral
            uses: neutral_risk_analyst@1
            with:
              priorState: ${{ nodes.aggressive_risk.outputs.aggressive.nextState }}
          - kind: step
            id: conservative_risk
            slot: conservative
            uses: conservative_risk_analyst@1
            with:
              priorState: ${{ nodes.neutral_risk.outputs.neutral.nextState }}
    - kind: step
      id: portfolio_manager
      slot: decision
      uses: portfolio_manager@1
      with:
        riskState: ${{ nodes.risk_debate_loop.outputs.conservative.nextState }}
output:
  from: ${{ nodes.platform_graph_review.outputs.decision }}
postRunMemory:
  enabled: true
  source:
    ticker: ${{ inputs.ticker }}
    action: ${{ nodes.portfolio_manager.outputs.decision.action }}
    rationale: ${{ nodes.portfolio_manager.outputs.decision.rationale }}
    riskSummary: ${{ nodes.portfolio_manager.outputs.decision.riskSummary }}
    executionPlan: ${{ nodes.portfolio_manager.outputs.decision.executionPlan }}
    portfolioSlug: ${{ inputs.portfolioSlug }}
    horizonDays: ${{ inputs.horizonDays }}
    decisionSummary: ${{ nodes.portfolio_manager.outputs.decision.rationale }}
  benchmarkSymbol: ${{ inputs.benchmarkSymbol }}
"""
)

__all__ = [
    "GENERIC_PLATFORM_MODEL_CONNECTION_SETUP",
    "GENERIC_PLATFORM_AGENT_MANIFEST_SOURCES",
    "GENERIC_PLATFORM_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE",
    "GENERIC_PLATFORM_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE",
    "GENERIC_PLATFORM_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE",
    "GENERIC_PLATFORM_V2_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE",
    "GENERIC_PLATFORM_V2_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE",
]

_EXACT_VERSION_REF_RE = re.compile(r"^[a-z][a-z0-9_]{0,119}@[1-9][0-9]*$")
_RAW_SECRET_TEXT_RE = re.compile(
    r"(?i)"
    + r"(api[_-]?key\s*[:=]|bearer\s+[A-Za-z0-9._~-]+|"
    + r"sk-[A-Za-z0-9_-]{10,}|secret\s*[:=]|token\s*[:=])"
)
_GENERIC_PLATFORM_ANALYST_AGENT_REFS = [
    "market_analyst@1",
    "social_analyst@1",
    "news_analyst@1",
    "fundamentals_analyst@1",
]
_GENERIC_PLATFORM_DEBATE_AND_DECISION_STEP_IDS = [
    "bull_research_round_1",
    "bear_research_round_1",
    "bull_research_round_2",
    "bear_research_round_2",
    "research_manager",
    "trader",
    "aggressive_risk_round_1",
    "neutral_risk_round_1",
    "conservative_risk_round_1",
    "portfolio_manager",
]


def _required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


class _DemoAnalystReports(CamelModel):
    market_report: str
    social_sentiment_report: str
    news_report: str
    fundamentals_report: str

    @field_validator(
        "market_report",
        "social_sentiment_report",
        "news_report",
        "fundamentals_report",
        mode="before",
    )
    @classmethod
    def validate_reports(cls, value: object) -> str:
        return _required_text(value, field_name="Analyst report")


class _DemoInvestmentDebateState(CamelModel):
    analyst_reports: _DemoAnalystReports
    bull_case: str
    bear_case: str
    debate_history: list[str]


class _DemoResearchPlan(CamelModel):
    recommendation: Literal["buy", "hold", "sell"]
    thesis: str
    debate_summary: str

    @field_validator("thesis", "debate_summary", mode="before")
    @classmethod
    def validate_text_fields(cls, value: object) -> str:
        return _required_text(value, field_name="Research plan field")


class _DemoTraderProposal(CamelModel):
    action: Literal["buy", "hold", "sell"]
    rationale: str
    sizing_notes: str

    @field_validator("rationale", "sizing_notes", mode="before")
    @classmethod
    def validate_text_fields(cls, value: object) -> str:
        return _required_text(value, field_name="Trader proposal field")


class _DemoRiskDebateState(CamelModel):
    research_plan: _DemoResearchPlan
    trader_proposal: _DemoTraderProposal
    aggressive_case: str
    neutral_case: str
    conservative_case: str
    debate_history: list[str]


class _DemoPortfolioDecision(CamelModel):
    action: Literal["buy", "hold", "sell"]
    rationale: str
    risk_summary: str
    execution_plan: str

    @field_validator("rationale", "risk_summary", "execution_plan", mode="before")
    @classmethod
    def validate_text_fields(cls, value: object) -> str:
        return _required_text(value, field_name="Portfolio decision field")


class _DemoInvestmentDebateTransition(CamelModel):
    next_state: _DemoInvestmentDebateState


class _DemoRiskDebateTransition(CamelModel):
    next_state: _DemoRiskDebateState


class _DemoInitialRoundConfig(CamelModel):
    investment_debate_rounds: StrictInt = Field(default=2, ge=1, le=5)
    risk_debate_rounds: StrictInt = Field(default=2, ge=1, le=5)


def _valid_manifest_source(*, uses: str = "research_agent@1") -> str:
    return f"""apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: market_review
  name: Market Review
  description: Runs research before producing the final slot output.
inputSchema:
  type: object
  properties:
    ticker:
      type: string
  required:
    - ticker
  additionalProperties: false
steps:
  - id: research
    agents:
      - slot: analysis
        uses: {uses}
        with:
          ticker: ${{{{ inputs.ticker }}}}
  - id: decision
    agents:
      - slot: final
        uses: decision_agent@2
        with:
          analysis: ${{{{ steps.research.outputs.analysis.summary }}}}
output:
  from: ${{{{ steps.decision.outputs.final }}}}
"""


def _single_diagnostic(source: str) -> WorkflowManifestDiagnostic:
    result = parse_workflow_manifest(source)

    assert result.manifest is None
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.severity == "error"
    assert diagnostic.path
    assert diagnostic.line is not None
    assert diagnostic.column is not None
    return diagnostic


def _analyst_reports_payload() -> dict[str, str]:
    return {
        "marketReport": "Market structure remains constructive.",
        "socialSentimentReport": "Social sentiment is balanced.",
        "newsReport": "Recent news flow is mixed.",
        "fundamentalsReport": "Fundamentals support the base case.",
    }


def _investment_debate_state_payload(
    *,
    bull_case: str = "Bull case favors upside.",
    bear_case: str = "Bear case highlights drawdown risk.",
) -> dict[str, object]:
    return {
        "analystReports": _analyst_reports_payload(),
        "bullCase": bull_case,
        "bearCase": bear_case,
        "debateHistory": ["Bull: margin expansion offsets valuation risk."],
    }


def _research_plan_payload() -> dict[str, str]:
    return {
        "recommendation": "hold",
        "thesis": "Wait for valuation confirmation before increasing exposure.",
        "debateSummary": "Bull and bear arguments are balanced.",
    }


def _trader_proposal_payload() -> dict[str, str]:
    return {
        "action": "hold",
        "rationale": "Current exposure is aligned with conviction.",
        "sizingNotes": "Do not add until risk/reward improves.",
    }


def _risk_debate_state_payload() -> dict[str, object]:
    return {
        "researchPlan": _research_plan_payload(),
        "traderProposal": _trader_proposal_payload(),
        "aggressiveCase": "Increase exposure on breakout confirmation.",
        "neutralCase": "Maintain the current position size.",
        "conservativeCase": "Trim if volatility rises.",
        "debateHistory": ["Neutral: current sizing best matches the evidence."],
    }


def test_platform_graph_contracts_validate_full_state_transitions_and_round_config() -> None:
    investment_transition = _DemoInvestmentDebateTransition.model_validate(
        {
            "nextState": _investment_debate_state_payload(
                bull_case="Bull case updated after the first unrolled round.",
                bear_case="",
            ),
        }
    )
    risk_transition = _DemoRiskDebateTransition.model_validate(
        {
            "nextState": _risk_debate_state_payload()
            | {"neutralCase": "Maintain exposure after risk review."},
        }
    )
    decision = _DemoPortfolioDecision.model_validate(
        {
            "action": "hold",
            "rationale": "Research and risk views agree on patience.",
            "riskSummary": "Downside risks are contained but not absent.",
            "executionPlan": "No trade for the initial portfolio decision.",
        }
    )
    round_config = _DemoInitialRoundConfig.model_validate(
        {"investmentDebateRounds": 2, "riskDebateRounds": 3}
    )

    investment_dump = investment_transition.model_dump(mode="json", by_alias=True)
    assert set(investment_dump) == {"nextState"}
    assert investment_dump["nextState"]["bullCase"] == (
        "Bull case updated after the first unrolled round."
    )
    assert risk_transition.next_state.neutral_case == "Maintain exposure after risk review."
    assert decision.action == "hold"
    assert round_config.model_dump(mode="json", by_alias=True) == {
        "investmentDebateRounds": 2,
        "riskDebateRounds": 3,
    }

    with pytest.raises(ValidationError) as investment_prior_exc:
        _ = _DemoInvestmentDebateTransition.model_validate(
            {
                "priorState": _investment_debate_state_payload(),
                "nextState": _investment_debate_state_payload(),
            }
        )
    assert any(
        error["type"] == "extra_forbidden" and error["loc"] == ("priorState",)
        for error in investment_prior_exc.value.errors()
    )

    with pytest.raises(ValidationError) as risk_prior_exc:
        _ = _DemoRiskDebateTransition.model_validate(
            {
                "priorState": _risk_debate_state_payload(),
                "nextState": _risk_debate_state_payload(),
            }
        )
    assert any(
        error["type"] == "extra_forbidden" and error["loc"] == ("priorState",)
        for error in risk_prior_exc.value.errors()
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"investmentDebateRounds": 0, "riskDebateRounds": 2},
        {"investmentDebateRounds": 2, "riskDebateRounds": 6},
        {"investmentDebateRounds": "2", "riskDebateRounds": 2},
    ],
)
def test_platform_graph_round_config_is_fixed_bounded_data(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _ = _DemoInitialRoundConfig.model_validate(payload)


def test_platform_graph_debate_transitions_reject_partial_or_patch_outputs() -> None:
    with pytest.raises(ValidationError) as partial_exc:
        _ = _DemoInvestmentDebateTransition.model_validate(
            {
                "nextState": {"bullCase": "Only the updated delta."},
            }
        )
    missing_fields = {
        str(error["loc"][-1]) for error in partial_exc.value.errors() if error["type"] == "missing"
    }
    assert {"analystReports", "bearCase", "debateHistory"} <= missing_fields

    with pytest.raises(ValidationError) as patch_exc:
        _ = _DemoRiskDebateTransition.model_validate(
            {
                "nextState": _risk_debate_state_payload()
                | {"patch": {"neutralCase": "Only a patch."}},
            }
        )
    extra_paths = {
        error["loc"] for error in patch_exc.value.errors() if error["type"] == "extra_forbidden"
    }
    assert ("nextState", "patch") in extra_paths


def test_platform_graph_contracts_do_not_weaken_manifest_validation() -> None:
    same_step_reference = _valid_manifest_source().replace(
        "${{ steps.research.outputs.analysis.summary }}",
        "${{ steps.decision.outputs.final.summary }}",
        1,
    )
    same_step_diagnostic = _single_diagnostic(same_step_reference)
    assert same_step_diagnostic.path == "steps[1].agents[0].with.analysis"
    assert "Step references must point to an earlier step" in same_step_diagnostic.message

    compiled_output_field = _valid_manifest_source().replace(
        "output:\n  from: ${{ steps.decision.outputs.final }}\n",
        "outputSpec:\n  kind: slot\n  stepIndex: 2\n  slot: final\n"
        + "output:\n  from: ${{ steps.decision.outputs.final }}\n",
        1,
    )
    compiled_field_diagnostic = _single_diagnostic(compiled_output_field)
    assert compiled_field_diagnostic.path == "outputSpec"
    assert "Extra inputs are not permitted" in compiled_field_diagnostic.message


def test_parse_valid_workflow_manifest_returns_typed_manifest() -> None:
    result = parse_workflow_manifest(_valid_manifest_source())

    assert result.diagnostics == []
    assert result.manifest is not None
    assert isinstance(result.manifest, WorkflowManifest)
    assert result.manifest.api_version == "ledger.workflow/v1"
    assert result.manifest.kind == "Workflow"
    assert result.manifest.metadata.key == "market_review"
    assert result.manifest.steps[0].id == "research"
    assert result.manifest.steps[0].agents[0].uses.key == "research_agent"
    assert result.manifest.steps[0].agents[0].uses.version == 1
    assert result.manifest.steps[1].agents[0].inputs["analysis"].step_id == "research"

    dumped = result.manifest.model_dump(mode="json", by_alias=True)
    assert dumped["apiVersion"] == "ledger.workflow/v1"
    assert dumped["steps"][0]["agents"][0]["uses"] == "research_agent@1"
    assert dumped["steps"][1]["agents"][0]["with"]["analysis"] == (
        "${{ steps.research.outputs.analysis.summary }}"
    )


def _valid_v2_manifest_source(*, flow: str, output_reference: str) -> str:
    return f"""apiVersion: ledger.workflow/v2
kind: Workflow
metadata:
  key: market_review_v2
  name: Market Review V2
inputSchema:
  type: object
  properties:
    ticker:
      type: string
flow:
{flow}
output:
  from: {output_reference}
"""


@pytest.mark.parametrize(
    ("flow", "output_reference", "expected_root_kind"),
    [
        (
            """  kind: step
  id: research
  slot: analysis
  uses: research_agent@1
  with:
    ticker: ${{ inputs.ticker }}""",
            "${{ nodes.research.outputs.analysis }}",
            "step",
        ),
        (
            """  kind: fanout
  id: analyst_fanout
  branches:
    - id: market
      node:
        kind: step
        id: market_analysis
        slot: analysis
        uses: market_agent@1
        with:
          ticker: ${{ inputs.ticker }}""",
            "${{ nodes.analyst_fanout.outputs.market }}",
            "fanout",
        ),
        (
            """  kind: fanout
  id: analyst_fanout
  branches:
    - id: market
      node:
        kind: step
        id: market_analysis
        slot: analysis
        uses: market_agent@1
        with:
          ticker: ${{ inputs.ticker }}""",
            "${{ nodes.analyst_fanout.outputs.analysis }}",
            "fanout",
        ),
        (
            """  kind: loop
  id: review_loop
  maxIterations: 2
  sequence:
    kind: sequence
    id: review_sequence
    nodes:
      - kind: step
        id: risk_review
        slot: risk
        uses: risk_agent@1
        with:
          ticker: ${{ inputs.ticker }}""",
            "${{ nodes.review_loop.outputs.risk }}",
            "loop",
        ),
        (
            """  kind: sequence
  id: root_sequence
  nodes:
    - kind: step
      id: research
      slot: analysis
      uses: research_agent@1
      with:
        ticker: ${{ inputs.ticker }}""",
            "${{ nodes.root_sequence.outputs.analysis }}",
            "sequence",
        ),
    ],
)
def test_parse_valid_v2_manifest_allows_each_root_node_kind(
    flow: str,
    output_reference: str,
    expected_root_kind: str,
) -> None:
    result = parse_workflow_manifest(
        _valid_v2_manifest_source(flow=flow, output_reference=output_reference)
    )

    assert result.diagnostics == []
    assert result.manifest is not None
    dumped = result.manifest.model_dump(mode="json", by_alias=True)
    assert dumped["apiVersion"] == "ledger.workflow/v2"
    assert dumped["flow"]["kind"] == expected_root_kind


@pytest.mark.parametrize(
    ("output_reference", "expected_message"),
    [
        ("${{ nodes.missing.outputs.analysis }}", "Node 'missing' was not found"),
        ("${{ nodes.research.outputs.missing }}", "Slot 'missing' was not found"),
    ],
)
def test_v2_root_step_output_rejects_unknown_refs_and_slots(
    output_reference: str,
    expected_message: str,
) -> None:
    diagnostic = _single_diagnostic(
        _valid_v2_manifest_source(
            flow="""  kind: step
  id: research
  slot: analysis
  uses: research_agent@1
  with:
    ticker: ${{ inputs.ticker }}""",
            output_reference=output_reference,
        )
    )

    assert diagnostic.path == "output.from"
    assert expected_message in diagnostic.message


def test_v2_root_step_inputs_reject_same_node_refs() -> None:
    diagnostic = _single_diagnostic(
        _valid_v2_manifest_source(
            flow="""  kind: step
  id: research
  slot: analysis
  uses: research_agent@1
  with:
    prior: ${{ nodes.research.outputs.analysis }}""",
            output_reference="${{ nodes.research.outputs.analysis }}",
        )
    )

    assert diagnostic.path == "flow.with.prior"
    assert "Node references must point to an earlier node" in diagnostic.message


def test_v2_sequence_inputs_reject_future_refs() -> None:
    diagnostic = _single_diagnostic(
        _valid_v2_manifest_source(
            flow="""  kind: sequence
  id: root_sequence
  nodes:
    - kind: step
      id: research
      slot: analysis
      uses: research_agent@1
      with:
        prior: ${{ nodes.decision.outputs.final }}
    - kind: step
      id: decision
      slot: final
      uses: decision_agent@1""",
            output_reference="${{ nodes.decision.outputs.final }}",
        )
    )

    assert diagnostic.path == "flow.nodes[0].with.prior"
    assert "Node references must point to an earlier node" in diagnostic.message


def test_v2_fanout_branch_inputs_reject_sibling_branch_refs() -> None:
    diagnostic = _single_diagnostic(
        _valid_v2_manifest_source(
            flow="""  kind: fanout
  id: analyst_fanout
  branches:
    - id: market
      node:
        kind: step
        id: market_analysis
        slot: market_report
        uses: market_agent@1
        with:
          ticker: ${{ inputs.ticker }}
    - id: news
      node:
        kind: step
        id: news_analysis
        slot: news_report
        uses: news_agent@1
        with:
          marketReport: ${{ nodes.market_analysis.outputs.market_report }}""",
            output_reference="${{ nodes.analyst_fanout.outputs.news_report }}",
        )
    )

    assert diagnostic.path == "flow.branches[1].node.with.marketReport"
    assert "Node references must point to an earlier node" in diagnostic.message


@pytest.mark.parametrize(
    ("flow", "expected_path", "expected_message"),
    [
        (
            """  kind: fanout
  id: analyst_fanout
  branches:
    - id: market
      node:
        kind: step
        id: market_analysis
        slot: analysis
        uses: market_agent@1
    - id: market
      node:
        kind: step
        id: news_analysis
        slot: news
        uses: news_agent@1""",
            "flow.branches[1].id",
            "Duplicate fanout branch id",
        ),
        (
            """  kind: sequence
  id: root_sequence
  nodes:
    - kind: step
      id: research
      slot: analysis
      uses: research_agent@1
    - kind: step
      id: research
      slot: final
      uses: decision_agent@1""",
            "flow.nodes[1].id",
            "Duplicate node id",
        ),
        (
            """  kind: sequence
  id: root_sequence
  nodes:
    - kind: step
      id: research
      slot: analysis
      uses: research_agent@1
    - kind: step
      id: decision
      slot: analysis
      uses: decision_agent@1""",
            "flow.nodes[1].slot",
            "Duplicate output slot name within the same sequence",
        ),
    ],
)
def test_v2_semantics_preserve_duplicate_diagnostics(
    flow: str,
    expected_path: str,
    expected_message: str,
) -> None:
    diagnostic = _single_diagnostic(
        _valid_v2_manifest_source(
            flow=flow,
            output_reference="${{ nodes.root_sequence.outputs.analysis }}",
        )
    )

    assert diagnostic.path == expected_path
    assert expected_message in diagnostic.message


def test_parser_rejects_malformed_yaml_with_location() -> None:
    diagnostic = _single_diagnostic(
        """apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: [broken
"""
    )

    assert diagnostic.path == "$"
    assert "Malformed YAML" in diagnostic.message


def test_parser_rejects_duplicate_yaml_keys_with_location() -> None:
    diagnostic = _single_diagnostic(
        """apiVersion: ledger.workflow/v1
apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: market_review
  name: Market Review
inputSchema:
  type: object
steps: []
output:
  from: ${{ steps.research.outputs.analysis }}
"""
    )

    assert diagnostic.path == "$"
    assert "Duplicate mapping key" in diagnostic.message


@pytest.mark.parametrize(
    ("source", "expected_message"),
    [
        (
            """apiVersion: ledger.workflow/v1
kind: Workflow
metadata: &metadata
  key: market_review
  name: Market Review
inputSchema:
  type: object
steps: []
output:
  from: ${{ steps.research.outputs.analysis }}
""",
            "YAML anchors are not supported",
        ),
        (
            """apiVersion: ledger.workflow/v1
kind: Workflow
metadata: *metadata
inputSchema:
  type: object
steps: []
output:
  from: ${{ steps.research.outputs.analysis }}
""",
            "YAML aliases are not supported",
        ),
        (
            """apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  <<: {key: market_review, name: Market Review}
inputSchema:
  type: object
steps: []
output:
  from: ${{ steps.research.outputs.analysis }}
""",
            "YAML merge keys are not supported",
        ),
    ],
)
def test_parser_rejects_unsupported_yaml_features(
    source: str,
    expected_message: str,
) -> None:
    result = parse_workflow_manifest(source)

    assert result.manifest is None
    assert any(expected_message in diagnostic.message for diagnostic in result.diagnostics)
    assert all(diagnostic.line is not None for diagnostic in result.diagnostics)
    assert all(diagnostic.column is not None for diagnostic in result.diagnostics)


@pytest.mark.parametrize(
    ("source", "expected_path", "expected_message"),
    [
        (
            _valid_manifest_source().replace("apiVersion: ledger.workflow/v1\n", "", 1),
            "apiVersion",
            "Field required",
        ),
        (
            _valid_manifest_source().replace("ledger.workflow/v1", "ledger.workflow/v2", 1),
            "apiVersion",
            "Input should be 'ledger.workflow/v1'",
        ),
        (
            _valid_manifest_source().replace("  name: Market Review\n", "", 1),
            "metadata.name",
            "Field required",
        ),
        (
            _valid_manifest_source().replace("  type: object\n", "  type: string\n", 1),
            "inputSchema",
            "inputSchema must be an object schema",
        ),
    ],
)
def test_parser_returns_schema_validation_diagnostics(
    source: str,
    expected_path: str,
    expected_message: str,
) -> None:
    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == expected_path
    assert expected_message in diagnostic.message


@pytest.mark.parametrize("uses", ["research_agent@latest", "research_agent", "research_agent@1.2"])
def test_parser_rejects_non_exact_agent_versions(uses: str) -> None:
    diagnostic = _single_diagnostic(_valid_manifest_source(uses=uses))

    assert diagnostic.path == "steps[0].agents[0].uses"
    assert "pin an exact numeric version" in diagnostic.message


def test_parser_rejects_duplicate_step_ids_and_slots_with_manifest_paths() -> None:
    duplicate_step = _valid_manifest_source().replace("  - id: decision", "  - id: research", 1)
    duplicate_step_diagnostic = _single_diagnostic(duplicate_step)

    assert duplicate_step_diagnostic.path == "steps[1].id"
    assert "Duplicate step id" in duplicate_step_diagnostic.message

    duplicate_slot = _valid_manifest_source().replace(
        "      - slot: analysis\n        uses: research_agent@1",
        "      - slot: analysis\n        uses: research_agent@1\n"
        + "      - slot: analysis\n        uses: review_agent@3",
        1,
    )
    duplicate_slot_diagnostic = _single_diagnostic(duplicate_slot)

    assert duplicate_slot_diagnostic.path == "steps[0].agents[1].slot"
    assert "Duplicate slot name within the same step" in duplicate_slot_diagnostic.message


def test_parser_rejects_invalid_step_references_and_optional_final_output() -> None:
    forward_reference = _valid_manifest_source().replace(
        "${{ steps.research.outputs.analysis.summary }}",
        "${{ steps.decision.outputs.final.summary }}",
    )
    forward_diagnostic = _single_diagnostic(forward_reference)

    assert forward_diagnostic.path == "steps[1].agents[0].with.analysis"
    assert "Step references must point to an earlier step" in forward_diagnostic.message

    optional_output = _valid_manifest_source().replace(
        "        uses: decision_agent@2",
        "        uses: decision_agent@2\n        optional: true",
    )
    optional_output_diagnostic = _single_diagnostic(optional_output)

    assert optional_output_diagnostic.path == "output.from"
    assert "Final output cannot reference an optional slot" in optional_output_diagnostic.message


def test_platform_graph_example_agent_manifests_parse_with_exact_numeric_pins() -> None:
    assert set(GENERIC_PLATFORM_AGENT_MANIFEST_SOURCES) == {
        "market_analyst",
        "social_analyst",
        "news_analyst",
        "fundamentals_analyst",
        "bull_researcher",
        "bear_researcher",
        "research_manager",
        "trader",
        "aggressive_risk_analyst",
        "neutral_risk_analyst",
        "conservative_risk_analyst",
        "portfolio_manager",
    }

    expected_capability_refs = {
        "market_analyst": ["platform_graph_market_data@1"],
        "social_analyst": ["platform_graph_news@1"],
        "news_analyst": ["platform_graph_news@1"],
        "fundamentals_analyst": ["platform_graph_fundamentals@1"],
        "bull_researcher": ["ledger_reports@1"],
        "bear_researcher": ["ledger_reports@1"],
        "research_manager": ["ledger_reports@1"],
        "trader": ["ledger_positions@1"],
        "aggressive_risk_analyst": ["ledger_reports@1"],
        "neutral_risk_analyst": ["ledger_reports@1"],
        "conservative_risk_analyst": ["ledger_reports@1"],
        "portfolio_manager": ["ledger_reports@1", "platform_graph_memory@1"],
    }
    expected_prompt_fragments = {
        "market_analyst": [
            "instead of inventing market prices",
            "data quality or provider limitations",
        ],
        "social_analyst": [
            "synthesize social sentiment only from returned news",
            "no direct social feed or social sentiment tool exists",
        ],
        "news_analyst": [
            "instead of inventing articles",
            "data quality or provider limitations",
        ],
        "fundamentals_analyst": [
            "instead of inventing metrics or filings",
            "data quality or provider limitations",
        ],
    }

    for role, source in GENERIC_PLATFORM_AGENT_MANIFEST_SOURCES.items():
        assert "skills:" not in source
        assert _RAW_SECRET_TEXT_RE.search(source) is None

        result = parse_agent_manifest(source)
        assert result.diagnostics == [], role
        assert result.manifest is not None
        assert result.manifest.metadata.key == role
        assert result.manifest.spec.output_schema.version == 1

        dumped = result.manifest.model_dump(mode="json", by_alias=True)
        spec = cast(dict[str, object], dumped["spec"])
        capability_refs = cast(list[object], spec["capabilities"])
        assert spec["modelConnection"] == GENERIC_PLATFORM_MODEL_CONNECTION_SETUP["key"]
        assert "skills" not in spec
        assert _EXACT_VERSION_REF_RE.fullmatch(str(spec["outputSchema"])) is not None
        assert all(
            _EXACT_VERSION_REF_RE.fullmatch(str(capability_ref)) is not None
            for capability_ref in capability_refs
        )
        assert [
            f"{capability.key}@{capability.version}"
            for capability in result.manifest.spec.capabilities
        ] == expected_capability_refs[role]
        for expected_fragment in expected_prompt_fragments.get(role, []):
            assert expected_fragment in result.manifest.spec.system_prompt


def test_platform_graph_fixed_unrolled_manifest_has_expected_topology() -> None:
    result = parse_workflow_manifest(GENERIC_PLATFORM_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE)

    assert result.diagnostics == []
    assert result.manifest is not None
    assert isinstance(result.manifest, WorkflowManifest)
    steps = result.manifest.steps
    assert [step.id for step in steps] == [
        "analyst_fanout",
        "bull_research_round_1",
        "bear_research_round_1",
        "bull_research_round_2",
        "bear_research_round_2",
        "research_manager",
        "trader",
        "aggressive_risk_round_1",
        "neutral_risk_round_1",
        "conservative_risk_round_1",
        "portfolio_manager",
    ]
    analyst_step = steps[0]
    assert [agent.slot for agent in analyst_step.agents] == [
        "market_report",
        "social_sentiment_report",
        "news_report",
        "fundamentals_report",
    ]
    assert all(
        reference.source == "inputs"
        for agent in analyst_step.agents
        for reference in agent.inputs.values()
    )
    assert [
        f"{agent.uses.key}@{agent.uses.version}" for step in steps for agent in step.agents
    ] == [
        "market_analyst@1",
        "social_analyst@1",
        "news_analyst@1",
        "fundamentals_analyst@1",
        "bull_researcher@1",
        "bear_researcher@1",
        "bull_researcher@1",
        "bear_researcher@1",
        "research_manager@1",
        "trader@1",
        "aggressive_risk_analyst@1",
        "neutral_risk_analyst@1",
        "conservative_risk_analyst@1",
        "portfolio_manager@1",
    ]
    debate_chain = [
        steps[1].agents[0].inputs["priorState"],
        steps[2].agents[0].inputs["priorState"],
        steps[3].agents[0].inputs["priorState"],
        steps[4].agents[0].inputs["priorState"],
        steps[7].agents[0].inputs["priorState"],
        steps[8].agents[0].inputs["priorState"],
        steps[9].agents[0].inputs["priorState"],
    ]
    assert [reference.source for reference in debate_chain] == [
        "inputs",
        "steps",
        "steps",
        "steps",
        "inputs",
        "steps",
        "steps",
    ]
    assert [reference.output_path for reference in debate_chain[1:4]] == [
        "nextState",
        "nextState",
        "nextState",
    ]
    assert [reference.output_path for reference in debate_chain[5:]] == [
        "nextState",
        "nextState",
    ]
    assert result.manifest.output.from_.step_id == "portfolio_manager"
    assert result.manifest.output.from_.slot == "decision"


@pytest.mark.parametrize(
    ("source", "expected_key"),
    [
        (
            GENERIC_PLATFORM_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE,
            "platform_graph_strict_sequential_review",
        ),
        (
            GENERIC_PLATFORM_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE,
            "platform_graph_practical_fanout_review",
        ),
    ],
)
def test_platform_graph_v1_review_examples_parse_with_workflow_api_version(
    source: str,
    expected_key: str,
) -> None:
    result = parse_workflow_manifest(source)

    assert result.diagnostics == []
    assert result.manifest is not None
    assert result.manifest.api_version == "ledger.workflow/v1"
    assert result.manifest.metadata.key == expected_key


def test_platform_graph_strict_sequential_manifest_orders_single_analyst_steps_before_debate() -> (
    None
):
    result = parse_workflow_manifest(
        GENERIC_PLATFORM_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE
    )

    assert result.diagnostics == []
    assert result.manifest is not None
    assert isinstance(result.manifest, WorkflowManifest)
    steps = result.manifest.steps
    analyst_steps = steps[:4]
    first_debate_step = steps[4]

    assert [step.id for step in analyst_steps] == [
        "market_analysis",
        "social_analysis",
        "news_analysis",
        "fundamentals_analysis",
    ]
    analyst_refs = [
        f"{step.agents[0].uses.key}@{step.agents[0].uses.version}" for step in analyst_steps
    ]
    assert [len(step.agents) for step in analyst_steps] == [1, 1, 1, 1]
    assert analyst_refs == _GENERIC_PLATFORM_ANALYST_AGENT_REFS
    assert [step.id for step in steps[4:]] == _GENERIC_PLATFORM_DEBATE_AND_DECISION_STEP_IDS
    assert first_debate_step.id == "bull_research_round_1"
    assert first_debate_step.agents[0].inputs["marketReport"].step_id == "market_analysis"
    assert first_debate_step.agents[0].inputs["socialSentimentReport"].step_id == "social_analysis"
    assert first_debate_step.agents[0].inputs["newsReport"].step_id == "news_analysis"
    assert first_debate_step.agents[0].inputs["fundamentalsReport"].step_id == (
        "fundamentals_analysis"
    )


def test_platform_graph_practical_fanout_manifest_keeps_single_analyst_fanout_before_debate() -> (
    None
):
    result = parse_workflow_manifest(
        GENERIC_PLATFORM_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE
    )

    assert result.diagnostics == []
    assert result.manifest is not None
    assert isinstance(result.manifest, WorkflowManifest)
    steps = result.manifest.steps
    analyst_step = steps[0]

    analyst_refs = [f"{agent.uses.key}@{agent.uses.version}" for agent in analyst_step.agents]
    assert analyst_step.id == "analyst_fanout"
    assert analyst_refs == _GENERIC_PLATFORM_ANALYST_AGENT_REFS
    assert [agent.slot for agent in analyst_step.agents] == [
        "market_report",
        "social_sentiment_report",
        "news_report",
        "fundamentals_report",
    ]
    assert all(
        reference.source == "inputs"
        for agent in analyst_step.agents
        for reference in agent.inputs.values()
    )
    assert [step.id for step in steps[1:]] == _GENERIC_PLATFORM_DEBATE_AND_DECISION_STEP_IDS
    assert steps[1].agents[0].inputs["marketReport"].step_id == "analyst_fanout"
    assert steps[1].agents[0].inputs["socialSentimentReport"].step_id == "analyst_fanout"
    assert steps[1].agents[0].inputs["newsReport"].step_id == "analyst_fanout"
    assert steps[1].agents[0].inputs["fundamentalsReport"].step_id == "analyst_fanout"


@pytest.mark.parametrize(
    ("source", "expected_key", "expected_analyst_node_kind"),
    [
        (
            GENERIC_PLATFORM_V2_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE,
            "platform_graph_v2_strict_sequential_review",
            "step",
        ),
        (
            GENERIC_PLATFORM_V2_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE,
            "platform_graph_v2_practical_fanout_review",
            "fanout",
        ),
    ],
)
def test_platform_graph_v2_review_examples_parse_with_bounded_loops_and_memory(
    source: str,
    expected_key: str,
    expected_analyst_node_kind: str,
) -> None:
    assert _RAW_SECRET_TEXT_RE.search(source) is None

    result = parse_workflow_manifest(source)

    assert result.diagnostics == []
    assert result.manifest is not None
    dumped = result.manifest.model_dump(mode="json", by_alias=True)
    flow = cast(dict[str, object], dumped["flow"])
    nodes = cast(list[dict[str, object]], flow["nodes"])
    loop_nodes = [node for node in nodes if node["kind"] == "loop"]

    assert dumped["apiVersion"] == "ledger.workflow/v2"
    assert dumped["metadata"]["key"] == expected_key
    assert nodes[0]["kind"] == expected_analyst_node_kind
    if expected_analyst_node_kind == "step":
        assert [node["id"] for node in nodes[:4]] == [
            "market_analysis",
            "social_analysis",
            "news_analysis",
            "fundamentals_analysis",
        ]
    else:
        assert cast(list[object], nodes[0]["branches"])
        assert len(cast(list[object], nodes[0]["branches"])) == 4
    assert [node["id"] for node in loop_nodes] == ["investment_debate_loop", "risk_debate_loop"]
    assert [node["maxIterations"] for node in loop_nodes] == [2, 2]
    assert dumped["postRunMemory"]["enabled"] is True
    assert dumped["postRunMemory"]["source"]["action"] == (
        "${{ nodes.portfolio_manager.outputs.decision.action }}"
    )
    assert dumped["postRunMemory"]["benchmarkSymbol"] == "${{ inputs.benchmarkSymbol }}"


def test_platform_graph_model_connection_setup_metadata_is_secret_free() -> None:
    assert GENERIC_PLATFORM_MODEL_CONNECTION_SETUP == {
        "key": "platform_graph_local_gpt54_mini",
        "baseUrl": "http://192.168.1.222:8087/v1",
        "modelId": "gpt-5.4-mini",
        "reasoningEffort": "medium",
        "apiStyle": "responses",
    }
    assert _RAW_SECRET_TEXT_RE.search(str(GENERIC_PLATFORM_MODEL_CONNECTION_SETUP)) is None


def test_platform_graph_fixed_unrolled_manifest_rejects_same_step_debate_refs() -> None:
    source = GENERIC_PLATFORM_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE.replace(
        "priorState: ${{ inputs.initialInvestmentDebateState }}",
        "priorState: ${{ steps.bull_research_round_1.outputs.bull.nextState }}",
        1,
    )

    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == "steps[1].agents[0].with.priorState"
    assert "Step references must point to an earlier step" in diagnostic.message


def test_platform_graph_fixed_unrolled_manifest_rejects_future_debate_refs() -> None:
    source = GENERIC_PLATFORM_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE.replace(
        "priorState: ${{ steps.bull_research_round_1.outputs.bull.nextState }}",
        "priorState: ${{ steps.bull_research_round_2.outputs.bull.nextState }}",
        1,
    )

    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == "steps[2].agents[0].with.priorState"
    assert "Step references must point to an earlier step" in diagnostic.message


def test_platform_graph_fixed_unrolled_manifest_rejects_same_step_analyst_refs() -> None:
    source = GENERIC_PLATFORM_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE.replace(
        "ticker: ${{ inputs.ticker }}",
        "ticker: ${{ steps.analyst_fanout.outputs.market_report }}",
        1,
    )

    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == "steps[0].agents[0].with.ticker"
    assert "Step references must point to an earlier step" in diagnostic.message
