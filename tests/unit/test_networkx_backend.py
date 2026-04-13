"""NetworkXBackend 단위 테스트."""
import pytest

from src.graph.networkx_backend import NetworkXBackend
from src.models.ontology import OntologyEdge, OntologyNode
from tests.conftest import make_edge, make_node


# ── merge_node ────────────────────────────────────────────────────────────────

class TestMergeNode:
    def test_add_single_node(self, empty_backend):
        empty_backend.merge_node(make_node(id="A"))
        assert empty_backend.node_count() == 1

    def test_add_multiple_nodes(self, empty_backend):
        for i in range(5):
            empty_backend.merge_node(make_node(id=f"N-{i:03d}"))
        assert empty_backend.node_count() == 5

    def test_idempotent_same_id(self, empty_backend):
        n = make_node(id="A", name="first")
        empty_backend.merge_node(n)
        empty_backend.merge_node(make_node(id="A", name="second"))
        assert empty_backend.node_count() == 1  # 중복 없음

    def test_get_node_returns_correct(self, empty_backend):
        n = make_node(id="CAM-001", type="Requirement", name="latency req")
        empty_backend.merge_node(n)
        result = empty_backend.get_node("CAM-001")
        assert result is not None
        assert result.id == "CAM-001"
        assert result.type == "Requirement"

    def test_get_nonexistent_node_returns_none(self, empty_backend):
        assert empty_backend.get_node("DOES-NOT-EXIST") is None


# ── merge_edge ────────────────────────────────────────────────────────────────

class TestMergeEdge:
    def test_add_single_edge(self, empty_backend):
        empty_backend.merge_node(make_node(id="A"))
        empty_backend.merge_node(make_node(id="B"))
        empty_backend.merge_edge(make_edge("A", "B", "satisfies"))
        assert empty_backend.edge_count() == 1

    def test_idempotent_same_edge(self, empty_backend):
        empty_backend.merge_node(make_node(id="A"))
        empty_backend.merge_node(make_node(id="B"))
        empty_backend.merge_edge(make_edge("A", "B", "satisfies"))
        empty_backend.merge_edge(make_edge("A", "B", "satisfies"))
        assert empty_backend.edge_count() == 1

    def test_different_relations_not_deduplicated(self, empty_backend):
        empty_backend.merge_node(make_node(id="A"))
        empty_backend.merge_node(make_node(id="B"))
        empty_backend.merge_edge(make_edge("A", "B", "satisfies"))
        empty_backend.merge_edge(make_edge("A", "B", "affects"))
        assert empty_backend.edge_count() == 2

    def test_inferred_flag_preserved(self, empty_backend):
        empty_backend.merge_node(make_node(id="A"))
        empty_backend.merge_node(make_node(id="B"))
        empty_backend.merge_edge(make_edge("A", "B", "satisfies", is_inferred=True))
        sg = empty_backend.query_full_graph()
        assert sg.edges[0].is_inferred is True


# ── query_full_graph ──────────────────────────────────────────────────────────

class TestQueryFullGraph:
    def test_empty_graph(self, empty_backend):
        sg = empty_backend.query_full_graph()
        assert len(sg.nodes) == 0
        assert len(sg.edges) == 0

    def test_loaded_graph_counts(self, loaded_backend):
        sg = loaded_backend.query_full_graph()
        assert len(sg.nodes) == 18
        assert len(sg.edges) == 20

    def test_inferred_edges_in_loaded(self, loaded_backend):
        sg = loaded_backend.query_full_graph()
        inferred = [e for e in sg.edges if e.is_inferred]
        assert len(inferred) == 4


# ── query_orphan_nodes ────────────────────────────────────────────────────────

class TestQueryOrphanNodes:
    def test_all_orphans_when_no_edges(self, empty_backend):
        for i in range(3):
            empty_backend.merge_node(make_node(id=f"N-{i}"))
        assert len(empty_backend.query_orphan_nodes()) == 3

    def test_connected_node_not_orphan(self, empty_backend):
        empty_backend.merge_node(make_node(id="A", type="Design_Spec"))
        empty_backend.merge_node(make_node(id="B", type="Requirement"))
        empty_backend.merge_edge(make_edge("A", "B", "satisfies"))
        orphans = empty_backend.query_orphan_nodes()
        orphan_ids = [o.id for o in orphans]
        assert "A" not in orphan_ids
        assert "B" not in orphan_ids

    def test_affects_edge_makes_orphan(self, empty_backend):
        """affects/blocks는 traceability 관계 아니므로 여전히 고아."""
        empty_backend.merge_node(make_node(id="A", type="Issue"))
        empty_backend.merge_node(make_node(id="B", type="Requirement"))
        empty_backend.merge_edge(make_edge("A", "B", "affects"))
        # affects는 orphan 판별에서 제외 (satisfies/implements/verifies만 연결 인정)
        orphans = empty_backend.query_orphan_nodes()
        assert len(orphans) == 2

    def test_loaded_backend_orphan_count(self, loaded_backend):
        orphans = loaded_backend.query_orphan_nodes()
        assert len(orphans) == 5

    def test_loaded_backend_orphan_ids(self, loaded_backend):
        orphan_ids = sorted([o.id for o in loaded_backend.query_orphan_nodes()])
        assert orphan_ids == ["CAM-040", "CAM-041", "CAM-042", "CAM-050", "CAM-051"]


# ── get_traceability_chain ────────────────────────────────────────────────────

class TestTraceabilityChain:
    def test_empty_for_isolated_node(self, empty_backend):
        empty_backend.merge_node(make_node(id="R", type="Requirement"))
        assert empty_backend.get_traceability_chain("R") == []

    def test_single_hop_chain(self, empty_backend):
        empty_backend.merge_node(make_node(id="R", type="Requirement"))
        empty_backend.merge_node(make_node(id="A", type="Architecture_Block"))
        empty_backend.merge_edge(make_edge("A", "R", "satisfies"))
        chains = empty_backend.get_traceability_chain("R")
        assert len(chains) >= 1
        all_ids = {n.id for path in chains for n in path}
        assert "A" in all_ids

    def test_uses_ancestors_not_descendants(self, empty_backend):
        """엣지 방향: child→parent. CAM-001의 ancestors가 존재해야 함."""
        empty_backend.merge_node(make_node(id="R", type="Requirement"))
        empty_backend.merge_node(make_node(id="A", type="Architecture_Block"))
        empty_backend.merge_node(make_node(id="D", type="Design_Spec"))
        empty_backend.merge_edge(make_edge("A", "R", "satisfies"))
        empty_backend.merge_edge(make_edge("D", "A", "implements"))
        chains = empty_backend.get_traceability_chain("R")
        all_ids = {n.id for path in chains for n in path}
        assert "A" in all_ids
        assert "D" in all_ids

    def test_cam001_chain_not_empty(self, loaded_backend):
        chains = loaded_backend.get_traceability_chain("CAM-001")
        assert len(chains) > 0

    def test_nonexistent_node_returns_empty(self, empty_backend):
        assert empty_backend.get_traceability_chain("GHOST") == []


# ── get_reachable_node_types ──────────────────────────────────────────────────

class TestReachableNodeTypes:
    def test_isolated_node_empty(self, empty_backend):
        empty_backend.merge_node(make_node(id="R", type="Requirement"))
        assert empty_backend.get_reachable_node_types("R") == set()

    def test_single_upstream(self, empty_backend):
        empty_backend.merge_node(make_node(id="R", type="Requirement"))
        empty_backend.merge_node(make_node(id="A", type="Architecture_Block"))
        empty_backend.merge_edge(make_edge("A", "R", "satisfies"))
        types = empty_backend.get_reachable_node_types("R")
        assert "Architecture_Block" in types

    def test_cam001_has_multiple_types(self, loaded_backend):
        types = loaded_backend.get_reachable_node_types("CAM-001")
        assert "Architecture_Block" in types
        assert "Design_Spec" in types
        assert "Verification" in types


# ── detect_conflicts ──────────────────────────────────────────────────────────

class TestDetectConflicts:
    def test_no_conflict_single_impl(self, empty_backend):
        empty_backend.merge_node(make_node(id="A", type="Architecture_Block"))
        empty_backend.merge_node(make_node(id="D", type="Design_Spec"))
        empty_backend.merge_edge(make_edge("D", "A", "implements"))
        assert empty_backend.detect_conflicts() == []

    def test_conflict_two_impls(self, empty_backend):
        empty_backend.merge_node(make_node(id="A", type="Architecture_Block"))
        empty_backend.merge_node(make_node(id="D1", type="Design_Spec"))
        empty_backend.merge_node(make_node(id="D2", type="Design_Spec"))
        empty_backend.merge_edge(make_edge("D1", "A", "implements"))
        empty_backend.merge_edge(make_edge("D2", "A", "implements"))
        conflicts = empty_backend.detect_conflicts()
        assert len(conflicts) == 1
        assert "A" in conflicts[0].affected_node_ids
        assert "D1" in conflicts[0].affected_node_ids
        assert "D2" in conflicts[0].affected_node_ids

    def test_loaded_backend_has_one_conflict(self, loaded_backend):
        conflicts = loaded_backend.detect_conflicts()
        assert len(conflicts) == 1
        ids = conflicts[0].affected_node_ids
        assert "CAM-010" in ids
        assert "CAM-020" in ids
        assert "CAM-021" in ids

    def test_conflict_severity_is_high(self, empty_backend):
        empty_backend.merge_node(make_node(id="A", type="Architecture_Block"))
        for i in range(2):
            empty_backend.merge_node(make_node(id=f"D{i}", type="Design_Spec"))
            empty_backend.merge_edge(make_edge(f"D{i}", "A", "implements"))
        assert empty_backend.detect_conflicts()[0].severity == "high"


# ── get_neighbors ─────────────────────────────────────────────────────────────

class TestGetNeighbors:
    def test_no_neighbors(self, empty_backend):
        empty_backend.merge_node(make_node(id="A"))
        assert empty_backend.get_neighbors("A") == []

    def test_successor_and_predecessor(self, empty_backend):
        empty_backend.merge_node(make_node(id="A"))
        empty_backend.merge_node(make_node(id="B"))
        empty_backend.merge_node(make_node(id="C"))
        empty_backend.merge_edge(make_edge("A", "B", "satisfies"))
        empty_backend.merge_edge(make_edge("C", "A", "implements"))
        neighbors = empty_backend.get_neighbors("A")
        assert "B" in neighbors
        assert "C" in neighbors

    def test_cam010_neighbors(self, loaded_backend):
        neighbors = sorted(loaded_backend.get_neighbors("CAM-010"))
        assert "CAM-001" in neighbors
        assert "CAM-020" in neighbors
        assert "CAM-021" in neighbors


# ── clear ─────────────────────────────────────────────────────────────────────

class TestClear:
    def test_clear_empties_graph(self, empty_backend):
        empty_backend.merge_node(make_node(id="A"))
        empty_backend.merge_node(make_node(id="B"))
        empty_backend.merge_edge(make_edge("A", "B", "satisfies"))
        empty_backend.clear()
        assert empty_backend.node_count() == 0
        assert empty_backend.edge_count() == 0
