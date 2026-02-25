"""Tests for clock lifecycle improvements: reduced churn, better context."""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field

from scripts.aeonisk.multiagent.mechanics import MechanicsEngine, SceneClock


class TestDeadCodeRemoved:
    """Verify that the keyword-detection clock updater has been removed."""

    def test_update_clocks_from_action_does_not_exist(self):
        """update_clocks_from_action was keyword-detection based and should be removed."""
        engine = MechanicsEngine.__new__(MechanicsEngine)
        assert not hasattr(engine, 'update_clocks_from_action'), \
            "update_clocks_from_action should be removed — it uses keyword detection"


class TestBuildClockContext:
    """Test the DM's _build_clock_context() helper method."""

    def _make_dm_with_clocks(self, clocks: dict):
        """Create a minimal DM-like object with mocked shared state containing clocks."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent

        dm = AIDMAgent.__new__(AIDMAgent)
        dm.shared_state = MagicMock()
        mechanics = MagicMock()
        mechanics.scene_clocks = clocks
        dm.shared_state.mechanics_engine = mechanics
        dm.shared_state.get_mechanics_engine.return_value = mechanics
        return dm

    def test_empty_clocks_returns_empty_string(self):
        """No clocks = no context."""
        dm = self._make_dm_with_clocks({})
        result = dm._build_clock_context()
        assert result == ""

    def test_basic_clock_shows_progress_and_age(self):
        """Clock context should show current/max and round age."""
        clock = SceneClock(name="Investigation", current=2, maximum=6,
                          description="Tracking down the saboteur",
                          timeout_rounds=8)
        clock._rounds_alive = 3
        dm = self._make_dm_with_clocks({"Investigation": clock})

        result = dm._build_clock_context()
        assert "Investigation" in result
        assert "(2/6" in result
        assert "round 3/8" in result or "round 4/8" in result  # age info present
        assert "Tracking down the saboteur" in result

    def test_advance_regress_meanings_shown(self):
        """Clock context should include advance/regress meanings."""
        clock = SceneClock(name="Enemy Reinforcements", current=3, maximum=6,
                          description="Corporate response team mobilizing",
                          advance_meaning="response escalates",
                          regress_meaning="response delayed",
                          timeout_rounds=8)
        clock._rounds_alive = 4
        dm = self._make_dm_with_clocks({"Enemy Reinforcements": clock})

        result = dm._build_clock_context()
        assert "response escalates" in result
        assert "response delayed" in result

    def test_expiring_soon_warning(self):
        """Clocks within 2 rounds of timeout should show EXPIRING SOON warning."""
        clock = SceneClock(name="Escape Route", current=2, maximum=6,
                          description="Find exit before lockdown",
                          timeout_rounds=6)
        clock._rounds_alive = 5  # 5 >= 6 - 2 = 4, so should warn
        dm = self._make_dm_with_clocks({"Escape Route": clock})

        result = dm._build_clock_context()
        assert "EXPIRING SOON" in result

    def test_not_expiring_soon_no_warning(self):
        """Clocks with plenty of time left should NOT warn."""
        clock = SceneClock(name="Escape Route", current=2, maximum=6,
                          description="Find exit before lockdown",
                          timeout_rounds=8)
        clock._rounds_alive = 2  # 2 < 8 - 2 = 6, no warning
        dm = self._make_dm_with_clocks({"Escape Route": clock})

        result = dm._build_clock_context()
        assert "EXPIRING SOON" not in result

    def test_exact_clock_names_instruction_present(self):
        """Context should remind DM to use exact clock names."""
        clock = SceneClock(name="Test Clock", current=1, maximum=4,
                          description="Test", timeout_rounds=6)
        clock._rounds_alive = 0
        dm = self._make_dm_with_clocks({"Test Clock": clock})

        result = dm._build_clock_context()
        assert "EXACT" in result or "exact" in result

    def test_no_shared_state_returns_empty(self):
        """If shared_state is None, return empty string."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        dm = AIDMAgent.__new__(AIDMAgent)
        dm.shared_state = None
        result = dm._build_clock_context()
        assert result == ""

    def test_multiple_clocks_all_shown(self):
        """All active clocks should appear in the context."""
        clocks = {
            "Alpha": SceneClock(name="Alpha", current=1, maximum=4,
                               description="First", timeout_rounds=6),
            "Beta": SceneClock(name="Beta", current=3, maximum=6,
                              description="Second", timeout_rounds=8),
        }
        clocks["Alpha"]._rounds_alive = 1
        clocks["Beta"]._rounds_alive = 3
        dm = self._make_dm_with_clocks(clocks)

        result = dm._build_clock_context()
        assert "Alpha" in result
        assert "Beta" in result


class TestClockBudgetReminder:
    """Test that synthesis prompt includes clock budget guidance."""

    def test_budget_warning_at_4_plus_clocks(self):
        """With 4+ active clocks, budget should discourage new spawns."""
        # This tests the budget text generated in the synthesis prompt.
        # We verify it by checking the _get_clock_budget_text helper.
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        dm = AIDMAgent.__new__(AIDMAgent)
        result = dm._get_clock_budget_text(4)
        assert "do NOT spawn" in result.lower() or "do not spawn" in result.lower()

    def test_budget_moderate_at_2_3_clocks(self):
        """With 2-3 clocks, budget should allow cautious spawning."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        dm = AIDMAgent.__new__(AIDMAgent)
        result = dm._get_clock_budget_text(2)
        assert "spawn" in result.lower()
        # Should not have the strong "do NOT spawn" language
        assert "do not spawn" not in result.lower()

    def test_budget_permissive_at_0_1_clocks(self):
        """With 0-1 clocks, budget should allow spawning."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        dm = AIDMAgent.__new__(AIDMAgent)
        result = dm._get_clock_budget_text(0)
        assert "spawn" in result.lower()
        assert "may" in result.lower() or "you may" in result.lower()
