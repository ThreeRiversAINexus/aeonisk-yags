"""
Parse narrative outcomes to extract mechanical state changes.
Automatically advance clocks and void based on DM narration.
"""

import re
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


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


def parse_clock_triggers(narration: str, outcome_tier: str, margin: int, active_clocks: dict = None) -> List[Tuple[str, int, str]]:
    """
    Parse narration and outcome to determine clock advancements.

    Works with dynamic clock names by pattern matching themes/categories.

    Args:
        narration: DM's narrative text
        outcome_tier: Action outcome tier
        margin: Success margin
        active_clocks: Dict of active clock names to Clock objects (optional)

    Returns:
        List of (clock_name, ticks, reason) tuples
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
        return explicit_triggers

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
            triggers.append((clock_name, 1, "Security response"))

    if danger_clocks and any(phrase in narration_lower for phrase in [
        'psi-lockdown', 'facility-wide', 'catatonic', 'panic', 'emergency', 'crisis'
    ]):
        for clock_name in danger_clocks:
            triggers.append((clock_name, 2, "Major incident"))

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
                triggers.append((clock_name, ticks, f"Evidence discovered (margin +{margin})"))

    # CORRUPTION triggers (advances corruption-themed clocks on void exposure/failures)
    if corruption_clocks:
        if any(phrase in narration_lower for phrase in [
            'corruption', 'void manifests', 'contamination spreads', 'tainted',
            'void energy', 'void exposure', 'corrupted', 'defiled', 'infected'
        ]):
            for clock_name in corruption_clocks:
                triggers.append((clock_name, 1, "Void corruption spreading"))

        # Failed void manipulation increases corruption
        if outcome_tier in ['failure', 'critical_failure']:
            if any(phrase in narration_lower for phrase in [
                'void', 'ritual', 'astral', 'channel', 'corruption', 'taint'
            ]):
                ticks = 2 if outcome_tier == 'critical_failure' else 1
                for clock_name in corruption_clocks:
                    triggers.append((clock_name, ticks, "Failed void manipulation"))

    # TIME triggers (advances time-pressure clocks automatically or on delays)
    if time_clocks:
        if any(phrase in narration_lower for phrase in [
            'time passes', 'hours pass', 'delay', 'wait', 'slow', 'take too long',
            'meanwhile', 'during this', 'while you'
        ]):
            for clock_name in time_clocks:
                triggers.append((clock_name, 1, "Time passing"))

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
                    triggers.append((clock_name, ticks, "Social cohesion degrading"))

        # Improvement on successful healing/stabilization
        elif outcome_tier in ['marginal', 'moderate', 'good', 'excellent', 'exceptional']:
            if any(phrase in narration_lower for phrase in [
                'stabiliz', 'heal', 'mend', 'bond', 'harmoni', 'protective',
                'reconstitute', 'restore', 'strengthen', 'repair', 'comfort', 'calm'
            ]):
                # Negative ticks = regress (improve)
                for clock_name in stability_clocks:
                    triggers.append((clock_name, -1, "Bonds stabilized"))

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
                triggers.append((clock_name, ticks, f"Evacuation progress (margin +{margin})"))

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
                    triggers.append((clock_name, ticks, "Failed containment"))

        # Even marginal successes might not be enough to prevent cascade
        elif outcome_tier == 'marginal' and margin <= 2:
            if any(phrase in narration_lower for phrase in [
                'barely', 'tenuous', 'struggle', 'strain', 'flicker', 'unstable',
                'temporary', 'hold', 'fragile', 'wobble', 'waver'
            ]):
                for clock_name in containment_clocks:
                    triggers.append((clock_name, 1, "Barely contained"))

    return triggers


def parse_void_triggers(narration: str, action_intent: str, outcome_tier: str) -> Tuple[int, List[str]]:
    """
    Parse for void gains based on narration and action context.

    Returns:
        Tuple of (void_change, list_of_reasons)
    """
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

    # Ritual failures
    if 'ritual' in intent_lower and outcome_tier in ['failure', 'critical_failure']:
        void_change += 1
        reasons.append("Failed ritual")

    # Void manipulation and exposure
    if any(phrase in narration_lower or phrase in intent_lower for phrase in [
        'void energy', 'void manipulation', 'void-touched', 'void resonance',
        'corrupt', 'forbidden', 'void-shield', 'tap into void',
        'controlled void', 'void exposure', 'void-enhanced', 'void scan',
        'attune to void', 'opening to the void', 'void channel'
    ]):
        # Critical failures with void get extra
        if outcome_tier == 'critical_failure':
            void_change += 1
            reasons.append("Void backlash from critical failure")
        # Failures with void manipulation also risky
        elif outcome_tier == 'failure':
            void_change += 1
            reasons.append("Failed void manipulation")

    # Psychic damage
    if any(phrase in narration_lower for phrase in [
        'psychic recoil', 'feedback', 'backlash', 'mental trauma',
        'consciousness corrupted'
    ]):
        if outcome_tier in ['failure', 'critical_failure']:
            void_change += 1
            reasons.append("Psychic/mental corruption")

    # Unbound activities
    if any(phrase in intent_lower for phrase in [
        'without offering', 'skip offering', 'shortcut'
    ]):
        void_change += 1
        reasons.append("Ritual shortcut (no offering)")

    return (void_change, reasons)


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
        Dict with state changes: clocks, void, conditions, etc.
    """
    state_changes = {
        'clock_triggers': [],
        'void_change': 0,
        'void_reasons': [],
        'conditions': [],
        'notes': []
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

    # Parse void triggers
    void_change, void_reasons = parse_void_triggers(narration, intent, outcome_tier)

    # RECOVERY MOVES: Reduce void on successful grounding/purge
    intent_lower = intent.lower()
    grounding_keywords = ['ground', 'center', 'meditate', 'calm self', 'focus inward', 'discipline mind']
    purge_keywords = ['purge', 'cleanse', 'dephase', 'filter', 'contain void', 'isolate corruption']

    if outcome_tier in ['marginal', 'moderate', 'good', 'excellent', 'exceptional']:
        if any(kw in intent_lower for kw in grounding_keywords):
            # Successful grounding: -1 personal void
            void_change = -1
            void_reasons = ['Grounding meditation success']
            state_changes['notes'].append("Grounding: -1 Void (personal recovery)")

        elif any(kw in intent_lower for kw in purge_keywords):
            # Successful purge: -scene void (handled by DM, mark as note)
            state_changes['notes'].append("Purge: -Scene Void pressure (one round)")

    state_changes['void_change'] = void_change
    state_changes['void_reasons'] = void_reasons

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

    return state_changes
