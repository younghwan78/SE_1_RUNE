"""Abstract graph backend."""
from abc import ABC, abstractmethod
from typing import List
from src.models.ontology import GapFinding, OntologyEdge, OntologyNode, SubGraph


class GraphBackend(ABC):
    @abstractmethod
    def merge_node(self, node: OntologyNode) -> None:
        """Upsert a node — idempotent."""
        ...

    @abstractmethod
    def merge_edge(self, edge: OntologyEdge) -> None:
        """Upsert an edge — idempotent."""
        ...

    @abstractmethod
    def query_full_graph(self) -> SubGraph:
        """Return all nodes and edges."""
        ...

    @abstractmethod
    def query_orphan_nodes(self) -> List[OntologyNode]:
        """Return nodes with no satisfies/implements edges (in or out)."""
        ...

    @abstractmethod
    def get_traceability_chain(self, req_id: str) -> List[List[OntologyNode]]:
        """BFS from a requirement node — return all reachable chains."""
        ...

    @abstractmethod
    def get_node(self, node_id: str) -> OntologyNode | None:
        ...

    @abstractmethod
    def detect_conflicts(self) -> List[GapFinding]:
        """Detect nodes that have multiple 'implements' edges to the same target."""
        ...

    @abstractmethod
    def node_count(self) -> int:
        ...

    @abstractmethod
    def edge_count(self) -> int:
        ...

    @abstractmethod
    def clear(self) -> None:
        """Remove all data."""
        ...
