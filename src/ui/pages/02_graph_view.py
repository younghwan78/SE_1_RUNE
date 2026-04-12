"""Page 2: Graph View — After AI (interactive Knowledge Graph)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import streamlit.components.v1 as components

from src.graph.factory import get_backend
from src.graph.loader import load_dummy_graph
from src.models.ontology import OntologyNode, SubGraph
from src.ui.components.graph_renderer import NODE_COLORS, NODE_SHAPES, build_pyvis_html
from src.ui.components.styles import inject_global_css

st.set_page_config(page_title="Graph View", page_icon="🕸️", layout="wide")
inject_global_css()

# --------------------------------------------------------------------------- minimal top header
st.markdown(
    "<h2 style='margin-bottom:2px;'>🕸️ Knowledge Graph View</h2>"
    "<p style='color:#888;margin-top:0;font-size:13px;'>Ulysses Camera HAL — MBSE Traceability (AI-enhanced)</p>",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- load graph
@st.cache_resource(show_spinner="그래프 로딩 중...")
def get_graph_backend():
    backend = get_backend(persist=False)
    load_dummy_graph(backend)
    return backend


backend = get_graph_backend()
subgraph = backend.query_full_graph()
orphan_ids = {n.id for n in backend.query_orphan_nodes()}

# --------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("## Knowledge Graph Controls")

    st.markdown("**Search Components:**")
    search_term = st.text_input("", placeholder="Search nodes… e.g. latency, CAM-001")

    st.markdown("**Filter by Ontology:**")
    all_types = ["Requirement", "Architecture_Block", "Design_Spec", "Verification", "Issue"]
    selected_types: set[str] = set()
    for t in all_types:
        color = NODE_COLORS.get(t, "#888")
        if st.checkbox(
            t.replace("_", " "),
            value=True,
            key=f"type_{t}",
        ):
            selected_types.add(t)

    st.divider()
    highlight_orphans = st.toggle("Highlight Orphans", value=True, help="고아 노드를 빨간 테두리로 표시")
    show_inferred_only = st.toggle("Inferred Edges Only", value=False, help="AI가 새로 발견한 엣지만 표시")

    st.divider()
    if st.button("🔄 Reload Graph", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()

    st.divider()

    # ── Node Legend ──────────────────────────────────────────
    st.markdown(
        "<div style='font-size:11px;font-weight:600;color:#8e8aaa;"
        "letter-spacing:0.08em;text-transform:uppercase;margin-bottom:6px;'>"
        "Node Types</div>",
        unsafe_allow_html=True,
    )

    NODE_META = {
        "Requirement":        ("◆", "diamond",  "고객/시스템 요구사항"),
        "Architecture_Block": ("■", "square",   "아키텍처 설계 결정"),
        "Design_Spec":        ("●", "circle",   "SW/HW 구현 명세"),
        "Verification":       ("▲", "triangle", "테스트 / 검증 계획"),
        "Issue":              ("★", "star",     "버그 / 리스크 / 이슈"),
    }

    for t, (icon, shape_name, desc) in NODE_META.items():
        color = NODE_COLORS.get(t, "#888")
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:8px;"
            f"padding:5px 6px;border-radius:5px;margin-bottom:2px;"
            f"background:rgba(255,255,255,0.03);'>"
            f"  <span style='color:{color};font-size:15px;width:18px;text-align:center;flex-shrink:0;'>{icon}</span>"
            f"  <div style='flex:1;'>"
            f"    <div style='color:{color};font-size:12px;font-weight:600;'>{t.replace('_',' ')}</div>"
            f"    <div style='color:#6a667a;font-size:10px;'>{desc}</div>"
            f"  </div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:6px;'/>", unsafe_allow_html=True)

    # ── Edge Legend ──────────────────────────────────────────
    from src.ui.components.graph_renderer import RELATION_COLORS
    st.markdown(
        "<div style='font-size:11px;font-weight:600;color:#8e8aaa;"
        "letter-spacing:0.08em;text-transform:uppercase;margin:8px 0 6px;'>"
        "Edge Relations</div>",
        unsafe_allow_html=True,
    )

    EDGE_META = {
        "satisfies":  "아키텍처가 요구사항을 만족",
        "implements": "설계가 아키텍처를 구현",
        "verifies":   "검증이 노드를 테스트",
        "affects":    "이슈가 노드에 영향",
        "blocks":     "노드가 다른 노드를 차단",
    }

    for rel, desc in EDGE_META.items():
        color = RELATION_COLORS.get(rel, "#888")
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:7px;padding:3px 4px;'>"
            f"  <span style='display:inline-block;width:20px;height:2px;"
            f"background:{color};flex-shrink:0;border-radius:1px;'></span>"
            f"  <div style='flex:1;'>"
            f"    <span style='color:{color};font-size:11px;font-weight:600;'>{rel}</span>"
            f"    <span style='color:#6a667a;font-size:10px;margin-left:4px;'>{desc}</span>"
            f"  </div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<div style='margin-top:8px;padding:6px 8px;background:rgba(255,255,255,0.03);"
        "border-radius:5px;font-size:10px;color:#6a667a;line-height:1.7;'>"
        "<span style='color:#8e8aaa;'>━━</span> Explicit (JIRA 원본 링크)<br>"
        "<span style='color:#8e8aaa;'>╌╌</span> Inferred (AI 추론 링크)<br>"
        "<span style='color:#dd3333;'>■</span> Red border = Orphan node"
        "</div>",
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------------- filter
if search_term:
    search_lower = search_term.lower()
    matched_ids: set[str] = {
        n.id for n in subgraph.nodes
        if search_lower in n.id.lower()
        or search_lower in n.name.lower()
        or search_lower in n.description.lower()
    }
    # include neighbors
    from src.graph.networkx_backend import NetworkXBackend
    if isinstance(backend, NetworkXBackend):
        for nid in list(matched_ids):
            matched_ids.update(backend.get_neighbors(nid))
    filtered_nodes = [n for n in subgraph.nodes if n.id in matched_ids]
    filtered_node_ids = {n.id for n in filtered_nodes}
    filtered_edges = [
        e for e in subgraph.edges
        if e.source_id in filtered_node_ids and e.target_id in filtered_node_ids
    ]
else:
    filtered_nodes = [n for n in subgraph.nodes if n.type in selected_types]
    filtered_node_ids = {n.id for n in filtered_nodes}
    filtered_edges = [
        e for e in subgraph.edges
        if e.source_id in filtered_node_ids and e.target_id in filtered_node_ids
    ]

if show_inferred_only:
    filtered_edges = [e for e in filtered_edges if e.is_inferred]

display_graph = SubGraph(nodes=filtered_nodes, edges=filtered_edges)

# --------------------------------------------------------------------------- layout: graph left, info right
graph_col, info_col = st.columns([4, 1], gap="small")

with graph_col:
    # Stats bar
    n_inferred = sum(1 for e in filtered_edges if e.is_inferred)
    n_explicit = len(filtered_edges) - n_inferred
    st.markdown(
        f"<div style='font-size:12px;color:#888;margin-bottom:4px;'>"
        f"<b style='color:#ccc;'>{len(filtered_nodes)}</b> nodes &nbsp;·&nbsp; "
        f"<b style='color:#ccc;'>{n_explicit}</b> explicit edges &nbsp;·&nbsp; "
        f"<b style='color:#9e93e0;'>{n_inferred}</b> AI inferred &nbsp;·&nbsp; "
        f"<b style='color:#9e5555;'>{len(orphan_ids)}</b> orphans"
        f"</div>",
        unsafe_allow_html=True,
    )

    html_content = build_pyvis_html(
        display_graph,
        height=760,
        filter_types=selected_types,
        highlight_orphans=highlight_orphans,
        orphan_ids=orphan_ids,
    )
    components.html(html_content, height=780, scrolling=False)

with info_col:
    st.markdown("### Node Info")

    node_options = ["— select —"] + sorted([
        f"{n.id}" for n in subgraph.nodes
    ])
    selected_id = st.selectbox("", node_options, label_visibility="collapsed")

    if selected_id and selected_id != "— select —":
        node: OntologyNode | None = backend.get_node(selected_id)
        if node:
            color = NODE_COLORS.get(node.type, "#888")
            st.markdown(
                f"<div style='border-left:3px solid {color};padding:6px 10px;"
                f"background:#111;border-radius:0 6px 6px 0;margin-bottom:8px;'>"
                f"<b style='font-size:15px;color:#fff;'>{node.id}</b>"
                f"</div>",
                unsafe_allow_html=True,
            )

            out_edges = [e for e in subgraph.edges if e.source_id == node.id]
            in_edges  = [e for e in subgraph.edges if e.target_id == node.id]

            st.markdown(
                f"<small style='color:#888;'>Type:</small> "
                f"<b style='color:{color};'>{node.type.replace('_',' ')}</b><br>"
                f"<small style='color:#888;'>Status:</small> "
                f"<span style='color:#ddd;'>{node.status}</span><br>"
                f"<small style='color:#888;'>Links:</small> "
                f"<span style='color:#ddd;'>{len(in_edges)} in / {len(out_edges)} out</span>",
                unsafe_allow_html=True,
            )

            if node.labels:
                tags_html = " ".join(
                    f"<span style='background:{color}22;color:{color};font-size:10px;"
                    f"padding:1px 5px;border-radius:3px;border:1px solid {color}44;'>{lbl}</span>"
                    for lbl in node.labels[:4]
                )
                st.markdown(tags_html, unsafe_allow_html=True)

            st.divider()
            st.caption(
                node.description[:250] + "…" if len(node.description) > 250
                else node.description
            )

            if out_edges or in_edges:
                st.divider()
                st.markdown("**Connections:**")
                for e in (in_edges + out_edges)[:10]:
                    other = e.source_id if e.target_id == node.id else e.target_id
                    arrow = "←" if e.target_id == node.id else "→"
                    from src.ui.components.graph_renderer import RELATION_COLORS
                    rel_color = RELATION_COLORS.get(e.relation, "#888")
                    inferred = " 🤖" if e.is_inferred else ""
                    st.markdown(
                        f"<span style='color:{rel_color};font-size:11px;'>"
                        f"{arrow} {e.relation}</span>"
                        f"<span style='color:#ccc;font-size:11px;'> {other}{inferred}</span>",
                        unsafe_allow_html=True,
                    )

            if node.id in orphan_ids:
                st.warning("⚠️ No traceability links")
    else:
        st.markdown(
            "<div style='color:#555;font-size:12px;margin-top:16px;line-height:1.8;'>"
            "Select a node above<br>or hover over the<br>graph for details.<br><br>"
            "<span style='color:#9e93e0;'>●</span> hover = tooltip<br>"
            "<span style='color:#888;'>🤖</span> = AI inferred<br>"
            "<span style='color:#9e5555;'>■</span> border = orphan"
            "</div>",
            unsafe_allow_html=True,
        )
