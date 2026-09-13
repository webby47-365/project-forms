# Cloudflare Pages 설정값 (연결 시 이 값을 그대로 입력)

| 항목 | 값 |
|---|---|
| Framework preset | None |
| Build command | `pip install -r requirements.txt && python scripts/build_site.py` |
| Build output directory | `public` |
| Root directory | (비움) |
| Environment variable | `PYTHON_VERSION` = `3.11` |

서식 파일(PDF·DOCX·HWPX·미리보기)은 저장소에 이미 커밋되어 있으므로 Cloudflare 빌드에서는
사이트 HTML만 생성한다. 따라서 빌드 환경에 LibreOffice·python-hwpx가 필요하지 않다.
