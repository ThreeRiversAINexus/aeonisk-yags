"""A conversion may not assert harm the log says never happened (#138).

Session a518e68b, round 1. The DM emitted, in one payload:

    {"enemy_conversions":[{"enemy_id":"enemy_void_cultist_01",
                           "resolution":"subdued",
                           "reason":"Tranquilized by Sergeant Corin Ireveth's
                                     non-lethal shot - rendered unconscious but alive."}],
     "reasoning":"Matron Ysolde Xalith tranquilized and unconscious ... converted
                  to subdued prisoner NPC. Threshold Acolyte Nyv Rift remains
                  active combatant"}

The structured id names Nyv Rift. The prose, twice, names Ysolde and says Nyv
Rift stays an active combatant. Corin had shot *Ysolde*
(`combat_action ... Tranquilizer Gun dealt=14 type=stun`). `character_state` for
the entity actually converted:

    r1..r4  hp=40/40 wounds=0 stuns=0 defeated=False death=alive

Never touched, in any round.

`validate_enemy_conversion` passed it because the id exists in the roster. That
is the whole check — nothing tested whether the *claim* about the entity was
true. So the untouched cultist became a prisoner, the tranquilised boss stayed a
notional enemy, and the typed record of the session reports nobody harmed.

The claim is falsifiable without any rules model: "subdued" and "killed" assert
a physical state, and `character_state` is the oracle for it. "Neutralized",
"convinced" and "fled" assert no such thing — a surrender needs no damage — so
they must keep passing, which is the half that stops this becoming a check that
fires on everything.
"""

import pytest

from scripts.aeonisk.multiagent.conversion_validation import (
    enemies_to_snapshot, validate_conversion_claim,
)
from scripts.aeonisk.multiagent.schemas.story_events import EnemyResolution
from tests.factories import FakeAgent


def enemy(agent_id="enemy_01", name="Threshold Acolyte Nyv Rift", health=40,
          max_health=40, wounds=0, stuns=0, is_active=True):
    agent = FakeAgent(agent_id=agent_id, name=name, health=health,
                      max_health=max_health, wounds=wounds, stuns=stuns)
    agent.is_active = is_active
    return agent


def ok(resolution, subject):
    valid, _ = validate_conversion_claim(resolution, subject)
    return valid


class TestPhysicalClaimsMustMatchTheOracle:
    """The exact shape of #138: an untouched entity declared subdued."""

    def test_subduing_an_untouched_enemy_is_rejected(self):
        assert not ok(EnemyResolution.SUBDUED, enemy())

    def test_killing_an_untouched_enemy_is_rejected(self):
        assert not ok(EnemyResolution.KILLED, enemy())

    def test_the_rejection_says_what_the_oracle_shows(self):
        _, reason = validate_conversion_claim(EnemyResolution.SUBDUED, enemy())

        assert "40/40" in reason and "subdued" in reason.lower()

    @pytest.mark.parametrize("subject", [
        enemy(stuns=8),                     # the tranquilised boss
        enemy(wounds=3),
        enemy(health=12),
        enemy(is_active=False),
    ], ids=["stunned", "wounded", "hurt", "already-inactive"])
    def test_a_real_incapacitation_still_converts(self, subject):
        assert ok(EnemyResolution.SUBDUED, subject)


class TestNonPhysicalClaimsNeedNoHarm:
    """The half that keeps this from firing on every peaceful resolution.

    An arrest, a negotiated surrender and a retreat are all lawful outcomes
    against an unharmed entity — and they are the outcomes the II.8 off-ramp
    exists to make reachable, so rejecting them would be worse than the bug.
    """

    @pytest.mark.parametrize("resolution", [
        EnemyResolution.NEUTRALIZED,
        EnemyResolution.CONVINCED,
        EnemyResolution.FLED,
        EnemyResolution.STORY_ADVANCED,
    ])
    def test_untouched_entity_may_still_be_resolved(self, resolution):
        assert ok(resolution, enemy())


class TestDefeatedEnemiesAreStillSnapshotted:
    """The second half of #138.

    `character_state` skipped enemies whose `is_active` had gone False, so an
    enemy stopped being snapshotted at the exact moment it became interesting.
    Ysolde was tranquilised during round 1 resolution, before the round-end
    snapshot ran, and therefore has **zero** rows in the entire session and no
    mention in `session_end`.

    Six lines below that loop, the NPC path already carries the comment for this
    same bug: "Without this an entity de-escalated to prisoner vanished from the
    oracle at the moment of arrest — the lawful outcome was the one that went
    unobserved." It was fixed for NPCs and never for enemies.
    """

    def test_an_inactive_enemy_is_still_snapshotted(self):
        downed = enemy(agent_id="enemy_boss_01", name="Matron Ysolde Xalith",
                       stuns=8, is_active=False)

        assert list(enemies_to_snapshot([downed])) == [downed]

    def test_active_enemies_are_unaffected(self):
        alive = enemy()

        assert list(enemies_to_snapshot([alive])) == [alive]

    def test_the_whole_roster_is_covered(self):
        roster = [enemy(agent_id="a"), enemy(agent_id="b", is_active=False)]

        assert len(list(enemies_to_snapshot(roster))) == 2

    def test_an_empty_roster_is_fine(self):
        assert list(enemies_to_snapshot([])) == []

    def test_none_is_tolerated(self):
        assert list(enemies_to_snapshot(None)) == []
