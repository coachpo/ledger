from __future__ import annotations

from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy import select

from app.db.session import get_session_factory, init_db, reset_db_caches
from app.extensions.signaldeck_finance.services.portfolio_service import PortfolioService
from app.models.balance import Balance
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.report import Report
from app.models.text_template import TextTemplate
from app.reset_seed import reset_and_seed_database
from app.schemas.portfolio import PortfolioCreate


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
            )
        )

    summary = reset_and_seed_database(database_url)

    assert summary.portfolio_slugs == ()
    assert summary.template_names == ()
    assert summary.output_schema_keys == ()
    assert summary.capability_keys == ()
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
        table_names = set(sqlalchemy_inspect(session.get_bind()).get_table_names())
        assert {
            "agents",
            "workflows",
            "capabilities",
            "mcp_servers",
            "output_schemas",
        }.isdisjoint(table_names)
