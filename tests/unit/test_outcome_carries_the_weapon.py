"""The narrator invented a weapon because it was never told one (#141).

Session a518e68b, round 1. Mechanics:

    combat_action  Matron Ysolde Xalith -> Sergeant Corin Ireveth
                   weapon='Heavy Machine Gun'  dealt=14  type=wound

Prose:

    "With a flick of her wrist, she hurls a crackling bolt of void energy across
     the chamber. The dark lightning streaks toward Sergeant Corin Ireveth..."

The obvious reading is that the narrator contradicted the log. The `AppliedOutcome`
it was actually handed says otherwise:

    intent: attack     method: attack     applied_effects: {}
    observable_facts:
        success: 'The attempt succeeds.'
        damage:  'Sergeant Corin Ireveth is badly wounded but remains conscious.'

There is no weapon in it, because `AppliedOutcome` had no field for one. The
model had a Tempest void-coven Matron and the word "attack", and wrote the only
scene those two facts support. It did not contradict the mechanics; it was never
given them.

So the fix is structured data, not a checker. A checker would have flagged the
symptom every round while the cause — a narrator briefed with `intent="attack"`
— went on producing it.

A weapon name is fiction, not mechanics: it carries no number and leaks nothing,
so it belongs in `prose_safe_summary` where the narrator actually reads it.
"""

import pytest

from aeonisk.multiagent.outcome_pipeline import (
    build_applied_outcome, _weapon_of,
)

from tests.unit.test_outcome_pipeline import _state


def _build(action):
    return build_applied_outcome(
        round_num=1,
        sequence=1,
        actor_id="enemy_boss_01",
        actor_name="Matron Ysolde Xalith",
        action=action,
        resolution_data={"success": True},
        before={"player_02": _state(health=27)},
        after={"player_02": _state(health=13)},
    )


class TestTheWeaponReachesTheOutcome:

    def test_a_declared_weapon_is_carried(self):
        outcome = _build({"intent": "attack", "weapon": "Heavy Machine Gun"})

        assert outcome.weapon == "Heavy Machine Gun"

    def test_the_resolved_weapon_wins_over_the_declared_one(self):
        """#131's gap, closed in the record too: what fired, not what was asked
        for. `_weapon_resolution` is memoised on the action by #134."""
        action = {
            "intent": "attack",
            "weapon": "Stun Baton (STUN)",
            "_weapon_resolution": ("Tranquilizer Gun", "stun", object()),
        }

        outcome = _build(action)

        assert outcome.weapon == "Tranquilizer Gun"
        assert outcome.damage_type == "stun"

    def test_an_unresolvable_weapon_does_not_masquerade_as_one(self):
        action = {"intent": "attack",
                  "_weapon_resolution": ("Unknown Weapon", "wound", None)}

        assert _weapon_of(action) == (None, None)

    def test_a_non_combat_action_carries_no_weapon(self):
        outcome = _build({"intent": "investigate the terminal"})

        assert outcome.weapon is None


class TestTheNarratorCanSeeIt:
    """`observable_facts` is what reaches the synthesis prompt. A weapon that
    lives only on the outcome object and never in a prose-safe summary would
    leave the narrator exactly as uninformed as before."""

    def test_the_weapon_appears_in_a_prose_safe_summary(self):
        outcome = _build({"intent": "attack", "weapon": "Heavy Machine Gun"})

        summaries = " ".join(f.prose_safe_summary for f in outcome.observable_facts)
        assert "Heavy Machine Gun" in summaries

    def test_the_summary_stays_free_of_mechanics(self):
        outcome = _build({"intent": "attack", "weapon": "Heavy Machine Gun"})

        summaries = " ".join(f.prose_safe_summary for f in outcome.observable_facts)
        assert not any(ch.isdigit() for ch in summaries), summaries

    def test_no_weapon_leaves_the_summary_as_it_was(self):
        outcome = _build({"intent": "investigate the terminal"})

        assert outcome.observable_facts[0].prose_safe_summary == "The attempt succeeds."
