from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from app.agents import get_default_skill_registry
from app.agents.mcp import DefaultMcpConnectionTester
from app.core.config import get_settings, reset_settings_cache
from app.db.session import get_engine, get_session_factory, init_db, reset_db_caches
from app.schemas.agent import AgentCreate
from app.schemas.balance import BalanceCreate
from app.schemas.mcp_server import McpServerCreate, McpServerTransport
from app.schemas.output_schema import OutputSchemaDraftCreate, OutputSchemaKind
from app.schemas.portfolio import PortfolioCreate
from app.schemas.position import PositionCreate
from app.schemas.skill import SkillDraftCreate, SkillToolDefinitionWrite
from app.schemas.text_template import TextTemplateCreate
from app.schemas.workflow import WorkflowCreate
from app.services.agent_service import AgentService
from app.services.balance_service import BalanceService
from app.services.mcp_server_service import McpServerService
from app.services.output_schema_service import OutputSchemaService
from app.services.portfolio_service import PortfolioService
from app.services.position_service import PositionService
from app.services.quote_provider import DeterministicQuoteProvider
from app.services.report_service import ReportService
from app.services.skill_service import SkillService
from app.services.text_template_service import TextTemplateService
from app.services.workflow_service import WorkflowService

STARTER_PORTFOLIO_SLUG = "mag7_core"
STARTER_PORTFOLIO_NAME = "Mag7 Core Portfolio"
STARTER_BALANCE_LABEL = "Core Cash"
STARTER_WORKFLOW_KEY = "stock_analysis"
STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS = (
    "financials_analyst",
    "news_analyst",
    "market_analyst",
    "industry_analyst",
    "economy_analyst",
    "price_analyst",
    "position_reader",
    "history_reader",
)
STOCK_ANALYSIS_SYNTHESIZER_KEY = "decision_synthesizer"
STOCK_ANALYSIS_NOTE_SCHEMA_KEY = "stock_analysis_note"
TRADING_DECISION_SCHEMA_KEY = "trading_decision"
STOCK_ANALYSIS_SKILL_KEY = "stock_analysis_tools"
STOCK_ANALYSIS_MCP_SERVER_KEY = "stock_analysis_data"
STOCK_ANALYSIS_REFERENCE_MCP_COMMAND = "python3 -m app.agents.mcp.stock_analysis_reference_server"
STOCK_ANALYSIS_REFERENCE_TOOL_KEYS = (
    "ledger.stock_analysis.market_snapshot",
    "ledger.stock_analysis.price_history",
    "ledger.stock_analysis.position_inventory",
    "ledger.stock_analysis.report_lookup",
    "ledger.stock_analysis.market_context",
)
STARTER_TEMPLATE_NAMES = (
    "Mag7 Portfolio Snapshot",
    "Mag7 Ticker Review",
)
MAG7_PORTFOLIO_TEMPLATE_CONTENT = (
    "# Mag7 Portfolio Snapshot\n\n"
    "Portfolio: {{portfolios.mag7_core.name}}\n"
    "Base currency: {{portfolios.mag7_core.base_currency}}\n"
    "Positions:\n{{portfolios.mag7_core.positions}}"
)
MAG7_TICKER_TEMPLATE_CONTENT = (
    "Ticker: {{inputs.ticker}}\n"
    "Portfolio: {{portfolios.by_slug(inputs.portfolio_slug).name}}\n"
    "Quantity: {{portfolios.by_slug(inputs.portfolio_slug).positions."
    "by_symbol(inputs.ticker).quantity}}\n"
    "Tagged prior: {{reports.by_tag(inputs.analysis_tag).latest.name}}\n"
    "Latest ticker analysis: {{reports.latest(inputs.ticker).content}}"
)
MAG7_COMPANIES = (
    {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "quantity": "40.00000000",
        "averageCost": "185.50000000",
        "reportSlug": "aapl_seed_report",
        "reportTag": "aapl_loop",
    },
    {
        "symbol": "MSFT",
        "name": "Microsoft Corporation",
        "quantity": "28.00000000",
        "averageCost": "410.00000000",
        "reportSlug": "msft_seed_report",
        "reportTag": "msft_loop",
    },
    {
        "symbol": "NVDA",
        "name": "NVIDIA Corporation",
        "quantity": "24.00000000",
        "averageCost": "101.50000000",
        "reportSlug": "nvda_seed_report",
        "reportTag": "nvda_loop",
    },
    {
        "symbol": "AMZN",
        "name": "Amazon.com, Inc.",
        "quantity": "18.00000000",
        "averageCost": "175.00000000",
        "reportSlug": "amzn_seed_report",
        "reportTag": "amzn_loop",
    },
    {
        "symbol": "GOOGL",
        "name": "Alphabet Inc.",
        "quantity": "20.00000000",
        "averageCost": "168.00000000",
        "reportSlug": "googl_seed_report",
        "reportTag": "googl_loop",
    },
    {
        "symbol": "META",
        "name": "Meta Platforms, Inc.",
        "quantity": "14.00000000",
        "averageCost": "485.00000000",
        "reportSlug": "meta_seed_report",
        "reportTag": "meta_loop",
    },
    {
        "symbol": "TSLA",
        "name": "Tesla, Inc.",
        "quantity": "16.00000000",
        "averageCost": "205.00000000",
        "reportSlug": "tsla_seed_report",
        "reportTag": "tsla_loop",
    },
)


@dataclass(frozen=True)
class ResetSeedSummary:
    portfolio_slugs: tuple[str, ...]
    template_names: tuple[str, ...]
    output_schema_keys: tuple[str, ...]
    skill_keys: tuple[str, ...]
    mcp_server_keys: tuple[str, ...]
    agent_keys: tuple[str, ...]
    report_slugs: tuple[str, ...]
    workflow_keys: tuple[str, ...]


def _resolve_database_url(database_url: str | None) -> str:
    return database_url or get_settings().database_url


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _validate_target_database(database_url: str) -> URL:
    target_url = make_url(database_url)
    if target_url.get_backend_name() not in {"postgresql", "postgres"}:
        raise RuntimeError("Reset-and-seed requires a PostgreSQL database URL.")
    if not target_url.database or target_url.database == "postgres":
        raise RuntimeError("Refusing to wipe the admin postgres database.")
    return target_url


def recreate_database(database_url: str) -> None:
    target_url = _validate_target_database(database_url)
    admin_url = target_url.set(database="postgres")
    database_name = target_url.database or ""

    try:
        get_engine(database_url).dispose()
    finally:
        reset_db_caches()
        reset_settings_cache()

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
    try:
        with admin_engine.connect() as connection:
            connection.execute(
                text(f"DROP DATABASE IF EXISTS {_quote_identifier(database_name)} WITH (FORCE)")
            )
            connection.execute(text(f"CREATE DATABASE {_quote_identifier(database_name)}"))
    finally:
        admin_engine.dispose()
        reset_db_caches()
        reset_settings_cache()


def stock_analysis_workflow_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "horizon_days": {"type": "integer"},
        },
        "required": ["ticker", "horizon_days"],
        "additionalProperties": False,
    }


def stock_analysis_note_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "signal": {"type": "string"},
        },
        "required": ["summary", "signal"],
        "additionalProperties": False,
    }


def trading_decision_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
            "confidence": {"type": "number"},
            "rationale": {"type": "string"},
            "price_targets": {"type": "array", "items": {"type": "number"}},
            "risks": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["action", "confidence", "rationale", "price_targets", "risks"],
        "additionalProperties": False,
    }


def _stock_analysis_agent_prompt(key: str) -> str:
    prompts = {
        "financials_analyst": (
            "Act like an investment research analyst. Focus on earnings quality, "
            "profitability, cash flow resilience, and capital allocation. Summarize "
            "the strongest financial signal and one caveat."
        ),
        "news_analyst": (
            "Act like a verified news researcher. Focus on the latest company-specific "
            "developments and sentiment. Summarize the most decision-relevant catalyst "
            "and one uncertainty."
        ),
        "market_analyst": (
            "Act like a market strategist. Focus on current market regime, momentum, "
            "and price context. Summarize what the market is implying right now."
        ),
        "industry_analyst": (
            "Act like a sector analyst. Focus on competitive positioning and market "
            "structure. Summarize whether the company is outperforming or lagging its "
            "peer context."
        ),
        "economy_analyst": (
            "Act like a macro strategist. Focus on rates, consumer demand, growth "
            "sensitivity, and macro backdrop in decision-ready language."
        ),
        "price_analyst": (
            "Act like a technical analyst. Focus on recent price trend, support and "
            "resistance, and time-horizon momentum. Summarize the setup with a clear bias."
        ),
        "position_reader": (
            "Act like a portfolio analyst. Focus on how the ticker already sits inside "
            "the portfolio. Summarize exposure, concentration, and the practical "
            "implication for sizing."
        ),
        "history_reader": (
            "Act like a market historian. Focus on the available historical range and "
            "volatility. Summarize the historical context that matters for the decision horizon."
        ),
    }
    return prompts[key]


def _stock_analysis_agent_payload(key: str, *, budget_usd: str = "0.05000000") -> dict[str, Any]:
    return {
        "key": key,
        "name": key.replace("_", " ").title(),
        "description": f"Seeded stock-analysis agent for {key}.",
        "model": "openai:gpt-5.4-mini",
        "systemPrompt": _stock_analysis_agent_prompt(key),
        "inputSchema": stock_analysis_workflow_input_schema(),
        "outputSchemaKey": STOCK_ANALYSIS_NOTE_SCHEMA_KEY,
        "skills": [{"skillKey": STOCK_ANALYSIS_SKILL_KEY}],
        "mcpServers": [{"mcpServerKey": STOCK_ANALYSIS_MCP_SERVER_KEY}],
        "budgetUsd": budget_usd,
        "streaming": False,
    }


def _stock_analysis_synthesizer_payload() -> dict[str, Any]:
    return {
        "key": STOCK_ANALYSIS_SYNTHESIZER_KEY,
        "name": "Decision Synthesizer",
        "description": "Combines seeded stock-analysis notes into a TradingDecision.",
        "model": "openai:gpt-5.4-mini",
        "systemPrompt": (
            "Synthesize the analyst notes into a single trading decision. Weigh signal quality, "
            "portfolio context, and macro risk, then return a concise rationale "
            "with explicit risks."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                key: stock_analysis_note_schema() for key in STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS
            },
            "required": list(STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS),
            "additionalProperties": False,
        },
        "outputSchemaKey": TRADING_DECISION_SCHEMA_KEY,
        "skills": [{"skillKey": STOCK_ANALYSIS_SKILL_KEY}],
        "mcpServers": [{"mcpServerKey": STOCK_ANALYSIS_MCP_SERVER_KEY}],
        "budgetUsd": "0.10000000",
        "streaming": False,
    }


def _create_and_activate_output_schema(
    service: OutputSchemaService,
    *,
    key: str,
    name: str,
    description: str,
    json_schema: dict[str, Any],
) -> str:
    draft = service.create_draft(
        OutputSchemaDraftCreate(
            key=key,
            kind=OutputSchemaKind.STANDALONE,
            name=name,
            description=description,
            json_schema=json_schema,
        )
    )
    return service.activate(draft.id).key


def _create_and_activate_skill(service: SkillService) -> str:
    draft = service.create_draft(
        SkillDraftCreate(
            key=STOCK_ANALYSIS_SKILL_KEY,
            name="Stock Analysis Tools",
            description="Seeded stock-analysis skill bundle.",
            tool_definitions=[
                SkillToolDefinitionWrite(tool=tool_key)
                for tool_key in STOCK_ANALYSIS_REFERENCE_TOOL_KEYS
            ],
        )
    )
    return service.activate(draft.id).key


def _create_and_activate_mcp_server(service: McpServerService) -> str:
    draft = service.create_draft(
        McpServerCreate(
            key=STOCK_ANALYSIS_MCP_SERVER_KEY,
            name="Stock Analysis Data",
            description="Seeded stock-analysis MCP server boundary.",
            transport=McpServerTransport.STDIO,
            command="python3",
            args=[
                "-m",
                "app.agents.mcp.stock_analysis_reference_server",
            ],
            env={},
            enabled=True,
        )
    )
    return service.activate(draft.id).key


def _workflow_payload() -> dict[str, Any]:
    return {
        "key": STARTER_WORKFLOW_KEY,
        "name": "Stock Analysis",
        "description": "Seeded Mag7 stock-analysis workflow.",
        "inputSchema": stock_analysis_workflow_input_schema(),
        "steps": [
            {
                "index": 1,
                "agents": [
                    {
                        "agentKey": key,
                        "slot": key,
                        "wiring": {
                            "ticker": {"from": "input", "path": "ticker"},
                            "horizon_days": {"from": "input", "path": "horizon_days"},
                        },
                    }
                    for key in STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS
                ],
            }
        ],
        "outputSpec": {
            "kind": "agent",
            "agentKey": STOCK_ANALYSIS_SYNTHESIZER_KEY,
            "wiring": {
                key: {"from": "step", "stepIndex": 1, "slot": key}
                for key in STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS
            },
        },
    }


def _build_seed_report_content(symbol: str, company_name: str) -> str:
    return (
        f"# {symbol} Seed Analysis\n\n"
        f"{company_name} remains part of the seeded Mag7 workflow context. "
        "This report exists so the stock-analysis experience has persisted "
        "company-specific context for financial and news lookup steps."
    )


def seed_initial_data(database_url: str | None = None) -> ResetSeedSummary:
    resolved_database_url = _resolve_database_url(database_url)
    session_factory = get_session_factory(resolved_database_url)

    with session_factory() as session:
        portfolio_service = PortfolioService(session)
        balance_service = BalanceService(session)
        position_service = PositionService(session, DeterministicQuoteProvider())
        template_service = TextTemplateService(session)
        report_service = ReportService(session)
        workflow_service = WorkflowService(session)
        output_schema_service = OutputSchemaService(session)
        skill_registry = get_default_skill_registry()
        connection_tester = DefaultMcpConnectionTester()
        skill_service = SkillService(session, skill_registry)
        mcp_server_service = McpServerService(session, connection_tester)
        agent_service = AgentService(session, skill_registry, connection_tester)

        portfolio = portfolio_service.create_portfolio(
            PortfolioCreate(
                name=STARTER_PORTFOLIO_NAME,
                slug=STARTER_PORTFOLIO_SLUG,
                description=(
                    "Seeded Magnificent 7 portfolio for the starter stock-analysis experience."
                ),
                base_currency="USD",
            )
        )
        balance_service.create_balance(
            portfolio.id,
            BalanceCreate.model_validate(
                {
                    "label": STARTER_BALANCE_LABEL,
                    "amount": "250000.00",
                    "operationType": "DEPOSIT",
                }
            ),
        )
        for company in MAG7_COMPANIES:
            position_service.create_position(
                portfolio.id,
                PositionCreate.model_validate(
                    {
                        "symbol": company["symbol"],
                        "name": company["name"],
                        "quantity": company["quantity"],
                        "averageCost": company["averageCost"],
                    }
                ),
            )

        templates = (
            template_service.create_template(
                TextTemplateCreate(
                    name=STARTER_TEMPLATE_NAMES[0],
                    content=MAG7_PORTFOLIO_TEMPLATE_CONTENT,
                )
            ),
            template_service.create_template(
                TextTemplateCreate(
                    name=STARTER_TEMPLATE_NAMES[1],
                    content=MAG7_TICKER_TEMPLATE_CONTENT,
                )
            ),
        )

        report_slugs: list[str] = []
        for company in MAG7_COMPANIES:
            report = report_service.create_external_report(
                name=f"{company['symbol']} Seed Analysis",
                slug=company["reportSlug"],
                content=_build_seed_report_content(company["symbol"], company["name"]),
                metadata={
                    "author": "Seeded Mag7 Workspace",
                    "tags": ["mag7", "seed", company["reportTag"]],
                    "analysis": {
                        "ticker": company["symbol"],
                        "portfolioSlug": STARTER_PORTFOLIO_SLUG,
                        "reviewType": "fundamental",
                    },
                },
            )
            report_slugs.append(report.slug)

        output_schema_keys = (
            _create_and_activate_output_schema(
                output_schema_service,
                key=STOCK_ANALYSIS_NOTE_SCHEMA_KEY,
                name="Stock Analysis Note",
                description="Seeded stock-analysis note output schema.",
                json_schema=stock_analysis_note_schema(),
            ),
            _create_and_activate_output_schema(
                output_schema_service,
                key=TRADING_DECISION_SCHEMA_KEY,
                name="Trading Decision",
                description="Seeded trading decision output schema.",
                json_schema=trading_decision_schema(),
            ),
        )
        skill_keys = (_create_and_activate_skill(skill_service),)
        mcp_server_keys = (_create_and_activate_mcp_server(mcp_server_service),)

        agent_keys = [
            agent_service.create_agent(
                AgentCreate.model_validate(_stock_analysis_agent_payload(key))
            ).key
            for key in STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS
        ]
        agent_keys.append(
            agent_service.create_agent(
                AgentCreate.model_validate(_stock_analysis_synthesizer_payload())
            ).key
        )
        workflow = workflow_service.create_workflow(
            WorkflowCreate.model_validate(_workflow_payload())
        )

        return ResetSeedSummary(
            portfolio_slugs=(portfolio.slug,),
            template_names=tuple(template.name for template in templates),
            output_schema_keys=output_schema_keys,
            skill_keys=skill_keys,
            mcp_server_keys=mcp_server_keys,
            agent_keys=tuple(agent_keys),
            report_slugs=tuple(report_slugs),
            workflow_keys=(workflow.key,),
        )


def reset_and_seed_database(database_url: str | None = None) -> ResetSeedSummary:
    resolved_database_url = _resolve_database_url(database_url)
    recreate_database(resolved_database_url)
    init_db(resolved_database_url)
    return seed_initial_data(resolved_database_url)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset the Ledger application database and seed starter data."
    )
    parser.add_argument("--database-url", default=None, help="Explicit PostgreSQL database URL.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation for the destructive reset.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if not args.yes:
        raise SystemExit("Refusing to wipe the database without --yes.")

    summary = reset_and_seed_database(args.database_url)
    print("Reset complete.")
    print(f"Portfolios: {', '.join(summary.portfolio_slugs)}")
    print(f"Templates: {', '.join(summary.template_names)}")
    print(f"Reports: {', '.join(summary.report_slugs)}")
    print(f"Workflows: {', '.join(summary.workflow_keys)}")
    print(f"Output schemas: {', '.join(summary.output_schema_keys)}")
    print(f"Skills: {', '.join(summary.skill_keys)}")
    print(f"MCP servers: {', '.join(summary.mcp_server_keys)}")
    print(f"Agents: {', '.join(summary.agent_keys)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
