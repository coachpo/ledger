from __future__ import annotations

from sqlalchemy import select

from app.db.session import get_session_factory, init_db, reset_db_caches
from app.models.agent import Agent
from app.models.balance import Balance
from app.models.mcp_server import McpServer
from app.models.output_schema import OutputSchema
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.report import Report
from app.models.skill import Skill
from app.models.text_template import TextTemplate
from app.models.workflow import Workflow
from app.reset_seed import (
    MAG7_COMPANIES,
    STARTER_BALANCE_LABEL,
    STARTER_PORTFOLIO_SLUG,
    STARTER_TEMPLATE_NAMES,
    STARTER_WORKFLOW_KEY,
    STOCK_ANALYSIS_MCP_SERVER_KEY,
    STOCK_ANALYSIS_NOTE_SCHEMA_KEY,
    STOCK_ANALYSIS_SKILL_KEY,
    STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS,
    STOCK_ANALYSIS_SYNTHESIZER_KEY,
    TRADING_DECISION_SCHEMA_KEY,
    reset_and_seed_database,
)
from app.schemas.portfolio import PortfolioCreate
from app.services.portfolio_service import PortfolioService


def test_reset_and_seed_database_replaces_existing_data(database_url: str) -> None:
    init_db(database_url)
    session_factory = get_session_factory(database_url)

    with session_factory() as session:
        PortfolioService(session).create_portfolio(
            PortfolioCreate(
                name="Old Portfolio",
                slug="old_portfolio",
                description="Should be removed by reset.",
                base_currency="USD",
            )
        )

    summary = reset_and_seed_database(database_url)

    assert summary.portfolio_slugs == (STARTER_PORTFOLIO_SLUG,)
    assert summary.template_names == STARTER_TEMPLATE_NAMES
    assert summary.output_schema_keys == (
        STOCK_ANALYSIS_NOTE_SCHEMA_KEY,
        TRADING_DECISION_SCHEMA_KEY,
    )
    assert summary.skill_keys == (STOCK_ANALYSIS_SKILL_KEY,)
    assert summary.mcp_server_keys == (STOCK_ANALYSIS_MCP_SERVER_KEY,)
    assert set(summary.agent_keys) == {
        *STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS,
        STOCK_ANALYSIS_SYNTHESIZER_KEY,
    }
    assert set(summary.report_slugs) == {company["reportSlug"] for company in MAG7_COMPANIES}
    assert summary.workflow_keys == (STARTER_WORKFLOW_KEY,)

    reset_db_caches()
    verification_session_factory = get_session_factory(database_url)
    with verification_session_factory() as session:
        portfolios = session.scalars(select(Portfolio)).all()
        balances = session.scalars(select(Balance)).all()
        positions = session.scalars(select(Position)).all()
        templates = session.scalars(select(TextTemplate)).all()
        reports = session.scalars(select(Report)).all()
        workflows = session.scalars(select(Workflow)).all()
        output_schemas = session.scalars(select(OutputSchema)).all()
        skills = session.scalars(select(Skill)).all()
        mcp_servers = session.scalars(select(McpServer)).all()
        agents = session.scalars(select(Agent)).all()

        assert [portfolio.slug for portfolio in portfolios] == [STARTER_PORTFOLIO_SLUG]
        assert [balance.label for balance in balances] == [STARTER_BALANCE_LABEL]
        assert {position.symbol for position in positions} == {
            company["symbol"] for company in MAG7_COMPANIES
        }
        assert tuple(template.name for template in templates) == STARTER_TEMPLATE_NAMES
        assert {schema.key for schema in output_schemas} == {
            STOCK_ANALYSIS_NOTE_SCHEMA_KEY,
            TRADING_DECISION_SCHEMA_KEY,
        }
        assert [skill.key for skill in skills] == [STOCK_ANALYSIS_SKILL_KEY]
        assert [server.key for server in mcp_servers] == [STOCK_ANALYSIS_MCP_SERVER_KEY]
        assert {agent.key for agent in agents} == {
            *STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS,
            STOCK_ANALYSIS_SYNTHESIZER_KEY,
        }
        assert {report.slug for report in reports} == {
            company["reportSlug"] for company in MAG7_COMPANIES
        }
        assert [workflow.key for workflow in workflows] == [STARTER_WORKFLOW_KEY]
