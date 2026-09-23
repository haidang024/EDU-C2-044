# Template Design Specification

Status: completed
Date: 2026-07-16
Reviewer: [TBD]

## Position in AgentCore Architecture

- **Agent Class**: `Graph`
- **L1 Base**: AgentBaseGraph (outer) — Cat 2, with `GraphNode` composition wrapping an inner `BaseGraph`
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

### Cat Judgment

Cat 2 — the agent orchestrates a fixed, ordered sequence of domain steps to
accomplish one specific job-to-be-done: producing a RESTRICTED evidence briefing
for an authorized academic integrity review officer. It is not a single reusable
capability (not Cat 1) and does not run a self-directed think→act→observe loop
(not Cat 3): every step executes in a deterministic order following fail-closed
authorization.

### Composition Pattern

Outer graph keeps the standard 5-node backbone (`initialize → pre_process → main →
{route} → post_process → finalize`). The `main` slot is
`IntegrityTriageWorkflowGraphNode` (`GraphNode` subclass), which wraps an inner
`BaseGraph` — `src/graph/domain_workflow_graph.py`. The inner graph implements the
domain-specific steps with conditional routing: authorization failure halts the
graph immediately at `authorization_verification`, preventing any retrieval or LLM
call from executing. S-1/S-2 gates live on the outer `pre_process`; S-3 domain
output gate lives on the outer `post_process`.

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | Framework default: assigns trace/correlation IDs | — | `trace_id`, `correlation_id` | InitializeNode (default) |
| pre_process | S-1 input validate: reject student PII; parse/validate case intake JSON; validate case_type, audience, language | `user_input` | `validated_input`, `case_ref`, `case_type`, `evidence_bundle_ref`, `requester_ref`, `institution_id`, `audience`, `output_language`, `status` | `PreProcessNode` (`FunctionNode`) |
| main | Runs inner domain workflow via `GraphNode`; receives runtime config and optional injected LLM client; merges all domain results | `validated_input` + intake fields | `formatted_output`, `briefing_draft`, `triage_table`, `policy_results`, `prior_case_results`, `evidence_inventory`, `evidence_completeness_flags`, `authorization_status`, `authorization_ref`, `audit_ref`, `status` | `IntegrityTriageWorkflowGraphNode` (`GraphNode`, `VERIFIED_EXTERNAL`) |
| post_process | S-3 output gate: block adjudication/sanction/notification language; append RESTRICTED label and no-adjudication notice | `formatted_output` | `result`, `status` | `PostProcessNode` (`FunctionNode`) |
| finalize | Framework default: shapes final output envelope | `result` | `output` | FinalizeNode (default) |

**Inner graph nodes** (`src/graph/domain_workflow_graph.py`, `BaseGraph` topology):

| Node | Responsibility | Input | Output |
|------|----------------|-------|--------|
| authorization_verification | Verify requester against institution officer registry; fail-closed before any retrieval/LLM | `requester_ref`, `institution_id` | `authorization_status`, `authorization_ref` |
| evidence_inventory_normalization | Normalize evidence items to approved fields; apply required-evidence checklist per case type; assign PRIMARY/SUPPORTING/ANCILLARY priorities deterministically; no LLM | `case_type`, `evidence_bundle_ref`, `validated_input` | `evidence_inventory`, `evidence_completeness_flags` |
| policy_rag | Retrieve policy passages from policy collection only; enforces collection allowlisting and retrieval bounds | `case_type`, `evidence_inventory`, `authorization_status` | `policy_results`, `policy_retrieval_provenance` |
| prior_case_rag | Retrieve pre-anonymized precedents from prior-case collection only; never crosses into policy collection; validates/redacts identifier patterns | `case_type`, `evidence_inventory`, `authorization_status` | `prior_case_results`, `prior_case_retrieval_provenance` |
| evidence_triage_assembly | Assemble deterministic triage table; no LLM; no misconduct/credibility inference | `evidence_inventory`, `evidence_completeness_flags`, `case_type` | `triage_table` |
| briefing_draft | One bounded LLM call grounded in structured inventory, policy, prior-case, and triage; every claim requires source provenance | `evidence_inventory`, `triage_table`, `policy_results`, `prior_case_results`, `completeness_flags` | `briefing_draft` |
| output_node | Domain output gate: block adjudication/sanction/notification/identifier language; prepend RESTRICTED label; assemble final briefing package with caveats and citations | `briefing_draft`, `triage_table`, `policy_results`, `prior_case_results` | `formatted_output` |

### Data Flow

```
Outer:
START → initialize → pre_process → main → {route} → post_process → finalize → END
                                              ↓ (retry, max 3)
                                          pre_process

Inner (main slot, IntegrityTriageWorkflowGraphNode wraps):
START → authorization_verification
      → [authorized] evidence_inventory_normalization
      → policy_rag → prior_case_rag
      → evidence_triage_assembly → briefing_draft → output_node → END
      → [denied/error] END
```

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `user_input` | `str` | Raw case intake JSON (max 4000 chars, no student PII) | Yes (framework) |
| `validated_input` | `str` | S-1-validated input; no student identifiers | Yes (set by pre_process) |
| `case_ref` | `str` | Sanitized/anonymized case reference (no student PII) | Yes |
| `case_type` | `str` | e.g. "plagiarism", "contract_cheating", "exam_misconduct" | Yes |
| `evidence_bundle_ref` | `str` | Reference to submitted evidence bundle (no PII) | Yes |
| `requester_ref` | `str` | Anonymized officer reference | Yes |
| `institution_id` | `str` | Institution identifier from config | Yes |
| `audience` | `str` | Intended audience label, e.g. "integrity_officer" | Yes |
| `output_language` | `str` | Language code, e.g. "en" | Yes |
| `authorization_status` | `str` | "authorized" or "denied" | Yes (inner graph) |
| `authorization_ref` | `str` | Safe audit reference for access decision | Yes (inner graph) |
| `evidence_inventory` | `list` | Normalized evidence items (no student identifiers) | Yes (inner graph) |
| `evidence_completeness_flags` | `dict` | `{"MISSING_REQUIRED": [...], "INCOMPLETE_RECORD": bool}` | Yes (inner graph) |
| `policy_results` | `list` | Policy passage dicts (allowlisted fields only) | Yes (inner graph) |
| `policy_retrieval_provenance` | `dict` | Collection, version, timestamp, caveat | Yes (inner graph) |
| `prior_case_results` | `list` | Anonymized precedent dicts (allowlisted fields only) | Yes (inner graph) |
| `prior_case_retrieval_provenance` | `dict` | Collection, timestamp, caveat | Yes (inner graph) |
| `triage_table` | `list` | Deterministic triage rows | Yes (inner graph) |
| `briefing_draft` | `str` | LLM-drafted restricted briefing text | Yes (inner graph) |
| `formatted_output` | `str` | Final RESTRICTED output with label and caveats | Yes (inner graph) |
| `result` | `str` | Post-process output with no-adjudication notice | Yes (outer post_process) |
| `audit_ref` | `str` | Safe audit trace reference (no raw case data) | No |
| `status` | `str` | Node/pipeline status (`AgentStatus` value) | Yes |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No student names, student IDs, or contact details in any field
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)
- Prior-case data must be pre-anonymized before ingestion; `prior_case_results` holds only allowlisted fields

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, credential handle) — used in `authorization_verification_node`, `policy_rag_node`, `prior_case_rag_node`, `briefing_draft_node`
- [x] ConnectionPolicy (retry/timeout strategy) — runtime parameters in `config/config.yaml`
- [x] SecurityViolationError — raised by S-1/S-2 on student PII or adjudication language
- [x] S-2: `_extra_security_gate_input()` — on `PreProcessNode`: rejects student name/ID/email/number patterns, enforces 4000-char input limit
- [x] S-3: `_extra_security_gate_output()` — on `PostProcessNode`: blocks adjudication, sanction, grade-change, and student-notification language before final output
- [x] S-4: `emit_trace_event()` — at least one domain-specific event inside each `execute()`: `PreProcessNode_intake_validated`, `AuthorizationVerificationNode_authorized/denied`, `EvidenceInventoryNormalizationNode_normalized`, `PolicyRAGNode_retrieved`, `PriorCaseRAGNode_retrieved`, `EvidenceTriageAssemblyNode_assembled`, `BriefingDraftNode_drafted`, `OutputNode_assembled/blocked`, `PostProcessNode_output_gate_verified`

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass (`pre_process`, `post_process`, all inner-graph nodes) → framework `@final` gate always runs automatically; extended via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` (`main`/`IntegrityTriageWorkflowGraphNode`) → deliberate no-op; the outer `pre_process`/`post_process` already apply S-2/S-3 around the subgraph call
> - No custom `BaseNode` subclass used in this template

### Services

- **OfficerRegistryService** (`src/services/service.py`) — verifies requester against institution officer registry; accessed via `InvocationContext` in non-mock mode; mock stub uses synthetic officer fixtures
- **PolicyRAGService** — retrieves from the policy collection only; collection-allowlisted; accessed via `ctx.secrets.require("POLICY_RAG_API_KEY")`
- **PriorCaseRAGService** — retrieves from the prior-case collection only; never crosses into policy corpus; accessed via `ctx.secrets.require("PRIOR_CASE_RAG_API_KEY")`
- **BriefingDraftService** — shared platform LLM provider; accessed via `ctx.secrets.require("LLM_API_KEY")`; one bounded call grounded solely in structured inputs

### Corpus Separation

Two distinct collections are configured and enforced:
- **Policy corpus** (lower sensitivity): institutional policies, procedural rules, applicable regulations. Accessed only by `PolicyRAGNode`.
- **Prior-case corpus** (restricted, pre-anonymized): historical anonymized precedent records. Accessed only by `PriorCaseRAGNode`. Data must be anonymized before ingestion; no student-traceable identifiers permitted.

Cross-collection access is prohibited: each RAG node is bound to a single collection configuration key and verified by test (PB-10).

### Composition Pattern

- **Pattern**: GraphNode (subgraph) — `main` slot wraps inner `BaseGraph`
- **Composition target**: `src/graph/domain_workflow_graph.py` — `IntegrityTriageDomainWorkflowGraph(BaseGraph)`
- **Error propagation strategy**: `propagate` — any inner-graph node failure raises `SubgraphError` and fails the outer invocation; no partial/degraded briefing for an integrity review
- **`propagate_hitl`**: `False` (default) — no HITL in this template
- **Runtime config**: static registry metadata is in `config/agent.yaml`; `config/config.yaml` is passed through `Graph(config=...)` to the composite node and inner graph
- **LLM injection contract**: the server reads optional `ANTHROPIC_API_KEY` with `.get()` and the outer graph constructs `IntegrityTriageWorkflowGraphNode(llm=self.config.get("llm"), config=self.config)`; the existing fail-closed `LLM_API_KEY` connector remains the domain generation boundary

### HITL

`config/config.yaml` sets `hitl.enabled: false`. Human review happens outside
the agent boundary — the authorized officer reviews the RESTRICTED briefing document
offline. No `interrupt()` calls, no `memory_enabled: true` requirement.

## Sequence / Failure Diagrams

### Success path
```
pre_process (S-1/S-2) → authorization_verification (fail-closed)
  → evidence_inventory_normalization
  → policy_rag (policy collection only)
  → prior_case_rag (prior-case collection only)
  → evidence_triage_assembly (deterministic, no LLM)
  → briefing_draft (1 bounded LLM call)
  → output_node (domain gate, RESTRICTED label)
  → post_process (S-3 gate, no-adjudication notice)
```

### Authorization failure path
```
pre_process → authorization_verification (status=denied) → END
(zero policy retrieval, zero prior-case retrieval, zero LLM call, zero briefing output)
```

### RAG no-result path
```
... → policy_rag (no results) → prior_case_rag (no results)
  → evidence_triage_assembly → briefing_draft
  → output_node (POLICY CAVEAT + PRECEDENT CAVEAT appended)
```

### Output gate block path
```
... → briefing_draft → output_node (adjudication language detected → ERROR)
  → post_process not reached → no briefing output
```

## Trace-Event Map

| Node | Event name | Payload (safe fields only) |
|------|-----------|---------------------------|
| PreProcessNode | `PreProcessNode_intake_validated` | `case_type`, `institution_id`, `audience` |
| AuthorizationVerificationNode | `AuthorizationVerificationNode_authorized` | `institution_id`, `auth_ref` |
| AuthorizationVerificationNode | `AuthorizationVerificationNode_denied` | `institution_id`, `reason` |
| EvidenceInventoryNormalizationNode | `EvidenceInventoryNormalizationNode_normalized` | `case_type`, `item_count`, `incomplete_record`, `evidence_bundle_ref` |
| PolicyRAGNode | `PolicyRAGNode_retrieved` | `case_type`, `result_count`, `collection` |
| PriorCaseRAGNode | `PriorCaseRAGNode_retrieved` | `case_type`, `result_count`, `collection` |
| EvidenceTriageAssemblyNode | `EvidenceTriageAssemblyNode_assembled` | `case_type`, `triage_row_count`, `incomplete_record` |
| BriefingDraftNode | `BriefingDraftNode_drafted` | `case_type`, `policy_result_count`, `prior_case_count`, `draft_length` |
| OutputNode | `OutputNode_assembled` | `case_type`, `output_length`, `caveats_count` |
| OutputNode | `OutputNode_blocked` | `reason`, `snippet_preview` |
| PostProcessNode | `PostProcessNode_output_gate_verified` | `output_length` |

## Data Classifications

| Data | Classification | Handling |
|------|---------------|---------|
| Case reference | Anonymized (no student PII) | Carried through state; never in traces raw |
| Evidence bundle ref | Opaque reference | Carried through state only |
| Policy passages | Lower sensitivity | Allowlisted fields in state; section_ref + passage only |
| Prior-case records | Restricted (pre-anonymized) | Allowlisted fields; identifier patterns redacted before state |
| Briefing output | RESTRICTED | Labeled; only released after S-3 gate and adjudication-language check |
| LLM/RAG credentials | Confidential | `ctx.secrets.require()` only; never in state or traces |

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: `framework.*` and `shared.*` only

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | **AgentBaseGraph** | Fixed deterministic 8-step pipeline with no self-directed reasoning loop — Cat 2, not Cat 3 |
| Composition pattern | Flat nodes on outer backbone | GraphNode wrapping inner BaseGraph | **GraphNode + inner BaseGraph** | Outer backbone has 3 domain slots; the 6+ inner domain steps need custom topology including conditional authorization routing |
| Where S-1/S-3 gates live | Inside inner graph | On outer pre_process/post_process | **Outer pre_process/post_process** | Security-critical gates remain on backbone nodes the framework instruments directly; not hidden inside subgraph error-handling |
| Authorization placement | After retrieval | Before any retrieval/LLM | **Before any retrieval/LLM** | Fail-closed design: zero policy/prior-case retrieval and zero LLM call on unauthorized requests |
| Policy vs prior-case corpus | Single unified corpus | Separate collections with separate access nodes | **Separate collections** | Policy corpus (lower sensitivity) and prior-case corpus (restricted, pre-anonymized) have different sensitivity levels and must never be cross-queried |
| `error_strategy` for `IntegrityTriageWorkflowGraphNode` | `propagate` | `handle` | **propagate** | An integrity review briefing has no safe partial/degraded output — any inner failure must fail the whole invocation |
| HITL | Enabled (`interrupt()` before output) | Disabled — human review outside agent | **Disabled** | Human review of the RESTRICTED briefing happens offline by the authorized officer; no in-graph pause/resume confidence-threshold trigger |
