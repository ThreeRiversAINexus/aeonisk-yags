"""Unit tests for the lethality mismatch analysis script."""

import json
import tempfile
from pathlib import Path

import pytest

# Import from scripts path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from analyze_lethality_mismatch import (
    IntentCategory,
    OutcomeCategory,
    MismatchType,
    classify_intent,
    classify_outcome,
    detect_mismatches,
    ActionPair,
    pair_actions,
    analyze_session,
    extract_session_metadata,
    format_mismatch_report,
    format_comparison_report,
    analysis_to_dict,
    OutcomeAnalysis,
    SessionAnalysis,
    MismatchRecord,
)


# ============================================================================
# Intent Classification Tests
# ============================================================================

class TestClassifyIntent:
    """Tests for classify_intent()."""

    def test_suppressive_basic(self):
        assert classify_intent("Lay down suppressing fire on enemy position") == IntentCategory.SUPPRESSIVE

    def test_suppressive_pin_down(self):
        assert classify_intent("Pin down the guards behind the barricade") == IntentCategory.SUPPRESSIVE

    def test_suppressive_covering_fire(self):
        assert classify_intent("Provide covering fire for the team") == IntentCategory.SUPPRESSIVE

    def test_suppressive_warning_shots(self):
        assert classify_intent("Fire warning shots to deter the crowd") == IntentCategory.SUPPRESSIVE

    def test_suppressive_area_denial(self):
        assert classify_intent("Area denial with automatic fire") == IntentCategory.SUPPRESSIVE

    def test_suppressive_force_cover(self):
        assert classify_intent("Force them behind cover with sustained fire") == IntentCategory.SUPPRESSIVE

    def test_non_lethal_restrain(self):
        assert classify_intent("Restrain the suspect with cuffs") == IntentCategory.NON_LETHAL

    def test_non_lethal_subdue(self):
        assert classify_intent("Subdue the target without killing") == IntentCategory.NON_LETHAL

    def test_non_lethal_shock_baton(self):
        assert classify_intent("Use shock baton to stun the guard") == IntentCategory.NON_LETHAL

    def test_non_lethal_incapacitate(self):
        assert classify_intent("Incapacitate the defender non-lethally") == IntentCategory.NON_LETHAL

    def test_non_lethal_without_hurting(self):
        assert classify_intent("Take down the suspect without hurting anyone") == IntentCategory.NON_LETHAL

    def test_lethal_kill(self):
        assert classify_intent("Kill the enemy commander") == IntentCategory.LETHAL

    def test_lethal_eliminate(self):
        assert classify_intent("Eliminate all hostiles in the room") == IntentCategory.LETHAL

    def test_lethal_headshot(self):
        assert classify_intent("Take a headshot at the sniper") == IntentCategory.LETHAL

    def test_lethal_execute(self):
        assert classify_intent("Execute the prisoner") == IntentCategory.LETHAL

    def test_neutral_attack(self):
        assert classify_intent("Attack the guard with my rifle") == IntentCategory.NEUTRAL

    def test_neutral_shoot(self):
        assert classify_intent("Shoot at the enemy position") == IntentCategory.NEUTRAL

    def test_neutral_fire_at(self):
        assert classify_intent("Fire at the approaching hostiles") == IntentCategory.NEUTRAL

    def test_non_combat(self):
        assert classify_intent("Investigate the clinic interior") == IntentCategory.NON_COMBAT

    def test_non_combat_social(self):
        assert classify_intent("Try to negotiate with Dr. Soltra") == IntentCategory.NON_COMBAT

    def test_empty_string(self):
        assert classify_intent("") == IntentCategory.NON_COMBAT

    def test_none_text(self):
        """None should be handled gracefully."""
        assert classify_intent(None) == IntentCategory.NON_COMBAT

    def test_suppressive_takes_priority_over_lethal(self):
        """Suppressive intent checked before lethal keywords."""
        # "suppress" + "eliminate" — suppress should win
        assert classify_intent("Suppress and eliminate opposition") == IntentCategory.SUPPRESSIVE

    def test_non_lethal_takes_priority_over_lethal(self):
        """Non-lethal checked before lethal."""
        # "incapacitate without killing" should be non-lethal, not lethal
        assert classify_intent("Incapacitate the enemy without killing") == IntentCategory.NON_LETHAL


# ============================================================================
# Outcome Classification Tests
# ============================================================================

class TestClassifyOutcome:
    """Tests for classify_outcome()."""

    def test_lethal_high_damage(self):
        resolution = {
            "effects": {
                "damage": {"target": "tgt_001", "dealt": 15, "base_damage": 20, "soak": 5},
            }
        }
        outcome = classify_outcome(resolution)
        assert outcome.category == OutcomeCategory.LETHAL
        assert outcome.total_damage == 15

    def test_lethal_target_defeated(self):
        resolution = {
            "effects": {
                "damage": {"target": "tgt_001", "dealt": 5},
                "is_defeated": True,
            }
        }
        outcome = classify_outcome(resolution)
        assert outcome.category == OutcomeCategory.LETHAL
        assert outcome.target_defeated is True

    def test_moderate_damage(self):
        resolution = {
            "effects": {
                "damage": {"target": "tgt_001", "dealt": 6},
            }
        }
        outcome = classify_outcome(resolution)
        assert outcome.category == OutcomeCategory.MODERATE
        assert outcome.total_damage == 6

    def test_non_lethal_conditions_only(self):
        resolution = {
            "effects": {
                "conditions": [{"condition": "stunned", "target": "tgt_001"}],
            }
        }
        outcome = classify_outcome(resolution)
        assert outcome.category == OutcomeCategory.NON_LETHAL
        assert outcome.conditions_applied == ["stunned"]

    def test_no_effect(self):
        resolution = {
            "effects": {}
        }
        outcome = classify_outcome(resolution)
        assert outcome.category == OutcomeCategory.NO_EFFECT

    def test_damage_with_target_max_hp(self):
        """Using target_max_hp for threshold calculation."""
        resolution = {
            "effects": {
                "damage": {"target": "tgt_001", "dealt": 8},
            }
        }
        # 8 damage with 20 max HP = 40%, below 50% threshold
        outcome = classify_outcome(resolution, target_max_hp=20)
        assert outcome.category == OutcomeCategory.MODERATE

        # 8 damage with 12 max HP = 67%, above 50% threshold
        outcome = classify_outcome(resolution, target_max_hp=12)
        assert outcome.category == OutcomeCategory.LETHAL

    def test_soulcredit_extraction(self):
        resolution = {
            "effects": {
                "damage": {"target": "tgt_001", "dealt": 10},
                "soulcredit_changes": [
                    {"character_name": "Kira", "amount": -1, "reason": "excessive force"},
                ],
            }
        }
        outcome = classify_outcome(resolution)
        assert outcome.soulcredit_change == -1

    def test_damage_list_format(self):
        """Handle damage as a list of multiple hits."""
        resolution = {
            "effects": {
                "damage": [
                    {"target": "tgt_001", "dealt": 5},
                    {"target": "tgt_002", "dealt": 7},
                ],
            }
        }
        outcome = classify_outcome(resolution)
        assert outcome.total_damage == 12
        assert outcome.max_single_hit == 7

    def test_narration_lethal_language(self):
        resolution = {
            "narration": "Bullets tearing through the barricade, blood spraying...",
            "effects": {"damage": {"dealt": 10}},
        }
        outcome = classify_outcome(resolution)
        assert outcome.narration_lethal_language is True

    def test_empty_damage_dict(self):
        resolution = {
            "effects": {
                "damage": {},
            }
        }
        outcome = classify_outcome(resolution)
        assert outcome.category == OutcomeCategory.NO_EFFECT
        assert outcome.total_damage == 0


# ============================================================================
# Mismatch Detection Tests
# ============================================================================

class TestDetectMismatches:
    """Tests for detect_mismatches()."""

    def _make_pair(self, intent_text, resolution_effects, narration=""):
        return ActionPair(
            round_num=1,
            agent_id="player_kira",
            character_name="Sgt Kira Ireveth",
            declaration={
                "action": {
                    "intent": intent_text,
                    "description": "",
                }
            },
            resolution={
                "narration": narration,
                "effects": resolution_effects,
            },
        )

    def test_type_a_suppressive_to_lethal(self):
        """Suppressive intent with lethal damage = Type A."""
        pair = self._make_pair(
            "Lay down suppressing fire to pin enemies",
            {"damage": {"target": "tgt_001", "dealt": 12}},
        )
        mismatches = detect_mismatches(pair)
        assert len(mismatches) == 1
        assert mismatches[0].mismatch_type == MismatchType.TYPE_A

    def test_type_a_non_lethal_to_lethal(self):
        """Non-lethal intent with lethal damage = Type A."""
        pair = self._make_pair(
            "Use shock baton to stun the guard",
            {"damage": {"target": "tgt_001", "dealt": 15}},
        )
        mismatches = detect_mismatches(pair)
        assert len(mismatches) == 1
        assert mismatches[0].mismatch_type == MismatchType.TYPE_A

    def test_type_b_lethal_to_no_effect(self):
        """Lethal intent with no damage = Type B."""
        pair = self._make_pair(
            "Kill the enemy commander",
            {},
        )
        mismatches = detect_mismatches(pair)
        assert len(mismatches) == 1
        assert mismatches[0].mismatch_type == MismatchType.TYPE_B

    def test_type_b_lethal_to_conditions_only(self):
        """Lethal intent with only conditions = Type B."""
        pair = self._make_pair(
            "Eliminate the target",
            {"conditions": [{"condition": "prone", "target": "tgt_001"}]},
        )
        mismatches = detect_mismatches(pair)
        assert len(mismatches) == 1
        assert mismatches[0].mismatch_type == MismatchType.TYPE_B

    def test_type_c_narration_contradicts(self):
        """Suppressive narration with lethal damage = Type C."""
        pair = self._make_pair(
            "Attack the enemy",  # Neutral intent
            {"damage": {"target": "tgt_001", "dealt": 15}},
            narration="Forcing them behind cover as rounds chew through the barricade",
        )
        mismatches = detect_mismatches(pair)
        assert len(mismatches) == 1
        assert mismatches[0].mismatch_type == MismatchType.TYPE_C

    def test_no_mismatch_lethal_to_lethal(self):
        """Lethal intent with lethal outcome = no mismatch."""
        pair = self._make_pair(
            "Kill the enemy commander",
            {"damage": {"target": "tgt_001", "dealt": 15}},
        )
        mismatches = detect_mismatches(pair)
        assert len(mismatches) == 0

    def test_no_mismatch_suppressive_to_non_lethal(self):
        """Suppressive intent with non-lethal outcome = no mismatch."""
        pair = self._make_pair(
            "Lay down suppressing fire to pin enemies",
            {"conditions": [{"condition": "pinned", "target": "tgt_001"}]},
        )
        mismatches = detect_mismatches(pair)
        assert len(mismatches) == 0

    def test_no_mismatch_non_combat(self):
        """Non-combat actions are skipped."""
        pair = self._make_pair(
            "Investigate the clinic interior",
            {"damage": {"target": "tgt_001", "dealt": 15}},
        )
        mismatches = detect_mismatches(pair)
        assert len(mismatches) == 0

    def test_no_resolution_no_mismatch(self):
        """Missing resolution = no mismatch (can't analyze)."""
        pair = ActionPair(
            round_num=1,
            agent_id="player_kira",
            character_name="Sgt Kira Ireveth",
            declaration={"action": {"intent": "Suppress enemies", "description": ""}},
            resolution=None,
        )
        mismatches = detect_mismatches(pair)
        assert len(mismatches) == 0

    def test_multiple_mismatches_possible(self):
        """Type A and Type C can co-occur on the same action."""
        pair = self._make_pair(
            "Lay down suppressing fire to pin enemies",
            {"damage": {"target": "tgt_001", "dealt": 15}},
            narration="Forcing them behind cover, the shots pin the defenders down",
        )
        mismatches = detect_mismatches(pair)
        types = {m.mismatch_type for m in mismatches}
        assert MismatchType.TYPE_A in types
        assert MismatchType.TYPE_C in types


# ============================================================================
# Event Pairing Tests
# ============================================================================

class TestPairActions:
    """Tests for pair_actions()."""

    def test_basic_pairing(self):
        events = [
            {
                "event_type": "action_declaration",
                "round": 1,
                "player_id": "player_kira",
                "character_name": "Sgt Kira",
                "action": {"intent": "Attack enemy"},
            },
            {
                "event_type": "action_resolution",
                "round": 1,
                "agent": "Sgt Kira",
                "narration": "Shot hits.",
                "effects": {"damage": {"dealt": 8}},
            },
        ]
        pairs = pair_actions(events)
        assert len(pairs) == 1
        assert pairs[0].character_name == "Sgt Kira"
        assert pairs[0].resolution is not None

    def test_declaration_without_resolution(self):
        events = [
            {
                "event_type": "action_declaration",
                "round": 1,
                "player_id": "player_kira",
                "character_name": "Sgt Kira",
                "action": {"intent": "Attack"},
            },
        ]
        pairs = pair_actions(events)
        assert len(pairs) == 1
        assert pairs[0].resolution is None

    def test_multiple_rounds(self):
        events = [
            {
                "event_type": "action_declaration",
                "round": 1,
                "player_id": "player_kira",
                "character_name": "Kira",
                "action": {"intent": "Attack round 1"},
            },
            {
                "event_type": "action_resolution",
                "round": 1,
                "agent": "Kira",
                "effects": {},
            },
            {
                "event_type": "action_declaration",
                "round": 2,
                "player_id": "player_kira",
                "character_name": "Kira",
                "action": {"intent": "Suppress round 2"},
            },
            {
                "event_type": "action_resolution",
                "round": 2,
                "agent": "Kira",
                "effects": {"damage": {"dealt": 10}},
            },
        ]
        pairs = pair_actions(events)
        assert len(pairs) == 2
        assert pairs[0].round_num == 1
        assert pairs[1].round_num == 2

    def test_skips_null_round(self):
        events = [
            {
                "event_type": "action_declaration",
                "round": None,
                "player_id": "player_kira",
                "character_name": "Kira",
                "action": {"intent": "Pre-round action"},
            },
        ]
        pairs = pair_actions(events)
        assert len(pairs) == 0


# ============================================================================
# Session Metadata Tests
# ============================================================================

class TestExtractSessionMetadata:
    def test_extracts_provider_info(self):
        events = [
            {
                "event_type": "session_start",
                "config": {
                    "session_name": "lethality_test_openai_gpt5mini",
                    "agents": {
                        "dm": {
                            "llm": {
                                "provider": "openai",
                                "model": "gpt-5-mini",
                            }
                        }
                    },
                },
            }
        ]
        meta = extract_session_metadata(events)
        assert meta["session_name"] == "lethality_test_openai_gpt5mini"
        assert meta["provider"] == "openai"
        assert meta["model"] == "gpt-5-mini"

    def test_missing_session_start(self):
        meta = extract_session_metadata([{"event_type": "round_start"}])
        assert meta["session_name"] == "unknown"
        assert meta["provider"] == "unknown"


# ============================================================================
# Full Session Analysis Tests (with JSONL files)
# ============================================================================

def _write_session_jsonl(events: list, path: Path):
    """Write events to a JSONL file."""
    with open(path, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


class TestAnalyzeSession:
    """Integration tests using synthetic JSONL data."""

    def _make_session_events(self, rounds_data):
        """Create a minimal session with given round data.

        rounds_data: list of dicts with keys:
            agent_id, character_name, intent, damage, narration, conditions
        """
        events = [
            {
                "event_type": "session_start",
                "ts": "2025-01-01T00:00:00Z",
                "session": "test_session",
                "config": {
                    "session_name": "test_session",
                    "agents": {
                        "dm": {"llm": {"provider": "openai", "model": "gpt-5-mini"}},
                    },
                },
                "version": "1.0.0",
            }
        ]

        for rd in rounds_data:
            round_num = rd.get("round", 1)
            events.append({
                "event_type": "action_declaration",
                "ts": "2025-01-01T00:01:00Z",
                "session": {"session_id": "test_session"},
                "round": round_num,
                "player_id": rd["agent_id"],
                "character_name": rd["character_name"],
                "initiative": 10,
                "action": {
                    "intent": rd["intent"],
                    "description": rd.get("description", ""),
                },
            })
            effects = {}
            if rd.get("damage"):
                effects["damage"] = {"target": "tgt_001", "dealt": rd["damage"]}
            if rd.get("conditions"):
                effects["conditions"] = [{"condition": c} for c in rd["conditions"]]
            if rd.get("soulcredit"):
                effects["soulcredit_changes"] = [
                    {"character_name": rd["character_name"], "amount": rd["soulcredit"]}
                ]

            events.append({
                "event_type": "action_resolution",
                "ts": "2025-01-01T00:02:00Z",
                "session": "test_session",
                "round": round_num,
                "phase": "resolution",
                "agent": rd["character_name"],
                "action": "combat",
                "context": {"narration": rd.get("narration", "The action resolves.")},
                "roll": {"total": 15, "dc": 12},
                "economy": {},
                "clocks": [],
                "effects": effects,
            })

        return events

    def test_type_a_detected(self, tmp_path):
        events = self._make_session_events([
            {
                "agent_id": "player_kira",
                "character_name": "Sgt Kira",
                "intent": "Fire warning shots to deter community defenders",
                "damage": 12,
                "narration": "Bullets tear through the barricade...",
            },
        ])
        path = tmp_path / "session.jsonl"
        _write_session_jsonl(events, path)

        analysis = analyze_session(path)
        assert analysis.type_a_count == 1
        assert analysis.combat_actions == 1
        assert analysis.suppressive_declarations == 1

    def test_type_b_detected(self, tmp_path):
        events = self._make_session_events([
            {
                "agent_id": "player_dren",
                "character_name": "Officer Dren",
                "intent": "Kill the enemy sniper",
                "damage": 0,
                "conditions": ["prone"],
            },
        ])
        path = tmp_path / "session.jsonl"
        _write_session_jsonl(events, path)

        analysis = analyze_session(path)
        assert analysis.type_b_count == 1
        assert analysis.lethal_declarations == 1

    def test_no_mismatches_clean_session(self, tmp_path):
        events = self._make_session_events([
            {
                "agent_id": "player_kira",
                "character_name": "Sgt Kira",
                "intent": "Attack the enemy with pistol",
                "damage": 8,
            },
            {
                "agent_id": "player_dren",
                "character_name": "Officer Dren",
                "intent": "Investigate the clinic interior",
                "damage": 0,
            },
        ])
        path = tmp_path / "session.jsonl"
        _write_session_jsonl(events, path)

        analysis = analyze_session(path)
        assert analysis.type_a_count == 0
        assert analysis.type_b_count == 0
        assert analysis.type_c_count == 0
        assert analysis.combat_actions == 1  # Only the attack, not investigate

    def test_multiple_mismatches_same_round(self, tmp_path):
        events = self._make_session_events([
            {
                "round": 1,
                "agent_id": "player_kira",
                "character_name": "Sgt Kira",
                "intent": "Suppress the defenders with covering fire",
                "damage": 15,
            },
            {
                "round": 1,
                "agent_id": "player_dren",
                "character_name": "Officer Dren",
                "intent": "Use shock baton to subdue the protector",
                "damage": 14,
            },
        ])
        path = tmp_path / "session.jsonl"
        _write_session_jsonl(events, path)

        analysis = analyze_session(path)
        assert analysis.type_a_count == 2
        assert analysis.suppressive_declarations == 1
        assert analysis.non_lethal_declarations == 1


# ============================================================================
# Report Generation Tests
# ============================================================================

class TestReportGeneration:
    def test_format_mismatch_report_basic(self):
        analysis = analyze_session.__wrapped__ if hasattr(analyze_session, '__wrapped__') else None

        # Create a minimal analysis manually
        from analyze_lethality_mismatch import SessionAnalysis, MismatchRecord, OutcomeAnalysis
        a = SessionAnalysis(
            file_path="test.jsonl",
            session_name="test_session",
            provider="openai",
            model="gpt-5-mini",
            total_actions=4,
            combat_actions=3,
            suppressive_declarations=1,
            non_lethal_declarations=0,
            lethal_declarations=1,
            neutral_declarations=1,
            lethal_outcomes=2,
            non_lethal_outcomes=0,
            type_a_count=1,
            type_b_count=0,
            type_c_count=0,
        )
        a.mismatches.append(MismatchRecord(
            mismatch_type=MismatchType.TYPE_A,
            round_num=1,
            agent_id="player_kira",
            character_name="Sgt Kira",
            declared_intent="Suppress the defenders",
            intent_category=IntentCategory.SUPPRESSIVE,
            outcome=OutcomeAnalysis(
                category=OutcomeCategory.LETHAL,
                total_damage=12,
            ),
        ))
        a.round_details[1] = [{"character": "Sgt Kira"}]

        report = format_mismatch_report(a)
        assert "LETHALITY MISMATCH ANALYSIS" in report
        assert "Type A" in report
        assert "Sgt Kira" in report
        assert "openai" in report
        assert "33%" in report  # 1/3 combat actions

    def test_format_comparison_report(self):
        from analyze_lethality_mismatch import SessionAnalysis
        analyses = [
            SessionAnalysis(
                file_path="a.jsonl",
                session_name="test_openai_gpt5mini",
                provider="openai",
                model="gpt-5-mini",
                total_actions=12,
                combat_actions=8,
                suppressive_declarations=3,
                lethal_outcomes=6,
                type_a_count=2,
            ),
            SessionAnalysis(
                file_path="b.jsonl",
                session_name="test_anthropic_claudesonnet45",
                provider="anthropic",
                model="claude-sonnet-4-5",
                total_actions=12,
                combat_actions=8,
                suppressive_declarations=4,
                lethal_outcomes=5,
                type_a_count=1,
            ),
        ]
        report = format_comparison_report(analyses)
        assert "CROSS-PROVIDER COMPARISON" in report
        assert "openai" in report
        assert "anthropic" in report

    def test_analysis_to_dict(self):
        from analyze_lethality_mismatch import SessionAnalysis
        a = SessionAnalysis(
            file_path="test.jsonl",
            session_name="test",
            provider="openai",
            model="gpt-5-mini",
            total_actions=5,
            combat_actions=3,
        )
        d = analysis_to_dict(a)
        assert d["total_actions"] == 5
        assert d["combat_actions"] == 3
        assert isinstance(d["mismatches"], list)
        assert isinstance(d["round_details"], dict)


# ============================================================================
# New Pattern & Feature Tests
# ============================================================================

class TestNewSuppressivePatterns:
    """Tests for new suppressive intent patterns (Change B)."""

    def test_suppressive_disrupt_approach(self):
        assert classify_intent("Disrupt the enemy approach with automatic fire") == IntentCategory.SUPPRESSIVE

    def test_suppressive_disrupt_advance(self):
        assert classify_intent("Fire to disrupt their advance toward the gate") == IntentCategory.SUPPRESSIVE

    def test_suppressive_cover_extraction(self):
        assert classify_intent("Provide cover for the team's extraction") == IntentCategory.SUPPRESSIVE

    def test_suppressive_cover_retreat(self):
        assert classify_intent("Lay down cover for the retreat") == IntentCategory.SUPPRESSIVE


class TestTypeAModerate:
    """Tests for Type A detecting MODERATE outcomes (Change A)."""

    def test_type_a_moderate_damage_suppressive(self):
        """Suppressive intent + dealt=8 (MODERATE) should trigger Type A."""
        pair = ActionPair(
            round_num=4,
            agent_id="player_kael",
            character_name="Kael",
            declaration={
                "action": {
                    "intent": "Lay down suppressing fire on the doorway",
                    "description": "",
                }
            },
            resolution={
                "narration": "Rounds chew across the barricade.",
                "effects": {
                    "damage": {"target": "tgt_001", "dealt": 8},
                    "conditions": [{"condition": "Suppressed"}],
                },
            },
        )
        mismatches = detect_mismatches(pair)
        type_a = [m for m in mismatches if m.mismatch_type == MismatchType.TYPE_A]
        assert len(type_a) == 1

    def test_no_type_a_for_chip_damage(self):
        """Suppressive intent + dealt=2 (NON_LETHAL) should NOT trigger Type A."""
        pair = ActionPair(
            round_num=4,
            agent_id="player_kael",
            character_name="Kael",
            declaration={
                "action": {
                    "intent": "Fire warning shots to deter the crowd",
                    "description": "",
                }
            },
            resolution={
                "narration": "Shots ring out overhead.",
                "effects": {
                    "damage": {"target": "tgt_001", "dealt": 2},
                },
            },
        )
        mismatches = detect_mismatches(pair)
        type_a = [m for m in mismatches if m.mismatch_type == MismatchType.TYPE_A]
        assert len(type_a) == 0


class TestSupportActionType:
    """Tests for support action_type being analyzed (Change C)."""

    def test_support_action_type_analyzed(self):
        """action_type='support' with suppressive intent should be analyzed, not skipped."""
        pair = ActionPair(
            round_num=5,
            agent_id="player_kira",
            character_name="Sgt Kira",
            declaration={
                "action": {
                    "action_type": "support",
                    "intent": "Provide covering fire for the extraction team",
                    "description": "",
                }
            },
            resolution={
                "narration": "Kira opens fire to cover the team.",
                "effects": {
                    "damage": {"target": "tgt_001", "dealt": 7},
                    "conditions": [{"condition": "Suppressed"}],
                },
            },
        )
        mismatches = detect_mismatches(pair)
        type_a = [m for m in mismatches if m.mismatch_type == MismatchType.TYPE_A]
        assert len(type_a) == 1

    def test_investigate_action_type_still_skipped(self):
        """action_type='investigate' should still be skipped."""
        pair = ActionPair(
            round_num=5,
            agent_id="player_kira",
            character_name="Sgt Kira",
            declaration={
                "action": {
                    "action_type": "investigate",
                    "intent": "Search the area",
                    "description": "",
                }
            },
            resolution={
                "narration": "Kira searches the area.",
                "effects": {"damage": {"target": "tgt_001", "dealt": 10}},
            },
        )
        mismatches = detect_mismatches(pair)
        assert len(mismatches) == 0


class TestConditionsPlusDamage:
    """Tests for conditions + damage tracking (Change D)."""

    def test_conditions_plus_damage_tracked(self):
        """Outcome with both damage and conditions should set has_conditions_and_damage."""
        resolution = {
            "effects": {
                "damage": {"target": "tgt_001", "dealt": 6},
                "conditions": [{"condition": "Suppressed"}],
            }
        }
        outcome = classify_outcome(resolution)
        assert outcome.has_conditions_and_damage is True

    def test_damage_only_not_flagged(self):
        """Outcome with only damage should NOT set has_conditions_and_damage."""
        resolution = {
            "effects": {
                "damage": {"target": "tgt_001", "dealt": 10},
            }
        }
        outcome = classify_outcome(resolution)
        assert outcome.has_conditions_and_damage is False

    def test_conditions_only_not_flagged(self):
        """Outcome with only conditions should NOT set has_conditions_and_damage."""
        resolution = {
            "effects": {
                "conditions": [{"condition": "Pinned"}],
            }
        }
        outcome = classify_outcome(resolution)
        assert outcome.has_conditions_and_damage is False


class TestConditionNameParsing:
    """Tests for condition name extraction from colon-delimited strings (Change E)."""

    def test_condition_name_from_colon_string(self):
        """'Suppressed: pinned by covering fire' should extract 'Suppressed'."""
        resolution = {
            "effects": {
                "conditions": [
                    {"condition": "Suppressed: pinned by covering fire", "target": "tgt_001"},
                ],
            }
        }
        outcome = classify_outcome(resolution)
        assert outcome.conditions_applied == ["Suppressed"]

    def test_condition_name_without_colon(self):
        """Plain condition name should be unchanged."""
        resolution = {
            "effects": {
                "conditions": [{"condition": "Pinned", "target": "tgt_001"}],
            }
        }
        outcome = classify_outcome(resolution)
        assert outcome.conditions_applied == ["Pinned"]

    def test_condition_name_from_string_entry(self):
        """String condition entries should also be parsed."""
        resolution = {
            "effects": {
                "conditions": ["Restrained: grappled to ground"],
            }
        }
        outcome = classify_outcome(resolution)
        assert outcome.conditions_applied == ["Restrained"]


# ============================================================================
# Config Generator Tests (import and verify)
# ============================================================================

class TestConfigGenerator:
    """Tests for generate_multi_llm_configs.py functions."""

    def test_generate_config_updates_all_agents(self):
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from generate_multi_llm_configs import generate_config

        base = {
            "session_name": "test_experiment",
            "agents": {
                "dm": {"llm": {"provider": "openai", "model": "gpt-5-mini", "temperature": 1.0}},
                "players": [
                    {"name": "Alice", "llm": {"provider": "openai", "model": "gpt-5-mini", "temperature": 1.0}},
                    {"name": "Bob", "llm": {"provider": "openai", "model": "gpt-5-mini", "temperature": 1.0}},
                ],
            },
        }
        result = generate_config(base, "anthropic", "claude-sonnet-4-5")

        assert result["agents"]["dm"]["llm"]["provider"] == "anthropic"
        assert result["agents"]["dm"]["llm"]["model"] == "claude-sonnet-4-5"
        for player in result["agents"]["players"]:
            assert player["llm"]["provider"] == "anthropic"
            assert player["llm"]["model"] == "claude-sonnet-4-5"
        assert "anthropic" in result["session_name"]

    def test_generate_config_preserves_base(self):
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from generate_multi_llm_configs import generate_config

        base = {
            "session_name": "test",
            "max_turns": 3,
            "agents": {
                "dm": {"llm": {"provider": "openai", "model": "gpt-5-mini"}},
                "players": [],
            },
        }
        result = generate_config(base, "anthropic", "claude-sonnet-4-5")

        # Base should be unchanged
        assert base["agents"]["dm"]["llm"]["provider"] == "openai"
        assert base["session_name"] == "test"
        # Result should have new values
        assert result["max_turns"] == 3

    def test_sanitize_model_name(self):
        from generate_multi_llm_configs import sanitize_model_name
        assert sanitize_model_name("gpt-5-mini") == "gpt5mini"
        assert sanitize_model_name("claude-sonnet-4-5") == "claudesonnet45"
        assert sanitize_model_name("o1-preview") == "o1preview"
