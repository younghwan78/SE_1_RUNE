"""공유 pytest fixtures."""
import uuid
from pathlib import Path

import pytest

from src.graph.networkx_backend import NetworkXBackend
from src.models.ontology import OntologyEdge, OntologyNode


# ── 기본 노드/엣지 팩토리 ──────────────────────────────────────────────────────

def make_node(
    id: str = "N-001",
    type: str = "Requirement",
    name: str = "test node",
    description: str = "test description",
    status: str = "Open",
    labels: list[str] | None = None,
    original_jira_type: str = "",
    ai_classified: bool = False,
) -> OntologyNode:
    return OntologyNode(
        id=id,
        type=type,
        name=name,
        description=description,
        status=status,
        labels=labels or [],
        original_jira_type=original_jira_type,
        ai_classified=ai_classified,
    )


def make_edge(
    source_id: str = "A",
    target_id: str = "B",
    relation: str = "satisfies",
    reasoning: str = "test reasoning",
    is_inferred: bool = False,
) -> OntologyEdge:
    return OntologyEdge(
        source_id=source_id,
        target_id=target_id,
        relation=relation,
        reasoning=reasoning,
        is_inferred=is_inferred,
    )


# ── 그래프 fixture ──────────────────────────────────────────────────────────

@pytest.fixture
def empty_backend() -> NetworkXBackend:
    """영속성 없는 빈 NetworkX 백엔드."""
    return NetworkXBackend(persist=False)


@pytest.fixture
def loaded_backend() -> NetworkXBackend:
    """dummy 데이터가 로드된 NetworkX 백엔드."""
    from src.graph.loader import load_dummy_graph
    b = NetworkXBackend(persist=False)
    load_dummy_graph(b)
    return b


# ── StagingStore fixture (임시 DB) ──────────────────────────────────────────

@pytest.fixture
def staging_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """임시 경로를 사용하는 StagingStore (테스트 간 격리)."""
    import src.staging.sqlite_store as store_module
    tmp_db = tmp_path / "test_staging.db"
    monkeypatch.setattr(store_module, "DB_PATH", tmp_db)
    from src.staging.sqlite_store import StagingStore
    return StagingStore()
