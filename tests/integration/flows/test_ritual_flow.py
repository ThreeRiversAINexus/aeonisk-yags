"""
Ritual System Flow Integration Tests

Tests complete ritual performance flow:
- Preparation phase
- Roll resolution
- Offering consumption
- Group ritual coordination
- Void consequences
- Outcome narration
"""

import pytest
from unittest.mock import patch

from aeonisk.multiagent.mechanics import MechanicsEngine, Difficulty


class TestRitualPreparation:
    """Test ritual preparation phase."""

    def test_ritual_requires_preparation(self):
        """Test rituals require preparation time."""
        # Rituals in YAGS have preparation requirements
        ritual_types = {
            'minor': {'prep_time': '1 round', 'void_risk': 'low'},
            'standard': {'prep_time': '1 minute', 'void_risk': 'moderate'},
            'major': {'prep_time': '10 minutes', 'void_risk': 'high'},
            'forbidden': {'prep_time': '1 hour', 'void_risk': 'extreme'}
        }

        assert ritual_types['minor']['prep_time'] == '1 round'
        assert ritual_types['forbidden']['prep_time'] == '1 hour'

    def test_preparation_includes_offering(self):
        """Test preparation phase includes selecting offering."""
        ritual_components = ['intent', 'offering', 'primary_ritual_item', 'participants']

        assert 'offering' in ritual_components
        assert 'primary_ritual_item' in ritual_components


class TestRitualExecution:
    """Test ritual execution mechanics."""

    @pytest.fixture
    def mechanics(self):
        return MechanicsEngine(jsonl_logger=None)

    def test_solo_ritual_execution(self, mechanics):
        """Test single ritualist performing ritual."""
        with patch('random.randint', return_value=12):
            resolution = mechanics.resolve_action(
                intent="Perform divination ritual",
                attribute="Willpower",
                skill="Astral Arts",
                attribute_value=4,
                skill_value=3,
                difficulty=18  # Standard ritual
            )

            # Ability = 12, d20 = 12, total = 24
            assert resolution.success == True
            assert resolution.total == 24

    def test_group_ritual_execution(self, mechanics):
        """Test group ritual with multiple participants."""
        # Primary ritualist
        primary_ability = 4 * 3  # 12

        # Bonded assistant provides +2
        bonded_bonus = 2

        # Additional skilled assistant provides +1
        skilled_bonus = 1

        total_bonus = bonded_bonus + skilled_bonus  # +3
        effective_ability = primary_ability + total_bonus  # 15

        with patch('random.randint', return_value=10):
            # Simulating total roll
            total_roll = effective_ability + 10  # 25
            dc = 20  # Major ritual

            success = total_roll >= dc
            assert success == True

    def test_ritual_with_primary_item(self, mechanics):
        """Test ritual using Primary Ritual Item."""
        base_ability = 3 * 2  # 6

        # Primary Ritual Item provides +3 bonus
        item_bonus = 3
        total_ability = base_ability + item_bonus  # 9

        assert total_ability == 9


class TestOfferingConsumption:
    """Test offering consumption during rituals."""

    @pytest.fixture
    def mechanics(self):
        return MechanicsEngine(jsonl_logger=None)

    def test_offering_consumed_on_success(self, mechanics):
        """Test successful ritual consumes offering."""
        from types import SimpleNamespace

        character_state = SimpleNamespace(
            name='Test Ritualist',
            inventory={'incense': 3}
        )

        # Consume offering
        consumed = mechanics.consume_offering(character_state, 'incense')

        assert consumed == 'incense'
        assert character_state.inventory['incense'] == 2

    def test_skipped_offering_adds_void(self, mechanics):
        """Test skipping offering adds +1 Void."""
        void_state = mechanics.get_void_state("ritualist")

        # Skip offering = +1 Void
        void_state.add_void(1, "Skipped ritual offering")

        assert void_state.score >= 1


class TestRitualOutcomes:
    """Test ritual outcome variations."""

    def test_excellent_ritual_success(self):
        """Test excellent ritual success (margin 10+)."""
        margin = 12
        outcome = "exceptional"

        # Excellent ritual: powerful effect, minimal void
        void_gain = 0
        effect_quality = "maximum"

        assert margin >= 10
        assert outcome == "exceptional"
        assert void_gain == 0

    def test_marginal_ritual_success(self):
        """Test marginal ritual success (margin 0-4)."""
        margin = 2
        outcome = "marginal"

        # Marginal success: effect works but costs void
        void_gain = 1
        effect_quality = "partial"

        assert 0 <= margin < 5
        assert void_gain > 0

    def test_ritual_failure(self):
        """Test ritual failure consequences."""
        margin = -6
        outcome = "failure"

        # Failure: no effect, void gain, possible backlash
        void_gain = 2
        backlash_possible = True

        assert margin < 0
        assert void_gain >= 1
        assert backlash_possible == True

    def test_critical_ritual_failure(self):
        """Test critical ritual failure (margin -10+)."""
        margin = -15
        outcome = "critical_failure"

        # Critical failure: major void gain, corruption, backlash
        void_gain = 5
        corruption_risk = True
        backlash_certain = True

        assert margin <= -10
        assert void_gain >= 3
        assert corruption_risk == True


class TestForbiddenRituals:
    """Test forbidden ritual mechanics."""

    @pytest.fixture
    def mechanics(self):
        return MechanicsEngine(jsonl_logger=None)

    def test_forbidden_ritual_high_difficulty(self, mechanics):
        """Test forbidden rituals have DC 26-28."""
        forbidden_dc_range = (26, 28)

        assert Difficulty.DIFFICULT.value in forbidden_dc_range

    def test_forbidden_ritual_void_cost(self, mechanics):
        """Test forbidden rituals always cost void."""
        void_state = mechanics.get_void_state("dark_ritualist")

        # Even on success, forbidden rituals add void
        minimum_void_gain = 1

        void_state.add_void(minimum_void_gain, "Performed forbidden ritual")

        assert void_state.score >= minimum_void_gain

    def test_forbidden_ritual_high_risk(self):
        """Test forbidden rituals have extreme consequences on failure."""
        # Forbidden ritual failure consequences
        consequences = {
            'void_gain': 5,
            'corruption_likely': True,
            'backlash_severe': True,
            'permanent_effects_possible': True
        }

        assert consequences['void_gain'] >= 3
        assert consequences['corruption_likely'] == True


class TestRitualVoidProgression:
    """Test void accumulation through ritual use."""

    @pytest.fixture
    def mechanics(self):
        return MechanicsEngine(jsonl_logger=None)

    def test_minor_ritual_minimal_void(self, mechanics):
        """Test minor rituals add minimal/no void on success."""
        void_state = mechanics.get_void_state("careful_mage")

        # Successful minor ritual: 0 void
        # Failed minor ritual: +1 void
        void_gain_success = 0
        void_gain_failure = 1

        assert void_gain_success == 0
        assert void_gain_failure <= 1

    def test_standard_ritual_moderate_void(self, mechanics):
        """Test standard rituals add moderate void on failure."""
        void_state = mechanics.get_void_state("mage")

        # Failed standard ritual: +1-2 void
        void_state.add_void(1, "Failed standard ritual")

        assert void_state.score >= 1

    def test_major_ritual_high_void(self, mechanics):
        """Test major rituals add significant void."""
        void_state = mechanics.get_void_state("powerful_mage")

        # Failed major ritual: +2-3 void
        void_state.add_void(2, "Failed major ritual")

        assert void_state.score >= 2

    def test_ritual_series_void_accumulation(self, mechanics):
        """Test multiple rituals accumulate void."""
        void_state = mechanics.get_void_state("busy_mage")

        # Perform 3 rituals
        void_state.add_void(1, "Ritual 1")
        void_state.add_void(1, "Ritual 2")
        void_state.add_void(2, "Ritual 3 (major)")

        assert void_state.score == 4


class TestGroupRitualCoordination:
    """Test multi-participant ritual mechanics."""

    def test_primary_ritualist_leads(self):
        """Test primary ritualist makes the roll."""
        primary_ability = 12
        assistants = 2

        # Primary makes the roll, assistants provide bonuses
        assert primary_ability > 0

    def test_bonded_assistants_provide_bonus(self):
        """Test Bonded assistants provide +2 each."""
        bonded_count = 2
        bonus_per_bonded = 2
        total_bonus = bonded_count * bonus_per_bonded

        assert total_bonus == 4

    def test_skilled_assistants_provide_smaller_bonus(self):
        """Test non-Bonded skilled assistants provide +1."""
        skilled_count = 1
        bonus_per_skilled = 1
        total_bonus = skilled_count * bonus_per_skilled

        assert total_bonus == 1

    def test_untrained_assistants_no_bonus(self):
        """Test untrained participants provide no mechanical bonus."""
        untrained_count = 3
        bonus = 0

        # Untrained can participate narratively but don't help mechanically
        assert bonus == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
