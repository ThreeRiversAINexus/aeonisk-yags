"""Realistic test objects, built from the real classes.

Why this exists (#103): 110 of 317 test files use mocks, and a bare `MagicMock`
in a *value* position lies in ways that are silent and specific.

    list(mock.npc_agents)        -> []          iterates EMPTY
    bool(mock.is_active)         -> True        filters never exclude
    mock.health > 0              -> TypeError   (this is #81's crash)
    str(mock.name)               -> "<MagicMock name='mock.name' id=...>"
    a, b = mock.calculate_range() -> ValueError  (today's de-escalation failure)

The first is the worst. **32 test files mock `shared_state`**, and any of them
asking "did we process every NPC?" sees an empty list and passes — which is
exactly the shape of #89, where NPCs were missing from `character_state` for
months while the suite stayed green.

Mocks are still right for *sinks* you assert against — loggers, LLM providers,
message buses. They are wrong for anything the code under test reads a value
from. Use these builders for those.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from scripts.aeonisk.multiagent.enemy_agent import Position

_DEFAULT_ATTRIBUTES = {
    "Strength": 3, "Agility": 3, "Endurance": 3, "Dexterity": 3,
    "Perception": 3, "Intelligence": 3, "Empathy": 3, "Willpower": 3,
}


def make_attributes(**overrides: int) -> Dict[str, int]:
    """The eight YAGS attributes. Never includes a legacy 'Health' key —
    that shape hid #82 for eight months (see test_fixture_integrity)."""
    attrs = dict(_DEFAULT_ATTRIBUTES)
    for key, value in overrides.items():
        if key not in _DEFAULT_ATTRIBUTES:
            raise ValueError(
                f"{key!r} is not a YAGS attribute; valid: "
                f"{', '.join(sorted(_DEFAULT_ATTRIBUTES))}")
        attrs[key] = value
    return attrs


def make_position(ring: str = "Near", side: Optional[str] = "PC") -> Position:
    """A real Position. A mocked one returns a mock from `calculate_range()`,
    which unpacks as empty and raises ValueError."""
    return Position(ring=ring, side=side)


class FakeCharacterState:
    """Duck-types the fields the engine actually reads off `character_state`.

    Deliberately a plain object rather than a Mock: every attribute is a real
    value of the right type, so a comparison, a join, or an f-string behaves the
    way it will in production.
    """

    def __init__(self, name: str = "Test Character", faction: str = "Freeborn",
                 void_score: int = 0, soulcredit: int = 0,
                 attributes: Optional[Dict[str, int]] = None,
                 skills: Optional[Dict[str, int]] = None,
                 pronouns: str = "they/them", goals: Optional[List[str]] = None):
        self.name = name
        self.faction = faction
        self.void_score = void_score
        self.soulcredit = soulcredit
        self.attributes = attributes if attributes is not None else make_attributes()
        self.skills = skills if skills is not None else {"Awareness": 3}
        self.pronouns = pronouns
        self.goals = goals if goals is not None else []
        self.bonds: List[Any] = []
        self.inventory: Dict[str, int] = {}


class FakeAgent:
    """An entity with the mechanical surface the engine reads.

    Covers players, enemies and NPCs — all three expose the same fields to the
    logging and combat paths (`health`, `wounds`, `stuns`, `position`,
    `is_active`, `agent_id`).
    """

    def __init__(self, agent_id: str = "agent_01", name: str = "Test Character",
                 health: int = 25, max_health: int = 25, wounds: int = 0,
                 stuns: int = 0, void_score: int = 0, soulcredit: int = 0,
                 faction: str = "Freeborn", is_active: bool = True,
                 position: Optional[Position] = None,
                 character_state: Optional[FakeCharacterState] = None):
        self.agent_id = agent_id
        self.name = name
        self.health = health
        self.max_health = max_health
        self.wounds = wounds
        self.stuns = stuns
        self.void_score = void_score
        self.is_active = is_active
        self.position = position if position is not None else make_position()
        self.character_state = character_state if character_state is not None else \
            FakeCharacterState(name=name, faction=faction, void_score=void_score,
                               soulcredit=soulcredit)
        self.weapon_inventory: List[Any] = []
        self.equipped_weapons: Dict[str, Any] = {}


class FakeSharedState:
    """Real containers, so iteration yields what was put in.

    A mocked shared_state iterates empty, so a test asking "was every NPC
    processed?" sees zero and passes. That is #89's exact shape.
    """

    def __init__(self, players: Optional[List[Any]] = None,
                 npcs: Optional[List[Any]] = None,
                 enemies: Optional[List[Any]] = None,
                 mechanics_engine: Any = None):
        self.player_agents: List[Any] = list(players or [])
        self.npc_agents: List[Any] = list(npcs or [])
        self.registered_players: List[Dict[str, str]] = [
            {"agent_id": p.agent_id, "name": p.character_state.name}
            for p in self.player_agents
        ]
        self.mechanics_engine = mechanics_engine
        self.enemy_combat = FakeEnemyCombat(enemies or [])
        self.session_config: Dict[str, Any] = {}

    def get_mechanics_engine(self):
        return self.mechanics_engine


class FakeEnemyCombat:
    def __init__(self, enemies: Optional[List[Any]] = None, enabled: bool = True):
        self.enemy_agents: List[Any] = list(enemies or [])
        self.enabled = enabled


def make_party(size: int = 2, **kwargs) -> List[FakeAgent]:
    """A party with distinct ids and names — mocks share identity by default,
    which hides bugs where one entity's state is written over another's."""
    return [
        FakeAgent(agent_id=f"player_{i + 1:02d}",
                  name=f"Test Player {i + 1}", **kwargs)
        for i in range(size)
    ]
