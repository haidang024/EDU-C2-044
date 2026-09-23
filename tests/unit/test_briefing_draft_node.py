# BL-21, BL-22, BL-23 — BriefingDraftNode: grounded LLM draft


from framework.schemas.agent_status import AgentStatus

from src.nodes.briefing_draft_node import BriefingDraftNode


def _base_state(**overrides) -> dict:
    state = {
        "authorization_status": "authorized",
        "evidence_inventory": [
            {
                "evidence_type": "detection_report",
                "priority": "PRIMARY",
                "source_ref": "src-001",
                "submission_date": "2026-01-01",
                "integrity_status": "verified",
                "completeness_status": "complete",
            },
        ],
        "triage_table": [
            {
                "evidence_type": "detection_report",
                "priority": "PRIMARY",
                "source_ref": "src-001",
                "submission_date": "2026-01-01",
                "triage_note": "Present",
            },
        ],
        "policy_results": [
            {"section_ref": "AI-POLICY-3.2", "passage": "Policy passage text."},
        ],
        "prior_case_results": [],
        "evidence_completeness_flags": {"MISSING_REQUIRED": [], "INCOMPLETE_RECORD": False},
        "case_type": "plagiarism",
        "output_language": "en",
        "caller_trust_level": "ANONYMOUS",
        "correlation_id": "test-corr",
        "session_id": "test-session",
        "thread_id": "test-thread",
        "trace_id": "test-trace",
        "node_history": [],
        "error_log": [],
    }
    state.update(overrides)
    return state


class TestBriefingDraftNode:
    def setup_method(self):
        self.node = BriefingDraftNode()

    def test_drafts_briefing_in_mock_mode(self, monkeypatch):
        """BL-23: briefing drafted in mock mode."""
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["briefing_draft"]

    def test_fails_without_authorization(self, monkeypatch):
        """BL-21: no LLM call before authorization."""
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state(authorization_status=""))
        assert result["status"] == AgentStatus.ERROR.value

    def test_fails_on_empty_evidence_inventory(self, monkeypatch):
        """BL-22: no briefing without evidence."""
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state(evidence_inventory=[]))
        assert result["status"] == AgentStatus.ERROR.value

    def test_briefing_contains_case_type(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state())
        assert "plagiarism" in result["briefing_draft"].lower()

    def test_no_student_pii_in_briefing(self, monkeypatch):
        """Briefing draft must not contain raw student identifiers."""
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state())
        draft = result.get("briefing_draft", "")
        assert "student_id" not in draft.lower()
        assert "student_name" not in draft.lower()
