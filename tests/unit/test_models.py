"""OntologyNode, OntologyEdge, ProposedUpdate, JiraTicket, AgentState 모델 테스트."""
import uuid

import pytest
from pydantic import ValidationError

from src.models.jira_ticket import JiraTicket
from src.models.ontology import (
    GapFinding,
    OntologyEdge,
    OntologyNode,
    ProposedUpdate,
    SubGraph,
)
from tests.conftest import make_edge, make_node


class TestOntologyNode:
    def test_basic_creation(self):
        n = make_node()
        assert n.id == "N-001"
        assert n.type == "Requirement"
        assert n.status == "Open"

    def test_ai_fields_default(self):
        n = make_node()
        assert n.ai_classified is False
        assert n.original_jira_type == ""

    def test_ai_fields_set(self):
        n = make_node(original_jira_type="Epic", ai_classified=True)
        assert n.ai_classified is True
        assert n.original_jira_type == "Epic"

    def test_all_valid_types(self):
        for t in ("Requirement", "Architecture_Block", "Design_Spec", "Verification", "Issue"):
            n = make_node(type=t)
            assert n.type == t

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            make_node(type="InvalidType")

    def test_labels_default_empty(self):
        n = make_node()
        assert n.labels == []

    def test_labels_stored(self):
        n = make_node(labels=["camera", "hal"])
        assert n.labels == ["camera", "hal"]

    def test_json_roundtrip(self):
        n = make_node(id="CAM-001", type="Requirement", labels=["latency"])
        restored = OntologyNode.model_validate_json(n.model_dump_json())
        assert restored.id == n.id
        assert restored.labels == n.labels


class TestOntologyEdge:
    def test_basic_creation(self):
        e = make_edge()
        assert e.source_id == "A"
        assert e.target_id == "B"
        assert e.relation == "satisfies"
        assert e.is_inferred is False

    def test_all_valid_relations(self):
        for rel in ("satisfies", "implements", "verifies", "affects", "blocks"):
            e = make_edge(relation=rel)
            assert e.relation == rel

    def test_invalid_relation_raises(self):
        with pytest.raises(ValidationError):
            make_edge(relation="unknown_relation")

    def test_inferred_flag(self):
        e = make_edge(is_inferred=True, reasoning="[INFERRED] semantic match")
        assert e.is_inferred is True

    def test_json_roundtrip(self):
        e = make_edge(source_id="CAM-010", target_id="CAM-001", relation="satisfies")
        restored = OntologyEdge.model_validate_json(e.model_dump_json())
        assert restored.source_id == e.source_id
        assert restored.relation == e.relation


class TestProposedUpdate:
    def test_basic_creation(self):
        upd = ProposedUpdate(
            nodes=[make_node()],
            edges=[make_edge()],
            confidence_score=0.9,
            batch_id=uuid.uuid4().hex,
        )
        assert len(upd.nodes) == 1
        assert len(upd.edges) == 1
        assert upd.confidence_score == 0.9

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            ProposedUpdate(nodes=[], edges=[], confidence_score=1.1, batch_id="x")
        with pytest.raises(ValidationError):
            ProposedUpdate(nodes=[], edges=[], confidence_score=-0.1, batch_id="x")

    def test_json_roundtrip(self):
        bid = uuid.uuid4().hex
        upd = ProposedUpdate(
            nodes=[make_node(id="CAM-001", type="Requirement")],
            edges=[make_edge("CAM-010", "CAM-001", "satisfies")],
            confidence_score=0.85,
            batch_id=bid,
        )
        restored = ProposedUpdate.model_validate_json(upd.model_dump_json())
        assert restored.batch_id == bid
        assert restored.nodes[0].id == "CAM-001"
        assert restored.edges[0].relation == "satisfies"
        assert restored.confidence_score == 0.85


class TestGapFinding:
    def test_basic_creation(self):
        g = GapFinding(
            gap_id="G-001",
            gap_type="orphan_node",
            severity="high",
            affected_node_ids=["CAM-050"],
            description="no links",
            suggested_action="add links",
        )
        assert g.gap_id == "G-001"
        assert g.gap_type == "orphan_node"
        assert g.severity == "high"

    def test_all_gap_types(self):
        for gt in ("orphan_node", "missing_verification", "conflict", "cross_domain_hidden"):
            g = GapFinding(
                gap_id="x", gap_type=gt, severity="low",
                affected_node_ids=[], description="d", suggested_action="s"
            )
            assert g.gap_type == gt

    def test_all_severities(self):
        for sv in ("critical", "high", "medium", "low"):
            g = GapFinding(
                gap_id="x", gap_type="orphan_node", severity=sv,
                affected_node_ids=[], description="d", suggested_action="s"
            )
            assert g.severity == sv


class TestSubGraph:
    def test_empty(self):
        sg = SubGraph(nodes=[], edges=[])
        assert len(sg.nodes) == 0
        assert len(sg.edges) == 0

    def test_with_data(self):
        sg = SubGraph(nodes=[make_node()], edges=[make_edge()])
        assert len(sg.nodes) == 1
        assert len(sg.edges) == 1


class TestJiraTicket:
    def test_basic_creation(self):
        t = JiraTicket(
            id="CAM-001",
            type="Requirement",
            summary="4K latency",
            description="100ms budget",
        )
        assert t.id == "CAM-001"
        assert t.priority == "Medium"
        assert t.linked_issue_ids == []

    def test_linked_issue_ids(self):
        t = JiraTicket(
            id="CAM-010", type="Architecture_Block",
            summary="ISP", description="",
            linked_issue_ids=["CAM-001", "CAM-002"],
        )
        assert len(t.linked_issue_ids) == 2
