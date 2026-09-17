# 서식 명세 36종 작성 보고서

- 작업일자: 2026-09-13
- 작업 범위: `C:\New_Business\01.FreeForms\specs\` 신규 명세 36종 작성
- 작업 제외: 빌드·최종검증 (build_form.py / build_site.py / fit_one_page.py / validate_catalog.py 미실행, catalog.json 미수정)

## 1. 작성 완료 id 목록 (36/36)

### 기업 — 인사·노무 (corp/hr) 5종
| id | title | target_pages |
|---|---|---|
| fixed-term-labor-contract | 근로계약서 (기간제) | 2 |
| severance-calculation | 퇴직금 정산서 | 1 |
| written-apology | 시말서 | 1 |
| remote-work-request | 재택근무 신청서 | 1 |
| training-certificate | 교육훈련 참가확인서 | 1 |

### 기업 — 총무·행정 (corp/admin) 4종
| id | title | target_pages |
|---|---|---|
| cooperation-request | 협조전 | 1 |
| internal-memo | 내부 보고서 | 1 |
| business-card-request | 명함신청서 | 1 |
| access-pass-request | 출입증 신청서 | 1 |

### 기업 — 회계·세무 (corp/finance) 4종
| id | title | target_pages |
|---|---|---|
| tax-invoice | 세금계산서 (수기) | 1 |
| daily-cash-report | 자금일보 | 1 |
| corporate-card-report | 법인카드 사용내역서 | 1 |
| payment-confirmation | 입금확인서 | 1 |

### 법률 — 계약 (legal/contract) 4종
| id | title | target_pages |
|---|---|---|
| goods-sale-contract | 매매계약서 (동산) | 2 |
| freelance-contract | 프리랜서 계약서 | 2 |
| joint-venture-contract | 공동사업 계약서 | 2 |
| lease-termination-notice | 임대차계약 해지통보서 | 1 |

### 법률 — 통지·증명 (legal/notice) 3종
| id | title | target_pages |
|---|---|---|
| claim-assignment-notice | 채권양도 통지서 | 1 |
| payment-pledge | 지급각서 | 1 |
| statement-of-facts | 진술서 | 1 |

### 공공 — 민원·신고 (public/civil) 3종
| id | title | target_pages |
|---|---|---|
| moving-in-report | 전입신고서 | 1 |
| resident-registration-request | 주민등록등본 교부신청서 | 1 |
| seal-certificate-poa | 인감증명 발급 위임장 | 1 |

### 공공 — 신청·동의 (public/consent) 3종
| id | title | target_pages |
|---|---|---|
| sponsorship-application | 후원신청서 | 1 |
| volunteer-application | 자원봉사 신청서 | 1 |
| survey-consent | 설문조사 동의서 | 1 |

### 개인 — 취업·경력 (personal/career) 4종
| id | title | target_pages |
|---|---|---|
| career-description | 경력기술서 | 1 |
| portfolio-cover | 포트폴리오 표지 | 1 |
| recommendation-letter | 추천서 | 1 |
| english-cover-letter | 영문 커버레터 (Cover Letter) | 1 |

### 개인 — 생활·가정 (personal/life) 3종
| id | title | target_pages |
|---|---|---|
| daily-planner | 생활계획표 | 1 |
| invitation-card | 초대장 | 1 |
| moving-checklist | 이사 체크리스트 | 1 |

### 교육 — 학교·학원 (edu/school) 3종
| id | title | target_pages |
|---|---|---|
| class-timetable | 시간표 | 1 |
| course-registration | 수강신청서 | 1 |
| field-trip-consent | 현장학습 동의서 | 1 |

## 2. 작성하지 못한 id

없음. 지시된 36종 전부 작성 완료.

## 3. check_spec.py 최종 출력

```
검사 36건 / 문제 0건
```

(클라우드 작업폴더에 scripts/form_spec.py, scripts/check_spec.py, catalog/categories.json을
그대로 복사한 동일 구조에서 실행. 36건 전부 `[통과]`)

추가 자체 검증 스크립트로 아래도 확인했습니다.

- 36개 id가 지시 목록과 정확히 일치 (누락 0, 초과 0)
- 전 파일 `featured: false`
- 계약서류 4종만 `target_pages: 2`, 나머지 32종 `target_pages: 1`
- `tags` 3~6개 범위 충족
- 단일 칸 병합(`[r,c,r,c]`) 0건, merges 범위 이탈 0건 (check_spec.py가 별도 검증)
- `주민등록번호` 문자열 0건 — 전 서식 `생년월일`로 대체
- 전 파일 `date_line` 보유, 서명란은 `sign_line` 또는 결재 grid로 보유

## 4. 다음 세션이 알아야 할 특이사항

### 4-1. 구성상 판단한 부분
- **결재 grid 적용 서식(7종)**: remote-work-request, cooperation-request, internal-memo,
  business-card-request, access-pass-request, daily-cash-report, corporate-card-report.
  `담당 / 팀장 / 임원 / 대표` 4칸 + 라벨 1칸, `widths: [16,21,21,21,21]`,
  `row_height_mm: 15~16` (머리행 + 날인행 2행) 형태로 통일했습니다.
- **cooperation-request / internal-memo / daily-cash-report**: 결재 grid로 승인란을 대신하므로
  `sign_line`을 별도로 두지 않았습니다. 개인 서명이 추가로 필요하면 다음 세션에서 판단 바랍니다.
- **class-timetable / moving-checklist**: 서명 주체가 모호한 개인용 서식이나,
  "날짜란·서명란 누락 금지" 원칙에 따라 `sign_line: 작성자`를 추가했습니다.
- **tax-invoice**: 법정 세금계산서 서식의 좌우 2단 배치(공급자|공급받는자)는 grid 1개로
  구현이 어려워, 상하 2블록(공급자 → 공급받는 자)으로 재구성했습니다. 원본 서식과 배치가
  다르므로 렌더 결과 확인이 필요합니다.
- **fixed-term-labor-contract**: `source: law-standard` + `source_note`에 근로기준법 제17조 및
  기간제법 제17조 근거를 기재했습니다. 계약기간·근로일별 근로시간을 별도 grid + 요일별 table로
  이중 명시했습니다.

### 4-2. 빌드 시 주의할 점 (미검증 항목)
- **`target_pages` 초과 위험 서식**: 아래는 내용량이 많아 자동 축소가 85% 미만으로 떨어질
  가능성이 있습니다. 빌드 후 `[자동맞춤]` 비율을 우선 확인하고 필요 시 `empty_rows`를 줄이십시오.
  - `daily-cash-report` (table 3개 · empty_rows 10/10/6)
  - `moving-checklist` (table 4개 · empty_rows 12/10/8/6)
  - `corporate-card-report` (empty_rows 14)
  - `class-timetable` (table 3개 · empty_rows 10/10/7)
  - `statement-of-facts` (textbox 80mm)
  - `survey-consent`, `daily-planner`, `volunteer-application`
- **2페이지 서식 4종**은 `page_break`를 1개씩 넣어 두었습니다. 실제 분량이 달라지면
  page_break 위치 조정이 필요할 수 있습니다.
- `english-cover-letter`의 `date_line`은 `text: "Date : 20    /      /      "`로 영문화했습니다.
  (따옴표 없이 콜론을 쓰면 YAML 파싱이 실패하므로 반드시 따옴표 유지)

### 4-3. 개발가이드(SPEC_GUIDE.md) 반영 건의 — 미반영, 다음 세션 판단 요청
1. **YAML 콜론 함정 추가**: `No/Yes/On/Off` 불리언 함정은 규칙서에 있으나,
   `text: Date :` 처럼 **값 안에 콜론+공백이 들어가면 YAML 파싱이 실패**하는 건은 없습니다.
   이번 작업에서 실제로 1건 발생했으므로 "3.6 date_line" 항목에 한 줄 추가를 권고합니다.
2. **결재란 표준 스니펫 수록**: 사내 결재 서식마다 결재 grid를 매번 새로 쓰게 되므로,
   위 4-1의 `widths: [16,21,21,21,21]` 2행 구성을 규칙서 예시로 넣으면 일관성이 올라갑니다.
3. **`sign_line` 필수 여부 명확화**: 결재 grid가 있는 서식에도 `sign_line`이 필요한지
   규칙서에 명시되어 있지 않아 이번에 작성자 판단으로 처리했습니다.

## 5. 잔여 업무

| 순번 | 작업 | 담당 | 비고 |
|---|---|---|---|
| 1 | `python scripts/build_form.py` 로 36종 빌드 | 메인 세션 | **본 세션 미수행** |
| 2 | 빌드 로그의 `[자동맞춤]` 비율 확인 (85% 미만 시 empty_rows 축소) | 메인 세션 | 4-2 위험 서식 우선 |
| 3 | `[경고]` 항목(개인정보·항목누락·파일크기) 해소 | 메인 세션 | |
| 4 | `validate_catalog.py` 실행 및 `catalog.json` 등록 확인 | 메인 세션 | 본 세션 catalog.json 미수정 |
| 5 | `build_site.py` 사이트 반영 | 메인 세션 | |
| 6 | tax-invoice 렌더 결과 육안 확인 (4-1 참조) | 메인 세션 | 배치 재구성건 |
| 7 | SPEC_GUIDE.md 보완 3건 반영 여부 결정 | 메인 세션 | 4-3 참조 |

---

**명세 작성 완료 — 빌드와 검증은 메인 세션에서 진행 필요**
