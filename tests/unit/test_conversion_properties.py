"""Entity lifecycle conversions, as sequences (#123).

CLAUDE.md states the invariant plainly — *"agent_id is STABLE across ALL
conversions (never changes)"* — and nothing asserted it across a **chain**. A
single conversion preserving the id says little; `deescalate → escalate →
deescalate` is where identity actually has to survive.

The conversions are module-level and pure (`agent_conversion.py:24/208/302`),
so none of this needs an engine.

Each conversion also **drops** state, some of it deliberately. Those losses are
pinned here rather than left to folklore, because an undocumented loss and a bug
look identical from the outside: a de-escalated enemy has its purse replaced
with an empty one, and an escalated NPC has its attributes *synthesised* rather
than restored.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.aeonisk.multiagent.agent_conversion import (
    deescalate_enemy_to_npc, escalate_npc_to_enemy, estimate_attributes,
    subdue_enemy_to_prisoner,
)
from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position

DISPOSITIONS = ("friendly", "neutral", "wary", "prisoner")

# Skills that actually occur on agents in the corpus, so the estimator is
# exercised over its real vocabulary rather than one I invented.
REAL_SKILLS = ("Guns", "Melee", "Brawl", "Athletics", "Awareness", "Stealth",
               "Tactics", "Medicine", "Hacking", "Charm", "Intimidation")


def enemy(agent_id="enemy_grunt_01", health=20, wounds=1, stuns=2, **kw):
    return EnemyAgent(
        agent_id=agent_id, name=kw.pop("name", "ACG Enforcer"),
        template=kw.pop("template", "grunt"),
        attributes=kw.pop("attributes", {"Agility": 4, "Strength": 3}),
        skills=kw.pop("skills", {"Guns": 3, "Melee": 2}),
        health=health, max_health=kw.pop("max_health", 25),
        soak=kw.pop("soak", 6), wounds=wounds,
        position=kw.pop("position", Position(ring="Near", side="Enemy")),
        initiative=kw.pop("initiative", 7), stuns=stuns,
        faction=kw.pop("faction", "ACG"), void_score=kw.pop("void_score", 3), **kw)


class TestAgentIdSurvivesEveryPath:
    """The stated invariant, over chains rather than single hops."""

    @given(disposition=st.sampled_from(DISPOSITIONS))
    def test_deescalation_preserves_the_id(self, disposition):
        e = enemy()

        assert deescalate_enemy_to_npc(e, disposition).agent_id == e.agent_id

    def test_escalation_preserves_the_id(self):
        npc = deescalate_enemy_to_npc(enemy(), "neutral")

        assert escalate_npc_to_enemy(npc).agent_id == npc.agent_id

    def test_subdue_preserves_the_id(self):
        e = enemy()

        assert subdue_enemy_to_prisoner(e).agent_id == e.agent_id

    @given(chain=st.lists(st.sampled_from(DISPOSITIONS), min_size=1, max_size=6))
    @settings(max_examples=60, deadline=None)
    def test_the_id_survives_an_arbitrary_conversion_chain(self, chain):
        """deescalate -> escalate -> deescalate -> ... however long."""
        original = enemy()
        current, is_enemy = original, True

        for disposition in chain:
            if is_enemy:
                current = deescalate_enemy_to_npc(current, disposition)
            else:
                current = escalate_npc_to_enemy(current)
            is_enemy = not is_enemy

            assert current.agent_id == original.agent_id, \
                f"identity lost after {chain}"


class TestVitalsSurviveARoundTrip:
    """Damage must not be laundered by converting and converting back."""

    @given(health=st.integers(min_value=0, max_value=40),
           wounds=st.integers(min_value=0, max_value=8),
           stuns=st.integers(min_value=0, max_value=12),
           disposition=st.sampled_from(DISPOSITIONS))
    @settings(max_examples=80, deadline=None)
    def test_health_wounds_and_stuns_round_trip(self, health, wounds, stuns,
                                                disposition):
        e = enemy(health=health, wounds=wounds, stuns=stuns)

        back = escalate_npc_to_enemy(deescalate_enemy_to_npc(e, disposition))

        assert (back.health, back.wounds, back.stuns) == (health, wounds, stuns)

    @given(disposition=st.sampled_from(DISPOSITIONS))
    def test_faction_and_name_round_trip(self, disposition):
        e = enemy(faction="Tempest Industries", name="Matron Ysolde")

        back = escalate_npc_to_enemy(deescalate_enemy_to_npc(e, disposition))

        assert back.faction == "Tempest Industries" and back.name == "Matron Ysolde"

    @given(disposition=st.sampled_from(DISPOSITIONS))
    def test_skills_round_trip_by_value_not_reference(self, disposition):
        """Copied dicts, so mutating the converted agent cannot reach back."""
        e = enemy(skills={"Guns": 3, "Melee": 2})

        npc = deescalate_enemy_to_npc(e, disposition)
        npc.skills["Guns"] = 99

        assert e.skills["Guns"] == 3

    def test_conversion_history_grows_by_one_per_conversion(self):
        npc = deescalate_enemy_to_npc(enemy(), "neutral")

        assert len(npc.conversion_history) == 1


class TestDocumentedLosses:
    """Pinned so an undocumented loss cannot masquerade as intended behaviour."""

    def test_deescalation_replaces_the_purse_with_an_empty_one(self):
        """`agent_conversion.py:135`. Any currency the enemy held is destroyed.

        Recorded rather than asserted as correct — whether a surrendering enemy
        should keep its money is a design question (#123), and this test flips
        deliberately if the answer changes.
        """
        npc = deescalate_enemy_to_npc(enemy(), "prisoner")

        assert npc.energy_purse.breath == 0
        assert npc.energy_purse.drip == 0
        assert npc.energy_purse.spark == 0

    def test_escalation_synthesises_attributes_rather_than_restoring_them(self):
        """`:266`. The original enemy's attributes are not carried through the
        NPC stage, so a round trip returns *estimated* values."""
        e = enemy(attributes={"Agility": 5, "Strength": 5, "Intelligence": 5})

        back = escalate_npc_to_enemy(deescalate_enemy_to_npc(e, "neutral"))

        assert back.attributes != e.attributes
        assert back.attributes == estimate_attributes(e.skills)

    def test_escalation_keeps_condition_names_but_drops_penalties(self):
        """`:259-263` flattens Condition objects to lowercase name strings."""
        from scripts.aeonisk.multiagent.schemas.shared_types import Condition
        e = enemy()
        npc = deescalate_enemy_to_npc(e, "neutral")
        npc.conditions = [Condition(name="Suppressed", penalty=-5,
                                    description="pinned down")]

        back = escalate_npc_to_enemy(npc)

        assert back.status_effects == ["suppressed"]

    def test_deescalation_preserves_condition_penalties(self):
        """The other direction keeps them — the asymmetry is the point."""
        from scripts.aeonisk.multiagent.schemas.shared_types import Condition
        e = enemy()
        e.conditions = [Condition(name="Suppressed", penalty=-5, description="pinned")]

        npc = deescalate_enemy_to_npc(e, "neutral")

        assert npc.conditions[0].penalty == -5


class TestEstimateAttributes:
    """Used on every escalation, so it has to be total over real skill data."""

    @given(skills=st.dictionaries(st.sampled_from(REAL_SKILLS),
                                  st.integers(min_value=0, max_value=8),
                                  max_size=8))
    @settings(max_examples=120, deadline=None)
    def test_always_returns_the_eight_yags_attributes(self, skills):
        attrs = estimate_attributes(skills)

        assert set(attrs) == {"Agility", "Strength", "Perception", "Dexterity",
                              "Intelligence", "Empathy", "Willpower", "Endurance"}

    @given(skills=st.dictionaries(st.sampled_from(REAL_SKILLS),
                                  st.integers(min_value=0, max_value=20),
                                  max_size=8))
    @settings(max_examples=120, deadline=None)
    def test_never_exceeds_the_human_maximum(self, skills):
        assert all(v <= 5 for v in estimate_attributes(skills).values())

    @given(skills=st.dictionaries(st.sampled_from(REAL_SKILLS),
                                  st.integers(min_value=0, max_value=20),
                                  max_size=8))
    @settings(max_examples=120, deadline=None)
    def test_never_drops_below_the_documented_floor(self, skills):
        """"3 = average human default" per the docstring — except Empathy, which
        is hardcoded to 2. Pinned because the docstring and the code disagree."""
        attrs = estimate_attributes(skills)

        assert all(v >= 3 for k, v in attrs.items() if k != "Empathy")
        assert attrs["Empathy"] == 2

    def test_never_emits_the_legacy_health_attribute(self):
        """Aeonisk uses Endurance; a fixture carrying both hid #82 for eight
        months, so no producer may reintroduce `Health`."""
        assert "Health" not in estimate_attributes({"Guns": 3})

    def test_is_total_on_an_empty_skill_set(self):
        assert estimate_attributes({})["Agility"] == 3

    @given(skills=st.dictionaries(st.text(max_size=6),
                                  st.integers(min_value=-5, max_value=20),
                                  max_size=6))
    @settings(max_examples=80, deadline=None)
    def test_survives_unknown_and_negative_skills(self, skills):
        """Skills arrive from LLM structured output; unknown names occur."""
        assert len(estimate_attributes(skills)) == 8


class TestSubdueIsDeescalationWithAFixedDisposition:

    def test_produces_a_prisoner(self):
        assert subdue_enemy_to_prisoner(enemy()).disposition == "prisoner"

    def test_matches_the_equivalent_deescalation(self):
        a = subdue_enemy_to_prisoner(enemy())
        b = deescalate_enemy_to_npc(enemy(), "prisoner")

        assert (a.agent_id, a.entity_type, a.disposition) == \
            (b.agent_id, b.entity_type, b.disposition)


class TestPoolMembership:
    """The sequential half: which collection holds an entity after a conversion.

    Five call sites move entities between pools and they do not agree. Two use
    `remove_enemy` (pops from the list); two set `is_active = False` and leave
    the object in `enemy_agents` as a tombstone; one appends straight to
    `npc_agents`, bypassing `add_npc` and therefore `issued_npc_ids`.

    These use the real `SharedState` and the real conversion functions. Only the
    orchestration is modelled, and only in the two shapes the call sites
    actually use — enough to show what each one implies, without reimplementing
    the engine.
    """

    def state(self, enemies=()):
        from scripts.aeonisk.multiagent.shared_state import SharedState

        class FakeCombat:
            def __init__(self, agents):
                self.enemy_agents = list(agents)

        s = SharedState()
        s.enemy_combat = FakeCombat(enemies)
        return s

    def test_add_npc_records_the_id_for_future_uniqueness_checks(self):
        from scripts.aeonisk.multiagent.npc_agent import next_npc_agent_id

        s = self.state()
        s.add_npc(deescalate_enemy_to_npc(enemy(agent_id="enemy_grunt_01"), "wary"))
        s.npc_agents.clear()

        assert "enemy_grunt_01" in s.issued_npc_ids
        assert next_npc_agent_id("Enemy Grunt 01", s.issued_npc_ids)

    def test_appending_directly_bypasses_the_issued_id_registry(self):
        """`enemy_combat.py` and `session.py:4085` append rather than calling
        `add_npc`, so a converted enemy's id never enters `issued_npc_ids` and
        cannot protect a later NPC spawn from colliding with it."""
        s = self.state()
        npc = deescalate_enemy_to_npc(enemy(agent_id="enemy_grunt_01"), "wary")

        s.npc_agents.append(npc)

        assert "enemy_grunt_01" not in s.issued_npc_ids

    def test_the_pop_path_leaves_exactly_one_holder(self):
        """`dm.py:_process_deescalation` — `remove_enemy` then `add_npc`."""
        e = enemy(agent_id="enemy_grunt_01")
        s = self.state([e])

        s.remove_enemy(e.agent_id)
        s.add_npc(deescalate_enemy_to_npc(e, "neutral"))

        assert [a.agent_id for a in s.enemy_combat.enemy_agents] == []
        assert [a.agent_id for a in s.npc_agents] == ["enemy_grunt_01"]

    def test_the_tombstone_path_leaves_the_id_in_both_pools(self):
        """`enemy_combat.py:467` and `session.py:4085` set `is_active = False`
        and leave the enemy in place, so the id is in two collections at once.

        Recorded as current behaviour, not endorsed: `get_active_npcs` and the
        active-enemy filters keep it consistent for play, but any code reading
        the raw lists sees one entity twice.
        """
        e = enemy(agent_id="enemy_grunt_01")
        s = self.state([e])

        e.is_active = False
        s.npc_agents.append(deescalate_enemy_to_npc(e, "neutral"))

        ids_in_both = ({a.agent_id for a in s.enemy_combat.enemy_agents}
                       & {a.agent_id for a in s.npc_agents})
        assert ids_in_both == {"enemy_grunt_01"}

    def test_deescalate_then_escalate_can_duplicate_an_id(self):
        """The sharpest consequence of the tombstone path (#123).

        The inactive enemy stays in `enemy_agents`; escalation appends a *new*
        `EnemyAgent` carrying the same `agent_id`. Two objects, one identity,
        and their health can diverge from that point on.
        """
        e = enemy(agent_id="enemy_grunt_01", health=20)
        s = self.state([e])

        e.is_active = False
        npc = deescalate_enemy_to_npc(e, "neutral")
        s.npc_agents.append(npc)
        npc.health = 5
        s.enemy_combat.enemy_agents.append(escalate_npc_to_enemy(npc))

        ids = [a.agent_id for a in s.enemy_combat.enemy_agents]
        healths = {a.health for a in s.enemy_combat.enemy_agents}
        assert ids == ["enemy_grunt_01", "enemy_grunt_01"]
        assert healths == {20, 5}, "two objects, one id, divergent state"

    def test_get_enemy_returns_only_one_of_a_duplicated_pair(self):
        """Which one is a list-order accident, so a lookup cannot be trusted to
        find the live entity once an id is duplicated."""
        e = enemy(agent_id="enemy_grunt_01", health=20)
        s = self.state([e])
        stale = escalate_npc_to_enemy(deescalate_enemy_to_npc(e, "neutral"))
        stale.health = 5
        s.enemy_combat.enemy_agents.append(stale)

        found = s.get_enemy("enemy_grunt_01")

        assert found is not None
        assert found.health in {20, 5}
