"""PriorCaseRAGNode — retrieves anonymized precedents from the prior-case corpus."""

from __future__ import annotations

import asyncio
import re
from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.mock_mode import STUB_PRIOR_CASE_RAG_API_KEY, resolve_or_stub
from src.services.service import PriorCaseRAGService

# Allowlisted fields from prior-case retrieval — anonymized precedents only.
PRIOR_CASE_ALLOWLISTED_FIELDS = {
    "anon_case_ref",
    "case_type",
    "evidence_pattern_summary",
    "recorded_outcome",
    "applied_policy_sections",
}

# Patterns that may indicate unanonymized identifiers — redacted before state entry.
_IDENTIFIER_PATTERNS = (
    re.compile(r"\b[A-Z]{1,3}\d{6,}\b"),  # student ID patterns e.g. AB123456
    re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),  # email addresses
)

MAX_PRIOR_CASE_RESULTS = 3


def _redact_identifiers(text: str) -> str:
    """Redact identifier-like patterns from retrieved text."""
    for pattern in _IDENTIFIER_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


class PriorCaseRAGNode(FunctionNode):
    """Retrieve anonymized precedent records from the prior-case corpus only.

    Never crosses into the policy collection. Validates/redacts identifier-like
    patterns before state. Missing prior cases become coverage caveats.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        authorization_status = state.get("authorization_status", "")
        if authorization_status != "authorized":
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PriorCaseRAGNode: authorization not confirmed — aborting retrieval"],
            }

        case_type = state.get("case_type", "")
        evidence_inventory = state.get("evidence_inventory", [])
        evidence_pattern = [item.get("evidence_type", "") for item in evidence_inventory]

        ctx = InvocationContext.from_state(state)
        # Retrieval connector: fall back to the bundled stub corpus when it is
        # not provisioned so the briefing still completes. `prior_case_source`
        # records which corpus answered, for the audit log only.
        credential_handle, prior_case_source = resolve_or_stub(
            ctx, "PRIOR_CASE_RAG_API_KEY", STUB_PRIOR_CASE_RAG_API_KEY
        )

        emit_trace_event(
            "PriorCaseRAGNode_retrieved",
            {"case_type": case_type, "collection": PriorCaseRAGService.collection_name},
            state,
        )
        service = PriorCaseRAGService()
        try:
            raw_results = asyncio.run(
                service.retrieve_prior_cases(
                    case_type=case_type,
                    evidence_pattern=evidence_pattern,
                    credential_handle=credential_handle,
                    max_results=MAX_PRIOR_CASE_RESULTS,
                )
            )
        except NotImplementedError as exc:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"PriorCaseRAGNode: {exc}"],
            }

        # Allowlist fields and redact any residual identifiers
        filtered = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            safe = {}
            for k, v in item.items():
                if k not in PRIOR_CASE_ALLOWLISTED_FIELDS:
                    continue
                if isinstance(v, str):
                    v = _redact_identifiers(v)
                elif isinstance(v, list):
                    v = [_redact_identifiers(s) if isinstance(s, str) else s for s in v]
                safe[k] = v
            filtered.append(safe)

        provenance = {
            "collection": service.collection_name,
            "retrieved_count": len(filtered),
            "caveat": "no_results" if not filtered else "poor_coverage" if len(filtered) < 2 else None,
        }
        return {
            "prior_case_results": filtered,
            "prior_case_retrieval_provenance": provenance,
            # Operator-facing: "live" or "fixture". The briefing is identical
            # either way, so this is the only signal distinguishing them.
            "prior_case_source": prior_case_source,
            "status": AgentStatus.SUCCESS.value,
        }
