"""MetricsEngine 단위 테스트."""
import pytest

from src.graph.networkx_backend import NetworkXBackend
from src.metrics.traceability import MetricsEngine, TraceabilityReport
from tests.conftest import make_edge, make_node


@pytest.fixture
def engine_from_loaded(loaded_backend) -> MetricsEngine:
    return MetricsEngine(loaded_backend)


# ── baseline (dummy data) ─────────────────────────────────────────────────────

class TestBaselineMetrics:
    def test_total_nodes(self, engine_from_loaded):
        r = engine_from_loaded.compute_all()
        assert r.total_nodes == 18

    def test_total_edges(self, engine_from_loaded):
        r = engine_from_loaded.compute_all()
        assert r.total_edges == 20

    def test_inferred_edges(self, engine_from_loaded):
        r = engine_from_loaded.compute_all()
        assert r.inferred_edges == 4

    def test_coverage_score(self, engine_from_loaded):
        r = engine_from_loaded.compute_all()
        assert r.coverage_score == 25.0

    def test_orphan_rate(self, engine_from_loaded):
        r = engine_from_loaded.compute_all()
        assert abs(r.orphan_rate - 27.8) < 0.5

    def test_orphan_count(self, engine_from_loaded):
        r = engine_from_loaded.compute_all()
        assert r.orphan_nodes == 5

    def test_verification_coverage(self, engine_from_loaded):
        r = engine_from_loaded.compute_all()
        assert abs(r.verification_coverage - 66.7) < 0.5

    def test_gap_count(self, engine_from_loaded):
        r = engine_from_loaded.compute_all()
        assert len(r.gaps) == 9

    def test_conflict_count(self, engine_from_loaded):
        r = engine_from_loaded.compute_all()
        assert r.conflict_count == 1

    def test_total_requirements(self, engine_from_loaded):
        r = engine_from_loaded.compute_all()
        assert r.total_requirements == 4


# ── 빈 그래프 엣지 케이스 ─────────────────────────────────────────────────────

class TestEmptyGraph:
    def test_empty_graph_no_crash(self, empty_backend):
        r = MetricsEngine(empty_backend).compute_all()
        assert r.total_nodes == 0
        assert r.total_edges == 0
        assert r.coverage_score == 0.0
        assert r.orphan_rate == 0.0

    def test_single_requirement_no_chain(self, empty_backend):
        empty_backend.merge_node(make_node(id="R", type="Requirement"))
        r = MetricsEngine(empty_backend).compute_all()
        assert r.total_requirements == 1
        assert r.coverage_score == 0.0  # 체인 없으면 0%
        assert r.orphan_nodes == 1


# ── 커버리지 계산 로직 ────────────────────────────────────────────────────────

class TestCoverageLogic:
    def _make_full_chain_backend(self) -> NetworkXBackend:
        """Req → Arch → Design → Verif 완전 체인."""
        b = NetworkXBackend(persist=False)
        b.merge_node(make_node(id="R", type="Requirement"))
        b.merge_node(make_node(id="A", type="Architecture_Block"))
        b.merge_node(make_node(id="D", type="Design_Spec"))
        b.merge_node(make_node(id="V", type="Verification"))
        b.merge_edge(make_edge("A", "R", "satisfies"))
        b.merge_edge(make_edge("D", "A", "implements"))
        b.merge_edge(make_edge("V", "A", "verifies"))
        return b

    def test_full_chain_100_percent(self):
        b = self._make_full_chain_backend()
        r = MetricsEngine(b).compute_all()
        assert r.coverage_score == 100.0

    def test_partial_chain_zero_percent(self, empty_backend):
        """Arch만 있고 Design/Verif 없으면 full chain 아님."""
        empty_backend.merge_node(make_node(id="R", type="Requirement"))
        empty_backend.merge_node(make_node(id="A", type="Architecture_Block"))
        empty_backend.merge_edge(make_edge("A", "R", "satisfies"))
        r = MetricsEngine(empty_backend).compute_all()
        assert r.coverage_score == 0.0  # Design/Verif 없으므로 full chain 불충족

    def test_two_reqs_one_full_50_percent(self):
        b = self._make_full_chain_backend()
        # 체인 없는 두 번째 Requirement 추가
        b.merge_node(make_node(id="R2", type="Requirement"))
        r = MetricsEngine(b).compute_all()
        assert r.coverage_score == 50.0

    def test_req_layer_matrix_keys(self):
        b = self._make_full_chain_backend()
        r = MetricsEngine(b).compute_all()
        assert "R" in r.req_layer_matrix
        layers = r.req_layer_matrix["R"]
        assert all(k in layers for k in ("Requirement", "Architecture_Block", "Design_Spec", "Verification"))


# ── 갭 탐지 ───────────────────────────────────────────────────────────────────

class TestGapDetection:
    def test_orphan_gap_detected(self, empty_backend):
        empty_backend.merge_node(make_node(id="X", type="Design_Spec"))
        r = MetricsEngine(empty_backend).compute_all()
        gap_ids = [g.gap_id for g in r.gaps]
        assert any("X" in gid for gid in gap_ids)

    def test_no_gap_when_all_connected(self):
        b = NetworkXBackend(persist=False)
        b.merge_node(make_node(id="R", type="Requirement"))
        b.merge_node(make_node(id="A", type="Architecture_Block"))
        b.merge_node(make_node(id="V", type="Verification"))
        b.merge_edge(make_edge("A", "R", "satisfies"))
        b.merge_edge(make_edge("V", "A", "verifies"))
        r = MetricsEngine(b).compute_all()
        # 모두 연결됐으므로 orphan 갭 없음
        orphan_gaps = [g for g in r.gaps if g.gap_type == "orphan_node"]
        assert len(orphan_gaps) == 0

    def test_missing_verification_gap(self, empty_backend):
        empty_backend.merge_node(make_node(id="A", type="Architecture_Block"))
        empty_backend.merge_node(make_node(id="R", type="Requirement"))
        empty_backend.merge_edge(make_edge("A", "R", "satisfies"))
        r = MetricsEngine(empty_backend).compute_all()
        mv_gaps = [g for g in r.gaps if g.gap_type == "missing_verification"]
        assert any("A" in g.affected_node_ids for g in mv_gaps)

    def test_conflict_gap_in_baseline(self, loaded_backend):
        r = MetricsEngine(loaded_backend).compute_all()
        conflict_gaps = [g for g in r.gaps if g.gap_type == "conflict"]
        assert len(conflict_gaps) == 1
