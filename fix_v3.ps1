# =====================================================================
#  [로컬 작업] 무료서식 다운로드 — 화면 결함 2건 수정 + 저장소 정리
#  사용법 : C:\Project_Forms 에서  .\fix_v3.ps1
#  고치는 것
#    (1) 검색 화면: 서식 요청 배너와 아래 분류 카드가 간격 없이 맞붙던 문제
#    (2) 상세 화면: 함께 찾는 서식 카드에 현재 서식의 분류가 잘못 붙던 문제
#    (3) 저장소에 딸려 올라간 이관용 압축본 제거 + .gitignore 보강
#  이후   : .\deploy_forms.ps1 -SkipBuild -Message "검색 배너 여백·연관 서식 분류 라벨 수정"
# =====================================================================
[CmdletBinding()]
param([string]$Archive = "fix_20260914.tar.gz")

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

function Step([string]$m) { Write-Host ""; Write-Host "── $m" -ForegroundColor Cyan }

Step "1/3  수정본 풀기 — $Archive"
if (-not (Test-Path $Archive)) {
    Write-Host "[중단] $Archive 가 없습니다." -ForegroundColor Red; exit 1
}
tar -xzf $Archive
if ($LASTEXITCODE -ne 0) { Write-Host "[중단] 압축 해제 실패." -ForegroundColor Red; exit 1 }
Write-Host "  templates/base.html · templates/form.html · .gitignore 갱신"

# 2) 지난 커밋에 딸려 올라간 이관용 압축본을 저장소에서만 뺀다.
#    --cached 라서 C:\Project_Forms 의 파일 자체는 지워지지 않는다.
Step "2/3  저장소에서 이관용 압축본 제거"
$removed = 0
foreach ($f in @("transfer_20260914.tar.gz")) {
    git ls-files --error-unmatch $f *> $null
    if ($LASTEXITCODE -eq 0) {
        git rm --cached $f *> $null
        Write-Host "  제거: $f (로컬 파일은 그대로 둡니다)"
        $removed++
    }
}
if ($removed -eq 0) { Write-Host "  제거할 항목 없음" }

Step "3/3  사이트 재생성 · 수정 확인"
python scripts/build_site.py
if ($LASTEXITCODE -ne 0) { Write-Host "[중단] build_site 실패." -ForegroundColor Red; exit 1 }

python -c @"
import re, pathlib
ok = True

# (1) 검색 배너 아래 여백
css = pathlib.Path('templates/base.html').read_text(encoding='utf-8')
m = re.search(r'\.reqbanner\{[^}]*margin:38px 0 26px', css, re.S)
print('  배너 아래 여백 26px :', '적용됨' if m else '미적용')
ok = ok and bool(m)

# (2) 연관 서식 카드의 분류 라벨 (자산 인수인계서 = 총무·행정)
h = pathlib.Path('public/form/resignation-letter/index.html').read_text(encoding='utf-8')
seg = h[h.find('함께 찾는 서식'):]
hit = dict(re.findall(r'class=\"name\" href=\"[^\"]+\">([^<]+)</a>\s*<div class=\"cat\">([^<]+)</div>', seg))
lab = hit.get('자산 인수인계서', '(없음)')
print('  자산 인수인계서 분류 :', lab)
ok = ok and ('총무' in lab)

raise SystemExit(0 if ok else 1)
"@
if ($LASTEXITCODE -ne 0) {
    Write-Host "[주의] 수정이 반영되지 않았습니다. 압축 해제가 제대로 됐는지 확인하십시오." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "수정 완료. 이어서 실행하십시오:" -ForegroundColor Green
Write-Host '  .\deploy_forms.ps1 -SkipBuild -Message "검색 배너 여백·연관 서식 분류 라벨 수정"'
Write-Host ""

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "════════ fix_v3.ps1 실행 완료 · $stamp ════════" -ForegroundColor DarkYellow
