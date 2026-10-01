[가이드 검수] 2026-10-01 (목) KST
검수 대상 5편 · 공개 0 · 대기 4 · 내림 0 · 공개 가이드 15/15 · 이번 주 공개 0/3

공개 가능 수 = min(2, 3-0, 15-15) = 0 → 공개 한도(사이트 총 15편) 도달. 검수·수정만 하고 모두 draft 유지.

 1) 대기  guides/move-in-report-fixed-date.yaml — 신규 초안, 숫자 검증 불가로 미통과
    - 형식 검사 통과, build_site 알림 없음
    - 이번 실행 환경에서 easylaw.go.kr·gov.kr·law.go.kr 접속이 거부되어(ECONNREFUSED/timeout) 14일, 다음 날 0시 대항력, 확정일자 수수료 600원 등을 sources 에서 확인하지 못함
    - 확인하지 못한 문장을 삭제하면 글이 성립하지 않아 내용은 수정하지 않았고, updated_at·basis_date 도 갱신하지 않음. 접속 가능한 회차에 재검수
 2~5) 대기  sole-source-contract-guide, gift-limit-compliance, vehicle-ownership-transfer-registration, rental-car-insurance-checklist
    - 2026-09-28 검수 통과분. 이번 회차는 외부 접속 불가로 재확인하지 못했고 변경 없음. passed_waiting 유지

내린 글: 없음
검증: build_site.py / validate_catalog.py — 오류 0건
배포: 공개 전환 없음 → indexnow 생략
로컬 동기화 필요: .\sync_forms.ps1
