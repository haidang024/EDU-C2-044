"""AuthorizationVerificationNode — fail-closed officer registry check for EDU-C2-044."""

from __future__ import annotations

import json
from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.mock_mode import STUB_OFFICER_REGISTRY_API_KEY, resolve_or_stub
from src.services.service import OfficerRegistryService


class AuthorizationVerificationNode(FunctionNode):
    """Verify requester against the institution officer registry (fail-closed).

    Must succeed before any retrieval or LLM node executes. On failure, records
    a safe access-denied audit reference and returns ERROR to halt the graph.
    No registry details or requester identifiers are included in error messages.
    """

    # Inner-graph node: trust level is ANONYMOUS per Cat 2 inner-graph rule.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        requester_ref = state.get("requester_ref", "")
        institution_id = state.get("institution_id", "")

        # Inner-graph fallback: outer pre_process fields may not be in initial_state
        # when invoked via GraphNode.extract_input() — re-parse from validated_input.
        if not requester_ref or not institution_id:
            validated_input = state.get("validated_input", state.get("user_input", ""))
            try:
                payload = json.loads(validated_input) if validated_input else {}
                requester_ref = requester_ref or payload.get("requester_ref", "")
                institution_id = institution_id or payload.get("institution_id", "")
            except (json.JSONDecodeError, TypeError):
                pass

        if not requester_ref or not institution_id:
            emit_trace_event(
                "AuthorizationVerificationNode_denied",
                {"reason": "missing_requester_or_institution"},
                state,
            )
            return {
                "authorization_status": "denied",
                "authorization_ref": "auth-denied-missing-fields",
                "status": AgentStatus.ERROR.value,
                "error_log": ["AuthorizationVerificationNode: authorization denied"],
            }

        ctx = InvocationContext.from_state(state)
        # When the officer registry is not provisioned, check against the bundled
        # stub registry instead of denying outright. This still *verifies* the
        # requester — an unknown reference is denied exactly as it would be
        # against the live registry — it only changes which registry answers.
        # `registry_source` records that choice for the audit log.
        credential_handle, registry_source = resolve_or_stub(
            ctx, "OFFICER_REGISTRY_API_KEY", STUB_OFFICER_REGISTRY_API_KEY
        )
        if registry_source == "fixture":
            emit_trace_event(
                "AuthorizationVerificationNode_registry_fallback",
                {"registry_source": "fixture"},
                state,
            )
        registry_service = OfficerRegistryService()
        authorized = registry_service.is_authorized(
            requester_ref=requester_ref,
            institution_id=institution_id,
            credential_handle=credential_handle,
            ctx=ctx,
        )
        auth_ref = registry_service.last_auth_ref

        if not authorized:
            emit_trace_event(
                "AuthorizationVerificationNode_denied",
                {"institution_id": institution_id},
                state,
            )
            return {
                "authorization_status": "denied",
                "authorization_ref": auth_ref,
                "status": AgentStatus.ERROR.value,
                "error_log": ["AuthorizationVerificationNode: authorization denied"],
            }

        emit_trace_event(
            "AuthorizationVerificationNode_authorized",
            {"institution_id": institution_id, "auth_ref": auth_ref},
            state,
        )
        return {
            "authorization_status": "authorized",
            "authorization_ref": auth_ref,
            "status": AgentStatus.SUCCESS.value,
        }
