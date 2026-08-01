"""
Unit tests for BatchProxyProvider structured output resilience.

Tests retry-then-truncate logic for handling LLM responses that exceed
Pydantic max_length constraints on narrative text fields.
"""

import json
import logging
import pytest
from unittest.mock import Mock, patch, call
from pydantic import BaseModel, Field
from pydantic import ValidationError

from scripts.aeonisk.multiagent.llm_provider import LLMConfig
from scripts.aeonisk.multiagent.llm_batch_provider import BatchProxyProvider


# --- Test models with max_length constraints ---

class SimpleConstrained(BaseModel):
    """Model with a top-level max_length field."""
    title: str = Field(max_length=50)
    count: int


class NestedInner(BaseModel):
    """Inner model with max_length fields."""
    narrative: str = Field(max_length=100)
    mechanical_effect: str = Field(max_length=60)


class NestedConstrained(BaseModel):
    """Model with nested objects containing max_length fields."""
    summary: str = Field(max_length=80)
    detail: NestedInner


class MultiNested(BaseModel):
    """Model with a dict of nested objects."""
    narration: str = Field(max_length=200)
    tiers: dict[str, NestedInner] = Field(default_factory=dict)


# --- Fixtures ---

@pytest.fixture
def batch_provider():
    """Create BatchProxyProvider with mocked client."""
    config = LLMConfig(
        provider="batch_proxy",
        model="gpt-5-mini",
        temperature=0.7,
        max_tokens=1000,
        extra_params={
            'underlying_provider': 'openai',
            'use_proxy': True,
            'proxy_url': 'http://localhost:8000',
        }
    )
    with patch('scripts.aeonisk.multiagent.llm_batch_provider.UnifiedAIClient'):
        provider = BatchProxyProvider(config)
        provider.client = Mock()
        return provider


# ============================================================
# Tests for _pre_validate_fields() — truncation helper
# ============================================================

class TestPreValidateFields:
    """Test the _pre_validate_fields() recursive schema walker."""

    def test_truncates_top_level_long_string(self, batch_provider):
        """A string exceeding maxLength gets truncated to maxLength."""
        data = {"title": "x" * 100, "count": 5}
        schema = SimpleConstrained.model_json_schema()

        result = batch_provider._pre_validate_fields(data, schema)

        assert len(result["title"]) == 50
        assert result["count"] == 5

    def test_truncates_nested_string(self, batch_provider):
        """Nested object fields are also truncated."""
        data = {
            "summary": "ok",
            "detail": {
                "narrative": "n" * 200,
                "mechanical_effect": "m" * 100,
            }
        }
        schema = NestedConstrained.model_json_schema()

        result = batch_provider._pre_validate_fields(data, schema)

        assert len(result["detail"]["narrative"]) == 100
        assert len(result["detail"]["mechanical_effect"]) == 60
        assert result["summary"] == "ok"

    def test_preserves_valid_strings(self, batch_provider):
        """Strings within limits are not modified."""
        data = {"title": "Short title", "count": 7}
        schema = SimpleConstrained.model_json_schema()

        result = batch_provider._pre_validate_fields(data, schema)

        assert result["title"] == "Short title"
        assert result["count"] == 7

    def test_handles_dict_of_nested_objects(self, batch_provider):
        """Truncation works for dict values that are nested objects."""
        data = {
            "narration": "ok",
            "tiers": {
                "success": {
                    "narrative": "n" * 200,
                    "mechanical_effect": "short",
                },
                "failure": {
                    "narrative": "fine",
                    "mechanical_effect": "m" * 100,
                },
            }
        }
        schema = MultiNested.model_json_schema()

        result = batch_provider._pre_validate_fields(data, schema)

        assert len(result["tiers"]["success"]["narrative"]) == 100
        assert result["tiers"]["success"]["mechanical_effect"] == "short"
        assert result["tiers"]["failure"]["narrative"] == "fine"
        assert len(result["tiers"]["failure"]["mechanical_effect"]) == 60

    def test_logs_warning_on_truncation(self, batch_provider, caplog):
        """A WARNING is logged for each truncated field."""
        data = {"title": "x" * 100, "count": 1}
        schema = SimpleConstrained.model_json_schema()

        with caplog.at_level(logging.WARNING):
            batch_provider._pre_validate_fields(data, schema)

        assert any("truncating" in rec.message.lower() and "title" in rec.message for rec in caplog.records)

    def test_handles_missing_fields_gracefully(self, batch_provider):
        """Fields missing from data are not touched (Pydantic handles defaults)."""
        data = {"count": 3}  # 'title' missing
        schema = SimpleConstrained.model_json_schema()

        result = batch_provider._pre_validate_fields(data, schema)

        assert "title" not in result
        assert result["count"] == 3

    def test_handles_none_values(self, batch_provider):
        """None values in data are not truncated."""
        data = {"title": None, "count": 1}
        schema = SimpleConstrained.model_json_schema()

        result = batch_provider._pre_validate_fields(data, schema)

        assert result["title"] is None


# ============================================================
# Tests for generate_structured() retry + truncation flow
# ============================================================

class TestRetryAndTruncation:
    """Test the retry-then-truncate flow in generate_structured()."""

    @pytest.mark.asyncio
    async def test_retry_on_validation_error_then_succeed(self, batch_provider):
        """First call returns too-long string, retry succeeds with shorter response."""
        too_long = json.dumps({"title": "x" * 100, "count": 1})
        valid = json.dumps({"title": "Short", "count": 2})
        batch_provider.client.chat_completion.side_effect = [too_long, valid]

        result = await batch_provider.generate_structured(
            prompt="Test", result_type=SimpleConstrained
        )

        assert result.title == "Short"
        assert result.count == 2
        assert batch_provider.client.chat_completion.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_feedback_includes_error(self, batch_provider):
        """Retry prompt contains the validation error text."""
        too_long = json.dumps({"title": "x" * 100, "count": 1})
        valid = json.dumps({"title": "Ok", "count": 3})
        batch_provider.client.chat_completion.side_effect = [too_long, valid]

        await batch_provider.generate_structured(
            prompt="Test", result_type=SimpleConstrained
        )

        # Second call should have error feedback in the user message
        second_call_kwargs = batch_provider.client.chat_completion.call_args_list[1][1]
        user_msg = second_call_kwargs["messages"][-1]["content"]
        assert "FAILED VALIDATION" in user_msg
        assert "title" in user_msg.lower() or "max" in user_msg.lower()

    @pytest.mark.asyncio
    async def test_retries_exhausted_truncates_instead_of_raising(self, batch_provider):
        """All attempts return too-long strings → truncates and returns valid object."""
        too_long = json.dumps({"title": "x" * 100, "count": 5})
        # Return too_long for all 3 attempts (1 initial + 2 retries)
        batch_provider.client.chat_completion.return_value = too_long

        result = await batch_provider.generate_structured(
            prompt="Test", result_type=SimpleConstrained
        )

        # Should truncate and return valid result
        assert isinstance(result, SimpleConstrained)
        assert len(result.title) == 50
        assert result.count == 5
        # 3 total attempts: 1 initial + 2 retries
        assert batch_provider.client.chat_completion.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_connection_error(self, batch_provider):
        """Non-retryable errors (ConnectionError) raise immediately."""
        batch_provider.client.chat_completion.side_effect = ConnectionError("refused")

        with pytest.raises(ConnectionError):
            await batch_provider.generate_structured(
                prompt="Test", result_type=SimpleConstrained
            )

        assert batch_provider.client.chat_completion.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_json_decode_error_then_succeed(self, batch_provider):
        """First call returns bad JSON, retry returns valid JSON."""
        bad_json = "Not valid JSON at all"
        valid = json.dumps({"title": "Ok", "count": 1})
        batch_provider.client.chat_completion.side_effect = [bad_json, valid]

        result = await batch_provider.generate_structured(
            prompt="Test", result_type=SimpleConstrained
        )

        assert result.title == "Ok"
        assert batch_provider.client.chat_completion.call_count == 2

    @pytest.mark.asyncio
    async def test_success_on_first_attempt_no_retry(self, batch_provider):
        """Valid response on first attempt — no retries needed."""
        valid = json.dumps({"title": "Good", "count": 10})
        batch_provider.client.chat_completion.return_value = valid

        result = await batch_provider.generate_structured(
            prompt="Test", result_type=SimpleConstrained
        )

        assert result.title == "Good"
        assert result.count == 10
        assert batch_provider.client.chat_completion.call_count == 1

    @pytest.mark.asyncio
    async def test_truncation_logs_warning(self, batch_provider, caplog):
        """When truncation is used as last resort, a WARNING is logged."""
        too_long = json.dumps({"title": "x" * 100, "count": 1})
        batch_provider.client.chat_completion.return_value = too_long

        with caplog.at_level(logging.WARNING):
            await batch_provider.generate_structured(
                prompt="Test", result_type=SimpleConstrained
            )

        assert any("Truncating" in rec.message for rec in caplog.records)

    @pytest.mark.asyncio
    async def test_nested_truncation_after_retries_exhausted(self, batch_provider):
        """Nested fields are truncated when all retries fail."""
        too_long = json.dumps({
            "summary": "s" * 200,
            "detail": {
                "narrative": "n" * 200,
                "mechanical_effect": "m" * 100,
            }
        })
        batch_provider.client.chat_completion.return_value = too_long

        result = await batch_provider.generate_structured(
            prompt="Test", result_type=NestedConstrained
        )

        assert isinstance(result, NestedConstrained)
        assert len(result.summary) == 80
        assert len(result.detail.narrative) == 100
        assert len(result.detail.mechanical_effect) == 60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
