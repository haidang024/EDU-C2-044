"""EvidenceInventoryNormalizationNode — deterministic evidence normalization for EDU-C2-044."""

from __future__ import annotations

import json
from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

APPROVED_EVIDENCE_TYPES = {
    "detection_report",
    "submission_file",
    "witness_statement",
    "prior_warning_record",
    "correspondence",
    "other",
}

# Required-evidence checklist per case type (institution-configurable; these are defaults).
_DEFAULT_REQUIRED_EVIDENCE: dict[str, list[str]] = {
    "plagiarism": ["detection_report", "submission_file"],
    "contract_cheating": ["submission_file", "detection_report"],
    "exam_misconduct": ["submission_file"],
    "fabrication": ["submission_file"],
    "falsification": ["submission_file"],
    "unauthorized_collaboration": ["submission_file"],
    "other": [],
}

PRIORITY_MAP = {
    "detection_report": "PRIMARY",
    "submission_file": "PRIMARY",
    "prior_warning_record": "SUPPORTING",
    "witness_statement": "SUPPORTING",
    "correspondence": "ANCILLARY",
    "other": "ANCILLARY",
}

NORMALIZED_FIELDS = {"evidence_type", "source_ref", "submission_date", "integrity_status", "completeness_status"}


class EvidenceInventoryNormalizationNode(FunctionNode):
    """Normalize submitted evidence to approved fields; apply required-evidence checklist.

    Assigns PRIMARY / SUPPORTING / ANCILLARY priorities deterministically.
    No LLM call. Preserves evidence provenance without student identifiers.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        validated_input = state.get("validated_input", state.get("user_input", ""))

        # Inner-graph fallback: parse fields from validated_input when not in state.
        try:
            payload = json.loads(validated_input) if validated_input else {}
        except (json.JSONDecodeError, TypeError):
            payload = {}

        case_type = state.get("case_type") or payload.get("case_type", "other")
        evidence_bundle_ref = state.get("evidence_bundle_ref") or payload.get("evidence_bundle_ref", "")
        raw_items = payload.get("evidence_items", [])

        if not isinstance(raw_items, list):
            raw_items = []

        normalized = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            ev_type = item.get("evidence_type", "other")
            if ev_type not in APPROVED_EVIDENCE_TYPES:
                ev_type = "other"

            normalized.append(
                {
                    "evidence_type": ev_type,
                    "source_ref": str(item.get("source_ref", ""))[:200],  # cap length, no PII
                    "submission_date": str(item.get("submission_date", ""))[:20],
                    "integrity_status": item.get("integrity_status", "unknown"),
                    "completeness_status": item.get("completeness_status", "unknown"),
                    "priority": PRIORITY_MAP.get(ev_type, "ANCILLARY"),
                }
            )

        # Sort: PRIMARY first, then SUPPORTING, then ANCILLARY
        _order = {"PRIMARY": 0, "SUPPORTING": 1, "ANCILLARY": 2}
        normalized.sort(key=lambda x: _order.get(x["priority"], 3))

        # Apply required-evidence checklist
        required = _DEFAULT_REQUIRED_EVIDENCE.get(case_type, [])
        present_types = {item["evidence_type"] for item in normalized}
        missing_required = [r for r in required if r not in present_types]
        incomplete_record = bool(missing_required)

        completeness_flags = {
            "MISSING_REQUIRED": missing_required,
            "INCOMPLETE_RECORD": incomplete_record,
        }

        emit_trace_event(
            "EvidenceInventoryNormalizationNode_normalized",
            {
                "case_type": case_type,
                "item_count": len(normalized),
                "incomplete_record": incomplete_record,
                "evidence_bundle_ref": evidence_bundle_ref,
            },
            state,
        )
        # Also propagate parsed fields so downstream inner-graph nodes have them in state.
        output_language = state.get("output_language") or payload.get("output_language", "en")
        return {
            "evidence_inventory": normalized,
            "evidence_completeness_flags": completeness_flags,
            "case_type": case_type,
            "output_language": output_language,
            "evidence_bundle_ref": evidence_bundle_ref,
            "status": AgentStatus.SUCCESS.value,
        }
