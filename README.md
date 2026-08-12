# IntraFlow

IntraFlow는 소규모 내부 팀을 위한 오프라인 우선 업무 관리 데스크톱 앱입니다. 각 PC는 로컬 SQLite에 변경을 먼저 저장하고 NAS에는 JSON 스냅샷만 공유합니다. NAS가 연결되지 않아도 내 업무와 진행량은 계속 수정할 수 있습니다.

## 권한과 업무 소유권

- 시스템 관리자는 사용자·단위와 모든 프로젝트·파트를 관리합니다.
- 프로젝트 편집자는 지정된 프로젝트와 하위 파트를 관리합니다.
- 활성 사용자는 활성 프로젝트의 활성 파트 아래에 자신의 업무를 만듭니다.
- 업무 정의, 활성 상태, 진행량과 메모는 소유자만 수정하거나 삭제할 수 있습니다.
- 관리자와 프로젝트 편집자도 다른 사용자의 업무는 읽기만 합니다.
- `팀 업무`에서는 공개된 모든 사용자 업무를 읽기 전용으로 확인합니다.

## 설치 및 실행

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m intraflow.main
```

앱 시작 시 필요한 SQLite 백업과 Alembic migration이 자동으로 수행됩니다. migration에 실패하면 실행을 중단하고 생성된 백업 경로를 오류 메시지에 표시합니다.

첫 실행에서는 `새 팀 시작` 또는 `기존 팀 합류`를 선택합니다. 첫 번째 PC에서만 새 팀을 시작하며 최초 사용자는 시스템 관리자가 됩니다. 두 번째 PC는 첫 번째 PC의 관리자가 사용자를 생성하고 Push한 뒤 동일한 NAS 경로와 발급받은 사용자 코드를 입력해 합류합니다. 사용자 목록은 노출하지 않으며 기존 사용자 UUID를 유지한 채 현재 PC의 Device만 새로 등록합니다.

기존 팀 합류는 NAS의 사용자·단위·프로젝트와 모든 사용자의 공개 업무를 검증한 뒤 로컬 DB에 한 번에 적용합니다. 합류가 실패하면 로컬 DB와 설정을 변경하지 않습니다. 이미 두 번째 PC에서 사용자를 잘못 만든 경우 설정 창의 `잘못된 로컬 설정 백업 후 기존 팀 합류`를 사용할 수 있으며, 업무·진행·원격 반영 흔적이 있으면 안전을 위해 자동 초기화를 거부합니다.

같은 사용자를 여러 PC에서 사용할 수 있지만 작업 전 Pull, 작업 후 Push 순서를 지켜야 합니다. 다른 PC가 먼저 동일 사용자 snapshot을 Push했다면 현재 PC의 Push를 차단하고 `동기화 > 내 업무 충돌 해결`에서 업무별로 이 PC 또는 NAS 버전을 선택합니다. 적용 전 양쪽 snapshot은 `%LOCALAPPDATA%/IntraFlow/conflicts`에 백업됩니다.

## 첫 업무 만들기

1. 시스템 관리자가 `관리 > 단위 > 새 단위` 팝업에서 사용할 단위를 만듭니다.
2. 시스템 관리자가 `새 프로젝트` 팝업에서 시작일과 종료일을 지정합니다.
3. 시스템 관리자 또는 프로젝트 편집자가 `새 파트` 팝업에서 프로젝트 기간 안에 파트를 만듭니다.
4. 사용자가 `내 업무 > 새 업무` 팝업에서 활성 프로젝트와 파트를 선택합니다.
5. 업무 기간, 목표량, 단위와 설명을 저장합니다. 기간 기본값은 선택한 파트 기간입니다.
6. 증감량 또는 누적 완료량을 입력하고 여러 줄 메모를 저장합니다.
7. 어느 화면에서든 상단 명령 바에서 Pull, Push 또는 전체 동기화를 실행합니다.

프로젝트·파트·업무·사용자·단위는 목록에서 선택하면 오른쪽에 읽기 전용 상세가 표시됩니다. `새 …`와 `수정` 버튼을 누른 경우에만 별도 팝업이 열립니다. 내 업무 상세에서는 진행량과 메모를 바로 입력하고, 계획 기간은 업무 수정 팝업에서 변경합니다. 프로젝트 편집자 목록은 시스템 관리자만 변경할 수 있습니다.

## 자동 갱신과 개인 설정

- 현재 탭의 목록과 상세는 로컬 DB 기준으로 5초마다 갱신됩니다. 내 업무의 저장하지 않은 진행량·메모 입력은 자동 갱신이 덮어쓰지 않습니다.
- 현재 PC 이름은 개인 설정에서 변경합니다. 기기 정보는 NAS에 공유되는 관리자 데이터가 아닙니다.
- `개인 설정`에서 자동 Pull을 켜고 `1·5·10·30·60분` 중 주기를 선택할 수 있습니다. 기본값은 OFF와 5분입니다.
- 같은 화면에서 표시 시간대를 검색해 선택할 수 있습니다. 기본값은 Windows 시스템 시간대이며, DB와 snapshot의 시각은 UTC로 유지하고 화면에서만 선택한 시간대로 변환합니다.
- 자동 Pull을 켜면 앱 시작 10초 후 첫 Pull을 시도하고, 이후에는 이전 Pull이 끝난 시각부터 주기를 계산합니다.
- 자동 Pull은 Push를 실행하지 않습니다. 자동·수동 동기화는 백그라운드에서 하나씩 실행되므로 NAS 응답을 기다리는 동안에도 로컬 업무 입력을 계속할 수 있습니다.
- 설정은 현재 PC의 `intraflow.local.toml`에 원자적으로 저장되며 사용자 snapshot에는 포함되지 않습니다.

## 팀 업무 캘린더와 진행 현황

`팀 업무`에서는 상단의 `목록`, `캘린더`, `진행 현황`을 전환할 수 있습니다. 사용자·프로젝트·파트와 비활성 포함 필터는 세 보기가 공유합니다.

- 캘린더는 업무의 계획 시작일과 종료일을 표시합니다. 날짜 셀에는 업무를 최대 3개와 `+N개`로 보여주며 업무명과 마감일을 바로 확인할 수 있습니다. 업무를 누르면 공개 상세와 진행 이력이 열립니다.
- 진행 현황은 프로젝트→파트→업무 계층에서 가중 진행률, 완료·진행 중·미시작 수와 일정·목표량 경고를 보여줍니다. 비활성 업무는 기본 집계에서 제외됩니다.
- 서로 다른 단위의 목표량은 합산하지 않습니다. 목표량이 0인 업무는 진행률 계산에서 제외하고 경고로 표시합니다.

UI는 이글루코퍼레이션 CI의 Green `#00A98E`를 선택·진행 상태에 사용하고, 주요 버튼은 가독성을 위해 더 진한 Green을 사용합니다. 공식 로고나 별도 글꼴 파일은 포함하지 않습니다.

Windows의 라이트·다크 모드를 자동으로 감지해 앱 전체 Palette와 위젯 스타일을 함께 전환합니다. 1250px 이상에서는 목록과 상세를 함께 표시하고, 더 좁은 창에서는 목록과 상세를 전환해 가독성을 유지합니다. 상세에서는 진행 입력을 먼저 보여주고 설명과 이력을 아래에 배치합니다.

상단 명령 바는 모든 탭에서 Pull·Push·전체 동기화를 제공합니다. 동기화 센터에서는 마지막 Pull과 Push, 대상별 결과와 Outbox를 확인합니다. 일부 대상 실패는 성공으로 표시하지 않으며 공유 정의 충돌은 마지막 정상 snapshot을 기준으로 항목별 병합합니다.

표와 트리의 열은 직접 조절할 수 있으며 변경한 너비는 현재 PC에 저장됩니다. 긴 프로젝트·파트·업무·메모는 한 줄로 줄여 표시하고 마우스를 올리면 전체 내용을 확인할 수 있습니다.

상위 프로젝트나 파트가 비활성이면 하위 업무의 원래 상태는 유지되지만 실효 상태는 비활성이 됩니다. 이때 진행 입력은 차단되고 `비활성 포함` 필터로 조회할 수 있습니다.

로컬 DB는 `%LOCALAPPDATA%/IntraFlow/intraflow.db`에 저장됩니다. `intraflow.local.toml`과 로컬 SQLite를 NAS에 두지 마세요.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Windows EXE 빌드

기본 배포본은 Nuitka와 `PySide6-Essentials`만 사용하는 standalone ZIP입니다. 별도의 `.build-venv`에서 테스트와 빌드를 수행하므로 개발용 가상환경의 전체 PySide6 Addons가 배포본에 포함되지 않습니다.

```powershell
.\scripts\build-windows.ps1 -Clean
```

`.ps1`이 메모장으로 열리거나 CMD에서 실행하는 경우에는 함께 제공되는 CMD 래퍼를 사용합니다.

```bat
.\scripts\build-windows.cmd -Clean
```

CMD 래퍼는 코드 페이지와 PowerShell·Python 출력을 UTF-8로 맞춥니다. 그래도 한글이 네모나 물음표로 보이면 Windows Terminal을 사용하고 프로필 글꼴을 `Cascadia Mono`, `맑은 고딕` 또는 다른 한글 지원 글꼴로 변경하세요.

빌드 중 pytest와 Nuitka 캐시는 Windows 사용자 공용 경로를 사용하지 않고 각각 프로젝트의 `build/pytest-temp`, `build/nuitka-cache`를 사용합니다. 이전 관리자 실행이나 다른 계정이 만든 캐시 폴더의 권한과 관계없이 일반 사용자로 빌드할 수 있습니다.

Nuitka 빌드는 `python.org`에서 설치한 64비트 Python 3.11 또는 3.12를 권장합니다. Codex 번들 Python처럼 `libs/python312.lib`가 없는 배포판은 Windows 실행 파일을 링크할 수 없습니다. 잘못된 Python으로 `.build-venv`가 만들어졌다면 정식 Python의 경로를 지정해 빌드 환경을 다시 생성합니다.

```bat
scripts\build-windows.cmd -PythonPath "C:\Users\사용자명\AppData\Local\Programs\Python\Python312\python.exe" -RecreateBuildVenv -Mode OneFile -Clean
```

완성된 폴더와 ZIP은 `release/`에 생성됩니다. 두 번째 빌드부터 패키지 설치를 생략하려면 다음처럼 실행합니다.

```powershell
.\scripts\build-windows.ps1 -Clean -SkipInstall
```

단일 EXE가 필요한 경우에는 먼저 standalone 배포본을 검증한 뒤 다음 명령을 사용합니다.

```powershell
.\scripts\build-windows.ps1 -Mode OneFile -Clean -SkipInstall
```

PowerShell에서 `.ps1`을 명시적으로 실행하려면 호출 연산자를 사용할 수도 있습니다.

```powershell
& ".\scripts\build-windows.ps1" -Mode OneFile -Clean -SkipInstall
```

최초 실행에는 빌드 패키지가 아직 없으므로 `-SkipInstall`을 사용하지 마세요.

```bat
.\scripts\build-windows.cmd -Mode OneFile -Clean
```

사용 가능한 옵션:

- `-Clean`: 기존 `build/windows`와 `release` 산출물을 제거하고 다시 빌드
- `-Version 0.1.0`: 산출물 파일명에 사용할 버전 지정
- `-SkipTests`: 자동 테스트 생략
- `-SkipInstall`: 기존 `.build-venv`의 패키지를 그대로 사용
- `-AllowCompilerDownload`: Visual Studio C 컴파일러가 없을 때 Nuitka MinGW64 사용
- `-Help`: 한글 빌드 명령 도움말 표시

스크립트는 `alembic.ini`와 migration Python 파일을 압축 리소스로 포함합니다. 실행 시 이 리소스는 `%LOCALAPPDATA%\IntraFlow\migration-runtime`에 안전하게 풀리며, 실제 DB와 설정 역시 배포 폴더 밖의 로컬 앱 데이터 경로에 유지됩니다.

상세한 초기 설정과 데이터 흐름은 [MVP 설정 문서](docs/mvp-setup.md)를 참고하세요.
