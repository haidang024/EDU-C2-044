"""Graph — Cat 2 outer graph for EDU-C2-044."""

from __future__ import annotations

# Cat 2 — outer AgentBaseGraph wraps the inner domain workflow via GraphNode.
# S-1/S-2 gates live on the outer pre_process node (PreProcessNode).
# S-3 domain output gate lives on the outer post_process node (PostProcessNode).
# The inner graph (domain_workflow_graph.py) runs the domain steps:
#   authorization_verification → evidence_inventory_normalization →
#   policy_rag → prior_case_rag → evidence_triage_assembly →
#   briefing_draft → output_node
#
# No RAG or LLM node can execute before authorization succeeds.

from typing import TYPE_CHECKING, Any, ClassVar, cast

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.schemas.state import State

if TYPE_CHECKING:
    from src.graph.domain_workflow_graph import IntegrityTriageDomainWorkflowGraph


# Caller-facing text per stable workflow error code. Raw node error_log text
# names node classes and secret keys, so it must never be rendered into the
# chat window; the code is what support maps back to the detail kept on
# `workflow_error_detail`.
_WORKFLOW_ERROR_REASONS: dict[str, str] = {
    "CONFIGURATION_INVALID": (
        "This agent is not yet connected to the services it needs, so no triage briefing was produced."
    ),
    "AUTHORIZATION_DENIED": ("The requester is not authorised to run an academic integrity triage for this case."),
    "EVIDENCE_INCOMPLETE": ("The case does not yet have enough evidence on file to produce a triage briefing."),
    "OUTPUT_BLOCKED": ("The draft briefing did not pass the required content checks, so it was not released."),
    "WORKFLOW_FAILED": "The academic integrity triage could not be completed.",
}

_DEFAULT_WORKFLOW_ERROR_CODE = "WORKFLOW_FAILED"


def _classify_workflow_error(raw: str) -> str:
    """Map raw inner-graph error text onto a stable, caller-safe code."""
    lowered = raw.lower()
    if any(marker in lowered for marker in ("credential unavailable", "missingsecret", "required secret")):
        return "CONFIGURATION_INVALID"
    if any(marker in lowered for marker in ("authorization denied", "authorization not confirmed")):
        return "AUTHORIZATION_DENIED"
    if any(marker in lowered for marker in ("is empty", "not accepted", "exceeds")):
        return "EVIDENCE_INCOMPLETE"
    if any(marker in lowered for marker in ("gate blocked", "prohibited")):
        return "OUTPUT_BLOCKED"
    return _DEFAULT_WORKFLOW_ERROR_CODE


def _user_facing_reason(error_code: str) -> str:
    """Return text that is safe to show the caller for a workflow error code."""
    return _WORKFLOW_ERROR_REASONS.get(error_code, _WORKFLOW_ERROR_REASONS[_DEFAULT_WORKFLOW_ERROR_CODE])


class IntegrityTriageWorkflowGraphNode(GraphNode):
    """Wraps the inner integrity triage domain workflow; assigned to `main`."""

    # Fail fast — no safe partial/degraded briefing for an integrity review.
    # "handle" (not "propagate"): a propagated SubgraphError aborts the run
    # before merge_output(), so post_process never executes and the Marketplace
    # runner returns a bare RuntimeError with no reason. on_subgraph_error()
    # converts the failure into a domain field instead.
    error_strategy: ClassVar[str] = "handle"
    propagate_hitl: ClassVar[bool] = False
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, llm: object | None = None, config: dict | None = None) -> None:
        super().__init__()
        self._llm = llm
        self._config: dict = dict(config or {})
        self._config["llm"] = llm

    def get_subgraph(self) -> "IntegrityTriageDomainWorkflowGraph":
        from src.graph.domain_workflow_graph import IntegrityTriageDomainWorkflowGraph

        return IntegrityTriageDomainWorkflowGraph(config=self._parent_config())

    def extract_input(self, state: AgentState) -> str:
        return str(state.get("validated_input", state.get("user_input", "")))

    def execute(self, state: AgentState) -> dict[str, Any]:
        if state.get("input_error_message"):
            return {"status": AgentStatus.SUCCESS.value}
        return cast(dict[str, Any], super().execute(state))

    def on_subgraph_error(self, state: AgentState, error: Exception) -> dict[str, Any]:
        """Carry an inner failure as a domain field so the pipeline keeps running.

        Returning status=error here would route straight to finalize, skipping the
        post-process node; the Marketplace runner then drops `output` and the caller
        sees only "invocation did not succeed". post_process renders
        workflow_error_message into an actionable message instead.
        """
        error_log = getattr(error, "error_log", None) or []
        reasons = [str(e) for e in error_log if str(e).strip()]
        raw = reasons[-1] if reasons else ""
        # `raw` is node error_log text: it names the failing node class and the
        # exact secret key. That reached the caller's chat window verbatim, so
        # only a pre-authored description is rendered; the raw text stays on
        # workflow_error_detail, which is log-facing only.
        code = _classify_workflow_error(raw)
        return {
            "status": AgentStatus.SUCCESS.value,
            "workflow_error_code": code,
            "workflow_error_detail": raw,
            "workflow_error_message": _user_facing_reason(code),
        }

    def merge_output(self, state: AgentState, sub_result: dict) -> dict:
        return {
            "formatted_output": sub_result.get("formatted_output"),
            "briefing_draft": sub_result.get("briefing_draft"),
            "triage_table": sub_result.get("triage_table"),
            "policy_results": sub_result.get("policy_results"),
            "prior_case_results": sub_result.get("prior_case_results"),
            "evidence_inventory": sub_result.get("evidence_inventory"),
            "evidence_completeness_flags": sub_result.get("evidence_completeness_flags"),
            "authorization_status": sub_result.get("authorization_status"),
            "authorization_ref": sub_result.get("authorization_ref"),
            "policy_retrieval_provenance": sub_result.get("policy_retrieval_provenance"),
            "prior_case_retrieval_provenance": sub_result.get("prior_case_retrieval_provenance"),
            "audit_ref": sub_result.get("audit_ref"),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict:
        return dict(self._config)


class Graph(AgentBaseGraph):
    """Cat 2 outer graph — Academic Integrity Evidence Triage Agent (EDU-C2-044).

    Backbone: initialize → pre_process → main → post_process → finalize (fixed).
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config: dict = config or {}
        super().__init__(config=self._config)

    @property
    def name(self) -> str:
        return "EDU-C2-044"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects InitializeNode + FinalizeNode
        self._nodes["pre_process"] = PreProcessNode()
        self._nodes["main"] = IntegrityTriageWorkflowGraphNode(
            llm=self.config.get("llm"),
            config=self.config,
        )
        self._nodes["post_process"] = PostProcessNode(config=self.config)

    def get_output(self, state: AgentState) -> dict[str, Any]:
        output = cast(dict[str, Any], super().get_output(state))
        output["generation_mode"] = state.get("generation_mode")
        output["provider_error_message"] = state.get("provider_error_message")
        # Classification + raw cause for operators. `workflow_error_detail` is
        # deliberately absent from the rendered `output` string — it names node
        # classes and secret keys — but it must reach the audit log.
        output["workflow_error_code"] = state.get("workflow_error_code")
        output["workflow_error_detail"] = state.get("workflow_error_detail")
        _set_marketplace_guidance(output, state, "Academic integrity triage request")
        return output

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.


def _set_marketplace_guidance(output: dict[str, Any], state: AgentState, subject: str) -> None:
    context = state.get("input_context")
    message = state.get("input_error_message")
    if not (isinstance(context, dict) and "conversation_history" in context and message):
        return
    lines = [f"{subject} could not be processed.", "", f"Reason: {message}"]
    guidance = state.get("input_error_guidance")
    if isinstance(guidance, list) and guidance:
        lines.extend(["", "How to continue:"])
        lines.extend(f"- {item}" for item in guidance)
    output["output"] = "\n".join(lines)
