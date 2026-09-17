# =====================================================================
#  [로컬 작업] 무료서식 다운로드 — 연관 서식(related) + 주제 모음(collection) 적용
#  사용법 : C:\New_Business\01.FreeForms 에서  .\apply_v3.ps1
#  하는 일: 1) 원격(에이전트) 커밋 먼저 받기
#           2) 전송본 압축 풀기 (specs 239종 + 템플릿 + 스크립트)
#           3) ads.json에 collection_bottom 슬롯 추가 (기존 설정은 보존)
#           4) 카탈로그 글 필드 동기화 → 사이트 재생성 → 명세 검사
#  이후   : .\deploy_forms.ps1 -SkipBuild -Message "연관 서식·주제 모음 추가"
# =====================================================================
[CmdletBinding()]
param(
    [string]$Archive = "transfer_20260914.tar.gz",
    [switch]$NoPull
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

function Step([string]$msg) {
    Write-Host ""
    Write-Host "── $msg" -ForegroundColor Cyan
}

# 1) 원격 커밋 먼저 받기 — 매일 아침 에이전트가 올린 서식을 덮어쓰지 않기 위해서다.
if (-not $NoPull) {
    Step "1/5  원격 커밋 받기 (git pull)"
    git pull --rebase
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[중단] git pull 실패 — 충돌을 정리한 뒤 다시 실행하십시오." -ForegroundColor Red
        exit 1
    }
} else {
    Step "1/5  git pull 건너뜀 (-NoPull)"
}

# 2) 전송본 풀기
Step "2/5  전송본 풀기 — $Archive"
if (-not (Test-Path $Archive)) {
    Write-Host "[중단] $Archive 파일이 $root 에 없습니다." -ForegroundColor Red
    exit 1
}
tar -xzf $Archive
if ($LASTEXITCODE -ne 0) {
    Write-Host "[중단] 압축 해제 실패." -ForegroundColor Red
    exit 1
}
Write-Host "  specs 239종 · templates 4개 · scripts 8개 갱신"

# 3) 광고 슬롯 추가 — ads.json을 통째로 덮지 않고 없는 키만 넣는다.
#    (승인 후 client/슬롯 ID를 넣어 두었을 수 있으므로 기존 값은 그대로 둔다)
Step "3/5  ads.json에 collection_bottom 슬롯 추가"
python -c @"
import json, pathlib
p = pathlib.Path('catalog/ads.json')
d = json.loads(p.read_text(encoding='utf-8'))
added = False
if 'collection_bottom' not in d.get('slots', {}):
    d['slots']['collection_bottom'] = ''
    added = True
if 'collection_bottom' not in d.get('_slots_guide', {}):
    d['_slots_guide']['collection_bottom'] = '주제 모음 목록 아래 (가로 반응형)'
    added = True
if added:
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('  슬롯 추가 완료')
else:
    print('  이미 있음 — 변경 없음')
"@
if ($LASTEXITCODE -ne 0) { Write-Host "[중단] ads.json 처리 실패." -ForegroundColor Red; exit 1 }

# 4) 카탈로그 글 필드 동기화 → 사이트 재생성
#    related는 '글' 필드라 파일(PDF·DOCX·HWPX)을 다시 만들 필요가 없다.
Step "4/5  카탈로그 동기화 · 사이트 재생성"
python scripts/sync_meta.py
if ($LASTEXITCODE -ne 0) { Write-Host "[중단] sync_meta 실패." -ForegroundColor Red; exit 1 }
python scripts/build_site.py
if ($LASTEXITCODE -ne 0) { Write-Host "[중단] build_site 실패." -ForegroundColor Red; exit 1 }

# 5) 명세 검사 — related 규칙(2~4개·없는 id·같은 계열)을 여기서 잡는다.
Step "5/5  명세 검사"
python scripts/check_spec.py | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) {
    Write-Host "[주의] 검사에서 문제가 나왔습니다. 위 내용을 확인하십시오." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "적용 완료. 확인 후 아래를 실행하십시오:" -ForegroundColor Green
Write-Host '  .\deploy_forms.ps1 -SkipBuild -Message "연관 서식·주제 모음 추가"'
Write-Host ""

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "════════ apply_v3.ps1 실행 완료 · $stamp ════════" -ForegroundColor DarkYellow
