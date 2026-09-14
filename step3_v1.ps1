# =====================================================================
#  [로컬 작업] 이 스크립트는 더 이상 실행할 것이 없습니다 (2026-09-14 병합 완료)
#  원래 내용(다운로드 준비 페이지 / 검색 배너·연관 서식 수정)은 도장·서명 생성기 작업 때
#  templates·scripts에 이미 합쳐졌습니다. 옛 압축본으로 덮어쓰면 오늘 작업이 되돌아가므로
#  실제 적용 코드는 제거했습니다. 이 파일과 fix_20260914.tar.gz · step3_20260914.tar.gz 는 지워도 됩니다.
# =====================================================================
Write-Host ""
Write-Host "  이 스크립트는 2026-09-14 도장·서명 생성기 작업에 병합되어 실행할 것이 없습니다." -ForegroundColor Yellow
Write-Host "  배포는  .\deploy_forms.ps1 -SkipBuild  로 하십시오." -ForegroundColor Yellow
Write-Host ""
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host ("=" * 74) -ForegroundColor DarkYellow
Write-Host ">>> step3_v1.ps1 (병합 완료 · 실행 없음) | $stamp KST | [로컬 작업] <<<" -ForegroundColor DarkYellow
Write-Host ("=" * 74) -ForegroundColor DarkYellow
