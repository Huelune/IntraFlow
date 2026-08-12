from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker


def test_all_core_tables_exist(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        names = set(inspect(session.get_bind()).get_table_names())

    assert names == {
        "app_meta",
        "assignment_progress",
        "assignments",
        "devices",
        "parts",
        "progress_history",
        "project_editors",
        "projects",
        "sync_outbox",
        "sync_state",
        "units",
        "users",
        "work_items",
    }
