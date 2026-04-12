"""Internal canonical JIRA ticket model."""
from typing import List, Optional
from pydantic import BaseModel, Field


class JiraTicket(BaseModel):
    id: str = Field(description="Ticket ID e.g. CAM-001")
    type: str = Field(description="Issue type: Requirement, Architecture_Block, Design_Spec, Verification, Issue")
    summary: str
    description: str
    status: str = Field(default="Open")
    labels: List[str] = Field(default_factory=list)
    linked_issue_ids: List[str] = Field(default_factory=list, description="Explicit links from the ticket")
    reporter: str = Field(default="")
    sprint: str = Field(default="")
    priority: str = Field(default="Medium")
