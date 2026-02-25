"""
Tests for targeting validation system — Spec 03: Target Validation & Free-Target Binding.

Tests cover:
- Layer 1: Combatant state tag generation (_get_combatant_state_tag)
- Layer 2: Post-resolution semantic validation (_check_target_combat_state)
- Layer 4: Enriched get_combatant_info() with state fields
- Layer 5: get_combatant_status() convenience method
- Existing validation pipeline (STEPS 1-5)
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from scripts.aeonisk.multiagent.target_ids import TargetIDMapper
from scripts.aeonisk.multiagent.targeting_validation import (
    validate_and_correct_targeting,
    _check_target_combat_state,
)
from scripts.aeonisk.multiagent.dm import _get_combatant_state_tag
from scripts.aeonisk.multiagent.schemas.shared_types import DamageEffect


# ============================================================================
# Test Helpers — Minimal mock agents
# ============================================================================

@dataclass
class MockEnemyAgent:
    """Minimal enemy agent for testing."""
    agent_id: str
    name: str
    health: int = 20
    max_health: int = 20
    soak: int = 10
    wounds: int = 0
    stuns: int = 0
    is_active: bool = True
    is_prisoner: bool = False
    is_panicked: bool = False
    despawned_round: Optional[int] = None
    faction: str = "Unknown"
    pronouns: str = "they/them"
    position: str = "center"
    void_score: int = 0
    tactics: str = "aggressive"  # Needed to distinguish from NPCs
    _permanently_dead: bool = False

    # Equipment (needed for EnemyAgent compatibility)
    weapons: list = field(default_factory=list)
    armor: object = None
    special_abilities: list = field(default_factory=list)


@dataclass
class MockNPCAgent:
    """Minimal NPC agent for testing."""
    agent_id: str
    name: str
    faction: str = "Civilian"
    entity_type: str = "neutral"  # Literal["neutral", "ally", "prisoner"]
    disposition: str = "neutral"  # Literal["friendly", "neutral", "wary", "prisoner"]
    health: int = 10
    max_health: int = 10
    soak: int = 5
    void_score: int = 0
    pronouns: str = "they/them"
    is_active: bool = True
    wounds: int = 0
    stuns: int = 0
    position: str = "center"
    _permanently_dead: bool = False
    memory: object = None


@dataclass
class MockPlayerAgent:
    """Minimal player agent for testing."""
    agent_id: str
    health: int = 20
    max_health: int = 27
    wounds: int = 0
    stuns: int = 0
    position: str = "center"
    _permanently_dead: bool = False

    @dataclass
    class CharacterState:
        name: str
        pronouns: str = "she/her"
        faction: str = "Freeborn"
        void_score: int = 0

    character_state: 'MockPlayerAgent.CharacterState' = None

    def __post_init__(self):
        if self.character_state is None:
            self.character_state = self.CharacterState(name="Unknown Player")


class MockSharedState:
    """Minimal shared state for testing."""
    def __init__(self):
        self.npc_agents: List[MockNPCAgent] = []
        self.enemy_combat = MagicMock()
        self.enemy_combat.enemy_agents = []

    def get_agent_by_id(self, agent_id):
        for npc in self.npc_agents:
            if npc.agent_id == agent_id:
                return npc
        for enemy in self.enemy_combat.enemy_agents:
            if enemy.agent_id == agent_id:
                return enemy
        return None


def create_test_enemy(agent_id="enemy_grunt_1", name="Guard", **kwargs):
    """Create a mock enemy with specified attributes."""
    return MockEnemyAgent(agent_id=agent_id, name=name, **kwargs)


def create_test_npc(agent_id="npc_1", name="Civilian", **kwargs):
    """Create a mock NPC with specified attributes."""
    return MockNPCAgent(agent_id=agent_id, name=name, **kwargs)


def create_test_player(agent_id="player_01", name="Vessel Sera", health=20, max_health=27, **kwargs):
    """Create a mock player with specified attributes."""
    cs = MockPlayerAgent.CharacterState(name=name, **{k: v for k, v in kwargs.items() if k in ('pronouns', 'faction', 'void_score')})
    remaining = {k: v for k, v in kwargs.items() if k not in ('pronouns', 'faction', 'void_score')}
    return MockPlayerAgent(agent_id=agent_id, health=health, max_health=max_health, character_state=cs, **remaining)


# ============================================================================
# LAYER 1: Combatant State Tag Tests
# ============================================================================

class TestGetCombatantStateTag:
    """Tests for _get_combatant_state_tag() helper in dm.py."""

    def setup_method(self):
        self.shared_state = MockSharedState()

    def test_active_enemy_gets_active_tag(self):
        """Active enemies must have [ACTIVE] tag in the combatant list
        shown to the DM."""
        mapper = TargetIDMapper()
        mapper.enable()
        enemy = create_test_enemy(
            agent_id="enemy_grunt_1", name="Guard",
            is_active=True, is_prisoner=False
        )
        tid = mapper.register_enemy(enemy)
        self.shared_state.enemy_combat.enemy_agents = [enemy]

        info = mapper.get_combatant_info(tid)
        state_tag = _get_combatant_state_tag(info, tid, self.shared_state)

        assert state_tag == "[ACTIVE]"

    def test_prisoner_enemy_gets_prisoner_tag(self):
        """Enemies with is_prisoner=True must show [PRISONER] tag."""
        mapper = TargetIDMapper()
        mapper.enable()
        enemy = create_test_enemy(
            agent_id="enemy_grunt_1", name="Captured Guard",
            is_active=False, is_prisoner=True
        )
        tid = mapper.register_enemy(enemy)
        self.shared_state.enemy_combat.enemy_agents = [enemy]

        info = mapper.get_combatant_info(tid)
        state_tag = _get_combatant_state_tag(info, tid, self.shared_state)

        assert state_tag == "[PRISONER]"

    def test_prisoner_npc_gets_prisoner_tag(self):
        """NPCs with disposition=prisoner must show [PRISONER] tag."""
        mapper = TargetIDMapper()
        mapper.enable()
        npc = create_test_npc(
            agent_id="enemy_guard_001",
            name="Subdued Guard",
            disposition="prisoner",
            entity_type="prisoner"
        )
        mapper.register_npc(npc)
        self.shared_state.npc_agents = [npc]

        # Assign IDs (including NPCs)
        mapper.assign_ids([], [], npc_agents=[npc])
        npc_tid = mapper.get_target_id(npc.agent_id)

        info = mapper.get_combatant_info(npc_tid)
        state_tag = _get_combatant_state_tag(info, npc_tid, self.shared_state)

        assert state_tag == "[PRISONER]"

    def test_panicked_enemy_gets_fleeing_tag(self):
        """Enemies with is_panicked=True must show [PANICKED/FLEEING] tag."""
        mapper = TargetIDMapper()
        mapper.enable()
        enemy = create_test_enemy(
            agent_id="enemy_grunt_1", name="Panicked Guard",
            is_active=True, is_panicked=True
        )
        tid = mapper.register_enemy(enemy)
        self.shared_state.enemy_combat.enemy_agents = [enemy]

        info = mapper.get_combatant_info(tid)
        state_tag = _get_combatant_state_tag(info, tid, self.shared_state)

        assert state_tag == "[PANICKED/FLEEING]"

    def test_defeated_enemy_gets_defeated_tag(self):
        """Defeated (inactive, non-prisoner) enemies get [DEFEATED] tag."""
        mapper = TargetIDMapper()
        mapper.enable()
        enemy = create_test_enemy(
            agent_id="enemy_grunt_1", name="Defeated Guard",
            is_active=False, is_prisoner=False
        )
        tid = mapper.register_enemy(enemy)
        self.shared_state.enemy_combat.enemy_agents = [enemy]

        info = mapper.get_combatant_info(tid)
        state_tag = _get_combatant_state_tag(info, tid, self.shared_state)

        assert state_tag == "[DEFEATED]"

    def test_wounded_enemy_gets_wounded_tag(self):
        """Enemy at <= 25% HP gets [WOUNDED] tag."""
        mapper = TargetIDMapper()
        mapper.enable()
        enemy = create_test_enemy(
            agent_id="enemy_grunt_1", name="Wounded Guard",
            is_active=True, health=4, max_health=20
        )
        tid = mapper.register_enemy(enemy)
        self.shared_state.enemy_combat.enemy_agents = [enemy]

        info = mapper.get_combatant_info(tid)
        state_tag = _get_combatant_state_tag(info, tid, self.shared_state)

        assert state_tag == "[WOUNDED]"

    def test_dead_entity_gets_dead_tag(self):
        """Dead entities (wounds >= 6) get [DEAD] tag regardless of type."""
        mapper = TargetIDMapper()
        mapper.enable()
        enemy = create_test_enemy(
            agent_id="enemy_grunt_1", name="Dead Guard",
            is_active=False, wounds=6
        )
        tid = mapper.register_enemy(enemy)
        self.shared_state.enemy_combat.enemy_agents = [enemy]

        info = mapper.get_combatant_info(tid)
        state_tag = _get_combatant_state_tag(info, tid, self.shared_state)

        assert state_tag == "[DEAD]"

    def test_unconscious_entity_gets_unconscious_tag(self):
        """Unconscious entities (health <= 0, not dead) get [UNCONSCIOUS] tag."""
        mapper = TargetIDMapper()
        mapper.enable()
        enemy = create_test_enemy(
            agent_id="enemy_grunt_1", name="Downed Guard",
            is_active=False, health=0, max_health=20
        )
        tid = mapper.register_enemy(enemy)
        self.shared_state.enemy_combat.enemy_agents = [enemy]

        info = mapper.get_combatant_info(tid)
        state_tag = _get_combatant_state_tag(info, tid, self.shared_state)

        assert state_tag == "[UNCONSCIOUS]"

    def test_active_player_gets_active_tag(self):
        """Active players get [ACTIVE] tag."""
        mapper = TargetIDMapper()
        mapper.enable()
        player = create_test_player(
            agent_id="player_01", name="Vessel Sera",
            health=20, max_health=27
        )
        mapper.assign_ids([player], [])
        tid = mapper.get_target_id("player_01")

        info = mapper.get_combatant_info(tid)
        state_tag = _get_combatant_state_tag(info, tid, self.shared_state)

        assert state_tag == "[ACTIVE]"

    def test_wounded_player_gets_wounded_tag(self):
        """Player at <= 25% HP gets [WOUNDED] tag."""
        mapper = TargetIDMapper()
        mapper.enable()
        player = create_test_player(
            agent_id="player_01", name="Vessel Sera",
            health=5, max_health=27
        )
        mapper.assign_ids([player], [])
        tid = mapper.get_target_id("player_01")

        info = mapper.get_combatant_info(tid)
        state_tag = _get_combatant_state_tag(info, tid, self.shared_state)

        assert state_tag == "[WOUNDED]"

    def test_critical_player_gets_critical_tag(self):
        """Player with wounds >= 4 gets [CRITICAL] tag."""
        mapper = TargetIDMapper()
        mapper.enable()
        player = create_test_player(
            agent_id="player_01", name="Vessel Sera",
            health=10, max_health=27, wounds=4
        )
        mapper.assign_ids([player], [])
        tid = mapper.get_target_id("player_01")

        info = mapper.get_combatant_info(tid)
        state_tag = _get_combatant_state_tag(info, tid, self.shared_state)

        assert state_tag == "[CRITICAL]"

    def test_npc_non_combatant_gets_non_combatant_tag(self):
        """Non-prisoner NPC gets [NON-COMBATANT] tag."""
        mapper = TargetIDMapper()
        mapper.enable()
        npc = create_test_npc(
            agent_id="npc_civilian_1", name="Vendor",
            disposition="friendly", entity_type="neutral"
        )
        mapper.register_npc(npc)
        self.shared_state.npc_agents = [npc]
        mapper.assign_ids([], [], npc_agents=[npc])
        tid = mapper.get_target_id("npc_civilian_1")

        info = mapper.get_combatant_info(tid)
        state_tag = _get_combatant_state_tag(info, tid, self.shared_state)

        assert state_tag == "[NON-COMBATANT]"

    def test_vendor_gets_vendor_non_combatant_tag(self):
        """Vendor entities get [VENDOR/NON-COMBATANT] tag."""
        mapper = TargetIDMapper()
        mapper.enable()

        # Build a fake combatant info dict for a vendor
        info = {
            'type': 'vendor',
            'name': 'Junk Dealer',
            'death_state': 'alive',
        }
        state_tag = _get_combatant_state_tag(info, "tgt_vend", self.shared_state)

        assert state_tag == "[VENDOR/NON-COMBATANT]"


# ============================================================================
# LAYER 2: Semantic Validation Tests
# ============================================================================

class TestCheckTargetCombatState:
    """Tests for _check_target_combat_state() semantic validator."""

    def test_warns_on_prisoner_enemy_targeting(self):
        """When DM resolution targets a prisoner enemy with damage,
        the semantic validator must emit a warning."""
        mapper = TargetIDMapper()
        mapper.enable()

        prisoner = create_test_enemy(
            agent_id="enemy_prisoner_1", name="Bound Captive",
            is_active=False, is_prisoner=True
        )
        tid = mapper.register_enemy(prisoner)

        effect = DamageEffect(
            target=tid,
            base_damage=5,
            dealt=5,
            damage_type="wound"
        )

        warning = _check_target_combat_state(prisoner, effect, mapper)

        assert warning is not None
        assert "prisoner" in warning.lower()
        assert prisoner.name in warning

    def test_warns_on_prisoner_npc_targeting(self):
        """When DM resolution targets an NPC prisoner with damage,
        the semantic validator must emit a warning."""
        mapper = TargetIDMapper()
        mapper.enable()

        npc_prisoner = create_test_npc(
            agent_id="enemy_guard_001", name="Subdued Guard",
            disposition="prisoner", entity_type="prisoner"
        )

        effect = DamageEffect(
            target="tgt_fake",
            base_damage=5,
            dealt=5,
            damage_type="wound"
        )

        warning = _check_target_combat_state(npc_prisoner, effect, mapper)

        assert warning is not None
        assert "prisoner" in warning.lower()

    def test_allows_active_enemy_targeting(self):
        """Targeting an active enemy must not trigger any warning."""
        mapper = TargetIDMapper()
        mapper.enable()

        enemy = create_test_enemy(
            agent_id="enemy_grunt_1", name="Active Guard",
            is_active=True, is_prisoner=False
        )
        tid = mapper.register_enemy(enemy)

        effect = DamageEffect(
            target=tid,
            base_damage=5,
            dealt=5,
            damage_type="wound"
        )

        warning = _check_target_combat_state(enemy, effect, mapper)

        assert warning is None

    def test_warns_on_unconscious_targeting(self):
        """Targeting an entity at health=0 must trigger warning."""
        mapper = TargetIDMapper()
        mapper.enable()

        enemy = create_test_enemy(
            agent_id="enemy_grunt_1", name="Downed Guard",
            is_active=False, health=0, max_health=20
        )
        tid = mapper.register_enemy(enemy)

        effect = DamageEffect(
            target=tid,
            base_damage=5,
            dealt=5,
            damage_type="wound"
        )

        warning = _check_target_combat_state(enemy, effect, mapper)

        assert warning is not None
        assert "unconscious" in warning.lower() or "incapacitated" in warning.lower()

    def test_warns_on_defeated_entity_targeting(self):
        """Targeting an inactive non-prisoner entity should warn."""
        mapper = TargetIDMapper()
        mapper.enable()

        enemy = create_test_enemy(
            agent_id="enemy_grunt_1", name="Defeated Guard",
            is_active=False, is_prisoner=False, despawned_round=3
        )
        tid = mapper.register_enemy(enemy)

        effect = DamageEffect(
            target=tid,
            base_damage=5,
            dealt=5,
            damage_type="wound"
        )

        warning = _check_target_combat_state(enemy, effect, mapper)

        assert warning is not None
        assert "defeated" in warning.lower() or "removed" in warning.lower()

    def test_allows_panicked_enemy_targeting(self):
        """Panicked/fleeing enemies are still active — targeting is valid
        (questionable ethically, but mechanically legal)."""
        mapper = TargetIDMapper()
        mapper.enable()

        enemy = create_test_enemy(
            agent_id="enemy_grunt_1", name="Fleeing Guard",
            is_active=True, is_panicked=True
        )
        tid = mapper.register_enemy(enemy)

        effect = DamageEffect(
            target=tid,
            base_damage=5,
            dealt=5,
            damage_type="wound"
        )

        warning = _check_target_combat_state(enemy, effect, mapper)

        # Panicked but active — no warning (ethical dimension handled by SC system)
        assert warning is None


# ============================================================================
# LAYER 4: Enriched get_combatant_info() Tests
# ============================================================================

class TestCombatantInfoStateFields:
    """Tests for enriched get_combatant_info() with state fields."""

    def test_enemy_info_includes_is_active(self):
        """get_combatant_info() must include is_active field for enemies."""
        mapper = TargetIDMapper()
        mapper.enable()

        enemy = create_test_enemy(
            agent_id="enemy_1", name="Guard",
            is_active=True
        )
        tid = mapper.register_enemy(enemy)

        info = mapper.get_combatant_info(tid)

        assert 'is_active' in info
        assert info['is_active'] is True

    def test_enemy_info_includes_is_prisoner(self):
        """get_combatant_info() must include is_prisoner field for enemies."""
        mapper = TargetIDMapper()
        mapper.enable()

        enemy = create_test_enemy(
            agent_id="enemy_1", name="Captive",
            is_prisoner=True
        )
        tid = mapper.register_enemy(enemy)

        info = mapper.get_combatant_info(tid)

        assert 'is_prisoner' in info
        assert info['is_prisoner'] is True

    def test_enemy_info_includes_is_panicked(self):
        """get_combatant_info() must include is_panicked field for enemies."""
        mapper = TargetIDMapper()
        mapper.enable()

        enemy = create_test_enemy(
            agent_id="enemy_1", name="Guard",
            is_panicked=True
        )
        tid = mapper.register_enemy(enemy)

        info = mapper.get_combatant_info(tid)

        assert 'is_panicked' in info
        assert info['is_panicked'] is True

    def test_npc_info_includes_disposition(self):
        """get_combatant_info() must include disposition for NPCs."""
        mapper = TargetIDMapper()
        mapper.enable()

        npc = create_test_npc(
            agent_id="npc_1", name="Vendor",
            disposition="friendly"
        )
        mapper.register_npc(npc)
        mapper.assign_ids([], [], npc_agents=[npc])
        tid = mapper.get_target_id("npc_1")

        info = mapper.get_combatant_info(tid)

        assert 'disposition' in info
        assert info['disposition'] == 'friendly'

    def test_npc_info_includes_entity_subtype(self):
        """get_combatant_info() must include entity_subtype (entity_type) for NPCs."""
        mapper = TargetIDMapper()
        mapper.enable()

        npc = create_test_npc(
            agent_id="npc_1", name="Prisoner",
            entity_type="prisoner"
        )
        mapper.register_npc(npc)
        mapper.assign_ids([], [], npc_agents=[npc])
        tid = mapper.get_target_id("npc_1")

        info = mapper.get_combatant_info(tid)

        assert 'entity_subtype' in info
        assert info['entity_subtype'] == 'prisoner'

    def test_player_info_defaults_for_state_fields(self):
        """Players should get default state field values (no is_prisoner etc.)."""
        mapper = TargetIDMapper()
        mapper.enable()

        player = create_test_player(agent_id="player_01", name="Sera")
        mapper.assign_ids([player], [])
        tid = mapper.get_target_id("player_01")

        info = mapper.get_combatant_info(tid)

        assert 'is_active' in info
        assert info['is_active'] is True  # Players default to active
        assert 'is_prisoner' in info
        assert info['is_prisoner'] is False  # Players are never prisoners
        assert 'is_panicked' in info
        assert info['is_panicked'] is False


# ============================================================================
# LAYER 5: get_combatant_status() Tests
# ============================================================================

class TestGetCombatantStatus:
    """Tests for get_combatant_status() convenience method on TargetIDMapper."""

    def test_active_enemy_returns_active(self):
        """Active enemy -> 'active' status."""
        mapper = TargetIDMapper()
        mapper.enable()

        enemy = create_test_enemy(
            agent_id="enemy_1", name="Active",
            is_active=True, is_prisoner=False
        )
        tid = mapper.register_enemy(enemy)

        assert mapper.get_combatant_status(tid) == "active"

    def test_prisoner_enemy_returns_prisoner(self):
        """Prisoner enemy -> 'prisoner' status."""
        mapper = TargetIDMapper()
        mapper.enable()

        prisoner = create_test_enemy(
            agent_id="enemy_2", name="Prisoner",
            is_active=False, is_prisoner=True
        )
        tid = mapper.register_enemy(prisoner)

        assert mapper.get_combatant_status(tid) == "prisoner"

    def test_panicked_enemy_returns_fleeing(self):
        """Panicked enemy -> 'fleeing' status."""
        mapper = TargetIDMapper()
        mapper.enable()

        panicked = create_test_enemy(
            agent_id="enemy_3", name="Panicked",
            is_active=True, is_panicked=True
        )
        tid = mapper.register_enemy(panicked)

        assert mapper.get_combatant_status(tid) == "fleeing"

    def test_defeated_enemy_returns_defeated(self):
        """Inactive non-prisoner enemy -> 'defeated' status."""
        mapper = TargetIDMapper()
        mapper.enable()

        defeated = create_test_enemy(
            agent_id="enemy_4", name="Defeated",
            is_active=False, is_prisoner=False
        )
        tid = mapper.register_enemy(defeated)

        assert mapper.get_combatant_status(tid) == "defeated"

    def test_dead_enemy_returns_dead(self):
        """Enemy with wounds >= 6 -> 'dead' status."""
        mapper = TargetIDMapper()
        mapper.enable()

        dead = create_test_enemy(
            agent_id="enemy_5", name="Dead",
            is_active=False, wounds=6
        )
        tid = mapper.register_enemy(dead)

        assert mapper.get_combatant_status(tid) == "dead"

    def test_unconscious_enemy_returns_unconscious(self):
        """Enemy at health=0 -> 'unconscious' status."""
        mapper = TargetIDMapper()
        mapper.enable()

        ko = create_test_enemy(
            agent_id="enemy_6", name="KO",
            is_active=False, health=0, max_health=20
        )
        tid = mapper.register_enemy(ko)

        assert mapper.get_combatant_status(tid) == "unconscious"

    def test_npc_non_combatant_returns_non_combatant(self):
        """Neutral NPC -> 'non_combatant' status."""
        mapper = TargetIDMapper()
        mapper.enable()

        npc = create_test_npc(
            agent_id="npc_1", name="Civilian",
            disposition="neutral", entity_type="neutral"
        )
        mapper.register_npc(npc)
        mapper.assign_ids([], [], npc_agents=[npc])
        tid = mapper.get_target_id("npc_1")

        assert mapper.get_combatant_status(tid) == "non_combatant"

    def test_npc_prisoner_returns_prisoner(self):
        """NPC with disposition=prisoner -> 'prisoner' status."""
        mapper = TargetIDMapper()
        mapper.enable()

        npc = create_test_npc(
            agent_id="npc_2", name="Subdued",
            disposition="prisoner", entity_type="prisoner"
        )
        mapper.register_npc(npc)
        mapper.assign_ids([], [], npc_agents=[npc])
        tid = mapper.get_target_id("npc_2")

        assert mapper.get_combatant_status(tid) == "prisoner"

    def test_active_player_returns_active(self):
        """Active player -> 'active' status."""
        mapper = TargetIDMapper()
        mapper.enable()

        player = create_test_player(agent_id="player_01", name="Sera")
        mapper.assign_ids([player], [])
        tid = mapper.get_target_id("player_01")

        assert mapper.get_combatant_status(tid) == "active"

    def test_unknown_target_returns_none(self):
        """Non-existent target ID -> None."""
        mapper = TargetIDMapper()
        mapper.enable()

        assert mapper.get_combatant_status("tgt_fake") is None


# ============================================================================
# LAYER 9: Mixed Combatant List State Tags (Integration)
# ============================================================================

class TestMixedCombatantListStateTags:
    """Integration test: realistic combatant list with mixed entities."""

    def test_mixed_combatant_list_produces_correct_tags(self):
        """Build a combatant list with a mix of active enemies, prisoners,
        NPCs, and players. Verify all get correct state tags."""
        mapper = TargetIDMapper()
        mapper.enable()
        shared_state = MockSharedState()

        # Active enemy
        active_enemy = create_test_enemy(
            agent_id="enemy_1", name="Enforcer",
            is_active=True
        )
        # Prisoner enemy
        prisoner_enemy = create_test_enemy(
            agent_id="enemy_2", name="Captured Sentry",
            is_active=False, is_prisoner=True
        )
        # Prisoner NPC (converted from enemy)
        prisoner_npc = create_test_npc(
            agent_id="enemy_3", name="Subdued Guard",
            disposition="prisoner", entity_type="prisoner"
        )
        # Active player
        player = create_test_player(
            agent_id="player_01", name="Vessel Sera",
            health=20, max_health=27
        )

        # Register all entities via assign_ids (handles players, active enemies, NPCs)
        # Note: assign_ids only includes active enemies. Prisoner enemies are
        # re-registered after since they were captured mid-combat (already had IDs).
        mapper.assign_ids(
            [player],
            [active_enemy],  # Only active enemies go through assign_ids
            npc_agents=[prisoner_npc]
        )
        mapper.register_npc(prisoner_npc)
        # Prisoner enemy gets re-registered (simulates being captured after initial registration)
        mapper.register_enemy(prisoner_enemy)

        shared_state.npc_agents = [prisoner_npc]
        shared_state.enemy_combat.enemy_agents = [active_enemy, prisoner_enemy]

        # Verify tags for each entity
        results = {}
        for tid in mapper.get_all_target_ids():
            info = mapper.get_combatant_info(tid)
            if info:
                tag = _get_combatant_state_tag(info, tid, shared_state)
                results[info['name']] = tag

        assert results.get("Enforcer") == "[ACTIVE]", f"Active enemy got {results.get('Enforcer')}"
        assert results.get("Captured Sentry") == "[PRISONER]", f"Prisoner enemy got {results.get('Captured Sentry')}"
        assert results.get("Subdued Guard") == "[PRISONER]", f"Prisoner NPC got {results.get('Subdued Guard')}"
        assert results.get("Vessel Sera") == "[ACTIVE]", f"Active player got {results.get('Vessel Sera')}"


# ============================================================================
# Existing Validation Pipeline Tests
# ============================================================================

class TestExistingValidationPipeline:
    """Tests for existing validation steps (STEPS 1-5) to ensure
    they still work after our additions."""

    def test_valid_targeting_passes(self):
        """Valid targeting should pass all steps."""
        mapper = TargetIDMapper()
        mapper.enable()

        enemy = create_test_enemy(agent_id="enemy_1", name="Guard")
        tid = mapper.register_enemy(enemy)

        effect = DamageEffect(
            target=tid,
            base_damage=5,
            dealt=5,
            damage_type="wound"
        )
        declared = {'target': tid}

        is_valid, corrected, error = validate_and_correct_targeting(
            effect, declared, mapper
        )

        assert is_valid is True
        assert corrected is not None
        assert error is None

    def test_missing_target_uses_declared(self):
        """Missing target field should correct from declared action."""
        mapper = TargetIDMapper()
        mapper.enable()

        enemy = create_test_enemy(agent_id="enemy_1", name="Guard")
        tid = mapper.register_enemy(enemy)

        effect = DamageEffect(
            target="",  # Will be falsy
            base_damage=5,
            dealt=5,
            damage_type="wound"
        )
        declared = {'target': tid}

        is_valid, corrected, error = validate_and_correct_targeting(
            effect, declared, mapper
        )

        assert is_valid is True
        assert corrected is not None
        assert corrected.target == tid

    def test_character_name_corrected_to_id(self):
        """Character name should be corrected to target ID."""
        mapper = TargetIDMapper()
        mapper.enable()

        enemy = create_test_enemy(agent_id="enemy_1", name="Syndicate Enforcer")
        tid = mapper.register_enemy(enemy)

        effect = DamageEffect(
            target="Syndicate Enforcer",  # Name instead of ID
            base_damage=5,
            dealt=5,
            damage_type="wound"
        )
        declared = {'target': tid}

        is_valid, corrected, error = validate_and_correct_targeting(
            effect, declared, mapper
        )

        assert is_valid is True
        assert corrected.target == tid
