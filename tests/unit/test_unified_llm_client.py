"""
Unit tests for unified_llm_client.py

Tests proxy routing, retry logic, and fallback behavior.
Uses mocking at the requests level to verify retry counts and fallback decisions.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests

from scripts.aeonisk.multiagent.unified_llm_client import UnifiedAIClient


class TestProxyRouting:
    """Test proxy routing and request handling."""

    @patch('scripts.aeonisk.multiagent.unified_llm_client.requests.post')
    def test_proxy_routing_success(self, mock_post):
        """Test successful request routing through proxy."""
        # Mock successful proxy response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "completed",
            "content": "Hello, this is the response!"
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        client = UnifiedAIClient(
            provider="openai",
            use_proxy=True,
            proxy_url="http://localhost:8000"
        )

        result = client._proxy_completion(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-5-mini",
            temperature=0.7,
            max_tokens=100
        )

        assert result == "Hello, this is the response!"
        mock_post.assert_called_once()

        # Verify request was sent to proxy
        call_args = mock_post.call_args
        assert "http://localhost:8000/submit" in call_args[0][0]

    @patch('scripts.aeonisk.multiagent.unified_llm_client.requests.post')
    def test_proxy_timeout_is_forwarded_to_endpoint_and_requests(self, mock_post):
        """Configured proxy timeout bounds both server-side wait and HTTP wait."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "completed",
            "content": "bounded response"
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        client = UnifiedAIClient(
            provider="openai",
            use_proxy=True,
            proxy_url="http://localhost:8000",
            proxy_timeout=45,
        )

        result = client._proxy_completion(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-5-mini",
            temperature=0.7,
            max_tokens=100
        )

        assert result == "bounded response"
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["params"] == {"timeout": 45}
        assert call_kwargs["timeout"] == 45

    @patch('scripts.aeonisk.multiagent.unified_llm_client.requests.post')
    @patch('scripts.aeonisk.multiagent.unified_llm_client.time.sleep')
    def test_proxy_retry_on_connection_error(self, mock_sleep, mock_post):
        """Test that connection errors trigger retries with exponential backoff."""
        # First 2 calls fail with connection error, third succeeds
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "completed",
            "content": "Success after retries"
        }
        mock_response.raise_for_status = Mock()

        mock_post.side_effect = [
            requests.exceptions.ConnectionError("Connection refused"),
            requests.exceptions.ConnectionError("Connection refused"),
            mock_response  # Third attempt succeeds
        ]

        client = UnifiedAIClient(
            provider="openai",
            use_proxy=True,
            proxy_url="http://localhost:8000"
        )

        result = client._proxy_completion(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-5-mini",
            temperature=0.7,
            max_tokens=100
        )

        assert result == "Success after retries"
        assert mock_post.call_count == 3  # 2 failures + 1 success
        assert mock_sleep.call_count == 2  # Sleep between retries

        # Verify exponential backoff (5s, then 10s)
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert sleep_calls[0] == 5  # First retry delay
        assert sleep_calls[1] == 10  # Second retry delay (doubled)

    @patch('scripts.aeonisk.multiagent.unified_llm_client.requests.post')
    @patch('scripts.aeonisk.multiagent.unified_llm_client.time.sleep')
    def test_fallback_to_direct_api_after_retries(self, mock_sleep, mock_post):
        """Test that after 3 failed retries, client falls back to direct API."""
        # All proxy calls fail
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        client = UnifiedAIClient(
            provider="openai",
            use_proxy=True,
            proxy_url="http://localhost:8000"
        )

        # Mock the direct API method
        with patch.object(client, '_openai_completion', return_value="Direct API response") as mock_direct:
            result = client._proxy_completion(
                messages=[{"role": "user", "content": "Hello"}],
                model="gpt-5-mini",
                temperature=0.7,
                max_tokens=100
            )

            assert result == "Direct API response"
            assert mock_post.call_count == 3  # All 3 retries failed
            mock_direct.assert_called_once()  # Fell back to direct API

    @patch('scripts.aeonisk.multiagent.unified_llm_client.requests.post')
    def test_fallback_on_http_error(self, mock_post):
        """Test immediate fallback to direct API on HTTP 4xx/5xx errors."""
        # Proxy returns HTTP 500 error
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        mock_post.return_value = mock_response

        client = UnifiedAIClient(
            provider="openai",
            use_proxy=True,
            proxy_url="http://localhost:8000"
        )

        # Mock the direct API method
        with patch.object(client, '_openai_completion', return_value="Direct API fallback") as mock_direct:
            result = client._proxy_completion(
                messages=[{"role": "user", "content": "Hello"}],
                model="gpt-5-mini",
                temperature=0.7,
                max_tokens=100
            )

            assert result == "Direct API fallback"
            # HTTP errors should fallback immediately without retries
            assert mock_post.call_count == 1
            mock_direct.assert_called_once()


class TestHealthCheck:
    """Test proxy health check functionality."""

    @patch('scripts.aeonisk.multiagent.unified_llm_client.requests.get')
    def test_health_check_success(self, mock_get):
        """Test successful health check returns healthy status."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        client = UnifiedAIClient(
            provider="openai",
            use_proxy=True,
            proxy_url="http://localhost:8000"
        )

        result = client.health_check()

        assert result['reachable'] is True
        assert result['status'] == 'healthy'
        assert result['error'] is None

    @patch('scripts.aeonisk.multiagent.unified_llm_client.requests.get')
    def test_health_check_connection_error(self, mock_get):
        """Test health check returns unreachable on connection error."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        client = UnifiedAIClient(
            provider="openai",
            use_proxy=True,
            proxy_url="http://localhost:8000"
        )

        result = client.health_check()

        assert result['reachable'] is False
        assert result['status'] == 'unreachable'
        assert 'Connection error' in result['error']

    def test_health_check_proxy_disabled(self):
        """Test health check returns direct status when proxy disabled."""
        client = UnifiedAIClient(
            provider="openai",
            use_proxy=False
        )

        result = client.health_check()

        assert result['reachable'] is True
        assert result['status'] == 'direct'


class TestProviderInitialization:
    """Test client initialization and provider settings."""

    def test_init_with_openai(self):
        """Test initialization with OpenAI provider."""
        client = UnifiedAIClient(provider="openai")

        assert client.provider == "openai"
        assert client.default_model == "gpt-5-mini"

    def test_init_with_anthropic(self):
        """Test initialization with Anthropic provider."""
        client = UnifiedAIClient(provider="anthropic")

        assert client.provider == "anthropic"
        assert client.default_model == "claude-sonnet-4-5"

    def test_init_with_proxy_settings(self):
        """Test initialization with proxy configuration."""
        client = UnifiedAIClient(
            provider="openai",
            use_proxy=True,
            proxy_url="http://custom-proxy:9000",
            proxy_priority="high",
            proxy_strategy="batch"
        )

        assert client.use_proxy is True
        assert client.proxy_url == "http://custom-proxy:9000"
        assert client.proxy_priority == "high"
        assert client.proxy_strategy == "batch"

    def test_init_invalid_provider_raises(self):
        """Test that invalid provider raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported AI provider"):
            UnifiedAIClient(provider="invalid_provider")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
