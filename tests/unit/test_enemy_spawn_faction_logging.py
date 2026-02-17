"""
Unit tests for enemy_spawn faction logging (Fix 2).

Problem: All enemy_spawn JSONL events have faction: null.
Fix: Add faction param to log_enemy_spawn() and pass it from enemy_combat.py.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestEnemySpawnFactionLogging:
    """Verify enemy_spawn events include faction field."""

    def _make_mock_logger(self):
        """Create a mock JSONLLogger that captures events."""
        logger = MagicMock()
        logger.session_id = "test-session-123"
        self.captured_events = []

        def capture_write(event):
            self.captured_events.append(event)

        logger._write_event = capture_write
        return logger

    def test_log_enemy_spawn_includes_faction(self):
        """log_enemy_spawn should include faction in the event dict."""
        from scripts.aeonisk.multiagent.mechanics import JSONLLogger

        logger = JSONLLogger.__new__(JSONLLogger)
        logger.session_id = "test-session-123"
        logger.log_file = None

        captured = []
        logger._write_event = lambda event: captured.append(event)

        logger.log_enemy_spawn(
            round_num=1,
            enemy_id="enemy_grunt_01",
            enemy_name="Thug #1",
            template="grunt",
            stats={"health": 40, "soak": 9},
            position="near_hostile",
            tactics="aggressive_melee",
            count=1,
            faction="ACG"
        )

        assert len(captured) == 1
        event = captured[0]
        assert event["event_type"] == "enemy_spawn"
        assert event["faction"] == "ACG"

    def test_log_enemy_spawn_faction_defaults_to_unknown(self):
        """When faction not provided, should default to 'Unknown'."""
        from scripts.aeonisk.multiagent.mechanics import JSONLLogger

        logger = JSONLLogger.__new__(JSONLLogger)
        logger.session_id = "test-session-123"
        logger.log_file = None

        captured = []
        logger._write_event = lambda event: captured.append(event)

        # Call without faction param (uses default)
        logger.log_enemy_spawn(
            round_num=1,
            enemy_id="enemy_grunt_02",
            enemy_name="Guard #1",
            template="enforcer",
            stats={"health": 50},
            position="far_enemy",
            tactics="tactical_ranged",
        )

        assert len(captured) == 1
        event = captured[0]
        assert event["faction"] == "Unknown"

    def test_log_enemy_spawn_preserves_existing_fields(self):
        """Adding faction shouldn't break existing event fields."""
        from scripts.aeonisk.multiagent.mechanics import JSONLLogger

        logger = JSONLLogger.__new__(JSONLLogger)
        logger.session_id = "test-session-123"
        logger.log_file = None

        captured = []
        logger._write_event = lambda event: captured.append(event)

        logger.log_enemy_spawn(
            round_num=3,
            enemy_id="enemy_elite_01",
            enemy_name="Commander Zek",
            template="elite",
            stats={"health": 80, "soak": 15},
            position="near_neutral",
            tactics="tactical_ranged",
            count=1,
            faction="Pantheon Security"
        )

        event = captured[0]
        assert event["enemy_id"] == "enemy_elite_01"
        assert event["enemy_name"] == "Commander Zek"
        assert event["template"] == "elite"
        assert event["round"] == 3
        assert event["count"] == 1
        assert event["faction"] == "Pantheon Security"
