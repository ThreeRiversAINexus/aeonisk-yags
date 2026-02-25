"""
Unit tests for Inventory & Equipment Overhaul (Spec 07).

Tests cover:
1. NPC EnergyPurse initialization (npc_agent.py)
2. Converted NPC purse initialization (agent_conversion.py)
3. Weapon stats in DM resolution prompt (dm.py)
4. Formalized enemy loot acquisition (energy_economy.py)
5. Inter-agent item transfer (dm.py, player.py)
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field

from scripts.aeonisk.multiagent.energy_economy import (
    EnergyPurse,
    LootResult,
    acquire_loot,
    item_name_to_inventory_key,
)
from scripts.aeonisk.multiagent.npc_agent import NPCAgent
from scripts.aeonisk.multiagent.agent_conversion import deescalate_enemy_to_npc
from scripts.aeonisk.multiagent.weapons import Weapon, get_weapon, WEAPON_LIBRARY
from scripts.aeonisk.multiagent.dm import (
    _resolve_weapon_and_damage_type,
    _get_attacker_strength,
    _build_weapon_context,
    _execute_item_transfer,
)


# =============================================================================
# Test Helpers
# =============================================================================

def _make_npc(**kwargs):
    """Create a minimal NPCAgent for testing (no LLM client)."""
    defaults = dict(
        agent_id="npc_test_01",
        name="Test NPC",
        faction="Civilian",
        entity_type="neutral",
        disposition="friendly",
        threat_level="non_combatant",
        description="A test NPC",
        health=20,
        max_health=20,
        soak=6,
        void_score=0,
        can_act=False,  # Prevent LLM client init
    )
    defaults.update(kwargs)
    return NPCAgent(**defaults)


def _make_enemy_agent(**kwargs):
    """Create a minimal EnemyAgent for testing."""
    from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position
    defaults = dict(
        agent_id="enemy_grunt_01",
        name="Street Thug",
        faction="Freeborn",
        template="grunt",
        health=15,
        max_health=15,
        soak=8,
        wounds=0,
        void_score=0,
        skills={"Guns": 2, "Melee": 1},
        attributes={"Strength": 3, "Agility": 3, "Perception": 3, "Dexterity": 3},
        weapons=[get_weapon("pistol")],
        position=Position(ring="Near", side="Enemy"),
        initiative=5,
        spawned_round=0,
    )
    defaults.update(kwargs)
    return EnemyAgent(**defaults)


def _make_player_agent(
    agent_id="player_01",
    name="Kael Dren",
    faction="Freeborn",
    strength=3,
    primary_weapon="pistol",
    sidearm_weapon=None,
    inventory=None,
    energy_purse=None,
):
    """Create a mock AIPlayerAgent for testing."""
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.equipped_weapons = {
        "primary": get_weapon(primary_weapon) if primary_weapon else None,
        "sidearm": get_weapon(sidearm_weapon) if sidearm_weapon else None,
    }
    agent.weapon_inventory = []

    # Character state
    char_state = MagicMock()
    char_state.name = name
    char_state.faction = faction
    char_state.attributes = {
        "Strength": strength,
        "Agility": 3,
        "Perception": 3,
        "Dexterity": 3,
        "Intelligence": 3,
        "Empathy": 3,
        "Willpower": 3,
        "Endurance": 3,
    }
    char_state.inventory = inventory if inventory is not None else {"med_kit": 1}
    char_state.energy_purse = energy_purse if energy_purse is not None else EnergyPurse(
        breath=10, drip=20, grain=5, spark=2
    )
    agent.character_state = char_state
    return agent


def _make_shared_state(player_agents=None, npc_agents=None, enemy_agents=None):
    """Create a mock SharedState for testing."""
    state = MagicMock()
    state.player_agents = player_agents or []
    state.npc_agents = npc_agents or []

    if enemy_agents is not None:
        state.enemy_combat = MagicMock()
        state.enemy_combat.enemy_agents = enemy_agents
    else:
        state.enemy_combat = None

    return state


# =============================================================================
# Phase 1: NPC EnergyPurse Initialization
# =============================================================================

class TestNPCPurseInitialization:
    """NPCs should always have an EnergyPurse after creation."""

    def test_npc_created_with_empty_purse(self):
        """NPCs should always have an EnergyPurse after creation."""
        npc = _make_npc()
        assert npc.energy_purse is not None
        assert isinstance(npc.energy_purse, EnergyPurse)
        assert npc.energy_purse.breath == 0
        assert npc.energy_purse.drip == 0
        assert npc.energy_purse.grain == 0
        assert npc.energy_purse.spark == 0

    def test_npc_currency_transfer_succeeds(self):
        """Currency transfer to NPC should work now that purse exists."""
        npc = _make_npc()
        player_purse = EnergyPurse(breath=0, drip=10, grain=0, spark=0)
        success = player_purse.transfer_currency_to(npc.energy_purse, "drip", 5)
        assert success is True
        assert npc.energy_purse.drip == 5
        assert player_purse.drip == 5

    def test_vendor_npc_purse_preserved(self):
        """Vendor NPCs with explicit purse should keep their purse, not get overridden."""
        vendor_purse = EnergyPurse(breath=0, drip=100, grain=0, spark=50)
        npc = _make_npc(
            is_vendor=True,
            energy_purse=vendor_purse,
        )
        # Explicit purse should NOT be overridden by __post_init__
        assert npc.energy_purse.drip == 100
        assert npc.energy_purse.spark == 50

    def test_converted_npc_has_purse(self):
        """Enemy deescalated to NPC should have an energy purse."""
        enemy = _make_enemy_agent()
        npc = deescalate_enemy_to_npc(enemy, "wary", current_round=1)
        assert npc.energy_purse is not None
        assert isinstance(npc.energy_purse, EnergyPurse)

    def test_converted_npc_currency_transfer_works(self):
        """Converted NPC should be able to receive currency."""
        enemy = _make_enemy_agent()
        npc = deescalate_enemy_to_npc(enemy, "prisoner", current_round=1)
        player_purse = EnergyPurse(breath=0, drip=10, grain=0, spark=0)
        success = player_purse.transfer_currency_to(npc.energy_purse, "drip", 5)
        assert success is True
        assert npc.energy_purse.drip == 5

    def test_npc_purse_is_independent_instance(self):
        """Each NPC should have its own purse, not a shared reference."""
        npc1 = _make_npc(agent_id="npc_1", name="NPC 1")
        npc2 = _make_npc(agent_id="npc_2", name="NPC 2")
        npc1.energy_purse.add_currency("drip", 10)
        assert npc2.energy_purse.drip == 0  # Should not be affected


# =============================================================================
# Phase 2: Weapon Stats in DM Resolution Prompt
# =============================================================================

class TestWeaponStatsInDMPrompt:
    """DM resolution prompt should include mechanical weapon stats."""

    def test_get_attacker_strength(self):
        """_get_attacker_strength should return the player's Strength attribute."""
        player = _make_player_agent(agent_id="player_01", strength=4)
        shared_state = _make_shared_state(player_agents=[player])
        action = {"agent_id": "player_01", "action_type": "combat", "skill": "Guns"}
        result = _get_attacker_strength(action, shared_state)
        assert result == 4

    def test_get_attacker_strength_default(self):
        """_get_attacker_strength should return 3 if player not found."""
        shared_state = _make_shared_state(player_agents=[])
        action = {"agent_id": "player_99", "action_type": "combat", "skill": "Guns"}
        result = _get_attacker_strength(action, shared_state)
        assert result == 3

    def test_get_attacker_strength_no_agent_id(self):
        """_get_attacker_strength should return 3 if no agent_id in action."""
        shared_state = _make_shared_state()
        action = {"action_type": "combat", "skill": "Guns"}
        result = _get_attacker_strength(action, shared_state)
        assert result == 3

    def test_build_weapon_context_includes_damage_stat(self):
        """Weapon context should include weapon.damage bonus."""
        player = _make_player_agent(
            agent_id="player_01",
            primary_weapon="pistol",
            strength=3,
        )
        shared_state = _make_shared_state(player_agents=[player])
        action = {"agent_id": "player_01", "action_type": "combat", "skill": "Guns"}

        context = _build_weapon_context(action, shared_state)
        # Pistol damage = 6
        assert "Weapon Damage Bonus: 6" in context
        assert "Attack Bonus: 0" in context

    def test_build_weapon_context_includes_strength(self):
        """Weapon context should include attacker's Strength."""
        player = _make_player_agent(
            agent_id="player_01",
            primary_weapon="pistol",
            strength=4,
        )
        shared_state = _make_shared_state(player_agents=[player])
        action = {"agent_id": "player_01", "action_type": "combat", "skill": "Guns"}

        context = _build_weapon_context(action, shared_state)
        assert "Strength(4)" in context

    def test_build_weapon_context_damage_guidance_tiers(self):
        """Weapon context should show base_damage guidance by success tier."""
        player = _make_player_agent(
            agent_id="player_01",
            primary_weapon="pistol",  # damage=6
            strength=3,
        )
        shared_state = _make_shared_state(player_agents=[player])
        action = {"agent_id": "player_01", "action_type": "combat", "skill": "Guns"}

        context = _build_weapon_context(action, shared_state)
        # Str(3) + Weapon(6) = 9 for marginal success
        assert "base_damage = 9" in context
        assert "Marginal success" in context
        assert "Moderate success" in context

    def test_build_weapon_context_melee_weapon(self):
        """Weapon context for melee weapon should use sidearm."""
        player = _make_player_agent(
            agent_id="player_01",
            primary_weapon="pistol",
            sidearm_weapon="combat_knife",  # damage=6
            strength=4,
        )
        shared_state = _make_shared_state(player_agents=[player])
        action = {"agent_id": "player_01", "action_type": "combat", "skill": "Melee"}

        context = _build_weapon_context(action, shared_state)
        assert "Combat Knife" in context
        assert "Weapon Damage Bonus: 6" in context

    def test_build_weapon_context_unarmed(self):
        """Unarmed weapon context should show fists stats."""
        player = _make_player_agent(
            agent_id="player_01",
            primary_weapon="pistol",
            sidearm_weapon=None,
            strength=3,
        )
        shared_state = _make_shared_state(player_agents=[player])
        action = {"agent_id": "player_01", "action_type": "brawl", "skill": "Brawl"}

        context = _build_weapon_context(action, shared_state)
        assert "STUN" in context or "stun" in context
        assert "Weapon Damage Bonus: 0" in context

    def test_build_weapon_context_unknown_weapon_returns_empty(self):
        """If no weapon found, context should be empty."""
        shared_state = _make_shared_state(player_agents=[])
        action = {"agent_id": "unknown", "action_type": "combat", "skill": "Guns"}

        context = _build_weapon_context(action, shared_state)
        assert context == ""


# =============================================================================
# Phase 3: Loot Tables (acquire_loot)
# =============================================================================

class TestLootResult:
    """LootResult dataclass for structured loot."""

    def test_loot_result_structure(self):
        """LootResult should have required fields."""
        loot = LootResult(
            weapons=[],
            currency={"breath": 10, "drip": 5},
            seeds=[],
            special_items=["encrypted datapad"],
            source_name="Street Thug",
            description="Loot from Street Thug",
        )
        assert loot.source_name == "Street Thug"
        assert loot.currency["breath"] == 10
        assert len(loot.special_items) == 1

    def test_loot_result_empty(self):
        """LootResult with no items."""
        loot = LootResult(
            weapons=[],
            currency={},
            seeds=[],
            special_items=[],
            source_name="Unarmed Civilian",
            description="No loot",
        )
        assert len(loot.weapons) == 0
        assert len(loot.currency) == 0


class TestAcquireLoot:
    """acquire_loot() should add items to player inventory."""

    def test_acquire_loot_adds_currency(self):
        """acquire_loot should transfer loot currency to player's purse."""
        player = _make_player_agent(
            energy_purse=EnergyPurse(breath=0, drip=0, grain=0, spark=0),
        )
        enemy = _make_enemy_agent()

        result = acquire_loot(player.character_state, enemy)
        assert isinstance(result, LootResult)
        # Currency should be added to player purse
        purse = player.character_state.energy_purse
        total_currency = purse.breath + purse.drip + purse.grain + purse.spark
        assert total_currency > 0

    def test_acquire_loot_adds_special_items(self):
        """acquire_loot should add special items to player inventory."""
        player = _make_player_agent(
            energy_purse=EnergyPurse(breath=0, drip=0, grain=0, spark=0),
            inventory={"med_kit": 0},
        )
        enemy = _make_enemy_agent()

        # Force special item by mocking random
        with patch('scripts.aeonisk.multiagent.energy_economy.random') as mock_random:
            # Force special item: random < 0.1 for special, choice returns "encrypted datapad"
            mock_random.randint.side_effect = lambda a, b: (a + b) // 2  # Midpoint values
            mock_random.random.return_value = 0.05  # Forces special item drop
            mock_random.choice.return_value = "encrypted datapad"

            result = acquire_loot(player.character_state, enemy)

        # Check special items are in inventory
        if result.special_items:
            for item_name in result.special_items:
                key = item_name_to_inventory_key(item_name)
                assert player.character_state.inventory.get(key, 0) > 0

    def test_acquire_loot_returns_loot_result(self):
        """acquire_loot should return a LootResult."""
        player = _make_player_agent()
        enemy = _make_enemy_agent()

        result = acquire_loot(player.character_state, enemy)
        assert isinstance(result, LootResult)
        assert result.source_name == enemy.name

    def test_acquire_loot_no_weapons(self):
        """acquire_loot with weaponless enemy should still return loot (currency)."""
        player = _make_player_agent(
            energy_purse=EnergyPurse(breath=0, drip=0, grain=0, spark=0),
        )
        enemy = _make_enemy_agent(weapons=[])

        result = acquire_loot(player.character_state, enemy)
        assert isinstance(result, LootResult)
        assert len(result.weapons) == 0


# =============================================================================
# Phase 4: Inter-Agent Item Transfer
# =============================================================================

class TestInterAgentTransfer:
    """Test item and currency transfers between PCs and NPCs."""

    def test_pc_to_npc_currency_transfer(self):
        """Player should be able to transfer currency to NPC."""
        player = _make_player_agent(
            energy_purse=EnergyPurse(breath=0, drip=20, grain=0, spark=0),
        )
        npc = _make_npc()
        shared_state = _make_shared_state(
            player_agents=[player],
            npc_agents=[npc],
        )

        result = _execute_item_transfer(
            source_agent_id="player_01",
            target_agent_id="npc_test_01",
            currency_amounts={"drip": 10},
            item_amounts=None,
            shared_state=shared_state,
        )
        assert result["success"] is True
        assert player.character_state.energy_purse.drip == 10
        assert npc.energy_purse.drip == 10

    def test_npc_to_pc_currency_transfer(self):
        """NPC should be able to transfer currency to player."""
        npc = _make_npc()
        npc.energy_purse.add_currency("drip", 15)
        player = _make_player_agent(
            energy_purse=EnergyPurse(breath=0, drip=0, grain=0, spark=0),
        )
        shared_state = _make_shared_state(
            player_agents=[player],
            npc_agents=[npc],
        )

        result = _execute_item_transfer(
            source_agent_id="npc_test_01",
            target_agent_id="player_01",
            currency_amounts={"drip": 10},
            item_amounts=None,
            shared_state=shared_state,
        )
        assert result["success"] is True
        assert npc.energy_purse.drip == 5
        assert player.character_state.energy_purse.drip == 10

    def test_pc_to_npc_item_transfer(self):
        """Player should be able to transfer items to NPC."""
        player = _make_player_agent(
            inventory={"med_kit": 2},
        )
        npc = _make_npc()
        shared_state = _make_shared_state(
            player_agents=[player],
            npc_agents=[npc],
        )

        result = _execute_item_transfer(
            source_agent_id="player_01",
            target_agent_id="npc_test_01",
            currency_amounts=None,
            item_amounts={"med_kit": 1},
            shared_state=shared_state,
        )
        assert result["success"] is True
        assert player.character_state.inventory["med_kit"] == 1

    def test_insufficient_currency_fails(self):
        """Transfer should fail if source lacks currency."""
        player = _make_player_agent(
            energy_purse=EnergyPurse(breath=0, drip=2, grain=0, spark=0),
        )
        npc = _make_npc()
        shared_state = _make_shared_state(
            player_agents=[player],
            npc_agents=[npc],
        )

        result = _execute_item_transfer(
            source_agent_id="player_01",
            target_agent_id="npc_test_01",
            currency_amounts={"drip": 10},
            item_amounts=None,
            shared_state=shared_state,
        )
        assert result["success"] is False

    def test_insufficient_items_fails(self):
        """Transfer should fail if source lacks items."""
        player = _make_player_agent(
            inventory={"med_kit": 0},
        )
        npc = _make_npc()
        shared_state = _make_shared_state(
            player_agents=[player],
            npc_agents=[npc],
        )

        result = _execute_item_transfer(
            source_agent_id="player_01",
            target_agent_id="npc_test_01",
            currency_amounts=None,
            item_amounts={"med_kit": 1},
            shared_state=shared_state,
        )
        assert result["success"] is False

    def test_unknown_source_fails(self):
        """Transfer should fail if source agent not found."""
        npc = _make_npc()
        shared_state = _make_shared_state(
            player_agents=[],
            npc_agents=[npc],
        )

        result = _execute_item_transfer(
            source_agent_id="unknown_agent",
            target_agent_id="npc_test_01",
            currency_amounts={"drip": 5},
            item_amounts=None,
            shared_state=shared_state,
        )
        assert result["success"] is False

    def test_unknown_target_fails(self):
        """Transfer should fail if target agent not found."""
        player = _make_player_agent()
        shared_state = _make_shared_state(
            player_agents=[player],
            npc_agents=[],
        )

        result = _execute_item_transfer(
            source_agent_id="player_01",
            target_agent_id="unknown_agent",
            currency_amounts={"drip": 5},
            item_amounts=None,
            shared_state=shared_state,
        )
        assert result["success"] is False


# =============================================================================
# Phase 5: Find/Pickup Item Action
# =============================================================================

class TestFindPickupItem:
    """Test item discovery and addition to inventory via DM resolution."""

    def test_item_name_to_inventory_key(self):
        """item_name_to_inventory_key should handle various formats."""
        assert item_name_to_inventory_key("Med Kit") == "med_kit"
        assert item_name_to_inventory_key("Encrypted Datapad") == "encrypted_datapad"
        assert item_name_to_inventory_key("Echo-Calibrator") == "echo_calibrator"
        assert item_name_to_inventory_key("Med Kit (Basic)") == "med_kit_basic"
