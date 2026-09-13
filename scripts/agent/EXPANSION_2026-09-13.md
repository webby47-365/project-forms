# 서식 확충 계획 — 2026-09-13 (신규 120종)

## 방침

1. **변형 우선.** 네이버 한글 문서 서식처럼 하나의 서식을 실무 상황별 버전으로 나눈다.
   이력서 하나가 아니라 신입용·경력용·서술형·간편형·영문으로 나뉘어야 실제로 쓸모가 있다.
   같은 계열은 `series` / `series_name` / `variant` / `variant_rank`를 채워 묶는다.
2. **변형은 항목 구성이 실제로 달라야 한다.** 제목만 바꾼 같은 표는 만들지 않는다.
   신입용 이력서는 학력·대외활동·수상이 크고, 경력용은 경력기술·프로젝트가 커야 한다.
3. **모든 신규 서식에 미리보기 예시(sample)를 넣는다.** SPEC_GUIDE.md 3-1절 참조.

## 계열(series) 정의

| series | series_name | 포함 변형 |
|---|---|---|
| `resume` | 이력서 | 기본형(기존) · 신입용 · 경력용 · 서술형 · 간편형 · 영문 · 아르바이트용 |
| `cover-letter` | 자기소개서 | 기본형(기존) · 신입용 · 경력용 · 자유양식 · 항목형(STAR) |
| `career-desc` | 경력기술서 | 기본형(기존) · 프로젝트 중심 · 직무 중심 |
| `labor-contract` | 근로계약서 | 표준(기존) · 기간제(기존) · 단시간 · 일용직 · 연소근로자 |
| `resignation` | 사직서 | 기본형(기존) · 간편형 · 퇴직원 |
| `work-report` | 업무보고서 | 업무일지(기존) · 주간 · 월간 |
| `meeting-minutes` | 회의록 | 기본형(기존) · 간편형 · 주주총회 |
| `quotation` | 견적서 | 기본형(기존) · 간편형 · 상세형 |
| `certified-notice` | 내용증명 | 기본형(기존) · 대여금 반환 · 보증금 반환 · 계약해지 · 임금체불 |
| `complaint` | 소장 | 소액사건(기존) · 물품대금 · 대여금 |
| `privacy-consent` | 개인정보 동의서 | 기본형(기존) · 간편형 · 제3자 제공 · 마케팅 활용 |
| `household-budget` | 가계부 | 월간(기존) · 주간 · 연간 |
| `business-plan` | 사업계획서 | 표준형 · 간편형 |
| `lease` | 임대차계약서 | 주택(기존) · 상가(기존) · 갱신 · 전대차 · 주차장 |

## 신규 서식 120종

id는 모두 신규다. 기존 98종과 겹치지 않는지 `specs/` 목록을 확인하고 쓴다.

### A. 개인 · 취업·경력 (personal / career) — 14종

| id | title | series | variant | rank |
|---|---|---|---|---|
| resume-newcomer | 이력서 (신입용) | resume | 신입용 | 2 |
| resume-experienced | 이력서 (경력용) | resume | 경력용 | 3 |
| resume-narrative | 이력서 (서술형) | resume | 서술형 | 4 |
| resume-simple | 이력서 (간편형) | resume | 간편형 | 5 |
| resume-parttime | 이력서 (아르바이트용) | resume | 아르바이트용 | 6 |
| resume-english | 영문 이력서 (English Resume) | resume | 영문 | 7 |
| cover-letter-newcomer | 자기소개서 (신입용) | cover-letter | 신입용 | 2 |
| cover-letter-experienced | 자기소개서 (경력용) | cover-letter | 경력용 | 3 |
| cover-letter-free | 자기소개서 (자유양식) | cover-letter | 자유양식 | 4 |
| cover-letter-star | 자기소개서 (항목형·STAR) | cover-letter | 항목형 | 5 |
| career-desc-project | 경력기술서 (프로젝트 중심) | career-desc | 프로젝트 중심 | 2 |
| career-desc-job | 경력기술서 (직무 중심) | career-desc | 직무 중심 | 3 |
| job-application-form | 입사지원서 | | | |
| reference-check-consent | 평판조회 동의서 | | | |

### B. 기업 · 인사·노무 (corp / hr) — 15종

| id | title | series | variant | rank |
|---|---|---|---|---|
| labor-contract-parttime | 단시간 근로계약서 | labor-contract | 단시간 | 3 |
| labor-contract-daily | 일용직 근로계약서 | labor-contract | 일용직 | 4 |
| labor-contract-minor | 연소근로자 근로계약서 | labor-contract | 연소근로자 | 5 |
| resignation-simple | 사직서 (간편형) | resignation | 간편형 | 2 |
| retirement-application | 퇴직원 | resignation | 퇴직원 | 3 |
| handover-report | 업무 인수인계서 | | | |
| overtime-application | 연장·휴일근로 신청서 | | | |
| parental-leave-request | 육아휴직 신청서 | | | |
| disciplinary-notice | 징계 통보서 | | | |
| explanation-statement | 경위서 | | | |
| probation-evaluation | 수습 평가서 | | | |
| performance-evaluation | 인사고과표 | | | |
| mbo-sheet | 목표관리(MBO) 평가표 | | | |
| job-description | 직무기술서 | | | |
| interview-evaluation | 면접 평가표 | | | |

### C. 기업 · 총무·행정 (corp / admin) — 13종

| id | title | series | variant | rank |
|---|---|---|---|---|
| meeting-minutes-simple | 회의록 (간편형) | meeting-minutes | 간편형 | 2 |
| work-report-weekly | 주간업무보고서 | work-report | 주간 | 2 |
| work-report-monthly | 월간업무보고서 | work-report | 월간 | 3 |
| business-trip-report | 출장 보고서 | | | |
| asset-ledger | 비품 관리대장 | | | |
| document-register | 문서 수발대장 | | | |
| seal-usage-log | 법인인감 사용대장 | | | |
| visitor-log | 방문자 기록대장 | | | |
| facility-repair-request | 시설물 수리 요청서 | | | |
| vehicle-use-request | 업무용 차량 사용 신청서 | | | |
| internal-announcement | 사내 공지문 | | | |
| event-plan | 행사 기획서 | | | |
| asset-handover | 자산 인수인계서 | | | |

### D. 기업 · 회계·세무 (corp / finance) — 11종

| id | title | series | variant | rank |
|---|---|---|---|---|
| quotation-simple | 견적서 (간편형) | quotation | 간편형 | 2 |
| quotation-detailed | 견적서 (상세형) | quotation | 상세형 | 3 |
| invoice-request | 청구서 | | | |
| budget-plan | 예산 계획서 | | | |
| budget-execution | 예산 집행 내역서 | | | |
| account-ledger | 거래처 원장 | | | |
| balance-confirmation | 채권·채무 잔액확인서 | | | |
| withholding-request | 원천징수영수증 발급 요청서 | | | |
| year-end-tax-checklist | 연말정산 서류 점검표 | | | |
| depreciation-schedule | 감가상각 내역서 | | | |
| petty-cash-ledger | 소액현금 출납장 | | | |

### E. 기업 · 영업·마케팅 (corp / sales) — 9종

| id | title |
|---|---|
| sales-plan | 영업 계획서 |
| sales-daily-log | 영업일지 |
| customer-card | 고객관리 카드 |
| client-visit-report | 고객 방문 보고서 |
| complaint-handling | 고객 불만 처리서 |
| marketing-plan | 마케팅 기획서 |
| campaign-result | 캠페인 결과 보고서 |
| quotation-comparison | 견적 비교표 |
| distributor-contract | 대리점 계약서 |

### F. 기업 · 창업·법인 (corp / startup) — 7종

| id | title | series | variant | rank |
|---|---|---|---|---|
| business-plan-standard | 사업계획서 (표준형) | business-plan | 표준형 | 1 |
| business-plan-simple | 사업계획서 (간편형) | business-plan | 간편형 | 2 |
| shareholder-meeting-minutes | 주주총회 의사록 | meeting-minutes | 주주총회 | 3 |
| stock-transfer-contract | 주식 양도양수 계약서 | | | |
| director-acceptance | 취임 승낙서 | | | |
| startup-checklist | 창업 준비 체크리스트 | | | |
| business-reg-checklist | 사업자등록 준비 체크리스트 | | | |

### G. 법률 · 계약 (legal / contract) — 10종

| id | title | series | variant | rank |
|---|---|---|---|---|
| service-contract-simple | 용역계약서 (간편형) | | | |
| consulting-contract | 컨설팅 계약서 | | | |
| license-contract | 상표·저작물 사용허락 계약서 | | | |
| franchise-contract | 가맹계약서 | | | |
| loan-note-simple | 차용증 (간편형) | | | |
| loan-note-guaranteed | 차용증 (연대보증 포함) | | | |
| used-car-sale-contract | 중고차 매매계약서 | | | |
| equipment-lease-contract | 장비 임대차계약서 | | | |
| subcontract-agreement | 하도급 계약서 | | | |
| mou-agreement | 업무협약서 (MOU) | | | |

### H. 법률 · 통지·증명 (legal / notice) — 7종

| id | title | series | variant | rank |
|---|---|---|---|---|
| certified-notice-loan | 내용증명 (대여금 반환청구) | certified-notice | 대여금 반환 | 2 |
| certified-notice-deposit | 내용증명 (보증금 반환청구) | certified-notice | 보증금 반환 | 3 |
| certified-notice-terminate | 내용증명 (계약 해지 통보) | certified-notice | 계약 해지 | 4 |
| certified-notice-wage | 내용증명 (임금체불 청구) | certified-notice | 임금체불 | 5 |
| repayment-plan | 채무 변제계획서 | | | |
| quitclaim-letter | 권리포기 각서 | | | |
| delegation-revocation | 위임 해지 통지서 | | | |

### I. 법률 · 소송·민원 (legal / litigation) — 6종

| id | title | series | variant | rank |
|---|---|---|---|---|
| complaint-goods-payment | 소장 (물품대금 청구) | complaint | 물품대금 | 2 |
| complaint-loan-return | 소장 (대여금 반환청구) | complaint | 대여금 | 3 |
| answer-brief | 답변서 | | | |
| preparatory-brief | 준비서면 | | | |
| civil-conciliation | 민사조정 신청서 | | | |
| written-statement | 진술서 | | | |

### J. 공공 · 민원·신고 (public / civil) — 5종

| id | title |
|---|---|
| parking-fine-objection | 주차위반 과태료 이의신청서 |
| noise-complaint | 층간소음 민원 신청서 |
| road-repair-request | 도로·가로등 보수 요청 민원 |
| disclosure-objection | 정보공개 이의신청서 |
| illegal-dumping-report | 불법투기 신고서 |

### K. 공공 · 신청·동의 (public / consent) — 5종

| id | title | series | variant | rank |
|---|---|---|---|---|
| privacy-consent-simple | 개인정보 수집·이용 동의서 (간편형) | privacy-consent | 간편형 | 2 |
| privacy-consent-third | 개인정보 제3자 제공 동의서 | privacy-consent | 제3자 제공 | 3 |
| privacy-consent-marketing | 마케팅 활용 동의서 | privacy-consent | 마케팅 | 4 |
| event-photo-consent | 행사 사진·영상 활용 동의서 | | | |
| minor-activity-consent | 미성년자 활동 보호자 동의서 | | | |

### L. 부동산 · 임대·매매 (estate / lease) — 8종

| id | title | series | variant | rank |
|---|---|---|---|---|
| lease-renewal-contract | 임대차 계약 갱신계약서 | lease | 갱신 | 3 |
| sublease-contract | 전대차 계약서 | lease | 전대차 | 4 |
| parking-lease-contract | 주차장 임대차계약서 | lease | 주차장 | 5 |
| monthly-rent-receipt | 월세 영수증 | | | |
| lease-transfer-contract | 임차권 양도계약서 | | | |
| move-in-checklist | 입주 점검표 | | | |
| deposit-return-notice | 전세보증금 반환 내용증명 | | | |
| property-viewing-log | 부동산 임장 기록표 | | | |

### M. 개인 · 생활·가정 (personal / life) — 9종

| id | title | series | variant | rank |
|---|---|---|---|---|
| household-budget-weekly | 가계부 (주간) | household-budget | 주간 | 2 |
| household-budget-yearly | 가계부 (연간) | household-budget | 연간 | 3 |
| family-event-notice | 경조사 안내문 | | | |
| thank-you-letter | 감사장 | | | |
| car-accident-settlement | 교통사고 합의서 | | | |
| pet-adoption-contract | 반려동물 분양 계약서 | | | |
| gift-contract | 증여계약서 | | | |
| will-form | 자필유언장 양식 | | | |
| monthly-schedule | 월간 일정표 | | | |

### N. 교육 · 학교·학원 (edu / school) — 10종

| id | title |
|---|---|
| student-record-card | 학생 생활기록 카드 |
| lesson-plan | 수업 지도안 |
| weekly-study-plan | 주간 학습계획표 |
| reading-log | 독서기록장 |
| grade-report | 성적 통지표 |
| club-activity-record | 동아리 활동 기록부 |
| scholarship-application | 장학금 신청서 |
| teacher-recommendation | 교사 추천서 |
| tuition-refund-request | 수강료 환불 신청서 |
| academy-attendance | 학원 출결 관리표 |

### O. 의료·복지 · 동의·신청 (welfare / consent) — 8종

| id | title |
|---|---|
| surgery-consent | 수술·시술 동의서 |
| medical-record-request | 진료기록 사본 발급 신청서 |
| caregiver-contract | 간병인 계약서 |
| long-term-care-application | 장기요양 급여 신청서 |
| welfare-facility-application | 복지시설 이용 신청서 |
| medical-expense-support | 의료비 지원 신청서 |
| vaccination-consent | 예방접종 동의서 |
| hospital-transfer-request | 전원(轉院) 요청서 |

---

합계 14+15+13+11+9+7+10+7+6+5+5+8+9+10+8 = **137종**
(초과분은 품질 미달 시 제외해도 목표 100종을 넘긴다)
