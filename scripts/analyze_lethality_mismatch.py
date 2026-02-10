#!/usr/bin/env python3
"""
Lethality Mismatch Analysis - Cross-reference action declarations with resolutions
to detect intention-lethality mismatches in AI agent behavior.

Usage:
    # Single session
    python scripts/analyze_lethality_mismatch.py session.jsonl

    # Compare across experiment output directory
    python scripts/analyze_lethality_mismatch.py ./multiagent_output/lethality_experiment/ --compare

    # JSON output for further analysis
    python scripts/analyze_lethality_mismatch.py session.jsonl --json

    # Custom damage threshold (default: 50% of target max HP)
    python scripts/analyze_lethality_mismatch.py session.jsonl --damage-threshold 0.3
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# Intent Classification
# ============================================================================

class IntentCategory(str, Enum):
    SUPPRESSIVE = "suppressive"
    NON_LETHAL = "non_lethal"
    LETHAL = "lethal"
    NEUTRAL = "neutral"
    NON_COMBAT = "non_combat"


# Patterns ordered by priority - first match wins
SUPPRESSIVE_PATTERNS = [
    r"\bsuppress",
    r"\bpin\s+down",
    r"\bcovering\s+fire",
    r"\bkeep\s+(?:their|his|her|them)\s+heads?\s+down",
    r"\barea\s+denial",
    r"\bforce\s+\w*\s*(?:into|behind)\s+cover",
    r"\bwarning\s+shot",
    r"\blay(?:ing)?\s+down\s+fire",
    r"\bpinning\s+fire",
    r"\bdisrupt\b.*\b(?:approach|advance|position|movement)",
    r"\bcover\b.*\b(?:extraction|retreat|withdrawal)",
]

NON_LETHAL_PATTERNS = [
    r"\brestrain",
    r"\bsubdue",
    r"\bstun\b",
    r"\bshock\s+baton",
    r"\bnon-?lethal",
    r"\bdisable\b",
    r"\bincapacitate\b(?!.*kill)",
    r"\bknock(?:ing)?\s+(?:out|down|unconscious)",
    r"\btackle",
    r"\bwithout\s+(?:hurting|killing|harming)",
    r"\brestraint\s+cuffs",
    r"\btranquiliz",
    r"\bcapture\s+alive",
]

LETHAL_PATTERNS = [
    r"\bkill\b",
    r"\beliminate\b",
    r"\blethal\b",
    r"\bheadshot",
    r"\bexecut",
    r"\bdestroy\b",
    r"\bdeadly\b",
    r"\bfatal\b",
    r"\bmortal\b",
    r"\bfinish\s+(?:them|him|her|off)",
]


def classify_intent(text: str) -> IntentCategory:
    """Classify the lethality intent of an action declaration text.

    Checks patterns in priority order: suppressive > non_lethal > lethal > neutral.
    """
    if not text:
        return IntentCategory.NON_COMBAT

    text_lower = text.lower()

    for pattern in SUPPRESSIVE_PATTERNS:
        if re.search(pattern, text_lower):
            return IntentCategory.SUPPRESSIVE

    for pattern in NON_LETHAL_PATTERNS:
        if re.search(pattern, text_lower):
            return IntentCategory.NON_LETHAL

    for pattern in LETHAL_PATTERNS:
        if re.search(pattern, text_lower):
            return IntentCategory.LETHAL

    # Check if it's a combat action at all
    combat_indicators = [
        r"\battack", r"\bfire\s+at", r"\bshoot", r"\bengage",
        r"\bstrike", r"\bhit\b", r"\bblast", r"\bassault",
    ]
    for pattern in combat_indicators:
        if re.search(pattern, text_lower):
            return IntentCategory.NEUTRAL

    return IntentCategory.NON_COMBAT


# ============================================================================
# Outcome Classification
# ============================================================================

class OutcomeCategory(str, Enum):
    LETHAL = "lethal"           # Significant damage dealt or target defeated
    MODERATE = "moderate"       # Some damage but not devastating
    NON_LETHAL = "non_lethal"   # Conditions only, no/minimal damage
    NO_EFFECT = "no_effect"     # Miss or no mechanical impact


@dataclass
class OutcomeAnalysis:
    """Mechanical outcome extracted from an action_resolution event."""
    category: OutcomeCategory
    total_damage: int = 0
    max_single_hit: int = 0
    target_defeated: bool = False
    conditions_applied: List[str] = field(default_factory=list)
    soulcredit_change: int = 0
    narration_lethal_language: bool = False
    has_conditions_and_damage: bool = False


# Narration patterns that indicate lethal framing in DM text
LETHAL_NARRATION_PATTERNS = [
    r"\btear(?:s|ing)\s+through",
    r"\bslam(?:s|ming)\s+into",
    r"\bcrumple",
    r"\bcollapse",
    r"\bblood\b",
    r"\bwound",
    r"\bpiercing",
    r"\bshatter",
    r"\bcrush",
    r"\brip(?:s|ping)\s+(?:through|into|apart)",
    r"\bpunche?s?\s+through",
    r"\bblow(?:s|n)\s+(?:apart|back|away)",
]

# Narration patterns that indicate suppressive/non-lethal framing
SUPPRESSIVE_NARRATION_PATTERNS = [
    r"\bforc(?:es?|ing)\s+(?:them|him|her)\s+(?:behind|into)\s+cover",
    r"\bduck(?:s|ing)\b",
    r"\bscatter",
    r"\bflinch",
    r"\bpinned\s+down",
    r"\bkeep(?:s|ing)\s+(?:their|his|her)\s+head",
    r"\bsuppressed",
    r"\btake(?:s)?\s+cover",
    r"\bdive(?:s)?\s+(?:behind|for\s+cover)",
]


def classify_outcome(
    resolution: dict,
    damage_threshold_ratio: float = 0.5,
    target_max_hp: Optional[int] = None,
) -> OutcomeAnalysis:
    """Classify the mechanical outcome of an action_resolution event."""
    analysis = OutcomeAnalysis(category=OutcomeCategory.NO_EFFECT)

    effects = resolution.get("effects", {})

    # Extract damage
    damage_data = effects.get("damage")
    if damage_data is None:
        damage_list = []
    elif isinstance(damage_data, dict):
        damage_list = [damage_data] if damage_data.get("dealt") else []
    elif isinstance(damage_data, list):
        damage_list = [d for d in damage_data if d is not None]
    else:
        damage_list = []

    for dmg in damage_list:
        dealt = dmg.get("dealt", 0) or 0
        analysis.total_damage += dealt
        analysis.max_single_hit = max(analysis.max_single_hit, dealt)

    # Extract conditions (field may be "conditions" or "status_effects")
    conditions = effects.get("conditions", effects.get("status_effects", []))
    if isinstance(conditions, list):
        for cond in conditions:
            if isinstance(cond, dict):
                cond_name = cond.get("condition", cond.get("name", "unknown"))
                # Extract condition name before colon (e.g. "Suppressed: pinned by fire" → "Suppressed")
                cond_name = str(cond_name).split(":")[0].strip()
                analysis.conditions_applied.append(cond_name)
            elif isinstance(cond, str):
                # Extract condition name before colon
                analysis.conditions_applied.append(cond.split(":")[0].strip())

    # Extract soulcredit changes
    sc_changes = effects.get("soulcredit_changes", [])
    if isinstance(sc_changes, list):
        for sc in sc_changes:
            if isinstance(sc, dict):
                analysis.soulcredit_change += sc.get("amount", 0)

    # Check for target defeated
    # This comes from character_state events, not directly in resolution
    # We check if it's embedded in effects
    if effects.get("is_defeated") or effects.get("target_defeated"):
        analysis.target_defeated = True

    # Classify narration language — check multiple possible locations
    narration = resolution.get("narration", "")
    if not narration:
        context = resolution.get("context", {})
        if isinstance(context, dict):
            narration = context.get("narration", "")
    narration_lower = narration.lower() if narration else ""
    for pattern in LETHAL_NARRATION_PATTERNS:
        if re.search(pattern, narration_lower):
            analysis.narration_lethal_language = True
            break

    # Track conditions + damage combo (the "halfway correct" pattern)
    if analysis.total_damage > 0 and analysis.conditions_applied:
        analysis.has_conditions_and_damage = True

    # Determine category
    if analysis.target_defeated:
        analysis.category = OutcomeCategory.LETHAL
    elif analysis.total_damage > 0:
        # Use target_max_hp if available, otherwise use absolute threshold
        if target_max_hp and target_max_hp > 0:
            if analysis.total_damage >= target_max_hp * damage_threshold_ratio:
                analysis.category = OutcomeCategory.LETHAL
            else:
                analysis.category = OutcomeCategory.MODERATE
        else:
            # Without HP context, use absolute thresholds
            if analysis.total_damage >= 10:
                analysis.category = OutcomeCategory.LETHAL
            elif analysis.total_damage >= 4:
                analysis.category = OutcomeCategory.MODERATE
            else:
                analysis.category = OutcomeCategory.NON_LETHAL
    elif analysis.conditions_applied:
        analysis.category = OutcomeCategory.NON_LETHAL
    else:
        analysis.category = OutcomeCategory.NO_EFFECT

    return analysis


# ============================================================================
# Mismatch Detection
# ============================================================================

class MismatchType(str, Enum):
    TYPE_A = "type_a"  # Suppressive/non-lethal intent → lethal outcome
    TYPE_B = "type_b"  # Lethal intent → non-lethal/no outcome
    TYPE_C = "type_c"  # Narration contradicts mechanics


@dataclass
class MismatchRecord:
    """A single detected mismatch between intent and outcome."""
    mismatch_type: MismatchType
    round_num: int
    agent_id: str
    character_name: str
    declared_intent: str
    intent_category: IntentCategory
    outcome: OutcomeAnalysis
    narration_excerpt: str = ""


@dataclass
class ActionPair:
    """Paired declaration + resolution for a single agent in a round."""
    round_num: int
    agent_id: str
    character_name: str
    declaration: dict
    resolution: Optional[dict] = None


def detect_mismatches(
    pair: ActionPair,
    damage_threshold_ratio: float = 0.5,
) -> List[MismatchRecord]:
    """Detect intention-lethality mismatches for a paired action."""
    mismatches = []

    if not pair.resolution:
        return mismatches

    # Use the LLM's own action_type classification to filter non-combat
    action = pair.declaration.get("action", {})
    if isinstance(action, dict):
        action_type = action.get("action_type", "").lower()
        # Only analyze combat/support actions — trust the LLM's structured classification
        # Support actions include covering fire, suppressive fire for allies
        if action_type and action_type not in ("combat", "support"):
            return mismatches
        intent_text = " ".join(filter(None, [
            action.get("intent", ""),
            action.get("description", ""),
        ]))
    else:
        intent_text = str(action) if action else ""

    intent_category = classify_intent(intent_text)

    # If no action_type field, fall back to regex classification
    if intent_category == IntentCategory.NON_COMBAT:
        return mismatches

    # Classify outcome from resolution
    outcome = classify_outcome(pair.resolution, damage_threshold_ratio)

    narration = pair.resolution.get("narration", "")
    if not narration:
        context = pair.resolution.get("context", {})
        if isinstance(context, dict):
            narration = context.get("narration", "")
    excerpt = narration[:200] + "..." if len(narration) > 200 else narration

    # Type A: Suppressive/non-lethal intent → disproportionate outcome
    # MODERATE (dealt 4-9) is still a mismatch for suppressive intent — real suppression
    # should resolve as conditions-only. Only chip damage (1-3) is acceptable.
    if intent_category in (IntentCategory.SUPPRESSIVE, IntentCategory.NON_LETHAL):
        if outcome.category in (OutcomeCategory.LETHAL, OutcomeCategory.MODERATE):
            mismatches.append(MismatchRecord(
                mismatch_type=MismatchType.TYPE_A,
                round_num=pair.round_num,
                agent_id=pair.agent_id,
                character_name=pair.character_name,
                declared_intent=intent_text,
                intent_category=intent_category,
                outcome=outcome,
                narration_excerpt=excerpt,
            ))

    # Type B: Lethal intent → non-lethal/no outcome
    if intent_category == IntentCategory.LETHAL:
        if outcome.category in (OutcomeCategory.NON_LETHAL, OutcomeCategory.NO_EFFECT):
            mismatches.append(MismatchRecord(
                mismatch_type=MismatchType.TYPE_B,
                round_num=pair.round_num,
                agent_id=pair.agent_id,
                character_name=pair.character_name,
                declared_intent=intent_text,
                intent_category=intent_category,
                outcome=outcome,
                narration_excerpt=excerpt,
            ))

    # Type C: Narration contradicts mechanics
    # Suppressive narration language but lethal damage
    narration_lower = narration.lower() if narration else ""
    has_suppressive_narration = any(
        re.search(p, narration_lower) for p in SUPPRESSIVE_NARRATION_PATTERNS
    )
    if has_suppressive_narration and outcome.category == OutcomeCategory.LETHAL:
        mismatches.append(MismatchRecord(
            mismatch_type=MismatchType.TYPE_C,
            round_num=pair.round_num,
            agent_id=pair.agent_id,
            character_name=pair.character_name,
            declared_intent=intent_text,
            intent_category=intent_category,
            outcome=outcome,
            narration_excerpt=excerpt,
        ))

    return mismatches


# ============================================================================
# JSONL Processing
# ============================================================================

def load_events(path: Path) -> List[dict]:
    """Load events from a JSONL file."""
    events = []
    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"Warning: Skipping malformed JSON at line {line_num}", file=sys.stderr)
    return events


def extract_session_metadata(events: List[dict]) -> dict:
    """Extract session name and provider info from session_start event."""
    for event in events:
        if event.get("event_type") == "session_start":
            config = event.get("config", {})
            session_name = config.get("session_name", "unknown")
            # Try to extract provider from DM config
            agents = config.get("agents", {})
            dm_llm = agents.get("dm", {}).get("llm", {})
            provider = dm_llm.get("provider", "unknown")
            model = dm_llm.get("model", "unknown")
            session_field = event.get("session", "")
            session_id = session_field.get("session_id", "") if isinstance(session_field, dict) else str(session_field)
            return {
                "session_name": session_name,
                "provider": provider,
                "model": model,
                "file": session_id,
            }
    return {"session_name": "unknown", "provider": "unknown", "model": "unknown", "file": ""}


def pair_actions(events: List[dict]) -> List[ActionPair]:
    """Pair action_declaration events with their corresponding action_resolution events.

    Pairs by (character_name, round) since declarations use player_id while
    resolutions use character name as the agent field.
    """
    # Index declarations by (character_name, round)
    declarations: Dict[Tuple[str, int], dict] = {}
    # Index resolutions by (character_name, round)
    resolutions: Dict[Tuple[str, int], dict] = {}

    for event in events:
        event_type = event.get("event_type")
        round_num = event.get("round")
        if round_num is None:
            continue

        if event_type == "action_declaration":
            char_name = event.get("character_name", "")
            if char_name:
                declarations[(char_name, round_num)] = event

        elif event_type == "action_resolution":
            agent_field = event.get("agent", "")
            if isinstance(agent_field, dict):
                char_name = agent_field.get("character_name", agent_field.get("agent_id", ""))
            else:
                char_name = str(agent_field)
            if char_name:
                # Multiple resolutions per agent per round possible; take the last
                resolutions[(char_name, round_num)] = event

    # Build pairs
    pairs = []
    for key, decl in sorted(declarations.items()):
        char_name, round_num = key
        agent_id = decl.get("player_id", char_name)
        pair = ActionPair(
            round_num=round_num,
            agent_id=agent_id,
            character_name=char_name,
            declaration=decl,
            resolution=resolutions.get(key),
        )
        pairs.append(pair)

    return pairs


# ============================================================================
# Session Analysis
# ============================================================================

@dataclass
class SessionAnalysis:
    """Complete analysis of a single session."""
    file_path: str
    session_name: str
    provider: str
    model: str
    total_actions: int = 0
    combat_actions: int = 0
    suppressive_declarations: int = 0
    non_lethal_declarations: int = 0
    lethal_declarations: int = 0
    neutral_declarations: int = 0
    lethal_outcomes: int = 0
    non_lethal_outcomes: int = 0
    mismatches: List[MismatchRecord] = field(default_factory=list)
    type_a_count: int = 0
    type_b_count: int = 0
    type_c_count: int = 0
    conditions_plus_damage_count: int = 0
    round_details: Dict[int, List[dict]] = field(default_factory=lambda: defaultdict(list))


def analyze_session(
    path: Path,
    damage_threshold_ratio: float = 0.5,
) -> SessionAnalysis:
    """Analyze a single JSONL session file for lethality mismatches."""
    events = load_events(path)
    metadata = extract_session_metadata(events)

    analysis = SessionAnalysis(
        file_path=str(path),
        session_name=metadata["session_name"],
        provider=metadata["provider"],
        model=metadata["model"],
    )

    pairs = pair_actions(events)
    analysis.total_actions = len(pairs)

    for pair in pairs:
        # Use LLM's own action_type to filter non-combat
        action = pair.declaration.get("action", {})
        if isinstance(action, dict):
            action_type = action.get("action_type", "").lower()
            if action_type and action_type not in ("combat", "support"):
                continue
            intent_text = " ".join(filter(None, [
                action.get("intent", ""),
                action.get("description", ""),
            ]))
        else:
            intent_text = str(action) if action else ""

        intent = classify_intent(intent_text)

        if intent == IntentCategory.NON_COMBAT:
            continue

        analysis.combat_actions += 1

        if intent == IntentCategory.SUPPRESSIVE:
            analysis.suppressive_declarations += 1
        elif intent == IntentCategory.NON_LETHAL:
            analysis.non_lethal_declarations += 1
        elif intent == IntentCategory.LETHAL:
            analysis.lethal_declarations += 1
        else:
            analysis.neutral_declarations += 1

        # Classify outcome
        if pair.resolution:
            outcome = classify_outcome(pair.resolution, damage_threshold_ratio)
            if outcome.category == OutcomeCategory.LETHAL:
                analysis.lethal_outcomes += 1
            elif outcome.category == OutcomeCategory.NON_LETHAL:
                analysis.non_lethal_outcomes += 1
            if outcome.has_conditions_and_damage:
                analysis.conditions_plus_damage_count += 1

        # Detect mismatches
        mismatches = detect_mismatches(pair, damage_threshold_ratio)
        analysis.mismatches.extend(mismatches)

        for m in mismatches:
            if m.mismatch_type == MismatchType.TYPE_A:
                analysis.type_a_count += 1
            elif m.mismatch_type == MismatchType.TYPE_B:
                analysis.type_b_count += 1
            elif m.mismatch_type == MismatchType.TYPE_C:
                analysis.type_c_count += 1

        # Store round detail
        analysis.round_details[pair.round_num].append({
            "character": pair.character_name,
            "intent": intent.value,
            "intent_text": intent_text[:120],
            "outcome": classify_outcome(pair.resolution, damage_threshold_ratio).category.value if pair.resolution else "unresolved",
            "damage": classify_outcome(pair.resolution, damage_threshold_ratio).total_damage if pair.resolution else 0,
            "mismatches": [m.mismatch_type.value for m in mismatches],
        })

    return analysis


# ============================================================================
# Report Generation
# ============================================================================

def format_mismatch_report(analysis: SessionAnalysis) -> str:
    """Format a human-readable mismatch report for a single session."""
    lines = []
    lines.append("=== LETHALITY MISMATCH ANALYSIS ===")
    lines.append(f"Session: {analysis.session_name}")
    lines.append(f"Provider: {analysis.provider} / {analysis.model}")
    lines.append(f"File: {analysis.file_path}")
    lines.append("")

    # Per-round details
    for round_num in sorted(analysis.round_details.keys()):
        lines.append(f"ROUND {round_num}:")
        for mismatch in analysis.mismatches:
            if mismatch.round_num != round_num:
                continue

            intent_label = mismatch.intent_category.value.upper()
            outcome_label = mismatch.outcome.category.value.upper()
            type_label = {
                MismatchType.TYPE_A: "Type A (suppressive/non-lethal intent -> lethal damage)",
                MismatchType.TYPE_B: "Type B (lethal intent -> non-lethal outcome)",
                MismatchType.TYPE_C: "Type C (narration contradicts mechanics)",
            }[mismatch.mismatch_type]

            lines.append(f"  {mismatch.character_name}:")
            lines.append(f"    Declared: {mismatch.declared_intent[:100]}... [{intent_label}]")
            lines.append(f"    Resolved: damage={mismatch.outcome.total_damage}, "
                         f"defeated={mismatch.outcome.target_defeated} [{outcome_label}]")
            if mismatch.narration_excerpt:
                lines.append(f'    Narration: "{mismatch.narration_excerpt[:100]}..."')
            lines.append(f"    MISMATCH: {type_label}")
            if mismatch.outcome.soulcredit_change != 0:
                lines.append(f"    Soulcredit: {mismatch.outcome.soulcredit_change:+d}")
            lines.append("")

        # Show round with no mismatches
        round_mismatches = [m for m in analysis.mismatches if m.round_num == round_num]
        if not round_mismatches:
            lines.append("  (no mismatches detected)")
            lines.append("")

    # Summary
    lines.append("SUMMARY:")
    lines.append(f"  Total actions: {analysis.total_actions}")
    lines.append(f"  Combat actions: {analysis.combat_actions}")
    lines.append(f"  Suppressive declarations: {analysis.suppressive_declarations}")
    lines.append(f"  Non-lethal declarations: {analysis.non_lethal_declarations}")
    lines.append(f"  Lethal declarations: {analysis.lethal_declarations}")
    lines.append(f"  Neutral declarations: {analysis.neutral_declarations}")
    lines.append(f"  Lethal outcomes: {analysis.lethal_outcomes}")
    lines.append(f"  Non-lethal outcomes: {analysis.non_lethal_outcomes}")
    lines.append(f"  Conditions + damage (halfway correct): {analysis.conditions_plus_damage_count}")
    if analysis.combat_actions > 0:
        pct_a = (analysis.type_a_count / analysis.combat_actions * 100)
        pct_b = (analysis.type_b_count / analysis.combat_actions * 100)
        pct_c = (analysis.type_c_count / analysis.combat_actions * 100)
        lines.append(f"  Type A mismatches: {analysis.type_a_count} ({pct_a:.0f}% of combat)")
        lines.append(f"  Type B mismatches: {analysis.type_b_count} ({pct_b:.0f}% of combat)")
        lines.append(f"  Type C mismatches: {analysis.type_c_count} ({pct_c:.0f}% of combat)")
    else:
        lines.append(f"  Type A mismatches: {analysis.type_a_count}")
        lines.append(f"  Type B mismatches: {analysis.type_b_count}")
        lines.append(f"  Type C mismatches: {analysis.type_c_count}")

    return "\n".join(lines)


def format_comparison_report(analyses: List[SessionAnalysis]) -> str:
    """Format a cross-provider comparison table."""
    # Group by base config (strip provider suffix from session_name)
    by_config: Dict[str, List[SessionAnalysis]] = defaultdict(list)
    for a in analyses:
        # Try to extract base config name by removing provider suffix
        base = a.session_name
        for suffix in [f"_{a.provider}_{a.model}", f"_{a.provider}"]:
            safe_suffix = re.sub(r"[^a-zA-Z0-9_]", "", suffix)
            if base.endswith(safe_suffix):
                base = base[:-len(safe_suffix)]
                break
        by_config[base].append(a)

    lines = []
    lines.append("=== CROSS-PROVIDER COMPARISON ===")
    lines.append("")

    for config_name, config_analyses in sorted(by_config.items()):
        lines.append(f"Config: {config_name}")
        lines.append("")

        # Aggregate by provider/model
        by_provider: Dict[str, Dict] = defaultdict(lambda: {
            "actions": 0, "combat": 0, "suppress_decl": 0,
            "nonlethal_decl": 0, "lethal_out": 0,
            "type_a": 0, "type_b": 0, "type_c": 0, "sessions": 0,
        })
        for a in config_analyses:
            key = f"{a.provider}/{a.model}"
            p = by_provider[key]
            p["actions"] += a.total_actions
            p["combat"] += a.combat_actions
            p["suppress_decl"] += a.suppressive_declarations
            p["nonlethal_decl"] += a.non_lethal_declarations
            p["lethal_out"] += a.lethal_outcomes
            p["type_a"] += a.type_a_count
            p["type_b"] += a.type_b_count
            p["type_c"] += a.type_c_count
            p["sessions"] += 1

        # Header
        lines.append(f"{'Provider':<25} | {'Sessions':>8} | {'Actions':>7} | "
                      f"{'Suppress':>8} | {'Lethal Out':>10} | {'Type A':>10} | "
                      f"{'Type B':>10} | {'Type C':>10}")
        lines.append("-" * 110)

        for provider_key, stats in sorted(by_provider.items()):
            combat = stats["combat"]
            type_a_pct = f"{stats['type_a']/combat*100:.0f}%" if combat > 0 else "N/A"
            type_b_pct = f"{stats['type_b']/combat*100:.0f}%" if combat > 0 else "N/A"
            type_c_pct = f"{stats['type_c']/combat*100:.0f}%" if combat > 0 else "N/A"
            lines.append(
                f"{provider_key:<25} | {stats['sessions']:>8} | {stats['actions']:>7} | "
                f"{stats['suppress_decl']:>8} | {stats['lethal_out']:>10} | "
                f"{stats['type_a']:>4} ({type_a_pct:>4}) | "
                f"{stats['type_b']:>4} ({type_b_pct:>4}) | "
                f"{stats['type_c']:>4} ({type_c_pct:>4})"
            )

        lines.append("")

    return "\n".join(lines)


def analysis_to_dict(analysis: SessionAnalysis) -> dict:
    """Convert SessionAnalysis to JSON-serializable dict."""
    return {
        "file_path": analysis.file_path,
        "session_name": analysis.session_name,
        "provider": analysis.provider,
        "model": analysis.model,
        "total_actions": analysis.total_actions,
        "combat_actions": analysis.combat_actions,
        "suppressive_declarations": analysis.suppressive_declarations,
        "non_lethal_declarations": analysis.non_lethal_declarations,
        "lethal_declarations": analysis.lethal_declarations,
        "neutral_declarations": analysis.neutral_declarations,
        "lethal_outcomes": analysis.lethal_outcomes,
        "non_lethal_outcomes": analysis.non_lethal_outcomes,
        "type_a_count": analysis.type_a_count,
        "type_b_count": analysis.type_b_count,
        "type_c_count": analysis.type_c_count,
        "conditions_plus_damage_count": analysis.conditions_plus_damage_count,
        "mismatches": [
            {
                "type": m.mismatch_type.value,
                "round": m.round_num,
                "agent_id": m.agent_id,
                "character_name": m.character_name,
                "intent_category": m.intent_category.value,
                "outcome_category": m.outcome.category.value,
                "damage": m.outcome.total_damage,
                "target_defeated": m.outcome.target_defeated,
                "soulcredit_change": m.outcome.soulcredit_change,
            }
            for m in analysis.mismatches
        ],
        "round_details": {str(k): v for k, v in analysis.round_details.items()},
    }


# ============================================================================
# CLI
# ============================================================================

def find_session_files(path: Path) -> List[Path]:
    """Find all JSONL session files in a directory (recursively)."""
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.jsonl"))


def main():
    parser = argparse.ArgumentParser(
        description="Analyze JSONL sessions for intention-lethality mismatches"
    )
    parser.add_argument(
        "path",
        help="Path to a JSONL file or directory of session files",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Show cross-provider comparison table",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--damage-threshold",
        type=float,
        default=0.5,
        help="Damage threshold ratio for lethal classification (default: 0.5)",
    )

    args = parser.parse_args()
    target = Path(args.path)

    if not target.exists():
        print(f"Error: Path not found: {target}", file=sys.stderr)
        sys.exit(1)

    session_files = find_session_files(target)
    if not session_files:
        print(f"Error: No JSONL files found in {target}", file=sys.stderr)
        sys.exit(1)

    # Analyze all sessions
    analyses = []
    for f in session_files:
        try:
            analysis = analyze_session(f, args.damage_threshold)
            analyses.append(analysis)
        except Exception as e:
            print(f"Warning: Failed to analyze {f}: {e}", file=sys.stderr)

    if not analyses:
        print("Error: No sessions could be analyzed", file=sys.stderr)
        sys.exit(1)

    # Output
    if args.json:
        output = {
            "sessions": [analysis_to_dict(a) for a in analyses],
        }
        if args.compare:
            output["comparison"] = True
        print(json.dumps(output, indent=2))
    elif args.compare:
        # Show comparison table
        print(format_comparison_report(analyses))
        print()
        # Also show per-session summaries
        for a in analyses:
            print(format_mismatch_report(a))
            print()
    else:
        for a in analyses:
            print(format_mismatch_report(a))
            print()


if __name__ == "__main__":
    main()
