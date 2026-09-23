# BL-19, BL-20 — EvidenceTriageAssemblyNode: deterministic triage, no misconduct inference


from framework.schemas.agent_status import AgentStatus

from src.nodes.evidence_triage_assembly_node import EvidenceTriageAssemblyNode


def _base_state(**overrides) -> dict:
    state = {
        "case_type": "plagiarism",
        "evidence_inventory": [
            {
                "evidence_type": "detection_report",
                "priority": "PRIMARY",
                "source_ref": "src-001",
                "submission_date": "2026-01-01",
                "integrity_status": "verified",
                "completeness_status": "complete",
            },
            {
                "evidence_type": "submission_file",
                "priority": "PRIMARY",
                "source_ref": "src-002",
                "submission_date": "2026-01-02",
                "integrity_status": "verified",
                "completeness_status": "complete",
            },
        ],
        "evidence_completeness_flags": {"MISSING_REQUIRED": [], "INCOMPLETE_RECORD": False},
        "caller_trust_level": "anonymous",
        "correlation_id": "test-corr",
        "node_history": [],
        "error_log": [],
    }
    state.update(overrides)
    return state


class TestEvidenceTriageAssemblyNode:
    def setup_method(self):
        self.node = EvidenceTriageAssemblyNode()

    def test_assembles_triage_table(self):
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert len(result["triage_table"]) >= 2

    def test_missing_required_row_added(self):
        """BL-19: missing required evidence type produces a triage row."""
        result = self.node.execute(
            _base_state(
                evidence_completeness_flags={
                    "MISSING_REQUIRED": ["prior_warning_record"],
                    "INCOMPLETE_RECORD": True,
                }
            )
        )
        missing_rows = [r for r in result["triage_table"] if "MISSING" in r.get("triage_note", "")]
        assert len(missing_rows) >= 1

    def test_no_misconduct_language_in_triage_notes(self):
        """BL-20: triage notes are mechanical; no misconduct inference."""
        result = self.node.execute(_base_state())
        misconduct_terms = ["guilty", "misconduct", "sanction", "suspend", "credibility"]
        for row in result["triage_table"]:
            note = row.get("triage_note", "").lower()
            for term in misconduct_terms:
                assert term not in note, f"Misconduct term '{term}' found in triage note"

    def test_priority_ordering_primary_first(self):
        state = _base_state()
        state["evidence_inventory"] = [
            {
                "evidence_type": "correspondence",
                "priority": "ANCILLARY",
                "source_ref": "anc-001",
                "submission_date": "2026-01-03",
                "integrity_status": "ok",
                "completeness_status": "ok",
            },
            {
                "evidence_type": "detection_report",
                "priority": "PRIMARY",
                "source_ref": "pri-001",
                "submission_date": "2026-01-01",
                "integrity_status": "verified",
                "completeness_status": "complete",
            },
        ]
        result = self.node.execute(state)
        priorities = [
            r["priority"] for r in result["triage_table"] if r.get("source_ref")
        ]  # exclude missing-required placeholder rows
        order = {"PRIMARY": 0, "SUPPORTING": 1, "ANCILLARY": 2}
        assert priorities == sorted(priorities, key=lambda p: order.get(p, 3))

    def test_unverified_item_gets_pending_note(self):
        state = _base_state()
        state["evidence_inventory"] = [
            {
                "evidence_type": "detection_report",
                "priority": "PRIMARY",
                "source_ref": "src-001",
                "submission_date": "2026-01-01",
                "integrity_status": "unverified",
                "completeness_status": "complete",
            },
        ]
        result = self.node.execute(state)
        notes = [r["triage_note"] for r in result["triage_table"]]
        assert any("Pending verification" in n for n in notes)
