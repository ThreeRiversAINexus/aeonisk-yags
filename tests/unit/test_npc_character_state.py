"""Every active entity appears in the life-state oracle, NPCs included.

Regression origin (sessions fa9d2891 and a8ca2b7f, 2026-08-09): `character_state`
had exactly two call sites — players and enemies. NPCs had none. Because
de-escalation preserves `agent_id` but moves the entity from `enemy_agents` to
`npc_agents`, an arrested subject dropped out of the record from that round on:

    r3 entity_lifecycle: "Matron Ysolde critically wounded and sedated by
    tranquilizer - converting to SUBDUED prisoner"

Her `character_state` rows stop at round 2. The lawful outcome — a successful
arrest — was precisely the moment the subject became unobservable, which also
made the DM's claims about prisoners ("remains prisoner, 66% HP stable")
impossible to verify against typed events.

`character_state_row` is the shared builder all three loops use, so the three
entity kinds cannot drift apart again.
"""

import pytest

from scripts.aeonisk.multiagent.session import character_state_row
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine


def make_mechanics():
    engine = MechanicsEngine.__new__(MechanicsEngine)
    engine.void_states = {}
    engine.soulcredit_states = {}
    engine.conditions = {}
    return engine


class Entity:
    """Stands in for EnemyAgent / NPCAgent (both expose these attributes)."""

    def __init__(self, agent_id="npc_1", name="Kneeling Cultist",
                 health=15, max_health=15, wounds=0, stuns=0, void_score=0):
        self.agent_id = agent_id
        self.name = name
        self.health = health
        self.max_health = max_health
        self.wounds = wounds
        self.stuns = stuns
        self.void_score = void_score
        self.position = "Near-Enemy"


class TestCharacterStateRow:

    def test_builds_a_row_for_an_npc(self):
        row = character_state_row(Entity(), make_mechanics(), agent="npc")

        assert row["character_id"] == "npc_1"
        assert row["character_name"] == "Kneeling Cultist"
        assert row["agent"] == "npc"

    def test_uses_the_shared_death_state_oracle(self):
        """A sedated prisoner at 0 HP must read as unconscious, not alive."""
        row = character_state_row(Entity(health=0), make_mechanics(), agent="npc")

        assert row["death_state"] == "unconscious"
        assert row["is_defeated"] is True

    def test_stun_ko_is_reflected(self):
        row = character_state_row(Entity(stuns=8), make_mechanics(), agent="npc")

        assert row["death_state"] == "unconscious"

    def test_reports_the_entity_void_score(self):
        """Enemies carry real void from their template (a boss shows Void 3/10);
        hardcoding 0 erased it."""
        row = character_state_row(
            Entity(void_score=3), make_mechanics(), agent="enemy")

        assert row["void_score"] == 3

    def test_reports_the_soulcredit_ledger(self):
        """Non-players accrue standing once the magistrate can name them."""
        mechanics = make_mechanics()
        mechanics.get_soulcredit_state("npc_1").adjust(-3, "III.3", round_num=1)

        row = character_state_row(Entity(), mechanics, agent="npc")

        assert row["soulcredit"] == -3

    def test_unjudged_entity_reports_zero(self):
        assert character_state_row(Entity(), make_mechanics(), agent="npc")["soulcredit"] == 0

    def test_carries_position_and_stuns(self):
        row = character_state_row(Entity(stuns=4), make_mechanics(), agent="npc")

        assert row["stuns"] == 4
        assert row["position"] == "Near-Enemy"

    def test_missing_attributes_do_not_raise(self):
        class Bare:
            agent_id = "x"
            name = "Bare"

        row = character_state_row(Bare(), make_mechanics(), agent="npc")

        assert row["character_id"] == "x"
        assert row["death_state"] in {"alive", "unconscious", "dead"}

    def test_converted_prisoner_keeps_its_agent_id(self):
        """agent_id is stable across enemy->NPC conversion, so the oracle can be
        followed across the transition."""
        shared = "enemy_boss_f39006f0"

        as_enemy = character_state_row(
            Entity(agent_id=shared), make_mechanics(), agent="enemy")
        as_npc = character_state_row(
            Entity(agent_id=shared), make_mechanics(), agent="npc")

        assert as_enemy["character_id"] == as_npc["character_id"] == shared
