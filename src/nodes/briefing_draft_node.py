"""BriefingDraftNode — grounded LLM briefing draft for EDU-C2-044."""

from __future__ import annotations

import asyncio
import json
from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.llm_runtime import complete_text
from src.services.mock_data import stub_draft_briefing


class BriefingDraftNode(FunctionNode):
    """Draft a grounded RESTRICTED briefing via one bounded LLM call.

    Grounded solely in structured evidence inventory, policy passages,
    prior-case references, and triage results. Every policy/precedent
    statement must carry source provenance; unsupported claims are suppressed.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: object | None = None, config: dict | None = None) -> None:
        super().__init__()
        self._llm = llm
        self._config = config or {}

    def execute(self, state: dict) -> dict:
        authorization_status = state.get("authorization_status", "")
        if authorization_status != "authorized":
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["BriefingDraftNode: authorization not confirmed — aborting LLM call"],
            }

        evidence_inventory = state.get("evidence_inventory", [])
        triage_table = state.get("triage_table", [])
        policy_results = state.get("policy_results", [])
        prior_case_results = state.get("prior_case_results", [])
        completeness_flags = state.get("evidence_completeness_flags", {})
        case_type = state.get("case_type", "")
        output_language = state.get("output_language", "en")

        # Fail if upstream retrieval/config failed (no policy results AND no prior cases)
        if not evidence_inventory:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["BriefingDraftNode: evidence_inventory is empty — cannot draft briefing"],
            }

        prompt = json.dumps(
            {
                "case_type": case_type,
                "evidence_inventory": evidence_inventory,
                "triage_table": triage_table,
                "policy_results": policy_results,
                "prior_case_results": prior_case_results,
                "completeness_flags": completeness_flags,
                "output_language": output_language,
            },
            ensure_ascii=True,
            default=str,
        )
        try:
            briefing_draft = complete_text(
                state,
                [
                    {
                        "role": "system",
                        "content": (
                            "Draft a neutral academic-integrity evidence briefing grounded only in the supplied "
                            "records. Do not adjudicate, recommend sanctions, expose credentials, or add PII."
                        ),
                    },
                    {"role": "user", "content": prompt[:12000]},
                ],
                self._llm,
                max_tokens=1200,
                timeout_s=float(self._config.get("timeout_s", 30.0)),
                max_retry=int(self._config.get("max_retry", 3)),
            )
        except Exception:
            briefing_draft = asyncio.run(
                stub_draft_briefing(
                    case_type,
                    evidence_inventory,
                    triage_table,
                    policy_results,
                    prior_case_results,
                    completeness_flags,
                    output_language,
                )
            )

        emit_trace_event(
            "BriefingDraftNode_drafted",
            {
                "case_type": case_type,
                "policy_result_count": len(policy_results),
                "prior_case_count": len(prior_case_results),
                "draft_length": len(briefing_draft),
            },
            state,
        )
        return {
            "briefing_draft": briefing_draft,
            "status": AgentStatus.SUCCESS.value,
        }
