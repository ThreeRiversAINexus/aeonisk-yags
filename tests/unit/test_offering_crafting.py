"""
Unit tests for Offering Crafting System (TDD).

Tests verify players can craft offerings from materials using Attunement skill.
Per design: Simple conversion (Attunement check, no complex ritual required).

These tests are written BEFORE implementation (TDD).
"""

import pytest
from unittest.mock import patch
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.player import CharacterState


class TestOfferingCrafting:
    """Test crafting offerings from raw materials."""

    def setup_method(self):
        """Set up test character and mechanics engine."""
        self.mechanics = MechanicsEngine()

        # Create test character with Attunement skill
        self.character = CharacterState(
            name="Test Crafter",
            faction="Freeborn",
            attributes={
                'willpower': 7,
                'perception': 6,
                'intelligence': 5
            },
            skills={
                'attunement': 3,
                'astral_arts': 2,
                'investigation': 1
            },
            void_score=2,
            soulcredit=7,
            bonds=[],
            goals=[]
        )

    @patch('scripts.aeonisk.multiagent.mechanics.random.randint', return_value=6)
    def test_craft_blood_offering_success(self, mock_randint):
        """Test successfully crafting blood offering."""
        # Give character materials (represented as inventory item)
        self.character.inventory['blood_sample'] = 1

        # With mock returning 6 for each die: skill_pool(10) + 6 + 6 = 22 >= DC 15
        success, message, offering = self.mechanics.craft_offering(
            self.character,
            offering_type='blood_offering',
            materials=['blood_sample']
        )

        assert success is True
        assert offering == 'blood_offering'
        assert self.character.inventory['blood_offering'] == 1
        assert self.character.inventory['blood_sample'] == 0  # Consumed
        assert 'successfully' in message.lower() or 'crafted' in message.lower()

    @patch('scripts.aeonisk.multiagent.mechanics.random.randint', return_value=6)
    def test_craft_incense_success(self, mock_randint):
        """Test successfully crafting incense."""
        self.character.inventory['herbs'] = 2

        # With mock returning 6 for each die: skill_pool(10) + 6 + 6 = 22 >= DC 15
        success, message, offering = self.mechanics.craft_offering(
            self.character,
            offering_type='incense',
            materials=['herbs']
        )

        assert success is True
        assert offering == 'incense'
        assert self.character.inventory['incense'] == 1
        assert self.character.inventory['herbs'] == 1  # 1 consumed, 1 remaining

    @patch('scripts.aeonisk.multiagent.mechanics.random.randint', return_value=6)
    def test_craft_crystals_success(self, mock_randint):
        """Test successfully crafting crystals (offerings)."""
        self.character.inventory['raw_crystal'] = 1

        # With mock returning 6 for each die: skill_pool(10) + 6 + 6 = 22 >= DC 15
        success, message, offering = self.mechanics.craft_offering(
            self.character,
            offering_type='crystals',
            materials=['raw_crystal']
        )

        assert success is True
        assert offering == 'crystals'
        assert self.character.inventory['crystals'] == 1

    def test_craft_without_materials_fails(self):
        """Test crafting without required materials fails."""
        # No materials in inventory
        success, message, offering = self.mechanics.craft_offering(
            self.character,
            offering_type='blood_offering',
            materials=['blood_sample']
        )

        assert success is False
        assert offering is None
        assert 'no' in message.lower() or 'lack' in message.lower() or 'missing' in message.lower()

    def test_craft_with_low_skill_can_fail(self):
        """Test crafting can fail with low Attunement skill."""
        # Lower skill to make failure more likely
        self.character.skills['attunement'] = 1
        self.character.attributes['willpower'] = 3
        self.character.inventory['blood_sample'] = 5

        # Run multiple attempts to see if failures can occur
        results = []
        for _ in range(10):
            # Reset materials
            self.character.inventory['blood_sample'] = 1
            self.character.inventory['blood_offering'] = 0

            success, message, offering = self.mechanics.craft_offering(
                self.character,
                offering_type='blood_offering',
                materials=['blood_sample']
            )
            results.append(success)

        # With low skill (1d8+1d8-5 = DC 15), some should fail
        # Not requiring exact ratio, just that failure is possible
        assert False in results, "Low skill should allow failures"

    def test_craft_offering_difficulty_scales(self):
        """Test that crafting uses Attunement skill check (DC 15 base)."""
        # High skill character should succeed more often
        self.character.skills['attunement'] = 5
        self.character.attributes['willpower'] = 9
        self.character.inventory['blood_sample'] = 20

        successes = 0
        for _ in range(10):
            self.character.inventory['blood_sample'] = 1
            self.character.inventory['blood_offering'] = 0

            success, message, offering = self.mechanics.craft_offering(
                self.character,
                offering_type='blood_offering',
                materials=['blood_sample']
            )
            if success:
                successes += 1

        # High skill should succeed most of the time (allow some variance)
        assert successes >= 7, f"High skill should succeed often, got {successes}/10"

    def test_craft_offering_uses_attunement_skill(self):
        """Test that crafting specifically uses Attunement skill."""
        # Character with no Attunement but other skills
        no_attunement = CharacterState(
            name="No Attunement",
            faction="Freeborn",
            attributes={
                'willpower': 3,
                'perception': 8
            },
            skills={
                'attunement': 0,  # No skill
                'investigation': 5
            },
            void_score=2,
            soulcredit=7,
            bonds=[],
            goals=[]
        )
        no_attunement.inventory['blood_sample'] = 5

        # Should fail more often with no Attunement
        failures = 0
        for _ in range(10):
            no_attunement.inventory['blood_sample'] = 1
            no_attunement.inventory['blood_offering'] = 0

            success, message, offering = self.mechanics.craft_offering(
                no_attunement,
                offering_type='blood_offering',
                materials=['blood_sample']
            )
            if not success:
                failures += 1

        assert failures > 0, "Zero Attunement skill should cause some failures"

    def test_craft_offering_consumes_materials_on_failure(self):
        """Test that failed crafting still consumes materials."""
        # Set skill very low to ensure failure
        self.character.skills['attunement'] = 0
        self.character.attributes['willpower'] = 1
        self.character.inventory['blood_sample'] = 10

        # Try multiple times to get at least one failure
        for _ in range(20):
            if self.character.inventory['blood_sample'] == 0:
                break

            initial_materials = self.character.inventory['blood_sample']

            success, message, offering = self.mechanics.craft_offering(
                self.character,
                offering_type='blood_offering',
                materials=['blood_sample']
            )

            # Materials should be consumed regardless of success
            assert self.character.inventory['blood_sample'] < initial_materials

            if not success:
                # Found a failure, confirm material was consumed
                assert offering is None
                break
        else:
            pytest.skip("Could not generate failure in 20 attempts")

    def test_craft_multiple_offerings_depletes_materials(self):
        """Test crafting multiple offerings depletes materials correctly."""
        self.character.inventory['herbs'] = 5

        # Craft 3 incense
        for i in range(3):
            success, message, offering = self.mechanics.craft_offering(
                self.character,
                offering_type='incense',
                materials=['herbs']
            )

            if success:
                # Should have consumed 1 herb each time
                assert self.character.inventory['herbs'] == 5 - (i + 1)

    def test_craft_offering_types(self):
        """Test all major offering types can be crafted."""
        offering_recipes = {
            'blood_offering': 'blood_sample',
            'incense': 'herbs',
            'crystals': 'raw_crystal'
        }

        for offering_type, material in offering_recipes.items():
            # Fresh character for each test
            char = CharacterState(
                name="Test",
                faction="Freeborn",
                attributes={'willpower': 8, 'perception': 6},
                skills={'attunement': 5},
                void_score=2,
                soulcredit=7,
                bonds=[],
                goals=[]
            )
            char.inventory[material] = 1

            success, message, offering = self.mechanics.craft_offering(
                char,
                offering_type=offering_type,
                materials=[material]
            )

            # With high skill, should eventually succeed
            # If fails, try a few more times
            attempts = 1
            while not success and attempts < 5:
                char.inventory[material] = 1
                success, message, offering = self.mechanics.craft_offering(
                    char,
                    offering_type=offering_type,
                    materials=[material]
                )
                attempts += 1

            assert success is True, f"Failed to craft {offering_type} after {attempts} attempts"
            assert offering == offering_type

    def test_craft_offering_without_materials_key_error(self):
        """Test crafting gracefully handles missing material keys."""
        # No 'blood_sample' key in inventory at all
        success, message, offering = self.mechanics.craft_offering(
            self.character,
            offering_type='blood_offering',
            materials=['blood_sample']
        )

        assert success is False
        assert offering is None
        # Should not raise KeyError, should handle gracefully

    def test_craft_offering_invalid_offering_type(self):
        """Test crafting invalid offering type fails gracefully."""
        self.character.inventory['random_junk'] = 5

        success, message, offering = self.mechanics.craft_offering(
            self.character,
            offering_type='invalid_offering',
            materials=['random_junk']
        )

        assert success is False
        assert offering is None


class TestOfferingCraftingIntegration:
    """Integration tests for offering crafting with existing systems."""

    def setup_method(self):
        """Set up mechanics engine and character."""
        self.mechanics = MechanicsEngine()
        self.character = CharacterState(
            name="Integrated Tester",
            faction="Freeborn",
            attributes={'willpower': 7, 'perception': 6},
            skills={'attunement': 4},
            void_score=2,
            soulcredit=7,
            bonds=[],
            goals=[]
        )

    def test_crafted_offering_can_be_consumed(self):
        """Test that crafted offerings can be used in consume_offering()."""
        self.character.inventory['blood_sample'] = 1

        # Craft offering
        success, message, offering = self.mechanics.craft_offering(
            self.character,
            offering_type='blood_offering',
            materials=['blood_sample']
        )

        if not success:
            # Retry if failed (RNG)
            self.character.inventory['blood_sample'] = 1
            success, message, offering = self.mechanics.craft_offering(
                self.character,
                offering_type='blood_offering',
                materials=['blood_sample']
            )

        assert success is True
        assert self.character.inventory['blood_offering'] == 1

        # Consume the crafted offering
        consumed = self.mechanics.consume_offering(self.character, 'blood_offering')

        assert consumed == 'blood_offering'
        assert self.character.inventory['blood_offering'] == 0

    def test_craft_then_purchase_accumulates(self):
        """Test that crafted + purchased offerings stack correctly."""
        self.character.inventory['blood_sample'] = 1

        # Craft 1 offering
        success, message, offering = self.mechanics.craft_offering(
            self.character,
            offering_type='blood_offering',
            materials=['blood_sample']
        )

        if success:
            assert self.character.inventory['blood_offering'] == 1

            # Simulate purchase (manual addition)
            self.character.inventory['blood_offering'] += 1
            assert self.character.inventory['blood_offering'] == 2

            # Consume one
            consumed = self.mechanics.consume_offering(self.character, 'blood_offering')
            assert consumed == 'blood_offering'
            assert self.character.inventory['blood_offering'] == 1
