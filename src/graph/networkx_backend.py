"""NetworkX-based in-memory graph backend — zero infrastructure required."""
import pickle
from pathlib import Path
from typing import List

import networkx as nx

from src.graph.base import GraphBackend
from src.models.ontology import (
    GapFinding,
    OntologyEdge,
    OntologyNode,
    SubGraph,
)

PERSIST_PATH = Path(__file__).parent.parent.parent / "data" / "exports" / "graph.gpickle"


class NetworkXBackend(GraphBackend):
    def __init__(self, persist: bool = True) -> None:
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()
        self._persist = persist
        PERSIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        if persist and PERSIST_PATH.exists():
            self._load()

    # ------------------------------------------------------------------ persist
    def _save(self) -> None:
        if self._persist:
            with open(PERSIST_PATH, "wb") as f:
                pickle.dump(self._g, f)

    def _load(self) -> None:
        with open(PERSIST_PATH, "rb") as f:
            self._g = pickle.load(f)

    # ------------------------------------------------------------------ writes
    def merge_node(self, node: OntologyNode) -> None:
        self._g.add_node(
            node.id,
            type=node.type,
            name=node.name,
            description=node.description,
            status=node.status,
            labels=node.labels,
        )
        self._save()

    def merge_edge(self, edge: OntologyEdge) -> None:
        # Idempotency: skip if identical edge already exists
        existing = self._g.get_edge_data(edge.source_id, edge.target_id) or {}
        for _, data in existing.items():
            if data.get("relation") == edge.relation:
                return
        self._g.add_edge(
            edge.source_id,
            edge.target_id,
            relation=edge.relation,
            reasoning=edge.reasoning,
            is_inferred=edge.is_inferred,
        )
        self._save()

    def clear(self) -> None:
        self._g.clear()
        if self._persist and PERSIST_PATH.exists():
            PERSIST_PATH.unlink()

    # ------------------------------------------------------------------ reads
    def get_node(self, node_id: str) -> OntologyNode | None:
        if node_id not in self._g:
            return None
        data = self._g.nodes[node_id]
        return OntologyNode(
            id=node_id,
            type=data.get("type", "Issue"),
            name=data.get("name", node_id),
            description=data.get("description", ""),
            status=data.get("status", "Open"),
            labels=data.get("labels", []),
        )

    def query_full_graph(self) -> SubGraph:
        nodes: List[OntologyNode] = []
        for nid, data in self._g.nodes(data=True):
            nodes.append(
                OntologyNode(
                    id=nid,
                    type=data.get("type", "Issue"),
                    name=data.get("name", nid),
                    description=data.get("description", ""),
                    status=data.get("status", "Open"),
                    labels=data.get("labels", []),
                )
            )
        edges: List[OntologyEdge] = []
        for src, tgt, data in self._g.edges(data=True):
            edges.append(
                OntologyEdge(
                    source_id=src,
                    target_id=tgt,
                    relation=data.get("relation", "affects"),
                    reasoning=data.get("reasoning", ""),
                    is_inferred=data.get("is_inferred", False),
                )
            )
        return SubGraph(nodes=nodes, edges=edges)

    def query_orphan_nodes(self) -> List[OntologyNode]:
        """Nodes with no satisfies/implements/verifies edges (in or out)."""
        traceability_relations = {"satisfies", "implements", "verifies"}
        connected: set[str] = set()
        for src, tgt, data in self._g.edges(data=True):
            if data.get("relation") in traceability_relations:
                connected.add(src)
                connected.add(tgt)
        orphans: List[OntologyNode] = []
        for nid in self._g.nodes:
            if nid not in connected:
                node = self.get_node(nid)
                if node:
                    orphans.append(node)
        return orphans

    def get_traceability_chain(self, req_id: str) -> List[List[OntologyNode]]:
        """Return all nodes that have paths leading TO req_id (ancestors in directed graph).

        Edge semantics: CAM-010 --satisfies--> CAM-001 means edges point TOWARD requirements.
        So ancestors of a requirement = arch/design/verif nodes that satisfy/implement/verify it.
        """
        if req_id not in self._g:
            return []
        ancestor_ids = nx.ancestors(self._g, req_id)
        paths: List[List[OntologyNode]] = []
        for anc_id in ancestor_ids:
            try:
                path_nodes = nx.shortest_path(self._g, anc_id, req_id)
                chain = [self.get_node(n) for n in path_nodes]
                paths.append([n for n in chain if n is not None])
            except nx.NetworkXNoPath:
                continue
        return paths

    def get_reachable_node_types(self, req_id: str) -> set[str]:
        """Return all node types that have paths leading to req_id."""
        if req_id not in self._g:
            return set()
        ancestor_ids = nx.ancestors(self._g, req_id)
        types: set[str] = set()
        for nid in ancestor_ids:
            data = self._g.nodes[nid]
            types.add(data.get("type", ""))
        return types

    def detect_conflicts(self) -> List[GapFinding]:
        """Find targets that have multiple 'implements' sources — design conflict."""
        from collections import defaultdict
        impl_targets: dict[str, List[str]] = defaultdict(list)
        for src, tgt, data in self._g.edges(data=True):
            if data.get("relation") == "implements":
                impl_targets[tgt].append(src)

        findings: List[GapFinding] = []
        for tgt, sources in impl_targets.items():
            if len(sources) > 1:
                findings.append(
                    GapFinding(
                        gap_id=f"CONFLICT-{tgt}",
                        gap_type="conflict",
                        severity="high",
                        affected_node_ids=[tgt] + sources,
                        description=(
                            f"'{tgt}' has {len(sources)} conflicting implementations: "
                            + ", ".join(sources)
                        ),
                        suggested_action=(
                            f"Review and select one canonical implementation for '{tgt}'. "
                            "Mark alternatives as superseded or rejected."
                        ),
                    )
                )
        return findings

    def node_count(self) -> int:
        return self._g.number_of_nodes()

    def edge_count(self) -> int:
        return self._g.number_of_edges()

    # ------------------------------------------------------------------ helpers
    def get_neighbors(self, node_id: str) -> List[str]:
        return list(self._g.successors(node_id)) + list(self._g.predecessors(node_id))
