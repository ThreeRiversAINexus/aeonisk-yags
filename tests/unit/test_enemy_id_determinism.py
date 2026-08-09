"""Enemy agent_ids must be deterministic, and must never be reused.

`enemy_spawner.py:87` minted them with `uuid.uuid4().hex[:8]`, which ignores the
session's `random_seed`. The same config with the same seed produced
`enemy_boss_2937e857` on one run and a different suffix on the next, so replay —
which keys on `(agent_id, call_sequence)` — missed every enemy stream and every
enemy fell back to DEFENSIVE. That is the #101 blocker.

Never-reuse matters just as much. `enemy_combat.py:2191` does
`self.enemy_agents = surviving`, dropping defeated enemies from the roster, so an
index derived from the *live* list would hand a fresh enemy the id of a dead one
— and agent_id is the stable key across conversions (CLAUDE.md) and the JSONL
corpus's entity identity.
"""

import pytest

from scripts.aeonisk.multiagent.enemy_spawner import next_enemy_agent_id, spawn_enemy


class TestTheIdGenerator:

    def test_same_inputs_give_the_same_id(self):
        assert next_enemy_agent_id("boss", set()) == next_enemy_agent_id("boss", set())

    def test_no_random_component(self):
        """The whole defect: a uuid suffix that changes every run."""
        assert next_enemy_agent_id("boss", set()) == "enemy_boss_01"

    def test_second_of_a_template_gets_the_next_index(self):
        taken = {"enemy_boss_01"}

        assert next_enemy_agent_id("boss", taken) == "enemy_boss_02"

    def test_templates_are_numbered_independently(self):
        taken = {"enemy_boss_01", "enemy_boss_02"}

        assert next_enemy_agent_id("grunt", taken) == "enemy_grunt_01"

    def test_never_reuses_a_retired_id(self):
        """A defeated enemy leaves the roster but keeps its identity in the log."""
        taken = {"enemy_grunt_01", "enemy_grunt_02", "enemy_grunt_03"}

        assert next_enemy_agent_id("grunt", taken) == "enemy_grunt_04"

    def test_fills_no_gaps(self):
        """`enemy_grunt_02` was defeated; its id is spent, not free."""
        taken = {"enemy_grunt_01", "enemy_grunt_02"}

        assert next_enemy_agent_id("grunt", taken) == "enemy_grunt_03"

    def test_tolerates_legacy_uuid_ids_in_the_taken_set(self):
        """Resumed sessions and old saves carry the old format."""
        taken = {"enemy_boss_2937e857"}

        assert next_enemy_agent_id("boss", taken) == "enemy_boss_01"

    def test_ids_keep_the_enemy_prefix(self):
        """`session.py:6671` and the invariants route on this prefix."""
        assert next_enemy_agent_id("void_cultist", set()).startswith("enemy_")


class TestSpawnEnemy:

    def spawn(self, **kw):
        return spawn_enemy(name="Test Unit", template_key="grunt",
                           position_str="Near-Enemy", faction="Tempest Industries",
                           **kw)

    def test_is_deterministic_across_spawns(self):
        assert self.spawn().agent_id == self.spawn().agent_id == "enemy_grunt_01"

    def test_honours_the_taken_set(self):
        assert self.spawn(taken_ids={"enemy_grunt_01"}).agent_id == "enemy_grunt_02"

    def test_explicit_agent_id_wins(self):
        assert self.spawn(agent_id="enemy_custom_99").agent_id == "enemy_custom_99"


class TestTheSpawnerTracksIssuedIds:
    """The manager must remember every id it ever issued, not just live ones."""

    @pytest.fixture
    def manager(self):
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager
        manager = EnemyCombatManager(shared_state=None)
        # `spawn_from_structured` is a silent no-op while disabled. Two of the
        # tests below compared empty rosters and passed vacuously until this
        # line existed — the exact "check that cannot fail" this suite hunts.
        manager.enabled = True
        return manager

    def make_spawn(self, count=1, template="grunt"):
        from scripts.aeonisk.multiagent.schemas.story_events import EnemySpawn
        from scripts.aeonisk.multiagent.schemas.shared_types import Position

        return EnemySpawn(archetype="Enforcer", template=template, count=count,
                          faction="Tempest Industries",
                          initial_position=Position.NEAR_ENEMY,
                          spawn_reason="reinforcements arrive from the annex")

    def test_a_batch_gets_distinct_ids(self, manager):
        manager.spawn_from_structured([self.make_spawn(count=3)])

        assert len({e.agent_id for e in manager.enemy_agents}) == 3

    def test_ids_are_stable_across_identical_sessions(self, manager):
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager

        manager.spawn_from_structured([self.make_spawn(count=2)])
        other = EnemyCombatManager(shared_state=None)
        other.enabled = True
        other.spawn_from_structured([self.make_spawn(count=2)])

        ids = [e.agent_id for e in manager.enemy_agents]
        assert ids, "nothing spawned; the comparison below would be vacuous"
        assert ids == [e.agent_id for e in other.enemy_agents]

    def test_a_later_spawn_does_not_reuse_a_removed_id(self, manager):
        """The `self.enemy_agents = surviving` hazard, exercised directly."""
        manager.spawn_from_structured([self.make_spawn(count=2)])
        retired = {e.agent_id for e in manager.enemy_agents}
        assert len(retired) == 2
        manager.enemy_agents = []

        manager.spawn_from_structured([self.make_spawn(count=1)])

        fresh = {e.agent_id for e in manager.enemy_agents}
        assert len(fresh) == 1
        assert not (retired & fresh)


class TestNPCIdsAreDeterministicToo:
    """NPCs carried the same uuid suffix (`session.py:4179`, `:7711`).

    Replaying `vp_kneeling_outcome_first` failed on exactly this: the engine
    asked for an `NPCAction` whose agent had no recorded stream. Both spawn
    sites already refuse to create a second NPC with an existing name, so the
    name alone identifies the entity and the uuid was redundant.
    """

    def test_derives_from_the_name(self):
        from scripts.aeonisk.multiagent.npc_agent import next_npc_agent_id

        assert next_npc_agent_id("Coven Medic Lyra Senn", set()) == \
            "npc_coven_medic_lyra_senn"

    def test_is_stable_across_runs(self):
        from scripts.aeonisk.multiagent.npc_agent import next_npc_agent_id

        assert next_npc_agent_id("Ren Halsk", set()) == \
            next_npc_agent_id("Ren Halsk", set())

    def test_punctuation_and_case_normalise(self):
        from scripts.aeonisk.multiagent.npc_agent import next_npc_agent_id

        assert next_npc_agent_id("Kael  Thresh-Vey's", set()) == "npc_kael_thresh_vey_s"

    def test_a_name_clash_still_gets_a_distinct_id(self):
        from scripts.aeonisk.multiagent.npc_agent import next_npc_agent_id

        assert next_npc_agent_id("Ren Halsk", {"npc_ren_halsk"}) == "npc_ren_halsk_02"

    def test_an_unnameable_npc_still_gets_an_id(self):
        from scripts.aeonisk.multiagent.npc_agent import next_npc_agent_id

        assert next_npc_agent_id("???", set()).startswith("npc_")

    def test_shared_state_remembers_issued_ids(self):
        """Retired NPCs must not have their ids handed out again."""
        from scripts.aeonisk.multiagent.npc_agent import next_npc_agent_id
        from scripts.aeonisk.multiagent.shared_state import SharedState
        from tests.factories import FakeAgent

        state = SharedState()
        state.add_npc(FakeAgent(agent_id="npc_ren_halsk"))
        state.npc_agents = []   # the NPC is gone; its identity is not

        assert next_npc_agent_id("Ren Halsk", state.issued_npc_ids) == "npc_ren_halsk_02"
