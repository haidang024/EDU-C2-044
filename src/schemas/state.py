"""AgentCore Platform v1.0"""

# ADR-005: State must be a flat TypedDict (see ADR-005 for the prohibited
# alternatives). LangGraph checkpoints use msgpack serialization, so only
# plain serializable fields are allowed. Do NOT add credentials or secrets.
#
# Privacy constraints:
#   - No raw student names, student IDs, or contact details in any field.
#   - case_ref must be an anonymized/sanitized identifier (no student PII).
#   - prior_case_results contains only pre-anonymized precedent fields.
#   - credentials, JWTs, and InvocationContext are never stored in state.

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Agent state for EDU-C2-044 academic integrity evidence triage.

    No student name / student ID / contact detail field exists anywhere in
    this schema — S-1 input validation rejects those before they ever reach
    State. Prior-case data must be pre-anonymized before ingestion.
    """

    input_error_message: str | None
    input_error_guidance: list[str]
    # Inner-workflow failure reason, carried as a domain field so the run
    # keeps a valid AgentStatus and still reaches the post-process node.
    workflow_error_message: str | None
    # Stable classification + the raw cause. Both MUST stay declared here:
    # LangGraph drops undeclared keys between nodes, which would lose the
    # failure before the post-process node can report it.
    # `workflow_error_detail` is log-facing only — it names node classes and
    # secret keys, so it is never rendered into the caller-visible output.
    workflow_error_code: str | None
    workflow_error_detail: str | None
    generation_mode: str | None
    provider_error_message: str | None

    # ── Intake / validated input ────────────────────────────────────────────
    validated_input: str  # S-1-validated input; no student identifiers
    case_ref: str  # sanitized/anonymized case reference (no student PII)
    case_type: str  # e.g. "plagiarism", "contract_cheating", "exam_misconduct"
    requester_ref: str  # anonymized officer reference (no personal email/name)
    institution_id: str  # institution identifier from config
    output_language: str  # e.g. "en", "ja"
    audience: str  # intended audience label, e.g. "integrity_officer"

    # ── Authorization ────────────────────────────────────────────────────────
    authorization_status: str  # "authorized" | "denied" | "pending"
    authorization_ref: str  # safe audit reference for the access decision

    # ── Evidence inventory ───────────────────────────────────────────────────
    evidence_bundle_ref: str  # reference to the submitted evidence bundle (no PII)
    evidence_inventory: list  # normalized evidence items; each item: safe dict only
    evidence_completeness_flags: dict  # {"MISSING_REQUIRED": [...], "INCOMPLETE_RECORD": bool}

    # ── Retrieval — policy corpus ────────────────────────────────────────────
    policy_results: list  # list of policy passage dicts (allowlisted fields only)
    policy_retrieval_provenance: dict  # collection name, version, retrieval timestamp

    # ── Retrieval — prior-case corpus ────────────────────────────────────────
    prior_case_results: list  # list of anonymized precedent dicts (allowlisted fields)
    prior_case_retrieval_provenance: dict  # collection name, retrieval timestamp
    # Which corpus answered each retrieval: "live" when the connector is
    # provisioned, "fixture" when the bundled stub corpus was used.
    # Operator-facing only — the rendered briefing is identical either way.
    policy_source: str | None
    prior_case_source: str | None

    # ── Triage ───────────────────────────────────────────────────────────────
    triage_table: list  # deterministic triage rows; each: safe dict

    # ── Briefing ─────────────────────────────────────────────────────────────
    briefing_draft: str  # LLM-drafted restricted briefing text
    formatted_output: str  # final RESTRICTED output with label and caveats
    result: str  # post_process output (formatted_output + review boundary)

    # ── Audit ────────────────────────────────────────────────────────────────
    audit_ref: str  # safe audit trace reference (no raw case data)
