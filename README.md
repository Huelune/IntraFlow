# IntraFlow

인터넷 또는 중앙 DB/앱 서버 없이, 각 PC의 Local SQLite와 사내 NAS Snapshot 공유만으로 동작하는 소규모 팀 업무·일정 관리 데스크톱 앱입니다.

## 현재 구현 범위

- SQLAlchemy 2.x ORM 기반 Local SQLite DB Foundation
- 15개 핵심 테이블
- FK / CHECK / UNIQUE / INDEX 제약조건
- SQLite PRAGMA 설정 (`foreign_keys`, `WAL`, `synchronous`, `busy_timeout`)
- 진행량 변경 Transaction
  - `assignment_progress` 갱신
  - `progress_history` 자동 생성
  - `sync_outbox` Dirty 등록
- Alembic 초기 migration
- 기본 테스트

## 설치

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## DB 생성

```bash
alembic upgrade head
```

기본 DB 위치:

```text
%LOCALAPPDATA%/IntraFlow/intraflow.db
```

테스트 시에는 임시 SQLite DB를 사용합니다.

## 테스트

```bash
pytest
```

## 다음 단계

1. Snapshot Pydantic Schema 구현
2. `SnapshotBuilder` / `SnapshotValidator`
3. `NASClient`
4. `SyncWorker`
5. `내 업무` PySide6 MVP
