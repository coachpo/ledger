from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import reset_settings_cache
from app.db.session import get_engine, get_session_factory, init_db, reset_db_caches
from app.main import create_app

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://ledger:ledger@localhost:25432/ledger"


def _get_base_database_url() -> URL:
    raw_database_url = (
        os.environ.get("TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or DEFAULT_TEST_DATABASE_URL
    )
    database_url = make_url(raw_database_url)
    if database_url.get_backend_name() not in {"postgresql", "postgres"}:
        raise RuntimeError("Tests require a PostgreSQL DATABASE_URL or TEST_DATABASE_URL.")
    return database_url


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


@pytest.fixture()
def database_url() -> Iterator[str]:
    base_database_url = _get_base_database_url()
    admin_database_url = base_database_url.set(database="postgres")
    database_name = f"ledger_test_{uuid4().hex}"
    resolved_database_url = base_database_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    admin_engine = create_engine(admin_database_url, isolation_level="AUTOCOMMIT", future=True)

    with admin_engine.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {_quote_identifier(database_name)}"))

    try:
        yield resolved_database_url
    finally:
        get_engine(resolved_database_url).dispose()
        reset_db_caches()
        reset_settings_cache()
        with admin_engine.connect() as connection:
            connection.execute(
                text(f"DROP DATABASE IF EXISTS {_quote_identifier(database_name)} WITH (FORCE)")
            )
        admin_engine.dispose()


@pytest.fixture()
def session_factory(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[sessionmaker[Session]]:
    monkeypatch.setenv("DATABASE_URL", database_url)
    reset_settings_cache()
    reset_db_caches()
    init_db(database_url)

    yield get_session_factory(database_url)

    get_engine(database_url).dispose()
    reset_db_caches()
    reset_settings_cache()


@pytest.fixture()
def app(session_factory: sessionmaker[Session]) -> FastAPI:
    return create_app(init_database=False)


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
