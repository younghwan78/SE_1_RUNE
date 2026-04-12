"""Req-Tracker AI — Streamlit entrypoint."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from src.ui.components.styles import inject_global_css

st.set_page_config(
    page_title="Req-Tracker AI — Ulysses POC",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_css()

# ------------------------------------------------------------------ sidebar nav
st.sidebar.title("🔭 Req-Tracker AI")
st.sidebar.caption("Ulysses Camera HAL — MBSE Traceability POC")
st.sidebar.divider()

# ------------------------------------------------------------------ home page
st.title("🔭 Req-Tracker AI")
st.subheader("MBSE Traceability Knowledge Graph — Ulysses Camera HAL POC")

col1, col2 = st.columns(2)
with col1:
    st.info(
        """
        **프로젝트**: Ulysses (SoC Camera HAL)

        **도메인**: Sony IMX789 센서 / 4K60 파이프라인 / HDR TME

        **데이터**: 18개 가상 JIRA 티켓 (Req / Arch / Design / Verif / Issue)
        """,
        icon="📌",
    )

with col2:
    st.warning(
        """
        **POC 핵심 질문**

        기존 JIRA flat list로는 _요구사항 → 설계 → 검증_ 추적이 불가능합니다.

        AI + Knowledge Graph는 **수동 작업 없이** 이 체인을 자동 구성하고
        **누락/충돌**을 즉시 발견할 수 있을까요?
        """,
        icon="❓",
    )

st.divider()

# ------------------------------------------------------------------ clickable demo steps
st.markdown("### 📖 데모 순서")

pages_dir = Path(__file__).parent / "pages"

steps = [
    ("📋", "Flat View",       "기존 JIRA 방식의 한계 확인",        pages_dir / "01_flat_view.py"),
    ("🕸️", "Graph View",      "AI 구성 Knowledge Graph 시각화",    pages_dir / "02_graph_view.py"),
    ("⚙️", "Agent Run",       "LLM 파이프라인 실행 (Claude API)",  pages_dir / "03_agent_run.py"),
    ("✅", "Approvals",        "Human-in-the-Loop 승인",            pages_dir / "04_approvals.py"),
    ("📊", "Metrics",          "Before/After KPI 비교",             pages_dir / "05_metrics.py"),
]

cols = st.columns(5)
for col, (icon, title, desc, page_path) in zip(cols, steps):
    with col:
        st.markdown(
            f"""
            <div style="
                border: 1px solid #2e2e4a;
                border-radius: 8px;
                padding: 14px 12px;
                background: #1c1c2e;
                text-align: center;
                height: 100px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                gap: 4px;
            ">
                <div style="font-size: 22px;">{icon}</div>
                <div style="font-weight: 600; color: #dddaf0; font-size: 13px;">{title}</div>
                <div style="color: #8e8aaa; font-size: 11px;">{desc}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.page_link(str(page_path), label=f"→ {title} 열기", use_container_width=True)

st.divider()

# ------------------------------------------------------------------ quick stats
try:
    from src.graph.factory import get_backend
    from src.graph.loader import load_dummy_graph
    from src.metrics.traceability import MetricsEngine

    @st.cache_data(show_spinner=False)
    def _quick_stats():
        b = get_backend(persist=False)
        load_dummy_graph(b)
        r = MetricsEngine(b).compute_all()
        return r.total_nodes, r.total_edges, len(r.gaps), r.coverage_score

    nodes, edges, gaps, coverage = _quick_stats()
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Graph Nodes",      nodes)
    mc2.metric("Graph Edges",      edges)
    mc3.metric("Gaps Detected",    gaps)
    mc4.metric("Req Coverage",     f"{coverage:.0f}%")
except Exception:
    pass
