"""
Integration test for purchase flow through session.py.

Tests the ACTUAL flow:
1. Player declares purchase with vendor_id/item_id
2. session._handle_action_declared() pre-validates
3. Purchase executes mechanically (or fails)
4. State changes verified

This gives HIGH CONFIDENCE that session 340bd80e bug is fixed.
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from datetime import datetime
from scripts.aeonisk.multiagent.session import SelfPlayingSession
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.energy_economy import (
    EnergyPurse, Vendor, VendorItem, VendorType
)
from scripts.aeonisk.multiagent.base import Message, MessageType


class MockCharacterState:
    """Mock character for testing."""
    def __init__(self, name, agent_id, energy_purse, inventory=None, soulcredit=0):
        self.name = name
        self.agent_id = agent_id
        self.energy_purse = energy_purse
        self.inventory = inventory or {}
        self.soulcredit = soulcredit


class MockAgent:
    """Mock player agent."""
    def __init__(self, character_state):
        self.character_state = character_state
        self.agent_id = character_state.agent_id


class TestSessionPurchaseIntegration:
    """Test purchase flow through session._handle_action_declared()."""

    @pytest.fixture
    def setup_session(self):
        """Create minimal session setup for testing."""
        # Create shared state
        shared_state = SharedState()
        
        # Create mechanics with shared state
        mechanics = MechanicsEngine(jsonl_logger=None, shared_state=shared_state)
        shared_state.mechanics_engine = mechanics
        
        # Create vendor with items
        vendor = Vendor(
            vendor_id="vnd_test123",
            name="Test Shop",
            faction="Nexus",
            vendor_type=VendorType.VENDING_MACHINE,
            inventory=[
                VendorItem(
                    item_id="itm_health",
                    name="Health Kit",
                    description="Restores 10 HP",
                    inventory_key="health_kit",
                    price_drip=5
                ),
                VendorItem(
                    item_id="itm_expensive",
                    name="Expensive Item",
                    description="Costs 2 Spark",
                    inventory_key="expensive_item",
                    price_spark=2
                )
            ]
        )
        shared_state.add_vendor(vendor)
        
        # Create mock session (using replay_mode to bypass config file loading)
        session = SelfPlayingSession(
            replay_mode=True,
            replay_config={
                "session_name": "test_session",
                "agents": {"dm": {}, "players": []},
                "party_size": 2,
                "max_turns": 1
            }
        )
        session.shared_state = shared_state
        session._in_declaration_phase = True
        session._declared_actions = {}
        session._pending_declarations = {}
        session._current_initiative = {}
        
        # Create mock player agents
        rich_player = MockCharacterState(
            name="Rich Player",
            agent_id="player_rich",
            energy_purse=EnergyPurse(drip=10, spark=5),
            inventory={}
        )
        
        poor_player = MockCharacterState(
            name="Poor Player",
            agent_id="player_poor",
            energy_purse=EnergyPurse(drip=0, spark=0),
            inventory={}
        )
        
        session.agents = [
            MockAgent(rich_player),
            MockAgent(poor_player)
        ]
        
        return {
            'session': session,
            'shared_state': shared_state,
            'mechanics': mechanics,
            'vendor': vendor,
            'rich_player': rich_player,
            'poor_player': poor_player
        }

    def test_purchase_success_with_sufficient_funds(self, setup_session):
        """
        Test complete purchase flow: Rich player buys Health Kit (5 Drip).
        
        Flow:
        1. Player declares purchase with vendor_id/item_id
        2. session._handle_action_declared() pre-validates
        3. Purchase executes mechanically
        4. Currency deducted, item added
        """
        session = setup_session['session']
        rich_player = setup_session['rich_player']
        
        # Create purchase action message
        purchase_action = {
            'agent_id': 'player_rich',
            'character_name': 'Rich Player',
            'intent': 'Purchase Health Kit from Test Shop',
            'vendor_id': 'vnd_test123',  # ← KEY: ID-based purchase
            'item_id': 'itm_health',      # ← KEY: ID-based purchase
            'action_type': 'social'
        }
        
        message = Message(
            id='test_msg',
            type=MessageType.ACTION_DECLARED,
            sender='player_rich',
            recipient=None,
            payload=purchase_action,
            timestamp=datetime.now()
        )
        
        # Verify starting state
        assert rich_player.energy_purse.drip == 10
        assert rich_player.inventory.get('health_kit', 0) == 0
        
        # Handle action (this triggers pre-validation + execution)
        session._handle_action_declared(message)
        
        # Verify purchase was pre-validated and executed
        buffered_action = session._declared_actions['player_rich'][0]['action']
        
        assert 'purchase_validation' in buffered_action, "Pre-validation should have run"
        validation = buffered_action['purchase_validation']
        
        # Check validation results
        assert validation['can_afford'] == True, "Should be able to afford 5 Drip"
        assert validation['item_name'] == "Health Kit"
        assert validation['cost'] == {'drip': 5}
        assert validation['executed'] == True, "Purchase should have executed mechanically"
        
        # Verify state changes (THE KEY TEST)
        assert rich_player.energy_purse.drip == 5, "Should have deducted 5 Drip (10 - 5 = 5)"
        assert rich_player.inventory['health_kit'] == 1, "Should have added 1 Health Kit to inventory"
        
        print("✅ PASS: Purchase executed mechanically BEFORE DM narration")

    def test_purchase_failure_session_340bd80e_bug_is_fixed(self, setup_session):
        """
        CRITICAL TEST: Reproduce session 340bd80e bug and verify it's FIXED.
        
        Session 340bd80e scenario:
        - Poor player has 0 Spark, tries to buy item costing 2 Spark
        - OLD: DM narrates success, mechanics ERROR
        - NEW: Pre-validation catches shortage, purchase BLOCKED
        """
        session = setup_session['session']
        poor_player = setup_session['poor_player']
        
        # Simulate poor player trying to buy expensive item
        purchase_action = {
            'agent_id': 'player_poor',
            'character_name': 'Poor Player',
            'intent': 'Purchase Expensive Item',
            'vendor_id': 'vnd_test123',
            'item_id': 'itm_expensive',  # Costs 2 Spark
            'action_type': 'social'
        }
        
        message = Message(
            id='test_msg',
            type=MessageType.ACTION_DECLARED,
            sender='player_poor',
            recipient=None,
            payload=purchase_action,
            timestamp=datetime.now()
        )
        
        # Verify starting state (same as session 340bd80e)
        assert poor_player.energy_purse.spark == 0, "Player has 0 Spark"
        assert poor_player.inventory.get('expensive_item', 0) == 0
        
        # Handle action
        session._handle_action_declared(message)
        
        # Verify pre-validation caught the shortage
        buffered_action = session._declared_actions['player_poor'][0]['action']
        
        assert 'purchase_validation' in buffered_action, "Pre-validation should have run"
        validation = buffered_action['purchase_validation']
        
        # Check validation results (THE FIX)
        assert validation['can_afford'] == False, "Should NOT be able to afford 2 Spark"
        assert validation['shortage'] == {'spark': 2}, "Should show shortage of 2 Spark"
        assert validation['executed'] == False, "Purchase should NOT have executed"
        assert "Insufficient currency" in validation['failure_reason']
        
        # Verify state is UNCHANGED (this is the fix!)
        assert poor_player.energy_purse.spark == 0, "Spark should be unchanged (still 0)"
        assert poor_player.inventory.get('expensive_item', 0) == 0, "Item should NOT be added"
        
        print("✅ PASS: Session 340bd80e bug is FIXED - purchase blocked by pre-validation")

    def test_validation_failure_vendor_not_found(self, setup_session):
        """Test that missing vendor is handled gracefully."""
        session = setup_session['session']
        rich_player = setup_session['rich_player']
        
        purchase_action = {
            'agent_id': 'player_rich',
            'character_name': 'Rich Player',
            'intent': 'Purchase from nonexistent vendor',
            'vendor_id': 'vnd_missing',  # ← Vendor doesn't exist
            'item_id': 'itm_whatever',
            'action_type': 'social'
        }
        
        message = Message(
            id='test_msg',
            type=MessageType.ACTION_DECLARED,
            sender='player_rich',
            recipient=None,
            payload=purchase_action,
            timestamp=datetime.now()
        )
        
        session._handle_action_declared(message)
        
        buffered_action = session._declared_actions['player_rich'][0]['action']
        validation = buffered_action['purchase_validation']
        
        assert validation['can_afford'] == False
        assert validation['executed'] == False
        assert "not found" in validation['failure_reason'].lower()
        
        # State unchanged
        assert rich_player.energy_purse.drip == 10

    def test_validation_failure_item_not_in_inventory(self, setup_session):
        """Test that missing item is handled gracefully."""
        session = setup_session['session']
        rich_player = setup_session['rich_player']
        
        purchase_action = {
            'agent_id': 'player_rich',
            'character_name': 'Rich Player',
            'intent': 'Purchase nonexistent item',
            'vendor_id': 'vnd_test123',  # Vendor exists
            'item_id': 'itm_missing',     # Item doesn't exist
            'action_type': 'social'
        }
        
        message = Message(
            id='test_msg',
            type=MessageType.ACTION_DECLARED,
            sender='player_rich',
            recipient=None,
            payload=purchase_action,
            timestamp=datetime.now()
        )
        
        session._handle_action_declared(message)
        
        buffered_action = session._declared_actions['player_rich'][0]['action']
        validation = buffered_action['purchase_validation']
        
        assert validation['can_afford'] == False
        assert validation['executed'] == False
        assert "not in" in validation['failure_reason'].lower()

    def test_non_purchase_action_unaffected(self, setup_session):
        """Test that non-purchase actions aren't affected by purchase system."""
        session = setup_session['session']
        
        # Regular action without vendor_id/item_id
        regular_action = {
            'agent_id': 'player_rich',
            'character_name': 'Rich Player',
            'intent': 'Search the room',
            'action_type': 'investigate'
            # No vendor_id or item_id
        }
        
        message = Message(
            id='test_msg',
            type=MessageType.ACTION_DECLARED,
            sender='player_rich',
            recipient=None,
            payload=regular_action,
            timestamp=datetime.now()
        )
        
        session._handle_action_declared(message)
        
        buffered_action = session._declared_actions['player_rich'][0]['action']
        
        # Should NOT have purchase_validation
        assert 'purchase_validation' not in buffered_action, "Non-purchase actions shouldn't be validated as purchases"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
