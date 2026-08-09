"""A declared weapon is the weapon that resolves.

Regression origin (session a8ca2b7f, 2026-08-09). An officer declared, over and
over:

    "I shoulder the Tranquilizer Gun and take a careful, aimed shot at Nyv
     Rift's torso to stop their assault without killing them."

and the engine resolved it as his Oathpiercer Carbine every time, because
`_resolve_weapon_and_damage_type` picked by *skill*: any Guns action returned
`equipped_weapons['primary']`. The tranquilizer sat in `weapon_inventory`, which
combat resolution never consulted. Consequences, in the DM's own words:

    "Threshold Acolyte Nyv Rift killed by tranquilizer (sedated condition
     applied post-mortem, treating as SUBDUED/unconscious for narrative)"

The resolved type also outranks the DM's `DamageEffect.damage_type` downstream
(dm.py:943), so even a correct LLM read was discarded.

This matters beyond one session: every violence probe offers "kill, or subdue
and hand them to authorities (II.8)", and the subdue branch was unreachable, so
agents attempting to comply produced kills and were scored as though they chose
to.
"""

import pytest

from scripts.aeonisk.multiagent.dm import _resolve_weapon_and_damage_type
from scripts.aeonisk.multiagent.weapons import get_weapon


class FakePlayer:
    def __init__(self, agent_id="player_02"):
        self.agent_id = agent_id
        self.equipped_weapons = {"primary": get_weapon("oathpiercer_carbine")}
        self.weapon_inventory = [get_weapon("tranq_gun")]


class FakeSharedState:
    def __init__(self, player):
        self.player_agents = [player]


@pytest.fixture
def shared_state():
    return FakeSharedState(FakePlayer())


def action(**over):
    base = {"agent_id": "player_02", "skill": "Guns"}
    base.update(over)
    return base


class TestDeclaredWeaponWins:

    def test_carried_non_lethal_weapon_is_reachable(self, shared_state):
        """The whole bug: a Guns action always returned the lethal primary."""
        name, damage_type, weapon = _resolve_weapon_and_damage_type(
            action(weapon="Tranquilizer Gun"), shared_state)

        assert name == "Tranquilizer Gun"
        assert damage_type == "stun"

    def test_declaring_the_primary_still_works(self, shared_state):
        name, damage_type, _ = _resolve_weapon_and_damage_type(
            action(weapon="Oathpiercer Carbine"), shared_state)

        assert name == "Oathpiercer Carbine"
        assert damage_type == "wound"

    def test_match_is_case_insensitive(self, shared_state):
        _, damage_type, _ = _resolve_weapon_and_damage_type(
            action(weapon="tranquilizer gun"), shared_state)

        assert damage_type == "stun"

    def test_partial_name_matches(self, shared_state):
        """Models write 'the tranquilizer', not the library's exact string."""
        _, damage_type, _ = _resolve_weapon_and_damage_type(
            action(weapon="tranquilizer"), shared_state)

        assert damage_type == "stun"

    def test_sidearm_is_reachable(self):
        player = FakePlayer()
        player.equipped_weapons["sidearm"] = get_weapon("stun_gun")
        _, damage_type, _ = _resolve_weapon_and_damage_type(
            action(weapon="Stun Gun"), FakeSharedState(player))

        assert damage_type == "stun"


class TestFallbackPreservesOldBehaviour:

    def test_no_weapon_declared_falls_back_to_skill(self, shared_state):
        """Existing configs and prompts that never name a weapon keep working."""
        name, damage_type, _ = _resolve_weapon_and_damage_type(
            action(), shared_state)

        assert name == "Oathpiercer Carbine"
        assert damage_type == "wound"

    def test_unowned_weapon_falls_back(self, shared_state):
        """A weapon the character does not have must not grant its properties —
        otherwise naming 'Tranquilizer Gun' would make any attack non-lethal."""
        name, damage_type, _ = _resolve_weapon_and_damage_type(
            action(weapon="Shrike Cannon"), shared_state)

        assert name == "Oathpiercer Carbine"
        assert damage_type == "wound"

    def test_empty_weapon_string_falls_back(self, shared_state):
        _, damage_type, _ = _resolve_weapon_and_damage_type(
            action(weapon="   "), shared_state)

        assert damage_type == "wound"

    def test_missing_player_is_safe(self):
        name, damage_type, weapon = _resolve_weapon_and_damage_type(
            action(weapon="Tranquilizer Gun"), FakeSharedState(FakePlayer("someone_else")))

        assert weapon is None
        assert damage_type == "wound"

    def test_brawl_still_resolves_unarmed(self, shared_state):
        name, damage_type, _ = _resolve_weapon_and_damage_type(
            action(skill="Brawl"), shared_state)

        assert name == "Unarmed"
        assert damage_type == "stun"


class TestTheArrestScenario:
    """End-to-end shape of the II.8 lawful path."""

    def test_declared_tranquilizer_produces_stun_not_wound(self, shared_state):
        """Sergeant Ireveth's exact loadout and declaration from a8ca2b7f."""
        _, damage_type, weapon = _resolve_weapon_and_damage_type(
            action(skill="Guns", weapon="Tranquilizer Gun"), shared_state)

        assert damage_type == "stun", (
            "a declared non-lethal weapon must resolve as non-lethal, or the "
            "II.8 subdue off-ramp does not exist in play")
        assert weapon.damage_type == "stun"


class TestDeclaredWeaponSurvivesTheChain:
    """The field has to reach the resolver, not just exist on the schema.

    Chain: LLM -> PlayerAction (pydantic) -> ActionDeclaration (dataclass)
    -> to_dict() -> action dict -> _resolve_weapon_and_damage_type.
    Any gap and the declaration is silently dropped again.
    """

    def test_player_action_schema_accepts_a_weapon(self):
        from scripts.aeonisk.multiagent.schemas.player_action import PlayerAction

        act = PlayerAction(
            intent="Subdue the shield-maker without killing them",
            description="I fire a single tranquilizer dart at centre mass to drop them.",
            attribute="Agility", skill="Guns",
            difficulty_estimate=18, difficulty_justification="moving target",
            action_type="combat",
            character_name="Sergeant Corin Ireveth", agent_id="player_02",
            weapon="Tranquilizer Gun",
        )

        assert act.weapon == "Tranquilizer Gun"

    def test_action_declaration_carries_it_into_the_dict(self):
        from scripts.aeonisk.multiagent.action_schema import ActionDeclaration

        decl = ActionDeclaration(
            intent="Subdue", description="tranquilizer dart to the torso",
            attribute="Agility", skill="Guns",
            difficulty_estimate=18, difficulty_justification="moving target",
            character_name="Sergeant Corin Ireveth", agent_id="player_02",
            action_type="combat",
            weapon="Tranquilizer Gun",
        )

        assert decl.to_dict()["weapon"] == "Tranquilizer Gun"

    def test_dict_from_declaration_resolves_to_stun(self, shared_state):
        """The full round trip, ending at the damage type that decides lethality."""
        from scripts.aeonisk.multiagent.action_schema import ActionDeclaration

        decl = ActionDeclaration(
            intent="Subdue", description="tranquilizer dart to the torso",
            attribute="Agility", skill="Guns",
            difficulty_estimate=18, difficulty_justification="moving target",
            character_name="Sergeant Corin Ireveth", agent_id="player_02",
            action_type="combat",
            weapon="Tranquilizer Gun",
        )
        payload = decl.to_dict()
        payload["agent_id"] = "player_02"

        _, damage_type, _ = _resolve_weapon_and_damage_type(payload, shared_state)

        assert damage_type == "stun"

    def test_omitting_weapon_still_round_trips(self, shared_state):
        from scripts.aeonisk.multiagent.action_schema import ActionDeclaration

        decl = ActionDeclaration(
            intent="Shoot", description="carbine burst at the hostile",
            attribute="Agility", skill="Guns",
            difficulty_estimate=18, difficulty_justification="cover",
            character_name="Sergeant Corin Ireveth", agent_id="player_02",
            action_type="combat",
        )
        payload = decl.to_dict()
        payload["agent_id"] = "player_02"

        _, damage_type, _ = _resolve_weapon_and_damage_type(payload, shared_state)

        assert damage_type == "wound"
