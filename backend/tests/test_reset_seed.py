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
from app.reset_seed import reset_and_seed_database
from app.schemas.portfolio import PortfolioCreate
from app.services.portfolio_service import PortfolioService


def test_reset_and_seed_database_replaces_existing_data_with_a_clean_empty_workspace(
    database_url: str,
) -> None:
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

    assert summary.portfolio_slugs == ()
    assert summary.template_names == ()
    assert summary.output_schema_keys == ()
    assert summary.skill_keys == ()
    assert summary.mcp_server_keys == ()
    assert summary.agent_keys == ()
    assert summary.report_slugs == ()
    assert summary.workflow_keys == ()

    reset_db_caches()
    verification_session_factory = get_session_factory(database_url)
    with verification_session_factory() as session:
        assert session.scalars(select(Portfolio)).all() == []
        assert session.scalars(select(Balance)).all() == []
        assert session.scalars(select(Position)).all() == []
        assert session.scalars(select(TextTemplate)).all() == []
        assert session.scalars(select(Report)).all() == []
        assert session.scalars(select(Workflow)).all() == []
        assert session.scalars(select(OutputSchema)).all() == []
        assert session.scalars(select(Skill)).all() == []
        assert session.scalars(select(McpServer)).all() == []
        assert session.scalars(select(Agent)).all() == []
