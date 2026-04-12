"""Page 3: Agent Run — LangGraph pipeline execution."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import os
import streamlit as st
from src.ui.components.styles import inject_global_css

st.set_page_config(page_title="Agent Run", page_icon="⚙️", layout="wide")
inject_global_css()

st.title("⚙️ Agent Run")
st.caption("LangGraph 파이프라인 실행 — Claude API로 트레이서빌리티 자동 추출")

# --------------------------------------------------------------------------- env check
anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
jira_mode = os.getenv("DATASOURCE_MODE", "dummy")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**환경 설정 상태**")
    if anthropic_key and anthropic_key != "sk-ant-...":
        st.success("✅ ANTHROPIC_API_KEY 설정됨")
    else:
        st.error("❌ ANTHROPIC_API_KEY 미설정 — `.env` 파일을 확인하세요")

    if jira_mode == "jira":
        jira_url = os.getenv("JIRA_URL", "")
        if jira_url:
            st.success(f"✅ JIRA 연결 설정: {jira_url}")
        else:
            st.warning("⚠️ DATASOURCE_MODE=jira 이지만 JIRA_URL 미설정")
    else:
        st.info("ℹ️ DATASOURCE_MODE=dummy (가상 데이터 사용)")

with col2:
    st.markdown("**파이프라인 구성**")
    batch_size = st.number_input("Batch Size", min_value=1, max_value=18, value=5)
    threshold = st.slider("Auto-Approve Threshold", 0.0, 1.0, 0.75, 0.05)
    st.caption(f"신뢰도 ≥ {threshold:.0%} → 자동 승인, 미만 → 수동 검토")

st.divider()

# --------------------------------------------------------------------------- run button
if st.button("🚀 파이프라인 실행", type="primary", disabled=not (anthropic_key and anthropic_key != "sk-ant-...")):
    st.info("파이프라인 실행 중... (실시간 로그)")
    log_area = st.empty()
    progress = st.progress(0)

    log_lines = []

    def log(msg: str) -> None:
        log_lines.append(msg)
        log_area.code("\n".join(log_lines[-20:]), language="bash")

    try:
        from src.datasource.factory import get_adapter
        from src.graph.factory import get_backend

        log("📡 데이터 소스 연결 중...")
        adapter = get_adapter()
        tickets = adapter.fetch_all_tickets()
        log(f"✅ {len(tickets)}개 티켓 로드 완료")
        progress.progress(10)

        log("🗄️ 그래프 백엔드 초기화 중...")
        backend = get_backend()
        log(f"✅ GraphBackend: {type(backend).__name__}")
        progress.progress(20)

        log(f"🧠 LangGraph 파이프라인 시작 (batch_size={batch_size})")

        from src.agent.graph import run_pipeline
        result = run_pipeline(tickets=tickets, backend=backend, batch_size=batch_size, log_fn=log, progress_fn=progress.progress)

        progress.progress(100)
        log(f"✅ 완료! 노드: {result.get('nodes_created', 0)}, 엣지: {result.get('edges_created', 0)}, 갭: {result.get('gaps_found', 0)}")
        st.success("파이프라인 실행 완료! Approvals 페이지에서 결과를 검토하세요.")

    except ImportError as e:
        log(f"❌ 모듈 로드 실패: {e}")
        st.error(f"에이전트 모듈이 아직 구현되지 않았습니다: {e}")
    except Exception as e:
        log(f"❌ 오류 발생: {e}")
        st.exception(e)

elif not anthropic_key or anthropic_key == "sk-ant-...":
    st.warning(
        "ANTHROPIC_API_KEY가 필요합니다. `.env` 파일에 키를 설정하고 앱을 재시작하세요.\n\n"
        "**Demo 모드**: Graph View와 Metrics Dashboard는 사전 계산된 데이터로 API 없이도 동작합니다."
    )

st.divider()
st.markdown("### 파이프라인 아키텍처")
st.code(
    """
START → fetch_tickets → extract_ontology_nodes → infer_relationships
     → detect_gaps → stage_for_approval → commit_to_graph
     → [batch_complete_check]
           ├─ "next_batch" ──> extract_ontology_nodes  (look-back 패턴)
           └─ "finalize"   ──> finalize_report → END
    """,
    language="text",
)
st.caption("look-back 패턴: 배치가 진행될수록 이전 노드 컨텍스트가 누적되어 교차 참조 추론 품질 향상")
