[CmdletBinding()]
param(
    [ValidateSet("Standalone", "OneFile")]
    [string]$Mode = "Standalone",

    [string]$Version = "0.1.0",

    [string]$PythonPath = "",

    [switch]$Clean,
    [switch]$RecreateBuildVenv,
    [switch]$SkipTests,
    [switch]$SkipInstall,
    [switch]$AllowCompilerDownload,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if ($Help) {
    Write-Host "IntraFlow Windows 빌드"
    Write-Host "  최초 빌드: .\scripts\build-windows.cmd -Clean"
    Write-Host "  단일 EXE:  .\scripts\build-windows.cmd -Mode OneFile -Clean"
    Write-Host "  재빌드:    .\scripts\build-windows.cmd -Mode OneFile -Clean -SkipInstall"
    Write-Host "  Python 지정: .\scripts\build-windows.cmd -PythonPath C:\Python312\python.exe -RecreateBuildVenv -Clean"
    exit 0
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BuildVenv = Join-Path $ProjectRoot ".build-venv"
$BuildRoot = Join-Path $ProjectRoot "build\windows"
$PytestTemp = Join-Path $ProjectRoot "build\pytest-temp"
$NuitkaCache = Join-Path $ProjectRoot "build\nuitka-cache"
$ReleaseRoot = Join-Path $ProjectRoot "release"
$EntryPoint = Join-Path $ProjectRoot "src\intraflow\main.py"
$Python = Join-Path $BuildVenv "Scripts\python.exe"
$ArtifactBaseName = "IntraFlow-$Version-windows-x64"

Set-Location -LiteralPath $ProjectRoot
$env:NUITKA_CACHE_DIR = $NuitkaCache
New-Item -ItemType Directory -Path $NuitkaCache -Force | Out-Null

function Assert-ChildPath {
    param([Parameter(Mandatory)][string]$Path)

    $root = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\') + '\'
    $target = [System.IO.Path]::GetFullPath($Path)
    if (-not $target.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "작업 경로가 프로젝트 밖을 가리킵니다: $target"
    }
}

function Remove-BuildPath {
    param([Parameter(Mandatory)][string]$Path)

    Assert-ChildPath $Path
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory)][string]$Command,
        [Parameter(ValueFromRemainingArguments)][string[]]$Arguments
    )

    Write-Host "`n> $Command $($Arguments -join ' ')" -ForegroundColor Cyan
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "명령 실행 실패 (exit $LASTEXITCODE): $Command"
    }
}

function Test-NuitkaPython {
    param([Parameter(Mandatory)][string]$PythonExecutable)

    if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
        return $false
    }
    & $PythonExecutable -c "import pathlib, sys; p=pathlib.Path(sys.base_prefix)/'libs'/f'python{sys.version_info.major}{sys.version_info.minor}.lib'; raise SystemExit(0 if p.is_file() else 1)"
    return $LASTEXITCODE -eq 0
}

if ($Clean) {
    Write-Host "기존 빌드 산출물을 정리합니다." -ForegroundColor Yellow
    Remove-BuildPath $BuildRoot
    Remove-BuildPath $ReleaseRoot
}

if ($RecreateBuildVenv) {
    Remove-BuildPath $BuildVenv
}

if (-not (Test-Path -LiteralPath $Python)) {
    if ($PythonPath) {
        $SystemPythonPath = [System.IO.Path]::GetFullPath($PythonPath)
    } else {
        $SystemPython = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $SystemPython) {
            throw "Python 3.11 이상을 찾을 수 없습니다. python.org의 64비트 Python을 설치하거나 -PythonPath로 지정하세요."
        }
        $SystemPythonPath = $SystemPython.Source
    }
    if (-not (Test-NuitkaPython $SystemPythonPath)) {
        throw "Nuitka 링크 라이브러리가 없는 Python입니다: $SystemPythonPath`npython.org의 64비트 Python 3.11/3.12를 설치하고 -PythonPath와 -RecreateBuildVenv를 사용하세요."
    }
    Invoke-Checked $SystemPythonPath "-m" "venv" $BuildVenv
}

if (-not (Test-NuitkaPython $Python)) {
    throw "현재 .build-venv는 Nuitka 링크 라이브러리가 없는 Python으로 생성되었습니다.`npython.org의 64비트 Python 3.11/3.12를 설치한 뒤 다음처럼 다시 생성하세요:`n  scripts\build-windows.cmd -PythonPath C:\Python312\python.exe -RecreateBuildVenv -Mode $Mode -Clean"
}

if (-not $SkipInstall) {
    Invoke-Checked $Python "-m" "pip" "install" "--upgrade" "pip"
    Invoke-Checked $Python "-m" "pip" "install" `
        "SQLAlchemy>=2.0,<3.0" `
        "alembic>=1.13,<2.0" `
        "pydantic>=2.0,<3.0" `
        "PySide6-Essentials>=6.7,<7.0" `
        "Nuitka>=2.6,<5.0" `
        "ordered-set" `
        "zstandard" `
        "pytest>=8.0,<9.0"
    Invoke-Checked $Python "-m" "pip" "install" "--no-deps" "-e" $ProjectRoot
} else {
    & $Python -c "import nuitka, PySide6, sqlalchemy, alembic, pydantic"
    if ($LASTEXITCODE -ne 0) {
        throw "-SkipInstall을 사용할 수 없습니다. 빌드 패키지가 없습니다. -SkipInstall 없이 먼저 실행하세요."
    }
}

if (-not $SkipTests) {
    Remove-BuildPath $PytestTemp
    New-Item -ItemType Directory -Path (Split-Path -Parent $PytestTemp) -Force | Out-Null
    New-Item -ItemType Directory -Path $PytestTemp -Force | Out-Null
    Invoke-Checked $Python "-m" "pytest" "-q" "--basetemp=$PytestTemp" (Join-Path $ProjectRoot "tests")
}

Remove-BuildPath $BuildRoot
New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null

$ResourceStage = Join-Path $BuildRoot "resource-stage"
$MigrationStage = Join-Path $ResourceStage "bundle"
$MigrationArchive = Join-Path $ResourceStage "migrations.zip"
New-Item -ItemType Directory -Path $MigrationStage -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $ProjectRoot "alembic.ini") -Destination $MigrationStage
Copy-Item -LiteralPath (Join-Path $ProjectRoot "migrations") -Destination $MigrationStage -Recurse
Get-ChildItem -LiteralPath $MigrationStage -Directory -Filter "__pycache__" -Recurse |
    Remove-Item -Recurse -Force
Compress-Archive -Path (Join-Path $MigrationStage "*") -DestinationPath $MigrationArchive -CompressionLevel Optimal

$NuitkaArguments = @(
    "-m", "nuitka",
    "--enable-plugin=pyside6",
    "--windows-console-mode=disable",
    "--assume-yes-for-downloads",
    "--output-dir=$BuildRoot",
    "--output-filename=IntraFlow.exe",
    "--include-data-file=$MigrationArchive=intraflow_resources/migrations.zip",
    "--include-package=alembic",
    "--include-package=sqlalchemy.dialects.sqlite",
    "--nofollow-import-to=pytest",
    "--nofollow-import-to=tests",
    "--nofollow-import-to=PySide6.QtWebEngineCore",
    "--nofollow-import-to=PySide6.QtWebEngineWidgets",
    "--nofollow-import-to=PySide6.QtMultimedia",
    "--nofollow-import-to=PySide6.QtQuick",
    "--nofollow-import-to=PySide6.QtQml",
    "--nofollow-import-to=PySide6.Qt3DCore",
    "--noinclude-qt-translations"
)

if ($Mode -eq "OneFile") {
    $NuitkaArguments += "--onefile"
} else {
    $NuitkaArguments += "--standalone"
}
if ($AllowCompilerDownload) {
    $NuitkaArguments += "--mingw64"
}
$NuitkaArguments += $EntryPoint

Invoke-Checked $Python @NuitkaArguments

if ($Mode -eq "OneFile") {
    $BuiltExe = Get-ChildItem -LiteralPath $BuildRoot -Filter "IntraFlow.exe" -File -Recurse |
        Select-Object -First 1
    if ($null -eq $BuiltExe) {
        throw "Nuitka 단일 EXE 산출물을 찾지 못했습니다."
    }
    $ReleaseFile = Join-Path $ReleaseRoot "$ArtifactBaseName.exe"
    Copy-Item -LiteralPath $BuiltExe.FullName -Destination $ReleaseFile -Force
    $SizeMb = [math]::Round((Get-Item -LiteralPath $ReleaseFile).Length / 1MB, 1)
    Write-Host "`n완료: $ReleaseFile ($SizeMb MB)" -ForegroundColor Green
} else {
    $BuiltExe = Get-ChildItem -LiteralPath $BuildRoot -Filter "IntraFlow.exe" -File -Recurse |
        Where-Object { $_.Directory.Name -like "*.dist" } |
        Select-Object -First 1
    if ($null -eq $BuiltExe) {
        throw "Nuitka standalone 산출물을 찾지 못했습니다."
    }

    $ReleaseDirectory = Join-Path $ReleaseRoot $ArtifactBaseName
    $ReleaseZip = Join-Path $ReleaseRoot "$ArtifactBaseName.zip"
    Remove-BuildPath $ReleaseDirectory
    if (Test-Path -LiteralPath $ReleaseZip) {
        Remove-Item -LiteralPath $ReleaseZip -Force
    }
    Copy-Item -LiteralPath $BuiltExe.Directory.FullName -Destination $ReleaseDirectory -Recurse
    Compress-Archive -Path (Join-Path $ReleaseDirectory "*") -DestinationPath $ReleaseZip -CompressionLevel Optimal

    $DirectoryBytes = (Get-ChildItem -LiteralPath $ReleaseDirectory -File -Recurse |
        Measure-Object -Property Length -Sum).Sum
    $DirectoryMb = [math]::Round($DirectoryBytes / 1MB, 1)
    $ZipMb = [math]::Round((Get-Item -LiteralPath $ReleaseZip).Length / 1MB, 1)
    Write-Host "`n완료: $ReleaseDirectory ($DirectoryMb MB)" -ForegroundColor Green
    Write-Host "배포 ZIP: $ReleaseZip ($ZipMb MB)" -ForegroundColor Green
}

Write-Host "설정과 DB는 배포 폴더가 아니라 현재 PC의 로컬 경로에 보존됩니다." -ForegroundColor DarkGray
