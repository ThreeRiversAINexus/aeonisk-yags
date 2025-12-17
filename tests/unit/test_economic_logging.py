"""
Unit tests for economic action JSONL logging.

Tests verify that economic fields are properly populated in JSONL events:
1. Purchase actions populate effects.purchase (PurchaseEffect)
2. Transfer actions populate effects.currency_transfer / effects.item_transfer
3. Attunement actions populate effects.inventory_changes with seed consumption
4. Character state events include energy purse and seed counts

TDD: These tests are written FIRST to define expected behavior.
"""

import pytest
import json
import tempfile
from pathlib import Path
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine, JSONLLogger
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.energy_economy import (
    EnergyPurse, Vendor, VendorItem, VendorType, SeedType, Seed, Element, create_raw_seed
)


class MockCharacterState:
    """Mock character for testing."""
    def __init__(self, name, agent_id, energy_purse=None, inventory=None, void_score=0, soulcredit=0):
        self.name = name
        self.agent_id = agent_id
        self.energy_purse = energy_purse or EnergyPurse()
        self.inventory = inventory or {}
        self.void_score = void_score
        self.soulcredit = soulcredit


class TestCharacterStateEconomicFields:
    """Test character_state events include economic data (energy, seeds)."""

    @pytest.fixture
    def setup_logger(self):
        """Create JSONL logger in temp directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = JSONLLogger(session_id="test_char_state", output_dir=temp_dir)
            log_file = Path(temp_dir) / "session_test_char_state.jsonl"
            yield {'logger': logger, 'log_file': log_file}

    def test_character_state_includes_energy_fields(self, setup_logger):
        """Verify character_state events include energy purse data."""
        logger = setup_logger['logger']
        log_file = setup_logger['log_file']

        # Create character with specific currency amounts
        energy_data = {
            "breath": 5,
            "drip": 10,
            "grain": 3,
            "spark": 2,
            "hollow": 0
        }

        logger.log_character_state(
            round_num=1,
            character_id="player_01",
            character_name="Test Player",
            health=20,
            max_health=25,
            wounds=1,
            void_score=3,
            soulcredit=2,
            position="Near-PC",
            conditions=[],
            is_defeated=False,
            death_state="alive",
            agent="player",
            energy=energy_data,  # NEW: Energy purse data
            seeds={"raw": 2, "attuned": 1, "hollow": 0}  # NEW: Seed counts
        )

        # Parse JSONL and find character_state event
        with open(log_file, 'r') as f:
            events = [json.loads(line) for line in f]

        char_events = [e for e in events if e.get('event_type') == 'character_state']
        assert len(char_events) == 1

        event = char_events[0]

        # Verify energy fields exist and are populated
        assert 'energy' in event, "character_state should include 'energy' field"
        assert event['energy'] == energy_data, f"Expected energy={energy_data}, got {event.get('energy')}"

    def test_character_state_includes_seeds_fields(self, setup_logger):
        """Verify character_state events include seed counts."""
        logger = setup_logger['logger']
        log_file = setup_logger['log_file']

        seeds_data = {"raw": 2, "attuned": 1, "hollow": 0}

        logger.log_character_state(
            round_num=1,
            character_id="player_01",
            character_name="Test Player",
            health=20,
            max_health=25,
            wounds=1,
            void_score=3,
            soulcredit=2,
            position="Near-PC",
            conditions=[],
            is_defeated=False,
            death_state="alive",
            agent="player",
            energy={"breath": 5, "drip": 10, "grain": 3, "spark": 2, "hollow": 0},
            seeds=seeds_data  # NEW: Seed counts
        )

        # Parse JSONL and find character_state event
        with open(log_file, 'r') as f:
            events = [json.loads(line) for line in f]

        char_events = [e for e in events if e.get('event_type') == 'character_state']
        assert len(char_events) == 1

        event = char_events[0]

        # Verify seeds fields exist and are populated
        assert 'seeds' in event, "character_state should include 'seeds' field"
        assert event['seeds'] == seeds_data, f"Expected seeds={seeds_data}, got {event.get('seeds')}"

    def test_character_state_defaults_empty_economy(self, setup_logger):
        """Verify character_state defaults to empty dicts if no energy/seeds provided."""
        logger = setup_logger['logger']
        log_file = setup_logger['log_file']

        # Log without energy/seeds (backwards compat)
        logger.log_character_state(
            round_num=1,
            character_id="player_01",
            character_name="Test Player",
            health=20,
            max_health=25,
            wounds=1,
            void_score=3,
            soulcredit=2,
            position="Near-PC",
            conditions=[],
            is_defeated=False,
            death_state="alive",
            agent="player"
            # energy and seeds NOT provided
        )

        # Parse JSONL and find character_state event
        with open(log_file, 'r') as f:
            events = [json.loads(line) for line in f]

        char_events = [e for e in events if e.get('event_type') == 'character_state']
        assert len(char_events) == 1

        event = char_events[0]

        # Verify energy/seeds default to empty dicts (not missing)
        assert 'energy' in event, "character_state should always include 'energy' field"
        assert event['energy'] == {}, f"Expected energy={{}}, got {event.get('energy')}"
        assert 'seeds' in event, "character_state should always include 'seeds' field"
        assert event['seeds'] == {}, f"Expected seeds={{}}, got {event.get('seeds')}"


class TestActionResolutionPurchaseEffect:
    """Test that action_resolution events populate effects.purchase for purchase actions."""

    @pytest.fixture
    def setup_with_logging(self):
        """Create mechanics engine with JSONL logger and vendor."""
        with tempfile.TemporaryDirectory() as temp_dir:
            shared_state = SharedState()
            logger = JSONLLogger(session_id="test_purchase_effects", output_dir=temp_dir)
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
                    )
                ]
            )
            shared_state.add_vendor(vendor)

            log_file = Path(temp_dir) / "session_test_purchase_effects.jsonl"

            yield {
                'mechanics': mechanics,
                'logger': logger,
                'shared_state': shared_state,
                'log_file': log_file
            }

    def test_purchase_action_populates_effects_purchase(self, setup_with_logging):
        """Verify purchase actions log effects.purchase with PurchaseEffect fields.

        This tests that action_resolution events for purchase actions include:
        - effects.purchase.success
        - effects.purchase.vendor_name
        - effects.purchase.items_purchased
        - effects.purchase.currency_spent
        - effects.purchase.narrative
        """
        mechanics = setup_with_logging['mechanics']
        logger = setup_with_logging['logger']
        log_file = setup_with_logging['log_file']

        # Create mock action resolution with purchase effect
        purchase_data = {
            "success": True,
            "vendor_name": "Test Shop",
            "items_purchased": ["Health Kit"],
            "currency_spent": {"drip": 5},
            "narrative": "Transaction completed successfully",
            "failure_reason": None
        }

        inventory_changes = [
            {"item": "Health Kit", "delta": 1}
        ]

        # Log action_resolution with purchase effect populated
        logger.log_action_resolution(
            round_num=1,
            phase="action",
            agent_name="Test Player",
            action={"type": "purchase", "vendor_id": "vnd_test", "item_id": "itm_health"},
            resolution={
                "success": True,
                "success_tier": "auto",
                "narrative": "You purchased a Health Kit"
            },
            economy_changes={},
            clock_states={},
            effects=[],
            purchase_data=purchase_data,  # This should populate effects.purchase
            inventory_changes=inventory_changes
        )

        # Parse JSONL and find action_resolution event
        with open(log_file, 'r') as f:
            events = [json.loads(line) for line in f]

        action_events = [e for e in events if e.get('event_type') == 'action_resolution']
        assert len(action_events) == 1, f"Expected 1 action_resolution, got {len(action_events)}"

        event = action_events[0]

        # Verify effects.purchase is populated
        assert 'effects' in event, "action_resolution should have 'effects' field"
        effects = event['effects']

        assert 'purchase' in effects, "effects should include 'purchase' field for purchase actions"
        assert effects['purchase'] is not None, "effects.purchase should not be None"

        purchase = effects['purchase']
        assert purchase['success'] == True
        assert purchase['vendor_name'] == "Test Shop"
        assert purchase['items_purchased'] == ["Health Kit"]
        assert purchase['currency_spent'] == {"drip": 5}
        assert 'narrative' in purchase

        # Verify inventory_changes is also populated
        assert 'inventory_changes' in effects, "effects should include 'inventory_changes'"
        assert len(effects['inventory_changes']) > 0, "inventory_changes should not be empty for purchases"


class TestActionResolutionTransferEffect:
    """Test that action_resolution events populate effects.currency_transfer for transfers."""

    @pytest.fixture
    def setup_with_logging(self):
        """Create logger in temp directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            shared_state = SharedState()
            logger = JSONLLogger(session_id="test_transfer_effects", output_dir=temp_dir)
            mechanics = MechanicsEngine(jsonl_logger=logger, shared_state=shared_state)
            mechanics.current_round = 1

            log_file = Path(temp_dir) / "session_test_transfer_effects.jsonl"

            yield {
                'mechanics': mechanics,
                'logger': logger,
                'log_file': log_file
            }

    def test_transfer_action_populates_currency_transfer(self, setup_with_logging):
        """Verify transfer actions log effects.currency_transfer with full details.

        This tests that action_resolution events for transfer actions include:
        - effects.currency_transfer.from_character
        - effects.currency_transfer.to_character
        - effects.currency_transfer.drip/spark/grain/breath
        - effects.currency_transfer.purpose
        """
        logger = setup_with_logging['logger']
        log_file = setup_with_logging['log_file']

        # Create currency transfer data
        currency_transfer_data = {
            "from_character": "Ryn Thrace",
            "to_character": "Mira Solis",
            "drip": 10,
            "spark": 0,
            "grain": 0,
            "breath": 0,
            "purpose": "payment for information"
        }

        # Log action_resolution with currency_transfer effect
        logger.log_action_resolution(
            round_num=1,
            phase="action",
            agent_name="Ryn Thrace",
            action={"type": "transfer", "target": "Mira Solis", "currency": {"drip": 10}},
            resolution={
                "success": True,
                "success_tier": "auto",
                "narrative": "You press ten Drip talismans into Mira's palm"
            },
            economy_changes={},
            clock_states={},
            effects=[],
            currency_transfer_data=currency_transfer_data  # This should populate effects.currency_transfer
        )

        # Parse JSONL and find action_resolution event
        with open(log_file, 'r') as f:
            events = [json.loads(line) for line in f]

        action_events = [e for e in events if e.get('event_type') == 'action_resolution']
        assert len(action_events) == 1

        event = action_events[0]

        # Verify effects.currency_transfer is populated
        assert 'effects' in event
        effects = event['effects']

        assert 'currency_transfer' in effects, "effects should include 'currency_transfer' for transfers"
        assert effects['currency_transfer'] is not None, "effects.currency_transfer should not be None"

        transfer = effects['currency_transfer']
        assert transfer['from_character'] == "Ryn Thrace"
        assert transfer['to_character'] == "Mira Solis"
        assert transfer['drip'] == 10
        assert 'purpose' in transfer

    def test_transfer_action_populates_item_transfer(self, setup_with_logging):
        """Verify item transfers log effects.item_transfer with full details."""
        logger = setup_with_logging['logger']
        log_file = setup_with_logging['log_file']

        # Create item transfer data
        item_transfer_data = {
            "from_character": "Ash Kovalenko",
            "to_character": "Echo Rivera",
            "items": {"Medkit": 2, "Scanner": 1},
            "purpose": "Sharing medical supplies with wounded ally"
        }

        # Log action_resolution with item_transfer effect
        logger.log_action_resolution(
            round_num=1,
            phase="action",
            agent_name="Ash Kovalenko",
            action={"type": "transfer", "target": "Echo Rivera", "items": {"Medkit": 2}},
            resolution={
                "success": True,
                "success_tier": "auto",
                "narrative": "You hand over the medical supplies"
            },
            economy_changes={},
            clock_states={},
            effects=[],
            item_transfer_data=item_transfer_data  # This should populate effects.item_transfer
        )

        # Parse JSONL and find action_resolution event
        with open(log_file, 'r') as f:
            events = [json.loads(line) for line in f]

        action_events = [e for e in events if e.get('event_type') == 'action_resolution']
        assert len(action_events) == 1

        event = action_events[0]

        # Verify effects.item_transfer is populated
        effects = event['effects']

        assert 'item_transfer' in effects, "effects should include 'item_transfer' for item transfers"
        assert effects['item_transfer'] is not None, "effects.item_transfer should not be None"

        transfer = effects['item_transfer']
        assert transfer['from_character'] == "Ash Kovalenko"
        assert transfer['to_character'] == "Echo Rivera"
        assert transfer['items'] == {"Medkit": 2, "Scanner": 1}


class TestActionResolutionAttunementInventoryChanges:
    """Test that attunement actions populate effects.inventory_changes."""

    @pytest.fixture
    def setup_with_logging(self):
        """Create logger in temp directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            shared_state = SharedState()
            logger = JSONLLogger(session_id="test_attunement_inv", output_dir=temp_dir)
            mechanics = MechanicsEngine(jsonl_logger=logger, shared_state=shared_state)
            mechanics.current_round = 1

            log_file = Path(temp_dir) / "session_test_attunement_inv.jsonl"

            yield {
                'mechanics': mechanics,
                'logger': logger,
                'log_file': log_file
            }

    def test_attunement_populates_inventory_changes(self, setup_with_logging):
        """Verify attunement actions populate inventory_changes with seed consumption.

        When attunement succeeds, inventory_changes should show:
        - Seed consumed: {"item": "Raw Seed", "delta": -1}
        - Energy gained: {"item": "Drip", "delta": +20}
        """
        logger = setup_with_logging['logger']
        log_file = setup_with_logging['log_file']

        # Create attunement data
        attunement_data = {
            "success": True,
            "seed_consumed": True,
            "energy_type": "drip",
            "energy_gained": 20,
            "altar_id": None,
            "altar_bonus": 0,
            "echo_calibrator_used": False,
            "calibrator_check_success": None,
            "calibrator_void": 0,
            "upkeep_paid": False,
            "void_penalty": 0,
            "roll_total": 15,
            "roll_margin": 5
        }

        inventory_changes = [
            {"item": "Raw Seed", "delta": -1},
            {"item": "Drip", "delta": 20}
        ]

        # Log action_resolution with attunement effect and inventory_changes
        logger.log_action_resolution(
            round_num=1,
            phase="action",
            agent_name="Test Player",
            action={"type": "attune", "target_energy": "drip"},
            resolution={
                "success": True,
                "success_tier": "success",
                "narrative": "The seed dissolves into raw Drip energy"
            },
            economy_changes={},
            clock_states={},
            effects=[],
            attunement_data=attunement_data,
            inventory_changes=inventory_changes  # Should be populated for attunement
        )

        # Parse JSONL and find action_resolution event
        with open(log_file, 'r') as f:
            events = [json.loads(line) for line in f]

        action_events = [e for e in events if e.get('event_type') == 'action_resolution']
        assert len(action_events) == 1

        event = action_events[0]

        # Verify effects.attunement is populated
        effects = event['effects']
        assert 'attunement' in effects, "effects should include 'attunement'"
        assert effects['attunement'] is not None
        assert effects['attunement']['seed_consumed'] == True
        assert effects['attunement']['energy_gained'] == 20

        # Verify inventory_changes is populated
        assert 'inventory_changes' in effects, "effects should include 'inventory_changes'"
        inv_changes = effects['inventory_changes']
        assert len(inv_changes) >= 2, f"Expected at least 2 inventory changes, got {len(inv_changes)}"

        # Find seed consumption
        seed_change = next((c for c in inv_changes if c.get('item') == 'Raw Seed'), None)
        assert seed_change is not None, "Should have Raw Seed consumption in inventory_changes"
        assert seed_change['delta'] == -1, "Seed consumption should be -1"

        # Find energy gain
        energy_change = next((c for c in inv_changes if c.get('item') == 'Drip'), None)
        assert energy_change is not None, "Should have Drip gain in inventory_changes"
        assert energy_change['delta'] == 20, "Energy gain should be +20"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
