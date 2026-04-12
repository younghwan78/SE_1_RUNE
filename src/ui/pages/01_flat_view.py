"""Page 1: Flat View — Before (JIRA-like list)."""
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

# --------------------------------------------------------------------------- load
adapter = DummyAdapter()
tickets = adapter.fetch_all_tickets()

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
    selected_types = st.multiselect("Type 필터", all_types, default=all_types)

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
    rows.append({
        "ID": t.id,
        "Type": t.type,
        "Summary": t.summary,
        "Status": t.status,
        "Sprint": t.sprint,
        "Priority": t.priority,
        "Linked IDs": ", ".join(t.linked_issue_ids) if t.linked_issue_ids else "—",
        "Labels": ", ".join(t.labels[:3]),
    })

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
    bg = type_colors.get(row["Type"], "#18181b")
    # Keep text white so it's always readable against dark bg
    return [f"background-color: {bg}; color: #e8e8e8"] * len(row)


def color_type_cell(val):
    c = type_text_colors.get(val, "#e8e8e8")
    return f"color: {c}; font-weight: 600"


st.dataframe(
    df.style
      .apply(highlight_row, axis=1)
      .map(color_type_cell, subset=["Type"]),
    use_container_width=True,
    height=520,
)

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
