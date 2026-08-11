# IntraFlow — Codex 구현 지시서

## 현재 목표

DB Foundation이 기준이다. UI 기능을 먼저 확장하지 말고 아래 순서로 진행한다.

## Phase 1 — Local DB Foundation

완료 기준:

- `pytest` 통과
- 15개 테이블 생성
- FK 활성화 확인
- ProgressService `+5`가 Progress/History/Outbox를 한 Transaction에서 저장
- 권한 위반 시 rollback
- 할당량 초과 시 rollback

## Phase 2 — Snapshot Schema

추가 파일:

```text
src/intraflow/sync/schemas.py
src/intraflow/sync/snapshot_builder.py
src/intraflow/sync/snapshot_validator.py
```

Pydantic 2.x 모델로 다음을 구현한다.

- ProjectSnapshot
- UserPublicSnapshot
- SystemConfigSnapshot
- UsersSnapshot
- UnitsSnapshot

규칙:

- PRIVATE CalendarEvent 제외
- PersonalNote 제외
- ProgressHistory 최근 90일만 UserPublicSnapshot에 포함
- schema_version 필수
- revision 필수

## Phase 3 — NAS I/O

```text
src/intraflow/sync/nas_client.py
src/intraflow/sync/lock_manager.py
src/intraflow/sync/push_service.py
src/intraflow/sync/pull_service.py
```

규칙:

- `.tmp` 전체 기록 후 atomic replace
- Pull은 `.json`만 읽음
- 사용자는 자신의 `users/<user_id>/public.json`만 Write
- Project 저장만 short lock + base revision 비교
- Last Write Wins 금지
- NAS 실패가 Local 업무 저장을 실패시키면 안 됨

## Phase 4 — PySide6 내 업무 MVP

기능:

- 현재 사용자의 ACTIVE Assignment 목록
- 업무명 / Project / Part / 일정 / `완료량 / 할당량`
- 오늘 진행량 입력
- Enter 또는 반영 버튼으로 `ProgressService.add_delta()` 호출
- 저장 성공 즉시 Local 화면 갱신
- NAS 상태와 별도로 `로컬 저장됨 · 동기화 대기` 표시 가능

## 금지

- UI에서 Session 직접 생성
- UI에서 NAS 파일 직접 접근
- 진행률 % 저장 컬럼 추가
- Work schedule을 CalendarEvent에 복제
- Admin에게 타 사용자 진행량 수정 기능 추가
- NAS shared SQLite 추가
