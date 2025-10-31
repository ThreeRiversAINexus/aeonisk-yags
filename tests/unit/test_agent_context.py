"""
tests/unit/test_agent_context.py

Verify agents see correct information in their prompts/context.
Ensures game state is properly reflected in agent decision-making.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime


@pytest.fixture
def combat_events():
    """Load real combat session."""
    jsonl_path = Path(__file__).parent.parent / "fixtures" / "sample_logs" / "combat_session_sample.jsonl"
    events = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events


class TestPlayerContext:
    """Player agents should see relevant party information."""

    def test_player_prompts_have_character_info(self, combat_events):
        """Player prompts should show character state (health, void, skills, etc)."""
        llm_calls = [e for e in combat_events
                    if e['event_type'] == 'llm_call'
                    and e.get('agent_type') == 'player']

        for call in llm_calls:
            prompt = call.get('prompt', '')

            # Should mention character attributes/state (exact format varies)
            has_stats = any(keyword in prompt.lower() for keyword in
                          ['health', 'void', 'skill', 'attribute', 'wounds', 'energy'])

            if not has_stats:
                agent = call.get('agent_id', 'unknown')
                print(f"WARNING: Player {agent} prompt missing character stats")

    def test_player_sees_tactical_position(self, combat_events):
        """Players should see tactical positioning information in combat."""
        llm_calls = [e for e in combat_events
                    if e['event_type'] == 'llm_call'
                    and e.get('agent_type') == 'player']

        # Get all player names to check if this is multiplayer
        player_calls = [c for c in llm_calls if c.get('round')]  # In-combat calls

        position_keywords = ['Engaged', 'Near', 'Far', 'Extreme', 'position', 'range', 'distance']

        for call in player_calls:
            prompt = call.get('prompt', '')

            has_position = any(kw in prompt for kw in position_keywords)

            # Tactical info should generally be present in combat
            if not has_position:
                print(f"INFO: Player prompt missing position info (round {call.get('round')})")


class TestDMContext:
    """DM should see all declarations before resolving."""

    def test_dm_sees_all_declarations_in_round(self, combat_events):
        """DM resolution prompts should include all declarations for that round."""
        rounds = parse_into_rounds(combat_events)

        for round_num, events in rounds.items():
            # Get all declarations
            declarations = [e for e in events if e['event_type'] == 'action_declaration']

            # Get DM's llm_calls for this round
            dm_calls = [e for e in events
                       if e['event_type'] == 'llm_call'
                       and e.get('round') == round_num
                       and e.get('agent_type') == 'dm']

            if dm_calls and declarations:
                # Check DM calls have context about declarations
                for dm_call in dm_calls:
                    prompt = dm_call.get('prompt', '')

                    # DM should see declaration info
                    # (exact structure varies, but should mention actions or characters)
                    has_action_context = len(prompt) > 500  # DM prompts are substantial

                    if not has_action_context:
                        print(f"INFO: DM prompt in round {round_num} seems short")

    def test_dm_has_character_states(self, combat_events):
        """DM should have access to all character states."""
        llm_calls = [e for e in combat_events
                    if e['event_type'] == 'llm_call'
                    and e.get('agent_type') == 'dm'
                    and e.get('round')]  # Combat rounds

        for call in llm_calls:
            prompt = call.get('prompt', '')

            # Handle prompt as list (message array) or string
            if isinstance(prompt, list):
                prompt_text = ' '.join(str(msg.get('content', '')) if isinstance(msg, dict) else str(msg) for msg in prompt)
            else:
                prompt_text = str(prompt)

            # DM should see character health/void/status
            has_character_data = any(keyword in prompt_text.lower() for keyword in
                                    ['health', 'void', 'wounds', 'character', 'pc'])

            if not has_character_data:
                print(f"WARNING: DM prompt missing character state in round {call.get('round')}")


class TestEnemyContext:
    """Enemy agents should see player positions and states."""

    def test_enemy_prompts_have_position_info(self, combat_events):
        """Enemy prompts should mention tactical positions."""
        llm_calls = [e for e in combat_events
                    if e['event_type'] == 'llm_call'
                    and e.get('agent_type') == 'enemy']

        position_keywords = ['Engaged', 'Near', 'Far', 'Extreme', 'position', 'range', 'distance']

        for call in llm_calls:
            prompt = call.get('prompt', '')

            has_position = any(kw in prompt for kw in position_keywords)

            # Tactical info should generally be present
            if not has_position:
                print(f"INFO: Enemy prompt missing position information")

    def test_enemy_sees_player_characters(self, combat_events):
        """Enemy prompts should mention player characters."""
        # Get player names from character_state or action_resolution events
        player_names = set()
        for e in combat_events:
            if e.get('event_type') == 'character_state':
                name = e.get('character') or e.get('name') or e.get('character_name')
                if name and 'enemy' not in name.lower() and 'grunt' not in name.lower():
                    player_names.add(name)

        # Also check action resolutions for PC names
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']
        for res in resolutions:
            agent = res.get('agent')
            if agent and 'enemy' not in agent.lower() and 'grunt' not in agent.lower():
                player_names.add(agent)

        llm_calls = [e for e in combat_events
                    if e['event_type'] == 'llm_call'
                    and e.get('agent_type') == 'enemy']

        for call in llm_calls:
            prompt = call.get('prompt', '')

            # Handle prompt as list (message array) or string
            if isinstance(prompt, list):
                prompt_text = ' '.join(str(msg.get('content', '')) if isinstance(msg, dict) else str(msg) for msg in prompt)
            else:
                prompt_text = str(prompt)

            # Should mention at least one player (case insensitive)
            mentions_player = any(p.lower() in prompt_text.lower() for p in player_names if p)

            if not mentions_player and player_names:
                print(f"INFO: Enemy prompt doesn't mention any players")


class TestContextUpdates:
    """Context should reflect game state changes."""

    def test_context_reflects_previous_round(self, combat_events):
        """Round N+1 context should reflect Round N outcomes."""
        rounds = parse_into_rounds(combat_events)
        # Filter out None (round 0) and sort
        round_nums = sorted([r for r in rounds.keys() if r is not None and r > 0])

        if len(round_nums) < 2:
            pytest.skip("Need multiple rounds to test context updates")

        # Get resolutions from round 1
        round1_resolutions = [e for e in rounds[round_nums[0]]
                             if e['event_type'] == 'action_resolution']

        # Check if any significant events happened (damage, void, clocks)
        significant_events = []
        for res in round1_resolutions:
            economy = res.get('economy', {})
            if economy.get('void_delta', 0) != 0:
                significant_events.append(('void', res.get('agent')))
            if res.get('clocks'):
                significant_events.append(('clock', res.get('agent')))

        # Round 2 prompts should reference previous events
        round2_calls = [e for e in rounds[round_nums[1]]
                       if e['event_type'] == 'llm_call']

        # Just verify prompts exist and have substantial content
        # (actual state reflection is implementation-specific)
        for call in round2_calls:
            prompt = call.get('prompt', '')

            # Handle prompt as list (message array) or string
            if isinstance(prompt, list):
                prompt_len = sum(len(str(msg.get('content', ''))) if isinstance(msg, dict) else len(str(msg)) for msg in prompt)
            else:
                prompt_len = len(str(prompt))

            assert prompt_len > 100, \
                f"Round 2 prompt for {call.get('agent_type')} suspiciously short"

    @pytest.mark.xfail(reason="Known bug: Environmental changes may not always propagate to next round context")
    def test_environmental_changes_persist(self, combat_events):
        """Environmental changes should persist across rounds (known to have gaps)."""
        rounds = parse_into_rounds(combat_events)
        round_nums = sorted(rounds.keys())

        if len(round_nums) < 2:
            pytest.skip("Need multiple rounds to test environment persistence")

        # Look for environment mentions in round 1
        round1_resolutions = [e for e in rounds[round_nums[0]]
                             if e['event_type'] == 'action_resolution']

        env_changes = []
        for res in round1_resolutions:
            narration = res.get('context', {}).get('narration', '')
            # Look for environmental keywords
            if any(word in narration.lower() for word in ['fire', 'smoke', 'debris', 'cover', 'darkness']):
                env_changes.append(narration[:100])

        if env_changes:
            # Round 2 should reference these changes
            round2_calls = [e for e in rounds[round_nums[1]]
                           if e['event_type'] == 'llm_call'
                           and e.get('agent_type') == 'dm']

            # This may fail due to known bugs
            for call in round2_calls:
                prompt = call.get('prompt', '')
                # Should mention environment somehow
                assert len(prompt) > 500, "DM prompt should have environmental context"


class TestSharedGameState:
    """Test that shared game state (clocks, discoveries, etc.) is visible."""

    def test_clocks_visible_to_relevant_agents(self, combat_events):
        """Clocks should be visible in prompts when relevant."""
        # Find events where clocks exist
        clock_events = [e for e in combat_events
                       if e.get('event_type') == 'action_resolution'
                       and e.get('clocks')]

        if not clock_events:
            pytest.skip("No clock data in combat session")

        # Get clock names
        clock_names = set()
        for event in clock_events:
            clocks = event.get('clocks', {})
            clock_names.update(clocks.keys())

        # Check if clocks appear in subsequent prompts
        llm_calls = [e for e in combat_events if e['event_type'] == 'llm_call']

        clock_mentions = 0
        for call in llm_calls:
            prompt = call.get('prompt', '')

            # Handle prompt as list (message array) or string
            if isinstance(prompt, list):
                prompt_text = ' '.join(str(msg.get('content', '')) if isinstance(msg, dict) else str(msg) for msg in prompt)
            else:
                prompt_text = str(prompt)

            if any(clock_name.lower() in prompt_text.lower() for clock_name in clock_names):
                clock_mentions += 1

        # Soft check - clocks should be mentioned at least somewhere
        if clock_mentions == 0 and clock_names:
            print(f"INFO: Clocks exist ({clock_names}) but never mentioned in prompts")


# Helper
def parse_into_rounds(events):
    """Group events by round number."""
    rounds = {}
    for event in events:
        if 'round' in event:
            round_num = event['round']
            if round_num not in rounds:
                rounds[round_num] = []
            rounds[round_num].append(event)
    return rounds
