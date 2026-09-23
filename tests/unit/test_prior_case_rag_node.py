# BL-16, BL-17, BL-18 — PriorCaseRAGNode: identifier redaction and corpus isolation


from framework.schemas.agent_status import AgentStatus

from src.nodes.prior_case_rag_node import PRIOR_CASE_ALLOWLISTED_FIELDS, PriorCaseRAGNode


def _base_state(**overrides) -> dict:
    state = {
        "authorization_status": "authorized",
        "case_type": "plagiarism",
        "evidence_inventory": [{"evidence_type": "detection_report"}],
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


class TestPriorCaseRAGNode:
    def setup_method(self):
        self.node = PriorCaseRAGNode()

    def test_retrieves_prior_cases_in_mock_mode(self, monkeypatch):
        """BL-16: prior cases retrieved in mock mode."""
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert isinstance(result["prior_case_results"], list)

    def test_identifier_patterns_redacted(self, monkeypatch):
        """BL-17: student ID patterns (e.g. AB123456) redacted from retrieved text."""
        monkeypatch.setenv("USE_MOCK", "true")
        from src.services import mock_data

        async def stub_with_identifier(case_type, evidence_pattern, max_results):
            return [
                {
                    "anon_case_ref": "CASE-ANON-0099",
                    "case_type": case_type,
                    "evidence_pattern_summary": "Detection report for student AB123456.",
                    "recorded_outcome": "Referred. Email: student@univ.edu",
                    "applied_policy_sections": ["AI-POLICY-3.2"],
                }
            ]

        monkeypatch.setattr(mock_data, "stub_retrieve_prior_cases", stub_with_identifier)
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        for item in result["prior_case_results"]:
            for val in item.values():
                text = str(val)
                assert "AB123456" not in text, "Student ID pattern must be redacted"
                assert "student@univ.edu" not in text, "Email must be redacted"

    def test_only_allowlisted_fields_returned(self, monkeypatch):
        """BL-18: extra fields stripped before state entry."""
        monkeypatch.setenv("USE_MOCK", "true")
        from src.services import mock_data

        async def stub_with_extra(case_type, evidence_pattern, max_results):
            return [
                {
                    "anon_case_ref": "CASE-ANON-0099",
                    "case_type": case_type,
                    "evidence_pattern_summary": "test",
                    "recorded_outcome": "Referred",
                    "applied_policy_sections": ["AI-POLICY-3.2"],
                    "raw_student_name": "should_be_stripped",
                    "internal_field": "should_be_stripped",
                }
            ]

        monkeypatch.setattr(mock_data, "stub_retrieve_prior_cases", stub_with_extra)
        result = self.node.execute(_base_state())
        for item in result["prior_case_results"]:
            for key in item:
                assert key in PRIOR_CASE_ALLOWLISTED_FIELDS

    def test_aborts_when_not_authorized(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state(authorization_status="denied"))
        assert result["status"] == AgentStatus.ERROR.value

    def test_provenance_includes_collection_name(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state())
        assert result["prior_case_retrieval_provenance"]["collection"] == "prior_case_corpus"

    def test_no_result_becomes_caveat_not_error(self, monkeypatch):
        """Missing prior cases become a coverage caveat, not an error."""
        monkeypatch.setenv("USE_MOCK", "true")
        from src.services import mock_data

        async def empty_stub(case_type, evidence_pattern, max_results):
            return []

        monkeypatch.setattr(mock_data, "stub_retrieve_prior_cases", empty_stub)
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["prior_case_retrieval_provenance"]["caveat"] == "no_results"
