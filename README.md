# 무료서식 다운로드

업무·법률·공공·생활 서식을 회원가입 없이 **PDF · Word(DOCX) · 한글(HWPX)** 세 형식으로
제공하는 무료 서식 사이트. 서식은 명세(YAML) 하나에서 3형식을 동시에 생성하며,
사이트는 정적 페이지로 빌드해 **GitHub Pages**에 배포한다.

현재 서식 **98종** / 대분류 7개 · 중분류 15개. 서비스 주소는 <https://freeforms.kr>.

## 폴더 구조

```
C:\Project_Forms\
├─ specs\                   ★ 정본 — 서식 설계(YAML). 서식을 고치려면 여기를 고친다
│   └─ resume-basic.yaml
├─ catalog\
│   ├─ categories.json      대분류·중분류 정의 (URL 키 ↔ 한글 폴더명 매핑)
│   └─ catalog.json         빌드가 자동 생성하는 서식 메타데이터 (직접 수정 금지)
├─ masters\                 서식 DOCX 마스터 (빌드 산출물)
├─ public\                  ★ 배포 대상 — GitHub Pages가 이 폴더를 서비스한다
│   ├─ files\{id}\          {id}.pdf / .docx / .hwpx / preview-1.webp
│   └─ (빌드 생성) index.html, category\, form\, sitemap.xml, search-index.json
├─ assets\                  ★ 정본 — 도구 스크립트(stamp.js)·공유 카드 이미지. 빌드가 public/assets/ 로 복사
├─ templates\               사이트 HTML 템플릿 (Jinja2). tools.html·tool_stamp.html = 직장인 도구 화면
├─ scripts\
│   ├─ SPEC_GUIDE.md        ★ 서식 명세 작성 규칙서 (서식 추가 시 필독)
│   ├─ form_spec.py         명세 로더·검증
│   ├─ render_docx.py       명세 → DOCX
│   ├─ render_hwpx.py       명세 → HWPX
│   ├─ build_form.py        명세 → PDF·DOCX·HWPX·미리보기·카탈로그
│   ├─ build_site.py        카탈로그 → HTML·검색인덱스·사이트맵
│   ├─ check_spec.py        명세 문법 검사 (빠름, 렌더링 없음)
│   ├─ validate_catalog.py  배포 전 최종 검증
│   ├─ fit_one_page.py      페이지 초과 서식 자동 보정
│   ├─ export_to_folders.py 서식을 한글 카테고리 폴더로 내보내기
│   └─ agent\daily_forms_agent.md   일일 자동운영 지침 정본
├─ 기업\ 법률\ 공공\ 부동산\ 개인\ 교육\ 의료·복지\
│                           사람이 찾아보기 위한 **내보내기 결과** (정본 아님)
├─ logs\                    일일 리포트 기록
├─ .github\workflows\      [서버] GitHub Actions 배포 워크플로 (보호 경로 — 웹에서 편집)
├─ CNAME                    커스텀 도메인 (freeforms.kr) — 지우면 도메인이 풀린다
├─ _deploy_github_pages.md  배포 구성·복구 절차
├─ deploy_forms.ps1         ★ [로컬] 검증 → 커밋 → 푸시 → 배포 확인 (한 줄 실행)
└─ requirements.txt         빌드용 패키지 (jinja2)
```

## 자주 쓰는 명령

```powershell
# 배포 (가장 많이 쓰는 명령)
.\deploy_forms.ps1
.\deploy_forms.ps1 -Message "서식 3종 추가"
.\deploy_forms.ps1 -Pull          # 에이전트가 올린 커밋을 로컬 정본에 먼저 반영

# 서식 하나만 다시 만들기
python scripts\build_form.py resume-basic

# 명세 문법만 빠르게 검사 (렌더링 없음)
python scripts\check_spec.py

# 사이트만 다시 생성
python scripts\build_site.py

# 로컬에서 사이트 확인 (http://localhost:8000)
cd public; python -m http.server 8000
```

## 서식을 하나 추가하는 절차

1. `scripts\SPEC_GUIDE.md`를 읽는다.
2. `specs\{id}.yaml`을 만든다. (`id`는 영문 소문자·하이픈, 파일명과 동일)
3. `python scripts\check_spec.py {id}` → **[통과]** 확인
4. `python scripts\build_form.py {id}` → 페이지 수·경고 확인
5. `public\files\{id}\preview-1.webp`를 열어 눈으로 확인
6. `.\deploy_forms.ps1`

## 최초 1회 준비 (로컬)

```powershell
# 서식 생성에 필요한 패키지
python -m pip install python-docx python-hwpx jinja2 pyyaml pillow

# PDF 변환·미리보기에 필요한 외부 도구
#  - LibreOffice (soffice)  : https://ko.libreoffice.org/
#  - Poppler (pdftoppm 등)  : PATH에 추가
```

사이트 주소를 `site.url` 파일에 한 줄로 적어두면 `deploy_forms.ps1`이 배포 후
자동으로 200 응답을 확인한다. (이 파일은 git에 올라가지 않는다)

## 애드센스 (초기에는 꺼져 있음)

`catalog/ads.json` 하나로 제어한다. 기본값은 **광고 완전 OFF**이며, 이 상태에서는 애드센스
스크립트도 광고 자리도 페이지에 전혀 나가지 않는다.

```jsonc
{
  "enabled": false,                 // true로 바꾸면 광고 노출 시작
  "client": "",                     // ca-pub-XXXXXXXXXXXXXXXX
  "auto_ads": true,
  "download_interstitial": false,   // true면 다운로드가 중간 페이지를 경유
  "download_delay_sec": 2,
  "slots": { "main_top": "", "main_mid": "", ... }   // 각 슬롯 ID
}
```

승인 후 켜는 순서는 `client` 입력 → 켤 슬롯의 ID 입력 → `enabled: true` →
`.\deploy_forms.ps1 -SkipBuild` 이다. `client`를 넣으면 `ads.txt`도 자동 생성된다.

광고 위치는 페이지당 2~3개로 제한했다.

| 슬롯 | 위치 |
|---|---|
| `main_top` | 메인 히어로 아래 |
| `main_mid` | 대표 10종과 최근 추가 서식 사이 |
| `category_side` | 카테고리 좌측 사이드바 하단 (PC 전용, 모바일에서 자동 숨김) |
| `category_bottom` | 카테고리 카드 그리드 아래 |
| `detail_body` | 상세 화면 태그 아래 |
| `download_page` | 다운로드 준비 페이지 |
| `search_bottom` | 검색 결과 목록 아래 |
| `series_bottom` | 계열 비교표 아래 |
| `collection_bottom` | 주제 모음 목록 아래 |
| `request_bottom` | 서식 요청 화면 아래 |
| `footer` | 푸터 위 |

**정책상 주의.** 다운로드 버튼 바로 옆·아래에는 광고를 두지 않았다(오클릭 유도 금지).
상세 화면 광고는 다운로드 박스에서 충분히 떨어진 위치에 두고 CSS로 최소 38px 간격을
강제한다. `download_interstitial`을 켜면 파일은 중간 페이지에서 **자동으로** 내려가며
광고를 보거나 닫을 필요가 없다 — 광고를 닫아야 받을 수 있는 구조는 정책 위반이다.
광고 자리는 최소 높이를 예약해 두어 광고가 뜰 때 화면이 밀리지 않는다(CLS 방지).

### 승인 전에 광고 배치를 눈으로 확인하려면

```bash
FORMS_PREVIEW_ADS=1 python scripts/build_site.py    # (PowerShell) $env:FORMS_PREVIEW_ADS=1
```

광고 자리를 실제 크기의 회색 상자로 그리고 다운로드 준비 페이지도 함께 만든다.
**애드센스 코드는 나가지 않지만 배포하면 안 된다** — 확인이 끝나면 환경변수 없이
다시 빌드해 배포본을 되돌린다(`deploy_forms.ps1`은 항상 일반 빌드를 한다).

### 다운로드 준비 페이지

`download_interstitial: true`이면 다운로드 링크가 `/download/<id>/<형식>/`을 거친다.
파일은 2초 뒤 자동으로 내려가고, 기다리는 동안 **작성 순서·자주 묻는 질문·다른 형식·
함께 찾는 서식**을 함께 보여 준다. 방문당 페이지뷰가 1 늘고 광고 노출 자리가 하나 는다.

- 검색 결과에 나올 성격이 아니므로 `noindex, follow`이고 사이트맵에서도 뺀다.
- 다운로드 집계는 자동 다운로드 시점에 한 번만 잡는다. 그 뒤 '바로 내려받기'를 눌러도
  `data-no-track`으로 중복 집계되지 않는다.
- **광고가 꺼져 있으면 이 페이지는 아예 만들어지지 않는다.** 광고 없이 켜면 방문자에게
  기다림만 생기고 얻는 것이 없기 때문이다.

## 직장인 도구 (/tools/)

서식과 함께 쓰는 브라우저 전용 도구. 서버가 없으므로 계산·그리기는 전부 `assets/stamp.js`처럼
방문자 브라우저에서 돌고, 입력값은 어디에도 전송되지 않는다(처리방침 수정 불필요).

| 경로 | 내용 | 정의 위치 |
|---|---|---|
| `/tools/` | 허브. 도구 카드 + '준비 중' 목록 | `build_site.py` `TOOLS`·`TOOLS_SOON`, `templates/tools.html` |
| `/tools/stamp/` | 디지털 도장(원형·사각·타원 × 전서체풍·명조·고딕) + 손글씨·글꼴 서명 → 투명 PNG | `templates/tool_stamp.html`, `assets/stamp.js` |
| `/tools/salary/` | 연봉 실수령액 — 4대보험 + 간이세액표 소득세 | `templates/tool_calc.html`, `assets/calc.js` |
| `/tools/severance/` | 퇴직금 — 평균임금 자동 구간 분할, 상여·연차수당 3/12 산입 | 〃 |
| `/tools/annual-leave/` | 연차 — 입사일/회계연도 기준, 미사용 연차수당 | 〃 |
| 서식 상세 위젯 | 서명·날인 칸이 있는 서식(카탈로그 `seal: true`)에만 "이 서식에 찍을 도장 만들기" | `templates/form.html`, `form_spec.seal_of` |

새 도구를 추가하려면 ① `TOOLS`에 한 줄 ② `templates/tool_<key>.html` ③ `build()`에 렌더링 한 블록.
상단 메뉴·허브·사이트맵·llms.txt는 `TOOLS` 목록을 그대로 따라간다. 도구를 고친 날은 `TOOLS_UPDATED`에 적는다.

### 계산기 3종의 데이터 (연 1회 갱신)

계산기는 화면 글(`build_site.py` `CALCULATORS`), 계산 로직(`assets/calc.js`), **요율 데이터** 세 가지로
나뉜다. 매년 바뀌는 것은 요율뿐이라 코드를 건드릴 일이 없다.

| 파일 | 내용 | 갱신 시기 |
|---|---|---|
| `catalog/rates_2026.json` | 4대보험 요율, 국민연금 기준소득월액 상·하한, 자녀 세액공제액, 월 소정근로시간 209 | 매년 1월(요율)·7월(연금 상하한) |
| `catalog/tax_table_2026.json` | 근로소득 간이세액표 원문 (구간별 가족수 1~11명 세액) | 매년 2월경 개정 시 |

간이세액표는 **계산식이 아니라 표**다(소득세법 시행령 별표2). 그래서 원문 파일이 있어야 한다.

```powershell
# 1) 홈택스 → 세금신고 → 원천세 신고 → 근로소득 간이세액표 → 전체 파일(엑셀) 내려받아 catalog\ 에 넣는다
# 2) [로컬 작업]
python scripts\build_tax_table.py
```

`catalog/tax_table_2026.json` 이 없으면 빌드가 실패하지 않고 **`/tools/salary/` 만 건너뛴다**
(메뉴·푸터·사이트맵에서도 빠져 404가 나지 않는다). 퇴직금·연차 계산기는 표와 무관하게 동작한다.
표가 생기면 빌드가 `public/assets/tax_table.json` 으로 복사하고, 페이지는 그때만 내려받는다.

요율을 고칠 때는 `rates_2026.json` 의 `sources` 에 적힌 출처(복지부 보도자료·공단 안내)를 확인하고
`updated` 날짜를 함께 고친다. 일일 에이전트에게 맡기지 않는다 — 틀리면 방문자가 바로 알아본다.

## 설계 원칙

- **정본은 로컬.** GitHub는 배포 엔진 겸 형상관리 저장소다. 에이전트가 클라우드에서
  올린 커밋은 `.\deploy_forms.ps1 -Pull`로 로컬에 반영해 로컬을 최종본으로 유지한다.
- **매매봇 서버와 완전 분리.** 사이트는 정적 호스팅이므로 기존 가상서버에 포트를 열지
  않고 부하도 주지 않는다.
- **호스팅은 교체 가능한 부품.** 산출물이 `public/` 정적 파일이므로 GitHub Pages·
  Cloudflare Pages·Netlify 어디로든 옮길 수 있다. 현재는 GitHub Pages를 쓴다.
- **3형식은 변환이 아니라 병행 생성.** 완성된 파일 1개에서 다른 형식을 만들어내는 변환은
  불가능하다(한글 포맷을 쓰는 변환기가 없음). 그래서 명세 하나에서 DOCX와 HWPX를 각각
  처음부터 생성한다. PDF는 DOCX에서 뽑는다.
- **자동 맞춤.** 목표 페이지를 넘치면 행 높이·문단 간격을 줄이고, 여백이 남으면 넓혀
  지면을 채운다. 글자 크기는 건드리지 않는다.
- **URL은 영문, 저장 파일명은 한글.** 파일은 `/files/resume-basic/resume-basic.pdf`로
  서비스하고, 링크의 `download` 속성에 `이력서 (기본형).pdf`를 지정한다. URL에 한글이
  섞이면 공유·검색에 불리하고, 사용자는 한글 파일명으로 저장받는 편이 낫기 때문이다.
  파일명은 서식 제목에서 Windows 금지문자(`\ / : * ? " < > |`)만 치환해 만든다.
- **서식 추가 = 파일 3개 + 카탈로그 1건.** 코드를 고치지 않고 재빌드만으로 반영된다.

## 면책

제공 서식은 일반적인 참고용 양식이다. 개별 사안에 대한 법적 효력과 적합성은 이용자가
확인해야 한다. 법정 서식(`source: law-standard`)은 근거 법령을 `source_note`에 기록하며,
분기마다 개정 여부를 점검한다.
