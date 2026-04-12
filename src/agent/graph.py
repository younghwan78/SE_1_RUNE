"""LangGraph StateGraph 조립 및 run_pipeline() 진입점."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Callable

from langgraph.graph import END, StateGraph

from src.agent import edges as edge_fns
from src.agent import nodes as node_fns
from src.graph.base import GraphBackend
from src.models.graph_state import AgentState
from src.models.jira_ticket import JiraTicket
from src.models.ontology import RunMetadata


def _build_graph() -> object:
    """StateGraph 컴파일."""
    g: StateGraph = StateGraph(AgentState)

    # 노드 등록
    g.add_node("extract_nodes",       node_fns.extract_ontology_nodes)
    g.add_node("infer_relationships",  node_fns.infer_relationships)
    g.add_node("detect_gaps",          node_fns.detect_gaps)
    g.add_node("stage_for_approval",   node_fns.stage_for_approval)
    g.add_node("commit_to_graph",      node_fns.commit_to_graph)
    g.add_node("advance_batch",        edge_fns.advance_batch_index)
    g.add_node("finalize_report",      node_fns.finalize_report)

    # 엣지 연결 (선형 파이프)
    g.set_entry_point("extract_nodes")
    g.add_edge("extract_nodes",      "infer_relationships")
    g.add_edge("infer_relationships", "detect_gaps")
    g.add_edge("detect_gaps",         "stage_for_approval")
    g.add_edge("stage_for_approval",  "commit_to_graph")

    # 배치 완료 여부 분기
    g.add_conditional_edges(
        "commit_to_graph",
        edge_fns.batch_complete_check,
        {
            "next_batch": "advance_batch",
            "finalize":   "finalize_report",
        },
    )

    # look-back: 다음 배치로 루프
    g.add_edge("advance_batch", "extract_nodes")
    g.add_edge("finalize_report", END)

    return g.compile()


def run_pipeline(
    tickets: list[JiraTicket],
    backend: GraphBackend,
    batch_size: int = 5,
    log_fn: Callable[[str], None] | None = None,
    progress_fn: Callable[[int], None] | None = None,
) -> dict:
    """파이프라인 실행 진입점 — 03_agent_run.py에서 호출.

    Args:
        tickets:     분석할 JiraTicket 리스트
        backend:     GraphBackend 인스턴스 (NetworkX or Neo4j)
        batch_size:  배치당 처리 티켓 수
        log_fn:      UI 로그 콜백 (msg: str) → None
        progress_fn: UI 진행률 콜백 (pct: int) → None

    Returns:
        dict with keys: nodes_created, edges_created, gaps_found, run_id
    """
    if not tickets:
        if log_fn:
            log_fn("⚠️ 티켓이 없습니다.")
        return {"nodes_created": 0, "edges_created": 0, "gaps_found": 0}

    # 컨텍스트 초기화
    node_fns.init_context(
        backend=backend,
        log_fn=log_fn or (lambda m: None),
        progress_fn=progress_fn or (lambda p: None),
    )

    run_id = uuid.uuid4().hex[:8]
    initial_state: AgentState = {
        "tickets":           tickets,
        "batch_index":       0,
        "batch_size":        batch_size,
        "proposed_updates":  [],
        "approved_updates":  [],
        "rejected_updates":  [],
        "discovered_gaps":   [],
        "errors":            [],
        "committed_nodes":   [],
        "run_metadata": RunMetadata(
            run_id=run_id,
            started_at=datetime.utcnow().isoformat(),
            total_tickets=len(tickets),
        ),
    }

    if log_fn:
        log_fn(f"🚀 파이프라인 시작 (run_id={run_id}, tickets={len(tickets)}, batch_size={batch_size})")

    graph = _build_graph()
    total_batches = (len(tickets) + batch_size - 1) // batch_size

    final_state: AgentState = graph.invoke(
        initial_state,
        config={"recursion_limit": total_batches * 10 + 20},
    )

    metadata = final_state["run_metadata"]
    return {
        "nodes_created": metadata.total_nodes_created,
        "edges_created": metadata.total_edges_created,
        "gaps_found":    metadata.total_gaps_found,
        "run_id":        metadata.run_id,
    }
