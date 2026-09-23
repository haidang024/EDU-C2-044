# BL-13, BL-14, BL-15 — PolicyRAGNode


from framework.schemas.agent_status import AgentStatus

from src.nodes.policy_rag_node import POLICY_ALLOWLISTED_FIELDS, PolicyRAGNode


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


class TestPolicyRAGNode:
    def setup_method(self):
        self.node = PolicyRAGNode()

    def test_retrieves_policy_in_mock_mode(self, monkeypatch):
        """BL-13: policy retrieved in mock mode."""
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert isinstance(result["policy_results"], list)
        assert len(result["policy_results"]) > 0

    def test_no_result_caveat_set(self, monkeypatch):
        """BL-14: no-result caveat when empty retrieval."""
        monkeypatch.setenv("USE_MOCK", "true")
        from src.services import mock_data

        async def empty_stub(case_type, evidence_types, max_results):
            return []

        monkeypatch.setattr(mock_data, "stub_retrieve_policy", empty_stub)
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["policy_retrieval_provenance"]["caveat"] == "no_results"

    def test_only_allowlisted_fields_in_results(self, monkeypatch):
        """BL-15: extra fields from retrieval stripped."""
        monkeypatch.setenv("USE_MOCK", "true")
        from src.services import mock_data

        async def stub_with_extra(case_type, evidence_types, max_results):
            return [
                {
                    "section_ref": "AI-POLICY-3.2",
                    "policy_version": "2025.1",
                    "effective_date": "2025-01-01",
                    "passage": "test",
                    "applicability_rationale": "applicable",
                    "internal_field": "should_be_stripped",
                    "credential": "should_be_stripped",
                }
            ]

        monkeypatch.setattr(mock_data, "stub_retrieve_policy", stub_with_extra)
        result = self.node.execute(_base_state())
        for item in result["policy_results"]:
            for key in item:
                assert key in POLICY_ALLOWLISTED_FIELDS

    def test_aborts_when_not_authorized(self, monkeypatch):
        """Authorization must be confirmed before retrieval."""
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state(authorization_status="denied"))
        assert result["status"] == AgentStatus.ERROR.value

    def test_provenance_includes_collection_name(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state())
        assert result["policy_retrieval_provenance"]["collection"] == "policy_corpus"
