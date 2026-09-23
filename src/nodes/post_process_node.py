"""PostProcessNode — S-3 output gate; appends RESTRICTED label and review boundary."""

from __future__ import annotations

import re
from typing import Any, ClassVar

from framework.errors import SecurityViolationError
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.llm_runtime import provider_metadata, request_advisory

HUMAN_REVIEW_NOTICE = (
    "RESTRICTED — AUTHORIZED INTEGRITY REVIEW ONLY.\n"
    "This briefing is an AI-generated evidence summary for authorized review officers. "
    "It does not constitute an adjudication, finding of misconduct, or a recommendation "
    "of any disciplinary measure. All conclusions require human review and "
    "institutional decision-making by authorized personnel."
)

# Patterns that indicate adjudication / sanction language that must be blocked.
_ADJUDICATION_PATTERNS = (
    re.compile(r"\b(found\s+guilty|adjudicate[sd]?|misconduct\s+confirmed)\b", re.IGNORECASE),
    re.compile(r"\b(sanction|suspend[ed]*|expel[led]*|grade\s+change|fail\s+the\s+course)\b", re.IGNORECASE),
    re.compile(r"\b(notify\s+student|contact\s+student|inform\s+student)\b", re.IGNORECASE),
)


class PostProcessNode(FunctionNode):
    """S-3 output gate: blocks adjudication language; appends RESTRICTED label.

    Verifies formatted_output is present and does not contain prohibited
    adjudication/sanction/notification language before releasing the briefing.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, config: dict | None = None) -> None:
        super().__init__()
        self._config: dict = config or {}
        self._llm: object | None = self._config.get("llm")

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        """S-3 domain extension: block adjudication and sanction language."""
        output = result.get("formatted_output", "") or result.get("result", "")
        for pattern in _ADJUDICATION_PATTERNS:
            if pattern.search(output):
                raise SecurityViolationError(
                    "PostProcessNode: output contains prohibited adjudication/sanction "
                    "language — refusing to release"
                )
        return result

    def execute(self, state: dict) -> dict:
        if state.get("input_error_message"):
            message = str(state["input_error_message"])
            return {
                "status": AgentStatus.SUCCESS.value,
                "result": message,
                "formatted_output": message,
            }

        # Inner workflow failed (e.g. an unavailable credential or connector).
        # Report it on a SUCCESS envelope: the Marketplace runner only forwards
        # `output` when status == "success", so status=error would leave the
        # caller with no reason at all.
        if state.get("workflow_error_message"):
            # `workflow_error_message` is already caller-safe text chosen from a
            # fixed table in graph.py. The raw cause lives on
            # workflow_error_detail and must not be rendered here.
            reason = str(state["workflow_error_message"])
            reference = str(state.get("workflow_error_code") or "WORKFLOW_FAILED")
            # Only point the caller at their own request when the request is
            # actually at fault; for config/authorisation faults that misleads.
            if reference == "EVIDENCE_INCOMPLETE":
                next_step = "- Add the missing case evidence and submit the request again."
            elif reference == "AUTHORIZATION_DENIED":
                next_step = "- Ask an integrity officer with case access to submit this request."
            else:
                next_step = "- Ask an administrator to finish this agent's connection setup, then retry."
            message = (
                "The academic integrity triage could not be completed.\n\n"
                f"Reason: {reason}\n\n"
                f"How to continue:\n{next_step}\n\n"
                f"Reference: {reference}"
            )
            return {
                "status": AgentStatus.SUCCESS.value,
                "result": message,
                "formatted_output": message,
            }

        request_advisory(
            state,
            "Review the EDU-C2-044 workflow result for completeness.",
            self._llm,
            timeout_s=float(self._config.get("timeout_s", 30.0)),
            max_retry=int(self._config.get("max_retry", 3)),
        )
        metadata = provider_metadata(state)
        formatted_output = state.get("formatted_output", "")

        if not formatted_output:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PostProcessNode: formatted_output is empty or missing"],
                **metadata,
            }

        result = f"{formatted_output}\n\n---\n{HUMAN_REVIEW_NOTICE}"
        emit_trace_event(
            "PostProcessNode_output_gate_verified",
            {"output_length": len(result)},
            state,
        )
        return {
            "result": result,
            "status": AgentStatus.SUCCESS.value,
            **metadata,
        }
