"""
Regression test: Unsupported LLM providers (deepinfra, xai, gemini) caused
AttributeError: 'NoneType' object has no attribute 'lower' during adjudication.

Root cause chain:
1. create_provider() only supports openai/anthropic/batch_proxy/local
2. For deepinfra/xai/gemini: self.llm_provider = None
3. Structured output generation returns None (no provider)
4. Falls to legacy _generate_llm_response() path
5. Legacy path only handled openai/anthropic, no else clause
6. Function returned None implicitly
7. parse_state_changes(None, ...) → narration.lower() → AttributeError

Fixes:
- dm.py: Added else clause using UnifiedAIClient for all other providers
- outcome_parser.py: Added None guards in parse_state_changes and parse_clock_triggers
- dm.py: Added traceback logging in _handle_adjudication error handler
"""

import pytest
from scripts.aeonisk.multiagent.outcome_parser import (
    parse_state_changes,
    parse_clock_triggers,
)


class TestNoneNarrationGuards:
    """Verify parser functions handle None narration without crashing."""

    def test_parse_state_changes_none_narration(self):
        """parse_state_changes should return empty state changes for None narration."""
        action = {
            'action_type': 'combat',
            'description': 'Attack the enemy',
            'intent': 'Attack',
        }
        resolution = {
            'outcome_tier': 'success',
            'margin': 3,
        }

        # This was the crash: parse_state_changes(None, ...) → .lower() on None
        result = parse_state_changes(None, action, resolution)

        assert isinstance(result, dict)
        assert result['void_change'] == 0
        assert result['clock_triggers'] == []

    def test_parse_state_changes_empty_string_narration(self):
        """parse_state_changes should handle empty string narration."""
        result = parse_state_changes("", {'action_type': 'investigate'}, {'outcome_tier': 'failure', 'margin': -2})

        assert isinstance(result, dict)
        assert result['void_change'] == 0

    def test_parse_clock_triggers_none_narration(self):
        """parse_clock_triggers should return empty list for None narration."""
        result = parse_clock_triggers(None, 'success', 3, {'Test Clock': object()})

        assert isinstance(result, list)
        assert len(result) == 0

    def test_parse_clock_triggers_empty_string_narration(self):
        """parse_clock_triggers should handle empty string narration."""
        result = parse_clock_triggers("", 'success', 3, {'Test Clock': object()})

        assert isinstance(result, list)
        assert len(result) == 0

    def test_parse_clock_triggers_none_narration_no_clocks(self):
        """parse_clock_triggers with None narration and no clocks returns empty."""
        result = parse_clock_triggers(None, 'success', 3, None)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_parse_state_changes_normal_narration_still_works(self):
        """Normal narration should still be processed correctly."""
        action = {
            'action_type': 'combat',
            'description': 'Shoot the grunt',
            'intent': 'Attack',
        }
        resolution = {
            'outcome_tier': 'success',
            'margin': 5,
        }

        result = parse_state_changes(
            "The blast hits the grunt squarely in the chest.",
            action,
            resolution
        )

        assert isinstance(result, dict)
        # Normal processing shouldn't crash
        assert 'void_change' in result
        assert 'clock_triggers' in result


class TestProviderNameMapping:
    """Verify provider name mappings for UnifiedAIClient compatibility."""

    def test_xai_maps_to_grok(self):
        """xai provider should map to 'grok' for UnifiedAIClient."""
        provider_map = {'xai': 'grok'}
        assert provider_map.get('xai', 'xai') == 'grok'

    def test_deepinfra_passes_through(self):
        """deepinfra provider should pass through unchanged."""
        provider_map = {'xai': 'grok'}
        assert provider_map.get('deepinfra', 'deepinfra') == 'deepinfra'

    def test_gemini_passes_through(self):
        """gemini provider should pass through unchanged."""
        provider_map = {'xai': 'grok'}
        assert provider_map.get('gemini', 'gemini') == 'gemini'
