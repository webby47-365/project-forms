# =====================================================================
#  [로컬 작업] 무료서식 다운로드 — 최초 설치 (압축 해제 + 환경 점검)
#  사용법 : C:\New_Business\01.FreeForms 에서  .\setup_forms.ps1
#  이 스크립트는 한 번만 실행하면 됩니다. 이후 배포는 .\deploy_forms.ps1
# =====================================================================
[CmdletBinding()]
param(
    [string]$Bundle = "Project_Forms_bundle.zip",
    [switch]$KeepBundle
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

# 콘솔 한글 출력 깨짐 방지
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

function Write-Step([string]$t) {
    Write-Host ""
    Write-Host "── $t " -ForegroundColor Cyan -NoNewline
    Write-Host ("─" * [Math]::Max(0, 58 - $t.Length)) -ForegroundColor DarkGray
}
function Write-Ok([string]$t)   { Write-Host "  [완료] $t" -ForegroundColor Green }
function Write-Warn2([string]$t){ Write-Host "  [필요] $t" -ForegroundColor Yellow }
function Write-Fail([string]$t) { Write-Host "  [실패] $t" -ForegroundColor Red }

# ── 1. 압축 해제 ──
Write-Step "1. 프로젝트 파일 설치"
$zip = Join-Path $root $Bundle
if (-not (Test-Path $zip)) {
    Write-Fail "$Bundle 을 찾을 수 없습니다. 이 스크립트와 같은 폴더에 두십시오."
    exit 1
}
# Expand-Archive는 환경에 따라 한글 파일명을 깨뜨릴 수 있어 인코딩을 명시해 직접 푼다
Add-Type -AssemblyName System.IO.Compression.FileSystem
$utf8 = [System.Text.Encoding]::UTF8
$archive = [System.IO.Compression.ZipFile]::Open($zip, 'Read', $utf8)
try {
    foreach ($entry in $archive.Entries) {
        $dest = Join-Path $root $entry.FullName
        if ($entry.Name -eq '') {
            if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Force -Path $dest | Out-Null }
            continue
        }
        $dir = Split-Path $dest -Parent
        if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $dest, $true)
    }
} finally {
    $archive.Dispose()
}
$specCount = (Get-ChildItem (Join-Path $root "specs\*.yaml") -ErrorAction SilentlyContinue).Count
Write-Ok "압축 해제 — 서식 명세 $specCount 종"
if (-not $KeepBundle) {
    Remove-Item $zip -Force
    Write-Ok "설치용 압축파일 삭제"
}

# ── 2. Python 패키지 ──
Write-Step "2. Python 패키지 확인"
$python = $null
$pv = ""
foreach ($cand in @("python", "py", "python3")) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) {
        try {
            $out = & $cand --version 2>&1
            if ("$out" -match "Python") { $python = $cand; $pv = "$out"; break }
        } catch { }
    }
}
if (-not $python) {
    Write-Fail "Python을 찾을 수 없습니다. https://www.python.org 에서 설치 후 다시 실행하십시오."
    exit 1
}
Write-Host "  $python  ($pv)" -ForegroundColor Gray
& $python -m pip install --quiet --upgrade python-docx python-hwpx jinja2 pyyaml pillow
if ($LASTEXITCODE -ne 0) { Write-Fail "패키지 설치 실패"; exit 1 }
Write-Ok "python-docx · python-hwpx · jinja2 · pyyaml · pillow"

# ── 3. 외부 도구 확인 ──
Write-Step "3. 외부 도구 확인 (PDF 변환·미리보기)"
$need = @()

$soffice = Get-Command soffice -ErrorAction SilentlyContinue
if (-not $soffice) {
    $guess = "C:\Program Files\LibreOffice\program\soffice.exe"
    if (Test-Path $guess) {
        Write-Ok "LibreOffice 발견 (PATH 미등록 — 설치 경로로 자동 인식됩니다)"
    } else {
        $need += "LibreOffice  →  https://ko.libreoffice.org/download/  (PDF 변환에 필요)"
    }
} else { Write-Ok "LibreOffice (soffice)" }

foreach ($tool in @("pdftoppm", "pdfinfo", "pdftotext")) {
    if (Get-Command $tool -ErrorAction SilentlyContinue) { Write-Ok "$tool" }
    else { $need += "Poppler ($tool)  →  https://github.com/oschwartz10612/poppler-windows/releases  (미리보기·검수에 필요)" }
}

if (Get-Command git -ErrorAction SilentlyContinue) { Write-Ok "git" }
else { $need += "Git  →  https://git-scm.com/download/win  (GitHub 배포에 필요)" }

if ($need.Count -gt 0) {
    Write-Host ""
    Write-Host "  아래 도구를 설치한 뒤 이 스크립트를 다시 실행하십시오." -ForegroundColor Yellow
    foreach ($n in ($need | Select-Object -Unique)) { Write-Warn2 $n }
}

# ── 4. 동작 확인 ──
Write-Step "4. 동작 확인"
& $python "scripts\check_spec.py" | Select-Object -Last 2
if ($LASTEXITCODE -ne 0) { Write-Fail "명세 검사 실패"; exit 1 }
Write-Ok "명세 검사"

if ($need.Count -eq 0) {
    & $python "scripts\build_site.py" | Select-Object -Last 2
    if ($LASTEXITCODE -ne 0) { Write-Fail "사이트 생성 실패"; exit 1 }
    Write-Ok "사이트 생성"
    & $python "scripts\validate_catalog.py" | Select-Object -Last 2
    Write-Host ""
    Write-Host "  로컬에서 사이트를 보려면:" -ForegroundColor Gray
    Write-Host "    cd public; python -m http.server 8000    →  http://localhost:8000" -ForegroundColor White
} else {
    Write-Host "  외부 도구 설치 후 사이트 생성을 확인합니다." -ForegroundColor Yellow
}

# ── 다음 단계 안내 ──
Write-Step "다음 단계"
Write-Host "  1) GitHub 저장소 생성 후 연결" -ForegroundColor White
Write-Host "       git init; git add -A; git commit -m `"init: 무료서식 다운로드`"" -ForegroundColor Gray
Write-Host "       git branch -M main; git remote add origin <저장소 URL>; git push -u origin main" -ForegroundColor Gray
Write-Host "  2) Cloudflare Pages 연결 — _cloudflare_build.md 의 설정값을 그대로 입력" -ForegroundColor White
Write-Host "  3) 도메인 freeforms.kr 연결 (SITE_URL은 이미 반영되어 있습니다)" -ForegroundColor White
Write-Host "  4) 이후 배포는  .\deploy_forms.ps1  한 줄" -ForegroundColor White

# ── 실행 구분선 ──
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host ""
Write-Host ("=" * 74) -ForegroundColor DarkYellow
Write-Host ">>> setup_forms.ps1 실행 완료 | $stamp KST | 서식 $specCount 종 | [로컬 작업] <<<" -ForegroundColor DarkYellow
Write-Host ("=" * 74) -ForegroundColor DarkYellow
