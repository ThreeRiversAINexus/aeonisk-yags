"""Enemies must be reached through `enemy_combat`, never off `SharedState` (#120).

Three sites guarded on `hasattr(self.shared_state, 'enemy_agents')`. `SharedState`
has no such attribute — enemies live on `enemy_combat` and every other reader
goes through `getattr(self.enemy_combat, 'enemy_agents', [])`
(`shared_state.py:649`). So all three branches were dead, silently, since a
`hasattr` guard against an attribute that never existed simply never fires.

Two of them build **DM prompt context**, which is the larger half:

    dm.py:3400   "{n} enemies"          -> environment description
    dm.py:3456   "Outnumbered ({n} enemies)"  -> stakes description

Measured before the fix: `"Outnumbered ("` appeared **0 times in 60,728 LLM
events across 330 sessions**. Not once had the DM been told it was outnumbered,
in any session ever recorded. It was choosing difficulty, stakes and pacing
without a number the code plainly intended it to have.

The third (`dm.py:10378`) drops an escalated NPC on the floor: the NPC is removed
from its pool and the new enemy is added nowhere.

These tests use the real `SharedState` so that the guard cannot be "fixed" by
giving the fake an attribute production does not have — which is exactly how the
original defect stayed invisible.
"""

import pytest

from scripts.aeonisk.multiagent.shared_state import SharedState


class FakeCombat:
    def __init__(self, agents=()):
        self.enemy_agents = list(agents)


class FakeEnemy:
    def __init__(self, agent_id, is_active=True):
        self.agent_id = agent_id
        self.name = agent_id
        self.is_active = is_active
        self.health = 20


@pytest.fixture
def state():
    s = SharedState()
    s.enemy_combat = FakeCombat([FakeEnemy(f"enemy_grunt_{i:02d}") for i in range(1, 4)])
    return s


class TestSharedStateHasNoEnemyAgentsAttribute:
    """The premise of the bug, pinned so a future refactor cannot quietly make
    the old guard start working and mask what it was hiding."""

    def test_the_attribute_does_not_exist(self, state):
        assert not hasattr(state, "enemy_agents"), (
            "if SharedState gains this attribute, the three dm.py guards change "
            "behaviour silently — see #120")

    def test_enemies_are_reachable_through_enemy_combat(self, state):
        assert len(getattr(state.enemy_combat, "enemy_agents", [])) == 3


class TestTheAccessorUsedByTheFix:
    """`dm.py` now counts enemies the way every other reader already did."""

    def count(self, shared_state):
        from scripts.aeonisk.multiagent.dm import active_enemy_count
        return active_enemy_count(shared_state)

    def test_counts_the_enemies_that_exist(self, state):
        assert self.count(state) == 3

    def test_is_zero_when_there_is_no_combat_manager(self):
        assert self.count(SharedState()) == 0

    def test_is_zero_for_a_missing_shared_state(self):
        assert self.count(None) == 0

    def test_ignores_inactive_enemies(self, state):
        """A defeated enemy left as a tombstone must not inflate the count the
        DM is told about."""
        state.enemy_combat.enemy_agents.append(FakeEnemy("enemy_dead_01",
                                                         is_active=False))

        assert self.count(state) == 3

    def test_tolerates_agents_without_an_is_active_flag(self, state):
        class Bare:
            agent_id = "enemy_bare_01"

        state.enemy_combat.enemy_agents.append(Bare())

        assert self.count(state) == 4
