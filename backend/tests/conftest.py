from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.engine import create_engine_from_url
from backend.db.models import *  # noqa: F403


@pytest.fixture(scope="session")
def engine():
    engine = create_engine_from_url()
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    yield engine
    engine.dispose()


def reset_schema(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


@pytest.fixture()
def session(engine):
    reset_schema(engine)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
        session.rollback()
    reset_schema(engine)
