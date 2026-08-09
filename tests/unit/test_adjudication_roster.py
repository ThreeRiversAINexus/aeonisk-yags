"""The enforce magistrate must be able to name everyone it judges.

Regression origin (session fa9d2891, 2026-08-09): `apply_rulings()` resolved
each ruling's `character_name` against a roster built from
`shared_state.registered_players` alone. The magistrate rules on every
combatant, so all enemy and NPC rulings failed to match and were dropped:

    WARNING - Enforce: could not match ruling target
      'Tempest Industries Void Theorist': No character found matching ...
      Available characters: <the two PCs>

Five rulings applied, **eight dropped** — every dropped one aimed at the
antagonists, including a -3 for weaponizing Void against persons (III.3). In an
enforce run authored as an ethics probe, the criminals' ledger never moved.

The mechanics engine was never the blocker: get_void_state() and
get_soulcredit_state() are generic dicts keyed by arbitrary agent_id.
"""

import pytest

from scripts.aeonisk.multiagent.post_adjudication import build_adjudication_roster


class _Agent:
    """Minimal stand-in for EnemyAgent / NPCAgent."""

    def __init__(self, agent_id, name):
        self.agent_id = agent_id
        self.name = name


class TestBuildAdjudicationRoster:

    def test_includes_players(self):
        players = [{"agent_id": "player_01", "name": "Nera Mereth"}]

        roster = build_adjudication_roster(players, [], [])

        assert {"agent_id": "player_01", "name": "Nera Mereth"} in roster

    def test_includes_enemies(self):
        """The original failure mode: enemy rulings had nothing to match."""
        enemies = [_Agent("enemy_boss_f39006f0", "Tempest Industries Void Theorist")]

        roster = build_adjudication_roster([], enemies, [])

        assert [r["name"] for r in roster] == ["Tempest Industries Void Theorist"]
        assert roster[0]["agent_id"] == "enemy_boss_f39006f0"

    def test_includes_npcs(self):
        npcs = [_Agent("npc_kneeling_cultist_1040", "Kneeling Cultist")]

        roster = build_adjudication_roster([], [], npcs)

        assert roster[0]["name"] == "Kneeling Cultist"

    def test_merges_all_three_sources(self):
        roster = build_adjudication_roster(
            [{"agent_id": "player_01", "name": "Nera"},
             {"agent_id": "player_02", "name": "Corin"}],
            [_Agent("enemy_01", "Void Theorist")],
            [_Agent("npc_01", "Kneeling Cultist")],
        )

        assert len(roster) == 4
        assert {r["name"] for r in roster} == {
            "Nera", "Corin", "Void Theorist", "Kneeling Cultist"}

    def test_deduplicates_by_agent_id(self):
        """An entity converted enemy->NPC keeps its agent_id and can appear in
        both collections; it must land in the roster once."""
        shared = "enemy_boss_f39006f0"
        roster = build_adjudication_roster(
            [], [_Agent(shared, "Void Theorist")], [_Agent(shared, "Void Theorist")])

        assert len(roster) == 1

    def test_skips_entries_without_id_or_name(self):
        roster = build_adjudication_roster(
            [{"agent_id": "player_01"}, {"name": "Nameless"}],
            [_Agent("", "Blank Id")],
            [_Agent("npc_01", "")],
        )

        assert roster == []

    def test_handles_none_inputs(self):
        assert build_adjudication_roster(None, None, None) == []

    def test_player_entries_are_copied_not_aliased(self):
        """Mutating the roster must not corrupt shared_state.registered_players."""
        players = [{"agent_id": "player_01", "name": "Nera"}]

        roster = build_adjudication_roster(players, [], [])
        roster[0]["name"] = "mutated"

        assert players[0]["name"] == "Nera"


class TestApplyRulingsReachesNonPlayers:
    """End-to-end through apply_rulings with a roster that includes an enemy."""

    def test_enemy_ruling_is_applied(self):
        from scripts.aeonisk.multiagent.post_adjudication import apply_rulings
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine

        class _Ruling:
            character_name = "Tempest Industries Void Theorist"
            soulcredit_delta = -3
            void_delta = 0
            reason = "weaponizing Void against persons (III.3)"

        class _Rulings:
            rulings = [_Ruling()]

        mechanics = MechanicsEngine.__new__(MechanicsEngine)
        mechanics.void_states = {}
        mechanics.soulcredit_states = {}

        roster = build_adjudication_roster(
            [], [_Agent("enemy_boss_f39006f0", "Tempest Industries Void Theorist")], [])

        records = apply_rulings(_Rulings(), mechanics, roster, round_num=1)

        assert records[0]["applied"] is True
        assert records[0]["agent_id"] == "enemy_boss_f39006f0"
        assert mechanics.soulcredit_states["enemy_boss_f39006f0"].score == -3
