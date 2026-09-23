"""PreProcessNode — validates and sanitizes case intake input for EDU-C2-044."""

from __future__ import annotations

import json
import re
from typing import Any, ClassVar

from framework.errors import SecurityViolationError
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

MAX_INPUT_CHARS = 4000

# Patterns that indicate raw student PII — rejected at S-1/S-2.
_STUDENT_PII_PATTERNS = (
    re.compile(r"student[_\s-]?id", re.IGNORECASE),
    re.compile(r"student[_\s-]?name", re.IGNORECASE),
    re.compile(r"student[_\s-]?email", re.IGNORECASE),
    re.compile(r"student[_\s-]?number", re.IGNORECASE),
)

PERMITTED_CASE_TYPES = {
    "plagiarism",
    "contract_cheating",
    "exam_misconduct",
    "fabrication",
    "falsification",
    "unauthorized_collaboration",
    "other",
}

PERMITTED_AUDIENCES = {"integrity_officer", "panel", "committee"}
PERMITTED_LANGUAGES = {"en", "ja", "fr", "de", "es", "zh", "ko"}


class PreProcessNode(FunctionNode):
    """Validate case intake input; reject student PII and unsupported field values.

    S-1 gate: enforces VERIFIED_EXTERNAL trust. S-2 extension: rejects student
    identifiers, oversized input, and invalid/unbounded field values.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-2 domain extension: reject student PII and oversized input."""
        user_input = state.get("user_input", "")
        if not isinstance(user_input, str):
            raise SecurityViolationError("PreProcessNode: user_input must be a plain string")
        if len(user_input) > MAX_INPUT_CHARS:
            raise SecurityViolationError(f"PreProcessNode: input exceeds {MAX_INPUT_CHARS} chars")
        for pattern in _STUDENT_PII_PATTERNS:
            if pattern.search(user_input):
                raise SecurityViolationError(
                    "PreProcessNode: student identifiers are not accepted — " "use anonymized case references only"
                )
        return state

    def execute(self, state: dict) -> dict:
        user_input = state.get("user_input", "")

        if not user_input or not user_input.strip():
            return {
                "status": AgentStatus.SUCCESS.value,
                "input_error_message": "No academic integrity case intake was provided.",
                "input_error_guidance": [
                    "Provide an anonymized JSON case intake.",
                    "Include case_ref, case_type, evidence_bundle_ref, requester_ref, and institution_id.",
                ],
            }

        # Parse structured intake payload
        try:
            payload = json.loads(user_input.strip())
        except (json.JSONDecodeError, TypeError):
            return {
                "status": AgentStatus.SUCCESS.value,
                "input_error_message": "The academic integrity case intake is not valid JSON.",
                "input_error_guidance": [
                    "Provide a JSON object with case_ref, case_type, evidence_bundle_ref, requester_ref, and institution_id."
                ],
            }

        required_fields = ("case_ref", "case_type", "evidence_bundle_ref", "requester_ref", "institution_id")
        missing = [f for f in required_fields if not payload.get(f)]
        if missing:
            return {
                "status": AgentStatus.SUCCESS.value,
                "input_error_message": f"Required case intake fields are missing: {missing}.",
                "input_error_guidance": ["Add every required field using anonymized reference values."],
            }

        case_type = payload["case_type"]
        if case_type not in PERMITTED_CASE_TYPES:
            return {
                "status": AgentStatus.SUCCESS.value,
                "input_error_message": f"Case type '{case_type}' is not supported.",
                "input_error_guidance": [f"Use one of: {', '.join(sorted(PERMITTED_CASE_TYPES))}."],
            }

        audience = payload.get("audience", "integrity_officer")
        if audience not in PERMITTED_AUDIENCES:
            return {
                "status": AgentStatus.SUCCESS.value,
                "input_error_message": f"Audience '{audience}' is not supported.",
                "input_error_guidance": [f"Use one of: {', '.join(sorted(PERMITTED_AUDIENCES))}."],
            }

        output_language = payload.get("output_language", "en")
        if output_language not in PERMITTED_LANGUAGES:
            return {
                "status": AgentStatus.SUCCESS.value,
                "input_error_message": f"Output language '{output_language}' is not supported.",
                "input_error_guidance": [f"Use one of: {', '.join(sorted(PERMITTED_LANGUAGES))}."],
            }

        emit_trace_event(
            "PreProcessNode_intake_validated",
            {
                "case_type": case_type,
                "institution_id": payload["institution_id"],
                "audience": audience,
            },
            state,
        )
        return {
            "validated_input": user_input.strip(),
            "case_ref": payload["case_ref"],
            "case_type": case_type,
            "evidence_bundle_ref": payload["evidence_bundle_ref"],
            "requester_ref": payload["requester_ref"],
            "institution_id": payload["institution_id"],
            "audience": audience,
            "output_language": output_language,
            "status": AgentStatus.SUCCESS.value,
        }
