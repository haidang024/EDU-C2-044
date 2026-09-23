# BL-06, BL-07, BL-08 — AuthorizationVerificationNode: fail-closed authorization


from framework.schemas.agent_status import AgentStatus

from src.nodes.authorization_verification_node import AuthorizationVerificationNode


def _base_state(**overrides) -> dict:
    state = {
        "requester_ref": "officer-a1b2",
        "institution_id": "UNIV-001",
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


class TestAuthorizationVerificationNode:
    def setup_method(self):
        self.node = AuthorizationVerificationNode()

    def test_authorized_officer_in_mock_mode(self, monkeypatch):
        """BL-06: authorized officer in mock registry approved."""
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["authorization_status"] == "authorized"

    def test_unauthorized_officer_in_mock_mode(self, monkeypatch):
        """BL-07: unknown officer denied."""
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state(requester_ref="unknown-officer"))
        assert result["status"] == AgentStatus.ERROR.value
        assert result["authorization_status"] == "denied"

    def test_missing_requester_ref_denied(self, monkeypatch):
        """BL-08: missing requester_ref produces denial."""
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state(requester_ref=""))
        assert result["status"] == AgentStatus.ERROR.value
        assert result["authorization_status"] == "denied"

    def test_missing_institution_id_denied(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state(institution_id=""))
        assert result["status"] == AgentStatus.ERROR.value
        assert result["authorization_status"] == "denied"

    def test_error_message_does_not_leak_registry_details(self, monkeypatch):
        """Authorization error must not leak registry contents."""
        monkeypatch.setenv("USE_MOCK", "true")
        result = self.node.execute(_base_state(requester_ref="unknown"))
        error_msgs = " ".join(result.get("error_log", []))
        assert "officer-a1b2" not in error_msgs
        assert "officer-c3d4" not in error_msgs
        assert "UNIV-001" not in error_msgs or "institution" not in error_msgs

    def test_execute_method_signature(self):
        import inspect

        assert hasattr(AuthorizationVerificationNode, "execute")
        sig = inspect.signature(AuthorizationVerificationNode.execute)
        assert list(sig.parameters.keys())[1] == "state"
