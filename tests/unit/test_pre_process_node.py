# TC-08, TC-09 — PreProcessNode: S-1 trust gate, S-2 domain extension


from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.pre_process_node import PreProcessNode

_VALID_INPUT = (
    '{"case_ref": "CASE-ANON-001", "case_type": "plagiarism", '
    '"evidence_bundle_ref": "bundle-001", "requester_ref": "officer-a1b2", '
    '"institution_id": "UNIV-001", '
    '"evidence_items": [{"evidence_type": "detection_report", '
    '"source_ref": "src-001", "submission_date": "2026-01-01", '
    '"integrity_status": "verified", "completeness_status": "complete"}]}'
)


def _base_state(**overrides) -> dict:
    state = {
        "user_input": _VALID_INPUT,
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "correlation_id": "test-corr",
        "session_id": "test-session",
        "thread_id": "test-thread",
        "trace_id": "test-trace",
        "node_history": [],
        "error_log": [],
    }
    state.update(overrides)
    return state


class TestPreProcessNode:
    def setup_method(self):
        self.node = PreProcessNode()

    def test_success_path(self):
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["validated_input"]
        assert result["case_ref"] == "CASE-ANON-001"
        assert result["case_type"] == "plagiarism"

    def test_empty_input_returns_guidance(self):
        result = self.node.execute(_base_state(user_input=""))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "input_error_message" in result

    def test_invalid_json_returns_guidance(self):
        result = self.node.execute(_base_state(user_input="not json"))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "not valid JSON" in result["input_error_message"]

    def test_missing_required_fields_returns_guidance(self):
        import json

        payload = json.loads(_VALID_INPUT)
        del payload["case_ref"]
        result = self.node.execute(_base_state(user_input=json.dumps(payload)))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "missing" in result["input_error_message"].lower()

    def test_unsupported_case_type_returns_guidance(self):
        import json

        payload = json.loads(_VALID_INPUT)
        payload["case_type"] = "unknown_type"
        result = self.node.execute(_base_state(user_input=json.dumps(payload)))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "not supported" in result["input_error_message"]

    def test_unsupported_audience_returns_guidance(self):
        import json

        payload = json.loads(_VALID_INPUT)
        payload["audience"] = "student"
        result = self.node.execute(_base_state(user_input=json.dumps(payload)))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "not supported" in result["input_error_message"]

    def test_trust_gate_denies_anonymous_caller(self):
        """TC-08: insufficient trust level refused via __call__(), not execute()."""
        state = _base_state(caller_trust_level=TrustLevel.ANONYMOUS.value)
        result = self.node(state)
        assert result.get("status") != AgentStatus.SUCCESS.value

    def test_extra_security_gate_rejects_student_id(self):
        """TC-09: S-2 domain extension rejects student_id pattern."""
        state = _base_state(user_input='{"student_id": "S123", "case_ref": "x"}')
        result = self.node(state)
        assert result.get("status") == AgentStatus.ERROR.value

    def test_extra_security_gate_rejects_student_name(self):
        state = _base_state(user_input='{"student_name": "John Doe", "case_ref": "x"}')
        result = self.node(state)
        assert result.get("status") == AgentStatus.ERROR.value

    def test_extra_security_gate_rejects_oversized_input(self):
        state = _base_state(user_input="x" * 4001)
        result = self.node(state)
        assert result.get("status") == AgentStatus.ERROR.value

    def test_execute_method_signature(self):
        """Node contract: execute(self, state) — not _invoke_impl()."""
        import inspect

        assert hasattr(PreProcessNode, "execute")
        sig = inspect.signature(PreProcessNode.execute)
        params = list(sig.parameters.keys())
        assert params[1] == "state"
        assert "_invoke_impl" not in PreProcessNode.__dict__

    def test_default_audience_and_language(self):
        import json

        payload = json.loads(_VALID_INPUT)
        # Remove optional fields
        payload.pop("audience", None)
        payload.pop("output_language", None)
        result = self.node.execute(_base_state(user_input=json.dumps(payload)))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["audience"] == "integrity_officer"
        assert result["output_language"] == "en"
