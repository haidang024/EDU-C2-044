# Test Specification

## Test Strategy
- Coverage target: 80%
- Test types: Unit / Proof-of-Boundary / Integration

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict — no Pydantic/dataclass/credential fields | Type check pass; PB-2 scan 0 violations | Pass |
| TC-02 | SecurityViolationError fires on student PII input (student_id rejected) | Error raised via S-1/S-2 gate | Pass |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations | Pass |
| TC-04 | InvocationContext not stored in State | State scan: no InvocationContext type annotation | Pass |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start` / `node_complete` / `node_error` absent from `execute()` body | 0 duplicates |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides |
| TC-08 | `required_trust_level` enforced on PreProcessNode and PostProcessNode | Insufficient trust (ANONYMOUS) → refused (via `__call__()`, not `execute()` directly) | Pass |
| TC-09 | S-2: `_extra_security_gate_input()` non-trivial (PreProcessNode) | Rejects student_id/student_name/student_email patterns and oversized input | Pass |
| TC-10 | S-3: `_extra_security_gate_output()` non-trivial (PostProcessNode) | Blocks adjudication, sanction, grade-change, and student-notification language | Pass |
| TC-11 | S-4: at least one domain `emit_trace_event()` inside each `execute()` | Domain event emitted on every invocation path for all 9 nodes | ≥1 per node |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | Pass |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass | Pass |
| PB-3 | L1 → External service (registry/RAG/LLM, mock mode) | All services connect via service layer in mock mode | Mock data returned | Pass |
| PB-4 | Import isolation | No Level 0 imports in `src/` | AST scan: 0 violations | Pass |
| PB-5 | Checkpoint safety | Static state scan always runs; raw-ingress persistence assertion is conditional on checkpointing and framework ingress hooks | Static pass; persistence auto-waived while checkpointing is disabled | Conditional |
| PB-6 | Invoke execution order | `__call__()`: S-1 trust gate → S-4 `node_start` → S-2 `_security_gate_input` → `execute()` → S-3 `_security_gate_output` → S-4 `node_complete` for every node under `src/nodes/` | Order verified for all 9 nodes | Pass |
| PB-7 | HITL interrupt propagation *(conditional)* | `config/config.yaml` sets `hitl.enabled: false` | **Auto-waived — non-HITL** | Waived |
| PB-8 | Authorization fail-closed: unauthorized request produces zero retrieval/LLM/briefing | `requester_ref` not in officer registry | status=ERROR, `authorization_status`=denied, no `policy_results`, no `briefing_draft` | Pass |
| PB-9 | Authorized request routes correctly to evidence normalization | `requester_ref` in officer registry | `authorization_status`=authorized, flow continues to `evidence_inventory_normalization` | Pass |
| PB-10 | Policy queries route only to policy collection | `PolicyRAGNode` invoked | Traces show `collection=policy_corpus`; prior-case collection not accessed | Pass |
| PB-11 | Prior-case queries route only to prior-case collection | `PriorCaseRAGNode` invoked | Traces show `collection=prior_case_corpus`; policy collection not accessed | Pass |
| PB-12 | Cross-collection/config override rejected | Attempted override of collection name | Node uses configured collection name only; any override rejected | Pass |
| PB-13 | Student PII cannot appear in prompts, state snapshots, traces, or final output | Synthetic student identifiers injected in retrieved data | Redacted by `PriorCaseRAGNode`; absent from `prior_case_results` and final output | Pass |
| PB-14 | Adjudication/sanction/grade-change/notification language blocked | `briefing_draft` containing "found guilty" / "suspend" | `OutputNode` blocks output; `PostProcessNode` S-3 gate also blocks | Pass |
| PB-15 | Safe positive output includes RESTRICTED label, human-review boundary, citations, limitations | Valid authorized request in mock mode | Output contains RESTRICTED label, no-adjudication notice, policy section refs, anon_case_ref | Pass |
| PB-16 | Unsafe/malformed LLM output blocked by output gate | Mock `briefing_draft` with sanction language injected | `OutputNode` returns ERROR; `formatted_output` not set | Pass |

> **Pre-CoE gate checklist:** PB-1 through PB-6 are mandatory. PB-7 is auto-waived (no `hitl.enabled: true`). PB-8–PB-16 are EDU-C2-044 domain-specific boundary tests required by instructions #10 and #11.

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | PreProcessNode validates case intake with all required fields | Valid JSON `{case_ref, case_type, evidence_bundle_ref, requester_ref, institution_id}` | `validated_input` set, status SUCCESS | Pass |
| BL-02 | PreProcessNode rejects unsupported case_type | `case_type: "unknown_type"` | status ERROR | Pass |
| BL-03 | PreProcessNode rejects student_id in user_input | `user_input` containing `student_id` | SecurityViolationError via S-2 | Pass |
| BL-04 | PreProcessNode rejects oversized input | `user_input` > 4000 chars | SecurityViolationError via S-2 | Pass |
| BL-05 | PreProcessNode rejects empty input | `user_input: ""` | status ERROR | Pass |
| BL-06 | AuthorizationVerificationNode approves authorized officer (mock) | `requester_ref` in mock registry, `institution_id` matching | `authorization_status: "authorized"`, status SUCCESS | Pass |
| BL-07 | AuthorizationVerificationNode denies unknown officer | `requester_ref` not in mock registry | `authorization_status: "denied"`, status ERROR | Pass |
| BL-08 | AuthorizationVerificationNode denies when requester_ref missing | `requester_ref: ""` | status ERROR, authorization denied | Pass |
| BL-09 | EvidenceInventoryNormalizationNode normalizes valid evidence items | Evidence items with valid types | `evidence_inventory` populated, priorities assigned, status SUCCESS | Pass |
| BL-10 | EvidenceInventoryNormalizationNode maps unknown evidence type to "other" | `evidence_type: "new_type"` | `evidence_type: "other"`, `priority: "ANCILLARY"` | Pass |
| BL-11 | EvidenceInventoryNormalizationNode sets MISSING_REQUIRED for plagiarism without detection_report | `case_type: "plagiarism"`, no `detection_report` in items | `evidence_completeness_flags["MISSING_REQUIRED"]` contains `"detection_report"` | Pass |
| BL-12 | EvidenceInventoryNormalizationNode sorts PRIMARY before SUPPORTING before ANCILLARY | Mixed priority evidence items | `evidence_inventory` sorted by priority order | Pass |
| BL-13 | PolicyRAGNode retrieves policy passages in mock mode | Authorized state, `USE_MOCK=true` | `policy_results` populated, `policy_retrieval_provenance` set, status SUCCESS | Pass |
| BL-14 | PolicyRAGNode returns no-result caveat on empty retrieval | Mock returns empty list | `policy_retrieval_provenance["caveat"] = "no_results"`, status SUCCESS | Pass |
| BL-15 | PolicyRAGNode only includes allowlisted fields | Mock returns extra fields | Extra fields stripped; only `section_ref`, `policy_version`, `effective_date`, `passage`, `applicability_rationale` present | Pass |
| BL-16 | PriorCaseRAGNode retrieves anonymized precedents in mock mode | Authorized state, `USE_MOCK=true` | `prior_case_results` populated, status SUCCESS | Pass |
| BL-17 | PriorCaseRAGNode redacts identifier-like patterns from retrieved text | Retrieved text containing `AB123456` (student ID pattern) | Pattern replaced with `[REDACTED]` in `prior_case_results` | Pass |
| BL-18 | PriorCaseRAGNode only includes allowlisted fields | Mock returns extra fields | Only `anon_case_ref`, `case_type`, `evidence_pattern_summary`, `recorded_outcome`, `applied_policy_sections` present | Pass |
| BL-19 | EvidenceTriageAssemblyNode builds triage table with missing-required rows | Missing required evidence types | Triage table contains rows for missing types with `triage_note: "MISSING — required for this case type"` | Pass |
| BL-20 | EvidenceTriageAssemblyNode does not infer misconduct or credibility | Any valid inventory | Triage notes are mechanical (present/missing/incomplete) only; no misconduct language | Pass |
| BL-21 | BriefingDraftNode fails without prior authorization | `authorization_status: ""` | status ERROR, no LLM call | Pass |
| BL-22 | BriefingDraftNode fails on empty evidence_inventory | `evidence_inventory: []` | status ERROR | Pass |
| BL-23 | BriefingDraftNode drafts briefing in mock mode | Valid authorized state, `USE_MOCK=true` | `briefing_draft` populated, status SUCCESS | Pass |
| BL-24 | OutputNode assembles RESTRICTED output with caveats | Valid `briefing_draft`, completeness_flags with missing evidence | Output contains RESTRICTED label, caveat section, triage table, policy refs, precedent refs | Pass |
| BL-25 | OutputNode blocks briefing containing "found guilty" | `briefing_draft` with "found guilty" | status ERROR, `formatted_output` not set | Pass |
| BL-26 | OutputNode blocks briefing containing "suspend" | `briefing_draft` with "suspend the student" | status ERROR | Pass |
| BL-27 | OutputNode blocks briefing containing "notify student" | `briefing_draft` with "notify student" | status ERROR | Pass |
| BL-28 | OutputNode emits OutputNode_blocked trace on gate block | Blocked briefing | `OutputNode_blocked` trace event emitted | Pass |
| BL-29 | PostProcessNode appends RESTRICTED label and no-adjudication notice | Valid `formatted_output` | `result` contains HUMAN_REVIEW_NOTICE | Pass |
| BL-30 | PostProcessNode S-3 blocks adjudication language | `formatted_output` with "misconduct confirmed" | SecurityViolationError raised by `_extra_security_gate_output` | Pass |
| BL-31 | PostProcessNode returns ERROR on empty formatted_output | `formatted_output: ""` | status ERROR | Pass |
| BL-32 | mock_mode_enabled() resolves under USE_MOCK alone | `USE_MOCK=true`, `STG_MOCK_MODE` unset | True | Pass |
| BL-33 | mock_mode_enabled() resolves under STG_MOCK_MODE alone | `STG_MOCK_MODE=true`, `USE_MOCK` unset | True | Pass |
| BL-34 | mock_mode_enabled() is False when neither alias set | Both unset | False | Pass |
| BL-35 | End-to-end graph invoke in mock mode (VERIFIED_EXTERNAL trust) | Valid case intake JSON, `USE_MOCK=true` | status SUCCESS, `output` contains RESTRICTED label and no-adjudication notice | Pass |
| BL-36 | Inner graph falls back to `user_input` when `validated_input` absent | Inner graph invoked directly with only `user_input` set | `authorization_verification_node` reads `requester_ref` from parsed payload | Pass |

## Test Execution Summary
- Execution date: 2026-08-18
- Project suite: 89 collected — 86 passed, 0 failed, 3 conditionally skipped
- Proof-of-boundary suite: 14 collected — 11 passed, 0 failed, 3 conditionally skipped
- Lint / format / strict type check: Pass
- Stage 5 provisional invoke: Pass (HTTP 200, valid JSON, `status: success`)
- Coverage: not collected by `check-local.sh`
