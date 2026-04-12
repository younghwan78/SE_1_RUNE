"""Page 5: Metrics Dashboard — Before/After KPI comparison."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pandas as pd
import streamlit as st

from src.datasource.dummy_adapter import DummyAdapter
from src.ui.components.styles import inject_global_css
from src.graph.factory import get_backend
from src.graph.loader import load_dummy_graph
from src.graph.networkx_backend import NetworkXBackend
from src.metrics.traceability import MetricsEngine
from src.models.ontology import OntologyEdge, OntologyNode, SubGraph

st.set_page_config(page_title="Metrics Dashboard", page_icon="📊", layout="wide")
inject_global_css()

st.title("📊 Metrics Dashboard")
st.caption("AI Knowledge Graph Before/After 트레이서빌리티 KPI 비교")


# --------------------------------------------------------------------------- compute
@st.cache_data(show_spinner="KPI 계산 중...")
def compute_metrics():
    # --- AFTER AI (full graph with inferred edges) ---
    after_backend = get_backend(persist=False)
    load_dummy_graph(after_backend)
    after_report = MetricsEngine(after_backend).compute_all()

    # --- BEFORE AI (only explicit ticket links, no inferred) ---
    before_backend = NetworkXBackend(persist=False)
    adapter = DummyAdapter()
    tickets = adapter.fetch_all_tickets()
    pre_edges = adapter.fetch_pre_computed_edges()

    for ticket in tickets:
        node = OntologyNode(
            id=ticket.id,
            type=ticket.type,  # type: ignore[arg-type]
            name=ticket.summary,
            description=ticket.description,
            status=ticket.status,
            labels=ticket.labels,
        )
        before_backend.merge_node(node)

    # Only explicit (non-inferred) edges
    for edge in pre_edges:
        if not edge.is_inferred:
            before_backend.merge_edge(edge)

    before_report = MetricsEngine(before_backend).compute_all()
    return before_report, after_report


before, after = compute_metrics()

# --------------------------------------------------------------------------- KPI cards
st.markdown("## Key Performance Indicators")

kpis = [
    ("추적 커버리지", f"{before.coverage_score:.0f}%", f"{after.coverage_score:.0f}%",
     after.coverage_score - before.coverage_score, "요구사항 전체 체인 (Req→Arch→Design→Verif) 완성률"),
    ("고아 노드 비율", f"{before.orphan_rate:.0f}%", f"{after.orphan_rate:.0f}%",
     -(after.orphan_rate - before.orphan_rate), "트레이서빌리티 링크가 없는 노드 비율"),
    ("체인 완성도", f"{before.avg_chain_depth:.1f}/4.0", f"{after.avg_chain_depth:.1f}/4.0",
     after.avg_chain_depth - before.avg_chain_depth, "요구사항당 평균 레이어 깊이"),
    ("충돌 탐지", f"{before.conflict_count}건", f"{after.conflict_count}건",
     after.conflict_count - before.conflict_count, "동일 타겟에 복수 구현이 충돌하는 케이스"),
    ("검증 커버리지", f"{before.verification_coverage:.0f}%", f"{after.verification_coverage:.0f}%",
     after.verification_coverage - before.verification_coverage, "아키텍처 블록 대비 검증 티켓 존재율"),
    ("AI 추론 엣지", "0개", f"{after.inferred_edges}개",
     float(after.inferred_edges), "AI가 새로 발견한 연결 관계 수"),
]

cols = st.columns(6)
for col, (label, before_val, after_val, delta, tooltip) in zip(cols, kpis):
    with col:
        delta_str = f"+{delta:.0f}" if delta > 0 else f"{delta:.0f}"
        delta_color = "normal" if delta >= 0 else "inverse"
        # For orphan rate: lower is better
        if "고아" in label:
            delta_color = "inverse" if delta < 0 else "normal"  # green if decreased
            delta_str = f"{-delta:.0f}pp ↓" if delta < 0 else f"+{delta:.0f}pp ↑"
        st.metric(
            label=label,
            value=after_val,
            delta=f"Before: {before_val}",
            help=tooltip,
        )

# --------------------------------------------------------------------------- comparison table
st.divider()
st.markdown("## Before / After 비교 테이블")

comparison_data = {
    "KPI": [k[0] for k in kpis],
    "Before AI (원본 링크만)": [k[1] for k in kpis],
    "After AI (추론 포함)": [k[2] for k in kpis],
    "개선 효과": [],
    "설명": [k[4] for k in kpis],
}

improvements = []
for label, before_val, after_val, delta, _ in kpis:
    if "고아" in label:
        improvements.append(f"{'↓' if delta < 0 else '→'} {abs(delta):.0f}pp {'감소' if delta < 0 else '변화없음'}")
    elif delta > 0:
        improvements.append(f"↑ +{delta:.1f}")
    elif delta == 0:
        improvements.append("→ 동일 (정직한 수치)")
    else:
        improvements.append(f"↓ {delta:.1f}")

comparison_data["개선 효과"] = improvements

df_compare = pd.DataFrame(comparison_data)
st.dataframe(df_compare, use_container_width=True, hide_index=True)

st.info(
    "💡 **검증 커버리지가 동일한 이유**: AI는 검증 티켓을 날조하지 않습니다. "
    "존재하지 않는 테스트 계획을 만드는 대신 **갭으로 플래그**합니다. "
    "이것이 오히려 신뢰성을 높입니다.",
    icon="🤖",
)

# --------------------------------------------------------------------------- layer heatmap
st.divider()
st.markdown("## 요구사항별 레이어 커버리지 (After AI)")
st.caption("각 요구사항이 Arch / Design / Verif 레이어까지 추적되는지 확인")

if after.req_layer_matrix:
    heatmap_rows = []
    for req_id, layers in after.req_layer_matrix.items():
        node = None
        from src.graph.factory import get_backend as _get_backend
        _b = _get_backend(persist=False)
        load_dummy_graph(_b)
        node = _b.get_node(req_id)
        name = node.name[:35] if node else req_id
        row = {"Requirement": f"{req_id}: {name}"}
        for layer, present in layers.items():
            if layer == "Requirement":
                continue
            row[layer.replace("_", " ")] = "✅" if present else "❌"
        heatmap_rows.append(row)

    df_heatmap = pd.DataFrame(heatmap_rows)
    st.dataframe(df_heatmap, use_container_width=True, hide_index=True)

# --------------------------------------------------------------------------- gap inventory
st.divider()
st.markdown("## 갭 인벤토리")
st.caption(f"AI가 발견한 총 {len(after.gaps)}개 갭 — 기존 방식으로는 발견 불가")

if after.gaps:
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_gaps = sorted(after.gaps, key=lambda g: severity_order.get(g.severity, 99))

    severity_colors = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
    }

    for gap in sorted_gaps:
        icon = severity_colors.get(gap.severity, "⚪")
        with st.expander(f"{icon} [{gap.severity.upper()}] {gap.gap_id} — {gap.description[:60]}...", expanded=False):
            st.markdown(f"**Gap ID**: `{gap.gap_id}`")
            st.markdown(f"**Type**: `{gap.gap_type}`")
            st.markdown(f"**Severity**: `{gap.severity}`")
            st.markdown(f"**Affected Nodes**: {', '.join(f'`{n}`' for n in gap.affected_node_ids)}")
            st.markdown(f"**Description**: {gap.description}")
            st.markdown(f"**Suggested Action**: {gap.suggested_action}")
else:
    st.success("갭이 발견되지 않았습니다.")

# --------------------------------------------------------------------------- export
st.divider()
if st.button("📥 갭 리포트 CSV 다운로드"):
    if after.gaps:
        df_gaps = pd.DataFrame([
            {
                "Gap ID": g.gap_id,
                "Type": g.gap_type,
                "Severity": g.severity,
                "Affected Nodes": ", ".join(g.affected_node_ids),
                "Description": g.description,
                "Suggested Action": g.suggested_action,
            }
            for g in after.gaps
        ])
        csv = df_gaps.to_csv(index=False)
        st.download_button(
            "Download CSV",
            data=csv,
            file_name="ulysses_gap_report.csv",
            mime="text/csv",
        )
