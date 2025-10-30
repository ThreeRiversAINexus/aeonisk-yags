"""
Parse narrative outcomes to extract mechanical state changes.
Automatically advance clocks and void based on DM narration.

Phase 2 Migration: Now supports both structured output (ActionResolution objects)
and legacy text parsing for backward compatibility.
"""

import re
from typing import Dict, List, Tuple, Optional, Any, Union
import logging

logger = logging.getLogger(__name__)


def extract_from_structured_resolution(resolution_obj) -> Dict[str, Any]:
    """
    Extract state changes from a structured ActionResolution object.

    Phase 2 Migration: Converts Pydantic ActionResolution to legacy state_changes dict
    for backward compatibility with existing code.

    Args:
        resolution_obj: ActionResolution instance from structured output

    Returns:
        Dict with state changes (same format as parse_state_changes)
    """
    try:
        from .schemas.action_resolution import ActionResolution
    except ImportError:
        logger.error("Failed to import ActionResolution schema")
        return {
            'clock_triggers': [],
            'void_change': 0,
            'void_reasons': [],
            'void_target_character': None,
            'conditions': [],
            'notes': [],
            'position_change': None,
            'soulcredit_change': 0,
            'soulcredit_reasons': []
        }

    if not isinstance(resolution_obj, ActionResolution):
        logger.warning(f"extract_from_structured_resolution called with non-ActionResolution: {type(resolution_obj)}")
        return None

    logger.debug("Extracting state changes from structured ActionResolution")

    # Extract void changes
    void_change = sum(vc.amount for vc in resolution_obj.effects.void_changes)
    void_reasons = [vc.reason for vc in resolution_obj.effects.void_changes]
    void_target_character = resolution_obj.effects.void_changes[0].character_name if resolution_obj.effects.void_changes else None

    # Extract soulcredit changes
    soulcredit_change = sum(sc.amount for sc in resolution_obj.effects.soulcredit_changes)
    soulcredit_reasons = [sc.reason for sc in resolution_obj.effects.soulcredit_changes]

    # Extract clock updates
    # Note: Legacy format expects (clock_name, ticks, reason, source)
    clock_triggers = [
        (cu.clock_name, cu.ticks, cu.reason, 'structured_output')
        for cu in resolution_obj.effects.clock_updates
    ]

    # Extract conditions
    conditions = [
        {
            'type': cond.name,
            'penalty': cond.penalty,
            'duration': cond.duration,
            'description': cond.description
        }
        for cond in resolution_obj.effects.conditions
    ]

    # Extract position changes
    position_change = None
    if resolution_obj.effects.position_changes:
        # Take the first position change (usually only one per action)
        pc = resolution_obj.effects.position_changes[0]
        position_change = {
            'character_name': pc.character_name,
            'new_position': pc.new_position.value,
            'reason': pc.reason
        }

    # Build state_changes dict (legacy format)
    state_changes = {
        'clock_triggers': clock_triggers,
        'void_change': void_change,
        'void_reasons': void_reasons,
        'void_target_character': void_target_character,
        'void_source': 'structured_output',  # Mark as coming from structured output
        'llm_compliance_issue': None,  # Structured output is always compliant
        'conditions': conditions,
        'notes': resolution_obj.effects.notes,
        'position_change': position_change,
        'soulcredit_change': soulcredit_change,
        'soulcredit_reasons': soulcredit_reasons
    }

    logger.debug(f"Extracted from structured: void={void_change}, clocks={len(clock_triggers)}, conditions={len(conditions)}")

    return state_changes


def parse_soulcredit_markers(narration: str) -> Tuple[int, str, str]:
    """
    Parse explicit soulcredit markers from LLM narration.

    Format: ⚖️ Soulcredit: +X (reason) or -X (reason)

    Args:
        narration: DM's narrative text

    Returns:
        Tuple of (soulcredit_delta, reason, source)
        source is "dm_explicit" if marker found, "" otherwise
    """
    # Look for lines like: ⚖️ Soulcredit: -2 (created Hollow Seed)
    sc_pattern = r'⚖️\s*[Ss]oulcredit:\s*([+-]?\d+)\s*(?:\(([^)]+)\))?'

    match = re.search(sc_pattern, narration)
    if match:
        delta = int(match.group(1))
        reason = match.group(2).strip() if match.group(2) else "Soulcredit change"
        logger.debug(f"Parsed soulcredit marker: {delta:+d} ({reason})")
        return (delta, reason, "dm_explicit")

    return (0, "", "")


def parse_explicit_void_markers(narration: str, expected_target_id: str = None) -> Tuple[int, List[str], str, Optional[str], Optional[str]]:
    """
    Parse explicit void markers from LLM narration and check compliance.

    Format: ⚫ Void: +X (reason) or ⚫ Void (tgt_xxxx): +X (reason)

    Args:
        narration: DM's narrative text
        expected_target_id: The target ID that was provided in the prompt (for compliance checking)

    Returns:
        Tuple of (void_delta, reasons_list, source, target_identifier, compliance_issue)
        source is "dm_explicit" if marker found, "" otherwise
        target_identifier is None if targeting self, otherwise the target ID or character name
        compliance_issue is None if compliant, otherwise a string describing the issue
    """
    # Look for lines like: ⚫ Void: +1 (ritual backfire)
    # or: ⚫ Void (tgt_xxxx): -3 (powerful purification)
    # or: ⚫ Void (Character Name): -3 (non-compliant, but we handle it)
    void_pattern = r'⚫\s*[Vv]oid(?:\s*\(([^)]+)\))?:\s*([+-]?\d+)\s*(?:\(([^)]+)\))?'

    match = re.search(void_pattern, narration)
    if match:
        target_identifier = match.group(1).strip() if match.group(1) else None
        delta = int(match.group(2))
        reason = match.group(3).strip() if match.group(3) else "Void change"

        # Compliance checking
        compliance_issue = None
        if expected_target_id and target_identifier:
            # DM was given a target ID, check if they used it
            if not target_identifier.startswith('tgt_'):
                # DM used character name instead of target ID - non-compliant
                compliance_issue = f"llm_noncompliance:void_marker_used_name_not_id:expected={expected_target_id}:got={target_identifier}"
                logger.warning(f"⚠️  LLM COMPLIANCE ISSUE: DM used character name '{target_identifier}' instead of target ID '{expected_target_id}' in void marker")
            elif target_identifier != expected_target_id:
                # DM used wrong target ID - serious issue
                compliance_issue = f"llm_error:void_marker_wrong_target_id:expected={expected_target_id}:got={target_identifier}"
                logger.error(f"❌ LLM ERROR: DM used wrong target ID '{target_identifier}' (expected '{expected_target_id}')")

        if target_identifier:
            logger.debug(f"Parsed explicit void marker for '{target_identifier}': {delta:+d} ({reason})")
        else:
            logger.debug(f"Parsed explicit void marker: {delta:+d} ({reason})")

        return (delta, [reason], "dm_explicit", target_identifier, compliance_issue)

    return (0, [], "", None, None)


def parse_explicit_clock_markers(narration: str, active_clocks: dict = None) -> List[Tuple[str, int, str]]:
    """
    Parse explicit clock markers from LLM narration.

    Format: 📊 [Clock Name]: +X (reason) or -X (reason)

    Args:
        narration: DM's narrative text
        active_clocks: Dict of active clock names to Clock objects (optional)

    Returns:
        List of (clock_name, ticks, reason) tuples
    """
    triggers = []

    if not active_clocks:
        return triggers

    # Look for lines like: 📊 Passenger Safety: +2 (evacuation successful)
    clock_pattern = r'📊\s*([^:]+):\s*([+-]?\d+)\s*(?:\(([^)]+)\))?'

    for match in re.finditer(clock_pattern, narration):
        clock_name = match.group(1).strip()
        ticks = int(match.group(2))
        reason = match.group(3).strip() if match.group(3) else "Clock update"

        # Check if this clock exists
        if clock_name in active_clocks:
            triggers.append((clock_name, ticks, reason))
        else:
            # Try case-insensitive match
            for actual_clock_name in active_clocks.keys():
                if actual_clock_name.lower() == clock_name.lower():
                    triggers.append((actual_clock_name, ticks, reason))
                    break

    return triggers


def parse_clock_triggers(narration: str, outcome_tier: str, margin: int, active_clocks: dict = None) -> List[Tuple[str, int, str, str]]:
    """
    Parse narration and outcome to determine clock advancements.

    Works with dynamic clock names by pattern matching themes/categories.

    Args:
        narration: DM's narrative text
        outcome_tier: Action outcome tier
        margin: Success margin
        active_clocks: Dict of active clock names to Clock objects (optional)

    Returns:
        List of (clock_name, ticks, reason, source) tuples
        source is "dm_explicit" or "inferred_by_parser"
    """
    triggers = []
    narration_lower = narration.lower()

    # If no active clocks provided, return empty (no clocks to advance)
    if not active_clocks:
        return triggers

    # PRIORITY 1: Check for explicit clock markers first
    explicit_triggers = parse_explicit_clock_markers(narration, active_clocks)
    if explicit_triggers:
        # If LLM explicitly marked clocks, use those and skip pattern matching
        # Add source field to each trigger
        return [(name, ticks, reason, "dm_explicit") for name, ticks, reason in explicit_triggers]

    # Categorize each active clock by keywords in its name/description
    danger_clocks = []
    investigation_clocks = []
    corruption_clocks = []
    time_clocks = []
    stability_clocks = []
    safety_clocks = []  # NEW: Safety/evacuation/rescue clocks
    containment_clocks = []  # NEW: Surge/energy containment clocks

    for clock_name, clock_obj in active_clocks.items():
        name_lower = clock_name.lower()
        desc_lower = getattr(clock_obj, 'description', '').lower()
        combined = name_lower + ' ' + desc_lower

        # Categorize by theme
        if any(kw in combined for kw in ['danger', 'threat', 'escalation', 'suspicion', 'security', 'alarm', 'alert', 'lockdown', 'response']):
            danger_clocks.append(clock_name)
        if any(kw in combined for kw in ['investigation', 'progress', 'evidence', 'exposure', 'discovery', 'data', 'extraction']):
            investigation_clocks.append(clock_name)
        if any(kw in combined for kw in ['corruption', 'void', 'contamination', 'sanctuary', 'taint', 'manifests']):
            corruption_clocks.append(clock_name)
        if any(kw in combined for kw in ['time', 'pressure', 'deadline', 'clock', 'countdown']):
            time_clocks.append(clock_name)
        if any(kw in combined for kw in ['stability', 'sanity', 'morale', 'cohesion', 'crew', 'communal', 'bonds', 'bond', 'integrity']):
            stability_clocks.append(clock_name)
        # NEW: Safety/evacuation/rescue themed clocks
        if any(kw in combined for kw in ['safety', 'passenger', 'civilian', 'evacuation', 'rescue', 'protect', 'save', 'survivors']):
            safety_clocks.append(clock_name)
        # NEW: Containment/surge/cascade themed clocks (bad when they fill)
        if any(kw in combined for kw in ['cascade', 'surge', 'energy', 'meltdown', 'overload', 'breach', 'rupture']):
            containment_clocks.append(clock_name)

    # DANGER/SECURITY triggers (advances danger-themed clocks)
    if danger_clocks and any(phrase in narration_lower for phrase in [
        'security', 'alarm', 'alert', 'drone', 'protocol',
        'lockdown', 'surveillance', 'detected', 'suspicious', 'patrol', 'guard'
    ]):
        for clock_name in danger_clocks:
            triggers.append((clock_name, 1, "Security response", "inferred_by_parser"))

    if danger_clocks and any(phrase in narration_lower for phrase in [
        'psi-lockdown', 'facility-wide', 'catatonic', 'panic', 'emergency', 'crisis'
    ]):
        for clock_name in danger_clocks:
            triggers.append((clock_name, 2, "Major incident", "inferred_by_parser"))

    # INVESTIGATION triggers (advances investigation-themed clocks on successes)
    if investigation_clocks and outcome_tier in ['marginal', 'moderate', 'good', 'excellent', 'exceptional'] and margin >= 0:
        # Physical/digital evidence discovered
        evidence_phrases = [
            'badge', 'terminal', 'signature', 'log', 'trace',
            'pattern', 'evidence', 'fingerprint', 'id', 'credential',
            'device', 'tech', 'equipment', 'tool', 'neural-capture',
            'crystalline', 'residue', 'fracture', 'tampering',
            'maintenance duct', 'tunnel', 'path', 'trail',
            'syndicate', 'corporate', 'logo', 'insignia', 'sigil',
            'identifier', 'sequence', 'protocol', 'unauthorized',
            'clue', 'discovery', 'found', 'uncovered', 'revealed',
            # Cult/saboteur specific
            'obsidian path', 'crimson chorus', 'symmetry collective',
            'ritual-keeper', 'hegemony', 'inside job', 'saboteur',
            'acolyte', 'operative', 'infiltrator', 'collaborator',
            # Tech/data specific
            'data', 'file', 'record', 'database', 'archive', 'network'
        ]
        if any(phrase in narration_lower for phrase in evidence_phrases):
            # Stronger evidence for better success
            ticks = 2 if margin >= 10 else 1
            for clock_name in investigation_clocks:
                triggers.append((clock_name, ticks, f"Evidence discovered (margin +{margin})", "inferred_by_parser"))

    # CORRUPTION triggers (advances corruption-themed clocks on void exposure/failures)
    if corruption_clocks:
        if any(phrase in narration_lower for phrase in [
            'corruption', 'void manifests', 'contamination spreads', 'tainted',
            'void energy', 'void exposure', 'corrupted', 'defiled', 'infected'
        ]):
            for clock_name in corruption_clocks:
                triggers.append((clock_name, 1, "Void corruption spreading", "inferred_by_parser"))

        # Void changes are now controlled exclusively by DM through ⚫ Void: markers
        # Automatic keyword tracking removed - DM should explicitly apply void for:
        #   - Failed rituals (especially without offerings)
        #   - Void contamination events
        #   - Ritual backlash
        # This gives DM full mechanical control over when void corruption occurs

    # TIME triggers (advances time-pressure clocks automatically or on delays)
    if time_clocks:
        if any(phrase in narration_lower for phrase in [
            'time passes', 'hours pass', 'delay', 'wait', 'slow', 'take too long',
            'meanwhile', 'during this', 'while you'
        ]):
            for clock_name in time_clocks:
                triggers.append((clock_name, 1, "Time passing", "inferred_by_parser"))

    # STABILITY triggers (degrades on failures, improves on healing successes)
    if stability_clocks:
        # Degradation on social/mental failures
        if outcome_tier in ['failure', 'critical_failure']:
            if any(phrase in narration_lower for phrase in [
                'panic', 'traumat', 'scream', 'catatonic', 'shared consciousness',
                'discord', 'fracture', 'sever', 'broken bonds', 'disrupted',
                'fear', 'terror', 'horror', 'despair', 'breakdown', 'collapse'
            ]):
                ticks = 2 if outcome_tier == 'critical_failure' else 1
                for clock_name in stability_clocks:
                    triggers.append((clock_name, ticks, "Social cohesion degrading", "inferred_by_parser"))

        # Improvement on successful healing/stabilization
        elif outcome_tier in ['marginal', 'moderate', 'good', 'excellent', 'exceptional']:
            if any(phrase in narration_lower for phrase in [
                'stabiliz', 'heal', 'mend', 'bond', 'harmoni', 'protective',
                'reconstitute', 'restore', 'strengthen', 'repair', 'comfort', 'calm'
            ]):
                # Negative ticks = regress (improve)
                for clock_name in stability_clocks:
                    triggers.append((clock_name, -1, "Bonds stabilized", "inferred_by_parser"))

    # SAFETY/EVACUATION triggers (advances on successful evacuation/protection)
    if safety_clocks and outcome_tier in ['marginal', 'moderate', 'good', 'excellent', 'exceptional'] and margin >= 0:
        # Successful evacuation, rescue, protection of civilians
        safety_phrases = [
            'evacuate', 'evacuation', 'rescued', 'save', 'protect', 'shield', 'shelter',
            'passenger', 'civilian', 'corridor', 'safe passage', 'safe zone', 'safe path',
            'redirect flow', 'redirect passenger', 'reroute', 'guide', 'waypoint',
            'barrier', 'protective field', 'resonance anchor', 'safe alternative',
            'emergency route', 'escape path', 'exodus', 'flee', 'sanctuary'
        ]
        if any(phrase in narration_lower for phrase in safety_phrases):
            # Better success = more people saved
            ticks = 3 if margin >= 15 else (2 if margin >= 8 else 1)
            for clock_name in safety_clocks:
                triggers.append((clock_name, ticks, f"Evacuation progress (margin +{margin})", "inferred_by_parser"))

    # CONTAINMENT triggers (advances on failures - these are BAD clocks that fill toward disaster)
    if containment_clocks:
        # Failed containment actions make things worse
        if outcome_tier in ['failure', 'critical_failure']:
            if any(phrase in narration_lower for phrase in [
                'surge', 'cascade', 'energy', 'void', 'ritual', 'channel', 'contain',
                'redirect', 'stabiliz', 'barrier', 'field', 'diversion'
            ]):
                ticks = 3 if outcome_tier == 'critical_failure' else 2
                for clock_name in containment_clocks:
                    triggers.append((clock_name, ticks, "Failed containment", "inferred_by_parser"))

        # Even marginal successes might not be enough to prevent cascade
        elif outcome_tier == 'marginal' and margin <= 2:
            if any(phrase in narration_lower for phrase in [
                'barely', 'tenuous', 'struggle', 'strain', 'flicker', 'unstable',
                'temporary', 'hold', 'fragile', 'wobble', 'waver'
            ]):
                for clock_name in containment_clocks:
                    triggers.append((clock_name, 1, "Barely contained", "inferred_by_parser"))

    return triggers


def parse_void_triggers(narration: str, action_intent: str, outcome_tier: str, expected_target_id: str = None) -> Tuple[int, List[str], str, Optional[str], Optional[str]]:
    """
    Parse for void gains based on narration and action context.

    Args:
        narration: DM's narrative text
        action_intent: The action's intent string
        outcome_tier: The outcome tier (e.g., "success", "failure")
        expected_target_id: The target ID that was provided in the prompt (for compliance checking)

    Returns:
        Tuple of (void_change, list_of_reasons, source, target_identifier, compliance_issue)
        source is "dm_explicit" if explicit marker found, "inferred_by_parser" otherwise
        target_identifier is the target ID or name if targeting someone else, None if self
        compliance_issue is None if compliant, otherwise a string describing the issue
    """
    # PRIORITY 1: Check for explicit void markers first
    explicit_void, explicit_reasons, source, target_identifier, compliance_issue = parse_explicit_void_markers(narration, expected_target_id)
    if source == "dm_explicit":
        # If LLM explicitly marked void, use that and skip pattern matching
        if target_identifier:
            logger.debug(f"Void change targets '{target_identifier}': {explicit_void:+d}")
        return (explicit_void, explicit_reasons, "dm_explicit", target_identifier, compliance_issue)

    # PRIORITY 2: Keyword-based inference (fallback)
    void_change = 0
    reasons = []
    narration_lower = narration.lower()
    intent_lower = action_intent.lower()

    # Explicit void mentions (look for any variant)
    void_patterns = [
        (r'\+(\d+)\s*void', 'Void corruption'),
        (r'void\s*\+(\d+)', 'Void corruption'),
        (r'gains?\s+(\d+)\s+void', 'Void corruption'),
        (r'(\d+)\s+void\s+corruption', 'Void corruption'),
    ]

    for pattern, reason_text in void_patterns:
        for match in re.finditer(pattern, narration_lower):
            amount = int(match.group(1))
            void_change = max(void_change, amount)  # Take highest mentioned
            if reason_text not in reasons:
                reasons.append(reason_text)

    # ============================================================================
    # KEYWORD-BASED VOID DETECTION DISABLED (2025-10-29)
    # ============================================================================
    # Philosophy: "I despise keyword detection for game mechanics, I prefer tags from the LLMs"
    #
    # The DM LLM should explicitly include ⚫ Void: +X markers when thematically appropriate.
    # Keyword fallback was causing false positives:
    # - "center mass" → "center" → false "grounding meditation" match
    # - "neural feedback" → "feedback" → false "psychic damage" match
    # - Regular combat/investigation failures → false "void manipulation" match
    #
    # We now trust the DM to include explicit markers (parsed at lines 333-339 above).
    # If void changes happen without explicit markers, it's logged as a compliance issue.
    # ============================================================================

    # DISABLED: Ritual failures
    # if 'ritual' in intent_lower and outcome_tier in ['failure', 'critical_failure']:
    #     void_change += 1
    #     reasons.append("Failed ritual")

    # DISABLED: Void manipulation and exposure
    # if any(phrase in narration_lower or phrase in intent_lower for phrase in [
    #     'void energy', 'void manipulation', 'void-touched', 'void resonance',
    #     'corrupt', 'forbidden', 'void-shield', 'tap into void',
    #     'controlled void', 'void exposure', 'void-enhanced', 'void scan',
    #     'attune to void', 'opening to the void', 'void channel'
    # ]):
    #     # Critical failures with void get extra
    #     if outcome_tier == 'critical_failure':
    #         void_change += 1
    #         reasons.append("Void backlash from critical failure")
    #     # Failures with void manipulation also risky
    #     elif outcome_tier == 'failure':
    #         void_change += 1
    #         reasons.append("Failed void manipulation")

    # DISABLED: Psychic damage
    # if any(phrase in narration_lower for phrase in [
    #     'psychic recoil', 'feedback', 'backlash', 'mental trauma',
    #     'consciousness corrupted'
    # ]):
    #     if outcome_tier in ['failure', 'critical_failure']:
    #         void_change += 1
    #         reasons.append("Psychic/mental corruption")

    # DISABLED: Unbound activities
    # if any(phrase in intent_lower for phrase in [
    #     'without offering', 'skip offering', 'shortcut'
    # ]):
    #     void_change += 1
    #     reasons.append("Ritual shortcut (no offering)")

    # Return with source indicating this was inferred (or "none" if no void change)
    source = "inferred_by_parser" if void_change != 0 or reasons else ""
    return (void_change, reasons, source, None, None)  # None = no target, no compliance issue for inferred


def parse_creative_tactics_damage(
    action_intent: str,
    narration: str,
    outcome_tier: str,
    margin: int
) -> Tuple[int, str, str]:
    """
    Parse creative tactics (hacking, social manipulation, environmental) for damage interpretation.

    According to game analysis feedback:
    - High-margin social/hacking successes should deal damage, not just debuffs
    - Environmental hazards should cause actual damage
    - Turning enemies against each other should be supported

    Returns:
        Tuple of (damage_amount, damage_type, reason)
        damage_amount: 0 if no damage, 5-15 if damage dealt
        damage_type: "social_manipulation", "hacking", "environmental", "none"
        reason: Description of why damage was dealt
    """
    if outcome_tier not in ['moderate', 'good', 'excellent', 'exceptional']:
        # Only successes with decent margins can deal damage
        return (0, "none", "")

    intent_lower = action_intent.lower()
    narration_lower = narration.lower()
    combined = intent_lower + " " + narration_lower

    damage = 0
    damage_type = "none"
    reason = ""

    # SOCIAL MANIPULATION: Corporate authority, charm, intimidation
    social_keywords = [
        'corporate authority', 'command', 'order', 'intimidate', 'charm',
        'corporate influence', 'executive command', 'social manipulation',
        'convince', 'persuade', 'dominate', 'authority', 'corporate exorcism'
    ]

    if any(kw in combined for kw in social_keywords):
        # Check if targeting enemies (not allies)
        enemy_keywords = ['enemy', 'hostile', 'corrupted', 'void', 'parasite', 'scanner', 'sentinel']
        if any(kw in combined for kw in enemy_keywords):
            # High margin = confusion causes void corruption backlash damage
            if margin >= 15:
                damage = 10
                reason = "Exceptional social manipulation causes void corruption backlash in target"
            elif margin >= 10:
                damage = 7
                reason = "Strong social manipulation causes void corruption backlash"
            elif margin >= 5:
                damage = 5
                reason = "Social manipulation causes mild void corruption backlash"

            if damage > 0:
                damage_type = "social_manipulation"
                logger.debug(f"Creative tactic damage: {damage_type} → {damage} damage (margin {margin})")

    # HACKING: Turn enemies against each other or disable them
    hacking_keywords = [
        'hack', 'override', 'system', 'reprogram', 'control',
        'subvert', 'hijack', 'remote access', 'backdoor',
        'systems engineering', 'tech', 'interface', 'network'
    ]

    if any(kw in combined for kw in hacking_keywords):
        enemy_target_keywords = ['scanner', 'drone', 'turret', 'corrupted', 'automated', 'security', 'tendrils']
        if any(kw in combined for kw in enemy_target_keywords):
            # Hacking can:
            # 1. Turn enemy against others (friendly fire damage)
            # 2. Disable/overload enemy (direct damage)

            if 'turn against' in combined or 'attack other' in combined or 'target other' in combined:
                # Turning enemies against each other
                if margin >= 15:
                    damage = 12
                    reason = "Hacked enemy turns on allies, dealing significant friendly fire damage"
                elif margin >= 10:
                    damage = 8
                    reason = "Hacked enemy attacks allies before regaining control"
                elif margin >= 5:
                    damage = 5
                    reason = "Brief hacked control causes enemy to harm ally"
            elif 'overload' in combined or 'disable' in combined or 'shutdown' in combined:
                # Overloading/disabling causes damage
                if margin >= 15:
                    damage = 10
                    reason = "System overload causes catastrophic damage to target"
                elif margin >= 10:
                    damage = 7
                    reason = "System overload damages target's internal systems"
                elif margin >= 5:
                    damage = 5
                    reason = "Forced shutdown causes damage to target"

            if damage > 0:
                damage_type = "hacking"
                logger.debug(f"Creative tactic damage: {damage_type} → {damage} damage (margin {margin})")

    # ENVIRONMENTAL: Trigger hazards, overload systems, use environment
    environmental_keywords = [
        'overload power', 'trigger hazard', 'environmental', 'facility',
        'power surge', 'electrical', 'explosion', 'collapse',
        'redirect energy', 'containment breach', 'cascade failure',
        'use environment', 'trap', 'environmental damage'
    ]

    if any(kw in combined for kw in environmental_keywords):
        # Environmental damage should be area-effect (higher damage)
        if margin >= 15:
            damage = 15
            reason = "Environmental hazard triggers catastrophic damage to all in area"
        elif margin >= 10:
            damage = 12
            reason = "Environmental hazard causes significant area damage"
        elif margin >= 5:
            damage = 10
            reason = "Environmental hazard deals moderate area damage"

        if damage > 0:
            damage_type = "environmental"
            logger.debug(f"Creative tactic damage: {damage_type} → {damage} damage AoE (margin {margin})")

    return (damage, damage_type, reason)


def parse_position_change(narration: str, action_intent: str) -> Optional[str]:
    """
    Parse position changes from narration.

    Looks for patterns like:
    - "moves from X to Y" → returns Y
    - "shifts to Y" → returns Y
    - "[POSITION: Y]" → returns Y (explicit marker from DM)
    - "[TARGET_POSITION: Y]" → returns Y (player tactical declaration)

    Args:
        narration: DM's narrative text
        action_intent: Player's action intent

    Returns:
        New position string (e.g., "Near-PC", "Engaged-Enemy") or None if no change
    """
    narration_lower = narration.lower()

    # Look for explicit position marker first (highest priority)
    explicit_pattern = r'\[POSITION:\s*([^\]]+)\]'
    explicit_match = re.search(explicit_pattern, narration, re.IGNORECASE)
    if explicit_match:
        new_position = explicit_match.group(1).strip()
        logger.debug(f"Parsed explicit position marker: {new_position}")
        return new_position

    # Look for target position marker in player action (basic tactical movement)
    target_pattern = r'\[TARGET_POSITION:\s*([^\]]+)\]'
    target_match = re.search(target_pattern, action_intent, re.IGNORECASE)
    if target_match:
        new_position = target_match.group(1).strip()
        logger.debug(f"Parsed target position from player declaration: {new_position}")
        return new_position

    # Look for "moves from X to Y" pattern
    moves_pattern = r'moves?\s+from\s+([A-Za-z\-]+)\s+to\s+([A-Za-z\-]+)'
    moves_match = re.search(moves_pattern, narration_lower)
    if moves_match:
        new_position = moves_match.group(2)
        # Capitalize properly (e.g., "near-pc" → "Near-PC")
        new_position = '-'.join([word.capitalize() for word in new_position.split('-')])
        logger.debug(f"Parsed position change: {new_position}")
        return new_position

    # Look for "shifts to Y" or "moves to Y" pattern
    shifts_pattern = r'(?:shifts?|moves?)\s+to\s+([A-Za-z\-]+(?:\s+[A-Za-z\-]+)?)'
    shifts_match = re.search(shifts_pattern, narration_lower)
    if shifts_match:
        new_position = shifts_match.group(1).strip()
        # Capitalize properly
        new_position = '-'.join([word.capitalize() for word in new_position.split('-')])
        logger.debug(f"Parsed position change: {new_position}")
        return new_position

    return None


def parse_condition_markers(narration: str) -> List[Dict[str, Any]]:
    """
    Parse condition markers from DM narration.

    Format: 🎭 Condition: Unseen (description)
            🏔️ Token Claimed: High Ground (+2 ranged)

    Returns:
        List of condition dicts with name, type, description, penalty/bonus
    """
    conditions = []

    # Parse condition markers (🎭 Condition: Name (description))
    condition_pattern = r'🎭\s*Condition:\s*([^\(]+)\s*\(([^\)]+)\)'
    for match in re.finditer(condition_pattern, narration):
        name = match.group(1).strip()
        description = match.group(2).strip()

        # Determine penalty/bonus from description
        penalty = 0
        if "can't be targeted" in description.lower() or "unseen" in name.lower():
            # Unseen is special - no numeric penalty, but prevents targeting
            conditions.append({
                'type': 'Unseen',
                'name': name,
                'description': description,
                'penalty': 0,
                'special': 'prevents_targeting'
            })
        else:
            conditions.append({
                'type': name.replace(' ', '_'),
                'name': name,
                'description': description,
                'penalty': penalty
            })

    # Parse token markers (🏔️ Token Claimed: Name (+bonus))
    token_pattern = r'🏔️\s*Token Claimed:\s*([^\(]+)\s*\(([^\)]+)\)'
    for match in re.finditer(token_pattern, narration):
        token_name = match.group(1).strip()
        description = match.group(2).strip()

        # Extract bonus (e.g., "+2 ranged")
        bonus_match = re.search(r'([+\-]\d+)', description)
        bonus = int(bonus_match.group(1)) if bonus_match else 0

        conditions.append({
            'type': f'Token_{token_name.replace(" ", "_")}',
            'name': f'{token_name} Token',
            'description': description,
            'penalty': -bonus  # Negative penalty = bonus
        })

    if conditions:
        logger.debug(f"Parsed {len(conditions)} condition/token markers")

    return conditions


def parse_state_changes(
    narration: str,
    action: Dict,
    resolution: Dict,
    active_clocks: dict = None
) -> Dict[str, any]:
    """
    Parse complete state changes from a resolution.

    Args:
        narration: DM's narrative text
        action: Original action dict
        resolution: Resolution data (outcome_tier, margin, etc.)
        active_clocks: Dict of active clock names to Clock objects (optional)

    Returns:
        Dict with state changes: clocks, void, conditions, position_change, etc.
    """
    # Extract expected_target_id from action for compliance checking
    expected_target_id = None
    if action and action.get('target') and action['target'].startswith('tgt_'):
        expected_target_id = action['target']

    state_changes = {
        'clock_triggers': [],
        'void_change': 0,
        'void_reasons': [],
        'void_target_character': None,  # Track who receives void change (None = acting character)
        'llm_compliance_issue': None,  # Track LLM compliance issues for training data
        'conditions': [],
        'notes': [],
        'position_change': None
    }

    outcome_tier_raw = resolution.get('outcome_tier', 'moderate')
    margin = resolution.get('margin', 0)
    intent = action.get('intent', '')

    # Normalize outcome_tier to string (handle both enum and string values)
    if hasattr(outcome_tier_raw, 'value'):
        outcome_tier = outcome_tier_raw.value  # Extract .value from enum
    else:
        outcome_tier = str(outcome_tier_raw).lower()

    # Parse clock triggers (with dynamic clock support)
    clock_triggers = parse_clock_triggers(narration, outcome_tier, margin, active_clocks)
    state_changes['clock_triggers'] = clock_triggers

    # Parse void triggers (now returns source field + target + compliance)
    void_change, void_reasons, void_source, void_target, compliance_issue = parse_void_triggers(
        narration, intent, outcome_tier, expected_target_id
    )

    # Store target character if void change targets someone else
    if void_target:
        state_changes['void_target_character'] = void_target
        logger.debug(f"Void change will be applied to '{void_target}' instead of caster")

    # Store compliance issue if present
    if compliance_issue:
        state_changes['llm_compliance_issue'] = compliance_issue

    # ============================================================================
    # KEYWORD-BASED VOID RECOVERY DISABLED (2025-10-29)
    # ============================================================================
    # DISABLED: Grounding meditation keyword detection
    # Caused false positive: "Fire precise shots at center mass" → "center" → false "grounding meditation"
    # DM should use explicit markers for void recovery: ⚫ Void: -1 (grounding meditation success)
    # ============================================================================

    # DISABLED: Grounding/purge keyword detection
    # intent_lower = intent.lower()
    # narration_lower = narration.lower()
    # grounding_keywords = ['ground', 'center', 'meditate', 'calm self', 'focus inward', 'discipline mind']
    # purge_keywords = ['purge', 'cleanse', 'dephase', 'filter', 'contain void', 'isolate corruption']

    # if outcome_tier in ['marginal', 'moderate', 'good', 'excellent', 'exceptional']:
    #     if any(kw in intent_lower for kw in grounding_keywords):
    #         # Successful grounding: -1 personal void
    #         void_change = -1
    #         void_reasons = ['Grounding meditation success']
    #         state_changes['notes'].append("Grounding: -1 Void (personal recovery)")

    # NOTE: All void changes (positive and negative) now handled by DM explicit markers (⚫ Void: ±X)
    # The DM's narration prompt includes scaling rules based on success quality
    # No keyword detection needed - trust the DM's judgment

    # DISABLED: Purge keyword detection
    # elif any(kw in intent_lower for kw in purge_keywords):
    #     # Successful purge: -scene void (handled by DM, mark as note)
    #     state_changes['notes'].append("Purge: -Scene Void pressure (one round)")

    state_changes['void_change'] = void_change
    state_changes['void_reasons'] = void_reasons
    state_changes['void_source'] = void_source

    # Parse conditions (wounds, stuns, etc.)
    narration_lower = narration.lower()
    if any(phrase in narration_lower for phrase in [
        'headache', 'migraine', 'splitting pain'
    ]):
        state_changes['conditions'].append({
            'type': 'Mental Strain',
            'penalty': -2,
            'description': 'Headache from psychic feedback'
        })

    if any(phrase in narration_lower for phrase in [
        'overheat', 'crack', 'damage', 'short out'
    ]):
        state_changes['conditions'].append({
            'type': 'Equipment Damage',
            'penalty': -2,
            'description': 'Damaged equipment'
        })

    # Parse soulcredit markers (explicit ⚖️ Soulcredit: +/- markers from DM)
    sc_delta, sc_reason, sc_source = parse_soulcredit_markers(narration)
    state_changes['soulcredit_change'] = sc_delta
    state_changes['soulcredit_reasons'] = [sc_reason] if sc_reason else []
    state_changes['soulcredit_source'] = sc_source

    # Parse position changes (for tactical movement)
    position_change = parse_position_change(narration, intent)
    if position_change:
        state_changes['position_change'] = position_change

    # Parse condition/token markers (for skill-based movement benefits)
    condition_markers = parse_condition_markers(narration)
    for cond in condition_markers:
        state_changes['conditions'].append(cond)

    return state_changes


def parse_session_end_marker(narration: str) -> Dict[str, str]:
    """
    Parse session end markers from DM narration.

    Format: [SESSION_END: VICTORY] or [SESSION_END: DEFEAT] or [SESSION_END: DRAW]

    Args:
        narration: DM's narrative text

    Returns:
        Dict with 'status' (victory/defeat/draw/none) and optional 'reason'
    """
    pattern = r'\[SESSION_END:\s*(VICTORY|DEFEAT|DRAW)(?:\s*-\s*([^\]]+))?\]'
    match = re.search(pattern, narration, re.IGNORECASE)

    if match:
        status = match.group(1).lower()
        reason = match.group(2).strip() if match.group(2) else None
        logger.debug(f"Parsed session end marker: {status}" + (f" - {reason}" if reason else ""))
        return {'status': status, 'reason': reason}

    return {'status': 'none', 'reason': None}


def parse_new_clock_marker(narration: str) -> List[Dict[str, any]]:
    """
    Parse new clock spawn markers from DM narration.

    Format: [NEW_CLOCK: Name | Max | Description]

    Args:
        narration: DM's narrative text

    Returns:
        List of dicts with 'name', 'max', 'description'
    """
    pattern = r'\[NEW_CLOCK:\s*([^|]+)\s*\|\s*(\d+)\s*\|\s*([^\]]+)\]'
    matches = re.findall(pattern, narration)

    new_clocks = []
    for match in matches:
        name = match[0].strip()
        max_ticks = int(match[1].strip())
        description = match[2].strip()

        new_clocks.append({
            'name': name,
            'max': max_ticks,
            'description': description
        })
        logger.debug(f"Parsed new clock: {name} ({max_ticks} ticks) - {description}")

    return new_clocks


def extract_invalid_advance_story_markers(text: str) -> List[str]:
    """
    Find malformed [ADVANCE_STORY: ...] markers that don't have enough fields.

    Used for retry mechanism - detects markers that will fail parsing.

    Args:
        text: DM narration text

    Returns:
        List of incomplete marker contents (without brackets)
    """
    # Match any [ADVANCE_STORY: ...] marker
    pattern = r'\[ADVANCE_STORY:\s*([^\]]+)\]'
    candidates = re.findall(pattern, text, re.IGNORECASE)

    invalid = []
    for content in candidates:
        pipe_count = content.count('|')
        # Need at least 1 pipe for 2 fields (location|situation)
        if pipe_count < 1:
            invalid.append(content)
            logger.debug(f"Found invalid ADVANCE_STORY marker with {pipe_count + 1} fields (need 2): {content[:50]}")

    return invalid


def parse_advance_story_marker(narration: str) -> Dict[str, any]:
    """
    Parse story advancement markers from DM narration.

    Format: [ADVANCE_STORY: location | situation]
    Example: [ADVANCE_STORY: Abandoned Transit Hub | Having escaped, you find a wounded courier with urgent intel]

    Args:
        narration: DM's narrative text

    Returns:
        Dict with 'should_advance' (bool), 'location' (str), and 'situation' (str)
    """
    pattern = r'\[ADVANCE_STORY:\s*([^|]+)\|\s*([^\]]+)\]'
    match = re.search(pattern, narration)

    if match:
        location = match.group(1).strip()
        situation = match.group(2).strip()
        logger.debug(f"Parsed story advancement: {location} - {situation}")
        return {
            'should_advance': True,
            'location': location,
            'situation': situation
        }

    return {'should_advance': False, 'location': None, 'situation': None}


def parse_combat_triplet(narration: str) -> Dict[str, any]:
    """
    Parse combat triplet from narration: attack/damage/soak/post_soak_damage.

    Looks for patterns like:
    - "Attack: 18 vs DC 15"
    - "Damage: 8 → Soak: 3 → Final: 5"
    - "takes 5 damage"

    Args:
        narration: DM's narrative text

    Returns:
        Dict with 'attack', 'damage', 'soak', 'post_soak_damage' or empty if not combat
    """
    combat_data = {}

    # Look for attack roll
    attack_pattern = r'(?:Attack|attack):\s*(\d+)\s*(?:vs|against|VS)\s*(?:DC|dc)?\s*(\d+)'
    attack_match = re.search(attack_pattern, narration)
    if attack_match:
        combat_data['attack_roll'] = int(attack_match.group(1))
        combat_data['attack_dc'] = int(attack_match.group(2))
        combat_data['attack_hit'] = int(attack_match.group(1)) >= int(attack_match.group(2))

    # Look for damage triplet (Damage → Soak → Final)
    damage_triplet_pattern = r'(?:Damage|damage):\s*(\d+)\s*→\s*(?:Soak|soak):\s*(\d+)\s*→\s*(?:Final|final):\s*(\d+)'
    triplet_match = re.search(damage_triplet_pattern, narration)
    if triplet_match:
        combat_data['damage'] = int(triplet_match.group(1))
        combat_data['soak'] = int(triplet_match.group(2))
        combat_data['post_soak_damage'] = int(triplet_match.group(3))
        logger.debug(f"Parsed combat triplet: {combat_data['damage']} damage, {combat_data['soak']} soaked, {combat_data['post_soak_damage']} final")
    else:
        # Alternative: look for "takes X damage"
        damage_pattern = r'(?:takes|suffers)\s+(\d+)\s+damage'
        damage_match = re.search(damage_pattern, narration, re.IGNORECASE)
        if damage_match:
            combat_data['post_soak_damage'] = int(damage_match.group(1))

    return combat_data


def parse_mechanical_effect(narration: str, expected_target_id: str = None, intent: str = "", outcome_tier: str = "") -> Optional[Dict[str, any]]:
    """
    Parse [MECHANICAL_EFFECT] blocks from DM narration.

    Supports multiple effect types:
    - damage: Direct HP reduction
    - debuff: Ongoing penalty to rolls
    - status: Status effect (shocked, stunned, prone, etc.)
    - movement: Forced position change
    - reveal: Exposed weakness or intel

    Args:
        narration: DM's narrative text
        expected_target_id: The target ID that was provided in the prompt (for compliance checking)
        intent: The action intent (for void parsing)
        outcome_tier: The outcome tier (for void parsing)

    Returns:
        Dict with effect details or None if no effect block found
    """
    # Look for [MECHANICAL_EFFECT]...[/MECHANICAL_EFFECT] block
    pattern = r'\[MECHANICAL_EFFECT\](.*?)\[/MECHANICAL_EFFECT\]'
    match = re.search(pattern, narration, re.DOTALL | re.IGNORECASE)

    if not match:
        return None

    effect_block = match.group(1)
    effect = {}

    # Parse Type
    type_match = re.search(r'Type:\s*(\w+)', effect_block, re.IGNORECASE)
    if type_match:
        effect['type'] = type_match.group(1).lower()
    else:
        return None  # Type is required

    # Parse Target
    target_match = re.search(r'Target:\s*(.+?)(?:\n|$)', effect_block, re.IGNORECASE)
    if target_match:
        effect['target'] = target_match.group(1).strip()

    # Parse type-specific details
    if effect.get('type') == 'damage':
        # Parse damage triplet
        damage_match = re.search(r'Damage:\s*(\d+)\s*→\s*Soak:\s*(\d+)\s*→\s*Final:\s*(\d+)', effect_block)
        if damage_match:
            effect['damage'] = int(damage_match.group(1))
            effect['soak'] = int(damage_match.group(2))
            effect['final'] = int(damage_match.group(3))
            logger.debug(f"Parsed damage effect: {effect['final']} final damage to {effect.get('target', 'unknown')}")
        else:
            # Try just final damage
            final_match = re.search(r'(?:Final|Damage):\s*(\d+)', effect_block)
            if final_match:
                effect['final'] = int(final_match.group(1))

    elif effect.get('type') == 'debuff':
        # Parse debuff details
        effect_match = re.search(r'Effect:\s*(.+?)(?:\n|Duration:|$)', effect_block, re.IGNORECASE)
        duration_match = re.search(r'Duration:\s*(\d+)\s*rounds?', effect_block, re.IGNORECASE)

        if effect_match:
            effect['effect'] = effect_match.group(1).strip()
        if duration_match:
            effect['duration'] = int(duration_match.group(1))
        else:
            effect['duration'] = 3  # Default 3 rounds

        # Try to extract numeric penalty
        penalty_match = re.search(r'(-\d+)', effect.get('effect', ''))
        if penalty_match:
            effect['penalty'] = int(penalty_match.group(1))

        logger.debug(f"Parsed debuff effect: {effect.get('effect', 'unknown')} for {effect.get('duration', 3)} rounds")

    elif effect.get('type') == 'status':
        # Parse status effect
        effect_match = re.search(r'Effect:\s*(.+?)(?:\n|$)', effect_block, re.IGNORECASE)
        if effect_match:
            effect['effect'] = effect_match.group(1).strip()

        duration_match = re.search(r'Duration:\s*(\d+)\s*rounds?', effect_block, re.IGNORECASE)
        if duration_match:
            effect['duration'] = int(duration_match.group(1))
        else:
            effect['duration'] = 3  # Default 3 rounds

        logger.debug(f"Parsed status effect: {effect.get('effect', 'unknown')}")

    elif effect.get('type') == 'movement':
        # Parse movement effect
        effect_match = re.search(r'Effect:\s*(.+?)(?:\n|$)', effect_block, re.IGNORECASE)
        if effect_match:
            effect['effect'] = effect_match.group(1).strip()

        # Try to extract new position
        pos_match = re.search(r'(Engaged|Near-PC|Near-Enemy|Far-PC|Far-Enemy|Extreme-PC|Extreme-Enemy)', effect.get('effect', ''))
        if pos_match:
            effect['new_position'] = pos_match.group(1)

        logger.debug(f"Parsed movement effect: {effect.get('effect', 'unknown')}")

    elif effect.get('type') == 'reveal':
        # Parse reveal/intel effect
        effect_match = re.search(r'Effect:\s*(.+?)(?:\n|$)', effect_block, re.IGNORECASE)
        if effect_match:
            effect['effect'] = effect_match.group(1).strip()

        # Try to extract bonus for allies
        bonus_match = re.search(r'\+(\d+)', effect.get('effect', ''))
        if bonus_match:
            effect['bonus'] = int(bonus_match.group(1))

        logger.debug(f"Parsed reveal effect: {effect.get('effect', 'unknown')}")

    return effect if effect else None


def generate_fallback_effect(action: Dict[str, any], resolution: Dict[str, any]) -> Optional[Dict[str, any]]:
    """
    Generate default mechanical effect when LLM doesn't include one.

    Effect magnitude is based on margin of success.

    Args:
        action: The action dict with skill, target, etc.
        resolution: Resolution dict with success, margin, etc.

    Returns:
        Effect dict ready for application, or None
    """
    target = action.get('target')
    if not target:
        return None  # No target, no effect

    # Only generate effects for successful actions
    margin = resolution.get('margin', 0)
    if margin < 0:
        return None

    skill = action.get('skill', '').lower() if action.get('skill') else ''
    description = action.get('description', '').lower()

    # Determine effect type based on skill and narrative
    damage_keywords = ['attack', 'strike', 'blast', 'damage', 'hit', 'shoot', 'fire', 'slash', 'stab']
    debuff_keywords = ['disrupt', 'weaken', 'impair', 'jam', 'hack', 'interfere', 'destabilize']

    has_damage_intent = any(kw in description for kw in damage_keywords)
    has_debuff_intent = any(kw in description for kw in debuff_keywords)

    # Combat skills default to damage
    combat_skills = ['guns', 'melee', 'brawl']
    # Hybrid skills can do damage or debuffs
    hybrid_skills = ['astral arts', 'dreamwork', 'drone operation', 'charm', 'intimidation', 'corporate influence']
    # Tech/utility skills default to debuffs
    utility_skills = ['systems', 'engineering', 'investigation', 'perception']

    logger.debug(f"Generating fallback effect: skill={skill}, margin={margin}, has_damage_intent={has_damage_intent}")

    # Determine effect type and magnitude
    if skill in combat_skills or (skill in hybrid_skills and has_damage_intent):
        # Generate damage effect
        # Base damage = margin // 2, min 5, max 15 for mental attacks, max 20 for physical
        max_damage = 15 if skill in ['charm', 'intimidation', 'corporate influence'] else 20
        base_damage = max(5, min(max_damage, margin // 2))

        return {
            'type': 'damage',
            'target': target,
            'final': base_damage,
            'source': 'fallback',
            'description': f"Fallback damage from {skill} (margin +{margin})"
        }

    elif skill in utility_skills or (skill in hybrid_skills and has_debuff_intent) or has_debuff_intent:
        # Generate debuff effect with powerful status conditions
        # Penalty = -1 per 5 margin, min -1, max -5
        penalty = -max(1, min(5, margin // 5))
        duration = 3  # 3 rounds default

        # Determine status effect based on skill and margin
        status_effect = None
        if margin >= 20:  # Excellent success (margin ≥ 20)
            if skill in ['charm', 'intimidation', 'corporate influence']:
                status_effect = 'terrified (-5 to attacks, must make morale check)'
            elif skill in ['astral arts', 'dreamwork']:
                status_effect = 'mind-shattered (-5 to all rolls, confused)'
            elif skill in ['systems', 'engineering']:
                status_effect = 'systems paralyzed (cannot use tech abilities)'
        elif margin >= 15:  # Great success (margin 15-19)
            if skill in ['charm', 'intimidation', 'corporate influence']:
                status_effect = 'demoralized (-3 to attacks)'
            elif skill in ['astral arts', 'dreamwork']:
                status_effect = 'psychically disrupted (-3 to all rolls)'
            elif skill in ['systems', 'engineering']:
                status_effect = 'disrupted systems (-3 to tech rolls)'

        # Enhanced effect description
        if status_effect:
            effect_desc = f"{penalty} to rolls, {status_effect}"
        else:
            effect_desc = f"{penalty} to enemy rolls"

        return {
            'type': 'debuff',
            'target': target,
            'effect': effect_desc,
            'penalty': penalty,
            'duration': duration,
            'source': 'fallback',
            'description': f"Fallback debuff from {skill} (margin +{margin})"
        }

    elif skill == 'athletics':
        # Generate movement/prone effect
        return {
            'type': 'status',
            'target': target,
            'effect': 'knocked prone or forced movement',
            'duration': 1,
            'source': 'fallback',
            'description': f"Fallback movement from athletics (margin +{margin})"
        }

    else:
        # Generic minor debuff for other skills
        penalty = -max(1, margin // 10)
        return {
            'type': 'debuff',
            'target': target,
            'effect': f"{penalty} to enemy rolls",
            'penalty': penalty,
            'duration': 1,
            'source': 'fallback',
            'description': f"Fallback minor debuff from {skill} (margin +{margin})"
        }


def generate_fallback_buff(action: Dict[str, any], resolution: Dict[str, any]) -> Optional[Dict[str, any]]:
    """
    Generate default buff effect for ally-targeted support actions.

    Buff magnitude is based on margin of success.

    Args:
        action: The action dict with skill, target_ally, etc.
        resolution: Resolution dict with success, margin, etc.

    Returns:
        Buff dict ready for application, or None
    """
    target_ally = action.get('target_ally')
    if not target_ally:
        return None  # No ally target, no buff

    # Only generate buffs for successful actions
    margin = resolution.get('margin', 0)
    if margin < 0:
        return None

    skill = action.get('skill', '').lower() if action.get('skill') else ''
    description = action.get('description', '').lower()
    intent = action.get('intent', '').lower()

    # Support skill categories
    support_skills = ['charm', 'counsel', 'medicine', 'first aid', 'leadership']
    tactical_skills = ['awareness', 'perception', 'investigation', 'tactics']
    tech_skills = ['systems', 'engineering', 'drone operation']

    # Detect buff intent from description/intent
    heal_keywords = ['heal', 'treat', 'stabilize', 'medicine', 'first aid', 'bandage']
    inspire_keywords = ['inspire', 'encourage', 'rally', 'bolster', 'motivate', 'cheer']
    coordinate_keywords = ['coordinate', 'spot', 'aim', 'guide', 'direct', 'target']
    shield_keywords = ['shield', 'protect', 'cover', 'defend', 'guard']
    enhance_keywords = ['enhance', 'boost', 'amplify', 'strengthen', 'empower']

    has_heal_intent = any(kw in description or kw in intent for kw in heal_keywords)
    has_inspire_intent = any(kw in description or kw in intent for kw in inspire_keywords)
    has_coordinate_intent = any(kw in description or kw in intent for kw in coordinate_keywords)
    has_shield_intent = any(kw in description or kw in intent for kw in shield_keywords)
    has_enhance_intent = any(kw in description or kw in intent for kw in enhance_keywords)

    logger.debug(f"Generating fallback buff: skill={skill}, margin={margin}, target={target_ally}")

    # Determine buff type and magnitude based on skill and intent
    if has_heal_intent or skill in ['medicine', 'first aid']:
        # Healing effect - restore HP
        # Healing = margin // 2, min 3, max 12
        healing_amount = max(3, min(12, margin // 2))
        return {
            'type': 'heal',
            'target': target_ally,
            'amount': healing_amount,
            'source': 'fallback',
            'description': f"Heals {healing_amount} HP (margin +{margin})"
        }

    elif has_inspire_intent or skill in ['charm', 'counsel', 'leadership']:
        # Morale/inspiration buff - bonus to next attack/defense
        # Bonus = +1 per 5 margin, min +1, max +4
        bonus = max(1, min(4, margin // 5))
        duration = 2  # 2 rounds

        if margin >= 15:
            effect_desc = f"inspired (+{bonus} to attacks, +2 to morale checks)"
        else:
            effect_desc = f"encouraged (+{bonus} to next attack)"

        return {
            'type': 'buff',
            'target': target_ally,
            'effect': effect_desc,
            'bonus': bonus,
            'duration': duration,
            'source': 'fallback',
            'description': f"Fallback morale buff from {skill} (margin +{margin})"
        }

    elif has_coordinate_intent or skill in tactical_skills:
        # Tactical coordination - aim/targeting bonus
        # Bonus = +1 per 5 margin, min +1, max +3
        bonus = max(1, min(3, margin // 5))
        duration = 1  # 1 round (immediate next action)

        effect_desc = f"aimed shot (+{bonus} to next attack)"

        return {
            'type': 'buff',
            'target': target_ally,
            'effect': effect_desc,
            'bonus': bonus,
            'duration': duration,
            'source': 'fallback',
            'description': f"Fallback tactical buff from {skill} (margin +{margin})"
        }

    elif has_shield_intent:
        # Defensive buff - bonus to defense/soak
        bonus = max(1, min(3, margin // 5))
        duration = 2

        effect_desc = f"shielded (+{bonus} to defense, +2 soak)"

        return {
            'type': 'buff',
            'target': target_ally,
            'effect': effect_desc,
            'bonus': bonus,
            'duration': duration,
            'source': 'fallback',
            'description': f"Fallback shield buff from {skill} (margin +{margin})"
        }

    elif has_enhance_intent or skill in tech_skills:
        # Enhancement buff - bonus to specific roll types
        bonus = max(1, min(3, margin // 5))
        duration = 2

        if skill in tech_skills:
            effect_desc = f"enhanced systems (+{bonus} to tech rolls)"
        else:
            effect_desc = f"empowered (+{bonus} to next action)"

        return {
            'type': 'buff',
            'target': target_ally,
            'effect': effect_desc,
            'bonus': bonus,
            'duration': duration,
            'source': 'fallback',
            'description': f"Fallback enhancement buff from {skill} (margin +{margin})"
        }

    else:
        # Generic small buff for other support actions
        bonus = max(1, margin // 10)
        return {
            'type': 'buff',
            'target': target_ally,
            'effect': f"+{bonus} to next roll",
            'bonus': bonus,
            'duration': 1,
            'source': 'fallback',
            'description': f"Fallback minor buff from {skill} (margin +{margin})"
        }
