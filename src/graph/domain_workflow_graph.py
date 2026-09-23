"""IntegrityTriageDomainWorkflowGraph — inner BaseGraph for EDU-C2-044."""

from __future__ import annotations

# Inner graph for the Cat 2 integrity triage domain workflow.
# Instantiated by IntegrityTriageWorkflowGraphNode.get_subgraph() in graph.py.
# ONLY accepted path for the inner graph — do NOT place under src/subagents/.
#
# Pipeline (conditional topology — authorization failure halts immediately):
#   START → authorization_verification
#         → [authorized] evidence_inventory_normalization
#         → policy_rag → prior_case_rag
#         → evidence_triage_assembly → briefing_draft → output_node → END
#         → [denied/error] END  (via route())

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_status import AgentStatus
from src.nodes.authorization_verification_node import AuthorizationVerificationNode
from src.nodes.briefing_draft_node import BriefingDraftNode
from src.nodes.evidence_inventory_normalization_node import EvidenceInventoryNormalizationNode
from src.nodes.evidence_triage_assembly_node import EvidenceTriageAssemblyNode
from src.nodes.output_node import OutputNode
from src.nodes.policy_rag_node import PolicyRAGNode
from src.nodes.prior_case_rag_node import PriorCaseRAGNode
from src.schemas.state import State


class IntegrityTriageDomainWorkflowGraph(BaseGraph):
    """Inner graph for the academic integrity triage domain workflow.

    Pipeline:
        START → authorization_verification
              → [authorized] evidence_inventory_normalization
              → policy_rag → prior_case_rag → evidence_triage_assembly
              → briefing_draft → output_node → END
              → [denied/error] END
    """

    @property
    def name(self) -> str:
        return "edu_c2_044_integrity_triage_domain_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        """No mandatory config keys for the inner graph."""
        pass

    def register_nodes(self) -> None:
        """No super() call — BaseGraph.register_nodes() is abstract."""
        self._nodes["authorization_verification"] = AuthorizationVerificationNode()
        self._nodes["evidence_inventory_normalization"] = EvidenceInventoryNormalizationNode()
        self._nodes["policy_rag"] = PolicyRAGNode()
        self._nodes["prior_case_rag"] = PriorCaseRAGNode()
        self._nodes["evidence_triage_assembly"] = EvidenceTriageAssemblyNode()
        self._nodes["briefing_draft"] = BriefingDraftNode(
            llm=self.config.get("llm"),
            config=self.config,
        )
        self._nodes["output_node"] = OutputNode()

    def add_edges(self) -> None:
        """Conditional topology: authorization failure routes directly to END."""
        self._sg.add_edge(START, "authorization_verification")
        self._sg.add_conditional_edges("authorization_verification", self.route_after_auth)
        self._sg.add_edge("evidence_inventory_normalization", "policy_rag")
        self._sg.add_edge("policy_rag", "prior_case_rag")
        self._sg.add_edge("prior_case_rag", "evidence_triage_assembly")
        self._sg.add_edge("evidence_triage_assembly", "briefing_draft")
        self._sg.add_edge("briefing_draft", "output_node")
        self._sg.add_edge("output_node", END)

    def route_after_auth(self, state: State) -> str:
        """Route to evidence normalization on success; END on authorization failure."""
        if state.get("authorization_status") == "authorized" and state.get("status") != AgentStatus.ERROR.value:
            return "evidence_inventory_normalization"
        return str(END)

    def route(self, state: State) -> str:
        """Required by BaseGraph ABC — used for general error routing."""
        return str(END) if state.get("status") == AgentStatus.ERROR.value else "output_node"

    def get_output(self, state: State) -> dict:
        """Shape the sub_result dict returned to IntegrityTriageWorkflowGraphNode.merge_output()."""
        return {
            "formatted_output": state.get("formatted_output"),
            "briefing_draft": state.get("briefing_draft"),
            "triage_table": state.get("triage_table"),
            "policy_results": state.get("policy_results"),
            "prior_case_results": state.get("prior_case_results"),
            "evidence_inventory": state.get("evidence_inventory"),
            "evidence_completeness_flags": state.get("evidence_completeness_flags"),
            "authorization_status": state.get("authorization_status"),
            "authorization_ref": state.get("authorization_ref"),
            "policy_retrieval_provenance": state.get("policy_retrieval_provenance"),
            "prior_case_retrieval_provenance": state.get("prior_case_retrieval_provenance"),
            "audit_ref": state.get("audit_ref"),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
            # error_log must cross the subgraph boundary: GraphNode builds
            # SubgraphError from sub_result["error_log"], and an empty list
            # leaves the caller with a generic, unactionable reason.
            "error_log": state.get("error_log", []),
        }
