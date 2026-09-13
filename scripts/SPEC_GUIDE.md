# 서식 명세(YAML) 작성 규칙서

「무료서식 다운로드」 사이트의 서식은 **YAML 명세 파일 1개**로 정의한다.
명세를 `specs/{id}.yaml`로 저장하면 `scripts/build_form.py`가 PDF·DOCX·HWPX·미리보기·카탈로그를
모두 자동 생성한다. 작성자는 **명세만** 쓰면 되고 렌더링 코드는 건드리지 않는다.

## 1. 파일 위치와 이름

- 경로: `specs/{id}.yaml`
- `id`는 영문 소문자·숫자·하이픈만. **파일명과 `id` 필드가 반드시 일치**해야 한다.
- id는 서식 내용을 알 수 있게 짓는다. 예: `resignation-letter`, `meeting-minutes`, `expense-report`.

## 2. 머리말(메타데이터) 필수 필드

```yaml
id: meeting-minutes                 # 파일명과 동일
title: 회의록                        # 사이트에 표시되는 한국어 정식명
category: corp                      # categories.json의 대분류 key
subcategory: admin                  # categories.json의 중분류 key
tags: [회의록, 회의결과, 회의일지, minutes]   # 검색 별칭 3~6개
summary: 회의 일시·참석자·안건별 논의 내용과 결정사항·후속조치를 기록하는 회의록 양식입니다.
usage: >
  실제 사용 상황과 작성 요령을 3~5문장으로 쓴다. 상세 화면에 노출되고 검색 유입의
  핵심이 되므로 성의 있게 쓴다. "무엇에 쓰는 서류인지 / 어떻게 채우는지 /
  주의할 점" 순서로 쓴다.
source: original                    # original | law-standard | public-license
featured: false                     # 메인 노출 10종만 true
target_pages: 1                     # 목표 페이지 수 (넘치면 자동 축소, 0이면 자동 산출)
blocks:
  - ...
```

`category` / `subcategory` 유효값은 `catalog/categories.json`에서 확인한다.

| 대분류 | key | 중분류 key |
|---|---|---|
| 기업 | `corp` | `hr`(인사·노무) `admin`(총무·행정) `finance`(회계·세무) `sales`(영업·마케팅) `startup`(창업·법인) |
| 법률 | `legal` | `contract`(계약) `notice`(통지·증명) `litigation`(소송·민원) |
| 공공 | `public` | `civil`(민원·신고) `consent`(신청·동의) |
| 부동산 | `estate` | `lease`(임대·매매) |
| 개인 | `personal` | `career`(취업·경력) `life`(생활·가정) |
| 교육 | `edu` | `school`(학교·학원) |
| 의료·복지 | `welfare` | `consent`(동의·신청) |

법정 서식을 참고한 경우 `source: law-standard`와 함께 `source_note`에 근거 법령을 적는다.

## 3. 블록 타입 레퍼런스

블록은 `blocks:` 아래에 위에서 아래 순서로 렌더링된다.

### doc_title — 문서 제목 (서식마다 맨 위에 1개)
```yaml
- type: doc_title
  text: 회의록
  spaced: true      # 8자 이하면 글자 사이를 벌린다. 긴 제목은 false
```

### subtitle — 구역 제목 (악센트 바 + 밑선이 자동으로 붙는다)
```yaml
- type: subtitle
  text: 1. 회의 개요
```

### para — 일반 문단
```yaml
- type: para
  text: 위 기재사항은 사실과 다름이 없음을 확인합니다.
  align: center     # left | center | right | both
  size: 11          # 생략 시 10.5
```

### grid — 라벨-값 격자표 (인적사항·기본정보에 사용)
```yaml
- type: grid
  widths: [15, 35, 15, 35]     # 컬럼 비율(합 100). 셀 개수와 길이가 같아야 한다
  label_cols: [0, 2]           # 라벨(음영+굵게)로 처리할 컬럼 번호
  row_height_mm: 8             # 행 최소 높이
  merges:                      # [시작행, 시작열, 끝행, 끝열] — 선택
    - [1, 1, 1, 3]
  rows:
    - ["회의명", "", "일시", ""]
    - ["장소", "", "", ""]
```
- 값이 들어갈 칸은 `""`(빈 문자열)로 둔다. 사용자가 손으로 채우는 칸이다.
- `label_cols`를 생략하면 짝수 컬럼(0,2,4…)이 자동으로 라벨이 된다.
- `merges`로 병합한 칸은 한 칸처럼 넓어진다. 주소·이메일처럼 긴 값에 쓴다.

### table — 머리글 + 빈 입력행 표 (목록형 데이터에 사용)
```yaml
- type: table
  widths: [10, 30, 40, 20]
  header: ["No", 안건, 논의 내용, 결정사항]
  empty_rows: 5                # 빈 입력행 개수
  row_height_mm: 8
  body_align: center           # 미리 채운 rows의 정렬 (선택)
```
- 머리글은 짙은 네이비 배경 + 흰 글자로 자동 처리된다.
- **`"No"`처럼 YAML이 불리언으로 읽는 값은 반드시 따옴표로 감싼다.** (`No`, `Yes`, `On`, `Off`, `Y`, `N`)
  따옴표를 빼면 `False`로 출력되고, 빌드 시 명세 검증에서 오류로 막힌다.

### textbox — 자유기술란 (서술형 답변 칸)
```yaml
- type: textbox
  hint: "논의 배경과 경과를 시간순으로 작성하십시오."   # 박스 위 작은 회색 안내문 (선택)
  height_mm: 30                                    # 박스 높이
```
- **단일 칸 `table`을 자유기술란으로 쓰지 말 것.** 머리글이 짙은 띠로 나와 어색하다. 반드시 `textbox`를 쓴다.

### article — 계약서 조항 (조 제목 + 본문 여러 줄)
```yaml
- type: article
  heading: 제1조 (목적)
  lines:
    - "본 계약은 …을 목적으로 한다."
    - "제2항 내용."
```

### kv_list — 점(·) 목록
```yaml
- type: kv_list
  items:
    - "임금은 근로자에게 직접 지급한다."
    - "지급일이 휴일인 경우 그 전일에 지급한다."
```

### date_line / sign_line / notice / spacer / page_break
```yaml
- type: date_line                    # "20        년        월        일" 가운데 정렬
  text: 20        년        월        일   # 다르게 쓰려면 지정 (선택)

- type: sign_line
  label: 작성자                       # 1명
- type: sign_line
  labels: ["위임인", "수임인"]          # 여러 명

- type: notice
  text: 제출 전 사본을 보관하십시오.      # 하단 작은 회색 안내. 앞에 ※ 자동 삽입

- type: spacer
  height_pt: 8

- type: page_break                   # 여러 장 서식에서 장 구분
```

## 4. 서식 설계 원칙 (반드시 지킬 것)

1. **표준 구성을 지킨다.** 실무에서 쓰이는 항목을 빠뜨리지 않는다. 법정서식이 있는 경우
   해당 법령의 필수 기재사항을 모두 넣는다.
2. **주민등록번호를 넣지 않는다.** `생년월일`로 대체한다. 빌드 시 자동 검수에서 차단된다.
3. **1페이지 원칙.** 계약서·증명서가 아닌 일반 서식은 `target_pages: 1`을 목표로 한다.
   넘치면 `empty_rows`를 줄인다. 자동 축소는 간격만 줄이므로 내용이 너무 많으면 실패한다.
4. **자유기술란은 `textbox`, 목록은 `table`, 기본정보는 `grid`** 로 명확히 구분한다.
5. **`widths` 합은 100**, 그리고 `rows`의 각 행 길이는 `widths` 길이와 반드시 같아야 한다.
6. **서명·날인란과 날짜란**을 빠뜨리지 않는다. 제출용 서식은 거의 모두 필요하다.
7. **`summary`와 `usage`는 검색 유입의 핵심**이다. 서식명만 반복하지 말고 실제 사용 상황과
   주의사항을 구체적으로 쓴다.
8. 법률 판단이 필요한 내용(구체적 분쟁 대응, 세액 계산 등)은 서식 틀만 제공하고 본문에
   단정적으로 쓰지 않는다. 필요하면 `notice`로 "제출처 규정을 확인하십시오" 수준으로 안내한다.

## 5. 작성 후 확인 절차

```bash
python scripts/build_form.py {id}        # 해당 서식만 빌드
python scripts/build_form.py             # specs 전체 빌드
```

출력에서 다음을 확인한다.

- `[완료] 1p` — 목표 페이지 수 안에 들어왔는지
- `[자동맞춤] 간격 85%로 축소` — 85% 미만까지 축소되면 내용이 과다하므로 `empty_rows`를 줄인다
- `[경고]` — 항목 누락·개인정보·파일 크기 문제. 경고가 남은 채로 완료하지 않는다

생성물은 `public/files/{id}/`에 `{id}.pdf` `{id}.docx` `{id}.hwpx` `preview-1.webp`로 저장되고
`catalog/catalog.json`에 자동 등록된다.

## 6. 참고할 완성 예시

- `specs/resume-basic.yaml` — grid 병합(사진란), 여러 table 조합
- `specs/resignation-letter.yaml` — grid + textbox + table + 서명 구성
- `specs/labor-contract-standard.yaml` — article 다수 + 법정 필수기재사항
- `specs/quotation.yaml` — 금액 표와 합계 구성
- `specs/housing-lease-contract.yaml` — 2페이지 계약서 구성
