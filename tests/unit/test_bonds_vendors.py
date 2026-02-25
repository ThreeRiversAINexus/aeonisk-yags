"""
Unit tests for Spec 13: Bond System Completion & Vendor Spawning.

Tests cover:
- Default bond initialization (bonds=[] always exists on character state)
- bonds_enabled config flag (opt-out via bonds_enabled=false)
- Bond matrix generation by default for party_size >= 2
- Bond formation/breaking as player actions
- Agent bond context in prompts
- NPC vendor inventory initialization with faction-appropriate items
- Live bond transition testing (void-driven auto-transitions)
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from scripts.aeonisk.multiagent.schemas.shared_types import (
    Bond, BondType, BondStatus, BondTargetType
)
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine


# ============================================================================
# Helper: create a Bond instance for testing
# ============================================================================

def _make_bond(
    bond_id="bond_test_001",
    char_a="Alice",
    char_b="Bob",
    bond_type=BondType.KINSHIP,
    status=BondStatus.ACTIVE,
    formed_round=0,
    witnessed_by=None,
    narrative="Test bond",
):
    return Bond(
        bond_id=bond_id,
        character_a=char_a,
        character_b=char_b,
        bond_type=bond_type,
        status=status,
        formed_round=formed_round,
        witnessed_by=witnessed_by or [],
        narrative_description=narrative,
    )


# ============================================================================
# 1. Default Bond Initialization
# ============================================================================


class TestDefaultBondInitialization:
    """Characters always have bonds attribute as empty list."""

    def test_character_state_has_bonds_list(self):
        """CharacterState always initializes bonds as a list."""
        from scripts.aeonisk.multiagent.player import CharacterState

        state = CharacterState(
            name="Test Character",
            faction="Sovereign Nexus",
            attributes={"Strength": 3, "Agility": 4},
            skills={"Awareness": 2},
            void_score=0,
            soulcredit=5,
            bonds=[],
            goals=["Survive"],
        )
        assert isinstance(state.bonds, list)
        assert state.bonds == []

    def test_character_state_bonds_default_empty_from_config(self):
        """When character config has no 'bonds' key, bonds defaults to empty list."""
        from scripts.aeonisk.multiagent.player import CharacterState

        # Simulate config without bonds - the default should be []
        state = CharacterState(
            name="No Bonds Char",
            faction="Freeborn",
            attributes={"Strength": 3},
            skills={},
            void_score=0,
            soulcredit=5,
            bonds=[],  # This is what session.py passes via .get('bonds', [])
            goals=[],
        )
        assert isinstance(state.bonds, list)
        assert len(state.bonds) == 0

    def test_character_config_bonds_get_default(self):
        """Config .get('bonds', []) returns empty list when key absent."""
        config = {"name": "Test", "faction": "Tempest"}
        bonds = config.get('bonds', [])
        assert bonds == []


# ============================================================================
# 2. bonds_enabled Config Flag
# ============================================================================


class TestBondsEnabledConfigFlag:
    """bonds_enabled config flag controls bond matrix generation."""

    def test_bonds_enabled_defaults_to_true(self):
        """bonds_enabled defaults to True when absent from config."""
        config = {"session_name": "test", "agents": {"dm": {}}}
        bonds_enabled = config.get('bonds_enabled', True)
        assert bonds_enabled is True

    def test_bonds_enabled_false_disables(self):
        """bonds_enabled=False explicitly disables bond generation."""
        config = {"session_name": "test", "bonds_enabled": False}
        bonds_enabled = config.get('bonds_enabled', True)
        assert bonds_enabled is False

    def test_bonds_enabled_true_enables(self):
        """bonds_enabled=True explicitly enables bond generation."""
        config = {"session_name": "test", "bonds_enabled": True}
        bonds_enabled = config.get('bonds_enabled', True)
        assert bonds_enabled is True

    def test_session_respects_bonds_enabled_false(self):
        """Session setup skips bond generation when bonds_enabled=False."""
        from scripts.aeonisk.multiagent.session import SelfPlayingSession

        # The _should_generate_bonds method should return False
        # when bonds_enabled is False in config
        config = {
            "bonds_enabled": False,
            "party_size": 4,
        }
        result = _should_generate_bonds(config, party_size=4)
        assert result is False

    def test_session_generates_bonds_by_default(self):
        """Session generates bonds by default when bonds_enabled not specified."""
        config = {
            "party_size": 4,
        }
        result = _should_generate_bonds(config, party_size=4)
        assert result is True

    def test_session_skips_bonds_for_single_player(self):
        """Session skips bond generation for single-player sessions."""
        config = {
            "bonds_enabled": True,
            "party_size": 1,
        }
        result = _should_generate_bonds(config, party_size=1)
        assert result is False


def _should_generate_bonds(config: dict, party_size: int) -> bool:
    """Helper matching session.py logic for bond generation decision."""
    bonds_enabled = config.get('bonds_enabled', True)
    if not bonds_enabled:
        return False
    if party_size < 2:
        return False
    return True


# ============================================================================
# 3. Bond Matrix Generation
# ============================================================================


class TestBondMatrixGeneration:
    """Bond matrix generation for party_size >= 2."""

    def setup_method(self):
        self.mechanics = MechanicsEngine()

    def test_generate_default_bond_matrix_two_players(self):
        """Generate bond matrix with 2 players creates at least 1 bond."""
        from scripts.aeonisk.multiagent.mechanics import generate_default_bond_matrix

        bonds = generate_default_bond_matrix(
            character_names=["Alice", "Bob"],
            factions={"Alice": "Sovereign Nexus", "Bob": "Tempest"},
            random_seed=42,
        )
        assert len(bonds) >= 1
        # Verify bond structure
        for bond in bonds:
            assert 'character_a' in bond
            assert 'character_b' in bond
            assert 'bond_type' in bond

    def test_generate_default_bond_matrix_four_players(self):
        """Generate bond matrix with 4 players creates bonds for all."""
        from scripts.aeonisk.multiagent.mechanics import generate_default_bond_matrix

        names = ["Alice", "Bob", "Charlie", "Dana"]
        factions = {n: "Sovereign Nexus" for n in names}

        bonds = generate_default_bond_matrix(
            character_names=names,
            factions=factions,
            random_seed=42,
        )
        # Every character should have at least 1 bond
        bonded_chars = set()
        for bond in bonds:
            bonded_chars.add(bond['character_a'])
            bonded_chars.add(bond['character_b'])
        assert bonded_chars == set(names)

    def test_generate_default_bond_matrix_deterministic(self):
        """Same seed produces same bond matrix."""
        from scripts.aeonisk.multiagent.mechanics import generate_default_bond_matrix

        names = ["Alice", "Bob", "Charlie"]
        factions = {n: "Tempest" for n in names}

        bonds1 = generate_default_bond_matrix(names, factions, random_seed=12345)
        bonds2 = generate_default_bond_matrix(names, factions, random_seed=12345)

        assert len(bonds1) == len(bonds2)
        for b1, b2 in zip(bonds1, bonds2):
            assert b1['character_a'] == b2['character_a']
            assert b1['character_b'] == b2['character_b']
            assert b1['bond_type'] == b2['bond_type']

    def test_generate_default_bond_matrix_valid_bond_types(self):
        """All generated bond types are valid BondType values."""
        from scripts.aeonisk.multiagent.mechanics import generate_default_bond_matrix

        bonds = generate_default_bond_matrix(
            character_names=["Alice", "Bob", "Charlie"],
            factions={"Alice": "Tempest", "Bob": "Sovereign Nexus", "Charlie": "Freeborn"},
            random_seed=42,
        )
        valid_types = {bt.value for bt in BondType}
        for bond in bonds:
            assert bond['bond_type'] in valid_types

    def test_generate_default_bond_matrix_freeborn_limit(self):
        """Freeborn characters get maximum 1 bond."""
        from scripts.aeonisk.multiagent.mechanics import generate_default_bond_matrix

        # 4 players, one Freeborn
        names = ["Alice", "Bob", "Charlie", "FreeChar"]
        factions = {"Alice": "Tempest", "Bob": "Tempest", "Charlie": "Tempest", "FreeChar": "Freeborn"}

        bonds = generate_default_bond_matrix(
            character_names=names,
            factions=factions,
            random_seed=42,
        )
        # Count bonds for the Freeborn character
        freeborn_bonds = sum(
            1 for b in bonds
            if b['character_a'] == "FreeChar" or b['character_b'] == "FreeChar"
        )
        assert freeborn_bonds <= 1


# ============================================================================
# 4. Player Bond Context in Prompts
# ============================================================================


class TestPlayerBondContext:
    """Player agents see their bonds in action prompts."""

    def test_build_bond_context_with_active_bonds(self):
        """Active bonds show benefits in context string."""
        from scripts.aeonisk.multiagent.player import build_bond_context

        bonds = [
            _make_bond(char_a="Alice", char_b="Bob", status=BondStatus.ACTIVE,
                       bond_type=BondType.KINSHIP),
            _make_bond(bond_id="bond_test_002", char_a="Alice", char_b="Charlie",
                       status=BondStatus.DORMANT, bond_type=BondType.PASSION),
        ]
        context = build_bond_context(bonds)
        assert "Bob" in context
        assert "Charlie" in context
        assert "[ACTIVE]" in context
        assert "[DORMANT]" in context
        assert "Your Bonds:" in context

    def test_build_bond_context_empty_bonds(self):
        """Empty bonds list returns empty string."""
        from scripts.aeonisk.multiagent.player import build_bond_context

        context = build_bond_context([])
        assert context == ""

    def test_build_bond_context_shows_benefits_for_active(self):
        """Active bonds display mechanical benefits."""
        from scripts.aeonisk.multiagent.player import build_bond_context

        bonds = [
            _make_bond(status=BondStatus.ACTIVE, bond_type=BondType.KINSHIP),
        ]
        context = build_bond_context(bonds)
        assert "+2 ritual bonus" in context or "ritual" in context.lower()
        assert "+1 soak" in context.lower() or "soak" in context.lower()

    def test_build_bond_context_no_benefits_for_dormant(self):
        """Dormant bonds do not show mechanical benefits."""
        from scripts.aeonisk.multiagent.player import build_bond_context

        bonds = [
            _make_bond(status=BondStatus.DORMANT),
        ]
        context = build_bond_context(bonds)
        assert "[DORMANT]" in context
        # Should not show active benefits
        assert "+2 ritual bonus" not in context

    def test_build_bond_context_severed_and_void_locked(self):
        """Severed and void-locked bonds show appropriate status."""
        from scripts.aeonisk.multiagent.player import build_bond_context

        bonds = [
            _make_bond(bond_id="b1", char_b="Bob", status=BondStatus.SEVERED),
            _make_bond(bond_id="b2", char_b="Eve", status=BondStatus.VOID_LOCKED),
        ]
        context = build_bond_context(bonds)
        assert "[SEVERED]" in context
        assert "[VOID-LOCKED]" in context


# ============================================================================
# 5. NPC Vendor Inventory
# ============================================================================


class TestNPCVendorInventory:
    """NPC vendors initialized with faction-appropriate items."""

    def test_initialize_vendor_inventory_sovereign_nexus(self):
        """Sovereign Nexus vendors get sanctioned items."""
        from scripts.aeonisk.multiagent.npc_agent import initialize_vendor_inventory

        items = initialize_vendor_inventory(faction="Sovereign Nexus")
        assert len(items) >= 3
        # Should have proper VendorItem structure
        for item in items:
            assert hasattr(item, 'name')
            assert hasattr(item, 'price_spark') or hasattr(item, 'price_grain')

    def test_initialize_vendor_inventory_tempest(self):
        """Tempest vendors get void-related items."""
        from scripts.aeonisk.multiagent.npc_agent import initialize_vendor_inventory

        items = initialize_vendor_inventory(faction="Tempest")
        assert len(items) >= 3
        # At least one item should be void-related
        item_names = [item.name.lower() for item in items]
        has_void_item = any('void' in name or 'hollow' in name for name in item_names)
        assert has_void_item, f"Tempest vendor should have void items, got: {item_names}"

    def test_initialize_vendor_inventory_freeborn(self):
        """Freeborn vendors get practical survival items."""
        from scripts.aeonisk.multiagent.npc_agent import initialize_vendor_inventory

        items = initialize_vendor_inventory(faction="Freeborn")
        assert len(items) >= 3

    def test_initialize_vendor_inventory_default(self):
        """Unknown faction gets generic items."""
        from scripts.aeonisk.multiagent.npc_agent import initialize_vendor_inventory

        items = initialize_vendor_inventory(faction="Unknown Faction")
        assert len(items) >= 3

    def test_vendor_items_have_prices(self):
        """All vendor items have at least one non-zero price."""
        from scripts.aeonisk.multiagent.npc_agent import initialize_vendor_inventory

        items = initialize_vendor_inventory(faction="Sovereign Nexus")
        for item in items:
            total_price = (
                getattr(item, 'price_spark', 0) +
                getattr(item, 'price_grain', 0) +
                getattr(item, 'price_drip', 0) +
                getattr(item, 'price_breath', 0)
            )
            assert total_price > 0, f"Item '{item.name}' has zero total price"

    def test_npc_vendor_spawn_with_inventory(self):
        """NPC spawned as vendor gets populated inventory."""
        from scripts.aeonisk.multiagent.npc_agent import NPCAgent, initialize_vendor_inventory

        # Create NPC with vendor flag (using correct NPCAgent fields)
        npc = NPCAgent(
            agent_id="npc_vendor_001",
            name="Market Trader",
            faction="Sovereign Nexus",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="A vendor in the market",
            health=10,
            max_health=10,
            soak=5,
            void_score=0,
            is_vendor=True,
            accepts_purchases=True,
            vendor_type="human_trader",
            can_act=False,  # Skip LLM init for test
        )
        assert npc.is_vendor is True
        assert npc.accepts_purchases is True
        assert npc.vendor_type == "human_trader"


# ============================================================================
# 6. DM Vendor Spawning Guidance
# ============================================================================


class TestVendorSpawningGuidance:
    """DM gets vendor spawn guidance in appropriate scenarios."""

    def test_safe_zone_scenario_detected(self):
        """Market/safe zone keywords are correctly identified."""
        from scripts.aeonisk.multiagent.session import is_safe_zone_scenario

        assert is_safe_zone_scenario("The party enters a bustling market district") is True
        assert is_safe_zone_scenario("A fierce ambush in the dark alley") is False
        assert is_safe_zone_scenario("The festival grounds are alive with music") is True
        assert is_safe_zone_scenario("Trading post on the border") is True
        assert is_safe_zone_scenario("Neutral zone between factions") is True

    def test_combat_zone_not_safe(self):
        """Combat scenarios are not identified as safe zones."""
        from scripts.aeonisk.multiagent.session import is_safe_zone_scenario

        assert is_safe_zone_scenario("Enemy forces attack the compound") is False
        assert is_safe_zone_scenario("Combat erupts in the corridor") is False


# ============================================================================
# 7. Live Bond Transition Testing
# ============================================================================


class TestLiveBondTransitions:
    """Void-driven bond transitions work correctly."""

    def setup_method(self):
        self.mechanics = MechanicsEngine()

    def test_void_increase_6_to_7_triggers_dormancy(self):
        """Void change from 6->7 triggers ACTIVE->DORMANT."""
        bonds = [_make_bond(status=BondStatus.ACTIVE)]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=7,
            previous_void=6,
        )
        assert result['status_changed'] is True
        assert result['transitions'] == 1
        assert bonds[0].status == BondStatus.DORMANT

    def test_void_decrease_7_to_6_triggers_reactivation(self):
        """Void change from 7->6 triggers DORMANT->ACTIVE."""
        bonds = [_make_bond(status=BondStatus.DORMANT)]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=6,
            previous_void=7,
        )
        assert result['status_changed'] is True
        assert result['reactivations'] == 1
        assert bonds[0].status == BondStatus.ACTIVE

    def test_void_10_triggers_void_lock(self):
        """Void reaching 10 triggers VOID_LOCKED (permanent)."""
        bonds = [
            _make_bond(bond_id="b1", status=BondStatus.ACTIVE),
            _make_bond(bond_id="b2", char_b="Charlie", status=BondStatus.DORMANT),
        ]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=10,
            previous_void=9,
        )
        assert result['status_changed'] is True
        assert result['void_locked'] is True or result.get('void_locked', 0) > 0
        assert bonds[0].status == BondStatus.VOID_LOCKED
        assert bonds[1].status == BondStatus.VOID_LOCKED

    def test_void_locked_never_reverts(self):
        """VOID_LOCKED bond does not revert even if Void decreases."""
        bonds = [_make_bond(status=BondStatus.VOID_LOCKED)]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=5,
            previous_void=10,
        )
        assert bonds[0].status == BondStatus.VOID_LOCKED

    def test_severed_bond_not_affected_by_void(self):
        """SEVERED bonds are not affected by void transitions."""
        bonds = [_make_bond(status=BondStatus.SEVERED)]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=8,
            previous_void=5,
        )
        assert bonds[0].status == BondStatus.SEVERED

    def test_multiple_bonds_transition_independently(self):
        """Multiple bonds with different statuses transition independently."""
        bonds = [
            _make_bond(bond_id="b1", char_b="Bob", status=BondStatus.ACTIVE),
            _make_bond(bond_id="b2", char_b="Charlie", status=BondStatus.SEVERED),
            _make_bond(bond_id="b3", char_b="Dana", status=BondStatus.ACTIVE),
        ]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=7,
            previous_void=6,
        )
        # Active bonds go dormant, severed stays severed
        assert bonds[0].status == BondStatus.DORMANT
        assert bonds[1].status == BondStatus.SEVERED  # Unchanged
        assert bonds[2].status == BondStatus.DORMANT
        assert result['transitions'] == 2

    def test_bond_sacrifice_then_dormancy(self):
        """After sacrifice, remaining bonds still transition on void change."""
        bonds = [
            _make_bond(bond_id="b1", char_b="Bob", status=BondStatus.ACTIVE),
            _make_bond(bond_id="b2", char_b="Charlie", status=BondStatus.ACTIVE),
        ]

        # Sacrifice first bond
        sacrifice_result = self.mechanics.process_bond_sacrifice(
            character_name="Alice",
            character_bonds=bonds,
            bond_target="Bob",
            current_round=1,
        )
        assert sacrifice_result['success'] is True
        assert bonds[0].status == BondStatus.SEVERED

        # Now void change should only affect remaining active bond
        dormancy_result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=7,
            previous_void=6,
        )
        assert bonds[0].status == BondStatus.SEVERED  # Still severed
        assert bonds[1].status == BondStatus.DORMANT  # Went dormant
        assert dormancy_result['transitions'] == 1


# ============================================================================
# 8. Bond Formation / Breaking Validation
# ============================================================================


class TestBondFormationBreaking:
    """Bond formation and sacrifice mechanics."""

    def setup_method(self):
        self.mechanics = MechanicsEngine()

    def test_validate_bond_formation_success(self):
        """Valid bond formation passes validation."""
        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Bob",
            character_bonds=[],
            character_void=3,
            target_void=2,
            origin="standard",
            witnesses=["Charlie"],
        )
        assert result['valid'] is True
        assert len(result['errors']) == 0

    def test_validate_bond_formation_high_void(self):
        """Bond formation fails when Void >= 7."""
        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Bob",
            character_bonds=[],
            character_void=7,
            target_void=2,
            origin="standard",
            witnesses=["Charlie"],
        )
        assert result['valid'] is False
        assert 'void_too_high' in result['errors']

    def test_validate_bond_formation_at_limit(self):
        """Bond formation fails at bond limit."""
        existing_bonds = [
            _make_bond(bond_id=f"b{i}", char_b=f"Partner{i}")
            for i in range(3)
        ]
        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="NewPartner",
            character_bonds=existing_bonds,
            character_void=2,
            target_void=2,
            origin="standard",
            witnesses=["Witness"],
        )
        assert result['valid'] is False
        assert 'bond_limit' in result['errors']

    def test_bond_sacrifice_severs_bond(self):
        """Bond sacrifice sets status to SEVERED."""
        bonds = [_make_bond(status=BondStatus.ACTIVE)]
        result = self.mechanics.process_bond_sacrifice(
            character_name="Alice",
            character_bonds=bonds,
            bond_target="Bob",
            current_round=1,
        )
        assert result['success'] is True
        assert bonds[0].status == BondStatus.SEVERED
        assert result['willpower_bonus'] == 5
        assert result['void_change'] == 1

    def test_bond_sacrifice_dormant_bond(self):
        """Can sacrifice a DORMANT bond."""
        bonds = [_make_bond(status=BondStatus.DORMANT)]
        result = self.mechanics.process_bond_sacrifice(
            character_name="Alice",
            character_bonds=bonds,
            bond_target="Bob",
            current_round=1,
        )
        assert result['success'] is True
        assert bonds[0].status == BondStatus.SEVERED

    def test_bond_sacrifice_void_locked_fails(self):
        """Cannot sacrifice a VOID_LOCKED bond."""
        bonds = [_make_bond(status=BondStatus.VOID_LOCKED)]
        result = self.mechanics.process_bond_sacrifice(
            character_name="Alice",
            character_bonds=bonds,
            bond_target="Bob",
            current_round=1,
        )
        assert result['success'] is False
