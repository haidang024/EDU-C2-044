# BL-09 through BL-12 — EvidenceInventoryNormalizationNode

import json


from framework.schemas.agent_status import AgentStatus

from src.nodes.evidence_inventory_normalization_node import EvidenceInventoryNormalizationNode

_VALID_ITEMS = [
    {
        "evidence_type": "detection_report",
        "source_ref": "src-001",
        "submission_date": "2026-01-01",
        "integrity_status": "verified",
        "completeness_status": "complete",
    },
    {
        "evidence_type": "submission_file",
        "source_ref": "src-002",
        "submission_date": "2026-01-02",
        "integrity_status": "verified",
        "completeness_status": "complete",
    },
    {
        "evidence_type": "witness_statement",
        "source_ref": "src-003",
        "submission_date": "2026-01-03",
        "integrity_status": "unverified",
        "completeness_status": "complete",
    },
]


def _base_state(**overrides) -> dict:
    state = {
        "case_type": "plagiarism",
        "evidence_bundle_ref": "bundle-001",
        "validated_input": json.dumps({"evidence_items": _VALID_ITEMS}),
        "caller_trust_level": "anonymous",
        "correlation_id": "test-corr",
        "node_history": [],
        "error_log": [],
    }
    state.update(overrides)
    return state


class TestEvidenceInventoryNormalizationNode:
    def setup_method(self):
        self.node = EvidenceInventoryNormalizationNode()

    def test_success_with_valid_items(self):
        """BL-09: valid evidence items normalized correctly."""
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert len(result["evidence_inventory"]) == 3

    def test_unknown_evidence_type_mapped_to_other(self):
        """BL-10: unknown type → 'other'."""
        items = [
            {
                "evidence_type": "new_unknown_type",
                "source_ref": "x",
                "submission_date": "2026-01-01",
                "integrity_status": "ok",
                "completeness_status": "ok",
            }
        ]
        result = self.node.execute(_base_state(validated_input=json.dumps({"evidence_items": items})))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["evidence_inventory"][0]["evidence_type"] == "other"
        assert result["evidence_inventory"][0]["priority"] == "ANCILLARY"

    def test_missing_required_evidence_flagged(self):
        """BL-11: plagiarism without detection_report sets MISSING_REQUIRED."""
        items = [
            {
                "evidence_type": "submission_file",
                "source_ref": "x",
                "submission_date": "2026-01-01",
                "integrity_status": "ok",
                "completeness_status": "ok",
            }
        ]
        result = self.node.execute(
            _base_state(
                case_type="plagiarism",
                validated_input=json.dumps({"evidence_items": items}),
            )
        )
        assert "detection_report" in result["evidence_completeness_flags"]["MISSING_REQUIRED"]
        assert result["evidence_completeness_flags"]["INCOMPLETE_RECORD"] is True

    def test_priority_sort_order(self):
        """BL-12: PRIMARY items come before SUPPORTING come before ANCILLARY."""
        result = self.node.execute(_base_state())
        priorities = [item["priority"] for item in result["evidence_inventory"]]
        order = {"PRIMARY": 0, "SUPPORTING": 1, "ANCILLARY": 2}
        assert priorities == sorted(priorities, key=lambda p: order.get(p, 3))

    def test_empty_items_produces_incomplete_record(self):
        result = self.node.execute(_base_state(validated_input=json.dumps({"evidence_items": []})))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["evidence_completeness_flags"]["INCOMPLETE_RECORD"] is True

    def test_malformed_bundle_gracefully_handled(self):
        """Malformed bundle (not list) handled without exception."""
        result = self.node.execute(_base_state(validated_input="not json"))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["evidence_inventory"] == []

    def test_no_student_identifiers_in_normalized_items(self):
        """Evidence items must not carry student-identifiable fields."""
        result = self.node.execute(_base_state())
        for item in result["evidence_inventory"]:
            for key in item:
                assert "student" not in key.lower()

    def test_source_ref_capped(self):
        """source_ref is capped at 200 chars to prevent oversized state."""
        long_ref = "x" * 300
        items = [
            {
                "evidence_type": "detection_report",
                "source_ref": long_ref,
                "submission_date": "2026-01-01",
                "integrity_status": "ok",
                "completeness_status": "ok",
            }
        ]
        result = self.node.execute(_base_state(validated_input=json.dumps({"evidence_items": items})))
        assert len(result["evidence_inventory"][0]["source_ref"]) <= 200

    def test_other_case_type_no_required_evidence(self):
        """'other' case type has no required evidence checklist — no MISSING_REQUIRED."""
        result = self.node.execute(_base_state(case_type="other"))
        assert result["evidence_completeness_flags"]["MISSING_REQUIRED"] == []
