"""DummyAdapter 단위 테스트."""
import pytest

from src.datasource.dummy_adapter import DummyAdapter
from src.models.ontology import OntologyEdge


@pytest.fixture
def adapter() -> DummyAdapter:
    return DummyAdapter()


class TestDummyAdapterTickets:
    def test_fetch_all_returns_18(self, adapter):
        tickets = adapter.fetch_all_tickets()
        assert len(tickets) == 18

    def test_all_five_types_present(self, adapter):
        types = {t.type for t in adapter.fetch_all_tickets()}
        assert types == {"Requirement", "Architecture_Block", "Design_Spec", "Verification", "Issue"}

    def test_cam001_is_requirement(self, adapter):
        t = adapter.fetch_ticket("CAM-001")
        assert t.id == "CAM-001"
        assert t.type == "Requirement"

    def test_cam010_is_architecture(self, adapter):
        t = adapter.fetch_ticket("CAM-010")
        assert t.type == "Architecture_Block"

    def test_cam040_is_issue(self, adapter):
        t = adapter.fetch_ticket("CAM-040")
        assert t.type == "Issue"

    def test_cam030_is_verification(self, adapter):
        t = adapter.fetch_ticket("CAM-030")
        assert t.type == "Verification"

    def test_all_tickets_have_summary(self, adapter):
        for t in adapter.fetch_all_tickets():
            assert t.summary, f"{t.id} has empty summary"

    def test_all_tickets_have_id(self, adapter):
        ids = [t.id for t in adapter.fetch_all_tickets()]
        assert len(ids) == len(set(ids)), "Duplicate ticket IDs found"

    def test_fetch_unknown_raises(self, adapter):
        with pytest.raises(KeyError):
            adapter.fetch_ticket("NONEXISTENT-999")

    def test_sprints_are_strings(self, adapter):
        for t in adapter.fetch_all_tickets():
            assert isinstance(t.sprint, str)

    def test_labels_are_lists(self, adapter):
        for t in adapter.fetch_all_tickets():
            assert isinstance(t.labels, list)


class TestDummyAdapterEdges:
    def test_fetch_edges_returns_20(self, adapter):
        edges = adapter.fetch_pre_computed_edges()
        assert len(edges) == 20

    def test_edges_are_ontology_edge_type(self, adapter):
        for e in adapter.fetch_pre_computed_edges():
            assert isinstance(e, OntologyEdge)

    def test_inferred_edges_count(self, adapter):
        inferred = [e for e in adapter.fetch_pre_computed_edges() if e.is_inferred]
        assert len(inferred) == 4

    def test_explicit_edges_count(self, adapter):
        explicit = [e for e in adapter.fetch_pre_computed_edges() if not e.is_inferred]
        assert len(explicit) == 16

    def test_all_edges_have_reasoning(self, adapter):
        for e in adapter.fetch_pre_computed_edges():
            assert e.reasoning, f"Edge {e.source_id}→{e.target_id} has empty reasoning"

    def test_inferred_edges_tagged(self, adapter):
        for e in adapter.fetch_pre_computed_edges():
            if e.is_inferred:
                assert e.reasoning.startswith("[INFERRED]"), (
                    f"Inferred edge {e.source_id}→{e.target_id} missing [INFERRED] tag"
                )

    def test_all_relations_valid(self, adapter):
        valid = {"satisfies", "implements", "verifies", "affects", "blocks"}
        for e in adapter.fetch_pre_computed_edges():
            assert e.relation in valid, f"Invalid relation: {e.relation}"

    def test_g02_gap_edge_exists(self, adapter):
        """G-02: CAM-022 DVFS → CAM-001 latency affects 엣지 (핵심 데모 갭)."""
        edges = adapter.fetch_pre_computed_edges()
        dvfs_edges = [e for e in edges if e.source_id == "CAM-022" and e.target_id == "CAM-001"]
        assert len(dvfs_edges) == 1
        assert dvfs_edges[0].relation == "affects"
        assert dvfs_edges[0].is_inferred is True
