from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from zipfile import ZipFile


def migration_root(data_dir: Path) -> Path:
    """Return source migrations or materialize the archive bundled with the EXE."""

    source_root = Path(__file__).resolve().parents[2]
    if (source_root / "alembic.ini").is_file() and (source_root / "migrations").is_dir():
        return source_root

    candidates = [
        Path(__file__).resolve().parents[2] / "intraflow_resources" / "migrations.zip",
        Path(sys.argv[0]).resolve().parent / "intraflow_resources" / "migrations.zip",
    ]
    archive = next((path for path in candidates if path.is_file()), None)
    if archive is None:
        raise FileNotFoundError("배포본에서 Alembic migration 리소스를 찾을 수 없습니다.")

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()[:12]
    target = data_dir / "migration-runtime" / digest
    marker = target / ".complete"
    if marker.is_file():
        return target

    _extract_migration_archive(archive, target)
    marker.write_text(digest, encoding="ascii")
    return target


def _extract_migration_archive(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as bundle:
        target_root = target.resolve()
        for member in bundle.infolist():
            destination = (target / member.filename).resolve()
            if destination != target_root and target_root not in destination.parents:
                raise ValueError(f"안전하지 않은 migration 압축 경로입니다: {member.filename}")
        bundle.extractall(target)
    if not (target / "alembic.ini").is_file() or not (target / "migrations").is_dir():
        raise FileNotFoundError("migration 압축에 alembic.ini 또는 migrations 디렉터리가 없습니다.")
