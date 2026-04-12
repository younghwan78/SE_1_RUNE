"""Traceability KPI computation engine."""
from dataclasses import dataclass, field
from typing import Dict, List

from src.graph.base import GraphBackend
from src.models.ontology import GapFinding, OntologyNode


@dataclass
class TraceabilityReport:
    # Coverage
    total_requirements: int = 0
    requirements_with_full_chain: int = 0
    coverage_score: float = 0.0  # %

    # Orphan
    total_nodes: int = 0
    orphan_nodes: int = 0
    orphan_rate: float = 0.0  # %

    # Chain completeness
    avg_chain_depth: float = 0.0  # out of 4.0

    # Conflicts
    conflict_count: int = 0

    # Verification coverage
    total_arch_blocks: int = 0
    verified_arch_blocks: int = 0
    verification_coverage: float = 0.0  # %

    # Inferred links
    total_edges: int = 0
    inferred_edges: int = 0

    # Gaps
    gaps: List[GapFinding] = field(default_factory=list)

    # Layer completeness per requirement (for heatmap)
    req_layer_matrix: Dict[str, Dict[str, bool]] = field(default_factory=dict)


LAYER_ORDER = ["Requirement", "Architecture_Block", "Design_Spec", "Verification"]


class MetricsEngine:
    def __init__(self, backend: GraphBackend) -> None:
        self._b = backend

    def compute_all(self) -> TraceabilityReport:
        graph = self._b.query_full_graph()
        report = TraceabilityReport()

        nodes_by_id: Dict[str, OntologyNode] = {n.id: n for n in graph.nodes}
        edges = graph.edges

        report.total_nodes = len(graph.nodes)
        report.total_edges = len(edges)
        report.inferred_edges = sum(1 for e in edges if e.is_inferred)

        # --- Requirement nodes ---
        req_nodes = [n for n in graph.nodes if n.type == "Requirement"]
        report.total_requirements = len(req_nodes)

        # --- Architecture_Block nodes ---
        arch_nodes = [n for n in graph.nodes if n.type == "Architecture_Block"]
        report.total_arch_blocks = len(arch_nodes)

        # --- Orphan rate ---
        orphans = self._b.query_orphan_nodes()
        report.orphan_nodes = len(orphans)
        report.orphan_rate = (
            round(len(orphans) / max(len(graph.nodes), 1) * 100, 1)
        )

        # --- Conflicts ---
        conflicts = self._b.detect_conflicts()
        report.conflict_count = len(conflicts)

        # --- Chain completeness per requirement ---
        req_layer_matrix: Dict[str, Dict[str, bool]] = {}
        full_chain_count = 0

        for req in req_nodes:
            # Use ancestor-based reachability (edges point TOWARD requirements)
            reachable_types: set[str] = {req.type}
            if hasattr(self._b, "get_reachable_node_types"):
                reachable_types |= self._b.get_reachable_node_types(req.id)
            else:
                chains = self._b.get_traceability_chain(req.id)
                for chain in chains:
                    for node in chain:
                        reachable_types.add(node.type)

            layer_coverage = {layer: (layer in reachable_types) for layer in LAYER_ORDER}
            req_layer_matrix[req.id] = layer_coverage

            # Full chain = all 4 layers present
            if all(layer_coverage.values()):
                full_chain_count += 1

        report.requirements_with_full_chain = full_chain_count
        report.coverage_score = round(
            full_chain_count / max(len(req_nodes), 1) * 100, 1
        )
        report.req_layer_matrix = req_layer_matrix

        # --- Average chain depth ---
        depth_scores = [
            sum(v for v in layers.values()) / len(LAYER_ORDER)
            for layers in req_layer_matrix.values()
        ]
        if depth_scores:
            report.avg_chain_depth = round(
                sum(depth_scores) / len(depth_scores) * len(LAYER_ORDER), 2
            )

        # --- Verification coverage for arch blocks ---
        verifies_targets: set[str] = {
            e.target_id for e in edges if e.relation == "verifies"
        }
        report.verified_arch_blocks = sum(
            1 for n in arch_nodes if n.id in verifies_targets
        )
        report.verification_coverage = round(
            report.verified_arch_blocks / max(len(arch_nodes), 1) * 100, 1
        )

        # --- Gap findings ---
        gaps: List[GapFinding] = []
        gaps.extend(conflicts)
        gaps.extend(self._detect_missing_verification(graph.nodes, edges))
        gaps.extend(self._detect_orphans(orphans))
        gaps.extend(self._detect_unimplemented_requirements(req_nodes, edges, nodes_by_id))
        report.gaps = gaps

        return report

    def _detect_missing_verification(
        self, nodes: List[OntologyNode], edges
    ) -> List[GapFinding]:
        """Architecture blocks with no verifies-incoming edge."""
        verifies_targets = {e.target_id for e in edges if e.relation == "verifies"}
        findings: List[GapFinding] = []
        for node in nodes:
            if node.type == "Architecture_Block" and node.id not in verifies_targets:
                findings.append(
                    GapFinding(
                        gap_id=f"NO-VERIF-{node.id}",
                        gap_type="missing_verification",
                        severity="high",
                        affected_node_ids=[node.id],
                        description=f"Architecture block '{node.id}: {node.name}' has no verification ticket.",
                        suggested_action=f"Create a Verification ticket that targets '{node.id}'.",
                    )
                )
        return findings

    def _detect_orphans(self, orphans: List[OntologyNode]) -> List[GapFinding]:
        findings: List[GapFinding] = []
        for node in orphans:
            severity = "critical" if node.type == "Requirement" else "medium"
            findings.append(
                GapFinding(
                    gap_id=f"ORPHAN-{node.id}",
                    gap_type="orphan_node",
                    severity=severity,
                    affected_node_ids=[node.id],
                    description=(
                        f"'{node.id}: {node.name}' ({node.type}) has no traceability links."
                    ),
                    suggested_action=(
                        "Link this node to a parent requirement (satisfies) "
                        "or to a child design/verification (implements/verifies)."
                    ),
                )
            )
        return findings

    def _detect_unimplemented_requirements(
        self,
        req_nodes: List[OntologyNode],
        edges,
        nodes_by_id: Dict[str, OntologyNode],
    ) -> List[GapFinding]:
        """Requirements with no 'satisfies' incoming edge from arch/design."""
        satisfies_targets = {e.target_id for e in edges if e.relation == "satisfies"}
        findings: List[GapFinding] = []
        for req in req_nodes:
            if req.id not in satisfies_targets:
                findings.append(
                    GapFinding(
                        gap_id=f"NO-IMPL-{req.id}",
                        gap_type="orphan_node",
                        severity="critical",
                        affected_node_ids=[req.id],
                        description=(
                            f"Requirement '{req.id}: {req.name}' has no architecture "
                            "or design satisfying it."
                        ),
                        suggested_action=(
                            "Create an Architecture_Block or Design_Spec with a 'satisfies' "
                            f"edge pointing to '{req.id}'."
                        ),
                    )
                )
        return findings
