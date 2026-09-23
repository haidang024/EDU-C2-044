# BL-24 through BL-28 — OutputNode: domain output gate and RESTRICTED briefing assembly


from framework.schemas.agent_status import AgentStatus

from src.nodes.output_node import RESTRICTED_LABEL, OutputNode


def _base_state(**overrides) -> dict:
    state = {
        "briefing_draft": "[MOCK BRIEFING] This is a test evidence summary for review officers.",
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
            {
                "section_ref": "AI-POLICY-3.2",
                "policy_version": "2025.1",
                "effective_date": "2025-01-01",
                "passage": "test passage",
                "applicability_rationale": "applicable",
            },
        ],
        "prior_case_results": [],
        "evidence_completeness_flags": {"MISSING_REQUIRED": [], "INCOMPLETE_RECORD": False},
        "case_type": "plagiarism",
        "caller_trust_level": "anonymous",
        "correlation_id": "test-corr",
        "node_history": [],
        "error_log": [],
    }
    state.update(overrides)
    return state


class TestOutputNode:
    def setup_method(self):
        self.node = OutputNode()

    def test_assembles_restricted_output(self):
        """BL-24: RESTRICTED label present in formatted output."""
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert RESTRICTED_LABEL in result["formatted_output"]

    def test_blocks_found_guilty_language(self):
        """BL-25: 'found guilty' blocked by domain gate."""
        result = self.node.execute(_base_state(briefing_draft="The student was found guilty of plagiarism."))
        assert result["status"] == AgentStatus.ERROR.value
        assert "formatted_output" not in result or not result.get("formatted_output")

    def test_blocks_suspend_language(self):
        """BL-26: 'suspend' blocked."""
        result = self.node.execute(_base_state(briefing_draft="We recommend to suspend the student for one semester."))
        assert result["status"] == AgentStatus.ERROR.value

    def test_blocks_notify_student_language(self):
        """BL-27: 'notify student' blocked."""
        result = self.node.execute(_base_state(briefing_draft="Please notify student of the committee decision."))
        assert result["status"] == AgentStatus.ERROR.value

    def test_emits_output_blocked_trace(self, monkeypatch):
        """BL-28: OutputNode_blocked trace emitted on gate block."""
        events = []
        import src.nodes.output_node as output_node_module

        monkeypatch.setattr(
            output_node_module,
            "emit_trace_event",
            lambda name, payload, state, _e=events: _e.append(name),
        )
        self.node.execute(_base_state(briefing_draft="The student was found guilty."))
        assert "OutputNode_blocked" in events

    def test_empty_briefing_returns_error(self):
        result = self.node.execute(_base_state(briefing_draft=""))
        assert result["status"] == AgentStatus.ERROR.value

    def test_missing_evidence_caveat_appears(self):
        result = self.node.execute(
            _base_state(
                evidence_completeness_flags={"MISSING_REQUIRED": ["witness_statement"], "INCOMPLETE_RECORD": True}
            )
        )
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "INCOMPLETE RECORD" in result["formatted_output"]

    def test_no_policy_caveat_when_no_results(self):
        result = self.node.execute(_base_state(policy_results=[]))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "POLICY CAVEAT" in result["formatted_output"]

    def test_no_precedent_caveat_when_no_prior_cases(self):
        result = self.node.execute(_base_state(prior_case_results=[]))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "PRECEDENT CAVEAT" in result["formatted_output"]

    def test_triage_table_appears_in_output(self):
        result = self.node.execute(_base_state())
        assert "EVIDENCE TRIAGE TABLE" in result["formatted_output"]

    def test_policy_references_appear_in_output(self):
        result = self.node.execute(_base_state())
        assert "POLICY REFERENCES" in result["formatted_output"]
        assert "AI-POLICY-3.2" in result["formatted_output"]

    def test_no_student_identifiers_in_output(self):
        """PB-13: student PII must not appear in formatted output."""
        result = self.node.execute(_base_state())
        output = result.get("formatted_output", "")
        assert "student_id" not in output.lower()
        assert "student_name" not in output.lower()
