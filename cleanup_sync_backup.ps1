# cleanup_sync_backup.ps1 — 저장소에 잘못 들어간 백업 폴더를 걷어낸다 [로컬 작업]
#
# sync_forms.ps1 이 백업을 저장소 안(_sync_backup_날짜시각)에 만드는 바람에
# deploy_forms.ps1 이 그것까지 커밋했다. 파일은 디스크에 남기고 추적만 끊은 뒤,
# 확인 후 폴더를 지운다. public/ 은 건드리지 않으므로 사이트는 그대로다.

$ErrorActionPreference = 'Stop'
Set-Location 'C:\New_Business\01.FreeForms'

function Line($t) { Write-Host ("`n== " + $t + " " + ("=" * [Math]::Max(0, 58 - $t.Length))) -ForegroundColor Cyan }

Line '1. 저장소에 들어간 백업 폴더 확인'
$tracked = git ls-files '_sync_backup_*' 
if (-not $tracked) {
  Write-Host '  추적 중인 백업 폴더가 없습니다. 이미 정리됐습니다.' -ForegroundColor Yellow
} else {
  Write-Host ('  추적 중인 파일 ' + ($tracked | Measure-Object).Count + '개')
}

Line '2. 추적 해제 (디스크의 파일은 그대로 둔다)'
if ($tracked) {
  git rm -r --cached --quiet -- '_sync_backup_*'
  Write-Host '  [완료] git 추적에서 제외'
}

Line '3. .gitignore 확인'
if (Select-String -Path '.gitignore' -Pattern '_sync_backup_' -Quiet) {
  Write-Host '  [완료] .gitignore 에 차단 규칙 있음'
} else {
  Write-Host '  [경고] .gitignore 에 규칙이 없습니다 — 클로드에게 알려 주세요' -ForegroundColor Red
}

Line '4. 커밋 · 푸시'
git add -A
git commit -m 'chore: 저장소에서 sync 백업 폴더 제외(.gitignore)' | Out-Host
git push | Out-Host

Line '5. 디스크의 백업 폴더'
$dirs = Get-ChildItem -Directory -Filter '_sync_backup_*' -ErrorAction SilentlyContinue
if ($dirs) {
  foreach ($d in $dirs) { Write-Host ('  남아 있음: ' + $d.FullName) }
  Write-Host '  사이트가 정상인 것을 확인했으면 위 폴더를 지우세요:' -ForegroundColor Yellow
  Write-Host '    Remove-Item -Recurse -Force _sync_backup_*' -ForegroundColor Yellow
} else {
  Write-Host '  남아 있는 백업 폴더 없음'
}

Write-Host ''
Write-Host ('=' * 74) -ForegroundColor DarkYellow
Write-Host (">>> cleanup_sync_backup.ps1 실행 완료 | " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + " KST | [로컬 작업] <<<") -ForegroundColor DarkYellow
Write-Host ('=' * 74) -ForegroundColor DarkYellow
