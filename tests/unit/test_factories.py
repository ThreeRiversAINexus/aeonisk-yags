"""The factories must behave like the real thing — that is their whole job.

A builder that quietly lies is worse than the mock it replaces, because it comes
with a promise of realism attached.
"""

import pytest

from tests.factories import (
    FakeAgent, FakeCharacterState, FakeEnemyCombat, FakeSharedState,
    make_attributes, make_party, make_position,
)


class TestTheyFixTheHazardsMocksIntroduce:
    """Each test corresponds to one way a bare MagicMock lies."""

    def test_containers_iterate_what_was_put_in(self):
        """`list(mock.npc_agents)` is []; a test asking 'was every NPC
        processed?' therefore sees zero and passes. That is #89's shape."""
        npcs = [FakeAgent(agent_id="npc_1"), FakeAgent(agent_id="npc_2")]

        state = FakeSharedState(npcs=npcs)

        assert len(list(state.npc_agents)) == 2

    def test_comparisons_work(self):
        """`mock.health > 0` raises TypeError — literally #81's crash."""
        agent = FakeAgent(health=12)

        assert agent.health > 0
        assert agent.wounds < 6

    def test_names_are_strings(self):
        agent = FakeAgent(name="Nera Mereth")

        assert isinstance(agent.character_state.name, str)
        assert ", ".join([agent.character_state.name]) == "Nera Mereth"

    def test_position_unpacks(self):
        """`a, b = mock.calculate_range()` raises ValueError — today's
        de-escalation failure."""
        a, b = make_position("Near", "PC").calculate_range(make_position("Far", "PC"))

        assert isinstance(a, str) and isinstance(b, int)

    def test_inactive_entities_are_falsy(self):
        """`bool(mock.is_active)` is always True, so 'active only' filters
        never exclude anything."""
        active = [a for a in [FakeAgent(is_active=True), FakeAgent(is_active=False)]
                  if a.is_active]

        assert len(active) == 1


class TestAttributesMatchProduction:

    def test_no_legacy_health_key(self):
        """That exact shape hid #82 for eight months."""
        assert "Health" not in make_attributes()
        assert "Endurance" in make_attributes()

    def test_all_eight_yags_attributes(self):
        assert len(make_attributes()) == 8

    def test_overrides_are_validated(self):
        assert make_attributes(Endurance=5)["Endurance"] == 5

    def test_unknown_attribute_is_rejected(self):
        """'Presence' was accepted by the DM assessment path until #85; a
        factory must not reintroduce it quietly."""
        with pytest.raises(ValueError, match="not a YAGS attribute"):
            make_attributes(Presence=4)


class TestIdentityIsDistinct:

    def test_party_members_are_not_the_same_object(self):
        """Mocks share identity by default, hiding bugs where one entity's
        state is written over another's."""
        party = make_party(3)

        assert len({a.agent_id for a in party}) == 3
        assert len({id(a) for a in party}) == 3

    def test_registered_players_mirrors_the_party(self):
        state = FakeSharedState(players=make_party(2))

        assert [p["agent_id"] for p in state.registered_players] == \
            ["player_01", "player_02"]


class TestUsableWithTheRealCode:
    """The point is that production functions accept these unchanged."""

    def test_derive_death_state_reads_them(self):
        from scripts.aeonisk.multiagent.session import derive_death_state

        assert derive_death_state(FakeAgent(health=25)) == "alive"
        assert derive_death_state(FakeAgent(health=0)) == "unconscious"
        assert derive_death_state(FakeAgent(wounds=6)) == "dead"

    def test_log_fidelity_snapshots_them(self):
        from scripts.aeonisk.multiagent.log_fidelity import live_state

        state = FakeSharedState(players=make_party(2),
                                npcs=[FakeAgent(agent_id="npc_1")])
        snapshot = live_state(players=state.player_agents, npcs=state.npc_agents)

        assert set(snapshot) == {"player_01", "player_02", "npc_1"}

    def test_enemy_combat_container_is_real(self):
        combat = FakeEnemyCombat([FakeAgent(agent_id="e1"), FakeAgent(agent_id="e2")])

        assert [e.agent_id for e in combat.enemy_agents] == ["e1", "e2"]
