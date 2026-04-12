"""Core ontology data models for MBSE traceability graph."""
from typing import List, Literal
from pydantic import BaseModel, Field


NodeType = Literal["Requirement", "Architecture_Block", "Design_Spec", "Verification", "Issue"]
EdgeRelation = Literal["satisfies", "verifies", "affects", "implements", "blocks"]
GapType = Literal["orphan_node", "missing_verification", "conflict", "cross_domain_hidden"]
GapSeverity = Literal["critical", "high", "medium", "low"]


class OntologyNode(BaseModel):
    id: str = Field(description="JIRA Ticket ID (e.g., CAM-123) or inferred Component ID")
    type: NodeType
    name: str = Field(description="Summary of the ticket or component name")
    description: str
    status: str = Field(default="Open")
    labels: List[str] = Field(default_factory=list)
    # AI reclassification tracking
    original_jira_type: str = Field(default="", description="Original JIRA issue type before AI reclassification")
    ai_classified: bool = Field(default=False, description="True if type was assigned/confirmed by AI")


class OntologyEdge(BaseModel):
    source_id: str
    target_id: str
    relation: EdgeRelation
    reasoning: str = Field(
        description="Logic behind this connection. Must start with '[INFERRED]' if AI-derived."
    )
    is_inferred: bool = Field(
        default=False,
        description="True if AI-inferred, False if from original ticket linked_issues",
    )


class ProposedUpdate(BaseModel):
    nodes: List[OntologyNode]
    edges: List[OntologyEdge]
    confidence_score: float = Field(ge=0.0, le=1.0)
    batch_id: str = Field(default="")


class GapFinding(BaseModel):
    gap_id: str
    gap_type: GapType
    severity: GapSeverity
    affected_node_ids: List[str]
    description: str
    suggested_action: str


class SubGraph(BaseModel):
    nodes: List[OntologyNode]
    edges: List[OntologyEdge]


class RunMetadata(BaseModel):
    run_id: str
    started_at: str
    finished_at: str = ""
    total_tickets: int = 0
    total_nodes_created: int = 0
    total_edges_created: int = 0
    total_gaps_found: int = 0
    errors: List[str] = Field(default_factory=list)
