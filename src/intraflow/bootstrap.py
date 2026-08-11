from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from intraflow.database import create_session_factory, create_sqlite_engine


def build_database(database_url: str | None = None) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_sqlite_engine(database_url)
    return engine, create_session_factory(engine)
