"""Page 1: Flat View — Before (JIRA-like list) + AI 재분류 결과."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pandas as pd
import streamlit as st

from src.datasource.dummy_adapter import DummyAdapter
from src.ui.components.styles import inject_global_css

st.set_page_config(page_title="Flat View (Before)", page_icon="📋", layout="wide")
inject_global_css()

st.title("📋 Flat View — Before AI")
st.caption("기존 JIRA 방식 재현: 18개 티켓이 flat list로 나열됩니다.")

if has_ai_results:
    reclassified = sum(
        1 for v in ai_nodes.values()
        if v["ai_type"] != v["original_jira_type"]
    )
    st.success(
        f"✅ AI 분류 결과 로드됨 — {len(ai_nodes)}개 노드 분석 완료 "
        f"({'🔄 ' + str(reclassified) + '개 재분류' if reclassified else '모든 타입 일치'}). "
        f"**AI Type** 컬럼에서 변경 사항을 확인하세요.",
        icon="🤖",
    )
else:
    st.info(
        "⚙️ AI 분류 결과 없음 — **Agent Run** 페이지에서 파이프라인을 실행하면 "
        "JIRA 타입이 맞는지 AI가 검증하고 이 뷰에 결과가 표시됩니다.",
        icon="💡",
    )

# --------------------------------------------------------------------------- load
adapter = DummyAdapter()
tickets = adapter.fetch_all_tickets()

# AI 분류 결과 로드 (파이프라인 실행 후에만 존재)
@st.cache_resource(show_spinner=False)
def _load_ai_nodes() -> dict[str, dict]:
    """그래프 백엔드에서 AI 분류된 노드 로드.
    반환: {ticket_id: {"ai_type": str, "original_jira_type": str, "ai_classified": bool}}
    """
    try:
        from src.graph.factory import get_backend
        backend = get_backend(persist=True)  # 저장된 그래프 로드
        sg = backend.query_full_graph()
        result = {}
        for node in sg.nodes:
            if node.ai_classified:  # AI가 분류한 노드만
                result[node.id] = {
                    "ai_type": node.type,
                    "original_jira_type": node.original_jira_type,
                    "ai_classified": node.ai_classified,
                }
        return result
    except Exception:
        return {}

ai_nodes = _load_ai_nodes()
has_ai_results = len(ai_nodes) > 0

# --------------------------------------------------------------------------- pain point
st.error(
    "**⚠️ 기존 방식의 한계**: 아래 목록에서 "
    "\"CAM-001 (4K 레이턴시 요구사항)에 대한 검증이 완료되었나요?\"를 확인하려면 "
    "linked_issue_ids를 수작업으로 추적해야 합니다. "
    "CAM-022 DVFS가 레이턴시에 영향을 주는지는 이 목록만으로는 절대 알 수 없습니다.",
    icon="🚨",
)

# --------------------------------------------------------------------------- filters
st.divider()
col1, col2, col3 = st.columns(3)

with col1:
    all_types = sorted({t.type for t in tickets})
    selected_types = st.multiselect("JIRA Type 필터", all_types, default=all_types)

with col2:
    all_sprints = sorted({t.sprint for t in tickets if t.sprint})
    selected_sprints = st.multiselect("Sprint 필터", all_sprints, default=all_sprints)

with col3:
    status_filter = st.multiselect(
        "Status 필터",
        ["Open", "In Review", "In Progress", "Approved", "Planned"],
        default=["Open", "In Review", "In Progress", "Approved", "Planned"],
    )

# --------------------------------------------------------------------------- table
filtered = [
    t for t in tickets
    if t.type in selected_types
    and t.sprint in selected_sprints
    and t.status in status_filter
]

rows = []
for t in filtered:
    ai_info = ai_nodes.get(t.id, {})
    ai_type = ai_info.get("ai_type", "")
    changed = ai_type and ai_type != t.type
    row: dict = {
        "ID": t.id,
        "JIRA Type": t.type,
        "Summary": t.summary,
        "Status": t.status,
        "Sprint": t.sprint,
        "Priority": t.priority,
        "Linked IDs": ", ".join(t.linked_issue_ids) if t.linked_issue_ids else "—",
        "Labels": ", ".join(t.labels[:3]),
    }
    if has_ai_results:
        row["AI Type"] = (f"🔄 {ai_type}" if changed else ai_type) if ai_type else "—"
    rows.append(row)

df = pd.DataFrame(rows)

# Row tint — derived from NODE_COLORS at ~15% opacity over BG2
type_colors = {
    "Requirement":       "#18253a",   # steel blue tint
    "Architecture_Block":"#20203e",   # indigo tint
    "Design_Spec":       "#182a22",   # sage green tint
    "Verification":      "#2a2018",   # sienna tint
    "Issue":             "#2a1818",   # rose-red tint
}

type_text_colors = {
    "Requirement":       "#8aaed4",   # lighter steel blue
    "Architecture_Block":"#9e93e0",   # lighter indigo
    "Design_Spec":       "#7aaf90",   # lighter sage
    "Verification":      "#b89870",   # lighter sienna
    "Issue":             "#b87878",   # lighter rose
}


def highlight_row(row):
    # AI 재분류된 경우 행 배경색을 AI Type 기준으로 변경
    type_col = "JIRA Type"
    ai_col   = "AI Type" if "AI Type" in row.index else None
    ai_val   = str(row.get(ai_col, "")).replace("🔄 ", "") if ai_col else ""
    base_type = ai_val if ai_val and ai_val != "—" else row.get(type_col, "")
    bg = type_colors.get(base_type, "#18181b")
    return [f"background-color: {bg}; color: #e8e8e8"] * len(row)


def color_type_cell(val: str) -> str:
    clean = val.replace("🔄 ", "")
    c = type_text_colors.get(clean, "#e8e8e8")
    weight = "700" if val.startswith("🔄") else "600"
    return f"color: {c}; font-weight: {weight}"


style = df.style.apply(highlight_row, axis=1)
type_cols = ["JIRA Type"]
if "AI Type" in df.columns:
    type_cols.append("AI Type")
style = style.map(color_type_cell, subset=type_cols)

st.dataframe(style, use_container_width=True, height=520)

st.caption(f"총 {len(filtered)}개 티켓 표시 중 (전체 {len(tickets)}개)")

# --------------------------------------------------------------------------- manual challenge
st.divider()
st.markdown("### 🧩 직접 해보세요 — Manual Traceability Challenge")

with st.expander("Q1: CAM-001 요구사항이 검증되었나요?", expanded=False):
    st.markdown(
        """
        **수동 답변 방법**:
        1. CAM-001의 `Linked IDs`를 확인 → 비어 있음
        2. 전체 목록에서 `Verification` 타입 티켓 검색
        3. 각 Verification 티켓의 `Linked IDs`에 CAM-001이 있는지 확인
        4. CAM-030이 CAM-001을 참조 → **부분적으로 검증됨**
        5. But: CAM-010 (ISP 아키텍처)에 대한 직접 검증은? → **없음** (숨겨진 갭)

        **소요 시간**: 약 3-5분 / 엔지니어 1명
        """
    )

with st.expander("Q2: DVFS 구현이 레이턴시 요구사항에 위험을 주나요?", expanded=False):
    st.markdown(
        """
        **수동 답변 방법**:
        1. CAM-022 (DVFS) 상세 설명을 읽음
        2. "12-18ms 레이턴시 스파이크" 언급 발견
        3. CAM-001 (100ms 예산) 확인
        4. 수동으로 연결고리 판단 필요
        5. CAM-022의 `Linked IDs`에 CAM-001 없음 → **연결고리 누락**

        **문제**: 이 위험은 두 티켓의 설명을 모두 읽고 도메인 지식으로 연결해야만 발견 가능.
        **JIRA 검색으로는 자동 탐지 불가**.
        """
    )

with st.expander("Q3: 전체 요구사항 커버리지는 몇 %인가요?", expanded=False):
    st.markdown(
        """
        이 질문에 답하려면:
        - 모든 Requirement 티켓 (4개) 식별
        - 각각에 대해 Arch → Design → Verif 체인 수동 구성
        - 체인이 완성된 Requirement 개수 / 전체 Requirement 수

        **예상 소요 시간**: 30분 ~ 1시간
        **→ Metrics Dashboard에서 자동 계산된 결과를 확인하세요.**
        """
    )
