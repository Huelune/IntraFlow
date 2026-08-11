# IntraFlow

IntraFlow는 소규모 내부 팀을 위한 오프라인 우선 업무 관리 데스크톱 앱입니다. 각 PC는 로컬 SQLite에 작업을 저장하고, 연결된 NAS에는 JSON 스냅샷만 공유합니다. NAS가 연결되지 않아도 진행량 입력은 계속 사용할 수 있습니다.

## 현재 제공 기능

- 최초 사용자·기기 자동 생성
- 시스템 관리자용 사용자·기기·단위 관리
- 프로젝트 편집자용 프로젝트·파트·업무·배정 관리
- 사용자의 ACTIVE 배정 업무 조회와 진행량 입력
- 진행 이력과 동기화 Outbox의 원자적 저장
- 사용자·단위·프로젝트·공개 진행 snapshot 수동 push/pull
- revision 충돌 감지와 로컬 우선 저장

## 설치 및 실행

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m intraflow.main
```

첫 실행에서 사용자 코드, 표시 이름, 현재 PC 이름, NAS 경로를 입력합니다. 첫 사용자는 시스템 관리자가 되며, 자신이 만든 프로젝트의 프로젝트 편집자로 자동 등록됩니다.

## 첫 업무 만들기

1. `관리 > 사용자·기기`에서 업무 담당자를 추가합니다.
2. `관리 > 단위`에서 `EA`, `건`, `시간` 등의 단위를 추가합니다.
3. `관리 > 프로젝트`에서 프로젝트를 만듭니다.
4. `관리 > 파트`에서 프로젝트의 파트를 만듭니다.
5. `관리 > 업무`에서 수량과 단위를 가진 업무를 만듭니다.
6. `관리 > 배정`에서 업무를 사용자에게 배정합니다.
7. `내 업무`에서 진행량을 입력합니다.
8. NAS가 연결되어 있으면 `동기화` 탭에서 Push 또는 전체 동기화를 실행합니다.

로컬 DB는 `%LOCALAPPDATA%/IntraFlow/intraflow.db`에 저장됩니다. `intraflow.local.toml`과 로컬 SQLite를 NAS에 두지 마세요.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

상세 설정은 [MVP 설정 문서](docs/mvp-setup.md)를 참고하세요.
