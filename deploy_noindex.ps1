# =====================================================================
#  [로컬 작업] 구글 색인 정체 해소 — 조합 페이지 noindex + 사이트맵 제외 + 홈 타이틀 고정
#  작업지시서: claude/작업지시서_구글색인정체_20260919.md (2026-09-19)
#  범위       : 작업 1(조합 페이지 noindex) · 작업 2(사이트맵 제외) · 작업 3(홈 타이틀 고정)
#  사용법     : C:\New_Business\01.FreeForms 에서  .\deploy_noindex.ps1
#  옵션       : .\deploy_noindex.ps1 -Message "메시지"
#               .\deploy_noindex.ps1 -DryRun     (빌드·검증만, 커밋·푸시 안 함)
#
#  하는 일 (deploy_forms.ps1과 달리 서식 빌드(build_form.py)는 건너뜁니다 —
#           이번 작업은 명세(specs)를 건드리지 않고 사이트 생성 로직만 고쳤습니다):
#    1. 사이트 생성 (scripts\build_site.py) — 조합 페이지 noindex 메타, 사이트맵 제외,
#       홈 타이틀 고정이 이 단계에서 전 페이지에 반영됩니다.
#    2. 최종 검증 (scripts\validate_catalog.py)
#    3. git 커밋 · 푸시 (GitHub Actions가 자동 배포, 약 1~2분)
#    4. 배포 확인 (홈 HEAD 200 확인)
# =====================================================================
[CmdletBinding()]
param(
    [string]$Message = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

# 콘솔 한글 출력 깨짐 방지
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

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

# ── 1. 사이트 생성 (서식 빌드는 건너뜀 — 명세 변경 없음) ──
Write-Step "1. 사이트 생성 (카탈로그 → HTML·사이트맵·robots.txt)"
& $python "scripts\build_site.py"
if ($LASTEXITCODE -ne 0) { Write-Fail "사이트 생성 실패"; exit 1 }
Write-Ok "사이트 생성"

# 사이트맵 검증 — 절대 개수(작업지시서의 518→357)는 서식이 매일 자동 추가되어 계속 변하므로
# 고정값으로 막지 않는다. 대신 "조합 URL이 정확히 0개인가"·"허브 6개가 모두 있는가"로 확인한다.
$sitemapCount = (Select-String -Path "public\sitemap.xml" -Pattern "<url>" -AllMatches).Matches.Count
$comboLeft = (Select-String -Path "public\sitemap.xml" -Pattern '/tools/(salary|severance)/\d+/' -AllMatches).Matches.Count
Write-Host "  사이트맵 URL 수: $sitemapCount 개 (참고용 — 서식이 매일 늘어 절대값은 매번 다를 수 있음)" -ForegroundColor Gray
if ($comboLeft -ne 0) {
    Write-Fail "사이트맵에 조합 URL이 $comboLeft 개 남아 있습니다 — 배포를 중단합니다."
    exit 1
}
$hubPaths = @("/tools/</loc>", "/tools/stamp/</loc>", "/tools/salary/</loc>", "/tools/severance/</loc>",
              "/tools/annual-leave/</loc>", "/tools/retirement-tax/</loc>")
$missingHub = $hubPaths | Where-Object { -not (Select-String -Path "public\sitemap.xml" -Pattern ([regex]::Escape($_)) -Quiet) }
if ($missingHub) {
    Write-Fail ("허브 URL이 사이트맵에서 빠졌습니다: " + ($missingHub -join ", "))
    exit 1
}
Write-Ok "조합 URL 0개 확인 · 허브 6개 전부 존재 확인"

# 조합 페이지에 noindex가 실제로 박혔는지 로컬 파일로 즉석 확인
$sample1 = Select-String -Path "public\tools\salary\3000\index.html" -Pattern 'name="robots" content="noindex' -Quiet
$sample2 = Select-String -Path "public\tools\severance\10\index.html" -Pattern 'name="robots" content="noindex' -Quiet
$hubCheck = Select-String -Path "public\tools\salary\index.html" -Pattern 'name="robots" content="noindex' -Quiet
if (-not $sample1 -or -not $sample2) {
    Write-Fail "조합 페이지에 noindex 메타가 없습니다 — 배포를 중단합니다."
    exit 1
}
if ($hubCheck) {
    Write-Fail "허브 페이지(/tools/salary/)에 noindex가 잘못 들어갔습니다 — 배포를 중단합니다."
    exit 1
}
Write-Ok "조합 페이지 noindex 확인 · 허브 페이지 미적용 확인"

if ($DryRun) {
    Write-Step "DryRun — 커밋·푸시를 건너뜁니다"
    Write-Host "  scripts\build_site.py 결과만 public\ 에 반영되었습니다. 배포하려면 -DryRun 없이 다시 실행하십시오." -ForegroundColor Yellow
} else {
    # ── 2. 최종 검증 ──
    Write-Step "2. 최종 검증 (파일 실재·크기·분류·대표서식)"
    & $python "scripts\validate_catalog.py"
    if ($LASTEXITCODE -ne 0) { Write-Fail "검증 실패 — 배포를 중단합니다."; exit 1 }
    Write-Ok "검증 통과"

    # ── 3. 커밋 · 푸시 ──
    Write-Step "3. 형상관리 (git)"
    $changes = git status --porcelain
    $pushed = $false
    if ([string]::IsNullOrWhiteSpace($changes)) {
        Write-Host "  변경 사항이 없습니다. 커밋·푸시를 건너뜁니다." -ForegroundColor Yellow
    } else {
        $count = ($changes -split "`n" | Where-Object { $_.Trim() -ne "" }).Count
        Write-Host "  변경 파일 $count 개" -ForegroundColor Gray
        if ([string]::IsNullOrWhiteSpace($Message)) {
            $Message = "fix(seo): 조합 페이지 noindex + 사이트맵 제외 + 홈 타이틀 고정 (구글 색인 정체 해소)"
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

    # ── 4. 배포 확인 ──
    Write-Step "4. 배포 확인"
    $siteUrl = ""
    $cfgPath = Join-Path $root "site.url"
    if (Test-Path $cfgPath) { $siteUrl = (Get-Content $cfgPath -Raw).Trim() }
    if ([string]::IsNullOrWhiteSpace($siteUrl)) {
        Write-Host "  site.url 파일이 없어 자동 확인을 건너뜁니다." -ForegroundColor Yellow
    } elseif ($pushed) {
        Write-Host "  배포 반영 대기 90초..." -ForegroundColor Gray
        Start-Sleep -Seconds 90
        foreach ($path in @("/", "/sitemap.xml", "/tools/salary/3000/", "/tools/severance/10/")) {
            try {
                $res = Invoke-WebRequest -Uri "$siteUrl$path" -Method Head -TimeoutSec 20 -UseBasicParsing
                if ($res.StatusCode -eq 200) { Write-Host "    200  $path" -ForegroundColor DarkGreen }
                else { Write-Host "    $($res.StatusCode)  $path" -ForegroundColor Yellow }
            } catch {
                Write-Host "    실패 $path" -ForegroundColor Yellow
            }
        }
        Write-Ok "배포 확인"
        Write-Host "  상위 세션에서 curl 검증 1~6을 이어서 진행합니다." -ForegroundColor Gray
    } else {
        Write-Host "  푸시된 변경이 없어 배포 확인을 건너뜁니다." -ForegroundColor Yellow
    }
}

# ── 실행 구분선 ──
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$stampWidth = 74
try { $stampWidth = [Math]::Max(40, [Math]::Min(74, $Host.UI.RawUI.WindowSize.Width - 2)) } catch { }
Write-Host ""
Write-Host ("=" * $stampWidth) -ForegroundColor DarkYellow
Write-Host ">>> deploy_noindex.ps1 실행 완료 | $stamp KST | 구글 색인 정체 해소(작업 1~3) | [로컬 작업] <<<" -ForegroundColor DarkYellow
Write-Host ("=" * $stampWidth) -ForegroundColor DarkYellow
