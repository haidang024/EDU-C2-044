"""The chat window must never show internal implementation detail.

Node error_log text names the failing node class and the exact secret key
("AuthorizationVerificationNode: credential unavailable — Required secret
'OFFICER_REGISTRY_API_KEY' not found"). It was rendered verbatim as the
"Reason:" line, so a Marketplace user saw both in chat.

The cause must stay on workflow_error_detail (log-facing) while the caller sees
a stable description plus a reference code.
"""

from __future__ import annotations

import json

import pytest

from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import _WORKFLOW_ERROR_REASONS, Graph

_INTERNAL_MARKERS = (
    "AuthorizationVerificationNode",
    "PolicyRAGNode",
    "PriorCaseRAGNode",
    "BriefingDraftNode",
    "OFFICER_REGISTRY_API_KEY",
    "POLICY_RAG_API_KEY",
    "PRIOR_CASE_RAG_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "Traceback",
    "config.yaml",
)

_VALID_CASE = json.dumps(
    {
        "case_ref": "AI-2026-0117",
        "case_type": "plagiarism",
        "evidence_bundle_ref": "EV-0117",
        "requester_ref": "STAFF-88",
        "institution_id": "UNI-01",
    }
)


@pytest.fixture(autouse=True)
def _unconfigured_deployment(monkeypatch):
    for name in ("USE_MOCK", "STG_MOCK_MODE"):
        monkeypatch.delenv(name, raising=False)


def _invoke(user_input: str) -> dict:
    agent = Graph()
    agent.compile()
    ctx = InvocationContext(caller_id="u1", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL)
    return agent.invoke(user_input, ctx=ctx, input_context={"conversation_history": []})


@pytest.mark.parametrize(
    "user_input",
    [
        pytest.param(_VALID_CASE, id="valid-case-intake"),
        pytest.param("Hello", id="short-chat"),
        pytest.param("Hello, please triage a case for me.", id="chat-sentence"),
        pytest.param("{not json", id="malformed-json"),
    ],
)
def test_output_never_leaks_internal_detail(user_input: str) -> None:
    result = _invoke(user_input)

    status = getattr(result.get("status"), "value", result.get("status"))
    assert status == AgentStatus.SUCCESS.value, "runner would discard output and raise RuntimeError"

    output = str(result.get("output") or "")
    assert output, "runner requires a non-empty output on success"
    for marker in _INTERNAL_MARKERS:
        assert marker not in output, f"chat output leaked {marker!r}"


def test_failed_workflow_is_explained_with_a_reference() -> None:
    result = _invoke(_VALID_CASE)
    output = str(result.get("output"))
    code = result["workflow_error_code"]

    assert code in _WORKFLOW_ERROR_REASONS
    assert _WORKFLOW_ERROR_REASONS[code] in output
    assert f"Reference: {code}" in output


def test_raw_cause_is_preserved_for_operators() -> None:
    """Hiding detail from chat must not hide it from the logs."""
    result = _invoke(_VALID_CASE)

    assert str(result["workflow_error_detail"]).strip()
