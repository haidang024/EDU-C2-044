"""EvidenceTriageAssemblyNode — deterministic triage table assembly for EDU-C2-044."""

from __future__ import annotations

from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

# Priority order used for triage table row ordering
_PRIORITY_ORDER = {"PRIMARY": 0, "SUPPORTING": 1, "ANCILLARY": 2}


class EvidenceTriageAssemblyNode(FunctionNode):
    """Assemble deterministic triage table from normalized evidence inventory.

    No LLM call. Does not infer misconduct, credibility, or disciplinary outcome.
    Assigns triage notes based on completeness flags and evidence priority only.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        evidence_inventory = state.get("evidence_inventory", [])
        completeness_flags = state.get("evidence_completeness_flags", {})
        case_type = state.get("case_type", "other")

        missing_required = completeness_flags.get("MISSING_REQUIRED", [])
        incomplete_record = completeness_flags.get("INCOMPLETE_RECORD", False)

        triage_table = []
        for item in evidence_inventory:
            ev_type = item.get("evidence_type", "other")
            priority = item.get("priority", "ANCILLARY")
            source_ref = item.get("source_ref", "")
            submission_date = item.get("submission_date", "")
            integrity_status = item.get("integrity_status", "unknown")
            completeness_status = item.get("completeness_status", "unknown")

            # Deterministic triage note — no misconduct/credibility inference
            if ev_type in missing_required:
                triage_note = "REQUIRED — not yet provided"
            elif integrity_status == "unverified":
                triage_note = "Pending verification"
            elif completeness_status == "incomplete":
                triage_note = "Incomplete — partial evidence"
            else:
                triage_note = "Present"

            triage_table.append(
                {
                    "evidence_type": ev_type,
                    "priority": priority,
                    "source_ref": source_ref,
                    "submission_date": submission_date,
                    "triage_note": triage_note,
                }
            )

        # Add rows for missing required evidence types not in inventory
        present_types = {item.get("evidence_type") for item in evidence_inventory}
        for req_type in missing_required:
            if req_type not in present_types:
                triage_table.append(
                    {
                        "evidence_type": req_type,
                        "priority": "PRIMARY",
                        "source_ref": "",
                        "submission_date": "",
                        "triage_note": "MISSING — required for this case type",
                    }
                )

        # Sort by priority
        triage_table.sort(key=lambda x: _PRIORITY_ORDER.get(x.get("priority", "ANCILLARY"), 3))

        emit_trace_event(
            "EvidenceTriageAssemblyNode_assembled",
            {
                "case_type": case_type,
                "triage_row_count": len(triage_table),
                "incomplete_record": incomplete_record,
            },
            state,
        )
        return {
            "triage_table": triage_table,
            "status": AgentStatus.SUCCESS.value,
        }
