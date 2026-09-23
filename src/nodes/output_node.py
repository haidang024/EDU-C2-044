"""OutputNode — applies domain output gate and formats the RESTRICTED briefing."""

from __future__ import annotations

import re
from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

RESTRICTED_LABEL = "RESTRICTED — AUTHORIZED INTEGRITY REVIEW ONLY"
NO_ADJUDICATION_NOTICE = (
    "This document organizes submitted evidence for human review. "
    "It does not detect plagiarism or AI-generated content, make misconduct findings, "
    "recommend disciplinary measures, change grades, contact students, or write to institutional systems."
)

# Patterns blocked by the domain output gate
_BLOCKED_PATTERNS = (
    re.compile(r"\b(found\s+guilty|adjudicate[sd]?|misconduct\s+confirmed)\b", re.IGNORECASE),
    re.compile(r"\b(sanction|suspend[ed]*|expel[led]*|grade\s+change|fail\s+the\s+course)\b", re.IGNORECASE),
    re.compile(r"\b(notify\s+student|contact\s+student|inform\s+student)\b", re.IGNORECASE),
    re.compile(r"\b(student[_\s]?id|student[_\s]?name|student[_\s]?email)\s*[:=]\s*\S+", re.IGNORECASE),
)


def _contains_blocked_content(text: str) -> tuple[bool, str]:
    for pattern in _BLOCKED_PATTERNS:
        m = pattern.search(text)
        if m:
            return True, m.group(0)[:40]
    return False, ""


class OutputNode(FunctionNode):
    """Apply domain output gate and assemble the final RESTRICTED briefing package.

    Blocks adjudication, sanction, grade-change, and notification language.
    Removes identifier-like patterns. Prepends RESTRICTED label and human-review notice.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        briefing_draft = state.get("briefing_draft", "")
        triage_table = state.get("triage_table", [])
        policy_results = state.get("policy_results", [])
        prior_case_results = state.get("prior_case_results", [])
        completeness_flags = state.get("evidence_completeness_flags", {})
        case_type = state.get("case_type", "")

        if not briefing_draft:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["OutputNode: briefing_draft is empty — cannot produce output"],
            }

        blocked, blocked_snippet = _contains_blocked_content(briefing_draft)
        if blocked:
            emit_trace_event(
                "OutputNode_blocked",
                {"reason": "adjudication_language_detected", "snippet_preview": blocked_snippet},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    f"OutputNode: domain output gate blocked briefing — "
                    f"prohibited language detected near '{blocked_snippet}'"
                ],
            }

        # Assemble caveats for missing evidence / no-result retrievals
        missing_required = completeness_flags.get("MISSING_REQUIRED", [])
        caveats = []
        if missing_required:
            caveats.append(f"INCOMPLETE RECORD: missing required evidence types: {', '.join(missing_required)}")
        if not policy_results:
            caveats.append("POLICY CAVEAT: no policy passages retrieved — policy guidance unavailable")
        if not prior_case_results:
            caveats.append("PRECEDENT CAVEAT: no prior-case records retrieved — precedent coverage unavailable")

        caveat_section = "\n".join(f"  - {c}" for c in caveats) if caveats else "  None."

        # Assemble triage summary
        triage_lines = []
        for row in triage_table:
            triage_lines.append(
                f"  [{row.get('priority', '?')}] {row.get('evidence_type', '?')}: "
                f"{row.get('triage_note', '')} "
                f"(source_ref: {row.get('source_ref', 'n/a')}, date: {row.get('submission_date', 'n/a')})"
            )
        triage_section = "\n".join(triage_lines) if triage_lines else "  (no evidence items)"

        # Assemble policy citations
        policy_lines = []
        for p in policy_results:
            policy_lines.append(
                f"  [{p.get('section_ref', 'n/a')}] v{p.get('policy_version', '?')} "
                f"({p.get('effective_date', 'n/a')}): {p.get('passage', '')[:200]}"
            )
        policy_section = "\n".join(policy_lines) if policy_lines else "  (no policy passages retrieved)"

        # Assemble precedent references
        precedent_lines = []
        for c in prior_case_results:
            precedent_lines.append(
                f"  [{c.get('anon_case_ref', 'n/a')}] {c.get('case_type', '?')}: "
                f"{c.get('evidence_pattern_summary', '')} — "
                f"outcome: {c.get('recorded_outcome', 'n/a')} — "
                f"policy: {c.get('applied_policy_sections', [])}"
            )
        precedent_section = "\n".join(precedent_lines) if precedent_lines else "  (no prior cases retrieved)"

        formatted_output = (
            f"{RESTRICTED_LABEL}\n"
            f"Case Type: {case_type}\n\n"
            f"LIMITATIONS AND CAVEATS\n{caveat_section}\n\n"
            f"EVIDENCE TRIAGE TABLE\n{triage_section}\n\n"
            f"POLICY REFERENCES\n{policy_section}\n\n"
            f"COMPARABLE CASE REFERENCES\n{precedent_section}\n\n"
            f"EVIDENCE BRIEFING\n{briefing_draft}\n\n"
            f"HUMAN DECISION NOTICE\n{NO_ADJUDICATION_NOTICE}\n"
        )

        emit_trace_event(
            "OutputNode_assembled",
            {
                "case_type": case_type,
                "output_length": len(formatted_output),
                "caveats_count": len(caveats),
            },
            state,
        )
        return {
            "formatted_output": formatted_output,
            "status": AgentStatus.SUCCESS.value,
        }
