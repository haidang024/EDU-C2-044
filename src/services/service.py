"""AgentCore Platform v1.0"""

# Service layer: domain queries, external API wrappers, data aggregation.
# Must NOT contain business logic, routing, or credentials.
# Nodes call this; this calls shared/services/ for external integrations.

from __future__ import annotations

from typing import Any

from src.services.mock_mode import (
    STUB_OFFICER_REGISTRY_API_KEY,
    STUB_POLICY_RAG_API_KEY,
    STUB_PRIOR_CASE_RAG_API_KEY,
    STUB_LLM_API_KEY,
)


class OfficerRegistryService:
    """Verifies a requester reference against the institution officer registry."""

    def __init__(self) -> None:
        self.last_auth_ref: str = ""

    def is_authorized(
        self,
        requester_ref: str,
        institution_id: str,
        credential_handle: str = "",
        ctx: Any = None,
    ) -> bool:
        """Return True if the requester is authorized for the given institution.

        Args:
            requester_ref: Anonymized officer reference.
            institution_id: Institution identifier from config.
            credential_handle: Opaque handle from InvocationContext.secrets.require().
            ctx: InvocationContext (for credential resolution in non-mock mode).

        Returns:
            True if authorized; False otherwise.
        """
        if credential_handle == STUB_OFFICER_REGISTRY_API_KEY:
            from src.services.mock_data import stub_officer_is_authorized

            result, ref = stub_officer_is_authorized(requester_ref, institution_id)
            self.last_auth_ref = ref
            return result
        raise NotImplementedError(
            "OfficerRegistryService.is_authorized: not yet wired. "
            "Wire shared/services/officer_registry in the next sprint."
        )


class PolicyRAGService:
    """Retrieves policy passages from the configured institutional policy collection."""

    collection_name: str = "policy_corpus"
    policy_version: str = "unknown"

    async def retrieve_policy(
        self,
        case_type: str,
        evidence_types: list[str],
        credential_handle: str,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve policy passages bounded to the policy collection only.

        Args:
            case_type: Normalized case type for query construction.
            evidence_types: Present evidence types for bounded query.
            credential_handle: Opaque handle from InvocationContext.secrets.require().
            max_results: Maximum number of passages to retrieve.

        Returns:
            List of policy passage dicts (allowlisted fields only).
        """
        if credential_handle == STUB_POLICY_RAG_API_KEY:
            from src.services.mock_data import stub_retrieve_policy

            results = await stub_retrieve_policy(case_type, evidence_types, max_results)
            self.policy_version = "mock-v1.0"
            return results
        raise NotImplementedError(
            "PolicyRAGService.retrieve_policy: not yet wired. "
            "Wire shared/services/vector_rag with policy collection in the next sprint."
        )


class PriorCaseRAGService:
    """Retrieves pre-anonymized precedent records from the prior-case corpus."""

    collection_name: str = "prior_case_corpus"

    async def retrieve_prior_cases(
        self,
        case_type: str,
        evidence_pattern: list[str],
        credential_handle: str,
        max_results: int = 3,
    ) -> list[dict[str, Any]]:
        """Retrieve anonymized prior-case records from the prior-case collection only.

        Never crosses collection boundaries into the policy corpus.

        Args:
            case_type: Case type for query construction.
            evidence_pattern: Normalized evidence types present.
            credential_handle: Opaque handle from InvocationContext.secrets.require().
            max_results: Maximum number of precedent records.

        Returns:
            List of anonymized precedent dicts (allowlisted fields only).
        """
        if credential_handle == STUB_PRIOR_CASE_RAG_API_KEY:
            from src.services.mock_data import stub_retrieve_prior_cases

            return await stub_retrieve_prior_cases(case_type, evidence_pattern, max_results)
        raise NotImplementedError(
            "PriorCaseRAGService.retrieve_prior_cases: not yet wired. "
            "Wire shared/services/vector_rag with prior_case collection in the next sprint."
        )


class BriefingDraftService:
    """Drafts the restricted evidence briefing via the shared platform LLM."""

    async def draft_briefing(
        self,
        case_type: str,
        evidence_inventory: list[dict[str, Any]],
        triage_table: list[dict[str, Any]],
        policy_results: list[dict[str, Any]],
        prior_case_results: list[dict[str, Any]],
        completeness_flags: dict[str, Any],
        output_language: str,
        credential_handle: str,
    ) -> str:
        """Draft the evidence briefing via one bounded LLM call.

        Args:
            case_type: Normalized case type.
            evidence_inventory: Normalized evidence items.
            triage_table: Deterministic triage rows.
            policy_results: Retrieved policy passages.
            prior_case_results: Anonymized prior-case references.
            completeness_flags: Missing/incomplete evidence flags.
            output_language: Language code for output.
            credential_handle: Opaque handle — never log or store.

        Returns:
            Drafted briefing text (pre-output-gate).
        """
        if credential_handle == STUB_LLM_API_KEY:
            from src.services.mock_data import stub_draft_briefing

            return await stub_draft_briefing(
                case_type,
                evidence_inventory,
                triage_table,
                policy_results,
                prior_case_results,
                completeness_flags,
                output_language,
            )
        raise NotImplementedError(
            "BriefingDraftService.draft_briefing: not yet wired. " "Wire shared/services/llm_client in the next sprint."
        )
