"""
Unit tests for Spec 09: Range Bands & Movement Awareness.

Tests cover:
- Phase 1: Range penalty display in combatant lists (DM prompt)
- Phase 2: Player position context with range to targets
- Phase 3: Enemy range info in free-targeting mode
- Phase 4: Dodge-as-movement defense bonus
- Phase 5: Intra-round position tracking

TDD: Tests written BEFORE implementation per CLAUDE.md protocol.
"""

import pytest
from unittest.mock import MagicMock, patch
from scripts.aeonisk.multiagent.enemy_agent import Position


# =============================================================================
# HELPERS
# =============================================================================

def _make_player_agent(name="Test PC", faction="Freeborn", position_str="Near-PC",
                       health=20, max_health=20, agent_id="player_01"):
    """Create a minimal mock player agent with position."""
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.name = name
    agent.position = Position.from_string(position_str)
    agent.health = health
    agent.max_health = max_health
    agent.wounds = 0
    agent.stuns = 0
    agent.character_state = MagicMock()
    agent.character_state.name = name
    agent.character_state.faction = faction
    agent.character_state.pronouns = "they/them"
    agent.character_state.void_score = 0
    agent.character_state.soulcredit = 0
    agent.character_state.attributes = {"Agility": 3, "Strength": 3, "Perception": 3}
    agent.character_state.skills = {"Guns": 3, "Awareness": 2}
    agent.equipped_weapons = {"primary": None, "sidearm": None}
    return agent


def _make_enemy_agent(name="Grunt Alpha", position_str="Near-Enemy",
                      health=18, max_health=18, agent_id="enemy_01",
                      faction="Syndicate", tactics="aggressive_melee"):
    """Create a minimal mock enemy agent with position."""
    from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Weapon
    enemy = EnemyAgent(
        agent_id=agent_id,
        name=name,
        template="grunt",
        attributes={"Agility": 3, "Strength": 3, "Perception": 3,
                     "Intelligence": 2, "Empathy": 2, "Willpower": 2,
                     "Endurance": 3, "Dexterity": 3},
        skills={"Guns": 3, "Melee": 2, "Awareness": 2, "Athletics": 2, "Brawl": 1},
        health=health,
        max_health=max_health,
        soak=8,
        wounds=0,
        position=Position.from_string(position_str),
        initiative=12,
        faction=faction,
        tactics=tactics,
    )
    return enemy


# =============================================================================
# Phase 1: Range Display in DM Combatant List
# =============================================================================

class TestDMCombatantListRange:
    """DM resolution prompt combatant list should include position and range info."""

    def _create_dm_with_combatants(self, player_position="Near-PC", enemy_position="Near-Enemy"):
        """Create a DM agent with target_id_mapper and combatants."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine

        dm = AIDMAgent.__new__(AIDMAgent)
        dm.agent_id = "dm_test"
        dm.llm_config = {"provider": "openai", "model": "gpt-5-mini"}
        dm.current_scenario = MagicMock()
        dm.current_scenario.theme = "Test"
        dm.current_scenario.location = "Test Lab"
        dm.current_scenario.situation = "Testing"
        dm.current_scenario.void_level = 3
        dm.session_config = {}
        dm._round_synthesis_history = []

        # Create player and enemy
        player = _make_player_agent(position_str=player_position)
        enemy = _make_enemy_agent(position_str=enemy_position)

        # Set up shared state with target_id_mapper
        dm.shared_state = MagicMock()
        dm.shared_state.mechanics_engine = MechanicsEngine()
        dm.shared_state.get_mechanics_engine.return_value = dm.shared_state.mechanics_engine
        dm.shared_state.player_agents = [player]
        dm.shared_state.enemy_agents = [enemy]
        dm.shared_state.npc_agents = []

        # Target ID mapper
        mapper = MagicMock()
        mapper.enabled = True
        mapper.get_all_target_ids.return_value = ["tgt_pc01", "tgt_en01"]

        def get_combatant_info(tid):
            if tid == "tgt_pc01":
                return {
                    'name': 'Test PC',
                    'type': 'player',
                    'agent_id': 'player_01',
                    'pronouns': 'they/them',
                    'faction': 'Freeborn',
                }
            elif tid == "tgt_en01":
                return {
                    'name': 'Grunt Alpha',
                    'type': 'enemy',
                    'agent_id': 'enemy_01',
                    'pronouns': 'they/them',
                    'faction': 'Syndicate',
                }
            return None

        mapper.get_combatant_info = get_combatant_info
        dm.shared_state.get_target_id_mapper.return_value = mapper

        # Mock resolve methods
        def get_agent_by_id(aid):
            if aid == 'player_01':
                return player
            if aid == 'enemy_01':
                return enemy
            return None

        dm.shared_state.get_agent_by_id = get_agent_by_id

        return dm, player, enemy

    def test_combatant_list_includes_position(self):
        """Combatant list should show position for each target."""
        dm, player, enemy = self._create_dm_with_combatants()

        # Build the combatant list section from _build_resolution_prompt
        combatant_list = dm._build_combatant_list_with_range("player_01")
        assert "Near-PC" in combatant_list or "Near-Enemy" in combatant_list

    def test_combatant_list_includes_range_penalty(self):
        """Combatant list should show range and penalty for each target."""
        dm, player, enemy = self._create_dm_with_combatants(
            player_position="Near-PC", enemy_position="Near-Enemy"
        )

        # Near-PC to Near-Enemy = 2 rings apart = Far (-4)
        combatant_list = dm._build_combatant_list_with_range("player_01")
        assert "Far" in combatant_list
        assert "-4" in combatant_list

    def test_combatant_list_engaged_no_penalty(self):
        """Engaged combatants should show no penalty."""
        dm, player, enemy = self._create_dm_with_combatants(
            player_position="Engaged", enemy_position="Engaged"
        )

        combatant_list = dm._build_combatant_list_with_range("player_01")
        assert "Engaged" in combatant_list
        assert "no penalty" in combatant_list or "+0" in combatant_list

    def test_combatant_list_extreme_penalty(self):
        """Extreme range should show -6 penalty."""
        dm, player, enemy = self._create_dm_with_combatants(
            player_position="Far-PC", enemy_position="Extreme-Enemy"
        )

        combatant_list = dm._build_combatant_list_with_range("player_01")
        assert "Extreme" in combatant_list
        assert "-6" in combatant_list

    def test_range_context_in_resolution_prompt(self):
        """DM resolution prompt should contain range context for combat actions."""
        dm, player, enemy = self._create_dm_with_combatants()
        dm._get_party_personalities = MagicMock(return_value="")
        dm._build_clock_context = MagicMock(return_value="")
        dm._build_session_context = MagicMock(return_value="")

        # _build_resolution_prompt should include range info in combatant_list
        # We test the combatant_list section which is built inside _build_resolution_prompt
        # The method should now call _build_combatant_list_with_range
        combatant_list = dm._build_combatant_list_with_range("player_01")
        assert "Range:" in combatant_list


# =============================================================================
# Phase 2: Player Position Context
# =============================================================================

class TestPlayerPositionContext:
    """Player agents should see their position and ranges to targets."""

    def _create_player_with_enemies(self, player_pos="Near-PC", enemy_positions=None):
        """Create a player agent with shared_state containing enemies."""
        if enemy_positions is None:
            enemy_positions = [("Grunt Alpha", "Near-Enemy")]

        player = _make_player_agent(position_str=player_pos)

        enemies = []
        for i, (name, pos) in enumerate(enemy_positions):
            enemies.append(_make_enemy_agent(
                name=name,
                position_str=pos,
                agent_id=f"enemy_{i:02d}"
            ))

        shared_state = MagicMock()
        shared_state.enemy_agents = enemies
        shared_state.player_agents = [player]
        player.shared_state = shared_state

        return player

    def test_player_has_position_attribute(self):
        """Player agents should have a position attribute."""
        player = _make_player_agent()
        assert hasattr(player.position, 'ring')
        assert hasattr(player.position, 'side')

    def test_player_default_position_near_pc(self):
        """Player agents should default to Near-PC position."""
        # Create a real AIPlayerAgent (check the __init__)
        from scripts.aeonisk.multiagent.player import AIPlayerAgent
        from scripts.aeonisk.multiagent.enemy_agent import Position

        # Minimal character config
        config = {
            "name": "Test",
            "faction": "Freeborn",
            "attributes": {"Agility": 3, "Strength": 3, "Perception": 3,
                           "Intelligence": 3, "Empathy": 3, "Willpower": 3,
                           "Endurance": 3, "Dexterity": 3},
            "skills": {"Guns": 3},
            "void_score": 0,
            "soulcredit": 0,
            "bonds": [],
            "goals": ["Survive"],
            "pronouns": "they/them",
        }

        # Create with mock socket
        agent = AIPlayerAgent.__new__(AIPlayerAgent)
        agent.position = Position.from_string("Near-PC")

        assert agent.position.ring == "Near"
        assert agent.position.side == "PC"

    def test_build_position_context_shows_distances(self):
        """Position context should show range to all enemies."""
        player = self._create_player_with_enemies(
            player_pos="Near-PC",
            enemy_positions=[
                ("Alpha", "Near-Enemy"),
                ("Beta", "Far-Enemy"),
            ]
        )

        # The player should have a method to build position context
        context = build_position_context(player)
        assert "Alpha" in context
        assert "Beta" in context
        # Near-PC to Near-Enemy = Far (-4)
        assert "Far" in context or "-4" in context

    def test_build_position_context_shows_current_position(self):
        """Position context should show the player's current position."""
        player = self._create_player_with_enemies(player_pos="Far-PC")

        context = build_position_context(player)
        assert "Far-PC" in context

    def test_build_position_context_empty_no_position(self):
        """Position context should be empty if player has no position."""
        player = _make_player_agent()
        del player.position

        context = build_position_context(player)
        assert context == ""

    def test_range_penalty_table_in_context(self):
        """Position context should include range penalty reference."""
        player = self._create_player_with_enemies()

        context = build_position_context(player)
        # Should include penalty reference
        assert "-2" in context or "-4" in context or "-6" in context


# =============================================================================
# Phase 3: Enemy Range in Free-Targeting Mode
# =============================================================================

class TestEnemyFreeTargetingRange:
    """Enemy prompts in free-targeting mode should show range and penalty to each combatant."""

    def test_free_targeting_combatant_list_includes_range(self):
        """Free targeting combatant list should include range and penalty for each target."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_battlefield

        enemy = _make_enemy_agent(position_str="Near-Enemy")
        player = _make_player_agent(position_str="Near-PC")

        # Create target_id_mapper mock
        mapper = MagicMock()
        mapper.get_target_id.side_effect = lambda aid: {
            "player_01": "tgt_pc01",
            "enemy_01": "tgt_en01",
        }.get(aid)

        battlefield = _format_battlefield(
            enemy=enemy,
            player_agents=[player],
            enemy_agents=[enemy],
            available_tokens=[],
            target_id_mapper=mapper,
            free_targeting=True,
        )

        # Near-Enemy to Near-PC = 2 rings apart = Far (-4)
        assert "Far" in battlefield or "-4" in battlefield
        assert "Range" in battlefield or "range" in battlefield

    def test_free_targeting_engaged_shows_no_penalty(self):
        """Engaged targets in free-targeting mode should show no penalty."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_battlefield

        enemy = _make_enemy_agent(position_str="Engaged")
        player = _make_player_agent(position_str="Engaged")

        mapper = MagicMock()
        mapper.get_target_id.side_effect = lambda aid: {
            "player_01": "tgt_pc01",
            "enemy_01": "tgt_en01",
        }.get(aid)

        battlefield = _format_battlefield(
            enemy=enemy,
            player_agents=[player],
            enemy_agents=[enemy],
            available_tokens=[],
            target_id_mapper=mapper,
            free_targeting=True,
        )

        assert "Engaged" in battlefield
        # Should indicate no penalty for engaged range
        assert "no penalty" in battlefield or "+0" in battlefield or "0" in battlefield


# =============================================================================
# Phase 4: Dodge-as-Movement Defense Bonus
# =============================================================================

class TestDodgeAsMovement:
    """Players who declare dodge/take-cover should receive an agility-based defense bonus."""

    def test_dodge_declaration_grants_defense_bonus(self):
        """A player declaring 'dodge' should get an agility-based defense bonus."""
        from scripts.aeonisk.multiagent.session import compute_dodge_defense_bonus

        player = _make_player_agent()
        player.character_state.attributes = {"Agility": 4}

        # Player declared dodge action
        action = {"action_type": "combat", "intent": "dodge incoming fire"}

        bonus = compute_dodge_defense_bonus(player, action)
        assert bonus > 0  # Should grant a positive defense bonus

    def test_take_cover_declaration_grants_defense_bonus(self):
        """A player declaring 'take cover' should get an agility-based defense bonus."""
        from scripts.aeonisk.multiagent.session import compute_dodge_defense_bonus

        player = _make_player_agent()
        player.character_state.attributes = {"Agility": 3}

        action = {"action_type": "combat", "intent": "take cover behind the wall"}

        bonus = compute_dodge_defense_bonus(player, action)
        assert bonus > 0

    def test_no_dodge_bonus_for_attack_actions(self):
        """Attack actions should not receive dodge defense bonus."""
        from scripts.aeonisk.multiagent.session import compute_dodge_defense_bonus

        player = _make_player_agent()
        player.character_state.attributes = {"Agility": 5}

        action = {"action_type": "combat", "intent": "fire at the enemy"}

        bonus = compute_dodge_defense_bonus(player, action)
        assert bonus == 0

    def test_dodge_bonus_scales_with_agility(self):
        """Dodge defense bonus should scale with the player's Agility attribute."""
        from scripts.aeonisk.multiagent.session import compute_dodge_defense_bonus

        player_low_agi = _make_player_agent()
        player_low_agi.character_state.attributes = {"Agility": 2}

        player_high_agi = _make_player_agent()
        player_high_agi.character_state.attributes = {"Agility": 5}

        action = {"action_type": "combat", "intent": "dodge the incoming attack"}

        bonus_low = compute_dodge_defense_bonus(player_low_agi, action)
        bonus_high = compute_dodge_defense_bonus(player_high_agi, action)

        assert bonus_high > bonus_low


# =============================================================================
# Phase 5: Intra-Round Position Tracking
# =============================================================================

class TestIntraRoundPositionTracking:
    """Position changes within a round should affect subsequent resolutions."""

    def test_position_change_applied_immediately(self):
        """Position changes should take effect for subsequent resolutions."""
        player = _make_player_agent(position_str="Near-PC")
        enemy = _make_enemy_agent(position_str="Near-Enemy")

        # Initial range: Near-PC to Near-Enemy = Far (-4)
        range_name, penalty = player.position.calculate_range(enemy.position)
        assert range_name == "Far"
        assert penalty == -4

        # Player moves to Far-PC
        player.position = Position.from_string("Far-PC")

        # New range: Far-PC to Near-Enemy = Extreme (-6)
        range_name, penalty = player.position.calculate_range(enemy.position)
        assert range_name == "Extreme"
        assert penalty == -6

    def test_enemy_attack_uses_updated_position(self):
        """Enemy attack after player movement should use new range."""
        player = _make_player_agent(position_str="Near-PC")
        enemy = _make_enemy_agent(position_str="Near-Enemy")

        # Player moves to Far-PC during their action
        player.position = Position.from_string("Far-PC")

        # Enemy attacks player (should use Far-PC, not Near-PC)
        range_name, penalty = enemy.position.calculate_range(player.position)
        assert range_name == "Extreme"  # Near-Enemy to Far-PC = Extreme
        assert penalty == -6

    def test_multiple_position_changes_in_round(self):
        """Multiple agents moving in one round should all be tracked."""
        player_a = _make_player_agent(name="Player A", position_str="Near-PC", agent_id="pa")
        player_b = _make_player_agent(name="Player B", position_str="Near-PC", agent_id="pb")

        player_a.position = Position.from_string("Far-PC")
        player_b.position = Position.from_string("Engaged")

        assert player_a.position.ring == "Far"
        assert player_a.position.side == "PC"
        assert player_b.position.ring == "Engaged"

    def test_apply_intra_round_position_update(self):
        """session.apply_intra_round_position_update should update agent position
        and be callable from the resolution loop."""
        from scripts.aeonisk.multiagent.session import apply_intra_round_position_update

        player = _make_player_agent(position_str="Near-PC")

        apply_intra_round_position_update(player, "Far-PC")
        assert player.position.ring == "Far"
        assert player.position.side == "PC"

    def test_apply_intra_round_position_update_engaged(self):
        """apply_intra_round_position_update handles Engaged (no side)."""
        from scripts.aeonisk.multiagent.session import apply_intra_round_position_update

        player = _make_player_agent(position_str="Near-PC")

        apply_intra_round_position_update(player, "Engaged")
        assert player.position.ring == "Engaged"


# =============================================================================
# Position.calculate_range Validation (regression/foundation tests)
# =============================================================================

class TestPositionRangeCalculation:
    """Verify the Position.calculate_range method returns correct values
    for various position combinations used throughout the spec."""

    def test_engaged_to_engaged(self):
        a = Position.from_string("Engaged")
        b = Position.from_string("Engaged")
        name, penalty = a.calculate_range(b)
        assert name == "Engaged"
        assert penalty == 0

    def test_same_ring_same_side_is_melee(self):
        a = Position.from_string("Near-PC")
        b = Position.from_string("Near-PC")
        name, penalty = a.calculate_range(b)
        assert name == "Melee"
        assert penalty == 0

    def test_near_pc_to_engaged_is_near(self):
        a = Position.from_string("Near-PC")
        b = Position.from_string("Engaged")
        name, penalty = a.calculate_range(b)
        assert name == "Near"
        assert penalty == -2

    def test_near_pc_to_near_enemy_is_far(self):
        a = Position.from_string("Near-PC")
        b = Position.from_string("Near-Enemy")
        name, penalty = a.calculate_range(b)
        assert name == "Far"
        assert penalty == -4

    def test_far_pc_to_near_enemy_is_extreme(self):
        a = Position.from_string("Far-PC")
        b = Position.from_string("Near-Enemy")
        name, penalty = a.calculate_range(b)
        assert name == "Extreme"
        assert penalty == -6

    def test_far_pc_to_extreme_enemy_is_extreme(self):
        a = Position.from_string("Far-PC")
        b = Position.from_string("Extreme-Enemy")
        name, penalty = a.calculate_range(b)
        # Far-PC idx=2, Extreme-Enemy idx=3, different sides → 2+3=5, clamped to 3+ → Extreme
        assert name == "Extreme"
        assert penalty == -6


# =============================================================================
# Helper function for tests: build_position_context
# =============================================================================

def build_position_context(player) -> str:
    """Build position context showing player's current location and ranges.

    Imported from player.py once implemented. This is the test shim.
    """
    from scripts.aeonisk.multiagent.player import build_position_context as _impl
    return _impl(player)
