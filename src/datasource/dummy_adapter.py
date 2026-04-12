"""Dummy data source adapter — loads from local JSON file."""
import json
import os
import time
from pathlib import Path
from typing import List

from src.datasource.base import DataSourceAdapter
from src.models.jira_ticket import JiraTicket
from src.models.ontology import OntologyEdge

DUMMY_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "dummy" / "ulysses_tickets.json"


class DummyAdapter(DataSourceAdapter):
    def __init__(self) -> None:
        self._data: dict = self._load()
        self._latency_ms: int = int(os.getenv("DUMMY_LATENCY_MS", "0"))

    def _load(self) -> dict:
        if not DUMMY_DATA_PATH.exists():
            raise FileNotFoundError(f"Dummy data not found: {DUMMY_DATA_PATH}")
        with open(DUMMY_DATA_PATH, encoding="utf-8") as f:
            return json.load(f)

    def _simulate_latency(self) -> None:
        if self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000)

    def fetch_all_tickets(self) -> List[JiraTicket]:
        self._simulate_latency()
        return [
            JiraTicket(
                id=t["id"],
                type=t["type"],
                summary=t["summary"],
                description=t["description"],
                status=t.get("status", "Open"),
                labels=t.get("labels", []),
                linked_issue_ids=t.get("linked_issue_ids", []),
                reporter=t.get("reporter", ""),
                sprint=t.get("sprint", ""),
                priority=t.get("priority", "Medium"),
            )
            for t in self._data["tickets"]
        ]

    def fetch_ticket(self, ticket_id: str) -> JiraTicket:
        self._simulate_latency()
        for t in self._data["tickets"]:
            if t["id"] == ticket_id:
                return JiraTicket(
                    id=t["id"],
                    type=t["type"],
                    summary=t["summary"],
                    description=t["description"],
                    status=t.get("status", "Open"),
                    labels=t.get("labels", []),
                    linked_issue_ids=t.get("linked_issue_ids", []),
                    reporter=t.get("reporter", ""),
                    sprint=t.get("sprint", ""),
                    priority=t.get("priority", "Medium"),
                )
        raise KeyError(f"Ticket not found: {ticket_id}")

    def fetch_pre_computed_edges(self) -> List[OntologyEdge]:
        """Return pre-computed edges from the dummy data file (for demo without LLM)."""
        edges: List[OntologyEdge] = []
        for e in self._data.get("pre_computed_edges", []):
            edges.append(
                OntologyEdge(
                    source_id=e["source_id"],
                    target_id=e["target_id"],
                    relation=e["relation"],
                    reasoning=e["reasoning"],
                    is_inferred=e.get("is_inferred", False),
                )
            )
        return edges

    @property
    def project_name(self) -> str:
        return self._data.get("project", "Unknown")
