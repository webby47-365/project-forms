# =====================================================================
#  [로컬 작업] 무료서식 다운로드 — 검증 → 커밋 → 푸시 → 배포 확인
#  사용법 : C:\Project_Forms 에서  .\deploy_forms.ps1
#  옵션   : .\deploy_forms.ps1 -Message "서식 3종 추가"
#           .\deploy_forms.ps1 -SkipBuild      (빌드 없이 검증·배포만)
#           .\deploy_forms.ps1 -Pull           (서버/에이전트 커밋을 로컬로 먼저 받기)
# =====================================================================
[CmdletBinding()]
param(
    [string]$Message = "",
    [switch]$SkipBuild,
    [switch]$Pull
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

# 콘솔 한글 출력 깨짐 방지
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

# 한글은 콘솔에서 2칸을 차지하므로 .Length로 구분선 길이를 계산하면 줄이 창 너비를
# 넘어가 글자가 겹쳐 보인다. 표시 폭을 계산하고 창 너비 안으로 제한한다.
function Get-DisplayWidth([string]$s) {
    $w = 0
    foreach ($ch in $s.ToCharArray()) {
        $c = [int]$ch
        if (($c -ge 0x1100 -and $c -le 0x115F) -or ($c -ge 0x2E80 -and $c -le 0xA4CF) -or
            ($c -ge 0xAC00 -and $c -le 0xD7A3) -or ($c -ge 0xF900 -and $c -le 0xFAFF) -or
            ($c -ge 0xFE30 -and $c -le 0xFE6F) -or ($c -ge 0xFF00 -and $c -le 0xFF60) -or
            ($c -ge 0xFFE0 -and $c -le 0xFFE6)) { $w += 2 } else { $w += 1 }
    }
    return $w
}
function Write-Step([string]$text) {
    $prefix = "── $text "
    $limit = 70
    try { $limit = [Math]::Max(24, $Host.UI.RawUI.WindowSize.Width - 2) } catch { }
    $pad = [Math]::Max(0, [Math]::Min(70, $limit) - (Get-DisplayWidth $prefix))
    Write-Host ""
    Write-Host $prefix -ForegroundColor Cyan -NoNewline
    Write-Host ("─" * $pad) -ForegroundColor DarkGray
}
function Write-Fail([string]$text) { Write-Host "  [실패] $text" -ForegroundColor Red }
function Write-Ok([string]$text)   { Write-Host "  [완료] $text" -ForegroundColor Green }

$python = $null
foreach ($cand in @("python", "py", "python3")) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) { $python = $cand; break }
}
if (-not $python) { Write-Fail "Python을 찾을 수 없습니다."; exit 1 }

# ── 0. 원격 변경 수신 (에이전트가 클라우드에서 커밋한 서식을 로컬 정본에 반영) ──
if ($Pull) {
    Write-Step "0. 원격 변경 수신 (git pull)"
    # 로컬에 커밋 안 된 변경이 있으면 rebase가 거부된다. 먼저 커밋해 둔다.
    $dirty = git status --porcelain
    if (-not [string]::IsNullOrWhiteSpace($dirty)) {
        Write-Host "  로컬 미커밋 변경을 먼저 커밋합니다." -ForegroundColor Gray
        git add -A
        git commit -m "chore: pull 전 로컬 변경 커밋" | Out-Null
    }
    git pull --rebase
    if ($LASTEXITCODE -ne 0) { Write-Fail "git pull 실패 — 충돌을 먼저 해결하십시오."; exit 1 }
    Write-Ok "로컬 정본을 최신 상태로 갱신"
}

# 서식 빌드에 필요한 외부 도구 확인 (없으면 빌드를 건너뛰고 사이트 갱신만 한다)
function Test-BuildTools {
    $ok = $true
    if (-not (Get-Command soffice -ErrorAction SilentlyContinue)) {
        if (-not (Test-Path "C:\Program Files\LibreOffice\program\soffice.exe")) { $ok = $false }
    }
    foreach ($t in @("pdftoppm", "pdfinfo", "pdftotext")) {
        if (-not (Get-Command $t -ErrorAction SilentlyContinue)) { $ok = $false }
    }
    return $ok
}

if (-not $SkipBuild -and -not (Test-BuildTools)) {
    Write-Host ""
    Write-Host "  LibreOffice 또는 Poppler가 없어 서식 빌드를 건너뜁니다." -ForegroundColor Yellow
    Write-Host "  (이미 만들어진 서식 파일을 그대로 사용합니다. 새 서식을 만들 때만 필요합니다)" -ForegroundColor DarkGray
    $SkipBuild = $true
}

# ── 1. 서식 빌드 ──
if (-not $SkipBuild) {
    Write-Step "1. 서식 빌드 (명세 → PDF·DOCX·HWPX·미리보기)"
    & $python "scripts\build_form.py"
    if ($LASTEXITCODE -ne 0) { Write-Fail "서식 빌드 실패"; exit 1 }
    Write-Ok "서식 빌드"
} else {
    Write-Step "1. 서식 빌드 — 건너뜀 (기존 서식 파일 사용)"
}

# ── 2. 사이트 생성 ──
Write-Step "2. 사이트 생성 (카탈로그 → HTML·검색인덱스·사이트맵)"
& $python "scripts\build_site.py"
if ($LASTEXITCODE -ne 0) { Write-Fail "사이트 생성 실패"; exit 1 }
Write-Ok "사이트 생성"

# ── 3. 최종 검증 ──
Write-Step "3. 최종 검증 (파일 실재·크기·분류·대표서식)"
& $python "scripts\validate_catalog.py"
if ($LASTEXITCODE -ne 0) { Write-Fail "검증 실패 — 배포를 중단합니다."; exit 1 }
Write-Ok "검증 통과"

# ── 4. 변경 확인 및 커밋 ──
Write-Step "4. 형상관리 (git)"
$changes = git status --porcelain
$pushed = $false
if ([string]::IsNullOrWhiteSpace($changes)) {
    Write-Host "  변경 사항이 없습니다. 커밋·푸시를 건너뜁니다." -ForegroundColor Yellow
} else {
    $count = ($changes -split "`n" | Where-Object { $_.Trim() -ne "" }).Count
    Write-Host "  변경 파일 $count 개" -ForegroundColor Gray
    if ([string]::IsNullOrWhiteSpace($Message)) {
        $formCount = (Get-ChildItem "specs\*.yaml").Count
        $Message = "chore(forms): 서식 $formCount 종 빌드·사이트 갱신"
    }
    git add -A
    git commit -m $Message
    if ($LASTEXITCODE -ne 0) { Write-Fail "커밋 실패"; exit 1 }
    Write-Ok "커밋: $Message"

    git push
    if ($LASTEXITCODE -ne 0) { Write-Fail "푸시 실패 — 원격 저장소 인증·연결을 확인하십시오."; exit 1 }
    Write-Ok "푸시 (GitHub Actions가 자동 배포합니다 · 약 1~2분)"
    $pushed = $true
}

# ── 5. 배포 확인 ──
Write-Step "5. 배포 확인"
$siteUrl = ""
$cfgPath = Join-Path $root "site.url"
if (Test-Path $cfgPath) { $siteUrl = (Get-Content $cfgPath -Raw).Trim() }

if ([string]::IsNullOrWhiteSpace($siteUrl)) {
    Write-Host "  site.url 파일이 없어 자동 확인을 건너뜁니다." -ForegroundColor Yellow
    Write-Host "  (사이트 주소를 site.url 파일에 한 줄로 적어두면 매번 자동 확인합니다)" -ForegroundColor DarkGray
} else {
    Write-Host "  배포 반영 대기 90초..." -ForegroundColor Gray
    Start-Sleep -Seconds 90
    $ok = 0; $fail = 0
    foreach ($path in @("/", "/sitemap.xml", "/search-index.json")) {
        try {
            $res = Invoke-WebRequest -Uri "$siteUrl$path" -Method Head -TimeoutSec 20 -UseBasicParsing
            if ($res.StatusCode -eq 200) { $ok++; Write-Host "    200  $path" -ForegroundColor DarkGreen }
            else { $fail++; Write-Host "    $($res.StatusCode)  $path" -ForegroundColor Yellow }
        } catch {
            $fail++; Write-Host "    실패 $path" -ForegroundColor Yellow
        }
    }
    if ($fail -eq 0) { Write-Ok "배포 확인 ($ok/3)" }
    else { Write-Host "  [주의] 일부 경로 확인 실패 — 저장소 Actions 탭의 배포 로그를 확인하십시오." -ForegroundColor Yellow }
}

# ── 6. IndexNow 통보 ──
# 빙·네이버·Yandex 등에 "새 페이지가 올라왔다"를 즉시 알린다(구글은 미지원).
# 배포가 끝난 뒤에 보내야 한다 — 키 파일이 사이트에 올라가 있어야 소유 증명이 된다.
# 바뀐 것이 없으면 보내지 않는다(같은 URL을 반복해 보내면 요청 제한에 걸린다).
if ($pushed) {
    Write-Step "6. IndexNow 통보 (빙·네이버)"
    & $python "scripts\ping_indexnow.py" --recent 5
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [주의] 통보에 실패했습니다. 검색 노출에는 영향이 없으니 다음 배포 때 다시 시도됩니다." -ForegroundColor Yellow
    } else {
        Write-Ok "IndexNow 통보"
    }
}

# ── 실행 구분선 ──
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$stampWidth = 74
try { $stampWidth = [Math]::Max(40, [Math]::Min(74, $Host.UI.RawUI.WindowSize.Width - 2)) } catch { }
$formCount = (Get-ChildItem "specs\*.yaml").Count
Write-Host ""
Write-Host ("=" * $stampWidth) -ForegroundColor DarkYellow
Write-Host ">>> deploy_forms.ps1 실행 완료 | $stamp KST | 서식 $formCount 종 | [로컬 작업] <<<" -ForegroundColor DarkYellow
Write-Host ("=" * $stampWidth) -ForegroundColor DarkYellow
