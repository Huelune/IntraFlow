from __future__ import annotations

import argparse
import json
from pathlib import Path

from intraflow.config import settings
from intraflow.database import create_session_factory, create_sqlite_engine
from intraflow.database_upgrade import backup_sqlite_database, upgrade_database
from intraflow.maintenance import delete_nas_reset_targets, list_nas_reset_targets, reset_local_data


def main() -> int:
    parser = argparse.ArgumentParser(description="IntraFlow project-domain reset")
    parser.add_argument("--execute-reset", action="store_true")
    parser.add_argument("--expected-nas-root", required=True)
    args = parser.parse_args()

    database_path = settings.db_path.resolve(strict=True)
    runtime = settings.runtime_config()
    if not runtime.nas_root_path:
        raise RuntimeError("설정에 NAS 루트가 없습니다.")
    nas_root = Path(runtime.nas_root_path).resolve(strict=True)
    expected_root = Path(args.expected_nas_root).resolve(strict=True)
    if nas_root != expected_root:
        raise RuntimeError(f"NAS 루트 불일치: 설정={nas_root}, 예상={expected_root}")

    targets = list_nas_reset_targets(nas_root)
    preview = {
        "database": str(database_path),
        "nas_root": str(nas_root),
        "nas_targets": [str(path) for path in targets],
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    if not args.execute_reset:
        return 0

    backup = backup_sqlite_database(database_path)
    engine = create_sqlite_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        result = reset_local_data(create_session_factory(engine))
    finally:
        engine.dispose()
    deleted_targets = delete_nas_reset_targets(nas_root)
    migration_backup = upgrade_database(database_path, Path(__file__).resolve().parents[2])

    remaining_targets = list_nas_reset_targets(nas_root)
    if remaining_targets:
        raise RuntimeError(f"NAS 삭제 대상이 남았습니다: {remaining_targets}")
    output = {
        "backup": str(backup),
        "migration_backup": str(migration_backup) if migration_backup else None,
        "preserved_users": result.preserved_users,
        "preserved_devices": result.preserved_devices,
        "preserved_units": result.preserved_units,
        "deleted_local_rows": result.deleted_rows,
        "deleted_nas_targets": [str(path) for path in deleted_targets],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
