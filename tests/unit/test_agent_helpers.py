"""에이전트 헬퍼 함수 단위 테스트.

대상:
  - src.agent.nodes._guess_relation
  - src.agent.nodes._compute_confidence
  - src.agent.edges.batch_complete_check / advance_batch_index
  - src.datasource.jira_adapter._adf_to_text
"""
import pytest

from src.agent.edges import advance_batch_index, batch_complete_check
from src.agent.nodes import _compute_confidence, _guess_relation
from src.datasource.jira_adapter import _adf_to_text
from tests.conftest import make_edge, make_node


# ── _guess_relation ───────────────────────────────────────────────────────────

class TestGuessRelation:
    def _node_map(self, *nodes):
        return {n.id: n for n in nodes}

    def test_arch_to_req_returns_satisfies(self):
        src = make_node(id="A", type="Architecture_Block")
        tgt = make_node(id="R", type="Requirement")
        assert _guess_relation(src, "R", self._node_map(src, tgt)) == "satisfies"

    def test_design_to_req_returns_satisfies(self):
        src = make_node(id="D", type="Design_Spec")
        tgt = make_node(id="R", type="Requirement")
        assert _guess_relation(src, "R", self._node_map(src, tgt)) == "satisfies"

    def test_design_to_arch_returns_implements(self):
        src = make_node(id="D", type="Design_Spec")
        tgt = make_node(id="A", type="Architecture_Block")
        assert _guess_relation(src, "A", self._node_map(src, tgt)) == "implements"

    def test_verification_any_returns_verifies(self):
        src = make_node(id="V", type="Verification")
        tgt = make_node(id="A", type="Architecture_Block")
        assert _guess_relation(src, "A", self._node_map(src, tgt)) == "verifies"

    def test_issue_returns_affects(self):
        src = make_node(id="I", type="Issue")
        tgt = make_node(id="R", type="Requirement")
        assert _guess_relation(src, "R", self._node_map(src, tgt)) == "affects"

    def test_unknown_target_returns_affects(self):
        src = make_node(id="A", type="Architecture_Block")
        assert _guess_relation(src, "MISSING", {}) == "affects"

    def test_req_to_req_returns_affects(self):
        src = make_node(id="R1", type="Requirement")
        tgt = make_node(id="R2", type="Requirement")
        assert _guess_relation(src, "R2", self._node_map(src, tgt)) == "affects"


# ── _compute_confidence ───────────────────────────────────────────────────────

class TestComputeConfidence:
    def test_empty_nodes_returns_zero(self):
        assert _compute_confidence([], []) == 0.0

    def test_all_ai_classified_increases_score(self):
        nodes = [make_node(id=f"N{i}", ai_classified=True) for i in range(4)]
        score = _compute_confidence(nodes, [])
        assert score >= 0.90  # 0.70 base + 0.20 ai_ratio

    def test_no_ai_classified_base_score(self):
        nodes = [make_node(id=f"N{i}", ai_classified=False) for i in range(4)]
        score = _compute_confidence(nodes, [])
        assert score == pytest.approx(0.70, abs=0.01)

    def test_inferred_edges_add_bonus(self):
        nodes = [make_node(id="N1", ai_classified=False)]
        edges = [make_edge(is_inferred=True) for _ in range(3)]
        score = _compute_confidence(nodes, edges)
        assert score > 0.70

    def test_score_capped_at_1(self):
        nodes = [make_node(id=f"N{i}", ai_classified=True) for i in range(10)]
        edges = [make_edge(is_inferred=True) for _ in range(100)]
        score = _compute_confidence(nodes, edges)
        assert score <= 1.0

    def test_partial_ai_classified(self):
        nodes = [
            make_node(id="N1", ai_classified=True),
            make_node(id="N2", ai_classified=False),
        ]
        score = _compute_confidence(nodes, [])
        # ai_ratio = 0.5 → 0.70 + 0.10 = 0.80
        assert score == pytest.approx(0.80, abs=0.01)


# ── batch_complete_check / advance_batch_index ────────────────────────────────

def _make_state(tickets_n: int, batch_index: int, batch_size: int) -> dict:
    """최소 AgentState-like dict."""
    from src.models.jira_ticket import JiraTicket
    tickets = [
        JiraTicket(id=f"T-{i}", type="Requirement", summary=f"ticket {i}", description="")
        for i in range(tickets_n)
    ]
    return {
        "tickets": tickets,
        "batch_index": batch_index,
        "batch_size": batch_size,
        "proposed_updates": [],
        "approved_updates": [],
        "rejected_updates": [],
        "discovered_gaps": [],
        "errors": [],
        "run_metadata": {},
        "committed_nodes": [],
    }


class TestBatchCompleteCheck:
    def test_first_batch_of_many_returns_next_batch(self):
        state = _make_state(tickets_n=9, batch_index=0, batch_size=3)
        assert batch_complete_check(state) == "next_batch"

    def test_last_batch_returns_finalize(self):
        state = _make_state(tickets_n=9, batch_index=6, batch_size=3)
        assert batch_complete_check(state) == "finalize"

    def test_single_batch_returns_finalize(self):
        state = _make_state(tickets_n=3, batch_index=0, batch_size=3)
        assert batch_complete_check(state) == "finalize"

    def test_over_boundary_returns_finalize(self):
        """batch_index + batch_size가 len(tickets)를 초과해도 finalize."""
        state = _make_state(tickets_n=5, batch_index=4, batch_size=3)
        assert batch_complete_check(state) == "finalize"

    def test_middle_batch_returns_next_batch(self):
        state = _make_state(tickets_n=18, batch_index=3, batch_size=3)
        assert batch_complete_check(state) == "next_batch"


class TestAdvanceBatchIndex:
    def test_advances_by_batch_size(self):
        state = _make_state(tickets_n=9, batch_index=0, batch_size=3)
        new_state = advance_batch_index(state)
        assert new_state["batch_index"] == 3

    def test_original_state_unchanged(self):
        state = _make_state(tickets_n=9, batch_index=0, batch_size=3)
        advance_batch_index(state)
        assert state["batch_index"] == 0  # 원본 불변

    def test_multiple_advances(self):
        state = _make_state(tickets_n=9, batch_index=0, batch_size=3)
        state = advance_batch_index(state)
        state = advance_batch_index(state)
        assert state["batch_index"] == 6


# ── _adf_to_text (ADF 파서) ───────────────────────────────────────────────────

class TestAdfToText:
    def _paragraph(self, text: str) -> dict:
        return {
            "type": "paragraph",
            "content": [{"type": "text", "text": text}],
        }

    def test_simple_text_node(self):
        node = {"type": "text", "text": "hello world"}
        assert _adf_to_text(node) == "hello world"

    def test_paragraph_extraction(self):
        node = self._paragraph("camera latency requirement")
        result = _adf_to_text(node)
        assert "camera latency requirement" in result

    def test_heading_extraction(self):
        node = {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Overview"}],
        }
        result = _adf_to_text(node)
        assert "Overview" in result

    def test_doc_with_multiple_paragraphs(self):
        doc = {
            "type": "doc",
            "version": 1,
            "content": [
                self._paragraph("First paragraph."),
                self._paragraph("Second paragraph."),
            ],
        }
        result = _adf_to_text(doc)
        assert "First paragraph." in result
        assert "Second paragraph." in result

    def test_bullet_list(self):
        node = {
            "type": "bulletList",
            "content": [
                {
                    "type": "listItem",
                    "content": [self._paragraph("item one")],
                },
                {
                    "type": "listItem",
                    "content": [self._paragraph("item two")],
                },
            ],
        }
        result = _adf_to_text(node)
        assert "item one" in result
        assert "item two" in result

    def test_code_block(self):
        node = {
            "type": "codeBlock",
            "content": [{"type": "text", "text": "int x = 0;"}],
        }
        result = _adf_to_text(node)
        assert "int x = 0;" in result

    def test_hard_break(self):
        node = {"type": "hardBreak"}
        assert _adf_to_text(node) == "\n"

    def test_non_dict_returns_empty(self):
        assert _adf_to_text("not a dict") == ""
        assert _adf_to_text(None) == ""
        assert _adf_to_text(42) == ""

    def test_mention_node(self):
        node = {
            "type": "mention",
            "attrs": {"text": "john.doe", "id": "abc123"},
        }
        result = _adf_to_text(node)
        assert "@john.doe" in result

    def test_inline_card(self):
        node = {
            "type": "inlineCard",
            "attrs": {"url": "https://jira.example.com/browse/CAM-001"},
        }
        result = _adf_to_text(node)
        assert "CAM-001" in result

    def test_empty_doc(self):
        node = {"type": "doc", "version": 1, "content": []}
        result = _adf_to_text(node)
        assert result == ""
