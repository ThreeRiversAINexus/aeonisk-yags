#!/usr/bin/env python3
"""
Session Analyzer - Lightweight tool for analyzing JSONL session logs.

Usage:
    python scripts/analyze_session.py <session.jsonl> [--mode=summary|clocks|void|errors|actions|timeline]
    python scripts/analyze_session.py <session.jsonl> --validate-fixture
    python scripts/analyze_session.py --discover <directory> [--complete-only] [--min-rounds N]

Modes:
    summary (default) - Quick overview (~30-40 lines)
    clocks           - Clock progression detail (~5-30 lines)
    void             - Void trajectory (~10-20 lines)
    errors           - Error analysis (~10-50 lines)
    validate-fixture - Validate schema and replay-readiness (exit 0=pass, 1=fail)

Discovery:
    --discover <dir> - Scan directory for sessions, rank by interestingness
    --complete-only  - Only show complete sessions (with session_end)
    --min-rounds N   - Filter sessions with at least N rounds

Output is designed to be concise (<2000 tokens) for use in development/debugging
without blowing up context windows.
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional, Set, Tuple


# Event type schemas - define required fields for each event type
# All events have base fields: event_type, ts, session, event_id, parent_event_id, correlation_id (v1.2.0+)
# Note: event_id, parent_event_id, correlation_id are optional for backward compatibility with v1.0.0/v1.1.0 logs

# Base fields present in ALL events (v1.2.0+)
BASE_FIELDS = ["event_type", "ts", "session"]
CAUSAL_CHAIN_FIELDS = ["event_id", "parent_event_id", "correlation_id"]  # Optional for v1.0/v1.1 compat

EVENT_SCHEMAS = {
    # === Core Session Events ===
    "session_start": {
        "required": ["event_type", "ts", "session", "config", "version"],
        "optional": ["random_seed", "git_commit", "event_id", "parent_event_id", "correlation_id"]
    },
    "session_end": {
        "required": ["event_type", "ts", "session", "final_state"],
        "optional": ["termination_reason", "event_id", "parent_event_id", "correlation_id"]
    },
    "scenario": {
        "required": ["event_type", "ts", "session", "scenario"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },
    "round_start": {
        "required": ["event_type", "ts", "session", "round"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },

    # === Action Events ===
    "declaration_phase_start": {
        "required": ["event_type", "ts", "session", "round"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },
    "action_declaration": {
        "required": ["event_type", "ts", "session", "round", "player_id", "character_name", "initiative", "action"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },
    "adjudication_start": {
        "required": ["event_type", "ts", "session", "round", "action_count"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },
    "action_resolution": {
        "required": ["event_type", "ts", "session", "round", "phase", "agent", "action", "roll", "economy", "clocks", "effects"],
        "optional": ["context", "outcome_tiers", "outcome_tiers_full", "environment", "stakes", "goal",
                     "roll_formula", "rationale", "aware_agents", "event_id", "parent_event_id", "correlation_id"]
    },

    # === Combat Events ===
    "combat_action": {
        "required": ["event_type", "ts", "session", "round", "attacker", "defender", "weapon", "attack"],
        "optional": ["damage", "wounds_dealt", "defender_state_after", "event_id", "parent_event_id", "correlation_id"]
    },
    "enemy_spawn": {
        "required": ["event_type", "ts", "session", "round", "enemy_id", "enemy_name", "template", "stats", "position", "tactics"],
        "optional": ["count", "faction", "event_id", "parent_event_id", "correlation_id"]
    },
    "enemy_defeat": {
        "required": ["event_type", "ts", "session", "round", "enemy_id", "enemy_name", "defeat_reason", "rounds_survived"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },

    # === Character State Events ===
    "character_state": {
        "required": ["event_type", "ts", "session", "round", "character_id", "character_name", "health", "max_health",
                     "wounds", "void_score", "soulcredit", "position", "conditions", "is_defeated"],
        "optional": ["death_state", "agent", "event_id", "parent_event_id", "correlation_id",
                     "energy", "seeds"]  # Economy system fields
    },
    "void_change": {
        "required": ["event_type", "ts", "session", "round", "agent", "old_void", "new_void", "delta", "reason"],
        "optional": ["capped", "event_id", "parent_event_id", "correlation_id"]
    },

    # === Clock Events ===
    # Note: Clock events support two formats for backward compatibility:
    # - New format: fields at top level (clock_name, old_value, etc.)
    # - Old format: fields nested in 'data' wrapper
    "clock_spawn": {
        "required": ["event_type", "ts", "session", "clock_name", "max_ticks", "description"],
        "optional": ["round", "current_ticks", "advance_meaning", "regress_meaning", "filled_consequence",
                     "event_id", "parent_event_id", "correlation_id"]
    },
    "clock_advancement": {
        "required": ["event_type", "ts", "session", "round"],
        "optional": ["data", "clock_name", "old_value", "new_value", "maximum", "filled", "reason",
                     "event_id", "parent_event_id", "correlation_id"]
    },
    "clock_completion": {
        "required": ["event_type", "ts", "session", "round"],
        "optional": ["data", "clock_name", "final_ticks", "maximum_ticks", "reasons", "filled_consequence",
                     "advance_meaning", "regress_meaning", "event_id", "parent_event_id", "correlation_id"]
    },
    "clock_removal": {
        "required": ["event_type", "ts", "session", "round"],
        "optional": ["data", "clock_name", "reason", "event_id", "parent_event_id", "correlation_id"]
    },
    "clock_update": {
        "required": ["event_type", "ts", "session", "round", "data"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },

    # === Round Summary Events ===
    "round_summary": {
        "required": ["event_type", "ts", "session", "round", "actions_attempted", "success_count", "success_rate", "average_margin"],
        "optional": ["damage_dealt_by_players", "damage_taken_by_players", "void_gained", "void_lost",
                     "clocks_advanced", "clocks_regressed", "clocks_filled", "total_ticks_advanced",
                     "total_ticks_regressed", "active_enemies", "player_wounds_total",
                     "event_id", "parent_event_id", "correlation_id"]
    },
    "round_synthesis": {
        "required": ["event_type", "ts", "session", "round", "synthesis"],
        "optional": ["story_advancement", "scene_pivot", "clocks_filled", "clocks_expired",
                     "session_end", "session_end_reason", "event_id", "parent_event_id", "correlation_id"]
    },
    "mission_debrief": {
        "required": ["event_type", "ts", "session", "character", "debrief", "final_state"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },

    # === NPC/Entity Lifecycle Events ===
    "npc_departure": {
        "required": ["event_type", "ts", "session", "round", "npc_id", "npc_name", "departure_reason"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },
    "agent_conversion": {
        "required": ["event_type", "ts", "session", "round", "agent_id", "agent_name", "from_type", "to_type", "trigger"],
        "optional": ["state_before", "state_after", "event_id", "parent_event_id", "correlation_id"]
    },
    "entity_lifecycle": {
        "required": ["event_type", "ts", "session", "round", "data"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },

    # === Economy Events ===
    "purchase_attempt": {
        "required": ["event_type", "ts", "session", "round", "player_id", "character_name", "vendor_id",
                     "vendor_name", "item_id", "item_name", "cost", "player_currency", "success"],
        "optional": ["failure_reason", "shortage", "event_id", "parent_event_id", "correlation_id"]
    },

    # === Social Events ===
    "social_deescalation": {
        "required": ["event_type", "ts", "session", "round", "player_id", "player_name", "enemy_id",
                     "enemy_name", "action_type", "skill", "roll", "outcome", "narration"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },

    # === Targeting Events ===
    "targeting_validation": {
        "required": ["event_type", "ts", "session", "round", "agent_id", "original_target", "correction_method",
                     "triggered_by", "success"],
        "optional": ["corrected_target", "declared_target", "original_effect_type", "model_used",
                     "confidence", "reasoning", "error_description", "validation_time_ms",
                     "event_id", "parent_event_id", "correlation_id"]
    },

    # === Meta/System Events ===
    "llm_call": {
        "required": ["event_type", "ts", "session", "agent_id", "agent_type", "call_sequence", "prompt", "response", "model", "temperature", "tokens"],
        "optional": ["round", "event_id", "parent_event_id", "correlation_id"]
    },
    "marker_retry_attempt": {
        "required": ["event_type", "ts", "session", "round", "marker_type", "invalid_markers", "retry_prompt"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },
    "marker_retry_result": {
        "required": ["event_type", "ts", "session", "round", "marker_type", "retry_response", "success"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },
    "structured_output_metrics": {
        "required": ["event_type", "ts", "session", "round", "agent_type", "agent_id",
                     "structured_output_success", "fallback_triggered", "validation_warnings"],
        "optional": ["validation_issues_count", "completeness_score", "is_complete",
                     "event_id", "parent_event_id", "correlation_id"]
    },
    "pydantic_validation_failure": {
        "required": ["event_type", "ts", "session", "round", "agent_type", "agent_id", "schema_name",
                     "exception_type", "error_message", "attempt_number", "max_attempts"],
        "optional": ["is_final_attempt", "raw_model_response", "underlying_error", "action_context",
                     "event_id", "parent_event_id", "correlation_id"]
    },
    "narrative_memory": {
        "required": ["event_type", "ts", "session", "round", "agent_id", "character_name", "memory"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },

    # === Economy Events ===
    "energy_transfer": {
        "required": ["event_type", "ts", "session", "round", "data"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },

    # === Environment Events ===
    "void_level_update": {
        "required": ["event_type", "ts", "session", "round"],
        "optional": ["data", "old_level", "new_level", "reason", "event_id", "parent_event_id", "correlation_id"]
    },
    "entity_lifecycle_story_advancement": {
        "required": ["event_type", "ts", "session", "round"],
        "optional": ["data", "event_id", "parent_event_id", "correlation_id"]
    },

    # === Legacy/Deprecated Events (kept for backward compatibility) ===
    "attrition": {
        "required": ["event_type", "ts", "session", "round", "data"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },
    "morale_check": {
        "required": ["event_type", "ts", "session", "round", "data"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
    },
    "healing_applied": {
        "required": ["event_type", "ts", "session", "round", "data"],
        "optional": ["event_id", "parent_event_id", "correlation_id"]
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

    def validate_event_schema(self, event: Dict[str, Any], line_num: int, strict: bool = True) -> bool:
        """
        Validate a single event against its schema.

        Args:
            event: The event dict to validate
            line_num: Line number in JSONL file (for error reporting)
            strict: If True, fail on unknown event types and unknown fields

        Returns:
            True if valid, False if invalid
        """
        # Check event_type exists
        if "event_type" not in event:
            self.errors.append(f"Line {line_num}: Missing 'event_type' field")
            return False

        event_type = event["event_type"]

        # Check if event type has a schema
        if event_type not in EVENT_SCHEMAS:
            if strict:
                self.errors.append(f"Line {line_num}: Unknown event_type '{event_type}' - not in EVENT_SCHEMAS")
                return False
            else:
                self.warnings.append(f"Line {line_num}: Unknown event_type '{event_type}' (may be legacy)")
                return True

        schema = EVENT_SCHEMAS[event_type]

        # Check required fields
        valid = True
        for field in schema["required"]:
            if field not in event:
                self.errors.append(f"Line {line_num}: Event '{event_type}' missing required field '{field}'")
                valid = False

        # Check for unknown fields (strict mode)
        if strict:
            allowed_fields = set(schema["required"]) | set(schema.get("optional", []))
            actual_fields = set(event.keys())
            unknown_fields = actual_fields - allowed_fields
            if unknown_fields:
                self.errors.append(f"Line {line_num}: Event '{event_type}' has unknown fields: {sorted(unknown_fields)}")
                valid = False

        # Validate specific field structures
        if event_type == "combat_action" and "attack" in event:
            attack = event["attack"]
            # Attack can be empty {} for damage-only events or partial for simplified combat
            # Only validate if attack has ANY fields (non-empty)
            if attack:
                required_attack_fields = ["attr", "attr_val", "skill", "skill_val", "d20", "total", "dc", "hit", "margin"]
                missing_fields = [f for f in required_attack_fields if f not in attack]
                # Warn if partial but don't fail - combat may use simplified format
                if missing_fields and len(missing_fields) < len(required_attack_fields):
                    self.warnings.append(f"Line {line_num}: combat_action.attack has partial fields (missing: {missing_fields})")

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


class SessionDiscovery:
    """Scan directories for sessions and rank by interestingness."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.sessions = []

    def scan(self, complete_only: bool = False, min_rounds: int = 0) -> List[Dict[str, Any]]:
        """Scan directory for session files and extract metadata."""
        jsonl_files = sorted(self.directory.rglob("session_*.jsonl"))

        for jsonl_file in jsonl_files:
            metadata = self._extract_metadata(jsonl_file)

            # Apply filters
            if complete_only and not metadata['complete']:
                continue
            if min_rounds > 0 and metadata['rounds'] < min_rounds:
                continue

            self.sessions.append(metadata)

        return self.sessions

    def _extract_metadata(self, jsonl_file: Path) -> Dict[str, Any]:
        """Extract key metadata from a session file."""
        metadata = {
            'file': jsonl_file.name,
            'path': jsonl_file,
            'complete': False,
            'rounds': 0,
            'events': 0,
            'size': jsonl_file.stat().st_size,
            'scenario': None,
            'enemies_spawned': 0,
            'enemies_defeated': 0,
            'actions': 0,
            'clocks': set(),
            'deescalations': 0,
            'npcs': 0,
            'player_count': 0,
            'void_start': None,
            'void_end': None,
        }

        try:
            with open(jsonl_file) as f:
                for line in f:
                    event = json.loads(line)
                    metadata['events'] += 1
                    event_type = event.get('event_type')

                    if event_type == 'session_end':
                        metadata['complete'] = True
                    elif event_type == 'scenario':
                        metadata['scenario'] = event.get('scenario', {})
                        void_level = metadata['scenario'].get('void_level')
                        if void_level is not None and metadata['void_start'] is None:
                            metadata['void_start'] = void_level
                    elif event_type == 'action_resolution':
                        metadata['actions'] += 1
                        # Track clocks
                        clocks = event.get('clocks', {})
                        metadata['clocks'].update(clocks.keys())
                    elif event_type == 'enemy_spawn':
                        metadata['enemies_spawned'] += event.get('count', event.get('context', {}).get('count', 1))
                    elif event_type == 'enemy_defeat':
                        metadata['enemies_defeated'] += 1
                    elif event_type == 'round_synthesis':
                        # Check for deescalations/NPCs
                        synthesis = event.get('data', {})
                        if 'deescalations' in synthesis:
                            metadata['deescalations'] += len(synthesis.get('deescalations', []))
                        if 'npc_spawns' in synthesis:
                            metadata['npcs'] += len(synthesis.get('npc_spawns', []))
                    elif event_type == 'session_start':
                        config = event.get('config', {})
                        metadata['player_count'] = config.get('party_size', 0)

                    # Track max round
                    r = event.get('round')
                    if r and r > metadata['rounds']:
                        metadata['rounds'] = r

                    # Track environmental void at end
                    if event_type == 'round_synthesis':
                        synthesis = event.get('data', {})
                        if 'new_void_level' in synthesis:
                            metadata['void_end'] = synthesis['new_void_level']

        except Exception as e:
            print(f"Warning: Error reading {jsonl_file.name}: {e}")

        metadata['clocks'] = len(metadata['clocks'])
        return metadata

    def calculate_interestingness(self, session: Dict[str, Any]) -> float:
        """
        Calculate an interestingness score for story generation.

        Factors:
        - Longer sessions (more rounds)
        - Combat variety (enemies)
        - Story complexity (clocks, NPCs, deescalations)
        - Completeness (has ending)
        """
        score = 0.0

        # Rounds (linear scaling, max bonus at 10+ rounds)
        score += min(session['rounds'] * 10, 100)

        # Combat engagement
        if session['enemies_spawned'] > 0:
            score += 30
            score += min(session['enemies_defeated'] * 5, 30)

        # Story complexity
        score += session['clocks'] * 15  # Clocks indicate dynamic story
        score += session['deescalations'] * 20  # Deescalations = interesting social dynamics
        score += session['npcs'] * 10  # NPCs add depth

        # Actions indicate engagement
        score += min(session['actions'] * 2, 50)

        # Completeness bonus (big!)
        if session['complete']:
            score += 100

        # Void changes (interesting dynamics)
        if session['void_start'] is not None and session['void_end'] is not None:
            void_delta = abs(session['void_end'] - session['void_start'])
            score += void_delta * 5

        return score

    def print_ranked_sessions(self, limit: int = 20):
        """Print sessions ranked by interestingness."""
        # Calculate scores
        for session in self.sessions:
            session['score'] = self.calculate_interestingness(session)

        # Sort by score
        self.sessions.sort(key=lambda x: x['score'], reverse=True)

        # Print header
        total = len(self.sessions)
        complete = sum(1 for s in self.sessions if s['complete'])
        print(f"\n=== DISCOVERED {total} SESSIONS ({complete} complete) ===\n")

        # Print top sessions
        shown = min(limit, len(self.sessions))
        for i, s in enumerate(self.sessions[:shown], 1):
            self._print_session_summary(i, s)

        if len(self.sessions) > limit:
            print(f"\n({len(self.sessions) - limit} more sessions not shown)")

    def _print_session_summary(self, rank: int, s: Dict[str, Any]):
        """Print a single session summary."""
        status = "✓" if s['complete'] else "⚠"
        theme = s['scenario'].get('theme', 'Unknown')[:70] if s['scenario'] else 'Unknown'
        location = s['scenario'].get('location', 'Unknown')[:50] if s['scenario'] else 'Unknown'
        size_mb = s['size'] / (1024 * 1024)

        print(f"{rank}. {status} {s['file']} (score: {s['score']:.0f})")
        print(f"   {theme}")
        print(f"   Location: {location}")

        # Stats line
        stats = []
        stats.append(f"{s['rounds']} rounds")
        stats.append(f"{s['actions']} actions")
        if s['enemies_spawned'] > 0:
            stats.append(f"{s['enemies_spawned']} enemies ({s['enemies_defeated']} defeated)")
        if s['clocks'] > 0:
            stats.append(f"{s['clocks']} clocks")
        if s['deescalations'] > 0:
            stats.append(f"{s['deescalations']} deescalations")
        if s['npcs'] > 0:
            stats.append(f"{s['npcs']} NPCs")
        stats.append(f"{size_mb:.1f}MB")

        print(f"   {' | '.join(stats)}")

        # Void info
        if s['void_start'] is not None:
            if s['void_end'] is not None:
                delta = s['void_end'] - s['void_start']
                delta_str = f"{delta:+d}" if delta != 0 else "0"
                print(f"   Void: {s['void_start']}/10 → {s['void_end']}/10 ({delta_str})")
            else:
                print(f"   Void: {s['void_start']}/10")

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

        # Actions (split PC vs NPC)
        if self.stats['actions']:
            # Separate PC and NPC actions
            pc_actions = [a for a in self.stats['actions']
                          if not a.get('context', {}).get('is_npc', False)]
            npc_actions = [a for a in self.stats['actions']
                           if a.get('context', {}).get('is_npc', False)]

            total_actions = len(self.stats['actions'])

            # PC action stats
            pc_total = len(pc_actions)
            pc_successes = sum(1 for a in pc_actions if a['roll'].get('success', False))
            pc_failures = pc_total - pc_successes
            pc_rate = (pc_successes / pc_total * 100) if pc_total > 0 else 0

            # Calculate average margin (PC only)
            pc_margins = [a['roll'].get('margin', 0) for a in pc_actions if 'margin' in a['roll']]
            avg_margin = sum(pc_margins) / len(pc_margins) if pc_margins else 0

            # Top skills (PC only)
            skills_used = []
            for action in pc_actions:
                roll = action['roll']
                skill = roll.get('skill', 'Unknown')
                if skill != 'Unknown':
                    skills_used.append(skill)
            skill_counts = Counter(skills_used)
            top_skills = skill_counts.most_common(3)

            print(f"\nACTIONS ({total_actions} total, {pc_total} PC, {len(npc_actions)} NPC):")
            print(f"  PC Success: {pc_successes}/{pc_total} ({pc_rate:.0f}%)")
            print(f"  PC Failure: {pc_failures} ({100-pc_rate:.0f}%)")
            print(f"  PC Avg margin: {avg_margin:+.1f}")
            if top_skills:
                skills_str = ', '.join(f"{skill} ({count})" for skill, count in top_skills)
                print(f"  Top skills: {skills_str}")
            if npc_actions:
                npc_types = Counter(a.get('context', {}).get('action_type', 'unknown') for a in npc_actions)
                npc_str = ', '.join(f"{t} ({c})" for t, c in npc_types.most_common())
                print(f"  NPC actions: {len(npc_actions)} ({npc_str})")

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

    def print_errors(self):
        """Print error analysis from logged events (~10-50 lines)."""
        print(f"\n=== ERROR ANALYSIS ===\n")

        # Collect errors from various event types
        errors = {
            'session_errors': [],       # From session_error events (fatal errors)
            'validation_warnings': [],  # From structured_output_metrics
            'llm_fallbacks': [],        # From structured_output_metrics
            'failed_actions': [],       # From action_resolution with failure
            'parsing_errors': [],       # Any parsing/schema issues
            'system_errors': [],        # Generic error events
        }

        for idx, event in enumerate(self.events, start=1):
            event_type = event.get('event_type')
            round_num = event.get('round', 0)

            # Check for session_error events (fatal errors)
            if event_type == 'session_error':
                errors['session_errors'].append({
                    'line': idx,
                    'round': round_num,
                    'error_type': event.get('error_type', 'unknown'),
                    'error_message': event.get('error_message', 'Unknown error'),
                    'exception_type': event.get('exception_type', 'unknown'),
                    'context': event.get('context', {}),
                })

            # Check structured_output_metrics for validation warnings
            elif event_type == 'structured_output_metrics':
                warnings = event.get('validation_warnings', [])
                if warnings:
                    errors['validation_warnings'].append({
                        'line': idx,
                        'round': round_num,
                        'agent': event.get('agent_id', 'unknown'),
                        'warnings': warnings,
                    })

                if event.get('fallback_triggered', False):
                    errors['llm_fallbacks'].append({
                        'line': idx,
                        'round': round_num,
                        'agent': event.get('agent_id', 'unknown'),
                        'reason': event.get('fallback_reason', 'unknown'),
                        'attempt': event.get('attempt_number', 1),
                    })

            # Check action_resolution for failures
            elif event_type == 'action_resolution':
                roll = event.get('roll', {})
                if not roll.get('success', False):
                    # Only track significant failures (margin < -5)
                    margin = roll.get('margin', 0)
                    if margin < -5:
                        errors['failed_actions'].append({
                            'line': idx,
                            'round': round_num,
                            'agent': event.get('agent', 'unknown'),
                            'action': event.get('action', '')[:50],
                            'margin': margin,
                            'skill': roll.get('skill', 'unknown'),
                        })

            # Check for explicit error fields
            if 'error' in event or 'exception' in event:
                errors['system_errors'].append({
                    'line': idx,
                    'round': round_num,
                    'event_type': event_type,
                    'error': event.get('error', event.get('exception', 'unknown')),
                })

        # Print summary
        total_errors = sum(len(v) for v in errors.values())
        if total_errors == 0:
            print("✓ No errors found in session\n")
            return

        print(f"Found {total_errors} issues across {len([k for k, v in errors.items() if v])} categories:\n")

        # Print session errors (FATAL - most important)
        if errors['session_errors']:
            print(f"⚠️  SESSION ERRORS ({len(errors['session_errors'])}) - FATAL:")
            for err in errors['session_errors']:
                round_str = f"R{err['round']}" if err['round'] else "Setup"
                context = err.get('context', {})
                agent_id = context.get('agent_id', 'unknown')
                print(f"  Line {err['line']:4d} | {round_str:6s} | {err['error_type']}")
                print(f"    Exception: {err['exception_type']}")
                print(f"    Message: {err['error_message'][:100]}")
                if context:
                    print(f"    Context: {context}")
            print()

        # Print validation warnings
        if errors['validation_warnings']:
            print(f"VALIDATION WARNINGS ({len(errors['validation_warnings'])}):")
            for err in errors['validation_warnings'][:10]:
                round_str = f"R{err['round']}" if err['round'] else "Setup"
                warnings_str = ', '.join(err['warnings'][:3])
                if len(err['warnings']) > 3:
                    warnings_str += f" (+{len(err['warnings'])-3} more)"
                print(f"  Line {err['line']:4d} | {round_str:6s} | {err['agent']:20s} | {warnings_str}")
            if len(errors['validation_warnings']) > 10:
                print(f"  ... and {len(errors['validation_warnings']) - 10} more warnings")
            print()

        # Print LLM fallbacks
        if errors['llm_fallbacks']:
            print(f"LLM FALLBACKS ({len(errors['llm_fallbacks'])}):")
            for err in errors['llm_fallbacks'][:10]:
                round_str = f"R{err['round']}" if err['round'] else "Setup"
                print(f"  Line {err['line']:4d} | {round_str:6s} | {err['agent']:20s} | Attempt {err['attempt']} | {err['reason']}")
            if len(errors['llm_fallbacks']) > 10:
                print(f"  ... and {len(errors['llm_fallbacks']) - 10} more fallbacks")
            print()

        # Print significant action failures
        if errors['failed_actions']:
            print(f"SIGNIFICANT ACTION FAILURES ({len(errors['failed_actions'])} with margin < -5):")
            # Group by character
            by_character = defaultdict(list)
            for err in errors['failed_actions']:
                by_character[err['agent']].append(err)

            for character, failures in sorted(by_character.items()):
                avg_margin = sum(f['margin'] for f in failures) / len(failures)
                print(f"\n  {character} ({len(failures)} failures, avg margin: {avg_margin:.1f}):")
                for err in failures[:5]:
                    action = err['action'][:40] + '...' if len(err['action']) > 40 else err['action']
                    print(f"    R{err['round']:2d} | Line {err['line']:4d} | {err['skill']:15s} | {err['margin']:+3d} | {action}")
                if len(failures) > 5:
                    print(f"    ... and {len(failures) - 5} more failures")
            print()

        # Print system errors
        if errors['system_errors']:
            print(f"SYSTEM ERRORS ({len(errors['system_errors'])}):")
            for err in errors['system_errors']:
                round_str = f"R{err['round']}" if err['round'] else "Setup"
                error_str = str(err['error'])[:80]
                print(f"  Line {err['line']:4d} | {round_str:6s} | {err['event_type']:25s} | {error_str}")
            print()

        print()

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
            'action_resolution': ['round', 'agent_name', 'action', 'resolution.success_tier', 'resolution.margin', 'context.is_npc', 'context.dialogue_content'],
            'action_declaration': ['round', 'character_name', 'initiative', 'action.intent', 'action.action_type'],
            'scenario': ['scenario.theme', 'scenario.location', 'scenario.void_level'],
            'round_start': ['round'],
            'round_synthesis': ['round', 'synthesis'],  # synthesis field, not narration (legacy format)
            'enemy_spawn': ['round', 'context.template', 'context.count'],
            'enemy_defeat': ['round', 'context.enemy_name'],
            'session_start': ['config.session_name', 'git_commit'],  # git_commit is at top level, not in config
            'session_end': ['session'],
            'clock_advancement': ['round', 'data.clock_name', 'data.before_ticks', 'data.after_ticks', 'data.maximum_ticks', 'data.delta', 'data.filled'],
            'clock_completion': ['round', 'data.clock_name', 'data.final_ticks', 'data.maximum_ticks'],
            'clock_removal': ['round', 'data.clock_name', 'data.current_ticks', 'data.maximum_ticks', 'data.removal_reason', 'data.expiration_type', 'data.filled'],
            'npc_departure': ['round', 'npc_name', 'reason'],
            'entity_lifecycle': ['round', 'lifecycle_type', 'affected_entities'],
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
  python scripts/analyze_session.py session.jsonl --mode=errors

  # Search/extract specific events
  python scripts/analyze_session.py session.jsonl --search event_type=action_resolution
  python scripts/analyze_session.py session.jsonl --search event_type=action_resolution round=2
  python scripts/analyze_session.py session.jsonl --search event_type=scenario --fields scenario.void_level,scenario.location

  # Discovery mode (find interesting stories)
  python scripts/analyze_session.py --discover multiagent_output/
  python scripts/analyze_session.py --discover multiagent_output/ --complete-only
  python scripts/analyze_session.py --discover multiagent_output/ --min-rounds 5 --limit 10

  # Utilities
  python scripts/analyze_session.py session.jsonl --search event_type=action_resolution --count
  python scripts/analyze_session.py session.jsonl --search event_type=action_resolution --index
  python scripts/analyze_session.py session.jsonl --line 5

  # Fixture validation
  python scripts/analyze_session.py --validate-fixtures                    # All fixtures in tests/fixtures/sessions/
  python scripts/analyze_session.py tests/fixtures/sessions/*.jsonl --validate-fixture   # Multiple files
  python scripts/analyze_session.py fixture.jsonl --validate-fixture       # Single file (detailed report)
        """
    )
    parser.add_argument('jsonl_files', nargs='*', type=Path, help='Path(s) to JSONL session file(s)')
    parser.add_argument(
        '--discover',
        type=Path,
        metavar='DIR',
        help='Scan directory for sessions and rank by interestingness'
    )
    parser.add_argument(
        '--complete-only',
        action='store_true',
        help='Only show complete sessions (with session_end)'
    )
    parser.add_argument(
        '--min-rounds',
        type=int,
        default=0,
        help='Minimum rounds required for discovery results'
    )
    parser.add_argument(
        '--mode',
        choices=['summary', 'clocks', 'void', 'errors'],
        help='Analysis mode (summary=default, clocks, void, errors)'
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
    parser.add_argument(
        '--validate-fixtures',
        action='store_true',
        help='Validate ALL fixtures in tests/fixtures/sessions/. Shortcut for validating the standard fixture directory.'
    )

    args = parser.parse_args()

    # Handle --validate-fixtures shortcut (auto-discover fixtures)
    if args.validate_fixtures:
        fixture_dir = Path(__file__).parent.parent / "tests" / "fixtures" / "sessions"
        fixture_files = sorted(fixture_dir.glob("*.jsonl"))

        if not fixture_files:
            print(f"No fixtures found in {fixture_dir}")
            return 1

        print(f"{'='*70}")
        print(f"FIXTURE VALIDATION: {len(fixture_files)} files")
        print(f"{'='*70}\n")

        total_valid = 0
        total_invalid = 0
        results = []

        for fixture_path in fixture_files:
            validator = FixtureValidator(fixture_path)
            is_valid, _ = validator.validate()

            if is_valid:
                total_valid += 1
                status = "✅ VALID"
            else:
                total_invalid += 1
                status = "❌ INVALID"
                # Collect error summary
                error_summary = validator.errors[:3] if validator.errors else []
                results.append((fixture_path.name, error_summary))

            print(f"{status}  {fixture_path.name}")

        print(f"\n{'='*70}")
        print(f"SUMMARY: {total_valid} valid, {total_invalid} invalid")
        print(f"{'='*70}")

        # Print error details for invalid fixtures
        if results:
            print("\nINVALID FIXTURE DETAILS:")
            for name, errors in results:
                print(f"\n  {name}:")
                for err in errors:
                    print(f"    - {err[:80]}{'...' if len(err) > 80 else ''}")
                if len(errors) < len([e for e in validator.errors if name in str(e)]):
                    print(f"    ... and more errors")

        return 0 if total_invalid == 0 else 1

    # Handle --discover mode (scans directory)
    if args.discover:
        if not args.discover.exists():
            print(f"Error: Directory not found: {args.discover}")
            return 1
        if not args.discover.is_dir():
            print(f"Error: Not a directory: {args.discover}")
            return 1

        discovery = SessionDiscovery(args.discover)
        discovery.scan(complete_only=args.complete_only, min_rounds=args.min_rounds)
        discovery.print_ranked_sessions(limit=args.limit)
        return 0

    # For non-discover modes, require jsonl_files
    if not args.jsonl_files:
        print("Error: Either provide JSONL file(s) or use --discover <directory> or --validate-fixtures")
        parser.print_help()
        return 1

    # Validate all files exist
    for jsonl_file in args.jsonl_files:
        if not jsonl_file.exists():
            print(f"Error: File not found: {jsonl_file}")
            return 1

    # Handle --validate-fixture with multiple files
    if args.validate_fixture:
        if len(args.jsonl_files) == 1:
            # Single file - detailed report
            validator = FixtureValidator(args.jsonl_files[0])
            is_valid, exit_code = validator.validate()
            validator.print_report()
            return exit_code
        else:
            # Multiple files - summary table
            print(f"{'='*70}")
            print(f"FIXTURE VALIDATION: {len(args.jsonl_files)} files")
            print(f"{'='*70}\n")

            total_valid = 0
            total_invalid = 0
            invalid_details = []

            for jsonl_file in args.jsonl_files:
                validator = FixtureValidator(jsonl_file)
                is_valid, _ = validator.validate()

                if is_valid:
                    total_valid += 1
                    status = "✅ VALID"
                else:
                    total_invalid += 1
                    status = "❌ INVALID"
                    invalid_details.append((jsonl_file.name, validator.errors[:3]))

                print(f"{status}  {jsonl_file.name}")

            print(f"\n{'='*70}")
            print(f"SUMMARY: {total_valid} valid, {total_invalid} invalid")
            print(f"{'='*70}")

            if invalid_details:
                print("\nINVALID FIXTURE DETAILS:")
                for name, errors in invalid_details:
                    print(f"\n  {name}:")
                    for err in errors:
                        print(f"    - {err[:80]}{'...' if len(err) > 80 else ''}")

            return 0 if total_invalid == 0 else 1

    # For non-validation modes, only support single file
    if len(args.jsonl_files) > 1:
        print("Error: Multiple files only supported with --validate-fixture. Use one file for other modes.")
        return 1

    analyzer = SessionAnalyzer(args.jsonl_files[0])

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
    elif mode == 'errors':
        analyzer.print_errors()

    return 0


if __name__ == '__main__':
    exit(main())
