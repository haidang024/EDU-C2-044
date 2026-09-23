"""Shared pytest fixtures for EDU-C2-044.

Binds a mock SecretProvider for the entire test session so that
ctx.secrets.require() returns stub sentinel values that activate mock mode
in the service layer (detected via mock_mode_enabled() in service.py).
"""

import pytest
from framework.secrets.base import SecretProvider
from framework.secrets.context import bind_secrets, unbind_secrets
from src.services.mock_mode import (
    STUB_OFFICER_REGISTRY_API_KEY,
    STUB_POLICY_RAG_API_KEY,
    STUB_PRIOR_CASE_RAG_API_KEY,
    STUB_LLM_API_KEY,
)

_STUB_SECRETS = {
    "OFFICER_REGISTRY_API_KEY": STUB_OFFICER_REGISTRY_API_KEY,
    "POLICY_RAG_API_KEY": STUB_POLICY_RAG_API_KEY,
    "PRIOR_CASE_RAG_API_KEY": STUB_PRIOR_CASE_RAG_API_KEY,
    "LLM_API_KEY": STUB_LLM_API_KEY,
}


class _MockSecretProvider(SecretProvider):
    """Returns stub sentinel values so services activate mock mode."""

    def get(self, key: str, default: str | None = None) -> str | None:
        return _STUB_SECRETS.get(key, default)

    def require(self, key: str) -> str:
        value = _STUB_SECRETS.get(key)
        if value is None:
            raise KeyError(f"No stub secret configured for key: {key!r}")
        return value


@pytest.fixture(autouse=True, scope="session")
def bind_mock_secrets():
    """Bind stub secrets for the entire test session."""
    token = bind_secrets(_MockSecretProvider())
    yield
    unbind_secrets(token)
