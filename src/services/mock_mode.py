"""AgentCore Platform v1.0"""

# Stub sentinel values for provisional STG smoke check.
# Services detect these values and return canned responses without any real
# API call — no os.environ reads or test-framework imports required.
# These values are code constants, not real credentials.

STUB_OFFICER_REGISTRY_API_KEY = "stub-officer-registry-key-stg"
STUB_POLICY_RAG_API_KEY = "stub-policy-rag-key-stg"
STUB_PRIOR_CASE_RAG_API_KEY = "stub-prior-case-rag-key-stg"
STUB_LLM_API_KEY = "stub-llm-key-stg"

_STUB_HANDLES = frozenset(
    {
        STUB_OFFICER_REGISTRY_API_KEY,
        STUB_POLICY_RAG_API_KEY,
        STUB_PRIOR_CASE_RAG_API_KEY,
        STUB_LLM_API_KEY,
    }
)


def resolve_or_stub(ctx: object, key: str, stub: str) -> tuple[str, str]:
    """Return (credential_handle, source) for an optional retrieval connector.

    `ctx.secrets.require()` raises when the connector is not provisioned, which
    aborts the node. For *retrieval* connectors (policy corpus, prior-case
    corpus) the node can instead run against the bundled stub corpus, so a
    deployment without those connectors still produces a complete briefing.

    `source` is "live" or "fixture" and is recorded on state for the audit log;
    the caller-facing briefing is identical either way.

    NOTE: deliberately NOT used for the officer-registry credential. That one
    gates *authorization*, and silently substituting a stub would let an
    unauthorized requester through.
    """
    try:
        secrets = ctx.secrets  # type: ignore[attr-defined]
        value = secrets.require(key)
    except Exception:
        return stub, "fixture"
    return (str(value), "live") if value else (stub, "fixture")


def mock_mode_enabled(credential_handle: str = "") -> bool:
    """Return True when the credential handle is a stub sentinel value.

    Mock mode is detected solely by whether the credential handle matches a
    known stub constant — no os.environ reads required.
    """
    return credential_handle in _STUB_HANDLES
