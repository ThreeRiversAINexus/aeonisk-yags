"""One definition of "is this character down".

Regression origin (sessions fa9d2891 and a8ca2b7f, 2026-08-09): the
`end_state_snapshot` party block reported `is_defeated: False` for a character
whose `character_state` rows said `is_defeated: true` for three straight rounds.

Cause: the snapshot read `getattr(character_state, 'is_defeated', False)`, but —
as the comment above the character_state logger says outright — "Health/wounds/
stuns are stored on player agent, not CharacterState". The attribute did not
exist, so the getattr default made every character look unharmed, forever.

The oracle now lives in one place and both writers use it.
"""

import pytest

from scripts.aeonisk.multiagent.session import derive_death_state


class _Agent:
    def __init__(self, health=25, wounds=0, stuns=0):
        self.health = health
        self.wounds = wounds
        self.stuns = stuns


class TestDeriveDeathState:

    def test_healthy_is_alive(self):
        assert derive_death_state(_Agent()) == "alive"

    def test_six_wounds_is_dead(self):
        assert derive_death_state(_Agent(wounds=6)) == "dead"

    def test_zero_health_is_unconscious(self):
        """The fa9d2891 case: hp 0/26, wounds 5."""
        assert derive_death_state(_Agent(health=0, wounds=5)) == "unconscious"

    def test_stun_ko_is_unconscious(self):
        """The a8ca2b7f case: stuns pinned at 10 (Beaten threshold is 6)."""
        assert derive_death_state(_Agent(health=20, stuns=10)) == "unconscious"

    def test_wounds_outrank_stuns(self):
        assert derive_death_state(_Agent(health=0, wounds=6, stuns=10)) == "dead"

    def test_missing_attributes_do_not_raise(self):
        class _Bare:
            pass

        assert derive_death_state(_Bare()) in {"alive", "unconscious", "dead"}


class TestSnapshotUsesTheOracle:

    def test_snapshot_reports_defeat_for_a_downed_character(self):
        """Previously always False, because is_defeated was read off the wrong object."""
        from scripts.aeonisk.multiagent.session import party_snapshot_entry

        class _Char:
            name = "Nera Mereth"
            faction = "Sovereign Nexus"
            void_score = 1

        agent = _Agent(health=0, wounds=5)
        agent.character_state = _Char()

        entry = party_snapshot_entry(agent)

        assert entry["name"] == "Nera Mereth"
        assert entry["is_defeated"] is True
        assert entry["death_state"] == "unconscious"

    def test_snapshot_reports_alive_for_a_healthy_character(self):
        from scripts.aeonisk.multiagent.session import party_snapshot_entry

        class _Char:
            name = "Corin Ireveth"
            faction = "Pantheon Security"
            void_score = 2

        agent = _Agent(health=13, wounds=2)
        agent.character_state = _Char()

        entry = party_snapshot_entry(agent)

        assert entry["is_defeated"] is False
        assert entry["death_state"] == "alive"

    def test_stun_locked_character_is_defeated_in_the_snapshot(self):
        """a8ca2b7f: stuns 10 for three snapshots while the party block said fine."""
        from scripts.aeonisk.multiagent.session import party_snapshot_entry

        class _Char:
            name = "Nera Mereth"
            faction = "Sovereign Nexus"
            void_score = 1

        agent = _Agent(health=6, stuns=10)
        agent.character_state = _Char()

        assert party_snapshot_entry(agent)["is_defeated"] is True
