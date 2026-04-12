"""Abstract data source adapter."""
from abc import ABC, abstractmethod
from typing import List
from src.models.jira_ticket import JiraTicket


class DataSourceAdapter(ABC):
    @abstractmethod
    def fetch_all_tickets(self) -> List[JiraTicket]:
        """Fetch all tickets for the configured project."""
        ...

    @abstractmethod
    def fetch_ticket(self, ticket_id: str) -> JiraTicket:
        """Fetch a single ticket by ID."""
        ...
