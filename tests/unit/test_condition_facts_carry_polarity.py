"""A condition fact was a name-only diff, and the name does not say which way it cuts (#162).

Session 3de9e609, round 2. The DM applied a condition to Cold Tarn:

    Condition(name="Controlled Hold", penalty=2, duration=2,
              description="+2 to restraint checks while held")

`penalty` is added to the roll (`mechanics.py:2477`,
`modifiers[condition.name] = condition.penalty`), so a *positive* penalty is a
bonus. Cold Tarn was being helped. What the narrator received was:

    {"fact_kind": "condition", "symbolic_value": "Controlled Hold",
     "prose_safe_summary": "Cold Tarn is affected by Controlled Hold."}

"affected by" is neutral, and the prose that came back read the hold as
something done *to* Cold Tarn. The narrator did not contradict the record — the
record it was handed had no sign in it.

This is not one condition's problem. Corpus-wide, 88 of 88 condition facts carry
nothing but a label, and the labels are model-authored and genuinely ambiguous:
"Controlled Hold", "Secured", "Stabilized", "Coordinated Watch", "Separated"
sit in the same list as "Emboldened", "Focused", "Stunned" and "Pinned Down".

Movement (3 of 3) had the same shape for a different reason: `old.position` and
`new.position` are both in hand at the diff and were both discarded for
"changes position". They cannot be passed through verbatim — `Near-PC`,
`Far-Enemy`, `Engaged` are range-band labels, and a band name in prose is a
mechanics leak. They have to be translated.

What must NOT cross into the payload: `penalty` itself, `duration` as a number,
and `Condition.description`, which is model-authored and routinely reads
"+2 to all rolls for 3 rounds". The sign is prose-safe; the number is not.
"""

import pytest

from aeonisk.multiagent.outcome_pipeline import (
    ConditionDetail,
    EntityStateSnapshot,
    ObservableFact,
    _conditions,
    _condition_details,
    _observable_facts,
    prose_safe_outcome_payload,
    build_applied_outcome,
)


def _snap(*, conditions=None, details=None, position=None):
    return EntityStateSnapshot(
        entity_id="enemy_tarn",
        entity_type="enemy",
        name="Cold Tarn",
        narrative_name="Cold Tarn",
        health=20,
        max_health=20,
        position=position,
        conditions=conditions or [],
        condition_details=details or [],
    )


def _facts(before, after):
    return _observable_facts("player_kael", "restrain", True,
                             {"enemy_tarn": before}, {"enemy_tarn": after})


def _kind(facts, kind):
    return [f for f in facts if f.fact_kind == kind]


BOON = ConditionDetail(name="Controlled Hold", penalty=2, duration=2,
                       description="+2 to restraint checks while held")
HINDRANCE = ConditionDetail(name="Off-Balance", penalty=-2, duration=1,
                            description="next attack at -2")
NEUTRAL = ConditionDetail(name="Marked", penalty=0, duration=-1,
                          description="tracked by the watch")
BARRIER = ConditionDetail(name="Astral Barrier", penalty=0, duration=2,
                          description="Blocks 10 damage", protection_amount=10)


class TestThePolarityReachesTheFact:

    def test_a_bonus_condition_is_a_boon(self):
        facts = _facts(_snap(), _snap(conditions=["Controlled Hold"], details=[BOON]))

        assert _kind(facts, "condition")[0].polarity == "boon"

    def test_a_penalty_condition_is_a_hindrance(self):
        facts = _facts(_snap(), _snap(conditions=["Off-Balance"], details=[HINDRANCE]))

        assert _kind(facts, "condition")[0].polarity == "hindrance"

    def test_a_zero_modifier_condition_is_neutral(self):
        facts = _facts(_snap(), _snap(conditions=["Marked"], details=[NEUTRAL]))

        assert _kind(facts, "condition")[0].polarity == "neutral"

    def test_a_barrier_is_a_boon_despite_a_zero_penalty(self):
        """`Condition(name="Astral Barrier", penalty=0, protection_amount=10)` —
        the shipped example in `shared_types.py`. It absorbs damage; reading it
        off `penalty` alone would file it as neither help nor harm."""
        facts = _facts(_snap(), _snap(conditions=["Astral Barrier"], details=[BARRIER]))

        assert _kind(facts, "condition")[0].polarity == "boon"

    def test_the_summary_says_which_way_it_cuts(self):
        """The field the narrator actually reads. `polarity` is for checkers."""
        gained = _kind(_facts(_snap(), _snap(conditions=["Controlled Hold"],
                                             details=[BOON])), "condition")[0]
        suffered = _kind(_facts(_snap(), _snap(conditions=["Off-Balance"],
                                               details=[HINDRANCE])), "condition")[0]

        assert "favour" in gained.prose_safe_summary
        assert "against" in suffered.prose_safe_summary
        assert gained.prose_safe_summary != suffered.prose_safe_summary

    def test_the_condition_is_still_named(self):
        """Whatever else changes, the narrator must still be able to say what
        happened, and `symbolic_value` is what the coverage check reads."""
        fact = _kind(_facts(_snap(), _snap(conditions=["Controlled Hold"],
                                           details=[BOON])), "condition")[0]

        assert fact.symbolic_value == "Controlled Hold"
        assert "Controlled Hold" in fact.prose_safe_summary
        assert "Cold Tarn" in fact.prose_safe_summary

    def test_a_lasting_condition_reads_differently_from_a_passing_one(self):
        lasting = _kind(_facts(_snap(), _snap(conditions=["Marked"],
                                              details=[NEUTRAL])), "condition")[0]
        passing = _kind(_facts(_snap(), _snap(conditions=["Off-Balance"],
                                              details=[HINDRANCE])), "condition")[0]

        assert "until it is resolved" in lasting.prose_safe_summary
        assert "until it is resolved" not in passing.prose_safe_summary


class TestNoMechanicsCrossOver:
    """The dealbreaker. A number in the prose payload is worse than a vague
    summary — it ends up in the story."""

    @pytest.mark.parametrize("detail", [BOON, HINDRANCE, NEUTRAL, BARRIER])
    def test_no_number_from_the_condition_appears_in_the_summary(self, detail):
        fact = _kind(_facts(_snap(), _snap(conditions=[detail.name],
                                           details=[detail])), "condition")[0]

        assert not any(ch.isdigit() for ch in fact.prose_safe_summary)

    def test_the_model_authored_description_is_never_quoted(self):
        """`description` is written by the DM and reads "+2 to all rolls for 3
        rounds". It is the single most leak-prone string in the condition."""
        detail = ConditionDetail(name="Inspired", penalty=2, duration=3,
                                 description="+2 to all rolls for 3 rounds")

        fact = _kind(_facts(_snap(), _snap(conditions=["Inspired"],
                                           details=[detail])), "condition")[0]

        assert "+2" not in fact.prose_safe_summary
        assert "rolls" not in fact.prose_safe_summary

    def test_a_fact_with_no_polarity_does_not_carry_a_null_one(self):
        """Caught by the byte-identity oracle in `test_harness_case_kinds`, and
        pinned here where the cause is.

        A plain `model_dump()` puts `"polarity": null` on all ~530 non-condition
        facts in the corpus. That is noise in a payload whose whole discipline is
        that nothing appears in it without earning its place — and it re-renders
        every recorded prompt differently from the one that was actually sent,
        which destroys the harness's only exact oracle. Absent means "does not
        apply"; null would mean "applies, unknown", and nothing produces that.
        """
        outcome = build_applied_outcome(
            round_num=2, sequence=1, actor_id="player_kael", actor_name="Kael",
            action={"intent": "shoot"}, resolution_data={"success": True},
            before={"enemy_tarn": _snap()},
            after={"enemy_tarn": _snap(conditions=["Controlled Hold"], details=[BOON])})

        facts = prose_safe_outcome_payload([outcome])[0]["facts"]

        by_kind = {f["fact_kind"]: f for f in facts}
        assert "polarity" not in by_kind["success"]
        assert by_kind["condition"]["polarity"] == "boon"

    def test_the_detail_never_reaches_the_prose_payload(self):
        """`condition_details` lives on the state snapshot, which the
        whitelist in `prose_safe_outcome_payload` excludes. The numbers belong
        in the record — that is what the record is for — and nowhere near the
        narrator."""
        outcome = build_applied_outcome(
            round_num=2, sequence=1, actor_id="player_kael", actor_name="Kael",
            action={"intent": "restrain"}, resolution_data={"success": True},
            before={"enemy_tarn": _snap()},
            after={"enemy_tarn": _snap(conditions=["Inspired"], details=[
                ConditionDetail(name="Inspired", penalty=2, duration=3,
                                description="+2 to all rolls for 3 rounds")])},
        )

        rendered = str(prose_safe_outcome_payload([outcome]))

        assert "condition_details" not in rendered
        assert "+2 to all rolls" not in rendered
        assert "penalty" not in rendered


class TestTheOldShapeStillWorks:
    """Every recorded session has `conditions: List[str]` and no details.
    A fixture cannot be repaired, only replaced — so the fact builder has to
    keep producing something honest when the sign is genuinely unknown."""

    def test_a_condition_with_no_detail_keeps_the_neutral_wording(self):
        fact = _kind(_facts(_snap(), _snap(conditions=["Wavering"])), "condition")[0]

        assert fact.prose_safe_summary == "Cold Tarn is affected by Wavering."

    def test_an_unknown_polarity_is_none_not_neutral(self):
        """"Nobody looked" and "it is genuinely balanced" are different claims,
        and a checker built on this field must be able to tell them apart."""
        fact = _kind(_facts(_snap(), _snap(conditions=["Wavering"])), "condition")[0]

        assert fact.polarity is None

    def test_a_snapshot_without_details_still_validates(self):
        assert EntityStateSnapshot(
            entity_id="e", entity_type="enemy", name="n", narrative_name="n",
            conditions=["Stunned"]).condition_details == []

    def test_an_old_fact_without_polarity_still_validates(self):
        assert ObservableFact(
            fact_kind="condition", subject_id="e", causing_actor_id="a",
            symbolic_value="Stunned",
            prose_safe_summary="n is affected by Stunned.").polarity is None

    def test_a_detail_for_a_condition_that_did_not_change_is_ignored(self):
        """Details are carried for the whole entity; only the diff makes facts."""
        before = _snap(conditions=["Controlled Hold"], details=[BOON])
        after = _snap(conditions=["Controlled Hold", "Off-Balance"],
                      details=[BOON, HINDRANCE])

        facts = _kind(_facts(before, after), "condition")

        assert [f.symbolic_value for f in facts] == ["Off-Balance"]
        assert facts[0].polarity == "hindrance"


class TestMovementSaysWhichWay:

    def test_closing_to_contact_is_not_merely_a_position_change(self):
        facts = _kind(_facts(_snap(position="Near-Enemy"),
                             _snap(position="Engaged")), "movement")

        assert facts[0].symbolic_value == "closed"
        assert "changes position" not in facts[0].prose_safe_summary

    def test_leaving_contact_reads_as_breaking_away(self):
        facts = _kind(_facts(_snap(position="Engaged"),
                             _snap(position="Near-PC")), "movement")

        assert facts[0].symbolic_value == "disengaged"

    def test_far_to_near_closes_the_distance(self):
        facts = _kind(_facts(_snap(position="Far-Enemy"),
                             _snap(position="Near-Enemy")), "movement")

        assert facts[0].symbolic_value == "closed"

    def test_near_to_far_falls_back(self):
        facts = _kind(_facts(_snap(position="Near-PC"),
                             _snap(position="Far-PC")), "movement")

        assert facts[0].symbolic_value == "withdrew"

    def test_crossing_between_anchors_at_the_same_range_is_still_a_move(self):
        """`Near-PC` -> `Near-Enemy` is a real change with no direction in it.
        Inventing one would be worse than saying nothing."""
        facts = _kind(_facts(_snap(position="Near-PC"),
                             _snap(position="Near-Enemy")), "movement")

        assert facts[0].symbolic_value == "moved"

    def test_an_unrecognised_band_does_not_crash_or_invent(self):
        facts = _kind(_facts(_snap(position="somewhere odd"),
                             _snap(position="Engaged")), "movement")

        assert facts[0].symbolic_value == "closed"
        facts = _kind(_facts(_snap(position="somewhere odd"),
                             _snap(position="elsewhere")), "movement")
        assert facts[0].symbolic_value == "moved"

    @pytest.mark.parametrize("old,new", [("Near-PC", "Engaged"),
                                         ("Engaged", "Far-Enemy"),
                                         ("Far-PC", "Near-PC"),
                                         ("Near-PC", "Near-Enemy")])
    def test_no_range_band_label_ever_reaches_the_prose(self, old, new):
        """The reason positions could not simply be passed through. `Near-PC` in
        a story is the same defect class as a clock or a round number."""
        fact = _kind(_facts(_snap(position=old), _snap(position=new)), "movement")[0]

        lowered = fact.prose_safe_summary.lower()
        for band in ("near", "far", "engaged", "-pc", "-enemy"):
            assert band not in lowered, fact.prose_safe_summary


class TestDetailExtraction:

    class _Cond:
        def __init__(self, name, penalty=0, duration=-1, description="",
                     type="wound", protection_amount=None):
            self.name, self.penalty, self.duration = name, penalty, duration
            self.description, self.type = description, type
            self.protection_amount = protection_amount

    class _Entity:
        def __init__(self, agent_id, status_effects=()):
            self.agent_id = agent_id
            self.status_effects = list(status_effects)

    class _Mechanics:
        def __init__(self, conditions):
            self.conditions = conditions

    def test_details_come_from_both_places_names_do(self):
        """`_conditions` reads `entity.status_effects` *and*
        `mechanics.conditions[agent_id]`. A detail source that read only one
        would silently give half the conditions an unknown polarity."""
        entity = self._Entity("e1", [self._Cond("Off-Balance", penalty=-2)])
        mechanics = self._Mechanics({"e1": [self._Cond("Inspired", penalty=2)]})

        details = _condition_details(entity, mechanics)

        assert {d.name: d.penalty for d in details} == {"Off-Balance": -2, "Inspired": 2}

    def test_every_named_condition_has_a_detail(self):
        """The invariant that keeps the two lists from drifting: if a name is
        in `conditions` and not in `condition_details`, its fact silently loses
        its sign again and nothing says so."""
        entity = self._Entity("e1", [self._Cond("A", penalty=-1)])
        mechanics = self._Mechanics({"e1": [self._Cond("B", penalty=1)]})

        names = set(_conditions(entity, mechanics))

        assert {d.name for d in _condition_details(entity, mechanics)} == names

    def test_a_bare_string_condition_yields_no_detail(self):
        """`_conditions` tolerates plain strings in `status_effects`; a string
        has no sign, and guessing one would be an invention."""
        entity = self._Entity("e1", ["Legacy String Condition"])

        assert _condition_details(entity, None) == []
        assert _conditions(entity, None) == ["Legacy String Condition"]

    def test_no_mechanics_engine_is_not_an_error(self):
        entity = self._Entity("e1", [self._Cond("A", penalty=-1)])

        assert [d.name for d in _condition_details(entity, None)] == ["A"]

    def test_a_duplicate_across_both_sources_appears_once(self):
        cond = self._Cond("Stunned", penalty=-3)
        entity = self._Entity("e1", [cond])
        mechanics = self._Mechanics({"e1": [cond]})

        assert len(_condition_details(entity, mechanics)) == 1

    def test_a_condition_object_missing_fields_does_not_crash(self):
        class Sparse:
            name = "Odd"

        assert [d.name for d in _condition_details(
            self._Entity("e1", [Sparse()]), None)] == ["Odd"]


class TestTheWholeChain:
    """Unit tests over `_observable_facts` pass whether or not anything real
    calls it with details. The guard-rejection bug (#155) was exactly that
    shape — the function was right and both production callers omitted the
    argument — so this drives the real `Condition` through the real snapshot
    path and reads the result off the payload the narrator receives.
    """

    def _shared_state(self, mechanics, entity):
        class SharedState:
            mechanics_engine = mechanics
            player_agents = []
            npc_agents = [entity]
            enemy_combat = None
            current_env_objects = []
        return SharedState()

    class _Agent:
        def __init__(self, agent_id, name):
            self.agent_id, self.name = agent_id, name
            self.narrative_name = name
            self.health, self.max_health = 20, 20
            self.status_effects = []

    def test_a_real_condition_reaches_the_narrator_with_its_sign(self):
        from aeonisk.multiagent.mechanics import Condition
        from aeonisk.multiagent.outcome_pipeline import snapshot_shared_state

        agent = self._Agent("npc_tarn", "Cold Tarn")

        class Mechanics:
            conditions = {}
        mechanics = Mechanics()
        before = snapshot_shared_state(self._shared_state(mechanics, agent))
        # The exact condition from session 3de9e609 round 2.
        mechanics.conditions = {"npc_tarn": [Condition(
            name="Controlled Hold", type="restraint", penalty=2,
            description="+2 to restraint checks while held", duration=2)]}
        after = snapshot_shared_state(self._shared_state(mechanics, agent))

        outcome = build_applied_outcome(
            round_num=2, sequence=1, actor_id="player_kael", actor_name="Kael",
            action={"intent": "hold him steady"},
            resolution_data={"success": True}, before=before, after=after)
        payload = prose_safe_outcome_payload([outcome])

        fact = next(f for f in payload[0]["facts"] if f["fact_kind"] == "condition")
        assert fact["polarity"] == "boon"
        assert "works in their favour" in fact["prose_safe_summary"]
        # What the narrator saw before this change, and read as harm.
        assert fact["prose_safe_summary"] != "Cold Tarn is affected by Controlled Hold."

    def test_the_numbers_stay_in_the_record_and_out_of_the_prompt(self):
        from aeonisk.multiagent.mechanics import Condition
        from aeonisk.multiagent.outcome_pipeline import snapshot_shared_state

        agent = self._Agent("npc_tarn", "Cold Tarn")

        class Mechanics:
            conditions = {"npc_tarn": [Condition(
                name="Inspired", type="morale", penalty=2, duration=3,
                description="+2 to all rolls for 3 rounds")]}

        snap = snapshot_shared_state(self._shared_state(Mechanics(), agent))["npc_tarn"]

        # The record keeps everything...
        assert snap.condition_details[0].penalty == 2
        assert snap.condition_details[0].description == "+2 to all rolls for 3 rounds"
        # ...and the prompt sees none of it.
        outcome = build_applied_outcome(
            round_num=2, sequence=1, actor_id="a", actor_name="A",
            action={"intent": "rally"}, resolution_data={"success": True},
            before={}, after=snap and {"npc_tarn": snap})
        assert "+2 to all rolls" not in str(prose_safe_outcome_payload([outcome]))
