"""Real JIRA adapter — requires JIRA_URL, JIRA_EMAIL, JIRA_TOKEN env vars."""
import os
from typing import List

from src.datasource.base import DataSourceAdapter
from src.models.jira_ticket import JiraTicket


class JiraAdapter(DataSourceAdapter):
    def __init__(self) -> None:
        self._url: str = os.environ["JIRA_URL"]
        self._email: str = os.environ["JIRA_EMAIL"]
        self._token: str = os.environ["JIRA_TOKEN"]
        self._project_key: str = os.environ["JIRA_PROJECT_KEY"]
        self._client = self._build_client()

    def _build_client(self):  # type: ignore[return]
        try:
            from atlassian import Jira  # type: ignore[import]
            return Jira(
                url=self._url,
                username=self._email,
                password=self._token,
                cloud=True,
            )
        except ImportError as exc:
            raise ImportError(
                "atlassian-python-api is required for JIRA mode. "
                "Install with: uv add atlassian-python-api"
            ) from exc

    def fetch_all_tickets(self) -> List[JiraTicket]:
        jql = f"project = {self._project_key} ORDER BY created DESC"
        issues = self._client.jql(jql, limit=200)
        return [self._to_ticket(issue) for issue in issues.get("issues", [])]

    def fetch_ticket(self, ticket_id: str) -> JiraTicket:
        issue = self._client.issue(ticket_id)
        return self._to_ticket(issue)

    def _to_ticket(self, issue: dict) -> JiraTicket:
        fields = issue["fields"]
        linked_ids: List[str] = [
            link["outwardIssue"]["key"]
            for link in fields.get("issuelinks", [])
            if "outwardIssue" in link
        ]
        return JiraTicket(
            id=issue["key"],
            type=fields.get("issuetype", {}).get("name", "Issue"),
            summary=fields.get("summary", ""),
            description=fields.get("description") or "",
            status=fields.get("status", {}).get("name", "Open"),
            labels=fields.get("labels", []),
            linked_issue_ids=linked_ids,
            reporter=fields.get("reporter", {}).get("emailAddress", ""),
            sprint="",
            priority=fields.get("priority", {}).get("name", "Medium"),
        )
