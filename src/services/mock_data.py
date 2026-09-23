"""AgentCore Platform v1.0"""

# Mock stubs for local/CI mock-mode runs.
# Uses synthetic/de-identified fixtures only — no production student data.

from __future__ import annotations

from typing import Any

# Synthetic officer registry: institution_id → set of authorized requester_refs
_MOCK_OFFICER_REGISTRY: dict[str, set[str]] = {
    "UNIV-001": {"officer-a1b2", "officer-c3d4", "officer-e5f6"},
    "UNIV-002": {"officer-g7h8"},
}


def stub_officer_is_authorized(requester_ref: str, institution_id: str) -> tuple[bool, str]:
    """Stub officer registry check — synthetic fixture, no real PII."""
    authorized_set = _MOCK_OFFICER_REGISTRY.get(institution_id, set())
    if requester_ref in authorized_set:
        return True, f"auth-mock-{institution_id}-approved"
    return False, f"auth-mock-{institution_id}-denied"


async def stub_retrieve_policy(
    case_type: str,
    evidence_types: list[str],
    max_results: int,
) -> list[dict[str, Any]]:
    """Stub policy corpus retrieval — synthetic policy passages."""
    passages = [
        {
            "section_ref": "AI-POLICY-3.2",
            "policy_version": "2025.1",
            "effective_date": "2025-01-01",
            "passage": (
                f"For cases of type '{case_type}', the institution requires submission "
                "of all primary evidence before a review panel convenes."
            ),
            "applicability_rationale": f"Applicable to {case_type} review process.",
        },
        {
            "section_ref": "AI-POLICY-4.1",
            "policy_version": "2025.1",
            "effective_date": "2025-01-01",
            "passage": (
                "All review proceedings must maintain confidentiality of case references "
                "and may not disclose student identity in interim reports."
            ),
            "applicability_rationale": "Confidentiality requirement — always applicable.",
        },
    ]
    return passages[:max_results]


async def stub_retrieve_prior_cases(
    case_type: str,
    evidence_pattern: list[str],
    max_results: int,
) -> list[dict[str, Any]]:
    """Stub prior-case corpus retrieval — synthetic anonymized precedents."""
    cases = [
        {
            "anon_case_ref": "CASE-ANON-0042",
            "case_type": case_type,
            "evidence_pattern_summary": ("Detection report + submission file present; " "prior warning record absent."),
            "recorded_outcome": "Referred to review panel — no disciplinary measure recorded at triage stage.",
            "applied_policy_sections": ["AI-POLICY-3.2", "AI-POLICY-4.1"],
        },
        {
            "anon_case_ref": "CASE-ANON-0078",
            "case_type": case_type,
            "evidence_pattern_summary": "Detection report only; submission file missing.",
            "recorded_outcome": "Incomplete record — evidence gathering extended.",
            "applied_policy_sections": ["AI-POLICY-3.2"],
        },
    ]
    return cases[:max_results]


async def stub_draft_briefing(
    case_type: str,
    evidence_inventory: list[dict[str, Any]],
    triage_table: list[dict[str, Any]],
    policy_results: list[dict[str, Any]],
    prior_case_results: list[dict[str, Any]],
    completeness_flags: dict[str, Any],
    output_language: str,
) -> str:
    """Stub LLM briefing draft — synthetic output, no student PII."""
    missing = completeness_flags.get("MISSING_REQUIRED", [])
    missing_note = f"Missing required evidence: {missing}. " if missing else ""
    policy_count = len(policy_results)
    precedent_count = len(prior_case_results)
    evidence_count = len(evidence_inventory)

    return (
        f"[MOCK BRIEFING — {output_language.upper()}] "
        f"Case type: {case_type}. "
        f"Evidence items reviewed: {evidence_count}. "
        f"{missing_note}"
        f"Policy passages retrieved: {policy_count}. "
        f"Comparable precedent records: {precedent_count}. "
        "This synthetic briefing is for testing purposes only and does not "
        "reflect any real case, student, or institutional record."
    )
