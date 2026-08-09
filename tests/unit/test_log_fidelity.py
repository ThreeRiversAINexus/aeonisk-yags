"""The oracle must catch the five divergences that actually happened.

Each test below reconstructs a real defect from the 2026-08-09 audit and asserts
the oracle reports it. A telemetry check that cannot fail is precisely what this
work exists to eliminate, so most of these are "prove it fails" tests rather than
"prove it passes".
"""

import pytest

from scripts.aeonisk.multiagent.log_fidelity import (
    EXTRA_ROW, MISSING_ROW, VALUE_MISMATCH,
    compare_round_summary, compare_rows, live_snapshot, live_state,
)


class Entity:
    def __init__(self, agent_id="e1", name="Someone", health=20, max_health=20,
                 wounds=0, stuns=0, void_score=0, is_active=True):
        self.agent_id = agent_id
        self.name = name
        self.health = health
        self.max_health = max_health
        self.wounds = wounds
        self.stuns = stuns
        self.void_score = void_score
        self.is_active = is_active


class Ledger:
    def __init__(self, score):
        self.score = score


class Mechanics:
    def __init__(self, **scores):
        self.soulcredit_states = {k: Ledger(v) for k, v in scores.items()}


def row_from(entity, mechanics=None, **overrides):
    """A faithful row, then break one field to simulate a writer bug."""
    row = live_snapshot(entity, mechanics)
    row.update(overrides)
    return row


class TestLiveSnapshot:

    def test_reads_mechanical_state(self):
        snap = live_snapshot(Entity(health=12, wounds=2, stuns=3))

        assert snap["health"] == 12
        assert snap["wounds"] == 2
        assert snap["stuns"] == 3

    def test_derives_death_state_independently(self):
        assert live_snapshot(Entity(health=0))["death_state"] == "unconscious"
        assert live_snapshot(Entity(wounds=6))["death_state"] == "dead"
        assert live_snapshot(Entity(stuns=8))["death_state"] == "unconscious"
        assert live_snapshot(Entity())["death_state"] == "alive"

    def test_prefers_the_mechanics_ledger_for_soulcredit(self):
        """The ledger is authoritative once the magistrate can name an entity."""
        entity = Entity(agent_id="enemy_boss_1")

        snap = live_snapshot(entity, Mechanics(enemy_boss_1=-8))

        assert snap["soulcredit"] == -8

    def test_missing_attributes_do_not_raise(self):
        class Bare:
            agent_id = "x"

        assert live_snapshot(Bare())["death_state"] in {"alive", "unconscious", "dead"}


class TestCatchesTheRealDefects:
    """One test per divergence that shipped."""

    def test_missing_npc_rows(self):
        """#89: 7 NPCs alive, zero rows in the log."""
        npcs = [Entity(agent_id="npc_1", name="Kneeling Cultist"),
                Entity(agent_id="npc_2", name="Coven Medic")]
        expected = live_state(npcs=npcs)

        divergences = compare_rows(expected, logged={},
                                   names={"npc_1": "Kneeling Cultist"})

        assert len(divergences) == 2
        assert all(d.kind == MISSING_ROW for d in divergences)
        assert "produced no character_state row" in str(divergences[0])

    def test_hardcoded_soulcredit_zero(self):
        """#80 fallout: the magistrate wrote -8, character_state said 0."""
        boss = Entity(agent_id="enemy_boss_1", name="Matron Ysolde Xalith")
        mechanics = Mechanics(enemy_boss_1=-8)
        expected = live_state(enemies=[boss], mechanics=mechanics)
        logged = {"enemy_boss_1": row_from(boss, mechanics, soulcredit=0)}

        divergences = compare_rows(expected, logged)

        assert len(divergences) == 1
        assert divergences[0].kind == VALUE_MISMATCH
        assert divergences[0].field == "soulcredit"
        assert divergences[0].expected == -8
        assert divergences[0].logged == 0

    def test_defeated_flag_disagreement(self):
        """#86: engine said defeated, the snapshot said otherwise."""
        downed = Entity(agent_id="player_01", name="Nera Mereth", health=0, wounds=5)
        expected = live_state(players=[downed])
        logged = {"player_01": row_from(downed, is_defeated=False,
                                        death_state="alive")}

        divergences = compare_rows(expected, logged)
        fields = {d.field for d in divergences}

        assert fields == {"is_defeated", "death_state"}

    def test_round_summary_counters_never_incremented(self):
        """#87: actions_attempted 0 and avg_margin 0.0 for a round with five."""
        resolutions = [{"margin": m} for m in (-12, -18, 10, 2, -5)]
        summary = {"actions_attempted": 0, "average_margin": 0.0}

        divergences = compare_round_summary(summary, resolutions)
        fields = {d.field for d in divergences}

        assert "actions_attempted" in fields
        assert "average_margin" in fields

    def test_stale_health_after_damage(self):
        """A writer that logs a cached value rather than the current one."""
        hurt = Entity(agent_id="player_02", health=4, wounds=3)
        expected = live_state(players=[hurt])
        logged = {"player_02": row_from(hurt, health=27, wounds=0)}

        divergences = compare_rows(expected, logged)

        assert {d.field for d in divergences} == {"health", "wounds"}


class TestFaithfulLogsAreQuiet:
    """The other half: it must not cry wolf."""

    def test_matching_state_yields_nothing(self):
        entities = [Entity(agent_id=f"e{i}", health=10 + i) for i in range(4)]
        mechanics = Mechanics(e0=3, e1=-2)
        expected = live_state(players=entities, mechanics=mechanics)
        logged = {e.agent_id: row_from(e, mechanics) for e in entities}

        assert compare_rows(expected, logged) == []

    def test_inactive_entities_are_not_expected(self):
        """Writers only log active enemies/NPCs; the oracle must agree."""
        expected = live_state(enemies=[Entity(agent_id="dead_1", is_active=False)])

        assert expected == {}
        assert compare_rows(expected, logged={}) == []

    def test_downed_players_are_still_expected(self):
        """A defeated player keeps producing rows — #86 turned on exactly that."""
        expected = live_state(players=[Entity(agent_id="p1", health=0, is_active=False)])

        assert "p1" in expected

    def test_unchecked_fields_are_ignored(self):
        """Narrative/position fields drift legitimately; only mechanics are checked."""
        entity = Entity(agent_id="e1")
        expected = live_state(players=[entity])
        logged = {"e1": {**row_from(entity), "position": "somewhere else",
                         "conditions": ["Sedated"]}}

        assert compare_rows(expected, logged) == []

    def test_partial_rows_only_check_present_fields(self):
        entity = Entity(agent_id="e1", health=9)
        expected = live_state(players=[entity])

        assert compare_rows(expected, {"e1": {"health": 9}}) == []

    def test_summary_with_no_resolutions_is_quiet(self):
        assert compare_round_summary({"actions_attempted": 0,
                                      "average_margin": 0.0}, []) == []

    def test_rounding_slack_on_the_average(self):
        resolutions = [{"margin": 1}, {"margin": 2}]

        assert compare_round_summary({"average_margin": 1.5}, resolutions) == []


class TestExtraRows:

    def test_row_for_an_unknown_entity(self):
        """A phantom row is as wrong as a missing one."""
        divergences = compare_rows({}, {"ghost_1": {"health": 5}})

        assert len(divergences) == 1
        assert divergences[0].kind == EXTRA_ROW


class TestDivergenceIsSerialisable:

    def test_as_dict_round_trips_for_the_typed_event(self):
        d = compare_rows(live_state(players=[Entity(agent_id="p1")]), {})[0]
        payload = d.as_dict()

        assert payload["kind"] == MISSING_ROW
        assert payload["agent_id"] == "p1"
