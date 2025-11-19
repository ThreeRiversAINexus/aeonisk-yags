#!/usr/bin/env python3
"""
Session Analyzer - Lightweight tool for analyzing JSONL session logs.

Usage:
    python scripts/analyze_session.py <session.jsonl> [--mode=summary|clocks|void|actions|timeline]
    python scripts/analyze_session.py <session.jsonl> --validate-fixture

Modes:
    summary (default) - Quick overview (~30-40 lines)
    clocks           - Clock progression detail (~5-30 lines)
    void             - Void trajectory (~10-20 lines)
    validate-fixture - Validate schema and replay-readiness (exit 0=pass, 1=fail)

Output is designed to be concise (<2000 tokens) for use in development/debugging
without blowing up context windows.
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional, Set, Tuple


# Event type schemas - define required fields for each event type
EVENT_SCHEMAS = {
    "session_start": {
        "required": ["event_type", "ts", "session", "config", "version"],
        "optional": []
    },
    "scenario": {
        "required": ["event_type", "ts", "session", "scenario"],
        "optional": []
    },
    "round_start": {
        "required": ["event_type", "ts", "session", "round"],
        "optional": []
    },
    "action_resolution": {
        "required": ["event_type", "ts", "session", "round", "phase", "agent", "action", "roll", "economy", "clocks", "effects"],
        "optional": ["context"]
    },
    "combat_action": {
        "required": ["event_type", "ts", "session", "round", "attacker", "defender", "weapon", "attack"],
        "optional": ["damage", "wounds_dealt", "defender_state_after"]
    },
    "character_state": {
        "required": ["event_type", "ts", "session", "round", "character_id", "character_name", "health", "max_health", "wounds", "void_score", "soulcredit", "position", "conditions", "is_defeated"],
        "optional": []
    },
    "enemy_spawn": {
        "required": ["event_type", "ts", "session", "round", "enemy_id", "enemy_name", "template", "stats", "position", "tactics"],
        "optional": []
    },
    "enemy_defeat": {
        "required": ["event_type", "ts", "session", "round", "enemy_id", "enemy_name", "defeat_reason", "rounds_survived"],
        "optional": []
    },
    "round_summary": {
        "required": ["event_type", "ts", "session", "round", "actions_attempted", "success_count", "success_rate", "average_margin"],
        "optional": ["damage_dealt_by_players", "damage_taken_by_players", "void_gained", "void_lost", "clocks_advanced", "clocks_filled", "active_enemies", "player_wounds_total"]
    },
    "clock_advancement": {
        "required": ["event_type", "ts", "session", "round", "data"],
        "optional": []
    },
    "void_change": {
        "required": ["event_type", "ts", "session", "round", "agent", "old_void", "new_void", "delta", "reason"],
        "optional": ["capped"]
    },
    "clock_completion": {
        "required": ["event_type", "ts", "session", "round", "data"],
        "optional": []
    },
    "clock_removal": {
        "required": ["event_type", "ts", "session", "round", "data"],
        "optional": []
    },
    "llm_call": {
        "required": ["event_type", "ts", "session", "agent_id", "agent_type", "call_sequence", "prompt", "response", "model", "temperature", "tokens"],
        "optional": ["round"]
    }
}


class FixtureValidator:
    """Validate JSONL fixtures for schema compliance and replay-readiness."""

    def __init__(self, jsonl_path: Path):
        self.jsonl_path = jsonl_path
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.stats = {
            'total_events': 0,
            'valid_events': 0,
            'invalid_events': 0,
            'event_type_counts': Counter(),
            'player_llm_calls': 0,
            'dm_llm_calls': 0,
            'enemy_llm_calls': 0,
            'has_random_seed': False,
            'has_session_start': False,
            'has_scenario': False,
            'rounds': set(),
            'agent_ids': set(),
        }

    def validate_event_schema(self, event: Dict[str, Any], line_num: int) -> bool:
        """Validate a single event against its schema. Returns True if valid."""
        # Check event_type exists
        if "event_type" not in event:
            self.errors.append(f"Line {line_num}: Missing 'event_type' field")
            return False

        event_type = event["event_type"]

        # Check if event type has a schema
        if event_type not in EVENT_SCHEMAS:
            # Generic events are allowed but not validated
            if event_type not in ["action_declaration", "adjudication_start", "declaration_phase_start",
                                   "clock_spawn", "round_synthesis", "mission_debrief", "session_end",
                                   "attrition", "structured_output_metrics"]:
                self.warnings.append(f"Line {line_num}: Unknown event_type '{event_type}' (may be legacy or generic)")
            return True

        schema = EVENT_SCHEMAS[event_type]

        # Check required fields
        valid = True
        for field in schema["required"]:
            if field not in event:
                self.errors.append(f"Line {line_num}: Event '{event_type}' missing required field '{field}'")
                valid = False

        # Validate specific field structures
        if event_type == "combat_action" and "attack" in event:
            attack = event["attack"]
            required_attack_fields = ["attr", "attr_val", "skill", "skill_val", "d20", "total", "dc", "hit", "margin"]
            for field in required_attack_fields:
                if field not in attack:
                    self.errors.append(f"Line {line_num}: combat_action.attack missing field '{field}'")
                    valid = False

            # Validate damage structure if present
            if "damage" in event and event["damage"] is not None:
                damage = event["damage"]
                core_damage_fields = ["soak", "dealt"]
                for field in core_damage_fields:
                    if field not in damage:
                        self.errors.append(f"Line {line_num}: combat_action.damage missing field '{field}'")
                        valid = False

        elif event_type == "character_state":
            # Validate numeric fields
            for field in ["health", "max_health", "wounds", "void_score", "soulcredit"]:
                if field in event and not isinstance(event[field], (int, float)):
                    self.errors.append(f"Line {line_num}: character_state.{field} should be numeric, got {type(event[field])}")
                    valid = False

        elif event_type == "enemy_spawn" and "stats" in event:
            stats = event["stats"]
            required_stats_fields = ["health", "max_health", "soak", "attributes", "skills"]
            for field in required_stats_fields:
                if field not in stats:
                    self.errors.append(f"Line {line_num}: enemy_spawn.stats missing field '{field}'")
                    valid = False

        return valid

    def validate_replay_readiness(self):
        """Check if fixture is ready for replay (has player LLM calls, etc.)."""
        # Check for player LLM calls
        if self.stats['player_llm_calls'] == 0:
            self.errors.append("No player LLM calls found - fixture cannot be replayed (created before commit 55ad4a0?)")

        # Check for essential events
        if not self.stats['has_session_start']:
            self.errors.append("Missing session_start event")

        if not self.stats['has_scenario']:
            self.errors.append("Missing scenario event")

        # Check for random seed in config
        if not self.stats['has_random_seed']:
            self.warnings.append("No random_seed in session config - replay may not be deterministic")

    def validate(self) -> Tuple[bool, int]:
        """
        Validate the entire fixture.

        Returns:
            (is_valid, exit_code) where exit_code is 0 for pass, 1 for fail
        """
        with open(self.jsonl_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                    self.stats['total_events'] += 1

                    # Validate schema
                    is_valid = self.validate_event_schema(event, line_num)
                    if is_valid:
                        self.stats['valid_events'] += 1
                    else:
                        self.stats['invalid_events'] += 1

                    # Track event types
                    event_type = event.get("event_type", "unknown")
                    self.stats['event_type_counts'][event_type] += 1

                    # Track specific events for replay-readiness
                    if event_type == "session_start":
                        self.stats['has_session_start'] = True
                        config = event.get('config', {})
                        if 'random_seed' in config:
                            self.stats['has_random_seed'] = True

                    elif event_type == "scenario":
                        self.stats['has_scenario'] = True

                    elif event_type == "llm_call":
                        agent_type = event.get('agent_type', '')
                        if agent_type == 'player':
                            self.stats['player_llm_calls'] += 1
                        elif agent_type == 'enemy':
                            self.stats['enemy_llm_calls'] += 1
                        elif agent_type == 'dm':
                            self.stats['dm_llm_calls'] += 1

                        # Track agent IDs
                        if 'agent_id' in event:
                            self.stats['agent_ids'].add(event['agent_id'])

                    # Track rounds
                    if 'round' in event and event['round'] is not None:
                        self.stats['rounds'].add(event['round'])

                except json.JSONDecodeError as e:
                    self.stats['invalid_events'] += 1
                    self.errors.append(f"Line {line_num}: JSON parse error: {e}")

        # Run replay-readiness checks
        self.validate_replay_readiness()

        # Determine overall validity
        has_errors = len(self.errors) > 0
        exit_code = 1 if has_errors else 0

        return (not has_errors, exit_code)

    def print_report(self):
        """Print validation report to stdout."""
        print("\n" + "=" * 80)
        print("FIXTURE VALIDATION REPORT")
        print("=" * 80)
        print(f"\nFile: {self.jsonl_path}")
        print(f"Total Events: {self.stats['total_events']}")
        print(f"Valid Events: {self.stats['valid_events']} ({self.stats['valid_events']/self.stats['total_events']*100 if self.stats['total_events'] > 0 else 0:.1f}%)")
        print(f"Invalid Events: {self.stats['invalid_events']}")

        print("\n--- Event Type Distribution ---")
        for event_type, count in self.stats['event_type_counts'].most_common(15):
            print(f"  {event_type:30s}: {count:4d}")

        print(f"\n--- Replay Readiness ---")
        print(f"Session Start: {'✓' if self.stats['has_session_start'] else '✗'}")
        print(f"Scenario: {'✓' if self.stats['has_scenario'] else '✗'}")
        print(f"Random Seed: {'✓' if self.stats['has_random_seed'] else '✗'}")
        print(f"Rounds: {len(self.stats['rounds'])}")
        print(f"Player LLM Calls: {self.stats['player_llm_calls']}")
        print(f"DM LLM Calls: {self.stats['dm_llm_calls']}")
        print(f"Enemy LLM Calls: {self.stats['enemy_llm_calls']}")
        print(f"Unique Agent IDs: {len(self.stats['agent_ids'])}")

        if self.errors:
            print(f"\n--- Validation Errors ({len(self.errors)}) ---")
            for error in self.errors[:20]:
                print(f"  ✗ {error}")
            if len(self.errors) > 20:
                print(f"  ... and {len(self.errors) - 20} more errors")

        if self.warnings:
            print(f"\n--- Warnings ({len(self.warnings)}) ---")
            for warning in self.warnings:
                print(f"  ⚠ {warning}")

        print("\n" + "=" * 80)

        if self.errors:
            print("\n✗ VALIDATION FAILED")
        elif self.warnings:
            print("\n⚠ VALIDATION PASSED WITH WARNINGS")
        else:
            print("\n✓ VALIDATION PASSED")

        print()


class SessionAnalyzer:
    """Analyze JSONL session logs and produce concise stdout reports."""

    def __init__(self, jsonl_path: Path):
        self.jsonl_path = jsonl_path
        self.events: List[Dict[str, Any]] = []
        self.stats = {
            'rounds': 0,
            'total_events': 0,
            'session_id': None,
            'config': None,
            'scenario': None,
            'parties': [],
            'enemies_spawned': 0,
            'enemies_defeated': 0,
            'actions': [],
            'clocks': defaultdict(list),  # clock_name -> [(round, state, reason)]
            'void_changes': defaultdict(list),  # character -> [(round, delta, reason)]
            'environmental_void': [],  # [(round, void_level)]
            'llm_calls': 0,
            'llm_fallbacks': 0,
        }
        self._parse()

    def _parse(self):
        """Single-pass JSONL parsing to extract all relevant data."""
        with open(self.jsonl_path, 'r') as f:
            for line in f:
                event = json.loads(line)
                self.events.append(event)
                self.stats['total_events'] += 1

                event_type = event.get('event_type')
                round_num = event.get('round') or 0  # Handle None explicitly

                # Track max round
                if round_num and round_num > self.stats['rounds']:
                    self.stats['rounds'] = round_num

                # Session metadata
                if event_type == 'session_start':
                    self.stats['session_id'] = event.get('session')
                    self.stats['config'] = event.get('config', {})
                    self.stats['git_commit'] = event.get('git_commit', 'unknown')  # Git commit at event level, not config

                # Scenario info
                elif event_type == 'scenario':
                    scenario = event.get('scenario', {})
                    self.stats['scenario'] = scenario
                    void_level = scenario.get('void_level')
                    if void_level is not None:
                        self.stats['environmental_void'].append((round_num, void_level))

                # Action resolution
                elif event_type == 'action_resolution':
                    self.stats['actions'].append({
                        'round': round_num,
                        'character': event.get('agent', 'Unknown'),
                        'action': event.get('action', 'Unknown'),
                        'roll': event.get('roll', {}),
                        'context': event.get('context', {}),
                        'clocks': event.get('clocks', {}),
                    })

                    # Track clock states from action_resolution
                    clocks = event.get('clocks', {})
                    for clock_name, clock_state in clocks.items():
                        self.stats['clocks'][clock_name].append({
                            'round': round_num,
                            'state': clock_state,
                            'action': event.get('action', 'Unknown'),
                        })

                    # Track void changes from action_resolution economy
                    economy = event.get('economy', {})
                    if economy.get('void_delta', 0) != 0:
                        character = event.get('agent', 'Unknown')
                        reasons = economy.get('void_triggers', [])
                        reason_text = ', '.join(reasons) if reasons else 'unspecified'
                        self.stats['void_changes'][character].append({
                            'round': round_num,
                            'delta': economy['void_delta'],
                            'reason': reason_text,
                        })

                # Enemy spawns/defeats
                elif event_type == 'enemy_spawn':
                    self.stats['enemies_spawned'] += event.get('context', {}).get('count', 1)

                elif event_type == 'enemy_defeat':
                    self.stats['enemies_defeated'] += 1

                # LLM calls
                elif event_type == 'llm_call':
                    self.stats['llm_calls'] += 1

                elif event_type == 'structured_output_metrics':
                    if event.get('fallback_triggered', False):
                        self.stats['llm_fallbacks'] += 1

    def print_summary(self):
        """Print concise session summary (~30-40 lines)."""
        config = self.stats['config'] or {}
        scenario = self.stats['scenario'] or {}

        print(f"\n=== SESSION SUMMARY: {self.jsonl_path.name} ===")

        # Basic info
        session_name = config.get('session_name', 'unknown')
        git_commit = self.stats.get('git_commit', 'unknown')
        if git_commit != 'unknown' and len(git_commit) > 7:
            git_commit = git_commit[:7]  # Truncate to short hash
        print(f"Session: {session_name} | Git: {git_commit}")
        print(f"Rounds: {self.stats['rounds']} | Total Events: {self.stats['total_events']}")

        # Scenario
        if scenario:
            theme = scenario.get('theme', 'Unknown')
            location = scenario.get('location', 'Unknown')
            print(f"\nSCENARIO: {theme}")
            print(f"Location: {location}")

        # Void economy
        env_void = self.stats['environmental_void']
        if env_void:
            start_void = env_void[0][1]
            end_void = env_void[-1][1]
            change = end_void - start_void
            change_str = f"+{change}" if change > 0 else str(change)
            print(f"\nVOID ECONOMY:")
            print(f"  Environmental: {start_void} → {end_void} ({change_str})")

            # Player void averages
            if self.stats['void_changes']:
                total_delta = sum(
                    sum(change['delta'] for change in changes)
                    for changes in self.stats['void_changes'].values()
                )
                player_count = len(self.stats['void_changes'])
                avg_delta = total_delta / player_count if player_count > 0 else 0
                print(f"  Player changes: {total_delta} total ({avg_delta:+.1f} avg)")

        # Combat
        if self.stats['enemies_spawned'] > 0 or self.stats['enemies_defeated'] > 0:
            print(f"\nCOMBAT:")
            print(f"  Enemies spawned: {self.stats['enemies_spawned']}")
            print(f"  Enemies defeated: {self.stats['enemies_defeated']}")

        # Actions
        if self.stats['actions']:
            total_actions = len(self.stats['actions'])
            successes = sum(1 for a in self.stats['actions'] if a['roll'].get('success', False))
            failures = total_actions - successes
            success_rate = (successes / total_actions * 100) if total_actions > 0 else 0

            # Calculate average margin
            margins = [a['roll'].get('margin', 0) for a in self.stats['actions'] if 'margin' in a['roll']]
            avg_margin = sum(margins) / len(margins) if margins else 0

            # Top skills
            skills_used = []
            for action in self.stats['actions']:
                roll = action['roll']
                skill = roll.get('skill', 'Unknown')
                if skill != 'Unknown':
                    skills_used.append(skill)
            skill_counts = Counter(skills_used)
            top_skills = skill_counts.most_common(3)

            print(f"\nACTIONS ({total_actions} total):")
            print(f"  Success: {successes} ({success_rate:.0f}%)")
            print(f"  Failure: {failures} ({100-success_rate:.0f}%)")
            print(f"  Avg margin: {avg_margin:+.1f}")
            if top_skills:
                skills_str = ', '.join(f"{skill} ({count})" for skill, count in top_skills)
                print(f"  Top skills: {skills_str}")

        # Clocks
        if self.stats['clocks']:
            print(f"\nCLOCKS ({len(self.stats['clocks'])} tracked):")
            for clock_name, states in self.stats['clocks'].items():
                if states:
                    first_state = states[0]['state']
                    last_state = states[-1]['state']

                    # Check if filled
                    if '/' in last_state:
                        current, max_ticks = last_state.split('/')
                        filled = current == max_ticks
                        filled_str = " [FILLED]" if filled else ""
                    else:
                        filled_str = ""

                    print(f"  {clock_name}: {first_state} → {last_state}{filled_str}")

        # LLM metrics
        if self.stats['llm_calls'] > 0:
            fallback_rate = (self.stats['llm_fallbacks'] / self.stats['llm_calls'] * 100) if self.stats['llm_calls'] > 0 else 0
            print(f"\nLLM CALLS: {self.stats['llm_calls']} total ({self.stats['llm_fallbacks']} fallbacks, {fallback_rate:.0f}%)")

        print()  # Blank line at end

    def print_clocks(self):
        """Print detailed clock progression (~5-30 lines)."""
        print(f"\n=== CLOCK PROGRESSION ===\n")

        if not self.stats['clocks']:
            print("No clocks tracked in this session.\n")
            return

        for clock_name, states in sorted(self.stats['clocks'].items()):
            if not states:
                continue

            # Get max ticks from last state
            last_state = states[-1]['state']
            if '/' in last_state:
                _, max_ticks = last_state.split('/')
                print(f"[{clock_name}] max={max_ticks}")
            else:
                print(f"[{clock_name}]")

            # Track state changes
            prev_state = None
            for entry in states:
                current_state = entry['state']
                round_num = entry['round']
                action = entry['action']

                # Only print when state changes
                if current_state != prev_state:
                    if prev_state is not None:
                        # Calculate delta
                        if '/' in current_state and '/' in prev_state:
                            prev_ticks = int(prev_state.split('/')[0])
                            curr_ticks = int(current_state.split('/')[0])
                            delta = curr_ticks - prev_ticks
                            delta_str = f" ({delta:+d})" if delta != 0 else ""
                        else:
                            delta_str = ""

                        print(f"  R{round_num}: {prev_state} → {current_state}{delta_str} - {action}")
                    else:
                        print(f"  R{round_num}: {current_state} - {action}")

                    prev_state = current_state

            # Check if filled
            if '/' in last_state:
                current, max_ticks = last_state.split('/')
                if current == max_ticks:
                    print(f"  FILLED: Clock reached {max_ticks}/{max_ticks}")

            print()  # Blank line between clocks

    def print_void(self):
        """Print void trajectory (~10-20 lines)."""
        print(f"\n=== VOID TRAJECTORY ===\n")

        # Environmental void
        env_void = self.stats['environmental_void']
        if env_void:
            print("ENVIRONMENTAL:")
            for round_num, void_level in env_void:
                round_str = f"R{round_num}" if round_num > 0 else "Initial"
                print(f"  {round_str}: {void_level}/10")

        # Player void changes
        if self.stats['void_changes']:
            print("\nPLAYER CHANGES:")
            for character, changes in sorted(self.stats['void_changes'].items()):
                total_delta = sum(c['delta'] for c in changes)
                print(f"\n  {character} ({total_delta:+d} total):")
                for change in changes:
                    round_num = change['round']
                    delta = change['delta']
                    reason = change['reason']
                    print(f"    R{round_num}: {delta:+d} ({reason})")

        if not env_void and not self.stats['void_changes']:
            print("No void changes tracked in this session.")

        print()  # Blank line at end

    def _get_all_field_paths(self, obj: Any, prefix: str = '') -> List[str]:
        """Recursively get all field paths in a nested dict."""
        paths = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                paths.append(new_prefix)
                if isinstance(value, (dict, list)):
                    paths.extend(self._get_all_field_paths(value, new_prefix))
        elif isinstance(obj, list) and obj and isinstance(obj[0], dict):
            # For lists, show structure of first element
            paths.extend(self._get_all_field_paths(obj[0], prefix))
        return paths

    def _get_default_fields(self, event_type: str) -> List[str]:
        """Get smart default fields for an event type."""
        defaults = {
            'action_resolution': ['round', 'agent', 'action', 'roll.success', 'roll.margin'],
            'action_declaration': ['round', 'character_name', 'initiative', 'action.intent'],
            'scenario': ['scenario.theme', 'scenario.location', 'scenario.void_level'],
            'round_start': ['round'],
            'round_synthesis': ['round'],
            'enemy_spawn': ['round', 'context.template', 'context.count'],
            'enemy_defeat': ['round', 'context.enemy_name'],
            'session_start': ['config.session_name', 'config.git_commit'],
            'session_end': ['session'],
            'clock_advancement': ['round', 'data.clock_name', 'data.before_ticks', 'data.after_ticks', 'data.maximum_ticks', 'data.delta', 'data.filled'],
            'clock_completion': ['round', 'data.clock_name', 'data.final_ticks', 'data.maximum_ticks'],
            'clock_removal': ['round', 'data.clock_name', 'data.current_ticks', 'data.maximum_ticks', 'data.removal_reason', 'data.expiration_type', 'data.filled'],
        }
        return defaults.get(event_type, ['event_type', 'round'])

    def search_events(self, filters: Dict[str, str], limit: Optional[int] = 5,
                     fields: Optional[List[str]] = None, count_only: bool = False,
                     show_index: bool = False, show_schema: bool = False) -> List[Dict]:
        """
        Search for events matching filter criteria.

        Args:
            filters: Dict of key=value filters (e.g., {'event_type': 'action_resolution', 'round': '2'})
            limit: Max events to return (None = all)
            fields: List of field paths to extract (e.g., ['round', 'agent', 'roll.success'])
            count_only: If True, only return count
            show_index: If True, return line numbers instead of events

        Returns:
            List of matching events or line numbers
        """
        matches = []
        line_numbers = []

        for idx, event in enumerate(self.events, start=1):
            # Check if event matches all filters
            match = True
            for key, value in filters.items():
                # Support nested keys with dot notation (e.g., 'roll.success')
                keys = key.split('.')
                obj = event
                try:
                    for k in keys:
                        obj = obj[k]
                    # Convert to string for comparison
                    if str(obj) != value:
                        match = False
                        break
                except (KeyError, TypeError):
                    match = False
                    break

            if match:
                matches.append(event)
                line_numbers.append(idx)

        total_matches = len(matches)

        if count_only:
            print(f"Found {total_matches} matching events")
            return []

        if show_schema:
            if total_matches == 0:
                print("No matching events found")
                return []
            # Show available fields from first match
            sample = matches[0]
            all_fields = self._get_all_field_paths(sample)
            print(f"Available fields in {sample.get('event_type', 'unknown')} events:")
            for field in sorted(all_fields):
                print(f"  {field}")
            print(f"\n({total_matches} events match this type)")
            return []

        if show_index:
            if total_matches == 0:
                print("No matching events found")
            else:
                indices = ', '.join(str(i) for i in line_numbers[:20])
                if total_matches > 20:
                    print(f"Matching events at lines: {indices}... ({total_matches} total)")
                else:
                    print(f"Matching events at lines: {indices} ({total_matches} total)")
            return []

        # Apply limit
        shown_count = len(matches) if limit is None else min(limit, len(matches))
        to_show = matches if limit is None else matches[:limit]

        # Print header with count info
        if total_matches == 0:
            print("No matching events found")
            return []

        if limit and total_matches > limit:
            remaining = total_matches - limit
            print(f"Found {total_matches} matching events (showing first {shown_count}):\n")
        else:
            print(f"Found {total_matches} matching events:\n")

        # Determine fields to show
        if fields is None:
            # Use smart defaults based on event type
            event_type = filters.get('event_type')
            if event_type:
                fields = self._get_default_fields(event_type)
            else:
                # Mixed event types, use minimal default
                fields = ['event_type', 'round']

        # Extract and print events with line numbers
        for idx, event in enumerate(to_show):
            line_num = line_numbers[idx]
            extracted = {'_line': line_num}

            for field_path in fields:
                keys = field_path.split('.')
                obj = event
                try:
                    for k in keys:
                        obj = obj[k]
                    # Truncate long strings
                    if isinstance(obj, str) and len(obj) > 50:
                        obj = obj[:47] + '...'
                    extracted[field_path] = obj
                except (KeyError, TypeError):
                    extracted[field_path] = None

            print(json.dumps(extracted, separators=(',', ':')))

        # Print footer with remaining count
        if limit and total_matches > limit:
            remaining = total_matches - limit
            print(f"\n({remaining} more matches not shown. Use --limit {total_matches} to see all)")

        return matches

    def get_event_by_line(self, line_num: int):
        """Get a specific event by line number (1-indexed)."""
        if line_num < 1 or line_num > len(self.events):
            print(f"Error: Line {line_num} out of range (file has {len(self.events)} lines)")
            return None

        event = self.events[line_num - 1]
        print(json.dumps(event, indent=2))
        return event


def main():
    parser = argparse.ArgumentParser(
        description='Analyze JSONL session logs (concise stdout output)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Summary modes
  python scripts/analyze_session.py session.jsonl
  python scripts/analyze_session.py session.jsonl --mode=clocks
  python scripts/analyze_session.py session.jsonl --mode=void

  # Search/extract specific events
  python scripts/analyze_session.py session.jsonl --search event_type=action_resolution
  python scripts/analyze_session.py session.jsonl --search event_type=action_resolution round=2
  python scripts/analyze_session.py session.jsonl --search event_type=scenario --fields scenario.void_level,scenario.location

  # Utilities
  python scripts/analyze_session.py session.jsonl --search event_type=action_resolution --count
  python scripts/analyze_session.py session.jsonl --search event_type=action_resolution --index
  python scripts/analyze_session.py session.jsonl --line 5
        """
    )
    parser.add_argument('jsonl_file', type=Path, help='Path to JSONL session file')
    parser.add_argument(
        '--mode',
        choices=['summary', 'clocks', 'void'],
        help='Analysis mode (summary=default, clocks, void)'
    )
    parser.add_argument(
        '--search',
        nargs='+',
        metavar='KEY=VALUE',
        help='Search for events matching filters (e.g., event_type=action_resolution round=2)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=5,
        help='Max events to show in search (default: 5)'
    )
    parser.add_argument(
        '--fields',
        help='Comma-separated fields to extract (e.g., round,agent,roll.success)'
    )
    parser.add_argument(
        '--count',
        action='store_true',
        help='Only show count of matching events'
    )
    parser.add_argument(
        '--index',
        action='store_true',
        help='Show line numbers of matching events'
    )
    parser.add_argument(
        '--schema',
        action='store_true',
        help='Show available fields for event type'
    )
    parser.add_argument(
        '--line',
        type=int,
        metavar='N',
        help='Get specific event at line N (1-indexed)'
    )
    parser.add_argument(
        '--validate-fixture',
        action='store_true',
        help='Validate fixture schema and replay-readiness (exit 0=pass, 1=fail)'
    )

    args = parser.parse_args()

    if not args.jsonl_file.exists():
        print(f"Error: File not found: {args.jsonl_file}")
        return 1

    # Handle --validate-fixture (runs before SessionAnalyzer to avoid parsing overhead)
    if args.validate_fixture:
        validator = FixtureValidator(args.jsonl_file)
        is_valid, exit_code = validator.validate()
        validator.print_report()
        return exit_code

    analyzer = SessionAnalyzer(args.jsonl_file)

    # Handle --line (get specific event)
    if args.line:
        analyzer.get_event_by_line(args.line)
        return 0

    # Handle --search (extract events)
    if args.search:
        # Parse filters from KEY=VALUE format
        filters = {}
        for filter_str in args.search:
            if '=' not in filter_str:
                print(f"Error: Invalid filter format '{filter_str}'. Use KEY=VALUE")
                return 1
            key, value = filter_str.split('=', 1)
            filters[key] = value

        # Parse fields if provided
        fields_list = None
        if args.fields:
            fields_list = [f.strip() for f in args.fields.split(',')]

        analyzer.search_events(
            filters=filters,
            limit=None if args.count or args.index or args.schema else args.limit,
            fields=fields_list,
            count_only=args.count,
            show_index=args.index,
            show_schema=args.schema
        )
        return 0

    # Default to summary mode if no --search or --line
    mode = args.mode or 'summary'
    if mode == 'summary':
        analyzer.print_summary()
    elif mode == 'clocks':
        analyzer.print_clocks()
    elif mode == 'void':
        analyzer.print_void()

    return 0


if __name__ == '__main__':
    exit(main())
