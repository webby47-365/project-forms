# =====================================================================
#  [로컬 작업] 무료서식 다운로드 — 저장소 정리
#  사용법 : C:\New_Business\01.FreeForms 에서  .\cleanup_repo.ps1
#
#  하는 일
#    1) 'Claude outputs' 폴더와 이관용 압축본을 git 추적에서 제외 (파일은 그대로 둔다)
#    2) 이름이 겹쳐 생긴 사본 update_forms-*.ps1 을 'Claude outputs' 로 치운다
#    3) 커밋 · 푸시
#
#  주의. 이미 커밋된 이력 안의 용량은 이 작업으로 사라지지 않는다.
#        앞으로 쌓이지 않게 막는 것이 목적이다. 이력까지 지우려면 git 이력을
#        다시 쓰는 별도 작업(filter-repo + force push)이 필요하며 위험이 크다.
# =====================================================================
[CmdletBinding()]
param([switch]$NoPush)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

function Write-Step([string]$t) {
    Write-Host ""
    Write-Host "== $t " -ForegroundColor Cyan -NoNewline
    Write-Host ("=" * [Math]::Max(0, 56 - $t.Length)) -ForegroundColor DarkGray
}
function Write-Ok([string]$t)   { Write-Host "  [완료] $t" -ForegroundColor Green }
function Write-Skip([string]$t) { Write-Host "  [건너뜀] $t" -ForegroundColor DarkGray }
function Write-Fail([string]$t) { Write-Host "  [실패] $t" -ForegroundColor Red }

if (-not (Test-Path (Join-Path $root ".git"))) {
    Write-Fail "여기는 git 저장소가 아닙니다. C:\New_Business\01.FreeForms 에서 실행하십시오."
    exit 1
}

# ── 1. 이름 겹침 사본을 형상관리 밖으로 치운다 ──────────────────────
Write-Step "1. 중복 사본 정리"
$outDir = Join-Path $root "Claude outputs"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
$dupes = @(Get-ChildItem -Path $root -Filter "update_forms-*.ps1" -File -ErrorAction SilentlyContinue)
if ($dupes.Count -eq 0) {
    Write-Skip "치울 중복 사본 없음"
} else {
    foreach ($d in $dupes) {
        Move-Item $d.FullName (Join-Path $outDir $d.Name) -Force
        Write-Ok "$($d.Name) → Claude outputs\ 로 이동"
    }
}

# ── 2. git 추적에서 제외 (작업 폴더의 파일은 지우지 않는다) ─────────
Write-Step "2. git 추적 해제"
$targets = @("Claude outputs", "update_forms-1.ps1", "update_forms-2.ps1")
$removed = 0
foreach ($t in $targets) {
    $tracked = @(git ls-files -- "$t" 2>$null)
    if ($tracked.Count -gt 0) {
        git rm -r --cached --quiet -- "$t"
        Write-Ok "$t ($($tracked.Count)개 파일) 추적 해제"
        $removed += $tracked.Count
    }
}
if ($removed -eq 0) { Write-Skip "이미 추적에서 빠져 있음" }

# ── 3. 커밋 · 푸시 ──────────────────────────────────────────────────
Write-Step "3. 커밋 · 푸시"
git add -A -- .gitignore
$staged = @(git diff --cached --name-only)
if ($staged.Count -eq 0) {
    Write-Skip "커밋할 변경 없음"
} else {
    git commit -q -m "chore(repo): 이관용 압축본·앱 사본을 형상관리에서 제외"
    Write-Ok "커밋 ($($staged.Count)개 항목)"
    if ($NoPush) {
        Write-Skip "푸시 생략 (-NoPush)"
    } else {
        git push
        if ($LASTEXITCODE -ne 0) { Write-Fail "푸시 실패"; exit 1 }
        Write-Ok "푸시"
    }
}

# ── 결과 ────────────────────────────────────────────────────────────
Write-Step "4. 확인"
$ignored = @("Claude outputs/update_forms_1_source.zip", "update_forms-1.ps1")
foreach ($f in $ignored) {
    $still = @(git ls-files -- "$f" 2>$null)
    if ($still.Count -eq 0) { Write-Ok "$f — 추적 안 함 (정상)" }
    else { Write-Fail "$f — 아직 추적 중" }
}

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host ""
Write-Host ("=" * 74) -ForegroundColor DarkYellow
Write-Host ">>> cleanup_repo.ps1 실행 완료 | $stamp KST | [로컬 작업] <<<" -ForegroundColor DarkYellow
Write-Host ("=" * 74) -ForegroundColor DarkYellow
