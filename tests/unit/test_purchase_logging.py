"""
Unit tests for purchase attempt JSONL logging.

Tests that both successful and failed purchase attempts are logged correctly
for ML training data.
"""

import pytest
import json
import tempfile
from pathlib import Path
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine, JSONLLogger
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.energy_economy import (
    EnergyPurse, Vendor, VendorItem, VendorType
)


class MockCharacterState:
    """Mock character for testing."""
    def __init__(self, name, agent_id, energy_purse, inventory=None):
        self.name = name
        self.agent_id = agent_id
        self.energy_purse = energy_purse
        self.inventory = inventory or {}


class TestPurchaseLogging:
    """Test purchase attempt logging to JSONL."""

    @pytest.fixture
    def setup_with_logging(self):
        """Create mechanics engine with JSONL logger."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Setup shared state
            shared_state = SharedState()

            # Create logger
            logger = JSONLLogger(session_id="test_purchase", output_dir=temp_dir)

            # Create mechanics with logger
            mechanics = MechanicsEngine(jsonl_logger=logger, shared_state=shared_state)
            shared_state.mechanics_engine = mechanics
            mechanics.current_round = 1

            # Create vendor
            vendor = Vendor(
                vendor_id="vnd_test",
                name="Test Shop",
                faction="Nexus",
                vendor_type=VendorType.VENDING_MACHINE,
                inventory=[
                    VendorItem(
                        item_id="itm_health",
                        name="Health Kit",
                        description="Restores HP",
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

            # Create test characters
            rich_player = MockCharacterState(
                name="Rich Player",
                agent_id="player_rich",
                energy_purse=EnergyPurse(drip=10, spark=5)
            )

            poor_player = MockCharacterState(
                name="Poor Player",
                agent_id="player_poor",
                energy_purse=EnergyPurse(drip=0, spark=0)
            )

            log_file = Path(temp_dir) / "session_test_purchase.jsonl"

            yield {
                'mechanics': mechanics,
                'logger': logger,
                'vendor': vendor,
                'rich_player': rich_player,
                'poor_player': poor_player,
                'log_file': log_file
            }

    def test_successful_purchase_logged(self, setup_with_logging):
        """Test that successful purchases are logged with correct schema."""
        mechanics = setup_with_logging['mechanics']
        logger = setup_with_logging['logger']
        rich_player = setup_with_logging['rich_player']
        log_file = setup_with_logging['log_file']

        # Validate and log successful purchase
        validation = mechanics.validate_purchase(
            character_state=rich_player,
            vendor_id="vnd_test",
            item_id="itm_health"
        )

        logger.log_purchase_attempt(
            round_num=1,
            player_id="player_rich",
            character_name="Rich Player",
            vendor_id="vnd_test",
            vendor_name="Test Shop",
            item_id="itm_health",
            item_name=validation.item_name,
            cost=validation.cost,
            player_currency=validation.player_currency,
            success=validation.can_afford,
            failure_reason=validation.failure_reason,
            shortage=validation.shortage
        )

        # Parse JSONL and find purchase event
        with open(log_file, 'r') as f:
            events = [json.loads(line) for line in f]

        purchase_events = [e for e in events if e.get('event_type') == 'purchase_attempt']
        assert len(purchase_events) == 1

        event = purchase_events[0]

        # Verify event schema
        assert event['event_type'] == 'purchase_attempt'
        assert event['player_id'] == 'player_rich'
        assert event['character_name'] == 'Rich Player'
        assert event['vendor_id'] == 'vnd_test'
        assert event['vendor_name'] == 'Test Shop'
        assert event['item_id'] == 'itm_health'
        assert event['item_name'] == 'Health Kit'
        assert event['cost'] == {'drip': 5}
        # Player currency includes all currencies (breath, grain, etc.)
        assert event['player_currency']['spark'] == 5
        assert event['player_currency']['drip'] == 10
        assert event['success'] == True
        assert event['failure_reason'] is None
        assert event['shortage'] is None
        assert event['round'] == 1

    def test_failed_purchase_logged(self, setup_with_logging):
        """Test that failed purchases are logged with shortage details."""
        mechanics = setup_with_logging['mechanics']
        logger = setup_with_logging['logger']
        poor_player = setup_with_logging['poor_player']
        log_file = setup_with_logging['log_file']

        # Validate and log failed purchase
        validation = mechanics.validate_purchase(
            character_state=poor_player,
            vendor_id="vnd_test",
            item_id="itm_expensive"
        )

        logger.log_purchase_attempt(
            round_num=1,
            player_id="player_poor",
            character_name="Poor Player",
            vendor_id="vnd_test",
            vendor_name="Test Shop",
            item_id="itm_expensive",
            item_name=validation.item_name,
            cost=validation.cost,
            player_currency=validation.player_currency,
            success=validation.can_afford,
            failure_reason=validation.failure_reason,
            shortage=validation.shortage
        )

        # Parse JSONL and find purchase event
        with open(log_file, 'r') as f:
            events = [json.loads(line) for line in f]

        purchase_events = [e for e in events if e.get('event_type') == 'purchase_attempt']
        assert len(purchase_events) == 1

        event = purchase_events[0]

        # Verify failure event schema
        assert event['event_type'] == 'purchase_attempt'
        assert event['player_id'] == 'player_poor'
        assert event['character_name'] == 'Poor Player'
        assert event['vendor_id'] == 'vnd_test'
        assert event['item_id'] == 'itm_expensive'
        assert event['item_name'] == 'Expensive Item'
        assert event['cost'] == {'spark': 2}
        # Player currency includes all currencies (breath, grain, etc.)
        assert event['player_currency']['spark'] == 0
        assert event['player_currency']['drip'] == 0
        assert event['success'] == False
        assert 'Insufficient currency' in event['failure_reason']
        assert event['shortage'] == {'spark': 2}

    def test_multiple_purchases_logged(self, setup_with_logging):
        """Test that multiple purchase attempts are logged in sequence."""
        mechanics = setup_with_logging['mechanics']
        logger = setup_with_logging['logger']
        rich_player = setup_with_logging['rich_player']
        poor_player = setup_with_logging['poor_player']
        log_file = setup_with_logging['log_file']

        # Log successful purchase
        validation1 = mechanics.validate_purchase(
            character_state=rich_player,
            vendor_id="vnd_test",
            item_id="itm_health"
        )

        logger.log_purchase_attempt(
            round_num=1,
            player_id="player_rich",
            character_name="Rich Player",
            vendor_id="vnd_test",
            vendor_name="Test Shop",
            item_id="itm_health",
            item_name=validation1.item_name,
            cost=validation1.cost,
            player_currency=validation1.player_currency,
            success=validation1.can_afford,
            failure_reason=validation1.failure_reason,
            shortage=validation1.shortage
        )

        # Log failed purchase
        validation2 = mechanics.validate_purchase(
            character_state=poor_player,
            vendor_id="vnd_test",
            item_id="itm_expensive"
        )

        logger.log_purchase_attempt(
            round_num=1,
            player_id="player_poor",
            character_name="Poor Player",
            vendor_id="vnd_test",
            vendor_name="Test Shop",
            item_id="itm_expensive",
            item_name=validation2.item_name,
            cost=validation2.cost,
            player_currency=validation2.player_currency,
            success=validation2.can_afford,
            failure_reason=validation2.failure_reason,
            shortage=validation2.shortage
        )

        # Parse JSONL and verify both events
        with open(log_file, 'r') as f:
            events = [json.loads(line) for line in f]

        purchase_events = [e for e in events if e.get('event_type') == 'purchase_attempt']
        assert len(purchase_events) == 2

        # Verify first (success) and second (failure) events
        assert purchase_events[0]['success'] == True
        assert purchase_events[0]['player_id'] == 'player_rich'

        assert purchase_events[1]['success'] == False
        assert purchase_events[1]['player_id'] == 'player_poor'
        assert purchase_events[1]['shortage'] == {'spark': 2}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
