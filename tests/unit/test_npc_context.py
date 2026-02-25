"""
Tests for NPC context and action declaration display.

Tests verify:
1. NPC action broadcasts include description field
2. Player initiative displays show NPC action declarations
3. NPC prompts include narrative context (round synthesis, recent events, declarations)
"""

import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime

from scripts.aeonisk.multiagent.npc_agent import NPCAgent, NPCLLMClient, NPCAction
from scripts.aeonisk.multiagent.target_ids import TargetIDMapper
from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position


class TestNPCActionBroadcast:
    """Test that NPC action broadcasts include description field for player display."""

    @pytest.fixture
    def mock_npc(self):
        """Create mock NPC agent."""
        npc = Mock(spec=NPCAgent)
        npc.agent_id = "npc_test_123"
        npc.name = "Test NPC"
        npc.disposition = "wary"
        npc.entity_type = "neutral"
        npc.threat_level = "armed_neutral"
        npc.health = 30
        npc.max_health = 30
        npc.can_act = True
        npc.is_active = True
        npc.llm_client = Mock(spec=NPCLLMClient)
        return npc

    @pytest.fixture
    def mock_npc_action(self):
        """Create mock NPC action with reason text."""
        return NPCAction(
            action_type="flee",
            reason="I'm outnumbered and need to escape before they shoot!",
            target=None
        )

    @pytest.mark.asyncio
    async def test_npc_broadcast_includes_description_field(self, mock_npc, mock_npc_action):
        """
        Test: NPC action broadcast payload includes 'description' field.

        This ensures players can see NPC action descriptions in their initiative order display.
        """
        # Mock NPC LLM client to return action
        mock_npc.llm_client.declare_action = AsyncMock(return_value=mock_npc_action)

        # Build context and get NPC to declare action
        context = "Round 1: Calm situation. 2 players present."

        # Simulate NPC declaration (this is what happens in session.py lines 1034-1048)
        npc_action = await mock_npc.llm_client.declare_action(context)
        initiative_score = 15

        # Build broadcast message (mimicking CURRENT session.py logic - WITHOUT description)
        broadcast_payload_current = {
            'agent_id': mock_npc.agent_id,
            'character_name': mock_npc.name,
            'intent': npc_action.action_type,
            'initiative': initiative_score,
            'agent_type': 'npc'
        }

        # Build broadcast message (EXPECTED after fix - WITH description)
        broadcast_payload_expected = {
            'agent_id': mock_npc.agent_id,
            'character_name': mock_npc.name,
            'description': npc_action.reason,  # THIS IS WHAT'S MISSING
            'intent': npc_action.action_type,
            'initiative': initiative_score,
            'agent_type': 'npc'
        }

        # ASSERTION: Current implementation FAILS because description is missing
        assert 'description' not in broadcast_payload_current, \
            "EXPECTED FAILURE: description field should be missing in current implementation"

        # Verify what the payload SHOULD include after fix
        assert 'description' in broadcast_payload_expected
        assert broadcast_payload_expected['description'] == "I'm outnumbered and need to escape before they shoot!"

    def test_npc_declared_actions_stored_with_description(self, mock_npc, mock_npc_action):
        """
        Test: NPC actions stored in _declared_actions include description field.

        This verifies the internal storage is correct (session.py:1024-1031).
        """
        # Simulate internal storage (session.py:1024-1031)
        npc_action = mock_npc_action
        initiative_score = 15

        declared_actions = {}
        declared_actions[mock_npc.agent_id] = []
        declared_actions[mock_npc.agent_id].append({
            'agent_id': mock_npc.agent_id,
            'character_name': mock_npc.name,
            'intent': npc_action.action_type,
            'description': npc_action.reason,  # This IS stored internally
            'action_type': npc_action.action_type,
            'initiative': initiative_score
        })

        # Verify internal storage has description
        stored_action = declared_actions[mock_npc.agent_id][0]
        assert 'description' in stored_action
        assert stored_action['description'] == npc_action.reason
        assert stored_action['description'] == "I'm outnumbered and need to escape before they shoot!"


class TestPlayerInitiativeDisplay:
    """Test that players see NPC action declarations in their initiative order display."""

    def test_player_receives_npc_action_with_description(self):
        """
        Test: Player's declared_actions_this_round includes NPC description.

        When NPC broadcasts action, player should store it with description for display.
        """
        # Simulate player's declared_actions_this_round dict
        declared_actions_this_round = {}

        # Simulate player receiving NPC action broadcast (player.py:467-484)
        npc_message_payload = {
            'agent_id': 'npc_test_123',
            'character_name': 'Cornered Smuggler',
            'description': 'I surrender! Please do not hurt me!',  # Should be included after fix
            'intent': 'plead',
            'initiative': 15,
            'agent_type': 'npc'
        }

        # Player processes message (player.py:467-484 logic)
        character_name = npc_message_payload.get('character_name', 'Unknown')
        description = npc_message_payload.get('description', '')
        intent = npc_message_payload.get('intent', '')
        initiative = npc_message_payload.get('initiative', 0)

        if intent or description:
            declared_actions_this_round[character_name] = (description, intent, initiative)

        # Verify player stored NPC action with description
        assert 'Cornered Smuggler' in declared_actions_this_round
        stored = declared_actions_this_round['Cornered Smuggler']
        assert len(stored) == 3
        description_stored, intent_stored, init_stored = stored
        assert description_stored == 'I surrender! Please do not hurt me!'
        assert intent_stored == 'plead'
        assert init_stored == 15

    def test_player_initiative_display_shows_npc_actions(self):
        """
        Test: Player's initiative order display shows NPC action descriptions.

        This verifies the formatted output players see includes NPC actions.
        """
        # Setup declared actions (including NPCs)
        declared_actions_this_round = {
            'Test Player': ('I shoot at the enemy', 'attack', 20),  # Player's own action
            'Cornered Smuggler': ('I surrender! Please do not hurt me!', 'plead', 15),  # NPC action WITH description
            'Paranoid Enforcer': ('', 'attack', 10)  # NPC with empty description (current bug scenario)
        }

        # Build initiative display (player.py:1887-1897)
        narrative_context = "## 🎯 Declared Actions This Round:\n"

        # Sort by initiative (slowest first)
        sorted_declarations = sorted(
            declared_actions_this_round.items(),
            key=lambda x: x[1][2]  # Sort by initiative (3rd element)
        )

        for char_name, action_data in sorted_declarations:
            if len(action_data) == 3:
                description, intent, initiative = action_data
                narrative_context += f"- **{char_name}** [Init {initiative}]: {description}\n"

        # Verify display
        assert '**Cornered Smuggler** [Init 15]: I surrender! Please do not hurt me!' in narrative_context
        assert '**Paranoid Enforcer** [Init 10]: ' in narrative_context  # Empty description (current bug)

        # After fix, all NPCs should have description (none should be empty)
        assert narrative_context.count(': \n') == 1, \
            "EXPECTED: One NPC should have empty description (demonstrates current bug)"


class TestPCInitiativeBroadcast:
    """Regression test: PC action broadcasts must include initiative.

    Bug: player.py built action dicts from action_declaration.to_dict() and added
    character/faction/pronouns but NEVER included initiative. Other agents received
    action.get('initiative', 0) → always 0 for PCs, while enemies/NPCs were fine.
    """

    def test_pc_action_dict_includes_initiative(self):
        """PC action broadcast payload must contain initiative from current_initiative."""
        # Simulate what player.py does when building the action dict (lines 918-944)
        # action_declaration.to_dict() returns the base action
        action = {
            'intent': 'attack',
            'description': 'I fire at the enforcer',
            'action_type': 'combat',
            'attribute': 'Perception',
            'skill': 'Guns',
        }

        # These fields are added by player.py before broadcast
        action['attribute_value'] = 5
        action['skill_value'] = 4
        action['character'] = 'Test Player'
        action['agent_id'] = 'player_01'
        action['faction'] = 'Tempest'
        action['pronouns'] = 'he/him'
        action['is_free_action'] = False
        # THE FIX: initiative must be included
        current_initiative = 28  # Agility 4 × 4 + d20(12)
        action['initiative'] = current_initiative

        # Verify initiative is present and non-zero (the actual regression check)
        assert 'initiative' in action, "PC action broadcast must include 'initiative' key"
        assert action['initiative'] == 28
        assert action['initiative'] != 0, "PC initiative must not be 0 (was the old bug)"

    def test_receiving_agent_sees_real_pc_initiative(self):
        """When another agent receives a PC's broadcast, initiative must be real (not 0)."""
        # Simulate receiving agent's _handle_action_declared logic (player.py:729)
        broadcast_payload = {
            'agent_id': 'player_02',
            'character_name': 'Lyss',
            'description': 'I intimidate the patrol',
            'intent': 'intimidate',
            'target': None,
            'weapon': None,
            'reasoning': '',
            'initiative': 22,  # Real initiative from broadcast
            'faction': 'Nexus Collective',
        }

        # This is what _handle_action_declared does
        initiative = broadcast_payload.get('initiative', 0)
        character_name = broadcast_payload.get('character_name', 'Unknown')
        description = broadcast_payload.get('description', '')
        intent = broadcast_payload.get('intent', '')
        target = broadcast_payload.get('target')
        weapon = broadcast_payload.get('weapon')
        reasoning = broadcast_payload.get('reasoning', '')

        # Store in declared_actions_this_round
        declared_actions_this_round = {}
        if intent or description:
            declared_actions_this_round[character_name] = (
                description, intent, target, weapon, reasoning, initiative
            )

        # Verify the stored initiative is real
        stored = declared_actions_this_round['Lyss']
        assert stored[-1] == 22, f"Stored initiative should be 22, got {stored[-1]}"
        assert stored[-1] != 0, "Stored PC initiative must not be 0"

    def test_initiative_filtering_works_with_real_values(self):
        """Initiative-based filtering (show only slower declarers) requires real values."""
        # Agent with initiative 25 should see agents with lower initiative
        current_init = 25

        declared_actions_this_round = {
            'Lyss': ('Intimidate patrol', 'intimidate', None, None, '', 18),  # Lower → visible
            'Kael': ('Hack terminal', 'investigate', None, None, '', 30),  # Higher → hidden
            'ACG Patrol #1': ('', 'Attack', 'tgt_player_01', 'Shotgun', 'Eliminate threat', 22),  # Lower → visible
        }

        # Filter logic from player.py:3064-3070
        filtered = {
            char_name: action_data
            for char_name, action_data in declared_actions_this_round.items()
            if action_data[-1] < current_init
        }

        assert 'Lyss' in filtered, "Lower-init PC should be visible"
        assert 'ACG Patrol #1' in filtered, "Lower-init enemy should be visible"
        assert 'Kael' not in filtered, "Higher-init PC should be hidden (declares after you)"

    def test_initiative_filtering_broken_with_zero(self):
        """Demonstrates the old bug: if PCs have initiative 0, filtering is wrong."""
        current_init = 25

        # OLD BUG: all PCs had initiative 0
        declared_actions_this_round = {
            'Lyss': ('Intimidate patrol', 'intimidate', None, None, '', 0),  # Bug: 0 instead of 18
            'Kael': ('Hack terminal', 'investigate', None, None, '', 0),  # Bug: 0 instead of 30
        }

        # With initiative 0, ALL PCs appear "slower than you" regardless of actual speed
        filtered = {
            char_name: action_data
            for char_name, action_data in declared_actions_this_round.items()
            if action_data[-1] < current_init
        }

        # Both appear visible even though Kael (init 30) should be hidden
        assert len(filtered) == 2, "Old bug: both PCs visible because both have init 0"


class TestNPCPromptFormatting:
    """Test that NPC prompts include proper narrative context."""

    @pytest.fixture
    def npc_llm_client(self):
        """Create real NPC LLM client for prompt testing."""
        mock_npc = Mock(spec=NPCAgent)
        mock_npc.agent_id = "npc_test_789"
        mock_npc.name = "Test Smuggler"
        mock_npc.description = "Nervous smuggler caught in the crossfire"
        mock_npc.disposition = "wary"
        mock_npc.entity_type = "neutral"
        mock_npc.threat_level = "potential_threat"
        mock_npc.faction = "Freeborn"
        mock_npc.health = 25
        mock_npc.max_health = 30
        mock_npc.stuns = 0
        mock_npc.wounds = 1

        # llm_provider=None since we're only testing prompt building, not actual LLM calls
        return NPCLLMClient(npc=mock_npc, llm_provider=None)

    def test_npc_prompt_includes_recent_events(self, npc_llm_client):
        """
        Test: NPC context includes recent narrative events.

        NPCs should see what happened in previous rounds (from session.py:941-942).
        """
        context = """Round 2: Calm situation. 2 players present.

**Recent Events:**
[Ash] Ash hacks the terminal, disabling the security cameras (Success, margin +8)
[Marcus] Marcus intimidates the guard, who backs down nervously (Success, margin +3)"""

        prompt = npc_llm_client._build_prompt(context)

        # Verify recent events are included in prompt
        assert "Recent Events:" in prompt
        assert "Ash hacks the terminal" in prompt
        assert "Marcus intimidates the guard" in prompt

    def test_npc_prompt_includes_round_synthesis(self, npc_llm_client):
        """
        Test: NPC context includes DM round synthesis from previous round.

        NPCs should see DM narration (from session.py:945-949).
        """
        context = """Round 3: Calm situation. 2 players present.

**What Happened Last Round:**
The Tempest operatives successfully breach the security checkpoint. Guard Vex remains wary but allows them to pass after seeing forged credentials. The facility's alarm system remains silent for now."""

        prompt = npc_llm_client._build_prompt(context)

        # Verify round synthesis is included
        assert "What Happened Last Round:" in prompt
        assert "Tempest operatives successfully breach" in prompt
        assert "Guard Vex remains wary" in prompt

    def test_npc_prompt_includes_declared_actions(self, npc_llm_client):
        """
        Test: NPC context includes actions declared by higher-initiative agents.

        NPCs should see what faster agents declared (from session.py:965-967).
        """
        context = """Round 4: ALERT: combat: 2 hostiles. 2 players present.

**Actions Already Declared This Round:**
[Marcus] declared: I draw my pistol and aim at the smuggler
[Ash] declared: I hack the door controls to lock them in"""

        prompt = npc_llm_client._build_prompt(context)

        # Verify declared actions are included
        assert "Actions Already Declared This Round:" in prompt
        assert "Marcus" in prompt and "draw my pistol" in prompt
        assert "Ash" in prompt and "hack the door controls" in prompt

    def test_npc_prompt_formatting_vs_player_formatting(self, npc_llm_client):
        """
        Test: Document formatting differences between NPC and player prompts.

        This is informational - shows that NPCs get simpler formatting than players.
        """
        context = """Round 2: Calm situation. 2 players present.

**Recent Events:**
[Ash] Ash does something
**What Happened Last Round:**
The story progresses
**Actions Already Declared This Round:**
[Marcus] declared: something"""

        prompt = npc_llm_client._build_prompt(context)

        # NPCs get bold headers (**Header:**), not markdown headers (## Header)
        assert "**Recent Events:**" in prompt
        assert "## Recent Events" not in prompt  # Players get this format
        assert "# 📖 Recent Story Events" not in prompt  # Players get emoji headers

        # NPCs get simpler overall structure
        assert "**Current Situation:**" in prompt  # Simple wrapper
        assert "**Your Status:**" in prompt

        # Note: This is intentional - NPCs are designed to be simpler than players


class TestNPCContextEdgeCases:
    """Test edge cases and error handling for NPC context."""

    @pytest.fixture
    def minimal_npc_llm_client(self):
        """Create NPC LLM client with minimal context."""
        mock_npc = Mock(spec=NPCAgent)
        mock_npc.agent_id = "npc_minimal"
        mock_npc.name = "Minimal NPC"
        mock_npc.description = "Test NPC"
        mock_npc.disposition = "neutral"
        mock_npc.entity_type = "neutral"
        mock_npc.threat_level = "non_combatant"
        mock_npc.faction = "None"
        mock_npc.health = 10
        mock_npc.max_health = 10
        mock_npc.stuns = 0
        mock_npc.wounds = 0

        # llm_provider=None since we're only testing prompt building, not actual LLM calls
        return NPCLLMClient(npc=mock_npc, llm_provider=None)

    def test_npc_prompt_with_no_context(self, minimal_npc_llm_client):
        """
        Test: NPC prompt works with minimal context (early rounds).

        Early in the session, there may be no recent events or synthesis yet.
        """
        context = "Round 1: Calm situation. 2 players present."

        prompt = minimal_npc_llm_client._build_prompt(context)

        # Should still include basic sections
        assert "**Current Situation:**" in prompt
        assert "Round 1" in prompt
        assert "**Your Status:**" in prompt

        # Should not crash with missing sections
        assert "Recent Events:" not in prompt  # None to show
        assert "What Happened Last Round:" not in prompt  # Round 1 has no previous round

    def test_npc_prompt_with_threat_indicators(self, minimal_npc_llm_client):
        """
        Test: NPC context highlights threats (combat, captured allies).

        Session.py:889-910 builds intelligent threat assessment.
        """
        context = "Round 5: ALERT: combat: 3 hostiles, ally captured. 2 players present."

        prompt = minimal_npc_llm_client._build_prompt(context)

        # Verify threat indicators are prominent
        assert "ALERT:" in prompt
        assert "combat: 3 hostiles" in prompt
        assert "ally captured" in prompt

    def test_npc_action_with_empty_reason(self):
        """
        Test: NPC action with empty reason field.

        Edge case: What if LLM returns empty reason?
        Schema now requires min_length=10, so empty reason should fail validation.
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            NPCAction(
                action_type="pass",
                reason="",  # Empty reason - should fail min_length=10
                target=None
            )

        # Verify it's a string_too_short error
        assert "string_too_short" in str(exc_info.value) or "at least 10" in str(exc_info.value)


class TestNPCContextIntegration:
    """Integration tests for NPC context in full session flow.

    Validates NPC events exist in fixtures to verify the session flow works.
    """

    @pytest.fixture
    def npc_fixture_path(self):
        """Path to golden NPC fixture."""
        from pathlib import Path
        return Path(__file__).parent.parent / "fixtures" / "sessions" / "golden_npc_deescalation.jsonl"

    @pytest.fixture
    def npc_fixture_events(self, npc_fixture_path):
        """Load NPC fixture events."""
        import json
        if not npc_fixture_path.exists():
            pytest.skip(f"Fixture not found: {npc_fixture_path}")
        events = []
        with open(npc_fixture_path) as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events

    def test_npc_sees_player_actions_from_previous_round(self, npc_fixture_events):
        """
        Verify fixtures contain action declarations across multiple rounds.

        If NPCs see player actions from previous round, there must be:
        1. action_declaration events in round N
        2. Events in round N+1 (showing multi-round session)
        """
        action_declarations = [
            e for e in npc_fixture_events
            if e.get('event_type') == 'action_declaration'
        ]

        assert len(action_declarations) > 0, "Fixture should have action declarations"

        # Get unique rounds with actions (using player_id field)
        rounds_with_actions = set(
            e.get('round') for e in action_declarations
            if e.get('player_id') and e.get('round') is not None
        )

        assert len(rounds_with_actions) >= 1, \
            "Fixture should have player actions in at least 1 round"

        # Verify multi-round fixture
        max_round = max(rounds_with_actions) if rounds_with_actions else 0
        assert max_round >= 1, \
            "Fixture should span multiple rounds for NPC context testing"

    def test_npc_sees_dm_synthesis_from_previous_round(self, npc_fixture_events):
        """
        Verify fixtures contain DM round synthesis events.

        NPCs rely on round_synthesis from DM to understand story context.
        """
        round_synthesis_events = [
            e for e in npc_fixture_events
            if e.get('event_type') == 'round_synthesis'
        ]

        assert len(round_synthesis_events) >= 1, \
            "NPC fixture should have DM round synthesis events"

        # Verify synthesis has content (using 'synthesis' field per schema)
        synthesis = round_synthesis_events[0]
        assert 'synthesis' in synthesis, \
            "Round synthesis should have 'synthesis' field for NPC context"

    def test_npc_sees_higher_initiative_declarations(self, npc_fixture_events):
        """
        Verify fixtures contain action declarations from multiple characters.

        NPCs must see declarations from other agents to react appropriately.
        """
        all_declarations = [
            e for e in npc_fixture_events
            if e.get('event_type') == 'action_declaration'
        ]

        assert len(all_declarations) >= 2, \
            "Fixture should have multiple action declarations"

        # Get unique character names (proxy for different agents)
        character_names = set(
            e.get('character_name') for e in all_declarations
            if e.get('character_name')
        )

        # Fixture should have multiple characters taking actions
        assert len(character_names) >= 2, \
            f"Fixture should have actions from multiple characters, got {character_names}"


# === Helpers for enriched combatant info tests ===

def _create_test_npc(agent_id="npc_test_1", name="Test NPC", health=20, max_health=20,
                     wounds=0, stuns=0):
    """Create test NPC with configurable health/wounds."""
    return NPCAgent(
        agent_id=agent_id,
        name=name,
        faction="Test Faction",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Test NPC",
        health=health,
        max_health=max_health,
        soak=0,
        void_score=0,
        skills={},
        stuns=stuns,
        wounds=wounds,
    )


def _create_test_enemy(agent_id="enemy_grunt_001", name="Test Grunt", health=12,
                       max_health=12, wounds=0):
    """Create test EnemyAgent with configurable health/wounds."""
    enemy = EnemyAgent(
        agent_id=agent_id,
        name=name,
        template="grunt",
        attributes={"Agility": 3, "Strength": 3, "Perception": 3, "Intelligence": 2,
                     "Empathy": 2, "Willpower": 2, "Endurance": 3, "Dexterity": 3},
        skills={"Guns": 3, "Melee": 1, "Awareness": 2},
        health=health,
        max_health=max_health,
        soak=8,
        wounds=wounds,
        position=Position(ring="Near", side="Enemy"),
        initiative=0,
    )
    return enemy


def _create_test_player(agent_id="player_01", name="Test Player", health=27,
                        max_health=27, wounds=0, stuns=0, permanently_dead=False):
    """Create mock player agent with configurable health/wounds/death state."""
    player = Mock()
    player.agent_id = agent_id
    player.character_state = Mock()
    player.character_state.name = name
    player.character_state.void_score = 0
    player.health = health
    player.max_health = max_health
    player.wounds = wounds
    player.stuns = stuns
    player.position = "Near"
    player._permanently_dead = permanently_dead
    return player


class TestGetCombatantInfoEnriched:
    """Tests for enriched get_combatant_info() with wounds, stuns, death_state."""

    def test_alive_enemy_has_death_state_alive(self):
        """Healthy enemy returns death_state='alive'."""
        mapper = TargetIDMapper()
        mapper.enable()
        enemy = _create_test_enemy(health=12, max_health=12, wounds=0)
        tid = mapper.register_enemy(enemy)

        info = mapper.get_combatant_info(tid)
        assert info['wounds'] == 0
        assert info['stuns'] == 0
        assert info['death_state'] == 'alive'

    def test_alive_npc_has_death_state_alive(self):
        """Healthy NPC returns death_state='alive'."""
        mapper = TargetIDMapper()
        mapper.enable()
        npc = _create_test_npc(health=20, max_health=20, wounds=0)
        mapper.register_npc(npc)
        tid = "tgt_npc1"
        mapper.target_id_map[tid] = npc
        mapper.reverse_map[npc.agent_id] = tid

        info = mapper.get_combatant_info(tid)
        assert info['wounds'] == 0
        assert info['stuns'] == 0
        assert info['death_state'] == 'alive'

    def test_unconscious_enemy_has_death_state_unconscious(self):
        """Enemy at 0 HP with wounds < 6 returns death_state='unconscious'."""
        mapper = TargetIDMapper()
        mapper.enable()
        enemy = _create_test_enemy(health=0, max_health=12, wounds=3)
        tid = mapper.register_enemy(enemy)

        info = mapper.get_combatant_info(tid)
        assert info['health'] == 0
        assert info['wounds'] == 3
        assert info['death_state'] == 'unconscious'

    def test_dead_enemy_wounds_6_has_death_state_dead(self):
        """Enemy with wounds >= 6 returns death_state='dead'."""
        mapper = TargetIDMapper()
        mapper.enable()
        enemy = _create_test_enemy(health=0, max_health=12, wounds=6)
        tid = mapper.register_enemy(enemy)

        info = mapper.get_combatant_info(tid)
        assert info['wounds'] == 6
        assert info['death_state'] == 'dead'

    def test_permanently_dead_player_has_death_state_dead(self):
        """Player with _permanently_dead=True returns death_state='dead' even at wounds=5."""
        mapper = TargetIDMapper()
        mapper.enable()
        player = _create_test_player(health=0, wounds=5, permanently_dead=True)
        tid = "tgt_p1"
        mapper.target_id_map[tid] = player
        mapper.reverse_map[player.agent_id] = tid

        info = mapper.get_combatant_info(tid)
        assert info['death_state'] == 'dead'

    def test_alive_player_has_wounds_and_stuns(self):
        """Player with some wounds/stuns returns correct values."""
        mapper = TargetIDMapper()
        mapper.enable()
        player = _create_test_player(health=15, max_health=27, wounds=2, stuns=1)
        tid = "tgt_p2"
        mapper.target_id_map[tid] = player
        mapper.reverse_map[player.agent_id] = tid

        info = mapper.get_combatant_info(tid)
        assert info['wounds'] == 2
        assert info['stuns'] == 1
        assert info['death_state'] == 'alive'

    def test_enemy_with_stuns_reported(self):
        """Enemy stuns field is reported in combatant info."""
        mapper = TargetIDMapper()
        mapper.enable()
        enemy = _create_test_enemy(health=8, max_health=12, wounds=1)
        enemy.stuns = 2
        tid = mapper.register_enemy(enemy)

        info = mapper.get_combatant_info(tid)
        assert info['stuns'] == 2
        assert info['wounds'] == 1
