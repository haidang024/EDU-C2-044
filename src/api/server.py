"""Standalone HTTP adapter for EDU-C2-044."""

import os
import secrets
from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.context import bound_secrets
from framework.utils.config_loader import load_config
from shared.secrets import factory as secrets_factory
from shared.secrets.chained_provider import ChainedSecretProvider
from shared.secrets.env_provider import EnvProvider
from src.graph.graph import Graph
from src.services.mock_mode import (
    STUB_OFFICER_REGISTRY_API_KEY,
    STUB_POLICY_RAG_API_KEY,
    STUB_PRIOR_CASE_RAG_API_KEY,
)

app = FastAPI(title="EDU-C2-044 Academic Integrity Evidence Triage Agent")

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
_config = load_config(str(_CONFIG_PATH)) if _CONFIG_PATH.exists() else {}

# Provisional Stage 5 uses synthetic connectors only when explicitly enabled.
# Normal runtime never falls back to mock credentials because a production
# secret is absent.
if os.environ.get("STG_MOCK_MODE", "").lower() in {"1", "true", "yes"}:
    from shared.secrets.inmemory_provider import InMemoryProvider

    _domain_secrets_provider = InMemoryProvider(
        values={
            "OFFICER_REGISTRY_API_KEY": STUB_OFFICER_REGISTRY_API_KEY,
            "POLICY_RAG_API_KEY": STUB_POLICY_RAG_API_KEY,
            "PRIOR_CASE_RAG_API_KEY": STUB_PRIOR_CASE_RAG_API_KEY,
        },
        namespace="EDU",
        agent_name="Academic Integrity Evidence Triage Agent",
    )
else:
    _domain_secrets_provider = secrets_factory(
        namespace="agent1000",
        agent_name="EDU-C2-044",
    )
_namespace = "agent1000"
_secrets_provider = ChainedSecretProvider(
    EnvProvider(namespace=_namespace, agent_name="EDU-C2-044"),
    _domain_secrets_provider,
)

_llm: None = None  # Compatibility seam; Azure clients are invocation-scoped.
agent = Graph(config=_config)
_hitl_enabled = agent.config.get("hitl", {}).get("enabled", False)
_needs_checkpointer = agent.config.get("memory_enabled") or _hitl_enabled
agent.compile(checkpointer=MemorySaver() if _needs_checkpointer else None)
agent.provision_secrets(_secrets_provider)


class InvokeRequest(BaseModel):
    input: str
    session_id: str = ""


def _bearer_matches(supplied: str, expected: str) -> bool:
    """Compare bearer credentials in constant time, including non-ASCII input."""
    return secrets.compare_digest(supplied.encode(), f"Bearer {expected}".encode())


def _resolve_standalone_trust(
    current: TrustLevel,
    authorization: str,
    invoke_auth_token: str | None,
    internal_runner_token: str | None,
) -> TrustLevel:
    """Authenticate callers without promoting an external token to INTERNAL."""
    if current is not TrustLevel.ANONYMOUS:
        return current
    if internal_runner_token and _bearer_matches(authorization, internal_runner_token):
        return TrustLevel.INTERNAL
    if invoke_auth_token and _bearer_matches(authorization, invoke_auth_token):
        return TrustLevel.VERIFIED_EXTERNAL
    if internal_runner_token or invoke_auth_token:
        raise HTTPException(status_code=401, detail="Token is invalid or expired.")
    return TrustLevel.ANONYMOUS


@app.post("/invoke")
def invoke(req: InvokeRequest, request: Request) -> dict[str, object]:
    """Invoke the synchronous graph outside the ASGI event-loop thread.

    The domain nodes bridge their asynchronous connectors with
    ``asyncio.run()``.  A synchronous FastAPI handler is therefore required:
    FastAPI dispatches it in a worker thread where no event loop is active.
    """
    trust = _resolve_standalone_trust(
        getattr(request.state, "trust_level", TrustLevel.ANONYMOUS),
        request.headers.get("authorization", ""),
        os.environ.get("INVOKE_AUTH_TOKEN"),
        os.environ.get("STG_INTERNAL_RUNNER_TOKEN"),
    )
    with bound_secrets(agent._secrets_provider):
        ctx = InvocationContext(
            session_id=req.session_id or str(uuid4()),
            caller_trust_level=trust,
            caller_id=getattr(request.state, "caller_id", ""),
        )
        return cast(
            dict[str, object],
            agent.invoke(req.input, ctx=ctx, input_context={"raw": req.input}),
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "agent": "EDU-C2-044"}
