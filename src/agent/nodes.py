"""LangGraph 노드 함수들 — MBSE 분류, 관계 추론, 갭 탐지."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Callable

from pydantic import BaseModel, Field

from src.agent.prompts import (
    CLASSIFIER_SYSTEM,
    RELATIONSHIP_SYSTEM,
    build_classification_prompt,
    build_gap_detection_prompt,
    build_relationship_prompt,
)
from src.graph.base import GraphBackend
from src.models.graph_state import AgentState
from src.models.ontology import (
    GapFinding,
    GapSeverity,
    GapType,
    NodeType,
    OntologyEdge,
    OntologyNode,
    ProposedUpdate,
)
from src.staging.sqlite_store import StagingStore

logger = logging.getLogger(__name__)

# ── 모듈 레벨 싱글톤 — run_pipeline()이 실행 전에 설정 ─────────────────────────
_backend: GraphBackend | None = None
_staging: StagingStore | None = None
_log_fn: Callable[[str], None] | None = None
_progress_fn: Callable[[int], None] | None = None


def init_context(
    backend: GraphBackend,
    log_fn: Callable[[str], None],
    progress_fn: Callable[[int], None],
) -> None:
    """파이프라인 실행 전 모듈 컨텍스트 초기화."""
    global _backend, _staging, _log_fn, _progress_fn
    _backend = backend
    _staging = StagingStore()
    _log_fn = log_fn
    _progress_fn = progress_fn


def _log(msg: str) -> None:
    logger.info(msg)
    if _log_fn:
        _log_fn(msg)


def _progress(pct: int) -> None:
    if _progress_fn:
        _progress_fn(pct)


# ── Instructor 응답 모델 ───────────────────────────────────────────────────────

class NodeClassification(BaseModel):
    id: str
    recommended_type: NodeType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    original_type_correct: bool


class BatchClassification(BaseModel):
    classifications: list[NodeClassification]


class InferredRelationship(BaseModel):
    source_id: str
    target_id: str
    relation: str = Field(description="satisfies|implements|verifies|affects|blocks")
    reasoning: str = Field(description="Must start with [INFERRED]")
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)


class RelationshipBatch(BaseModel):
    relationships: list[InferredRelationship]


class GapItem(BaseModel):
    gap_id: str
    gap_type: GapType
    severity: GapSeverity
    affected_node_ids: list[str]
    description: str
    suggested_action: str


class GapBatch(BaseModel):
    gaps: list[GapItem]


# ── Instructor 클라이언트 (lazy init) ─────────────────────────────────────────

_instructor_client = None


def _get_client():
    global _instructor_client
    if _instructor_client is None:
        import instructor
        from anthropic import Anthropic
        _instructor_client = instructor.from_anthropic(
            Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        )
    return _instructor_client


_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

# ── 노드 함수 ─────────────────────────────────────────────────────────────────


def extract_ontology_nodes(state: AgentState) -> AgentState:
    """배치 내 티켓을 AI로 분류하여 OntologyNode 리스트 생성."""
    tickets = state["tickets"]
    start = state["batch_index"]
    size  = state["batch_size"]
    batch = tickets[start : start + size]

    _log(f"🔍 [Batch {start//size + 1}] {len(batch)}개 티켓 분류 중...")

    # 티켓을 JSON 요약으로 변환
    ticket_summaries = [
        {
            "id": t.id,
            "jira_type": t.type,
            "summary": t.summary,
            "description": t.description[:400],
            "labels": t.labels,
        }
        for t in batch
    ]

    classified_nodes: list[OntologyNode] = []

    try:
        client = _get_client()
        result: BatchClassification = client.messages.create(
            model=_MODEL,
            max_tokens=2048,
            system=CLASSIFIER_SYSTEM,
            messages=[{
                "role": "user",
                "content": build_classification_prompt(
                    json.dumps(ticket_summaries, ensure_ascii=False, indent=2)
                ),
            }],
            response_model=BatchClassification,
            max_retries=2,
        )

        ticket_map = {t.id: t for t in batch}
        for clf in result.classifications:
            t = ticket_map.get(clf.id)
            if not t:
                continue
            node = OntologyNode(
                id=clf.id,
                type=clf.recommended_type,
                name=t.summary,
                description=t.description,
                status=t.status,
                labels=t.labels,
                original_jira_type=t.type,
                ai_classified=True,
            )
            classified_nodes.append(node)
            changed = "✏️ 재분류" if not clf.original_type_correct else "✅ 유지"
            _log(f"  {clf.id}: {t.type} → {clf.recommended_type} {changed} (신뢰도: {clf.confidence:.0%})")

    except Exception as e:
        _log(f"⚠️ AI 분류 실패, JIRA 타입 그대로 사용: {e}")
        # fallback: JIRA 원본 타입 사용
        for t in batch:
            node = OntologyNode(
                id=t.id,
                type=t.type,  # type: ignore[arg-type]
                name=t.summary,
                description=t.description,
                status=t.status,
                labels=t.labels,
                original_jira_type=t.type,
                ai_classified=False,
            )
            classified_nodes.append(node)

    # 현재 배치 노드를 ProposedUpdate에 임시 저장 (infer_relationships 노드에서 사용)
    # state 업데이트: proposed_updates에 현재 배치 노드 추가
    batch_id = f"batch-{start//size + 1:03d}-{uuid.uuid4().hex[:6]}"
    current_proposal = ProposedUpdate(
        nodes=classified_nodes,
        edges=[],
        confidence_score=0.0,
        batch_id=batch_id,
    )

    return {
        **state,
        "proposed_updates": state["proposed_updates"] + [current_proposal],
    }


def infer_relationships(state: AgentState) -> AgentState:
    """현재 배치 노드 + 기존 그래프(look-back)로 관계 추론."""
    if not state["proposed_updates"]:
        return state

    current_proposal = state["proposed_updates"][-1]
    batch_nodes = current_proposal.nodes
    context_nodes = state["committed_nodes"]  # 이전 배치 누적 노드

    _log(f"🔗 관계 추론 중... (현재 배치: {len(batch_nodes)}개, 컨텍스트: {len(context_nodes)}개)")

    # 이미 알려진 명시적 링크 수집 (JIRA linked_issue_ids 기반)
    tickets = state["tickets"]
    ticket_map = {t.id: t for t in tickets}
    existing_edges: list[dict] = []
    for node in batch_nodes:
        t = ticket_map.get(node.id)
        if t:
            for linked_id in t.linked_issue_ids:
                existing_edges.append({"source": node.id, "target": linked_id, "type": "explicit_link"})

    inferred_edges: list[OntologyEdge] = []

    # 컨텍스트가 있어야 의미 있는 추론 가능
    if not context_nodes and len(batch_nodes) < 2:
        _log("  컨텍스트 부족 — 관계 추론 건너뜀")
    else:
        try:
            client = _get_client()

            batch_summary = [
                {"id": n.id, "type": n.type, "name": n.name, "description": n.description[:300]}
                for n in batch_nodes
            ]
            context_summary = [
                {"id": n.id, "type": n.type, "name": n.name}
                for n in context_nodes[-30:]  # 최근 30개만 (토큰 절약)
            ]

            result: RelationshipBatch = client.messages.create(
                model=_MODEL,
                max_tokens=2048,
                system=RELATIONSHIP_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": build_relationship_prompt(
                        json.dumps(batch_summary, ensure_ascii=False, indent=2),
                        json.dumps(context_summary, ensure_ascii=False, indent=2),
                        json.dumps(existing_edges, ensure_ascii=False, indent=2),
                    ),
                }],
                response_model=RelationshipBatch,
                max_retries=2,
            )

            valid_relations = {"satisfies", "implements", "verifies", "affects", "blocks"}
            all_node_ids = {n.id for n in batch_nodes} | {n.id for n in context_nodes}

            for rel in result.relationships:
                if rel.source_id not in all_node_ids or rel.target_id not in all_node_ids:
                    continue  # 존재하지 않는 노드 참조 무시
                if rel.relation not in valid_relations:
                    continue
                reasoning = rel.reasoning
                if not reasoning.startswith("[INFERRED]"):
                    reasoning = "[INFERRED] " + reasoning
                edge = OntologyEdge(
                    source_id=rel.source_id,
                    target_id=rel.target_id,
                    relation=rel.relation,  # type: ignore[arg-type]
                    reasoning=reasoning,
                    is_inferred=True,
                )
                inferred_edges.append(edge)
                _log(f"  🤖 {rel.source_id} --{rel.relation}--> {rel.target_id}")

        except Exception as e:
            _log(f"⚠️ 관계 추론 실패: {e}")

    # 명시적 엣지도 추가 (JIRA linked_issue_ids)
    all_node_ids = {n.id for n in batch_nodes} | {n.id for n in context_nodes}
    explicit_edges: list[OntologyEdge] = []
    for node in batch_nodes:
        t = ticket_map.get(node.id)
        if not t:
            continue
        for linked_id in t.linked_issue_ids:
            if linked_id not in all_node_ids:
                continue
            # 관계 타입 추정 (명시 링크는 가장 일반적인 관계로)
            relation = _guess_relation(node, linked_id, {n.id: n for n in batch_nodes + context_nodes})
            edge = OntologyEdge(
                source_id=node.id,
                target_id=linked_id,
                relation=relation,
                reasoning=f"Explicit JIRA link: {node.id} → {linked_id}",
                is_inferred=False,
            )
            explicit_edges.append(edge)

    all_edges = explicit_edges + inferred_edges
    _log(f"  → 명시적 엣지: {len(explicit_edges)}개, 추론 엣지: {len(inferred_edges)}개")

    # 현재 proposal 업데이트
    updated_proposal = ProposedUpdate(
        nodes=current_proposal.nodes,
        edges=all_edges,
        confidence_score=_compute_confidence(current_proposal.nodes, inferred_edges),
        batch_id=current_proposal.batch_id,
    )

    updated_proposals = state["proposed_updates"][:-1] + [updated_proposal]
    return {**state, "proposed_updates": updated_proposals}


def detect_gaps(state: AgentState) -> AgentState:
    """전체 그래프 기준 갭 탐지 (프로그래매틱 + AI 보완)."""
    if not state["proposed_updates"]:
        return state

    # 현재까지 커밋된 노드 + 현재 배치 노드
    current_proposal = state["proposed_updates"][-1]
    all_nodes = state["committed_nodes"] + current_proposal.nodes

    # 전체 엣지 (커밋된 것 + 현재 배치)
    committed_edge_pairs: set[tuple[str, str, str]] = set()
    if _backend:
        try:
            sg = _backend.query_full_graph()
            for e in sg.edges:
                committed_edge_pairs.add((e.source_id, e.target_id, e.relation))
        except Exception:
            pass
    for e in current_proposal.edges:
        committed_edge_pairs.add((e.source_id, e.target_id, e.relation))

    gaps: list[GapFinding] = list(state["discovered_gaps"])

    node_map = {n.id: n for n in all_nodes}
    connected_ids: set[str] = set()
    for src, tgt, _ in committed_edge_pairs:
        connected_ids.add(src)
        connected_ids.add(tgt)

    # G-1: 고아 노드 (연결 없음)
    for node in current_proposal.nodes:
        if node.id not in connected_ids:
            gaps.append(GapFinding(
                gap_id=f"G-orphan-{node.id}",
                gap_type="orphan_node",
                severity="high",
                affected_node_ids=[node.id],
                description=f"{node.id} ({node.type})에 어떤 트레이서빌리티 링크도 없습니다.",
                suggested_action=f"{node.id}를 연결할 부모 Requirement 또는 Architecture_Block을 찾거나 생성하세요.",
            ))

    # G-2: Requirements에 Verification이 없는 경우
    req_nodes = [n for n in all_nodes if n.type == "Requirement"]
    verified_req_ids = {
        tgt for src, tgt, rel in committed_edge_pairs if rel == "verifies"
    }
    for req in req_nodes:
        if req.id not in verified_req_ids:
            gaps.append(GapFinding(
                gap_id=f"G-no-verif-{req.id}",
                gap_type="missing_verification",
                severity="high",
                affected_node_ids=[req.id],
                description=f"Requirement {req.id} ({req.name[:50]})에 대한 Verification 티켓이 없습니다.",
                suggested_action=f"{req.id}를 검증하는 Test/Benchmark 티켓을 생성하세요.",
            ))

    # G-3: Architecture_Block에 Implementation이 여러 개인 경우 (충돌)
    arch_implementors: dict[str, list[str]] = {}
    for src, tgt, rel in committed_edge_pairs:
        if rel == "implements":
            arch_implementors.setdefault(tgt, []).append(src)
    for arch_id, impl_ids in arch_implementors.items():
        if len(impl_ids) > 1:
            gaps.append(GapFinding(
                gap_id=f"G-conflict-{arch_id}",
                gap_type="conflict",
                severity="critical",
                affected_node_ids=[arch_id] + impl_ids,
                description=f"{arch_id}를 동시에 구현하는 설계가 {len(impl_ids)}개 존재합니다: {', '.join(impl_ids)}",
                suggested_action=f"어떤 구현이 채택될지 명확히 하고 나머지는 'Deprecated' 처리하세요.",
            ))

    # 중복 gap_id 제거
    seen_gap_ids: set[str] = set()
    deduped: list[GapFinding] = []
    for g in gaps:
        if g.gap_id not in seen_gap_ids:
            seen_gap_ids.add(g.gap_id)
            deduped.append(g)

    if deduped != list(state["discovered_gaps"]):
        new_count = len(deduped) - len(state["discovered_gaps"])
        if new_count > 0:
            _log(f"🔴 갭 {new_count}개 탐지 (누적: {len(deduped)}개)")

    return {**state, "discovered_gaps": deduped}


def stage_for_approval(state: AgentState) -> AgentState:
    """현재 배치 ProposedUpdate를 SQLite 스테이징 큐에 적재."""
    if not state["proposed_updates"] or not _staging:
        return state

    current_proposal = state["proposed_updates"][-1]
    _staging.enqueue(current_proposal)
    _log(
        f"📋 승인 큐 적재: {len(current_proposal.nodes)}개 노드, "
        f"{len(current_proposal.edges)}개 엣지 "
        f"(신뢰도: {current_proposal.confidence_score:.0%})"
    )
    return state


def commit_to_graph(state: AgentState) -> AgentState:
    """현재 배치를 그래프 백엔드에 커밋 (신뢰도 임계값 이상 자동 승인)."""
    if not state["proposed_updates"] or not _backend:
        return state

    current_proposal = state["proposed_updates"][-1]
    threshold = float(os.getenv("APPROVAL_THRESHOLD", "0.75"))

    if current_proposal.confidence_score >= threshold:
        _log(f"✅ 자동 승인 (신뢰도 {current_proposal.confidence_score:.0%} ≥ {threshold:.0%})")
        for node in current_proposal.nodes:
            _backend.merge_node(node)
        for edge in current_proposal.edges:
            _backend.merge_edge(edge)
        if _staging:
            _staging.mark_approved(current_proposal.batch_id)
        approved = state["approved_updates"] + [current_proposal]
    else:
        _log(f"⏳ 수동 검토 필요 (신뢰도 {current_proposal.confidence_score:.0%} < {threshold:.0%})")
        approved = state["approved_updates"]

    # look-back: 커밋된 노드 누적
    committed = state["committed_nodes"] + current_proposal.nodes

    return {
        **state,
        "approved_updates": approved,
        "committed_nodes": committed,
    }


def finalize_report(state: AgentState) -> AgentState:
    """최종 메트릭 계산 및 런 메타데이터 업데이트."""
    metadata = state["run_metadata"]
    total_nodes = sum(len(p.nodes) for p in state["approved_updates"])
    total_edges = sum(len(p.edges) for p in state["approved_updates"])
    total_gaps  = len(state["discovered_gaps"])

    metadata.finished_at = datetime.utcnow().isoformat()
    metadata.total_nodes_created = total_nodes
    metadata.total_edges_created = total_edges
    metadata.total_gaps_found = total_gaps

    _log(f"")
    _log(f"📊 파이프라인 완료 리포트")
    _log(f"  노드 생성:  {total_nodes}개")
    _log(f"  엣지 생성:  {total_edges}개 (명시 + AI 추론)")
    _log(f"  갭 탐지:    {total_gaps}개")
    _log(f"  소요 시간:  {metadata.started_at} → {metadata.finished_at}")

    return {**state, "run_metadata": metadata}


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _guess_relation(
    source_node: OntologyNode,
    target_id: str,
    node_map: dict[str, OntologyNode],
) -> str:
    """명시적 JIRA 링크의 관계 타입을 소스/타깃 타입으로 추정."""
    target = node_map.get(target_id)
    if not target:
        return "affects"  # 알 수 없는 타깃 → 일반적 관계

    src_t = source_node.type
    tgt_t = target.type

    if src_t in ("Architecture_Block", "Design_Spec") and tgt_t == "Requirement":
        return "satisfies"
    if src_t == "Design_Spec" and tgt_t == "Architecture_Block":
        return "implements"
    if src_t == "Verification":
        return "verifies"
    if src_t == "Issue":
        return "affects"
    return "affects"


def _compute_confidence(
    nodes: list[OntologyNode],
    inferred_edges: list[OntologyEdge],
) -> float:
    """배치 ProposedUpdate의 전체 신뢰도 점수 계산."""
    if not nodes:
        return 0.0
    # 노드가 AI 분류됐을 경우 높은 기본 신뢰도
    ai_ratio = sum(1 for n in nodes if n.ai_classified) / len(nodes)
    # 추론 엣지가 많을수록 신뢰도 소폭 증가
    edge_bonus = min(0.1, len(inferred_edges) * 0.02)
    return round(min(1.0, 0.70 + ai_ratio * 0.20 + edge_bonus), 3)
