"""JIRA REST API adapter — DATASOURCE_MODE=jira 일 때 사용.

필수 환경 변수:
    JIRA_URL          https://your-company.atlassian.net  (Cloud)
                      https://jira.internal.company.com   (On-premise)
    JIRA_EMAIL        your.email@company.com
    JIRA_TOKEN        API Token (Cloud) 또는 Personal Access Token (On-premise)
    JIRA_PROJECT_KEY  프로젝트 키 (예: CAM, PROJ)

선택 환경 변수:
    JIRA_CLOUD        "true" (기본) | "false" (On-premise Server/DC)
    JIRA_TYPE_MAP     JSON 문자열로 커스텀 타입 매핑 오버라이드
                      예: '{"Epic":"Requirement","Technical Task":"Design_Spec"}'
    JIRA_MAX_RESULTS  한 번에 가져올 티켓 수 (기본: 100, 최대: 100)
    JIRA_JQL_EXTRA    기본 JQL에 추가할 필터 조건
                      예: "AND sprint in openSprints()"
"""
import json
import logging
import os
import re
from typing import Any

from src.datasource.base import DataSourceAdapter
from src.models.jira_ticket import JiraTicket

logger = logging.getLogger(__name__)

# ── 기본 이슈 타입 매핑 ────────────────────────────────────────────────────────
# 사내 JIRA 운용 방식에 따라 .env의 JIRA_TYPE_MAP으로 오버라이드 가능
_DEFAULT_TYPE_MAP: dict[str, str] = {
    # 표준 JIRA 타입
    "Epic":          "Requirement",
    "Story":         "Architecture_Block",
    "Task":          "Design_Spec",
    "Sub-task":      "Design_Spec",
    "Bug":           "Issue",
    "Test":          "Verification",
    # 커스텀 타입 예시 (사내 환경에서 자주 나오는 이름들)
    "Requirement":   "Requirement",
    "Feature":       "Requirement",
    "Architecture":  "Architecture_Block",
    "Design":        "Design_Spec",
    "Implementation":"Design_Spec",
    "Verification":  "Verification",
    "Test Case":     "Verification",
    "Risk":          "Issue",
    "Impediment":    "Issue",
}

_VALID_TYPES = {"Requirement", "Architecture_Block", "Design_Spec", "Verification", "Issue"}


class JiraAdapter(DataSourceAdapter):
    """atlassian-python-api 기반 JIRA 어댑터.

    설치: uv add atlassian-python-api
    """

    def __init__(self) -> None:
        self._url:         str  = os.environ["JIRA_URL"].rstrip("/")
        self._email:       str  = os.environ["JIRA_EMAIL"]
        self._token:       str  = os.environ["JIRA_TOKEN"]
        self._project_key: str  = os.environ["JIRA_PROJECT_KEY"]
        self._is_cloud:    bool = os.getenv("JIRA_CLOUD", "true").lower() != "false"
        self._max_results: int  = int(os.getenv("JIRA_MAX_RESULTS", "100"))
        self._jql_extra:   str  = os.getenv("JIRA_JQL_EXTRA", "")

        # 커스텀 타입 매핑 오버라이드 (JIRA_TYPE_MAP env)
        self._type_map: dict[str, str] = dict(_DEFAULT_TYPE_MAP)
        custom_map_json = os.getenv("JIRA_TYPE_MAP", "")
        if custom_map_json:
            try:
                self._type_map.update(json.loads(custom_map_json))
            except json.JSONDecodeError as e:
                logger.warning("JIRA_TYPE_MAP JSON 파싱 실패, 기본값 사용: %s", e)

        self._client = self._build_client()

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

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch_all_tickets(self) -> list[JiraTicket]:
        """프로젝트 전체 티켓을 페이지네이션으로 수집."""
        jql = f"project = {self._project_key} ORDER BY created ASC"
        if self._jql_extra:
            jql = f"project = {self._project_key} {self._jql_extra} ORDER BY created ASC"

        tickets: list[JiraTicket] = []
        start_at = 0

        while True:
            logger.info("JIRA 티켓 수집 중... start=%d", start_at)
            result = self._client.jql(
                jql,
                start=start_at,
                limit=self._max_results,
                fields=[
                    "summary", "description", "issuetype", "status",
                    "labels", "issuelinks", "priority", "reporter",
                    "customfield_10020",   # Sprint (Jira Cloud 기본 필드명)
                    "customfield_10014",   # Epic Link (일부 환경)
                    "parent",              # Epic parent (Next-gen projects)
                ],
            )
            issues: list[dict] = result.get("issues", [])
            if not issues:
                break

            for issue in issues:
                try:
                    tickets.append(self._to_ticket(issue))
                except Exception as e:
                    logger.warning("티켓 변환 실패 [%s]: %s", issue.get("key"), e)

            start_at += len(issues)
            total = result.get("total", 0)
            logger.info("  %d / %d 수집 완료", start_at, total)
            if start_at >= total:
                break

        logger.info("총 %d개 티켓 수집 완료 (프로젝트: %s)", len(tickets), self._project_key)
        return tickets

    def fetch_ticket(self, ticket_id: str) -> JiraTicket:
        """단일 티켓 조회."""
        issue = self._client.issue(ticket_id)
        return self._to_ticket(issue)

    def fetch_updated_since(self, since_iso: str) -> list[JiraTicket]:
        """증분 동기화 — 특정 시각 이후 변경된 티켓만 수집.

        Args:
            since_iso: ISO 8601 문자열, 예: "2024-01-01T00:00:00"
        """
        jql = (
            f"project = {self._project_key} "
            f"AND updated >= '{since_iso}' "
            f"ORDER BY updated ASC"
        )
        result = self._client.jql(jql, limit=500)
        return [self._to_ticket(i) for i in result.get("issues", [])]

    def list_issue_types(self) -> list[dict[str, str]]:
        """프로젝트에서 사용 중인 이슈 타입 목록 반환.

        타입 매핑 설정 시 참고용으로 사용.
        반환: [{"id": "...", "name": "Epic", "description": "..."}, ...]
        """
        meta = self._client.get_project_issue_types(self._project_key)
        return [
            {"id": t.get("id", ""), "name": t.get("name", ""), "description": t.get("description", "")}
            for t in meta
        ]

    # ── 내부 변환 메서드 ──────────────────────────────────────────────────────

    def _to_ticket(self, issue: dict) -> JiraTicket:
        fields = issue["fields"]

        raw_type  = fields.get("issuetype", {}).get("name", "Task")
        ont_type  = self._map_type(raw_type)
        linked_ids = self._extract_links(fields)
        sprint     = self._extract_sprint(fields)
        desc       = self._extract_description(fields.get("description") or "")

        return JiraTicket(
            id=issue["key"],
            type=ont_type,
            summary=fields.get("summary", ""),
            description=desc,
            status=fields.get("status", {}).get("name", "Open"),
            labels=fields.get("labels", []),
            linked_issue_ids=linked_ids,
            reporter=(fields.get("reporter") or {}).get("emailAddress", ""),
            sprint=sprint,
            priority=(fields.get("priority") or {}).get("name", "Medium"),
        )

    def _map_type(self, jira_type: str) -> str:
        """JIRA 이슈 타입 → OntologyNode 타입 변환.

        매핑되지 않은 타입은 'Design_Spec'으로 fallback.
        알 수 없는 타입은 경고 로그를 남김.
        """
        result = self._type_map.get(jira_type)
        if result is None:
            logger.warning(
                "알 수 없는 JIRA 이슈 타입: '%s' → 'Design_Spec'으로 fallback. "
                "JIRA_TYPE_MAP 환경 변수로 커스텀 매핑을 추가하세요.",
                jira_type,
            )
            return "Design_Spec"
        if result not in _VALID_TYPES:
            logger.warning("잘못된 매핑 대상: '%s' → 기본값 'Design_Spec' 사용", result)
            return "Design_Spec"
        return result

    def _extract_links(self, fields: dict) -> list[str]:
        """issuelinks 필드에서 연결된 티켓 ID 추출 (양방향)."""
        linked: list[str] = []
        for link in fields.get("issuelinks", []):
            if "outwardIssue" in link:
                linked.append(link["outwardIssue"]["key"])
            if "inwardIssue" in link:
                linked.append(link["inwardIssue"]["key"])
        # Epic Link (customfield_10014)
        epic_link = fields.get("customfield_10014")
        if epic_link and isinstance(epic_link, str):
            linked.append(epic_link)
        # Parent (Next-gen projects)
        parent = fields.get("parent")
        if parent and isinstance(parent, dict):
            linked.append(parent["key"])
        return list(dict.fromkeys(linked))  # 중복 제거, 순서 유지

    def _extract_sprint(self, fields: dict) -> str:
        """Sprint 커스텀 필드 파싱.

        Jira Cloud: customfield_10020 → list of sprint objects or strings.
        On-premise: 문자열 포맷이 다를 수 있음.
        """
        sprint_field = fields.get("customfield_10020")
        if not sprint_field:
            return ""
        # Cloud: 리스트 형태
        if isinstance(sprint_field, list) and sprint_field:
            item = sprint_field[-1]  # 가장 최근 스프린트
            if isinstance(item, dict):
                return item.get("name", "")
            if isinstance(item, str):
                # "com.atlassian.greenhopper...name=Sprint 3,..." 형식
                match = re.search(r"name=([^,\]]+)", item)
                return match.group(1).strip() if match else item
        if isinstance(sprint_field, str):
            match = re.search(r"name=([^,\]]+)", sprint_field)
            return match.group(1).strip() if match else sprint_field
        return ""

    def _extract_description(self, description: Any) -> str:
        """JIRA description 필드를 평문으로 변환.

        - Cloud: Atlassian Document Format (ADF, dict)
        - On-premise: Markdown / plain text (str)
        """
        if not description:
            return ""
        if isinstance(description, str):
            return description.strip()
        if isinstance(description, dict):
            # ADF 포맷 (Jira Cloud)
            return _adf_to_text(description).strip()
        return str(description)


# ── ADF (Atlassian Document Format) → 평문 변환 ──────────────────────────────

def _adf_to_text(node: Any, depth: int = 0) -> str:  # noqa: C901
    """ADF JSON 트리를 재귀적으로 순회하여 평문 추출.

    ADF 스펙: https://developer.atlassian.com/cloud/jira/platform/apis/document/
    """
    if not isinstance(node, dict):
        return ""

    node_type = node.get("type", "")
    parts: list[str] = []

    # Leaf: 텍스트 노드
    if node_type == "text":
        text = node.get("text", "")
        # 마크 처리 (bold, italic 등 — 평문이므로 무시)
        return text

    # 자식 노드 재귀 처리
    for child in node.get("content", []):
        parts.append(_adf_to_text(child, depth + 1))

    # 블록 노드 타입별 포맷
    if node_type in ("paragraph", "blockquote"):
        return " ".join(p for p in parts if p) + "\n"
    if node_type == "heading":
        text = " ".join(p for p in parts if p)
        return f"\n{text}\n"
    if node_type in ("bulletList", "orderedList"):
        return "\n".join(p.strip() for p in parts if p.strip()) + "\n"
    if node_type == "listItem":
        return "- " + " ".join(p for p in parts if p).replace("\n", " ")
    if node_type == "codeBlock":
        code = " ".join(p for p in parts if p)
        return f"[code: {code}]"
    if node_type == "inlineCard":
        url = node.get("attrs", {}).get("url", "")
        return f"[{url}]"
    if node_type == "hardBreak":
        return "\n"
    if node_type == "mention":
        return "@" + node.get("attrs", {}).get("text", "someone")
    if node_type == "emoji":
        return node.get("attrs", {}).get("shortName", "")

    # doc, tableRow, tableCell 등 컨테이너
    return "\n".join(p for p in parts if p)
