"""LangGraph 조건부 엣지 — 배치 완료 여부 라우팅."""
from src.models.graph_state import AgentState


def batch_complete_check(state: AgentState) -> str:
    """현재 배치가 마지막이면 'finalize', 아니면 'next_batch'를 반환."""
    next_start = state["batch_index"] + state["batch_size"]
    if next_start >= len(state["tickets"]):
        return "finalize"
    return "next_batch"


def advance_batch_index(state: AgentState) -> AgentState:
    """배치 인덱스를 다음 배치로 이동 (next_batch 전이 시 호출)."""
    return {
        **state,
        "batch_index": state["batch_index"] + state["batch_size"],
    }
