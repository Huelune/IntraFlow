# IntraFlow MVP 설정

## 설치

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

## 워크스테이션 설정

첫 실행 시 표시되는 설정 창에 사용자 코드, 표시 이름, PC 이름과 이미 연결된 NAS 경로를 입력합니다. IntraFlow는 UUIDv4 사용자·기기 레코드를 만들고 첫 사용자에게 시스템 관리자 권한을 부여한 뒤 `intraflow.local.toml`을 자동으로 작성합니다.

이미 사용자가 존재하는 공유 데이터라면 기존 사용자 코드로 연결할 수 있습니다. 로컬 SQLite DB는 NAS 경로에 두지 않습니다.

## 실행과 자동 migration

```powershell
.\.venv\Scripts\python.exe -m intraflow.main
```

앱은 시작할 때 DB revision을 확인합니다. migration이 필요하면 `%LOCALAPPDATA%/IntraFlow/backups`에 SQLite 백업을 만든 후 최신 revision을 적용합니다. 실패하면 앱을 열지 않으며 복원에 사용할 백업 경로를 표시합니다.

## 데이터 생성 순서

1. 시스템 관리자가 단위를 등록합니다.
2. 시스템 관리자가 필수 시작일·종료일을 포함한 프로젝트를 생성합니다.
3. 시스템 관리자 또는 프로젝트 편집자가 프로젝트 기간 안에 파트를 생성합니다.
4. 각 사용자가 활성 파트 아래 자신의 업무를 생성합니다.
5. 업무 저장 시 같은 소유자를 가리키는 내부 Assignment가 자동 생성됩니다.
6. 사용자는 `내 업무`에서 진행량, 현재 메모와 개인 일정을 수정합니다.
7. `팀 업무`에서는 다른 사용자의 공개 업무와 최신 진행을 읽기 전용으로 확인합니다.

프로젝트 snapshot에는 프로젝트·편집자·파트만 포함됩니다. 업무, 내부 Assignment와 진행 정보는 소유자의 `users/<user_id>/public.json`에 포함됩니다. 로컬 변경은 NAS 연결 상태와 무관하게 먼저 커밋되며 동기화 실패 항목은 Outbox에 남습니다.
