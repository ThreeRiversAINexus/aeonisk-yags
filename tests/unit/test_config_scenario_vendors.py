"""
Test-Driven Development: Config Scenario Must Include SharedState Vendors

BUG (from session 260c66f9):
- persistent_vendors loaded into SharedState ✅
- dm._use_config_scenario() ignores SharedState vendors ❌
- scenario_data['active_vendors'] = [] (empty) ❌
- Players never see vendor inventory with vendor_id/item_id ❌
- LLM can't provide vendor_id/item_id in purchase actions ❌

TEST FIRST, FIX SECOND (TDD)
"""

import pytest
from unittest.mock import Mock, MagicMock
from scripts.aeonisk.multiagent.dm import AIDMAgent
from scripts.aeonisk.multiagent.energy_economy import Vendor, VendorItem, VendorType
from scripts.aeonisk.multiagent.shared_state import SharedState


class TestConfigScenarioVendors:
    """
    TDD: Test that config scenarios include persistent vendors from SharedState.

    Write tests FIRST to define correct behavior, THEN fix the code.
    """

    @pytest.fixture
    def shared_state_with_vendor(self):
        """Create SharedState with a persistent vendor (like session.py does)."""
        shared_state = SharedState()

        # This is what session._initialize_persistent_vendors() does
        medkit = VendorItem(
            name="Med Kit",
            description="Restores 15 HP immediately",
            price_drip=5
        )
        vendor = Vendor(
            vendor_id="vnd_medic",  # Should have auto-generated ID
            name="Field Medic Jara",
            faction="Independent",
            vendor_type=VendorType.HUMAN_TRADER,
            inventory=[medkit],
            greeting="Got wounded? I've got Med Kits. 5 Drip each."
        )
        shared_state.add_vendor(vendor)

        assert len(shared_state.current_vendors) == 1, "Vendor should be in SharedState"
        assert shared_state.current_vendors[0].name == "Field Medic Jara"

        return shared_state

    @pytest.fixture
    def dm_with_shared_state(self, shared_state_with_vendor):
        """Create DM agent with SharedState containing persistent vendor."""
        dm = AIDMAgent(
            agent_id="dm_01",
            socket_path="/tmp/test.sock",
            llm_config={'provider': 'anthropic', 'model': 'claude-sonnet-4-5'}
        )
        dm.shared_state = shared_state_with_vendor
        return dm

    def test_config_scenario_includes_persistent_vendors_in_scenario_object(
        self,
        dm_with_shared_state
    ):
        """
        CRITICAL: When using config scenario, persistent vendors from SharedState
        must be included in the Scenario object.

        This test will FAIL until we fix dm._use_config_scenario()
        """
        scenario_config = {
            'theme': 'Medical Emergency',
            'location': 'Field Hospital',
            'situation': 'Rivan is injured and needs medical supplies.',
            'void_level': 2,
            'active_vendors': []  # Config says empty, but SharedState has vendors!
        }
        config = {
            'scenario': scenario_config,
            'initial_enemies': [],
            'initial_npcs': []
        }

        # Run config scenario setup (currently broken)
        import asyncio
        asyncio.run(dm_with_shared_state._use_config_scenario(scenario_config, config))

        # ASSERTION: Scenario object should include persistent vendors from SharedState
        assert dm_with_shared_state.current_scenario is not None
        assert dm_with_shared_state.current_scenario.active_vendors is not None
        assert len(dm_with_shared_state.current_scenario.active_vendors) == 1, \
            "Config scenario should include persistent vendor from SharedState"

        vendor = dm_with_shared_state.current_scenario.active_vendors[0]
        assert vendor.name == "Field Medic Jara"
        assert vendor.vendor_id == "vnd_medic"

    def test_config_scenario_includes_vendors_in_broadcast_payload(
        self,
        dm_with_shared_state
    ):
        """
        CRITICAL: scenario_data dict broadcast to players must include vendor inventory.

        Players read scenario_data['active_vendors'] to display vendor listings.
        If this is empty, players can't see vendor_id/item_id!
        """
        scenario_config = {
            'theme': 'Medical Emergency',
            'location': 'Field Hospital',
            'situation': 'Rivan is injured.',
            'void_level': 2
        }
        config = {'scenario': scenario_config}

        # Mock send_message_sync to capture payload
        messages_sent = []
        def capture_message(msg_type, recipient, payload):
            messages_sent.append({'type': msg_type, 'payload': payload})

        dm_with_shared_state.send_message_sync = capture_message

        # Run config scenario
        import asyncio
        asyncio.run(dm_with_shared_state._use_config_scenario(scenario_config, config))

        # Find SCENARIO_SETUP message
        setup_messages = [m for m in messages_sent if str(m['type']) == 'MessageType.SCENARIO_SETUP']
        assert len(setup_messages) == 1, "Should broadcast one SCENARIO_SETUP message"

        payload = setup_messages[0]['payload']
        scenario_data = payload['scenario']

        # ASSERTION: scenario_data must include active_vendors with full inventory
        assert 'active_vendors' in scenario_data, "scenario_data must have active_vendors field"
        assert len(scenario_data['active_vendors']) == 1, \
            "scenario_data should include persistent vendor from SharedState"

        vendor_data = scenario_data['active_vendors'][0]
        assert vendor_data['vendor_id'] == 'vnd_medic'
        assert vendor_data['name'] == 'Field Medic Jara'
        assert 'inventory' in vendor_data
        assert len(vendor_data['inventory']) > 0

        # Check inventory item has IDs
        item = vendor_data['inventory'][0]
        assert 'item_id' in item, "Items must have item_id for mechanical purchase"
        assert item['item_id'].startswith('itm_'), "item_id must follow itm_xxxx format"
        assert item['name'] == 'Med Kit'
        assert item['price_drip'] == 5

    def test_player_receives_vendor_inventory_in_scenario(
        self,
        dm_with_shared_state
    ):
        """
        END-TO-END: Verify player.current_scenario contains vendor data.

        This is what player.py reads to display vendor listings to LLM.
        """
        scenario_config = {
            'theme': 'Medical Emergency',
            'location': 'Field Hospital',
            'situation': 'Rivan is injured.',
            'void_level': 2
        }
        config = {'scenario': scenario_config}

        # Mock player agent
        player_scenario_data = None
        def capture_player_message(msg_type, recipient, payload):
            nonlocal player_scenario_data
            if 'scenario' in payload:
                player_scenario_data = payload['scenario']

        dm_with_shared_state.send_message_sync = capture_player_message

        # Run scenario
        import asyncio
        asyncio.run(dm_with_shared_state._use_config_scenario(scenario_config, config))

        # ASSERTION: Player receives vendor data
        assert player_scenario_data is not None
        assert 'active_vendors' in player_scenario_data
        assert len(player_scenario_data['active_vendors']) == 1

        vendor = player_scenario_data['active_vendors'][0]
        assert vendor['vendor_id'] == 'vnd_medic'
        assert len(vendor['inventory']) > 0
        assert vendor['inventory'][0]['item_id'].startswith('itm_')


# NOTE: TestVendorDisplayInPlayerPrompts class was removed as redundant.
# Vendor display in player prompts is tested by:
# 1. TestConfigScenarioVendors.test_player_receives_vendor_inventory_in_scenario (above)
# 2. Real LLM integration tests in session_config_purchase_test.json
# The above tests verify vendor_id/item_id reach player.current_scenario.
# Prompt formatting is inherently tested by successful purchase actions in live sessions.


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
