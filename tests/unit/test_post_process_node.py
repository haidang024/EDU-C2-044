# TC-10, BL-29, BL-30, BL-31 — PostProcessNode: S-3 domain extension output gate

import pytest

from framework.errors import SecurityViolationError
from framework.schemas.agent_status import AgentStatus

from src.nodes.post_process_node import HUMAN_REVIEW_NOTICE, PostProcessNode


def _base_state(**overrides) -> dict:
    state = {
        "formatted_output": "RESTRICTED — AUTHORIZED INTEGRITY REVIEW ONLY\n\nTest briefing content.",
        "caller_trust_level": "verified_external",
        "correlation_id": "test-corr",
        "node_history": [],
        "error_log": [],
    }
    state.update(overrides)
    return state


class TestPostProcessNode:
    def setup_method(self):
        self.node = PostProcessNode()

    def test_appends_human_review_notice(self):
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert HUMAN_REVIEW_NOTICE in result["result"]

    def test_empty_formatted_output_returns_error(self):
        result = self.node.execute(_base_state(formatted_output=""))
        assert result["status"] == AgentStatus.ERROR.value

    def test_extra_security_gate_blocks_adjudication_language(self):
        """TC-10/BL-30: S-3 blocks 'found guilty'."""
        with pytest.raises(SecurityViolationError):
            self.node._extra_security_gate_output({"formatted_output": "The student was found guilty."})

    def test_extra_security_gate_blocks_sanction_language(self):
        with pytest.raises(SecurityViolationError):
            self.node._extra_security_gate_output({"formatted_output": "We recommend to suspend the student."})

    def test_extra_security_gate_blocks_grade_change_language(self):
        with pytest.raises(SecurityViolationError):
            self.node._extra_security_gate_output({"formatted_output": "This requires a grade change."})

    def test_extra_security_gate_blocks_notify_student_language(self):
        with pytest.raises(SecurityViolationError):
            self.node._extra_security_gate_output({"formatted_output": "Please notify student of the outcome."})

    def test_extra_security_gate_passes_clean_output(self):
        result = self.node._extra_security_gate_output(
            {"formatted_output": "RESTRICTED — AUTHORIZED INTEGRITY REVIEW ONLY\nTest briefing.", "result": "test"}
        )
        assert result["formatted_output"]

    def test_result_contains_restricted_label(self):
        result = self.node.execute(_base_state())
        assert "RESTRICTED" in result["result"]
