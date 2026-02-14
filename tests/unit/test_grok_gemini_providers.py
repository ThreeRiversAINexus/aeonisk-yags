"""
Tests for Grok and Gemini provider support.

TDD: Tests written FIRST, then implementation.
"""

import copy
import json
import os
import sys
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from aeonisk.multiagent.llm_provider import (
    SUPPORTED_MODELS,
    RATE_LIMIT_PRESETS,
    LLMConfig,
)
from aeonisk.multiagent.unified_llm_client import UnifiedAIClient


# ── SUPPORTED_MODELS ──────────────────────────────────────────────────

class TestSupportedModels:
    """Verify grok/gemini are in SUPPORTED_MODELS and batch_proxy list."""

    def test_grok_in_supported_models(self):
        assert 'grok' in SUPPORTED_MODELS
        info = SUPPORTED_MODELS['grok']
        assert 'grok-4-latest' in info['models']
        assert info['recommended'] == 'grok-4-latest'

    def test_gemini_in_supported_models(self):
        assert 'gemini' in SUPPORTED_MODELS
        info = SUPPORTED_MODELS['gemini']
        assert 'gemini-2.5-pro' in info['models']
        assert info['recommended'] == 'gemini-2.5-pro'

    def test_grok_models_in_batch_proxy(self):
        proxy_models = SUPPORTED_MODELS['batch_proxy']['models']
        assert 'grok-4-latest' in proxy_models

    def test_gemini_models_in_batch_proxy(self):
        proxy_models = SUPPORTED_MODELS['batch_proxy']['models']
        assert 'gemini-2.5-pro' in proxy_models

    def test_grok_rate_limit_preset(self):
        assert 'grok' in RATE_LIMIT_PRESETS
        preset = RATE_LIMIT_PRESETS['grok']
        assert 'max_concurrent_requests' in preset
        assert 'min_request_interval' in preset

    def test_gemini_rate_limit_preset(self):
        assert 'gemini' in RATE_LIMIT_PRESETS
        preset = RATE_LIMIT_PRESETS['gemini']
        assert 'max_concurrent_requests' in preset
        assert 'min_request_interval' in preset


# ── LLMConfig Validation ─────────────────────────────────────────────

class TestLLMConfigValidation:
    """LLMConfig accepts grok/gemini without warnings."""

    def test_grok_config_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            config = LLMConfig(provider="grok", model="grok-4-latest")
        assert config.provider == "grok"
        assert config.model == "grok-4-latest"
        # No "Unknown provider" or "not in known models" warnings
        assert "Unknown provider" not in caplog.text
        assert "not in known models" not in caplog.text

    def test_gemini_config_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            config = LLMConfig(provider="gemini", model="gemini-2.5-pro")
        assert config.provider == "gemini"
        assert config.model == "gemini-2.5-pro"
        assert "Unknown provider" not in caplog.text
        assert "not in known models" not in caplog.text

    def test_grok_unknown_model_warns(self, caplog):
        with caplog.at_level(logging.WARNING):
            LLMConfig(provider="grok", model="grok-nonexistent")
        assert "not in known models" in caplog.text

    def test_gemini_unknown_model_warns(self, caplog):
        with caplog.at_level(logging.WARNING):
            LLMConfig(provider="gemini", model="gemini-nonexistent")
        assert "not in known models" in caplog.text

    def test_grok_rate_limits_applied(self):
        config = LLMConfig(provider="grok", model="grok-4-latest")
        preset = RATE_LIMIT_PRESETS['grok']
        assert config.max_concurrent_requests == preset['max_concurrent_requests']
        assert config.min_request_interval == preset['min_request_interval']

    def test_gemini_rate_limits_applied(self):
        config = LLMConfig(provider="gemini", model="gemini-2.5-pro")
        preset = RATE_LIMIT_PRESETS['gemini']
        assert config.max_concurrent_requests == preset['max_concurrent_requests']
        assert config.min_request_interval == preset['min_request_interval']


# ── UnifiedAIClient ───────────────────────────────────────────────────

class TestUnifiedClientInit:
    """UnifiedAIClient accepts grok/gemini providers."""

    def test_grok_init(self):
        client = UnifiedAIClient(provider="grok")
        assert client.provider == "grok"
        assert client.default_model == "grok-4-latest"

    def test_gemini_init(self):
        client = UnifiedAIClient(provider="gemini")
        assert client.provider == "gemini"
        assert client.default_model == "gemini-2.5-pro"

    def test_grok_default_model_env_override(self):
        with patch.dict(os.environ, {"GROK_MODEL": "grok-3"}):
            client = UnifiedAIClient(provider="grok")
            assert client.default_model == "grok-3"

    def test_gemini_default_model_env_override(self):
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-2.5-flash"}):
            client = UnifiedAIClient(provider="gemini")
            assert client.default_model == "gemini-2.5-flash"


# ── Direct Fallback Routing ──────────────────────────────────────────

class TestDirectFallback:
    """_direct_completion routes grok/gemini to OpenAI-compatible client."""

    def test_direct_completion_exists(self):
        client = UnifiedAIClient(provider="grok")
        assert hasattr(client, '_direct_completion')

    @patch.dict(os.environ, {"XAI_API_KEY": "test-key"})
    def test_grok_creates_openai_compatible_client(self):
        client = UnifiedAIClient(provider="grok")
        compat_client = client._get_openai_compatible_client()
        assert compat_client is not None
        assert compat_client.base_url.host == "api.x.ai"

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    def test_gemini_creates_openai_compatible_client(self):
        client = UnifiedAIClient(provider="gemini")
        compat_client = client._get_openai_compatible_client()
        assert compat_client is not None
        assert "generativelanguage.googleapis.com" in str(compat_client.base_url)

    def test_grok_missing_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove XAI_API_KEY if it exists
            os.environ.pop("XAI_API_KEY", None)
            client = UnifiedAIClient(provider="grok")
            with pytest.raises(ValueError, match="XAI_API_KEY"):
                client._get_openai_compatible_client()

    def test_gemini_missing_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            client = UnifiedAIClient(provider="gemini")
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                client._get_openai_compatible_client()


# ── Config Generator ──────────────────────────────────────────────────

class TestConfigGenerator:
    """generate_multi_llm_configs.py --proxy flag generates batch_proxy config."""

    def _get_functions(self):
        """Import functions from generate_multi_llm_configs.py."""
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from generate_multi_llm_configs import update_llm_block, generate_config
        return update_llm_block, generate_config

    def test_update_llm_block_without_proxy(self):
        update_llm_block, _ = self._get_functions()
        base_llm = {"provider": "openai", "model": "gpt-5-mini", "temperature": 0.7}
        result = update_llm_block(base_llm, "grok", "grok-4-latest")
        assert result["provider"] == "grok"
        assert result["model"] == "grok-4-latest"
        assert result["temperature"] == 0.7
        # Should NOT have batch_proxy keys when no proxy_url
        assert "underlying_provider" not in result

    def test_update_llm_block_with_proxy(self):
        update_llm_block, _ = self._get_functions()
        base_llm = {"provider": "openai", "model": "gpt-5-mini", "temperature": 0.7}
        result = update_llm_block(
            base_llm, "grok", "grok-4-latest",
            proxy_url="http://localhost:8000"
        )
        assert result["provider"] == "batch_proxy"
        assert result["model"] == "grok-4-latest"
        assert result["underlying_provider"] == "grok"
        assert result["use_proxy"] is True
        assert result["proxy_url"] == "http://localhost:8000"
        assert result["temperature"] == 0.7

    def test_generate_config_session_name_uses_original_provider(self):
        _, generate_config = self._get_functions()
        base = {
            "session_name": "lethality_test",
            "agents": {
                "dm": {"llm": {"provider": "openai", "model": "gpt-5-mini"}},
                "players": [{"llm": {"provider": "openai", "model": "gpt-5-mini"}}],
            },
        }
        config = generate_config(
            base, "grok", "grok-4-latest",
            proxy_url="http://localhost:8000"
        )
        # Session name uses original provider, not "batch_proxy"
        assert "grok" in config["session_name"]
        assert "batch_proxy" not in config["session_name"]
        # But agent LLM blocks use batch_proxy
        assert config["agents"]["dm"]["llm"]["provider"] == "batch_proxy"
        assert config["agents"]["dm"]["llm"]["underlying_provider"] == "grok"

    def test_generate_config_without_proxy(self):
        _, generate_config = self._get_functions()
        base = {
            "session_name": "lethality_test",
            "agents": {
                "dm": {"llm": {"provider": "openai", "model": "gpt-5-mini"}},
                "players": [],
            },
        }
        config = generate_config(base, "gemini", "gemini-2.5-pro")
        assert config["agents"]["dm"]["llm"]["provider"] == "gemini"
        assert config["agents"]["dm"]["llm"]["model"] == "gemini-2.5-pro"
        assert "underlying_provider" not in config["agents"]["dm"]["llm"]


# ── OpenAI-compatible provider config ─────────────────────────────────

OPENAI_COMPATIBLE_PROVIDERS = {
    'grok': {
        'base_url': 'https://api.x.ai/v1',
        'env_key': 'XAI_API_KEY',
    },
    'gemini': {
        'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai',
        'env_key': 'GEMINI_API_KEY',
    },
}


class TestOpenAICompatibleConfig:
    """Verify the base_url and env_key mapping for OpenAI-compatible providers."""

    def test_grok_base_url(self):
        client = UnifiedAIClient(provider="grok")
        assert client._openai_compatible_config['base_url'] == 'https://api.x.ai/v1'

    def test_gemini_base_url(self):
        client = UnifiedAIClient(provider="gemini")
        assert client._openai_compatible_config['base_url'] == \
            'https://generativelanguage.googleapis.com/v1beta/openai'

    def test_grok_env_key(self):
        client = UnifiedAIClient(provider="grok")
        assert client._openai_compatible_config['env_key'] == 'XAI_API_KEY'

    def test_gemini_env_key(self):
        client = UnifiedAIClient(provider="gemini")
        assert client._openai_compatible_config['env_key'] == 'GEMINI_API_KEY'
