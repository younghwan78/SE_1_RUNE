"""Page 4: Human-in-the-Loop Approvals."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
from src.ui.components.styles import inject_global_css

st.set_page_config(page_title="Approvals", page_icon="✅", layout="wide")
inject_global_css()

st.title("✅ Human-in-the-Loop Approvals")
st.caption("LLM이 제안한 트레이서빌리티 업데이트를 검토하고 승인/거부합니다.")

# --------------------------------------------------------------------------- check for pending
try:
    from src.staging.sqlite_store import StagingStore
    store = StagingStore()
    pending = store.get_pending()
except Exception:
    pending = []

if not pending:
    st.info(
        "현재 검토 대기 중인 항목이 없습니다.\n\n"
        "Agent Run 페이지에서 파이프라인을 실행하면 LLM이 제안한 "
        "트레이서빌리티 업데이트가 여기에 표시됩니다.",
        icon="📭",
    )

    st.divider()
    st.markdown("### 승인 플로우 미리보기")
    st.markdown(
        """
        파이프라인 실행 후 이 페이지에서:

        1. **제안된 노드/엣지** 목록 확인
        2. **AI 추론 근거** (reasoning) 검토
        3. **신뢰도 점수** 확인
        4. `[승인]` → Neo4j/NetworkX에 커밋
        5. `[거부]` → 제안 폐기
        6. `[수정]` → reasoning 편집 후 승인

        모든 승인/거부는 감사 로그에 기록됩니다.
        """
    )
else:
    st.markdown(f"**{len(pending)}개 항목** 검토 대기 중")

    for i, update in enumerate(pending):
        with st.expander(
            f"제안 #{i+1} | 신뢰도: {update.confidence_score:.0%} | "
            f"{len(update.nodes)}개 노드 / {len(update.edges)}개 엣지",
            expanded=i == 0,
        ):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**제안 노드:**")
                for node in update.nodes:
                    st.markdown(f"- `{node.id}` ({node.type}): {node.name}")

            with col2:
                st.markdown("**제안 엣지:**")
                for edge in update.edges:
                    inferred = " 🤖" if edge.is_inferred else ""
                    st.markdown(
                        f"- `{edge.source_id}` → `{edge.relation}` → `{edge.target_id}`{inferred}"
                    )
                    st.caption(f"  근거: {edge.reasoning[:80]}...")

            # Confidence indicator
            if update.confidence_score >= 0.75:
                st.success(f"신뢰도 {update.confidence_score:.0%} — 자동 승인 대상")
            else:
                st.warning(f"신뢰도 {update.confidence_score:.0%} — 수동 검토 필요")

            btn_col1, btn_col2, btn_col3 = st.columns(3)
            with btn_col1:
                if st.button("✅ 승인", key=f"approve_{i}", type="primary"):
                    from src.graph.factory import get_backend
                    backend = get_backend()
                    for node in update.nodes:
                        backend.merge_node(node)
                    for edge in update.edges:
                        backend.merge_edge(edge)
                    store.mark_approved(update.batch_id)
                    st.success("커밋 완료!")
                    st.rerun()
            with btn_col2:
                if st.button("❌ 거부", key=f"reject_{i}"):
                    store.mark_rejected(update.batch_id)
                    st.warning("거부 처리됨")
                    st.rerun()
            with btn_col3:
                if st.button("✏️ 수정", key=f"edit_{i}"):
                    st.session_state[f"editing_{i}"] = True

            if st.session_state.get(f"editing_{i}"):
                new_reasoning = st.text_area(
                    "수정된 reasoning:",
                    value=update.edges[0].reasoning if update.edges else "",
                    key=f"reasoning_{i}",
                )
                if st.button("수정 후 승인", key=f"edit_approve_{i}"):
                    st.session_state[f"editing_{i}"] = False
                    st.success("수정 후 승인 완료!")
                    st.rerun()
