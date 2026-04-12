"""LangGraph AgentState TypedDict."""
from typing import List, TypedDict
from src.models.jira_ticket import JiraTicket
from src.models.ontology import GapFinding, OntologyNode, ProposedUpdate, RunMetadata


class AgentState(TypedDict):
    tickets: List[JiraTicket]
    batch_index: int
    batch_size: int
    proposed_updates: List[ProposedUpdate]
    approved_updates: List[ProposedUpdate]
    rejected_updates: List[ProposedUpdate]
    discovered_gaps: List[GapFinding]
    errors: List[str]
    run_metadata: RunMetadata
    # look-back context: nodes committed so far (for cross-batch relationship inference)
    committed_nodes: List[OntologyNode]
