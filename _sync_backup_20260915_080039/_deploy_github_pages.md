# 배포 구성 — GitHub Pages (2026-09-13 적용)

Cloudflare Pages 가입이 반복 차단되어 GitHub Pages로 배포한다. 정적 사이트이므로
산출물(`public/`)은 동일하며, 필요하면 언제든 다른 호스팅으로 교체할 수 있다.

## 구성

| 항목 | 값 |
|---|---|
| 저장소 | `https://github.com/webby47-365/project-forms` (**Public** — 무료 Pages 조건) |
| 배포 방식 | GitHub Actions (`.github/workflows/deploy-pages.yml`) |
| Settings → Pages → Source | **GitHub Actions** |
| 빌드 | `pip install -r requirements.txt` → `python scripts/build_site.py` |
| 배포 대상 | `public/` |
| Python | 3.11 (`actions/setup-python@v5`) |
| 커스텀 도메인 | `freeforms.kr` (Settings → Pages → Custom domain **직접 입력 필요**) |
| CNAME 파일 | 저장소 루트 `CNAME` = `freeforms.kr` (재배포 시 도메인 유지용) |

## DNS (메일플러그에서 관리 — My메일플러그 → DNS 관리)

| 호스트명 | 타입 | 값 |
|---|---|---|
| `freeforms.kr` | A | `185.199.108.153` |
| `freeforms.kr` | A | `185.199.109.153` |
| `freeforms.kr` | A | `185.199.110.153` |
| `freeforms.kr` | A | `185.199.111.153` |
| `www.freeforms.kr` | CNAME | `freeforms.kr` |

**네임서버 변경 화면은 건드리지 않는다.** `ns.mailplug.com` / `ns2.mailplug.com` 유지.

## 평소 배포

```powershell
.\deploy_forms.ps1                 # 빌드 → 검증 → 커밋 → 푸시 → Actions가 자동 배포
.\deploy_forms.ps1 -Pull           # 원격(웹 편집·에이전트) 변경을 로컬 정본에 먼저 반영
```

푸시 후 1~2분이면 반영된다. 진행 상황은 저장소 **Actions** 탭에서 확인한다.

## 문제가 생겼을 때

| 증상 | 원인·조치 |
|---|---|
| Actions 실행이 빨간 X | Settings → Pages → Source가 `GitHub Actions`인지 확인 후 **Re-run all jobs** |
| 사이트가 옛 화면 | DNS 캐시. `ipconfig /flushdns` + `chrome://net-internals/#dns` 초기화. ISP 캐시는 최대 2시간 대기 |
| 커스텀 도메인이 풀림 | 루트 `CNAME` 파일이 삭제되었는지 확인 후 재배포 |
| `Enforce HTTPS`가 비활성 | 인증서 발급 대기(15분~1시간). 발급되면 자동 활성화 |
| `-Pull` 실패 (`unstaged changes`) | `git add -A; git commit -m "..."` 후 다시 `-Pull` |

## 워크플로 수정 방법

`.github\` 는 보호 경로라 로컬 도구로 편집할 수 없다. GitHub 웹 편집기에서 고친 뒤
`.\deploy_forms.ps1 -Pull` 로 로컬 정본에 내려받는다.
