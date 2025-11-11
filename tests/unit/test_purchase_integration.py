"""
Integration tests for purchase processing.

Tests the full flow from DM structured output -> purchase processing -> inventory update.
"""

import pytest
from unittest.mock import Mock, MagicMock
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.player import CharacterState
from scripts.aeonisk.multiagent.energy_economy import EnergyPurse


class TestPurchaseProcessingIntegration:
    """Test purchase effect processing with real CharacterState."""

    @pytest.fixture
    def mechanics(self):
        """Create mechanics engine."""
        return MechanicsEngine(jsonl_logger=None)

    @pytest.fixture
    def character_with_currency(self):
        """Create character with energy_purse and currency."""
        char = CharacterState(
            name="Test Buyer",
            faction="Freeborn",
            attributes={
                "strength": 2,
                "agility": 3,
                "endurance": 3,
                "perception": 4,
                "intelligence": 4,
                "empathy": 3,
                "willpower": 3,
                "charisma": 5,
                "size": 10
            },
            skills={"charm": 5, "guile": 4},
            void_score=0,
            soulcredit=0,
            bonds=[],
            goals=["Test trading"],
            pronouns="they/them"
        )

        # Initialize energy_purse
        char.energy_purse = EnergyPurse()
        char.energy_purse.breath = 15
        char.energy_purse.drip = 10  # Enough to buy items
        char.energy_purse.grain = 0
        char.energy_purse.spark = 0

        # Initialize inventory
        char.inventory = {
            "blood_offering": 0,
            "incense": 0,
            "crystals": 0
        }

        return char

    def test_process_purchase_effect_dict_input(self, mechanics, character_with_currency):
        """
        Test that process_purchase_effect works with dict input from JSONL.

        This is the ACTUAL data structure from session JSONL.
        """
        # Exact structure from session_017dcf69 line 13
        purchase_effect_dict = {
            "success": True,
            "vendor_name": "Vexx's Stall Attendant (Fungal Hybrid)",
            "items_purchased": ["Blood Offering", "Incense Bundle"],
            "currency_spent": {"drip": 20},
            "narrative": "The gene-spliced attendant accepts your Drip",
            "failure_reason": None
        }

        # Character has 10 Drip - needs 20 (should fail)
        result = mechanics.process_purchase_effect(purchase_effect_dict, character_with_currency)

        # Should fail because insufficient currency
        assert result is False

    def test_process_purchase_effect_with_sufficient_currency(self, mechanics, character_with_currency):
        """Test purchase with sufficient currency."""
        # Give character enough currency
        character_with_currency.energy_purse.drip = 25

        purchase_effect_dict = {
            "success": True,
            "vendor_name": "Test Vendor",
            "items_purchased": ["Blood Offering", "Incense Bundle"],
            "currency_spent": {"drip": 20},
            "narrative": "The vendor accepts your currency and provides the ritual supplies",  # Min 20 chars
            "failure_reason": None
        }

        # Starting state
        assert character_with_currency.energy_purse.drip == 25
        assert character_with_currency.inventory["blood_offering"] == 0
        assert character_with_currency.inventory["incense"] == 0

        # Process purchase
        result = mechanics.process_purchase_effect(purchase_effect_dict, character_with_currency)

        # Verify results
        assert result is True
        assert character_with_currency.energy_purse.drip == 5  # 25 - 20
        assert character_with_currency.inventory.get("blood_offering", 0) >= 1
        assert character_with_currency.inventory.get("incense", 0) >= 1

    def test_purchase_failure_handling(self, mechanics, character_with_currency):
        """Test that failed purchases don't deduct currency."""
        purchase_effect_dict = {
            "success": False,
            "vendor_name": "Test Vendor",
            "items_purchased": [],
            "currency_spent": {},
            "narrative": "Insufficient funds for purchase attempt",
            "failure_reason": "Need 20 Drip, have 10"
        }

        starting_drip = character_with_currency.energy_purse.drip

        result = mechanics.process_purchase_effect(purchase_effect_dict, character_with_currency)

        assert result is False
        assert character_with_currency.energy_purse.drip == starting_drip  # No change

    def test_item_name_mapping(self, mechanics, character_with_currency):
        """Test that item names are correctly mapped to inventory keys."""
        character_with_currency.energy_purse.drip = 50

        purchase_effect_dict = {
            "success": True,
            "vendor_name": "Test Vendor",
            "items_purchased": [
                "Blood Offering (Sanctified)",  # Should map to blood_offering
                "Incense Bundle (x3)",          # Should map to incense
                "Med Kit",                      # Should map to med_kit
            ],
            "currency_spent": {"drip": 30},
            "narrative": "The vendor provides all requested ritual supplies",
            "failure_reason": None
        }

        result = mechanics.process_purchase_effect(purchase_effect_dict, character_with_currency)

        assert result is True
        # Check inventory (exact keys depend on mapping logic in process_purchase_effect)
        print(f"DEBUG: Final inventory = {character_with_currency.inventory}")

    def test_character_without_energy_purse_fails(self, mechanics):
        """Test that characters without energy_purse can't make purchases."""
        char_no_energy = CharacterState(
            name="Broke Character",
            faction="Freeborn",
            attributes={"strength": 2, "agility": 3, "endurance": 3, "perception": 4, "intelligence": 4, "empathy": 3, "willpower": 3, "charisma": 5, "size": 10},
            skills={},
            void_score=0,
            soulcredit=0,
            bonds=[],
            goals=[],
            pronouns="they/them"
        )
        # Set energy_purse to None to test handling
        char_no_energy.energy_purse = None

        purchase_effect_dict = {
            "success": True,
            "vendor_name": "Test Vendor",
            "items_purchased": ["Item"],
            "currency_spent": {"drip": 5},
            "narrative": "Purchase attempt",
            "failure_reason": None
        }

        result = mechanics.process_purchase_effect(purchase_effect_dict, char_no_energy)

        assert result is False  # Should fail gracefully


class TestSessionPurchaseFlow:
    """Test the full session flow for purchases."""

    def test_detect_why_purchases_not_processing(self):
        """
        Document the actual issue based on session analysis.

        Findings from session_017dcf69:
        1. DM populated effects.purchase correctly (line 13)
        2. effects.purchase exists in JSONL
        3. NO logs showing process_purchase_effect() was called
        4. NO "Successfully processed purchase" or error logs

        Possible causes:
        A. session.py line 1204-1212 not being reached
        B. purchase_effect extraction failing (effects.get('purchase') returns None)
        C. Silent exception being swallowed
        D. Code path not being executed for some reason
        """
        # This test documents the bug for investigation
        # Real verification requires debugging session.py:1200-1212
        pass

    def test_round_status_display_requirements(self):
        """
        Document requirements for round status display.

        Missing from round status:
        1. Currency (Drip/Breath/Grain/Spark)
        2. Inventory items (blood_offering, incense, etc.)
        3. Vendor presence (should show active vendors)

        Current behavior:
        - Round status only shows HP, position, void, faction, weapons
        - Currency/inventory require energy_purse to exist
        - Vendors not displayed at all
        """
        pass


class TestVendorDisplayInRoundStatus:
    """Test that vendors appear in round status."""

    def test_vendors_should_appear_in_round_status(self):
        """
        Document expectation: Vendors should be shown in round status.

        Expected output:
        ```
        === Round Status ===

          Player Characters:
            [19] Quinn | 26/26 HP | Void 0/10
                 └─ Currency: Drip:3 | Breath:15
                 └─ Inventory: Blood:1 | Incense:2

          Vendors Present:
            - Black Market Dealer "Vex" (Freeborn trader)
              Items: Blood Offering (8 Drip), Incense (12 Drip), ...
        ```

        Currently: Vendors NOT shown in round status at all.
        """
        pass
