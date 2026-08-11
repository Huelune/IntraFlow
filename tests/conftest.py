from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from intraflow.database import create_session_factory, create_sqlite_engine
from intraflow.models import Base


@pytest.fixture()
def session_factory(tmp_path: Path) -> sessionmaker[Session]:
    db_path = tmp_path / "test.db"
    engine = create_sqlite_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        engine.dispose()
