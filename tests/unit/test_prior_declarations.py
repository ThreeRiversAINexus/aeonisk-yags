"""Unit tests for prior_declarations() — the NPC-facing "what has already been
declared this round" context builder.

Regression origin (session fa9d2891, 2026-08-09): the inline version of this
logic in session.py carried two defects in three lines.

1. ``action.get('initiative', 0) > initiative_score`` raised
   ``TypeError: '>' not supported between instances of 'NoneType' and 'int'``
   whenever a stored declaration carried ``'initiative': None``. ``dict.get``
   returns its default only when the key is ABSENT, not when it is present and
   None. The exception was swallowed by a broad ``except`` in the NPC
   declaration loop, so the NPC forfeited its turn and was later flagged as a
   "ghost agent". Round 4 of that session had one PC, zero enemies and two
   ghosted NPCs.

2. The filter direction was inverted. ``_declared_actions`` is cleared at round
   start and declaration runs slowest-initiative-first, so every entry already
   in the buffer has a LOWER initiative than the agent currently declaring.
   Selecting ``initiative > mine`` therefore matched nothing, ever — the block
   was silently empty even when it did not crash.
"""

import pytest

from scripts.aeonisk.multiagent.session import prior_declarations


class TestPriorDeclarations:

    def test_none_initiative_does_not_raise(self):
        """A stored declaration with initiative=None must not blow up the caller.

        This is the exact shape that ghosted two NPCs in session fa9d2891.
        """
        declared = {
            "npc_01": [{"character_name": "Kneeling Cultist",
                        "initiative": None,
                        "description": "I keep my hands raised."}],
        }

        result = prior_declarations(declared)

        assert result == [("Kneeling Cultist", 0, "I keep my hands raised.")]

    def test_returns_everything_already_declared(self):
        """Declaration runs slowest-first, so the buffer holds only agents who
        have already gone. All of them are visible context."""
        declared = {
            "enemy_01": [{"character_name": "Void Cultist", "initiative": 16,
                          "description": "I advance."}],
            "player_02": [{"character_name": "Corin", "initiative": 18,
                           "description": "I take cover."}],
            "player_01": [{"character_name": "Nera", "initiative": 21,
                           "description": "I call for surrender."}],
        }

        result = prior_declarations(declared)

        assert len(result) == 3, (
            "the old '> initiative_score' filter returned nothing here, which is "
            "why NPCs never saw prior declarations"
        )
        assert [name for name, _, _ in result] == ["Void Cultist", "Corin", "Nera"]

    def test_sorted_by_initiative_ascending(self):
        """Slowest declarer first, matching declaration order."""
        declared = {
            "a": [{"character_name": "Fast", "initiative": 30, "description": "x"}],
            "b": [{"character_name": "Slow", "initiative": 5, "description": "y"}],
            "c": [{"character_name": "Mid", "initiative": 17, "description": "z"}],
        }

        assert [i for _, i, _ in prior_declarations(declared)] == [5, 17, 30]

    def test_none_initiative_sorts_without_error(self):
        """Mixed None and int initiatives must still sort (None coerced to 0)."""
        declared = {
            "a": [{"character_name": "Fast", "initiative": 30, "description": "x"}],
            "b": [{"character_name": "Unset", "initiative": None, "description": "y"}],
        }

        result = prior_declarations(declared)

        assert [name for name, _, _ in result] == ["Unset", "Fast"]

    def test_multiple_actions_per_agent_all_included(self):
        """The buffer stores a list per agent; every entry counts."""
        declared = {
            "player_01": [
                {"character_name": "Nera", "initiative": 21, "description": "first"},
                {"character_name": "Nera", "initiative": 21, "description": "second"},
            ],
        }

        assert len(prior_declarations(declared)) == 2

    def test_falls_back_to_agent_id_and_intent(self):
        """Missing character_name falls back to agent_id; missing description
        falls back to intent, then to a placeholder."""
        declared = {
            "npc_07": [{"initiative": 12, "intent": "plead"}],
            "npc_08": [{"initiative": 13}],
        }

        result = prior_declarations(declared)

        assert result[0] == ("npc_07", 12, "plead")
        assert result[1] == ("npc_08", 13, "unknown action")

    def test_empty_input(self):
        assert prior_declarations({}) == []
        assert prior_declarations(None) == []
