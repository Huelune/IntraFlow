from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect


INITIAL_REVISION = "12916f19acec"


class DatabaseUpgradeError(RuntimeError):
    def __init__(self, backup_path: Path | None, cause: Exception) -> None:
        self.backup_path = backup_path
        location = str(backup_path) if backup_path else "백업 없음"
        super().__init__(f"데이터베이스 migration에 실패했습니다. 복원 백업: {location}. 원인: {cause}")


def backup_sqlite_database(database_path: Path) -> Path:
    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = backup_dir / f"{database_path.stem}-{timestamp}{database_path.suffix}"
    with sqlite3.connect(database_path) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    return destination


def upgrade_database(database_path: Path, project_root: Path) -> Path | None:
    """Back up and upgrade a SQLite database to the Alembic head revision."""
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        table_names = set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
        if table_names and current is None:
            command.stamp(config, INITIAL_REVISION)
            current = INITIAL_REVISION
        if current == head:
            return None
    finally:
        engine.dispose()

    backup = backup_sqlite_database(database_path) if database_path.exists() else None
    try:
        command.upgrade(config, "head")
    except Exception as exc:
        raise DatabaseUpgradeError(backup, exc) from exc
    return backup
