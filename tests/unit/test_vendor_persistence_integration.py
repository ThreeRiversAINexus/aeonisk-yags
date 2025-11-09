"""
Integration test that reproduces the actual vendor persistence bug.

This test calls the REAL _generate_ai_scenario method to verify vendors
appear in the final scenario serialization.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from scripts.aeonisk.multiagent.dm import AIDMAgent
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.energy_economy import Vendor, VendorItem, VendorType


class TestVendorPersistenceIntegration:
    """Integration test for vendor persistence through scenario generation."""

    @pytest.mark.asyncio
    async def test_vendors_appear_in_scenario_jsonl_structured_output_path(self):
        """
        Test that persistent vendors appear in scenario JSONL when using
        the structured output code path (the actual bug).
        """
        # Create SharedState
        shared_state = SharedState()

        # Create test vendor (simulating persistent vendor from config)
        vendor = Vendor(
            name="Black Market Dealer \"Vex\"",
            faction="Freeborn",
            inventory=[
                VendorItem(name="Blood Offering", description="Test", price_drip=8)
            ],
            greeting="Need offerings?",
            vendor_type=VendorType.HUMAN_TRADER
        )

        # Add vendor to SharedState (simulating what __init__ does)
        shared_state.add_vendor(vendor)

        # Verify vendor is in SharedState
        vendors_in_state = shared_state.get_all_vendors()
        assert len(vendors_in_state) == 1
        assert vendors_in_state[0].name == "Black Market Dealer \"Vex\""

        # Create DM agent with session config
        session_config = {
            "vendor_spawn_frequency": -1,  # No random vendors
            "agents": {
                "players": [
                    {
                        "name": "Test Player",
                        "faction": "Freeborn",
                        "goals": ["Test goal"]
                    }
                ]
            }
        }

        # Create minimal DM agent
        dm = object.__new__(AIDMAgent)
        dm.agent_id = "dm_01"
        dm.faction = "DM"
        dm.shared_state = shared_state
        dm.session_config = session_config
        dm.vendor_pool = []
        dm.llm_config = {"provider": "anthropic", "model": "claude-sonnet-4-5"}
        dm.force_scenario = None
        dm.current_scenario = None
        dm.llm_logger = None
        dm.agent_prompt_logger = None

        # Mock the LLM client
        dm.llm_client = Mock()

        # Mock _generate_scenario_structured to return a scenario
        mock_scenario_setup = Mock()
        mock_scenario_setup.theme = "Test Scenario"
        mock_scenario_setup.location = "Test Location"
        mock_scenario_setup.situation = "Test situation"
        mock_scenario_setup.void_level = 5
        mock_scenario_setup.starting_clocks = []

        with patch.object(dm, '_generate_scenario_structured', return_value=mock_scenario_setup):
            # Call _generate_ai_scenario (the actual method that has the bug)
            await dm._generate_ai_scenario(session_config)

        # Verify scenario was created
        assert dm.current_scenario is not None

        # THE BUG: Check if vendors are in the scenario object
        scenario = dm.current_scenario
        print(f"DEBUG: scenario.active_vendors = {scenario.active_vendors}")

        # This should pass but currently fails (the bug)
        assert scenario.active_vendors is not None, "active_vendors is None!"
        assert len(scenario.active_vendors) == 1, f"Expected 1 vendor, got {len(scenario.active_vendors)}"
        assert scenario.active_vendors[0].name == "Black Market Dealer \"Vex\""

        # Also check serialization (what goes to JSONL)
        scenario_data = {
            'theme': scenario.theme,
            'location': scenario.location,
            'situation': scenario.situation,
            'void_level': scenario.void_level,
            'active_vendors': [
                {'name': v.name, 'type': v.vendor_type.value}
                for v in scenario.active_vendors
            ] if scenario.active_vendors else []
        }

        print(f"DEBUG: scenario_data['active_vendors'] = {scenario_data['active_vendors']}")

        # This is what goes to JSONL - should have vendors
        assert scenario_data['active_vendors'] is not None
        assert len(scenario_data['active_vendors']) == 1
        assert scenario_data['active_vendors'][0]['name'] == "Black Market Dealer \"Vex\""
