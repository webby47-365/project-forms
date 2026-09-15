# 가이드 초안 검수·공개 에이전트 지침 (정본)

매주 **월요일·목요일 09:00 KST** GitHub Actions(`.github/workflows/guide-review.yml`)가 실행한다.
일일 에이전트가 `status: draft` 로 쌓아 둔 가이드 초안(`guides/*.yaml`)을 검수해, 통과한 글만 `published` 로 바꿔 배포한다.
작성 규칙 정본은 `scripts/agent/GUIDE_SPEC.md` 다. 이 문서는 **검수 기준과 공개 한도**만 정한다.

## 0. 한도 (애드센스 심사 전 대량 게시 방지)

| 항목 | 한도 |
|---|---|
| 1회 실행 공개 | 최대 **2편** |
| 한 주(월~일) 공개 | 최대 **3편** — 이번 주에 이미 공개한 수는 `logs/guide-review.json` 으로 센다 |
| 사이트 공개 가이드 총수 | 최대 **15편** (애드센스 승인 전). 도달하면 공개하지 않고 검수·수정만 한 뒤 draft 로 둔다 |

애드센스 승인 후 한도를 늘릴지는 사람이 정한다. 이 문서를 고치지 않는 한 한도를 넘기지 않는다.

## 1. 검수 순서

1. `guides/*.yaml` 에서 `status: draft` 를 `created_at` 오래된 순으로 모은다. 0편이면 "검수 대상 없음"만 기록하고 종료(커밋하지 않음)
2. 공개 가능 수 = min(2, 3 − 이번 주 공개 수, 15 − 현재 공개 수). 0이면 검수·수정만 한다
3. 오래된 초안부터 2절 기준으로 검수한다

## 2. 검수 기준 — 하나라도 걸리면 고치거나 내린다

| # | 항목 | 확인 방법 | 결과 |
|---|---|---|---|
| 1 | 형식 규칙 | `python scripts/build_site.py` 알림에 `[가이드] <slug>:` 가 없어야 한다 (draft 도 검사됨) | 고친다 |
| 2 | **숫자·기한·조문 정확성** | 본문의 모든 숫자·기간·요율·조문 번호를 `sources` 의 기관 페이지(WebFetch)에서 확인. 확인 못 한 문장은 **삭제** | 틀리면 고친다. 핵심 결론이 틀렸으면 `retired` |
| 3 | 출처 | 링크가 열리고(200), 내용이 본문 주장과 맞는가. `pay`·`money` 는 go.kr·or.kr 1건 이상 | 고친다 |
| 4 | 주제 범위 | `money` 는 세테크·연말정산·카드 소득공제만. 부업·투자·코인·대출은 `retired` | 내린다 |
| 5 | 중복 | 공개된 가이드와 검색 의도가 같으면 `retired`. 서식 상세의 howto·faq 문장을 그대로 옮긴 문장은 새로 쓴다 | 고치거나 내린다 |
| 6 | 연결 서식 | `forms` 2~4종이 글 주제와 실제로 이어지는가. 억지 연결은 교체 | 고친다 |
| 7 | 단정·과장 | "무조건·반드시 이긴다·100%" 류, 개별 사안 법률 판단 → 완화 문장으로 | 고친다 |
| 8 | 제목 | 검색 키워드가 앞 20자 안에, 40자 이내, 낚시성 없음 | 고친다 |
| 9 | 읽기 | 첫 문단에서 답을 먼저 주는가, 섹션이 일 처리 순서인가 | 고친다 |

고친 뒤에는 1번 검사를 다시 통과해야 한다. **2번에서 확인하지 못한 숫자를 남긴 채 공개하지 않는다.**

## 3. 공개 처리

- 통과한 글: `status: published`, `updated_at` = 오늘(KST), 사실을 다시 확인했으면 `basis_date` = 오늘
- 공개 가능 수를 넘는 통과 글은 draft 로 두고 다음 회차에 먼저 공개한다(`logs/guide-review.json` 의 `passed_waiting` 에 slug 기록)
- 내린 글: `status: retired` 와 사유를 리포트에 적는다(파일은 남긴다)

## 4. 검증·배포

```bash
python scripts/build_site.py
python scripts/validate_catalog.py        # 오류 0건이어야 커밋
git add guides/ logs/ public/
git commit -m "guide(review): publish {slug1},{slug2} [agent]"
git push
python scripts/ping_indexnow.py --paths /guide/,/guide/{slug1}/,/guide/{slug2}/
```

- **`git add -A` 를 쓰지 않는다** — 가이드·로그·빌드 결과만 커밋한다
- 푸시가 원격 앞섬으로 거부되면 `git pull --rebase` 후 재시도, 그래도 실패하면 리포트에 적고 종료
- 검증 오류가 나면 커밋하지 않고 원인을 리포트한다

## 5. 기록·리포트

`logs/guide-review.json` (누적):
```json
{"published": [{"slug": "...", "date": "2026-09-21"}], "retired": [{"slug": "...", "date": "...", "reason": "..."}], "passed_waiting": []}
```

`logs/guide-review-YYYY-MM-DD.md` 와 실행 로그에 한국어로:
```
[가이드 검수] 2026-09-21 (월) 09:12 KST
검수 대상 3편 · 공개 2 · 대기 1 · 내림 0 · 공개 가이드 13/15 · 이번 주 공개 2/3
 1) 공개  /guide/xxx/  — 숫자 4건 확인(고용노동부), 제목 수정
 2) 공개  /guide/yyy/  — 서식 연결 1종 교체
 3) 대기  guides/zzz.yaml — 주간 한도
로컬 동기화 필요: .\sync_forms.ps1
```
