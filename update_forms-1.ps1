# =====================================================================
#  [로컬 작업] 무료서식 다운로드 — 갱신본 적용 (update_forms.zip 반영)
#  사용법 : C:\Project_Forms 에서  .\update_forms.ps1
#  압축본 안의 파일만 덮어쓰고, 없는 파일은 건드리지 않습니다.
# =====================================================================
[CmdletBinding()]
param(
    [string]$Bundle = "update_forms*.zip",
    [switch]$KeepBundle,
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

function Write-Step([string]$t) {
    Write-Host ""
    Write-Host "== $t " -ForegroundColor Cyan -NoNewline
    Write-Host ("=" * [Math]::Max(0, 56 - $t.Length)) -ForegroundColor DarkGray
}
function Write-Ok([string]$t)   { Write-Host "  [완료] $t" -ForegroundColor Green }
function Write-Fail([string]$t) { Write-Host "  [실패] $t" -ForegroundColor Red }

# 1. 압축 해제 (갱신본이 여러 조각으로 나뉘어 있어도 이름순으로 모두 적용한다)
Write-Step "1. 갱신본 적용"
$zips = @(Get-ChildItem -Path (Join-Path $root $Bundle) -File -ErrorAction SilentlyContinue | Sort-Object Name)
if ($zips.Count -eq 0) {
    Write-Fail "$Bundle 을 찾을 수 없습니다. 이 스크립트와 같은 폴더에 두십시오."
    exit 1
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$count = 0
foreach ($zip in $zips) {
    $archive = [System.IO.Compression.ZipFile]::Open($zip.FullName, 'Read', [System.Text.Encoding]::UTF8)
    try {
        foreach ($entry in $archive.Entries) {
            if ($entry.Name -eq '') { continue }
            $dest = Join-Path $root $entry.FullName
            $dir = Split-Path $dest -Parent
            if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $dest, $true)
            $count++
        }
    } finally {
        $archive.Dispose()
    }
    Write-Ok "$($zip.Name) 적용"
}
Write-Ok "파일 $count 개 갱신 (압축본 $($zips.Count)개)"
if (-not $KeepBundle) {
    foreach ($zip in $zips) { Remove-Item $zip.FullName -Force }
    Write-Ok "갱신용 압축파일 삭제"
}

# 2. 사이트 재생성 + 검증 (외부 도구 없이 jinja2만 사용)
if (-not $NoBuild) {
    $python = $null
    foreach ($cand in @("python", "py", "python3")) {
        if (Get-Command $cand -ErrorAction SilentlyContinue) { $python = $cand; break }
    }
    if (-not $python) { Write-Fail "Python을 찾을 수 없습니다."; exit 1 }

    Write-Step "2. 한글 카테고리 폴더 갱신"
    & $python "scripts\export_to_folders.py"
    if ($LASTEXITCODE -ne 0) { Write-Fail "폴더 내보내기 실패"; exit 1 }

    Write-Step "3. 사이트 재생성"
    & $python "scripts\build_site.py"
    if ($LASTEXITCODE -ne 0) { Write-Fail "사이트 생성 실패"; exit 1 }

    Write-Step "4. 최종 검증"
    & $python "scripts\validate_catalog.py" | Select-Object -Last 3
}

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$specCount = (Get-ChildItem "specs\*.yaml" -ErrorAction SilentlyContinue).Count
Write-Host ""
Write-Host ("=" * 74) -ForegroundColor DarkYellow
Write-Host ">>> update_forms.ps1 실행 완료 | $stamp KST | 서식 $specCount 종 | [로컬 작업] <<<" -ForegroundColor DarkYellow
Write-Host ("=" * 74) -ForegroundColor DarkYellow
