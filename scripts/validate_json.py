"""JIRA MCP JSON 파싱 검증 스크립트.

Claude MCP로 저장한 JSON 파일이 FileIngestSource에서 올바르게 파싱되는지 확인.
실데이터 첫 실행 전에 반드시 실행할 것.

사용법:
    uv run python scripts/validate_json.py
    uv run python scripts/validate_json.py data/jira_fetch/MY_PROJECT_issues.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingest.file_source import FileIngestSource
from src.classification.keywords import keyword_classify

FETCH_DIR = Path("data/jira_fetch")
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def main() -> None:
    # 검증 대상 파일 결정
    if len(sys.argv) > 1:
        target_files = [Path(sys.argv[1])]
    else:
        target_files = sorted(FETCH_DIR.glob("*.json"))

    if not target_files:
        print(f"{RED}오류: {FETCH_DIR}/ 에 JSON 파일이 없습니다.{RESET}")
        print("Claude에게 JIRA 이슈를 JSON으로 저장해달라고 요청하세요.")
        sys.exit(1)

    total_ok = total_skip = total_err = 0

    for file_path in target_files:
        print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
        print(f"{BOLD}파일: {file_path}{RESET}")
        print(f"{'='*60}")

        # 1. Raw JSON 로드
        try:
            with open(file_path, encoding="utf-8") as f:
                raw_data = json.load(f)
        except Exception as e:
            print(f"{RED}JSON 로드 실패: {e}{RESET}")
            total_err += 1
            continue

        # 최상위 구조 감지
        if isinstance(raw_data, list):
            raw_issues = raw_data
            print(f"구조: JSON Array ({len(raw_issues)}개 항목)")
        elif isinstance(raw_data, dict) and "issues" in raw_data:
            raw_issues = raw_data["issues"]
            print(f"구조: JIRA REST 형식 (total={raw_data.get('total', '?')}, issues={len(raw_issues)}개)")
        elif isinstance(raw_data, dict):
            raw_issues = [raw_data]
            print(f"구조: 단일 이슈 dict")
        else:
            print(f"{RED}알 수 없는 최상위 구조: {type(raw_data)}{RESET}")
            total_err += 1
            continue

        # 2. FileIngestSource 파싱
        source = FileIngestSource(fetch_dir=file_path.parent)
        docs_ok = []
        docs_skip = []
        errors = []

        for raw in raw_issues:
            try:
                doc = source._to_raw_document(raw)
                if doc.is_processable:
                    docs_ok.append(doc)
                else:
                    docs_skip.append((doc.id, "빈 title 또는 body"))
            except Exception as e:
                issue_id = raw.get("key") or raw.get("id") or "?"
                errors.append((issue_id, str(e)))

        total_ok   += len(docs_ok)
        total_skip += len(docs_skip)
        total_err  += len(errors)

        # 3. 결과 출력
        print(f"\n{BOLD}파싱 결과:{RESET}")
        print(f"  {GREEN}처리 가능{RESET}: {len(docs_ok)}개")
        print(f"  {YELLOW}제외 (빈 내용){RESET}: {len(docs_skip)}개")
        print(f"  {RED}파싱 오류{RESET}: {len(errors)}개")

        # 4. 샘플 5개 미리보기
        if docs_ok:
            print(f"\n{BOLD}샘플 (처리 가능 최대 5개):{RESET}")
            for doc in docs_ok[:5]:
                kw_type, kw_conf = keyword_classify(doc.title, doc.body, doc.labels)
                kw_str = f"{kw_type}({kw_conf:.0%})" if kw_type else "→LLM필요"
                parent_str = f" parent={doc.parent_id}" if doc.parent_id else ""
                labels_str = f" labels={doc.labels}" if doc.labels else ""
                print(f"  {GREEN}✓{RESET} [{doc.id}] {doc.title[:55]}")
                print(f"      jira_type={doc.metadata.get('jira_type','?')}{parent_str}{labels_str}")
                print(f"      키워드 분류 예측: {kw_str}")
                print(f"      body 길이: {len(doc.body)}자")

        # 5. 제외 항목
        if docs_skip:
            print(f"\n{BOLD}제외 항목 (빈 내용):{RESET}")
            for doc_id, reason in docs_skip[:10]:
                print(f"  {YELLOW}–{RESET} [{doc_id}] {reason}")
            if len(docs_skip) > 10:
                print(f"  ... 외 {len(docs_skip)-10}개")

        # 6. 파싱 오류
        if errors:
            print(f"\n{BOLD}파싱 오류:{RESET}")
            for issue_id, err in errors:
                print(f"  {RED}✗{RESET} [{issue_id}] {err}")

        # 7. 필드 구조 힌트 (오류 있을 때)
        if errors and raw_issues:
            sample = raw_issues[0]
            print(f"\n{BOLD}첫 번째 항목 키 목록 (구조 확인용):{RESET}")
            if "fields" in sample:
                print(f"  최상위: {list(sample.keys())}")
                print(f"  fields: {list(sample['fields'].keys())[:20]}")
            else:
                print(f"  키: {list(sample.keys())[:20]}")

    # 전체 요약
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}전체 요약{RESET}")
    print(f"  {GREEN}처리 가능{RESET}: {total_ok}개")
    print(f"  {YELLOW}제외{RESET}: {total_skip}개")
    print(f"  {RED}파싱 오류{RESET}: {total_err}개")

    if total_err > 0:
        print(f"\n{RED}파싱 오류가 있습니다. 위 오류 내용과 필드 구조를 공유하면 파서를 수정하겠습니다.{RESET}")
    elif total_ok == 0:
        print(f"\n{YELLOW}처리 가능한 이슈가 없습니다. title/description 필드를 확인하세요.{RESET}")
    else:
        print(f"\n{GREEN}파싱 정상. 06 Ingest Pipeline 페이지에서 분류를 실행할 수 있습니다.{RESET}")


if __name__ == "__main__":
    main()
