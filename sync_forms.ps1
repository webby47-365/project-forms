# sync_forms.ps1 — 원격(일일 에이전트) 커밋과 로컬 작업을 합치고 배포까지 한 번에
#
# [언제 쓰나]
#   deploy_forms.ps1 의 푸시가 "non-fast-forward / tip of your current branch is behind" 로 거부될 때.
#   GitHub Actions 일일 에이전트가 서식을 추가해 원격이 앞서 있고, 로컬에도 내 커밋이 있어 갈라진 상태다.
#
# [무엇을 하나]
#   0) 현재 로컬·원격 커밋을 보여 준다
#   1) 소스 폴더를 통째로 백업한다 (_sync_backup_날짜시각)
#   2) 원격 위로 내 커밋을 다시 얹는다(rebase). public/ 같은 생성물이 충돌하면 원격 것을 쓴다 —
#      어차피 3)에서 다시 만든다. templates/·scripts/·assets/ 의 내 수정은 충돌 없이 그대로 남는다
#   3) deploy_forms.ps1 을 불러 재빌드 → 검증 → 커밋 → 푸시 → 배포 확인까지 마친다
#
# [로컬 작업]  실행:  .\sync_forms.ps1

$ErrorActionPreference = 'Stop'
Set-Location 'C:\Project_Forms'

function Line($t) { Write-Host ("`n── " + $t + " " + ("─" * [Math]::Max(0, 60 - $t.Length))) -ForegroundColor Cyan }

Line '0. 현재 상태'
git fetch origin
$local  = (git rev-parse --short HEAD).Trim()
$remote = (git rev-parse --short origin/main).Trim()
Write-Host ("  로컬  : " + $local + "  " + (git log -1 --pretty=%s HEAD))
Write-Host ("  원격  : " + $remote + "  " + (git log -1 --pretty=%s origin/main))

$behind = (git rev-list --count "HEAD..origin/main").Trim()
$ahead  = (git rev-list --count "origin/main..HEAD").Trim()
Write-Host ("  원격에만 있는 커밋 " + $behind + "개 · 로컬에만 있는 커밋 " + $ahead + "개")

if ($behind -eq '0') {
  Write-Host "`n  원격에 새 커밋이 없습니다. 이 스크립트는 필요 없고 .\deploy_forms.ps1 만 실행하면 됩니다." -ForegroundColor Yellow
  exit 0
}

Line '1. 안전 백업'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$bk = "C:\Project_Forms\_sync_backup_$stamp"
New-Item -ItemType Directory -Path $bk -Force | Out-Null
foreach ($d in @('templates', 'scripts', 'assets', 'catalog')) {
  robocopy $d "$bk\$d" /E /NFL /NDL /NJH /NJS /NC /NS | Out-Null
}
Get-ChildItem -Path . -Filter '*.md' -File | Copy-Item -Destination $bk -Force
Write-Host ("  백업 위치: " + $bk)
Write-Host "  (합치기가 잘못되면 이 폴더의 파일을 되돌리면 됩니다. 확인 후 지우세요)"

Line '2. 원격 위로 내 커밋 다시 얹기'
# -X ours : 충돌한 덩어리는 '원격(원래 있던 것)' 쪽을 쓴다. 생성물(public/·catalog)이 여기 해당한다.
#           내가 고친 templates/·scripts/·assets/ 파일은 원격이 건드리지 않았으므로 충돌 없이 남는다.
git rebase origin/main -X ours
if ($LASTEXITCODE -ne 0) {
  Write-Host "`n  [중단] 자동으로 합치지 못했습니다." -ForegroundColor Red
  Write-Host "  git rebase --abort 로 되돌린 뒤, 이 화면을 그대로 클로드에게 보여 주세요." -ForegroundColor Red
  exit 1
}
Write-Host ("  [완료] 합치기 성공 — 현재 " + (git rev-parse --short HEAD).Trim())

Line '3. 재빌드 · 검증 · 커밋 · 푸시'
# 생성물을 원격 것으로 되돌렸으므로 -SkipBuild 를 쓰지 않고 사이트를 새로 만든다.
& '.\deploy_forms.ps1' -Message 'chore: 원격 에이전트 커밋과 로컬 작업 병합 후 재배포'

Write-Host ''
Write-Host ('=' * 74) -ForegroundColor DarkYellow
Write-Host (">>> sync_forms.ps1 실행 완료 | " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + " KST | 백업 " + $stamp + " | [로컬 작업] <<<") -ForegroundColor DarkYellow
Write-Host ('=' * 74) -ForegroundColor DarkYellow
