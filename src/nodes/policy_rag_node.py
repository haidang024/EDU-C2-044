"""PolicyRAGNode — retrieves policy passages from the institutional policy corpus."""

from __future__ import annotations

import asyncio
from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.mock_mode import STUB_POLICY_RAG_API_KEY, resolve_or_stub
from src.services.service import PolicyRAGService

# Allowlisted fields returned from policy retrieval — no raw credentials or PII.
POLICY_ALLOWLISTED_FIELDS = {"section_ref", "policy_version", "effective_date", "passage", "applicability_rationale"}

MAX_POLICY_RESULTS = 5


class PolicyRAGNode(FunctionNode):
    """Retrieve policy passages from the configured policy collection only.

    Runs only after authorization. Enforces collection allowlisting, retrieval
    bounds, and treats retrieved content as untrusted (no prompt injection path).
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        authorization_status = state.get("authorization_status", "")
        if authorization_status != "authorized":
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PolicyRAGNode: authorization not confirmed — aborting retrieval"],
            }

        case_type = state.get("case_type", "")
        evidence_inventory = state.get("evidence_inventory", [])
        evidence_types = list(
            {item.get("evidence_type", "") for item in evidence_inventory if item.get("evidence_type")}
        )

        ctx = InvocationContext.from_state(state)
        # Retrieval connector: fall back to the bundled stub corpus when it is
        # not provisioned so the briefing still completes. `policy_source`
        # records which corpus answered, for the audit log only.
        credential_handle, policy_source = resolve_or_stub(ctx, "POLICY_RAG_API_KEY", STUB_POLICY_RAG_API_KEY)

        service = PolicyRAGService()
        try:
            raw_results = asyncio.run(
                service.retrieve_policy(
                    case_type=case_type,
                    evidence_types=evidence_types,
                    credential_handle=credential_handle,
                    max_results=MAX_POLICY_RESULTS,
                )
            )
        except NotImplementedError as exc:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"PolicyRAGNode: {exc}"],
            }

        # Allowlist fields — treat retrieved content as untrusted
        filtered = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            safe = {k: v for k, v in item.items() if k in POLICY_ALLOWLISTED_FIELDS}
            filtered.append(safe)

        provenance = {
            "collection": service.collection_name,
            "policy_version": service.policy_version,
            "retrieved_count": len(filtered),
            "caveat": "no_results" if not filtered else None,
        }

        emit_trace_event(
            "PolicyRAGNode_retrieved",
            {
                "case_type": case_type,
                "result_count": len(filtered),
                "collection": service.collection_name,
            },
            state,
        )
        return {
            "policy_results": filtered,
            "policy_retrieval_provenance": provenance,
            # Operator-facing: "live" or "fixture". The briefing is identical
            # either way, so this is the only signal distinguishing them.
            "policy_source": policy_source,
            "status": AgentStatus.SUCCESS.value,
        }
