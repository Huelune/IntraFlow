from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect

from intraflow.database_upgrade import DatabaseUpgradeError, upgrade_database


def test_upgrade_database_backs_up_and_adds_owned_work_columns(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    database = tmp_path / "legacy.db"
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "12916f19acec")
    backup = upgrade_database(database, root)
    assert backup is not None and backup.exists()
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    columns = {column["name"] for column in inspect(engine).get_columns("work_items")}
    assert {"owner_user_id", "description", "is_active"} <= columns
    assert "is_active" in {column["name"] for column in inspect(engine).get_columns("parts")}
    engine.dispose()


def test_upgrade_database_reports_backup_when_migration_fails(tmp_path: Path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    database = tmp_path / "legacy.db"
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "12916f19acec")

    def fail_upgrade(*_args, **_kwargs) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(command, "upgrade", fail_upgrade)
    with pytest.raises(DatabaseUpgradeError) as caught:
        upgrade_database(database, root)

    assert caught.value.backup_path is not None
    assert caught.value.backup_path.exists()
