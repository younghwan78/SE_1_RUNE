"""StagingStore 단위 테스트."""
import uuid

import pytest

from src.models.ontology import ProposedUpdate
from tests.conftest import make_edge, make_node


def _make_update(confidence: float = 0.85) -> ProposedUpdate:
    return ProposedUpdate(
        nodes=[make_node(id=f"N-{uuid.uuid4().hex[:6]}", type="Requirement")],
        edges=[make_edge()],
        confidence_score=confidence,
        batch_id=uuid.uuid4().hex,
    )


class TestStagingStoreEnqueue:
    def test_enqueue_increases_count(self, staging_store):
        assert staging_store.count_pending() == 0
        staging_store.enqueue(_make_update())
        assert staging_store.count_pending() == 1

    def test_enqueue_multiple(self, staging_store):
        for _ in range(3):
            staging_store.enqueue(_make_update())
        assert staging_store.count_pending() == 3

    def test_enqueue_idempotent_same_batch_id(self, staging_store):
        upd = _make_update()
        staging_store.enqueue(upd)
        staging_store.enqueue(upd)  # 동일 batch_id → INSERT OR REPLACE
        assert staging_store.count_pending() == 1

    def test_enqueued_item_retrievable(self, staging_store):
        upd = _make_update(confidence=0.92)
        staging_store.enqueue(upd)
        pending = staging_store.get_pending()
        assert len(pending) == 1
        assert pending[0].batch_id == upd.batch_id
        assert pending[0].confidence_score == 0.92


class TestStagingStoreApproval:
    def test_mark_approved_removes_from_pending(self, staging_store):
        upd = _make_update()
        staging_store.enqueue(upd)
        staging_store.mark_approved(upd.batch_id)
        assert staging_store.count_pending() == 0

    def test_mark_rejected_removes_from_pending(self, staging_store):
        upd = _make_update()
        staging_store.enqueue(upd)
        staging_store.mark_rejected(upd.batch_id)
        assert staging_store.count_pending() == 0

    def test_approve_one_of_two_leaves_one_pending(self, staging_store):
        upd1 = _make_update()
        upd2 = _make_update()
        staging_store.enqueue(upd1)
        staging_store.enqueue(upd2)
        staging_store.mark_approved(upd1.batch_id)
        assert staging_store.count_pending() == 1
        pending_ids = [p.batch_id for p in staging_store.get_pending()]
        assert upd2.batch_id in pending_ids
        assert upd1.batch_id not in pending_ids

    def test_get_pending_order_is_fifo(self, staging_store):
        """enqueue 순서대로 반환되는지 확인."""
        updates = [_make_update() for _ in range(4)]
        for u in updates:
            staging_store.enqueue(u)
        pending = staging_store.get_pending()
        assert [p.batch_id for p in pending] == [u.batch_id for u in updates]


class TestStagingStoreRoundtrip:
    def test_nodes_survive_json_roundtrip(self, staging_store):
        node = make_node(id="CAM-001", type="Requirement", labels=["latency", "camera"])
        upd = ProposedUpdate(nodes=[node], edges=[], confidence_score=0.8, batch_id=uuid.uuid4().hex)
        staging_store.enqueue(upd)
        restored = staging_store.get_pending()[0]
        assert restored.nodes[0].id == "CAM-001"
        assert restored.nodes[0].labels == ["latency", "camera"]

    def test_edges_survive_json_roundtrip(self, staging_store):
        edge = make_edge(source_id="CAM-010", target_id="CAM-001", relation="satisfies", is_inferred=True)
        upd = ProposedUpdate(nodes=[], edges=[edge], confidence_score=0.75, batch_id=uuid.uuid4().hex)
        staging_store.enqueue(upd)
        restored = staging_store.get_pending()[0]
        assert restored.edges[0].source_id == "CAM-010"
        assert restored.edges[0].is_inferred is True

    def test_empty_pending_returns_list(self, staging_store):
        assert staging_store.get_pending() == []


class TestStagingStoreIsolation:
    def test_two_stores_share_same_db(self, staging_store, tmp_path, monkeypatch):
        """같은 DB_PATH를 공유하는 두 인스턴스는 동일 데이터를 봐야 함."""
        import src.staging.sqlite_store as store_module
        from src.staging.sqlite_store import StagingStore

        upd = _make_update()
        staging_store.enqueue(upd)

        # 동일 경로를 가리키는 두 번째 인스턴스 생성
        store2 = StagingStore()
        assert store2.count_pending() == 1
