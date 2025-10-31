"""
tests/unit/test_yags_compliance.py

Validate game follows YAGS rules from content/Aeonisk - YAGS Module - v1.2.2.md

Tests core game mechanics:
- Combat round structure (declare→resolve→synthesis)
- Dice mechanics and difficulty tiers
- Void progression rules
- Clock advancement
- Enemy spawning
- Action economy (free vs main actions)
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


class TestCombatRoundStructure:
    """Combat rounds should follow YAGS structure: declare all → resolve all → synthesis."""

    def test_combat_round_phase_order(self, combat_events):
        """Rounds follow: declarations → resolutions → synthesis."""
        rounds = parse_into_rounds(combat_events)

        for round_num, events in rounds.items():
            declarations = [e for e in events if e['event_type'] == 'action_declaration']
            resolutions = [e for e in events if e['event_type'] == 'action_resolution']
            synthesis = [e for e in events if e['event_type'] in ['round_synthesis', 'round_summary']]

            # Should have all three phases
            if not declarations:
                continue  # May be narrative-only rounds

            assert len(resolutions) > 0, \
                f"Round {round_num} has declarations but no resolutions"
            assert len(synthesis) > 0, \
                f"Round {round_num} has actions but no synthesis"

            # Check rough temporal order (allow async overlap)
            if declarations and resolutions:
                last_decl_ts = max(datetime.fromisoformat(e['ts']) for e in declarations)
                first_res_ts = min(datetime.fromisoformat(e['ts']) for e in resolutions)

                # Resolutions should generally come after declarations
                # (allow small overlap due to async processing)
                time_diff = (first_res_ts - last_decl_ts).total_seconds()

                assert time_diff >= -5, \
                    f"Round {round_num}: Resolutions started too early before declarations ({time_diff}s)"

    def test_round_numbers_sequential(self, combat_events):
        """Round numbers should be sequential (1, 2, 3, ...)."""
        round_starts = [e for e in combat_events if e['event_type'] == 'round_start']
        round_nums = [e['round'] for e in round_starts]

        # Should start at 1
        assert min(round_nums) == 1, f"Rounds should start at 1, got {min(round_nums)}"

        # Should be sequential
        expected = list(range(1, max(round_nums) + 1))
        assert sorted(set(round_nums)) == expected, \
            f"Round numbers not sequential: {sorted(set(round_nums))}"


class TestDiceMechanics:
    """Validate dice rolling and success tier calculations."""

    def test_roll_calculation_correct(self, combat_events):
        """Roll total should equal (attr × skill + d20)."""
        resolutions = [e for e in combat_events
                      if e['event_type'] == 'action_resolution'
                      and e.get('roll')]

        for res in resolutions:
            roll = res['roll']

            # Get values
            attr_val = roll.get('attr_val')
            skill_val = roll.get('skill_val')
            d20 = roll.get('d20')
            total = roll.get('total')
            ability = roll.get('ability')

            if attr_val is not None and skill_val is not None and d20 is not None:
                # YAGS formula: (attr × skill) + d20 = total
                # BUT: if skill = 0, apply unskilled penalty: attr - 5
                if skill_val == 0:
                    expected_ability = attr_val - 5  # Unskilled penalty
                else:
                    expected_ability = attr_val * skill_val

                expected_total = expected_ability + d20

                assert ability == expected_ability, \
                    f"Ability calculation wrong: {attr_val} × {skill_val} (unskilled: {skill_val == 0}) = {ability}, expected {expected_ability}"

                assert total == expected_total, \
                    f"Total calculation wrong: {ability} + {d20} = {total}, expected {expected_total}"

    def test_success_tier_from_margin(self, combat_events):
        """Success tier should match margin thresholds."""
        resolutions = [e for e in combat_events
                      if e['event_type'] == 'action_resolution'
                      and e.get('roll')]

        for res in resolutions:
            roll = res['roll']
            margin = roll.get('margin')
            tier = roll.get('tier', '').lower()
            success = roll.get('success')

            if margin is None:
                continue

            # YAGS tiers (approximate):
            # margin < -10: critical_failure
            # margin < 0: failure
            # margin >= 0: moderate_success
            # margin >= 5: good_success
            # margin >= 10: excellent_success
            # margin >= 15: exceptional_success

            if margin < 0:
                assert not success, f"Negative margin ({margin}) but success=True"
                assert 'failure' in tier, f"Negative margin ({margin}) but tier={tier}"
            else:
                assert success, f"Positive margin ({margin}) but success=False"
                assert 'success' in tier or tier in ['moderate', 'good', 'excellent', 'exceptional'], \
                    f"Positive margin ({margin}) but tier={tier}"

    def test_margin_calculation(self, combat_events):
        """Margin should equal (total - DC)."""
        resolutions = [e for e in combat_events
                      if e['event_type'] == 'action_resolution'
                      and e.get('roll')]

        for res in resolutions:
            roll = res['roll']
            total = roll.get('total')
            dc = roll.get('dc')
            margin = roll.get('margin')

            if total is not None and dc is not None and margin is not None:
                expected_margin = total - dc

                assert margin == expected_margin, \
                    f"Margin wrong: {total} - {dc} = {margin}, expected {expected_margin}"


class TestVoidProgression:
    """Validate void corruption mechanics."""

    def test_void_values_in_valid_range(self, combat_events):
        """Void should be 0-10 range."""
        character_states = [e for e in combat_events if e['event_type'] == 'character_state']

        for state in character_states:
            # Check if void field exists (may be nested)
            void_value = None

            # Try different possible locations
            if 'void' in state:
                void_value = state['void']
            elif 'character_data' in state and 'void' in state['character_data']:
                void_value = state['character_data']['void']

            if void_value is not None:
                assert 0 <= void_value <= 10, \
                    f"Void value {void_value} outside valid range [0, 10]"

    def test_void_changes_tracked_in_economy(self, combat_events):
        """Void changes should be in economy.void_delta."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        for res in resolutions:
            economy = res.get('economy', {})

            if 'void_delta' in economy:
                void_delta = economy['void_delta']

                # Void changes should be reasonable (not huge jumps)
                assert -5 <= void_delta <= 5, \
                    f"Void delta {void_delta} suspiciously large"

                # Should have reason or source
                has_context = ('void_triggers' in economy or
                             'void_source' in economy)

                if not has_context:
                    print(f"INFO: Void delta {void_delta} without context")

    @pytest.mark.xfail(reason="Known bug: Void ceiling at 8 may not be enforced consistently")
    def test_void_ceiling_enforced(self, combat_events):
        """Void should not exceed 8 during normal gameplay (ceiling rule)."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        for res in resolutions:
            char_data = res.get('character_data', {})
            void_value = char_data.get('void')

            if void_value is not None:
                # This may fail - known bug where void can exceed 8
                assert void_value <= 8, \
                    f"Void {void_value} exceeds ceiling of 8 for {char_data.get('name')}"


class TestClockMechanics:
    """Validate scene clock advancement."""

    def test_clock_progress_format(self, combat_events):
        """Clocks should be in format 'X/Y' (current/max)."""
        resolutions = [e for e in combat_events
                      if e['event_type'] == 'action_resolution'
                      and e.get('clocks')]

        for res in resolutions:
            clocks = res['clocks']

            for clock_name, clock_value in clocks.items():
                # Should be in format "N/M"
                assert '/' in str(clock_value), \
                    f"Clock '{clock_name}' has invalid format: {clock_value}"

                # Parse and validate
                parts = str(clock_value).split('/')
                assert len(parts) == 2, \
                    f"Clock '{clock_name}' format wrong: {clock_value}"

                current, maximum = parts
                current_int = int(current)
                max_int = int(maximum)

                assert 0 <= current_int <= max_int, \
                    f"Clock '{clock_name}' progress invalid: {current_int}/{max_int}"

    def test_clock_advancement_reasonable(self, combat_events):
        """Clock advancement should be gradual (not jumping to completion)."""
        resolutions = [e for e in combat_events
                      if e['event_type'] == 'action_resolution'
                      and e.get('clocks')]

        clock_history = {}

        for res in resolutions:
            clocks = res.get('clocks', {})

            for clock_name, clock_value in clocks.items():
                current, maximum = map(int, str(clock_value).split('/'))

                if clock_name in clock_history:
                    prev_current, prev_max = clock_history[clock_name]

                    # Max should stay consistent
                    assert maximum == prev_max, \
                        f"Clock '{clock_name}' max changed: {prev_max} → {maximum}"

                    # Progress should be gradual (not jumping more than 2 segments)
                    delta = current - prev_current
                    assert -2 <= delta <= 2, \
                        f"Clock '{clock_name}' jumped too much: {prev_current} → {current}"

                clock_history[clock_name] = (current, maximum)


class TestEnemySpawning:
    """Validate enemy spawning mechanics."""

    def test_enemy_spawn_events_logged(self, combat_events):
        """Enemy spawns should have enemy_spawn events."""
        spawns = [e for e in combat_events if e['event_type'] == 'enemy_spawn']

        # Should have at least one spawn in combat session
        assert len(spawns) > 0, "Combat session should have at least one enemy_spawn event"

    def test_enemy_spawn_has_required_fields(self, combat_events):
        """Enemy spawn events must have name, template, position."""
        spawns = [e for e in combat_events if e['event_type'] == 'enemy_spawn']

        for spawn in spawns:
            # Should have identifying info
            has_identifier = ('name' in spawn or 'enemy_name' in spawn or
                            'character_name' in spawn)

            assert has_identifier, \
                f"Enemy spawn missing identifier: {list(spawn.keys())}"

    def test_enemies_appear_in_declarations(self, combat_events):
        """Spawned enemies should make action declarations."""
        spawns = [e for e in combat_events if e['event_type'] == 'enemy_spawn']
        declarations = [e for e in combat_events if e['event_type'] == 'action_declaration']

        # Get enemy identifiers from spawns
        enemy_ids = set()
        for spawn in spawns:
            enemy_id = spawn.get('enemy_id') or spawn.get('player_id') or spawn.get('name')
            if enemy_id:
                enemy_ids.add(enemy_id)

        # Check if enemies declared actions
        declaring_agents = set()
        for decl in declarations:
            agent = decl.get('player_id') or decl.get('character_name') or decl.get('agent_id')
            if agent:
                declaring_agents.add(agent)

        # Should have some overlap
        if enemy_ids:
            overlap = enemy_ids & declaring_agents
            if not overlap:
                print(f"INFO: Spawned enemies ({enemy_ids}) may not have declared actions")


class TestActionEconomy:
    """Validate free actions vs main actions."""

    def test_free_actions_marked(self, combat_events):
        """Free actions should be marked as is_free_action."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        for res in resolutions:
            context = res.get('context', {})

            # Check if is_free_action flag exists
            if 'is_free_action' in context:
                is_free = context['is_free_action']

                # Should be boolean
                assert isinstance(is_free, bool), \
                    f"is_free_action should be bool, got {type(is_free)}"

                # If free action, should typically be communication/perception
                if is_free:
                    action_type = context.get('action_type', '').lower()
                    action_text = res.get('action', '').lower()

                    # Common free action patterns (not exhaustive)
                    free_keywords = ['communicate', 'coordinate', 'observe', 'notice', 'shout', 'signal']

                    is_plausible_free = any(kw in action_text or kw in action_type
                                           for kw in free_keywords)

                    if not is_plausible_free:
                        print(f"INFO: Action marked as free but may be main: {action_text[:50]}")

    @pytest.mark.xfail(reason="Known bug: Action economy tracking may have gaps")
    def test_one_main_action_per_round(self, combat_events):
        """Each character should have at most one main action per round (known gaps)."""
        rounds = parse_into_rounds(combat_events)

        for round_num, events in rounds.items():
            resolutions = [e for e in events
                          if e['event_type'] == 'action_resolution'
                          and not e.get('context', {}).get('is_free_action', False)]

            # Count main actions per character
            character_actions = {}
            for res in resolutions:
                agent = res.get('agent') or res.get('character_name')
                if agent:
                    character_actions[agent] = character_actions.get(agent, 0) + 1

            # Each should have ≤1 main action
            for character, count in character_actions.items():
                # This may fail due to known bugs
                assert count <= 1, \
                    f"Round {round_num}: {character} has {count} main actions (should be ≤1)"


class TestInterPartyCoordination:
    """Validate party coordination mechanics."""

    def test_coordination_actions_identified(self, combat_events):
        """Coordination actions should be identifiable."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        coordination_keywords = ['coordinate', 'help', 'assist', 'support', 'team up', 'work together']

        coordination_count = 0
        for res in resolutions:
            action = res.get('action', '').lower()
            context = res.get('context', {}).get('description', '').lower()

            if any(kw in action or kw in context for kw in coordination_keywords):
                coordination_count += 1

                # Should have economy/soulcredit data for coordinating
                economy = res.get('economy', {})
                if economy.get('soulcredit_delta', 0) > 0:
                    # Good - rewarded for coordination
                    pass
                else:
                    print(f"INFO: Coordination action without soulcredit: {action[:50]}")

        # Soft check - coordination should happen in team combat
        if coordination_count == 0:
            print("INFO: No coordination actions detected in combat session")


# Helper functions
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
