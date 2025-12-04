"""
Test that bulk_session_runner.py disables human interface to prevent prompt spam.
"""

import pytest
import json
import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts'))

from bulk_session_runner import modify_config_for_bulk_run


class TestBulkRunnerHumanInterface:
    """Test that bulk runner disables human interface."""

    def test_modify_config_for_bulk_run_disables_human_interface(self):
        """
        CRITICAL: Bulk runner must disable human interface to prevent
        Observer> prompt spam in stdout logs.
        """
        # Minimal config
        config = {
            'session_name': 'test_session',
            'agents': {
                'dm': {'llm': {'provider': 'openai', 'model': 'gpt-5-mini'}},
                'players': []
            }
        }

        # Prepare config for bulk run
        modified = modify_config_for_bulk_run(
            config=config,
            run_id=1,
            output_path='/tmp/test_output.jsonl',
            proxy_url=None
        )

        # Assert: enable_human_interface must be False
        assert 'enable_human_interface' in modified, \
            "modify_config_for_bulk_run must set enable_human_interface"
        assert modified['enable_human_interface'] is False, \
            "Bulk runs must disable human interface to prevent prompt spam"

    def test_modify_config_overrides_existing_human_interface_setting(self):
        """
        Even if config explicitly enables human interface,
        bulk runner should override to False.
        """
        config = {
            'session_name': 'test_session',
            'enable_human_interface': True,  # Explicitly enabled
            'agents': {
                'dm': {'llm': {'provider': 'openai', 'model': 'gpt-5-mini'}},
                'players': []
            }
        }

        modified = modify_config_for_bulk_run(
            config=config,
            run_id=1,
            output_path='/tmp/test_output.jsonl',
            proxy_url=None
        )

        # Assert: Should override to False
        assert modified['enable_human_interface'] is False, \
            "Bulk runner must override enable_human_interface to False"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
