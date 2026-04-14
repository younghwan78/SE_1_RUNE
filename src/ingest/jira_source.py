"""JIRA IngestSource — atlassian-python-api 기반.

환경 변수:
    JIRA_URL          https://your-company.atlassian.net
    JIRA_EMAIL        your.email@company.com
    JIRA_TOKEN        API Token (Cloud) 또는 PAT (On-premise)
    JIRA_CLOUD        "true" (기본) | "false"
    JIRA_MAX_RESULTS  페이지당 최대 수 (기본 100)

의존:
    uv add atlassian-python-api
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Any

from src.ingest.base import IngestSource
from src.models.raw_document import RawDocument

logger = logging.getLogger(__name__)


class JiraIngestSource(IngestSource):
    """JIRA REST API 기반 IngestSource.

    MCP 대안: 사내 JIRA MCP가 가용하면 동일 ABC를 구현하는
    JiraMcpSource로 교체 가능. 파이프라인 코드 변경 불필요.
    """

    source_name = "jira"

    # JIRA 이슈 타입 → 전처리 힌트 (분류에 영향 없음, Epic만 특별 처리)
    _EPIC_TYPE_NAMES = {"Epic", "에픽"}

    def __init__(self) -> None:
        self._url: str = os.environ["JIRA_URL"].rstrip("/")
        self._email: str = os.environ["JIRA_EMAIL"]
        self._token: str = os.environ["JIRA_TOKEN"]
        self._is_cloud: bool = os.getenv("JIRA_CLOUD", "true").lower() != "false"
        self._max_results: int = int(os.getenv("JIRA_MAX_RESULTS", "100"))
        self._client = self._build_client()

    # ── 연결 ──────────────────────────────────────────────────────────────────

    def _build_client(self) -> Any:
        try:
            from atlassian import Jira  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "atlassian-python-api 패키지가 필요합니다.\n"
                "설치: uv add atlassian-python-api"
            ) from exc
        return Jira(
            url=self._url,
            username=self._email,
            password=self._token,
            cloud=self._is_cloud,
        )

    def test_connection(self) -> tuple[bool, str]:
        """JIRA 서버 연결 및 인증 확인."""
        try:
            me = self._client.get_current_user()
            name = me.get("displayName") or me.get("name") or "unknown"
            return True, f"연결 성공 — {name} ({self._url})"
        except Exception as exc:
            return False, f"연결 실패: {exc}"

    # ── 문서 수 조회 ──────────────────────────────────────────────────────────

    def fetch_candidate_count(
        self,
        project_key: str,
        domain_keywords: list[str],
    ) -> int:
        """JQL로 필터링한 이슈 총 수 반환 (is_processable 판정 전 전체 수)."""
        jql = self._build_jql(project_key, domain_keywords)
        try:
            result = self._client.jql(jql, limit=0)
            return result.get("total", 0)
        except Exception as exc:
            logger.error("이슈 수 조회 실패: %s", exc)
            return 0

    # ── 문서 수집 ─────────────────────────────────────────────────────────────

    def fetch_documents(
        self,
        project_key: str,
        domain_keywords: list[str],
        max_results: int = 200,
    ) -> list[RawDocument]:
        """처리 가능한 RawDocument 목록 반환 (is_processable 필터 포함)."""
        jql = self._build_jql(project_key, domain_keywords)
        docs: list[RawDocument] = []
        start = 0
        skipped = 0

        while len(docs) < max_results:
            page_limit = min(self._max_results, max_results - len(docs))
            try:
                result = self._client.jql(
                    jql,
                    start=start,
                    limit=page_limit,
                    fields=self._FETCH_FIELDS,
                )
            except Exception as exc:
                logger.error("JIRA JQL 실패 (start=%d): %s", start, exc)
                break

            issues: list[dict] = result.get("issues", [])
            if not issues:
                break

            for issue in issues:
                try:
                    doc = self._to_raw_document(issue)
                    if doc.is_processable:
                        docs.append(doc)
                    else:
                        skipped += 1
                        logger.debug("건너뜀 (빈 내용): %s", issue.get("key"))
                except Exception as exc:
                    logger.warning("변환 실패 [%s]: %s", issue.get("key"), exc)

            start += len(issues)
            total = result.get("total", 0)
            logger.info("  수집 중: %d / %d (처리가능: %d, 제외: %d)", start, total, len(docs), skipped)
            if start >= total:
                break

        logger.info(
            "수집 완료 — 처리 가능: %d개, 제외(빈 내용): %d개 (프로젝트: %s)",
            len(docs), skipped, project_key,
        )
        return docs

    def fetch_updated_since(
        self,
        project_key: str,
        since_iso: str,
    ) -> list[RawDocument]:
        """증분 동기화 — since_iso 이후 변경 이슈만 수집."""
        jql = (
            f"project = {project_key} "
            f"AND updated >= '{since_iso}' "
            f"ORDER BY updated ASC"
        )
        try:
            result = self._client.jql(jql, limit=500, fields=self._FETCH_FIELDS)
        except Exception as exc:
            logger.error("증분 동기화 실패: %s", exc)
            return []

        docs = []
        for issue in result.get("issues", []):
            try:
                doc = self._to_raw_document(issue)
                if doc.is_processable:
                    docs.append(doc)
            except Exception as exc:
                logger.warning("변환 실패 [%s]: %s", issue.get("key"), exc)
        return docs

    def list_document_types(self, project_key: str) -> list[dict[str, str]]:
        """프로젝트 이슈 타입 목록 (타입 매핑 확인용)."""
        try:
            meta = self._client.get_project_issue_types(project_key)
            return [
                {
                    "id": t.get("id", ""),
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                }
                for t in meta
            ]
        except Exception as exc:
            logger.error("이슈 타입 조회 실패: %s", exc)
            return []

    # ── 내부 변환 ─────────────────────────────────────────────────────────────

    _FETCH_FIELDS = [
        "summary", "description", "issuetype", "status", "labels",
        "issuelinks", "priority", "reporter",
        "customfield_10020",  # Sprint (Cloud)
        "customfield_10014",  # Epic Link (classic project)
        "parent",             # Epic parent (next-gen project)
        "created", "updated",
    ]

    def _to_raw_document(self, issue: dict) -> RawDocument:
        fields = issue["fields"]

        body = self._extract_description(fields.get("description") or "")
        parent_id = self._extract_parent_id(fields)
        related_ids = self._extract_links(fields)

        # 날짜 파싱 (없으면 현재 시각)
        def _parse_dt(s: str | None) -> datetime:
            if not s:
                return datetime.utcnow()
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                return datetime.utcnow()

        return RawDocument(
            id=issue["key"],
            source="jira",
            title=fields.get("summary", "").strip(),
            body=body,
            url=f"{self._url}/browse/{issue['key']}",
            author=(fields.get("reporter") or {}).get("emailAddress", ""),
            created_at=_parse_dt(fields.get("created")),
            updated_at=_parse_dt(fields.get("updated")),
            parent_id=parent_id,
            related_ids=related_ids,
            labels=fields.get("labels", []),
            metadata={
                "jira_type": fields.get("issuetype", {}).get("name", "Task"),
                "status": fields.get("status", {}).get("name", "Open"),
                "priority": (fields.get("priority") or {}).get("name", "Medium"),
                "sprint": self._extract_sprint(fields),
            },
        )

    def _extract_parent_id(self, fields: dict) -> str | None:
        # Next-gen project parent
        parent = fields.get("parent")
        if parent:
            return parent["key"]
        # Classic project Epic Link
        epic_link = fields.get("customfield_10014")
        if epic_link and isinstance(epic_link, str):
            return epic_link
        return None

    def _extract_links(self, fields: dict) -> list[str]:
        linked: list[str] = []
        for link in fields.get("issuelinks", []):
            if "outwardIssue" in link:
                linked.append(link["outwardIssue"]["key"])
            if "inwardIssue" in link:
                linked.append(link["inwardIssue"]["key"])
        return list(dict.fromkeys(linked))

    def _extract_sprint(self, fields: dict) -> str:
        sprint_field = fields.get("customfield_10020")
        if not sprint_field:
            return ""
        if isinstance(sprint_field, list) and sprint_field:
            item = sprint_field[-1]
            if isinstance(item, dict):
                return item.get("name", "")
            if isinstance(item, str):
                m = re.search(r"name=([^,\]]+)", item)
                return m.group(1).strip() if m else item
        if isinstance(sprint_field, str):
            m = re.search(r"name=([^,\]]+)", sprint_field)
            return m.group(1).strip() if m else sprint_field
        return ""

    def _extract_description(self, description: Any) -> str:
        if not description:
            return ""
        if isinstance(description, str):
            return description.strip()
        if isinstance(description, dict):
            return _adf_to_text(description).strip()
        return str(description)

    # ── JQL 빌더 ──────────────────────────────────────────────────────────────

    def _build_jql(self, project_key: str, domain_keywords: list[str]) -> str:
        base = f"project = {project_key}"
        if domain_keywords:
            kw_clause = " OR ".join(f'text ~ "{kw}"' for kw in domain_keywords)
            base += f" AND ({kw_clause})"
        return base + " ORDER BY created ASC"


# ── ADF → 평문 변환 (Jira Cloud) ──────────────────────────────────────────────

def _adf_to_text(node: Any, depth: int = 0) -> str:  # noqa: C901
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
    if node_type == "mention":
        return "@" + node.get("attrs", {}).get("text", "someone")
    if node_type == "inlineCard":
        return "[" + node.get("attrs", {}).get("url", "") + "]"
    if node_type == "emoji":
        return node.get("attrs", {}).get("shortName", "")
    return "\n".join(p for p in parts if p)
