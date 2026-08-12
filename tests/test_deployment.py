from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from intraflow.deployment import _extract_migration_archive, migration_root


def test_source_tree_is_used_for_migrations(tmp_path: Path) -> None:
    root = migration_root(tmp_path)

    assert (root / "alembic.ini").is_file()
    assert (root / "migrations" / "versions").is_dir()


def test_migration_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "unsafe")

    with pytest.raises(ValueError, match="안전하지 않은"):
        _extract_migration_archive(archive, tmp_path / "target")


def test_migration_archive_is_materialized_for_packaged_app(tmp_path: Path) -> None:
    archive = tmp_path / "migrations.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("alembic.ini", "[alembic]\nscript_location = migrations\n")
        bundle.writestr("migrations/env.py", "# packaged migration\n")

    target = tmp_path / "target"
    _extract_migration_archive(archive, target)

    assert (target / "alembic.ini").is_file()
    assert (target / "migrations" / "env.py").read_text(encoding="utf-8") == "# packaged migration\n"
