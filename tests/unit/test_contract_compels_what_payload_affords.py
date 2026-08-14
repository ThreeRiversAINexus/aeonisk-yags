"""The contract must not compel a claim the payload cannot support (#162, #156).

One line of the synthesis contract does most of the damage when it drifts:

    Emit a state claim for every supplied damage, death, healing, condition,
    movement, or dialogue fact.

Every kind named there is a promise that the narrator can say something true
about that fact. #162 was that promise broken in two places at once: 88 condition
facts and 3 movement facts arrived carrying nothing but a label, and the narrator
was *required* to state them anyway. It did the only thing available — it guessed
— and a +2 buff narrated as a teammate being grappled.

That defect had no oracle. `inv_log_fidelity` compares the log to engine state
and both agreed; only reading the story against the mechanics found it. So this
file is the oracle: the compelled kinds are parsed out of the contract itself,
and each one must have a declared affordance that a real fact satisfies. Adding a
kind to the contract without affording anything fails here rather than in prose
six sessions later.

It also pins the correction to the audit that produced #162. That audit counted
*fields*, and reported dialogue (141), success (260) and failure (129) as
carrying "only a label" alongside condition and movement. They do not: a dialogue
fact carries the spoken line, and "The attempt succeeds" is complete by kind. The
real gap was 91 facts, not 621, and the assertions below say which is which.
"""

import re

import pytest
import yaml

from aeonisk.multiagent import synthesis_prompt
from aeonisk.multiagent.outcome_pipeline import (
    ConditionDetail, EntityStateSnapshot, _observable_facts,
)

CONTRACT_LINE = re.compile(
    r"Emit a state claim for every supplied (.+?) fact", re.S)


def compelled_kinds() -> set:
    """The kinds the shipped contract obliges the narrator to state."""
    template = yaml.safe_load(
        synthesis_prompt.MODULE_PATH.read_text(encoding="utf-8"))["user_prompt"]
    match = CONTRACT_LINE.search(template)
    assert match, (
        "the contract no longer carries the rule this file audits — if it was "
        "reworded, re-point CONTRACT_LINE; if it was dropped, nothing compels "
        "the narrator to state a condition and #162 can return unnoticed")
    return {word.strip(" ,") for word in re.split(r",|\bor\b", match.group(1))
            if word.strip(" ,")}


def _snap(**kw):
    base = dict(entity_id="e1", entity_type="enemy", name="Tarn",
                narrative_name="Cold Tarn", health=20, max_health=20)
    base.update(kw)
    return EntityStateSnapshot(**base)


def _facts(before, after, action=None):
    return _observable_facts("player_kael", "act", True,
                             {"e1": before}, {"e1": after})


def _only(facts, kind):
    matching = [f for f in facts if f.fact_kind == kind]
    assert matching, f"no {kind} fact was produced by the scenario"
    return matching[0]


# ── One affordance per compelled kind ────────────────────────────────────
# Each entry answers: what must a fact of this kind carry beyond its name, for
# the compelled state claim to be sayable without guessing?

def _afford_damage():
    fact = _only(_facts(_snap(health=20), _snap(health=8)), "damage")
    # Severity, not a number. "is badly wounded" is sayable; "-12 HP" is not.
    assert fact.severity in ("minor", "moderate", "severe", "critical")
    assert "Cold Tarn" in fact.prose_safe_summary


def _afford_death():
    fact = _only(_facts(_snap(health=20), _snap(health=0, life_state="dead")), "death")
    assert "killed" in fact.prose_safe_summary


def _afford_healing():
    fact = _only(_facts(_snap(health=8), _snap(health=18)), "healing")
    # Distinguishable from harm without reading the kind field.
    assert "improves" in fact.prose_safe_summary


def _afford_condition():
    """#162. The name alone does not say which way it cuts, and the names are
    model-authored: "Controlled Hold" and "Emboldened" are the same shape."""
    detail = ConditionDetail(name="Controlled Hold", penalty=2, duration=2,
                             description="+2 to restraint checks")
    fact = _only(_facts(_snap(), _snap(conditions=["Controlled Hold"],
                                       condition_details=[detail])), "condition")
    assert fact.polarity == "boon"
    assert "favour" in fact.prose_safe_summary


def _afford_movement():
    """#162. Both positions are in hand at the diff; discarding them left
    "changes position", the one fact about a move carrying no information."""
    fact = _only(_facts(_snap(position="Far-Enemy"),
                        _snap(position="Engaged")), "movement")
    assert fact.symbolic_value == "closed"
    assert "changes position" not in fact.prose_safe_summary


def _afford_dialogue():
    """Not a gap, despite what the #162 audit first reported. A dialogue fact
    carries the line itself, so the compelled claim is fully sayable."""
    from aeonisk.multiagent.outcome_pipeline import build_applied_outcome

    outcome = build_applied_outcome(
        round_num=1, sequence=1, actor_id="player_kael", actor_name="Kael",
        action={"intent": "speak", "dialogue_content": "Stand down."},
        resolution_data={"success": True}, before={}, after={})
    fact = _only(outcome.observable_facts, "dialogue")

    assert "Stand down." in fact.prose_safe_summary


AFFORDANCES = {
    "damage": _afford_damage,
    "death": _afford_death,
    "healing": _afford_healing,
    "condition": _afford_condition,
    "movement": _afford_movement,
    "dialogue": _afford_dialogue,
}


class TestEveryCompelledKindIsAfforded:

    def test_the_contract_compels_exactly_what_is_audited_here(self):
        """The meta-check, and the only part that catches a *future* #162.

        A kind added to the contract with no affordance declared below is a
        promise the payload has not been shown to keep — which is precisely the
        state condition and movement were in.
        """
        assert compelled_kinds() == set(AFFORDANCES), (
            "the contract's compelled-fact list and the affordances audited here "
            "have diverged; a compelled kind with no affordance is a claim the "
            "narrator must make and cannot support")

    @pytest.mark.parametrize("kind", sorted(AFFORDANCES))
    def test_a_real_fact_of_this_kind_carries_what_the_claim_needs(self, kind):
        AFFORDANCES[kind]()


class TestKindsTheContractDoesNotCompel:
    """`success`, `failure` and `attempt` are not in the compelled list, and the
    #162 audit wrongly counted them as gaps. They are complete by kind — there
    is nothing about "the attempt succeeds" that a payload field could add — and
    a rule compelling a claim for each would force a beat per no-op in rounds
    that are already half NPC passes."""

    def test_success_is_complete_without_extra_fields(self):
        fact = _only(_facts(_snap(), _snap()), "success")

        assert fact.prose_safe_summary == "The attempt succeeds."
        assert fact.severity is None and fact.polarity is None

    def test_they_are_deliberately_outside_the_compelled_set(self):
        assert not {"success", "failure", "attempt"} & compelled_kinds()
