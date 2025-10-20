"""
Parse narrative outcomes to extract mechanical state changes.
Automatically advance clocks and void based on DM narration.
"""

import re
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


def parse_clock_triggers(narration: str, outcome_tier: str, margin: int) -> List[Tuple[str, int, str]]:
    """
    Parse narration and outcome to determine clock advancements.

    Returns:
        List of (clock_name, ticks, reason) tuples
    """
    triggers = []
    narration_lower = narration.lower()

    # Corporate Suspicion triggers
    if any(phrase in narration_lower for phrase in [
        'security', 'alarm', 'alert', 'drone', 'protocol',
        'lockdown', 'surveillance', 'detected', 'suspicious'
    ]):
        triggers.append(('Corporate Suspicion', 1, "Security response"))

    if any(phrase in narration_lower for phrase in [
        'psi-lockdown', 'facility-wide', 'catatonic', 'panic'
    ]):
        triggers.append(('Corporate Suspicion', 2, "Major incident"))

    # Evidence Trail / Saboteur Exposure triggers - concrete clues discovered
    if outcome_tier in ['marginal', 'moderate', 'good', 'excellent', 'exceptional'] and margin >= 0:
        # Physical/digital evidence
        evidence_phrases = [
            'badge', 'terminal', 'signature', 'log', 'trace',
            'pattern', 'evidence', 'fingerprint', 'id', 'credential',
            'device', 'tech', 'equipment', 'tool', 'neural-capture',
            'crystalline', 'residue', 'fracture', 'tampering',
            'maintenance duct', 'tunnel', 'path', 'trail',
            'syndicate', 'corporate', 'logo', 'insignia', 'sigil',
            'identifier', 'sequence', 'protocol', 'unauthorized',
            # Cult/saboteur specific
            'obsidian path', 'crimson chorus', 'symmetry collective',
            'ritual-keeper', 'hegemony', 'inside job', 'saboteur',
            'acolyte', 'operative', 'infiltrator', 'collaborator'
        ]
        if any(phrase in narration_lower for phrase in evidence_phrases):
            # Stronger evidence for better success
            ticks = 2 if margin >= 10 else 1
            triggers.append(('Evidence Trail', ticks, f"Concrete evidence discovered (margin +{margin})"))
            triggers.append(('Saboteur Exposure', ticks, f"Saboteur clue found (margin +{margin})"))

    # Sanctuary/Facility specific clocks
    if any(phrase in narration_lower for phrase in [
        'lockdown', 'sealed', 'containment', 'quarantine',
        'drones converging', 'security converging', 'armed response',
        'psi backlash', 'psychic backlash', 'feedback', 'cascad',
        'families collapsing', 'catatonic', 'chaos', 'disorder'
    ]):
        triggers.append(('Facility Lockdown', 1, "Security/chaos escalation"))

    if any(phrase in narration_lower for phrase in [
        'corruption', 'void manifests', 'contamination spreads'
    ]):
        triggers.append(('Sanctuary Corruption', 1, "Void corruption spreading"))

    # Communal Stability (degrades on failures, improves on healing successes)
    if outcome_tier in ['failure', 'critical_failure']:
        if any(phrase in narration_lower for phrase in [
            'panic', 'traumat', 'scream', 'catatonic', 'shared consciousness',
            'discord', 'fracture', 'sever', 'broken bonds', 'disrupted'
        ]):
            ticks = 2 if outcome_tier == 'critical_failure' else 1
            triggers.append(('Communal Stability', ticks, "Social cohesion degrading"))
    elif outcome_tier in ['marginal', 'moderate', 'good', 'excellent', 'exceptional']:
        # Successful healing/stabilization improves stability (regress the degradation clock)
        if any(phrase in narration_lower for phrase in [
            'stabiliz', 'heal', 'mend', 'bond', 'harmoni', 'protective',
            'reconstitute', 'restore', 'strengthen', 'repair'
        ]):
            # Note: This should REGRESS the clock (improvement), handled in DM logic
            triggers.append(('Communal Stability', -1, "Bonds stabilized"))

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

    # Explicit void mentions
    if '+1 void' in narration_lower or 'void +1' in narration_lower:
        void_change += 1
        reasons.append("Explicit void gain mentioned")

    if '+2 void' in narration_lower or 'void +2' in narration_lower:
        void_change += 2
        reasons.append("Major void gain mentioned")

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
    resolution: Dict
) -> Dict[str, any]:
    """
    Parse complete state changes from a resolution.

    Args:
        narration: DM's narrative text
        action: Original action dict
        resolution: Resolution data (outcome_tier, margin, etc.)

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

    # Parse clock triggers
    clock_triggers = parse_clock_triggers(narration, outcome_tier, margin)
    state_changes['clock_triggers'] = clock_triggers

    # Parse void triggers
    void_change, void_reasons = parse_void_triggers(narration, intent, outcome_tier)
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
