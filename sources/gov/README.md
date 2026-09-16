# 법정서식 재현본 원문·중간 산출물 (분기 점검 기준 자료)

- `pdf/<id>.pdf` : 국가법령정보센터에서 받은 원문 서식 (2026-09-16 수집)
- `blocks/<id>.yaml` : `scripts/pdf_to_gov_spec.py` 변환 결과 (손대지 않음)
- `meta/<id>.yaml` : 설명·작성순서·FAQ·예시값 (Haiku 작성 → Opus 검수)
- `law_sources.tsv` : id · 법령명 · bylNo · bylBrNo (원문 주소 재구성용)
- `roster_batch1.tsv` : id · 사이트 제목 · 분류 · 소관 · 합류 계열

재조립: `python scripts/assemble_gov_spec.py <id>` → `python scripts/build_form.py <id>` → `python scripts/qa_gov_compare.py sources/gov/pdf/<id>.pdf public/files/<id>/<id>.pdf`
분기 점검: 원문 페이지의 개정일이 `specs/<id>.yaml` 의 `law_ref.amended` 와 다르면 원문 PDF 교체 후 위 절차를 다시 돈다.
