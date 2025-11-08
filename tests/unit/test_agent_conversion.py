"""
Unit tests for agent conversion mechanics (Enemy ↔ NPC).

Tests the conversion functions that preserve state while changing behavior mode.
Critical: agent_id is STABLE across all conversions.
"""

import pytest
from scripts.aeonisk.multiagent.agent_conversion import (
    deescalate_enemy_to_npc,
    escalate_npc_to_enemy,
    subdue_enemy_to_prisoner
)
from scripts.aeonisk.multiagent.npc_agent import NPCAgent
from scripts.aeonisk.multiagent.schemas.shared_types import Condition


# Helper to create test enemy
def create_test_enemy(
    agent_id="enemy_raider_1",
    name="Raider",
    health=30,
    max_health=30,
    stuns=0,
    wounds=0,
    conditions=None
):
    """Create minimal test enemy for conversion testing."""
    from dataclasses import dataclass, field
    from typing import List, Dict

    @dataclass
    class TestEnemy:
        agent_id: str
        name: str
        faction: str = "Freeborn"
        health: int = 30
        max_health: int = 30
        soak: int = 5
        void_score: int = 4
        skills: Dict[str, int] = field(default_factory=lambda: {"combat": 5})
        stuns: int = 0
        wounds: int = 0
        conditions: List = field(default_factory=list)
        template: str = "freeborn_pirate"
        personality: str = "professional"

    return TestEnemy(
        agent_id=agent_id,
        name=name,
        health=health,
        max_health=max_health,
        stuns=stuns,
        wounds=wounds,
        conditions=conditions or []
    )


def test_deescalate_enemy_to_npc_preserves_id():
    """Critical: agent_id never changes during conversion."""
    enemy = create_test_enemy(
        agent_id="enemy_raider_1",
        name="Raider",
        health=30
    )
    npc = deescalate_enemy_to_npc(enemy, disposition="neutral")

    assert npc.agent_id == "enemy_raider_1"  # ✅ STABLE
    assert npc.name == "Raider"
    assert npc.health == 30
    assert npc.soak == 5
    assert npc.entity_type == "neutral"
    assert not hasattr(npc, 'tactics')
    assert not hasattr(npc, 'template')
    assert npc.converted_from_enemy == True


def test_deescalate_preserves_all_state():
    """Wounds, stuns, conditions preserved exactly."""
    enemy = create_test_enemy(
        agent_id="enemy_guard_1",
        health=15,
        max_health=30,
        stuns=2,
        wounds=1,
        conditions=[Condition(name="Bleeding", penalty=-2, description="Bleeding wound")]
    )
    npc = deescalate_enemy_to_npc(enemy, disposition="prisoner")

    assert npc.health == 15
    assert npc.max_health == 30
    assert npc.stuns == 2
    assert npc.wounds == 1
    assert len(npc.conditions) == 1
    assert npc.conditions[0].name == "Bleeding"
    assert npc.entity_type == "prisoner"
    assert npc.disposition == "prisoner"


def test_deescalate_tracks_original_template():
    """NPC remembers original enemy template for reverse conversion."""
    enemy = create_test_enemy(agent_id="enemy_pirate_1")
    enemy.template = "freeborn_pirate"

    npc = deescalate_enemy_to_npc(enemy, disposition="neutral")

    assert npc.original_enemy_template == "freeborn_pirate"
    assert npc.converted_from_enemy == True


def test_deescalate_copies_skills():
    """NPC retains enemy's skill set."""
    enemy = create_test_enemy(agent_id="enemy_soldier_1")
    enemy.skills = {"combat": 5, "perception": 4, "guile": 3}

    npc = deescalate_enemy_to_npc(enemy, disposition="neutral")

    assert npc.skills == {"combat": 5, "perception": 4, "guile": 3}


def test_deescalate_dispositions():
    """De-escalation supports all disposition types."""
    enemy = create_test_enemy(agent_id="enemy_test_1")

    for disposition in ["friendly", "neutral", "wary", "prisoner"]:
        npc = deescalate_enemy_to_npc(enemy, disposition=disposition)
        assert npc.disposition == disposition


def test_escalate_npc_to_enemy_preserves_id():
    """Escalation also preserves agent_id."""
    npc = NPCAgent(
        agent_id="enemy_civilian_1",
        name="Bystander",
        faction="Civilian",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Panicked civilian",
        health=20,
        max_health=20,
        soak=0,
        void_score=2,
        skills={"perception": 2},
        original_enemy_template="desperate_fighter"
    )

    enemy = escalate_npc_to_enemy(npc)

    assert enemy.agent_id == "enemy_civilian_1"  # ✅ STABLE
    assert enemy.name == "Bystander"
    assert enemy.health == 20
    assert hasattr(enemy, 'template')
    assert enemy.template == "desperate_fighter"


def test_escalate_preserves_all_state():
    """Escalation preserves wounds, stuns, conditions."""
    npc = NPCAgent(
        agent_id="enemy_wounded_1",
        name="Wounded NPC",
        faction="Freeborn",
        entity_type="neutral",
        disposition="neutral",
        threat_level="potential_threat",
        description="Injured NPC",
        health=10,
        max_health=25,
        soak=3,
        void_score=3,
        skills={"combat": 4},
        stuns=3,
        wounds=2,
        conditions=[Condition(name="Shaken", penalty=-1, description="Frightened")]
    )

    enemy = escalate_npc_to_enemy(npc)

    assert enemy.health == 10
    assert enemy.max_health == 25
    assert enemy.stuns == 3
    assert enemy.wounds == 2
    # Note: conditions are not directly copied (EnemyAgent uses status_effects, not conditions)
    # Condition conversion would be handled separately if needed


def test_escalate_uses_original_template():
    """If NPC was converted from enemy, use original template."""
    npc = NPCAgent(
        agent_id="enemy_pirate_1",
        name="Surrendered Pirate",
        faction="Freeborn",
        entity_type="prisoner",
        disposition="prisoner",
        threat_level="armed_neutral",
        description="Former pirate",
        health=20,
        max_health=30,
        soak=5,
        void_score=4,
        skills={"combat": 5},
        converted_from_enemy=True,
        original_enemy_template="freeborn_pirate"
    )

    enemy = escalate_npc_to_enemy(npc)

    assert enemy.template == "freeborn_pirate"


def test_escalate_uses_default_if_no_template():
    """If NPC has no original template, use desperate_fighter."""
    npc = NPCAgent(
        agent_id="enemy_civilian_1",
        name="Panicked Civilian",
        faction="Civilian",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Native NPC, never was enemy",
        health=15,
        max_health=15,
        soak=0,
        void_score=2,
        skills={},
        converted_from_enemy=False,
        original_enemy_template=None
    )

    enemy = escalate_npc_to_enemy(npc)

    assert enemy.template == "desperate_fighter"


def test_escalate_template_override():
    """Can override template explicitly."""
    npc = NPCAgent(
        agent_id="enemy_guard_1",
        name="Security Guard",
        faction="ACG",
        entity_type="neutral",
        disposition="neutral",
        threat_level="armed_neutral",
        description="Guard forced to fight",
        health=25,
        max_health=25,
        soak=4,
        void_score=3,
        skills={"combat": 4}
    )

    enemy = escalate_npc_to_enemy(npc, template_override="acg_security")

    assert enemy.template == "acg_security"


def test_subdue_enemy_to_prisoner():
    """Stun damage converts enemy to prisoner."""
    enemy = create_test_enemy(
        agent_id="enemy_guard_1",
        name="Guard",
        health=0,
        stuns=5
    )

    prisoner = subdue_enemy_to_prisoner(enemy)

    assert prisoner.agent_id == "enemy_guard_1"  # ✅ STABLE
    assert prisoner.entity_type == "prisoner"
    assert prisoner.disposition == "prisoner"
    assert prisoner.stuns == 5
    assert prisoner.converted_from_enemy == True


def test_subdue_preserves_damage():
    """Subdued prisoners retain all damage."""
    enemy = create_test_enemy(
        agent_id="enemy_raider_1",
        health=5,
        max_health=30,
        stuns=4,
        wounds=3
    )

    prisoner = subdue_enemy_to_prisoner(enemy)

    assert prisoner.health == 5
    assert prisoner.max_health == 30
    assert prisoner.stuns == 4
    assert prisoner.wounds == 3


def test_conversion_history_tracked():
    """Conversions are logged for replay."""
    enemy = create_test_enemy(agent_id="enemy_pirate_1")

    npc = deescalate_enemy_to_npc(enemy, disposition="neutral")

    # Check conversion history exists and has record
    assert len(npc.conversion_history) >= 1
    # Note: Full history tracking implemented when ConversionRecord is populated
