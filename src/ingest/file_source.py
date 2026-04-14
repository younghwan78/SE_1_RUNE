"""FileIngestSource — Claude MCP로 저장한 JIRA JSON 파일을 읽는 어댑터.

Claude Code에서 JIRA MCP로 이슈를 조회한 뒤 JSON으로 저장하면
이 소스가 읽어서 RawDocument 로 변환한다.

저장 디렉터리: data/jira_fetch/
파일 형식:
  - JIRA REST API 원본: [{"key": "X-1", "fields": {...}}, ...]
  - Claude 단순화 형식: [{"id": "X-1", "summary": "...", ...}, ...]
  두 형식 모두 자동 감지해서 파싱한다.

Claude에게 요청하는 예시 프롬프트:
  "PROJECT 프로젝트의 모든 이슈를 key, summary, description,
   issuetype, parent, labels, status, priority 필드로 JSON 배열로 만들어서
   data/jira_fetch/PROJECT_issues.json 파일로 저장해줘"
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from src.ingest.base import IngestSource
from src.models.raw_document import RawDocument

logger = logging.getLogger(__name__)

# MCP 저장 기본 디렉터리
_DEFAULT_DIR = Path("data/jira_fetch")


class FileIngestSource(IngestSource):
    """Claude MCP로 저장한 JSON 파일 기반 IngestSource.

    REST API 자격증명 불필요. Claude Code에서 MCP로 저장한 파일을 읽는다.
    """

    source_name = "file"

    def __init__(self, fetch_dir: Path | str | None = None) -> None:
        self._dir = Path(fetch_dir) if fetch_dir else _DEFAULT_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── 연결 확인 ─────────────────────────────────────────────────────────────

    def test_connection(self) -> tuple[bool, str]:
        """JSON 파일 존재 여부 확인."""
        files = self._list_json_files()
        if not files:
            return False, (
                f"'{self._dir}' 에 JSON 파일이 없습니다.\n"
                f"Claude에게 JIRA 이슈를 이 경로에 저장해달라고 요청하세요."
            )
        total = sum(self._count_issues(f) for f in files)
        return True, f"파일 {len(files)}개 발견 — 총 {total}개 이슈 ({', '.join(f.name for f in files)})"

    # ── 문서 수 조회 ──────────────────────────────────────────────────────────

    def fetch_candidate_count(
        self,
        project_key: str,
        domain_keywords: list[str],
    ) -> int:
        docs = self.fetch_documents(project_key, domain_keywords)
        return len(docs)

    # ── 문서 수집 ─────────────────────────────────────────────────────────────

    def fetch_documents(
        self,
        project_key: str,
        domain_keywords: list[str],
        max_results: int = 1000,
    ) -> list[RawDocument]:
        """JSON 파일에서 RawDocument 목록 반환.

        - project_key: 파일명에 포함되거나 이슈 ID 접두사로 필터 (없으면 전체)
        - domain_keywords: 제목/본문에 키워드 포함 여부로 필터 (없으면 전체)
        """
        files = self._list_json_files(project_key)
        if not files:
            logger.warning("'%s'에서 프로젝트 '%s' 관련 파일을 찾지 못했습니다.", self._dir, project_key)
            return []

        docs: list[RawDocument] = []
        skipped = 0

        for file_path in files:
            raw_issues = self._load_json(file_path)
            for raw in raw_issues:
                try:
                    doc = self._to_raw_document(raw)
                    if not doc.is_processable:
                        skipped += 1
                        continue
                    if domain_keywords and not self._matches_keywords(doc, domain_keywords):
                        continue
                    docs.append(doc)
                    if len(docs) >= max_results:
                        break
                except Exception as exc:
                    logger.warning("변환 실패: %s — %s", raw.get("key", raw.get("id", "?")), exc)
            if len(docs) >= max_results:
                break

        logger.info(
            "파일 소스 수집 완료 — 처리 가능: %d개, 제외(빈 내용): %d개",
            len(docs), skipped,
        )
        return docs

    def fetch_updated_since(self, project_key: str, since_iso: str) -> list[RawDocument]:
        """파일 소스는 증분 동기화 미지원 — 전체 재수집."""
        logger.info("FileIngestSource: 증분 동기화 미지원, 전체 재수집")
        return self.fetch_documents(project_key, [])

    # ── 파일 목록 ─────────────────────────────────────────────────────────────

    def list_json_files(self) -> list[Path]:
        """저장된 JSON 파일 목록 반환 (공개 API)."""
        return self._list_json_files()

    def _list_json_files(self, project_key: str = "") -> list[Path]:
        """project_key가 있으면 파일명에 포함된 것만 반환."""
        all_files = sorted(self._dir.glob("*.json"))
        if not project_key:
            return all_files
        key_lower = project_key.lower()
        matched = [f for f in all_files if key_lower in f.stem.lower()]
        return matched if matched else all_files  # 매칭 없으면 전체 반환

    def _count_issues(self, file_path: Path) -> int:
        try:
            raw = self._load_json(file_path)
            return len(raw)
        except Exception:
            return 0

    # ── JSON 파싱 ─────────────────────────────────────────────────────────────

    def _load_json(self, file_path: Path) -> list[dict]:
        """JSON 파일 로드. 최상위가 list 또는 {"issues": [...]} 형식 모두 허용."""
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # JIRA REST API 검색 결과 형식: {"issues": [...], "total": N}
            if "issues" in data:
                return data["issues"]
            # 단일 이슈를 감싼 형식
            return [data]

        raise ValueError(f"지원하지 않는 JSON 구조: {type(data)}")

    def _to_raw_document(self, raw: dict) -> RawDocument:
        """raw dict → RawDocument. JIRA REST API 형식과 단순화 형식 모두 지원."""

        # ── ID 추출 ──────────────────────────────────────────────────────────
        doc_id = raw.get("key") or raw.get("id") or ""
        if not doc_id:
            raise ValueError("이슈 ID(key/id) 없음")

        # ── fields 분기 ───────────────────────────────────────────────────────
        # JIRA REST API 원본: {"key": "X-1", "fields": {...}}
        # Claude 단순화:     {"id": "X-1", "summary": "...", ...}
        fields: dict = raw.get("fields", raw)

        # ── 기본 필드 ─────────────────────────────────────────────────────────
        title = _str_or(fields.get("summary")) or ""
        body  = _extract_description(fields.get("description") or "")

        # ── 이슈 타입 ─────────────────────────────────────────────────────────
        issuetype_raw = fields.get("issuetype") or fields.get("type") or {}
        jira_type = (
            issuetype_raw.get("name") if isinstance(issuetype_raw, dict)
            else str(issuetype_raw)
        )

        # ── 상위 항목 ─────────────────────────────────────────────────────────
        parent_id: str | None = None
        parent_raw = fields.get("parent") or fields.get("parentId") or fields.get("epicLink")
        if isinstance(parent_raw, dict):
            parent_id = parent_raw.get("key") or parent_raw.get("id")
        elif isinstance(parent_raw, str) and parent_raw:
            parent_id = parent_raw

        # ── 연결 이슈 ─────────────────────────────────────────────────────────
        related_ids: list[str] = []
        for link in fields.get("issuelinks", []):
            if isinstance(link, dict):
                if "outwardIssue" in link:
                    related_ids.append(link["outwardIssue"].get("key", ""))
                if "inwardIssue" in link:
                    related_ids.append(link["inwardIssue"].get("key", ""))
            elif isinstance(link, str):
                related_ids.append(link)
        related_ids = [r for r in related_ids if r]

        # ── 레이블 ────────────────────────────────────────────────────────────
        labels_raw = fields.get("labels", [])
        labels = [str(l) for l in labels_raw] if isinstance(labels_raw, list) else []

        # ── 상태 / 우선순위 ───────────────────────────────────────────────────
        status_raw = fields.get("status", {})
        status = (
            status_raw.get("name") if isinstance(status_raw, dict)
            else str(status_raw)
        ) or "Open"

        priority_raw = fields.get("priority", {})
        priority = (
            priority_raw.get("name") if isinstance(priority_raw, dict)
            else str(priority_raw)
        ) or "Medium"

        # ── URL (없어도 무방) ─────────────────────────────────────────────────
        url = fields.get("url") or fields.get("self") or ""
        if not url and doc_id:
            jira_url = os.getenv("JIRA_URL", "")
            url = f"{jira_url}/browse/{doc_id}" if jira_url else ""

        return RawDocument(
            id=doc_id,
            source="file",
            title=title,
            body=body,
            url=url,
            author=_extract_author(fields),
            labels=labels,
            parent_id=parent_id,
            related_ids=related_ids,
            metadata={
                "jira_type": jira_type or "Task",
                "status": status,
                "priority": priority,
            },
        )

    # ── 키워드 필터 ───────────────────────────────────────────────────────────

    @staticmethod
    def _matches_keywords(doc: RawDocument, keywords: list[str]) -> bool:
        """제목 또는 본문에 키워드 중 하나라도 포함되면 True."""
        text = (doc.title + " " + doc.body).lower()
        return any(kw.lower() in text for kw in keywords)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _str_or(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    return str(val)


def _extract_description(desc: Any) -> str:
    """description 필드 → 평문. ADF dict / 문자열 모두 처리."""
    if not desc:
        return ""
    if isinstance(desc, str):
        return desc.strip()
    if isinstance(desc, dict):
        # ADF 포맷 (Jira Cloud)
        return _adf_to_text(desc).strip()
    return str(desc)


def _extract_author(fields: dict) -> str:
    for key in ("reporter", "assignee", "creator"):
        val = fields.get(key)
        if isinstance(val, dict):
            return val.get("emailAddress") or val.get("displayName") or ""
        if isinstance(val, str) and val:
            return val
    return ""


def _adf_to_text(node: Any, depth: int = 0) -> str:  # noqa: C901
    """Atlassian Document Format → 평문."""
    if not isinstance(node, dict):
        return ""
    node_type = node.get("type", "")
    parts: list[str] = []
    if node_type == "text":
        return node.get("text", "")
    for child in node.get("content", []):
        parts.append(_adf_to_text(child, depth + 1))
    if node_type in ("paragraph", "blockquote"):
        return " ".join(p for p in parts if p) + "\n"
    if node_type == "heading":
        return "\n" + " ".join(p for p in parts if p) + "\n"
    if node_type in ("bulletList", "orderedList"):
        return "\n".join(p.strip() for p in parts if p.strip()) + "\n"
    if node_type == "listItem":
        return "- " + " ".join(p for p in parts if p).replace("\n", " ")
    if node_type == "codeBlock":
        return "[code: " + " ".join(p for p in parts if p) + "]"
    if node_type == "hardBreak":
        return "\n"
    return "\n".join(p for p in parts if p)
