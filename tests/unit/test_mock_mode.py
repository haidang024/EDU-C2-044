# BL-32, BL-33, BL-34 — mock_mode_enabled() flag resolution

from src.services.mock_mode import (
    mock_mode_enabled,
    STUB_OFFICER_REGISTRY_API_KEY,
    STUB_POLICY_RAG_API_KEY,
    STUB_PRIOR_CASE_RAG_API_KEY,
    STUB_LLM_API_KEY,
)


class TestMockMode:
    def test_use_mock_enables_mock_mode(self):
        """BL-32: stub officer registry key enables mock mode."""
        assert mock_mode_enabled(STUB_OFFICER_REGISTRY_API_KEY) is True

    def test_stg_mock_mode_enables_mock_mode(self):
        """BL-33: stub LLM key enables mock mode."""
        assert mock_mode_enabled(STUB_LLM_API_KEY) is True

    def test_no_flags_disables_mock_mode(self):
        """BL-34: non-stub handle → mock mode off."""
        assert mock_mode_enabled("") is False

    def test_use_mock_1_enables_mock_mode(self):
        """BL: stub policy RAG key enables mock mode."""
        assert mock_mode_enabled(STUB_POLICY_RAG_API_KEY) is True

    def test_use_mock_yes_enables_mock_mode(self):
        """BL: stub prior case RAG key enables mock mode."""
        assert mock_mode_enabled(STUB_PRIOR_CASE_RAG_API_KEY) is True
