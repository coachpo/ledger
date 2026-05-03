from __future__ import annotations

TRADINGAGENTS_MODEL_CONNECTION_SETUP: dict[str, str] = {
    "key": "tradingagents_local_gpt54_mini",
    "baseUrl": "http://192.168.1.222:8087/v1",
    "modelId": "gpt-5.4-mini",
    "reasoningEffort": "medium",
    "apiStyle": "responses",
}

TRADINGAGENTS_AGENT_MANIFEST_SOURCES: dict[str, str] = {
    "market_analyst": """apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: market_analyst
  name: Market Analyst
  description: Produces a market technical report for the fixed TradingAgents workflow.
spec:
  modelConnection: tradingagents_local_gpt54_mini
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
  modelConnection: tradingagents_local_gpt54_mini
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
  modelConnection: tradingagents_local_gpt54_mini
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
  modelConnection: tradingagents_local_gpt54_mini
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
  modelConnection: tradingagents_local_gpt54_mini
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
  modelConnection: tradingagents_local_gpt54_mini
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
  modelConnection: tradingagents_local_gpt54_mini
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
  modelConnection: tradingagents_local_gpt54_mini
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
  modelConnection: tradingagents_local_gpt54_mini
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
  modelConnection: tradingagents_local_gpt54_mini
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
  modelConnection: tradingagents_local_gpt54_mini
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
  modelConnection: tradingagents_local_gpt54_mini
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
  outputSchema: tradingagents_portfolio_decision@1
  capabilities:
    - ledger_reports@1
    - tradingagents_memory@1
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

TRADINGAGENTS_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE = """apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: tradingagents_strict_sequential_review
  name: TradingAgents Strict Sequential Review
  description: >
    Strict v1 Ledger approximation of the TradingAgents topology with each
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

TRADINGAGENTS_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE = (
    TRADINGAGENTS_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE.replace(
        """key: tradingagents_fixed_unrolled_review
  name: TradingAgents Fixed Unrolled Review
  description: >
    Fixed Ledger approximation of the TradingAgents analyst, debate, trader,
    risk, and portfolio-manager topology.""",
        """key: tradingagents_practical_fanout_review
  name: TradingAgents Practical Fanout Review
  description: >
    Practical v1 Ledger approximation of the TradingAgents topology with
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

TRADINGAGENTS_V2_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE = (
    "apiVersion: ledger.workflow/v2\n"
    """kind: Workflow
metadata:
  key: tradingagents_v2_strict_sequential_review
  name: TradingAgents V2 Strict Sequential Review
  description: >
    TradingAgents v2 template with analysts evaluated as a strict ordered chain,
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
  id: tradingagents_review
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
  from: ${{ nodes.tradingagents_review.outputs.decision }}
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

TRADINGAGENTS_V2_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE = (
    "apiVersion: ledger.workflow/v2\n"
    """kind: Workflow
metadata:
  key: tradingagents_v2_practical_fanout_review
  name: TradingAgents V2 Practical Fanout Review
  description: >
    TradingAgents v2 template with analyst roles fanning out concurrently before
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
  id: tradingagents_review
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
  from: ${{ nodes.tradingagents_review.outputs.decision }}
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
    "TRADINGAGENTS_MODEL_CONNECTION_SETUP",
    "TRADINGAGENTS_AGENT_MANIFEST_SOURCES",
    "TRADINGAGENTS_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE",
    "TRADINGAGENTS_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE",
    "TRADINGAGENTS_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE",
    "TRADINGAGENTS_V2_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE",
    "TRADINGAGENTS_V2_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE",
]
