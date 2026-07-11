"""
YAGS mechanical resolution system for Aeonisk multi-agent gameplay.
Implements core dice mechanics, rituals, void progression, and scene clocks.
"""

import random
import logging
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .constants import YAGS_ATTRIBUTES
from .schemas.shared_types import RollModifier

logger = logging.getLogger(__name__)


def _resolution_success(resolution) -> bool:
    """
    Safely check if ActionResolution succeeded.

    Handles both old dataclass (has .success field) and new Pydantic schema (has .success_tier enum).
    For new schema, success = success_tier in (MODERATE, GOOD, EXCELLENT, EXCEPTIONAL).
    """
    # Old schema: has .success field
    if hasattr(resolution, 'success'):
        return resolution.success

    # New schema: derive from success_tier
    if hasattr(resolution, 'success_tier'):
        from .schemas.action_resolution import SuccessTier
        success_tiers = {SuccessTier.MODERATE, SuccessTier.GOOD, SuccessTier.EXCELLENT, SuccessTier.EXCEPTIONAL, SuccessTier.MARGINAL}
        return resolution.success_tier in success_tiers

    # Fallback: assume success if we can't determine
    return True


def is_knowledge_skill(skill_name: Optional[str]) -> bool:
    """
    Check if a skill is a Knowledge skill (cannot be used untrained per YAGS rules).

    Knowledge skills require training (skill >= 1) to attempt.
    Standard skills can be attempted untrained with d20 ÷ 2.

    Knowledge skills: Magic Theory, Ritual Lore, Science, History, Area Lore,
                      Void Theory, Debt Law
    """
    if not skill_name:
        return False
    try:
        from .skill_descriptions import SKILL_DATABASE
        from .skill_mapping import normalize_skill
        normalized = normalize_skill(skill_name)
        if normalized and normalized in SKILL_DATABASE:
            return SKILL_DATABASE[normalized].category == "Knowledge"
        # Also check unnormalized
        if skill_name in SKILL_DATABASE:
            return SKILL_DATABASE[skill_name].category == "Knowledge"
    except ImportError:
        logger.warning("skill_descriptions not available for Knowledge skill check")
    return False


# Import energy economy types for seed attunement
try:
    from .energy_economy import SeedType, Element, Seed, Vendor, VendorItem, VendorType
except ImportError:
    logger.warning("energy_economy module not found, seed attunement will not be available")
    SeedType = None
    Element = None
    Seed = None
    Vendor = None
    VendorItem = None
    VendorType = None


@dataclass
class PurchaseValidation:
    """
    Result of pre-purchase validation check.

    Used to validate purchase requests BEFORE calling the DM, preventing
    LLM hallucinations about successful purchases when player lacks funds.
    """
    is_valid: bool
    failure_reason: Optional[str] = None
    shortage: Optional[Dict[str, int]] = None  # {currency_type: amount_short}
    sc_blocked: bool = False  # True if purchase blocked by Soulcredit threshold
    vendor_accessible: bool = True  # True if vendor exists and is accessible
    # New fields for mechanical purchase system
    can_afford: bool = False  # Alias for is_valid
    item_name: str = ""
    inventory_key: str = ""
    cost: Dict[str, int] = field(default_factory=dict)
    player_currency: Dict[str, int] = field(default_factory=dict)
    surplus: Optional[Dict[str, int]] = None  # How much extra currency player has

    def __post_init__(self):
        """Sync can_afford with is_valid."""
        self.can_afford = self.is_valid


@dataclass
class CheckpointAccess:
    """Result of a checkpoint / sector access check (Codex Nexum VIII.1-VIII.2)."""
    is_allowed: bool
    checkpoint_name: str = ""
    sc_blocked: bool = False
    failure_reason: Optional[str] = None


@dataclass
class TransferValidation:
    """
    Result of pre-transfer validation check.

    Used to validate energy transfers and item transfers BEFORE calling the DM,
    preventing impossible transfers (out of range, insufficient currency/items, etc.).
    """
    is_valid: bool
    failure_reason: Optional[str] = None
    sender_name: str = ""
    receiver_name: str = ""
    receiver_agent_id: str = ""
    currency: Dict[str, int] = field(default_factory=dict)
    items: Dict[str, int] = field(default_factory=dict)
    shortage: Optional[Dict[str, int]] = None  # {currency_type: amount_short}
    item_shortage: Optional[Dict[str, int]] = None  # {item_name: amount_short}
    sender_currency: Dict[str, int] = field(default_factory=dict)
    sender_items: Dict[str, int] = field(default_factory=dict)
    in_range: bool = False  # True if characters are in same range band


@dataclass
class AttunementValidation:
    """
    Result of pre-attunement validation check.

    Used to validate seed attunement requests BEFORE calling the DM,
    preventing impossible attunements (no seeds, missing altar, insufficient upkeep, etc.).
    """
    is_valid: bool
    failure_reason: Optional[str] = None
    has_raw_seed: bool = False
    target_energy: Optional[str] = None
    # Altar-specific fields
    altar_exists: bool = False
    altar_bonus: int = 0  # Bonus from altar quality (+1-3)
    altar_id: Optional[str] = None
    # Echo-Calibrator fields
    has_echo_calibrator: bool = False
    upkeep_required: bool = False
    has_upkeep_currency: bool = False
    usage_count: int = 0


@dataclass
class ConsumptionValidation:
    """
    Result of pre-consumption validation check.

    Used to validate food consumption requests BEFORE calling the DM,
    preventing impossible consumption (no item, not food, already at full HP, etc.).
    """
    is_valid: bool
    failure_reason: Optional[str] = None


@dataclass
class DiscoveryValidation:
    """
    Result of item discovery validation check.

    Used to validate discovery requests BEFORE applying ItemEffect,
    preventing abuse (daily limits exceeded, invalid source, etc.).

    Configurable limits via session config:
    - discovery_limits.max_seeds_per_session (default: 3)
    - discovery_limits.max_currency_per_session (default: 50 drip)
    - discovery_limits.quest_rewards_bypass_limits (default: True)
    """
    is_valid: bool
    failure_reason: Optional[str] = None
    capped_items: Optional[Dict[str, int]] = None  # Items after applying limits


class OutcomeTier(Enum):
    """Outcome quality tiers based on margin of success."""
    CRITICAL_FAILURE = "critical_failure"  # -20 or worse
    FAILURE = "failure"  # Below target
    MARGINAL = "marginal"  # 0-4 over target
    MODERATE = "moderate"  # 5-9 over target
    GOOD = "good"  # 10-14 over target
    EXCELLENT = "excellent"  # 15-19 over target
    EXCEPTIONAL = "exceptional"  # 20+ over target


class Difficulty(Enum):
    """
    Standard difficulty ratings (YAGS canonical + Aeonisk calibration).

    Codex Nexum guidance: Routine/pressured checks 18-22; only 26+ for extreme, multi-stage actions.
    """
    TRIVIAL = 10          # Nearly automatic for skilled characters
    EASY = 15             # Low-risk, straightforward actions
    ROUTINE = 18          # Standard pressured action (combat-pace, time-sensitive)
    MODERATE = 20         # Default for uncertain outcomes
    CHALLENGING = 22      # Requires focus and skill
    DIFFICULT = 26        # Extreme, multi-stage, or dangerous
    VERY_DIFFICULT = 30   # Legendary, desperate, or void-corrupted
    FORMIDABLE = 35       # Nearly impossible without preparation
    LEGENDARY = 40        # Requires exceptional circumstances


class JSONLLogger:
    """
    Machine-readable event logger for Aeonisk YAGS sessions.

    Codex Nexum guidance: "JSONL events alongside prose" for observability and replay.
    Each line is a complete JSON object representing one game event.
    """

    def __init__(self, session_id: str, output_dir: str = "./output", config: Dict[str, Any] = None, random_seed: Optional[int] = None):
        self.session_id = session_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.log_file = self.output_dir / f"session_{session_id}.jsonl"

        # Event causal chain tracking
        self.current_parent_event_id: Optional[str] = None  # Last event ID (for parent_event_id)
        self.current_correlation_id: Optional[str] = None  # Current round/group ID

        # Get git commit hash for reproducibility tracking
        git_commit = self._get_git_commit()

        # Initialize log file with session start event
        session_start_event = {
            "event_type": "session_start",
            "event_id": str(uuid.uuid4()),  # Generate unique event ID
            "parent_event_id": None,  # Root event has no parent
            "correlation_id": None,  # Session start not part of a round
            "ts": datetime.now().isoformat(),
            "session": session_id,
            "config": config or {},
            "random_seed": random_seed,  # For deterministic replay
            "git_commit": git_commit,  # Track codebase version
            "version": "1.2.0"  # BREAKING CHANGE: Added event_id, parent_event_id, correlation_id
        }
        self._write_event(session_start_event)
        self.current_parent_event_id = session_start_event["event_id"]  # Session start is parent of first events

    def _get_git_commit(self) -> Optional[str]:
        """Get current git commit hash for version tracking.

        Appends '-dirty' when the working tree has uncommitted changes, so the stamp
        cannot silently claim a clean commit that the running code did not match. A
        bare short SHA therefore reliably means "generated from exactly that commit";
        a '-dirty' suffix means the code had local modifications on top of it.
        """
        import subprocess
        repo_root = Path(__file__).parent.parent.parent.parent  # Go up to repo root
        try:
            # Get short commit hash (first 7 chars)
            result = subprocess.run(
                ['git', 'rev-parse', '--short', 'HEAD'],
                capture_output=True,
                text=True,
                timeout=1,
                cwd=repo_root
            )
            if result.returncode == 0:
                commit = result.stdout.strip()
                # Flag a dirty working tree so the version stamp stays trustworthy
                status = subprocess.run(
                    ['git', 'status', '--porcelain'],
                    capture_output=True,
                    text=True,
                    timeout=1,
                    cwd=repo_root
                )
                if status.returncode == 0 and status.stdout.strip():
                    commit += '-dirty'
                return commit
        except Exception:
            pass
        return None

    def start_round(self, round_num: int):
        """Start a new round - sets correlation_id for all events in this round."""
        self.current_correlation_id = f"round_{round_num}_{uuid.uuid4().hex[:8]}"

    def _add_event_chain_fields(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add event_id, parent_event_id, correlation_id to event.

        Returns modified event dict.
        """
        # Generate new event ID
        event_id = str(uuid.uuid4())
        event["event_id"] = event_id

        # Set parent (previous event)
        event["parent_event_id"] = self.current_parent_event_id

        # Set correlation (current round/group)
        event["correlation_id"] = self.current_correlation_id

        # Update parent for next event
        self.current_parent_event_id = event_id

        return event

    def _write_event(self, event: Dict[str, Any]):
        """Write a single event as a JSON line with causal chain metadata."""
        # Add event chain fields if not already present (session_start sets them manually)
        if "event_id" not in event:
            event = self._add_event_chain_fields(event)

        with open(self.log_file, 'a') as f:
            f.write(json.dumps(event, default=str) + '\n')
            f.flush()  # Force flush to prevent partial writes on interrupts

    def write_event(self, event: Dict[str, Any]):
        """Public method for writing custom events (used by LLMCallLogger)."""
        self._write_event(event)

    def calculate_outcome_tiers(self, resolution: 'ActionResolution') -> Dict[str, Dict[str, int]]:
        """
        Calculate hypothetical outcomes for all 6 tiers for ML training.

        Returns dict with tier names as keys, each containing:
        - dc_threshold: DC needed for this tier
        - margin_needed: Margin needed from actual roll
        - d20_needed: Minimum d20 roll needed from base ability

        The 6 tiers follow Aeonisk/YAGS guidelines:
        - critical_failure: Natural 1 or margin ≤ -10
        - failure: Roll < DC (margin -9 to -1)
        - moderate_success: Roll = DC (margin 0 to +4)
        - good_success: Roll = DC+10 (margin +5 to +9)
        - excellent_success: Roll = DC+20 (margin +10 to +14)
        - exceptional_success: Roll = DC+30+ (margin +15+)
        """
        # Defensive attribute access for old vs new ActionResolution schema
        attribute_value = getattr(resolution, 'attribute_value', 0)
        skill_value = getattr(resolution, 'skill_value', 0)
        skill = getattr(resolution, 'skill', None)
        difficulty = getattr(resolution, 'difficulty', 0)

        # Calculate ability based on YAGS Aeonisk v1.3.0 rules:
        # - Skilled: Attribute × Skill
        # - Unskilled (skill_value=0): ability is 0, d20 gets halved
        # - Raw attribute checks removed in v1.3.0
        if skill_value > 0:
            ability = attribute_value * skill_value
        else:
            # Unskilled - ability is 0, d20 gets halved
            ability = 0

        dc = difficulty

        tiers = {
            "critical_failure": {
                "dc_threshold": dc - 10,
                "margin_needed": -10,
                "d20_needed": max(1, dc - 10 - ability)  # Natural 1 is always crit fail
            },
            "failure": {
                "dc_threshold": dc - 1,
                "margin_needed": -1,
                "d20_needed": max(1, dc - 1 - ability)
            },
            "moderate_success": {
                "dc_threshold": dc,
                "margin_needed": 0,
                "d20_needed": max(1, dc - ability)
            },
            "good_success": {
                "dc_threshold": dc + 5,
                "margin_needed": 5,
                "d20_needed": max(1, dc + 5 - ability)
            },
            "excellent_success": {
                "dc_threshold": dc + 10,
                "margin_needed": 10,
                "d20_needed": max(1, dc + 10 - ability)
            },
            "exceptional_success": {
                "dc_threshold": dc + 15,
                "margin_needed": 15,
                "d20_needed": max(1, dc + 15 - ability)
            }
        }

        return tiers

    def log_action_resolution(
        self,
        round_num: int,
        phase: str,
        agent_name: str,
        action: str,
        resolution: 'ActionResolution',
        economy_changes: Dict[str, Any],
        clock_states: Dict[str, str],
        effects: List[str],
        context: Dict[str, Any] = None,
        inventory_changes: List[Dict[str, Any]] = None,
        purchase_data: Dict[str, Any] = None,
        crafting_data: Dict[str, Any] = None,
        attunement_data: Dict[str, Any] = None,
        currency_transfer_data: Dict[str, Any] = None,
        item_transfer_data: Dict[str, Any] = None,
        item_discovery_data: Dict[str, Any] = None,
        # New ML training fields (dataset guidelines compliance)
        # character_data removed - redundant with character_state events (saves ~7,200 tokens/session)
        environment: str = None,
        stakes: str = None,
        goal: str = None,
        roll_formula: str = None,
        rationale: str = None,
        outcome_tiers_with_narratives: Dict[str, Dict[str, str]] = None,
        aware_agents: List[str] = None
    ):
        """
        Log a complete action resolution event with 6-tier outcome analysis.

        Schema matches Codex Nexum specification plus 6-tier outcomes for ML training:
        {
          "ts": "ISO-8601",
          "session": "uuid",
          "round": 14,
          "phase": "declare|resolve",
          "agent": "Zara Nightwhisper",
          "action": "Resonance Barrier",
          "context": {"range": "Near", "cover": true, "stance": "braced"},
          "roll": {"attr": "Willpower", "attr_val": 3, "skill": "Astral Arts",
                   "skill_val": 2, "ability": 6, "d20": 12, "total": 18,
                   "dc": 20, "margin": -2, "tier": "Failure"},
          "outcome_tiers": {
            "critical_failure": {"dc_threshold": 10, "margin_needed": -10, "d20_needed": 4},
            "failure": {"dc_threshold": 19, "margin_needed": -1, "d20_needed": 13},
            ...
          },
          "economy": {"void_delta": +1, "soulcredit_delta": 0,
                      "offering_used": false, "bonds_applied": []},
          "clocks": {"core_access": "7/8", "infection": "2/6"},
          "effects": {
            "damage": {"target": "enemy_123", "dealt": 8},
            "status_effects": ["Barrier fails; backlash ripples"],
            "inventory_changes": [{"item": "incense", "delta": -1}],
            "purchase": {"success": true, "vendor_name": "S4CU", "items_purchased": ["Med Kit"], "currency_spent": {"spark": 1}},
            "crafting": {"offering_type": "blood_offering", "materials_used": ["blood_sample"], "success": true},
            "attunement": {"success": true, "energy_type": "drip", "amount": 20, "seed_consumed": "raw", "altar_id": "alt_test_basic"},
            "currency_transfer": {"from_character": "Ash", "to_character": "Echo", "drip": 15, "grain": 1, "purpose": "Pooling funds"},
            "item_transfer": {"from_character": "Ash", "to_character": "Echo", "items": {"Medkit": 2}, "purpose": "Sharing supplies"}
          }
        }
        """
        # Use cached ability from ActionResolution (calculated once in resolve_action)
        # Fallback to recalculation for backward compatibility with old resolutions
        skill = getattr(resolution, 'skill', None)
        skill_value = getattr(resolution, 'skill_value', 0)
        attribute_value = getattr(resolution, 'attribute_value', 0)
        ability = getattr(resolution, 'ability', None)

        if ability is None:
            # Fallback for old ActionResolution objects without ability field
            if skill and skill_value > 0:
                ability = attribute_value * skill_value
            else:
                ability = 0

        # Calculate 6-tier outcomes for ML training (threshold-based for backward compat)
        outcome_tiers = self.calculate_outcome_tiers(resolution)

        # Extract damage from context if available (from structured output)
        damage_dealt = None
        if context and context.get('damage_effects'):
            # Get first damage effect (single-target actions)
            damage_data = context['damage_effects'][0]
            damage_dealt = {
                "target": damage_data.get('target'),
                "dealt": damage_data.get('dealt'),
                "source": "structured_output"
            }

        # Build roll dict with defensive attribute access (handles both old dataclass and new Pydantic schema)
        # Extract modifiers for ML training data
        modifiers_applied = getattr(resolution, 'modifiers_applied', [])
        modifiers_list = [m.model_dump() if hasattr(m, 'model_dump') else {"source": m.source, "value": m.value, "details": m.details} for m in modifiers_applied]
        modifier_total = sum(m.value for m in modifiers_applied) if modifiers_applied else 0

        roll_dict = {
            "attr": getattr(resolution, 'attribute', None),
            "attr_val": attribute_value,
            "skill": skill,
            "skill_val": skill_value,
            "ability": ability,
            "d20": getattr(resolution, 'roll', None),
            "modifiers": modifiers_list if modifiers_list else None,  # List of applied modifiers for ML training
            "modifier_total": modifier_total if modifiers_list else None,  # Sum of all modifiers
            "total": getattr(resolution, 'total', None),
            "dc": getattr(resolution, 'difficulty', None),
            "margin": getattr(resolution, 'margin', 0),
            "tier": getattr(resolution.outcome_tier, 'value', None) if hasattr(resolution, 'outcome_tier') else None,
            "success": getattr(resolution, 'success', None)
        }

        event = {
            "event_type": "action_resolution",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "phase": phase,
            "agent": agent_name,
            "action": action,
            "context": context or {},
            "roll": roll_dict,
            "outcome_tiers": outcome_tiers,  # Threshold-based (backward compat)
            "economy": economy_changes,
            "clocks": clock_states,
            "effects": {
                "damage": damage_dealt,  # NEW: Damage dealt to targets (for ML training)
                "status_effects": effects,  # Renamed from top-level effects for clarity
                "inventory_changes": inventory_changes or [],  # New: track offering consumption, item pickups, etc.
                "purchase": purchase_data,  # Purchase transaction details (vendor, items, currency)
                "crafting": crafting_data,  # Crafting attempt details (offering type, materials, success)
                "attunement": attunement_data,  # Attunement ritual details (energy type, amount, seed consumed, altar)
                "currency_transfer": currency_transfer_data,  # Currency transfer details (from, to, amounts, purpose)
                "item_transfer": item_transfer_data,  # Item transfer details (from, to, items, purpose)
                "item_discovery": item_discovery_data  # Item discovery (seeds, currency, items found via investigate/social)
            }
        }

        # Add ML training fields if provided (dataset guidelines compliance)
        # character_data removed - redundant with character_state events

        if environment:
            event["environment"] = environment

        if stakes:
            event["stakes"] = stakes

        if goal:
            event["goal"] = goal

        if roll_formula:
            event["roll_formula"] = roll_formula

        if rationale:
            event["rationale"] = rationale

        if outcome_tiers_with_narratives:
            # Full outcome tiers with narrative + mechanical_effect (dataset format)
            event["outcome_tiers_full"] = outcome_tiers_with_narratives

        if aware_agents is not None:
            # Stealth/secrets visibility control - which agents know about this action
            event["aware_agents"] = aware_agents

        self._write_event(event)

    def log_enemy_action(
        self,
        round_num: int,
        enemy_id: str,
        enemy_name: str,
        action_type: str,
        result: str,
        narration: str,
        target_id: str = None,
        target_name: str = None,
        damage_dealt: int = None,
        roll_data: Dict[str, Any] = None,
        effects: Dict[str, Any] = None
    ):
        """
        DEPRECATED: Use log_combat_action() instead.

        This method produces action_resolution events with null skill data,
        duplicating the combat_action events logged by enemy_combat.py.

        Args:
            round_num: Current round number
            enemy_id: Enemy agent ID
            enemy_name: Enemy display name
            action_type: Type of action (attack, suppress, flee, charge, etc.)
            result: Result string (success, miss, hit, invalid target, etc.)
            narration: Narrative description of the action
            target_id: Target agent ID (if applicable)
            target_name: Target display name (if applicable)
            damage_dealt: Damage dealt (if combat action)
            roll_data: Roll details if available (d20, total, dc, etc.)
            effects: Additional effects (status changes, positioning, etc.)
        """
        import warnings
        warnings.warn(
            "log_enemy_action() is deprecated. Use log_combat_action() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        event = {
            "event_type": "action_resolution",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "phase": "enemy_execution",
            "agent": enemy_name,
            "action": narration[:200] if narration else action_type,  # Truncate for consistency
            "context": {
                "action_type": action_type,
                "is_enemy": True,
                "enemy_id": enemy_id,
                "result": result
            },
            "roll": roll_data or {
                "attr": None,
                "attr_val": 0,
                "skill": None,
                "skill_val": 0,
                "ability": 0,
                "d20": None,
                "total": None,
                "dc": None,
                "margin": 0,
                "tier": None,
                "success": result in ('success', 'hit')
            },
            "outcome_tiers": {},  # No tier calculation for enemies (fixed behaviors)
            "economy": {},
            "clocks": {},
            "effects": {
                "damage": {"target": target_id, "dealt": damage_dealt, "target_name": target_name} if damage_dealt else None,
                "status_effects": effects.get('status_effects', []) if effects else [],
                "inventory_changes": [],
                "purchase": None,
                "crafting": None,
                "attunement": None,
                "currency_transfer": None,
                "item_transfer": None,
                "item_discovery": None
            }
        }
        self._write_event(event)

    def log_clock_event(
        self,
        round_num: int,
        clock_name: str,
        old_value: int,
        new_value: int,
        maximum: int,
        filled: bool,
        reason: str
    ):
        """Log a clock advancement event."""
        event = {
            "event_type": "clock_advancement",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "clock_name": clock_name,
            "old_value": old_value,
            "new_value": new_value,
            "maximum": maximum,
            "filled": filled,
            "reason": reason
        }
        self._write_event(event)

    def log_void_change(
        self,
        round_num: int,
        agent_name: str,
        old_void: int,
        new_void: int,
        delta: int,
        reason: str,
        capped: bool = False
    ):
        """Log a void corruption change event."""
        event = {
            "event_type": "void_change",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "agent": agent_name,
            "old_void": old_void,
            "new_void": new_void,
            "delta": delta,
            "reason": reason,
            "capped": capped
        }
        self._write_event(event)

    def log_scenario(self, scenario: Dict[str, Any]):
        """Log scenario setup."""
        event = {
            "event_type": "scenario",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "scenario": scenario
        }
        self._write_event(event)

    def log_round_start(self, round_num: int):
        """Log round start event."""
        event = {
            "event_type": "round_start",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num
        }
        self._write_event(event)

    def log_session_end(self, final_state: Dict[str, Any], termination_reason: str = "completed"):
        """Log session end event with final state.

        Args:
            final_state: Final game state summary
            termination_reason: One of "completed", "interrupted", "crashed", "timeout"
        """
        event = {
            "event_type": "session_end",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "termination_reason": termination_reason,
            "final_state": final_state
        }
        self._write_event(event)

    def log_session_termination(self, reason: str, details: Optional[str] = None):
        """Log session termination when session_end wasn't reached normally.

        This is called from signal handlers or exception handlers to record
        why the session ended prematurely.

        Args:
            reason: One of "interrupted", "crashed", "timeout"
            details: Optional error message or context
        """
        event = {
            "event_type": "session_end",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "termination_reason": reason,
            "final_state": {
                "premature_termination": True,
                "reason": reason,
                "details": details
            }
        }
        self._write_event(event)

    def log_session_error(
        self,
        error_type: str,
        error_message: str,
        exception_type: str,
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = False
    ):
        """Log a fatal or significant error during the session.

        This is called when an agent encounters an error that affects session flow.
        Used for debugging and for bulk runner error detection.

        Args:
            error_type: Category of error (e.g., "adjudication_failure", "llm_error")
            error_message: Human-readable error description
            exception_type: Python exception class name
            context: Optional dict with additional context (round, agent_id, etc.)
            recoverable: Whether the session can continue after this error
        """
        event = {
            "event_type": "session_error",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "error_type": error_type,
            "error_message": error_message,
            "exception_type": exception_type,
            "context": context or {},
            "recoverable": recoverable,
            "round": context.get('round') if context else None
        }
        self._write_event(event)

    def log_debrief(self, character_name: str, debrief_text: str, character_state: Dict[str, Any]):
        """Log mission debrief statement from a character."""
        event = {
            "event_type": "mission_debrief",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "character": character_name,
            "debrief": debrief_text,
            "final_state": character_state
        }
        self._write_event(event)

    def log_declaration_phase_start(self, round_num: int):
        """Log start of declaration phase."""
        event = {
            "event_type": "declaration_phase_start",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num
        }
        self._write_event(event)

    def log_difficulty_assessment(self, round_num: int,
                                  assessments: List[Dict[str, Any]],
                                  changes: List[str]):
        """Log the DM's round-batch difficulty/framing assessment.

        Each assessment entry carries the DM's ruling alongside the
        player's counterfactual estimate for calibration analysis.
        """
        event = {
            "event_type": "difficulty_assessment",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "assessments": assessments,
            "changes": changes
        }
        self._write_event(event)

    def log_action_declaration(self, player_id: str, character_name: str, initiative: int, action: Dict[str, Any], round_num: int):
        """Log individual action declaration."""
        event = {
            "event_type": "action_declaration",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "player_id": player_id,
            "character_name": character_name,
            "initiative": initiative,
            "action": action
        }
        self._write_event(event)

    def log_adjudication_start(self, round_num: int, action_count: int):
        """Log start of adjudication phase."""
        event = {
            "event_type": "adjudication_start",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "action_count": action_count
        }
        self._write_event(event)

    def log_clock_spawn(
        self,
        clock_name: str,
        max_ticks: int,
        description: str,
        round_num: Optional[int] = None,
        current_ticks: int = 0,
        advance_meaning: Optional[str] = None,
        regress_meaning: Optional[str] = None,
        filled_consequence: Optional[str] = None
    ):
        """
        Log spawning of a new scene clock.

        Args:
            clock_name: Clock identifier
            max_ticks: Maximum ticks before fill
            description: What the clock represents
            round_num: Round when clock was created (None for session start)
            current_ticks: Starting tick value (default 0)
            advance_meaning: What advancing the clock represents
            regress_meaning: What regressing the clock represents
            filled_consequence: What happens when clock fills
        """
        event = {
            "event_type": "clock_spawn",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "clock_name": clock_name,
            "max_ticks": max_ticks,
            "current_ticks": current_ticks,
            "description": description
        }

        # Add semantic fields if provided
        if advance_meaning:
            event["advance_meaning"] = advance_meaning
        if regress_meaning:
            event["regress_meaning"] = regress_meaning
        if filled_consequence:
            event["filled_consequence"] = filled_consequence

        self._write_event(event)

    def log_synthesis(self, round_num: int, synthesis: str, structured_synthesis=None):
        """Log round synthesis narrative and optional structured data.

        Args:
            round_num: Current round number
            synthesis: Narrative text from DM
            structured_synthesis: Optional RoundSynthesis Pydantic model with
                                story_advancement, scene_pivot, enemy_spawns, etc.
        """
        event = {
            "event_type": "round_synthesis",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "synthesis": synthesis
        }

        # Add structured fields if available
        if structured_synthesis:
            # Add story_advancement if present
            if structured_synthesis.story_advancement and structured_synthesis.story_advancement.should_advance:
                event["story_advancement"] = {
                    "should_advance": True,
                    "location": structured_synthesis.story_advancement.location,
                    "situation": structured_synthesis.story_advancement.situation,
                    "new_void_level": structured_synthesis.story_advancement.new_void_level,
                    "clear_all_enemies": structured_synthesis.story_advancement.clear_all_enemies,
                    "new_clocks": [clock.model_dump() for clock in structured_synthesis.story_advancement.new_clocks]
                }

            # Add scene_pivot if present
            if structured_synthesis.scene_pivot and structured_synthesis.scene_pivot.should_pivot:
                event["scene_pivot"] = {
                    "should_pivot": True,
                    "new_room": structured_synthesis.scene_pivot.new_room,
                    "situation_change": structured_synthesis.scene_pivot.situation_change,
                    "clear_specific_clocks": structured_synthesis.scene_pivot.clear_specific_clocks,
                    "new_clocks": [clock.model_dump() for clock in structured_synthesis.scene_pivot.new_clocks]
                }

            # NOTE: Enemy/NPC management fields removed from RoundSynthesis
            # (moved to Entity Lifecycle Phase)
            # These are now in ConversionDecisions and logged via entity_lifecycle event

            # Add clock lifecycle fields
            if structured_synthesis.clocks_filled:
                event["clocks_filled"] = structured_synthesis.clocks_filled

            if structured_synthesis.clocks_expired:
                event["clocks_expired"] = structured_synthesis.clocks_expired

            # Add session end fields
            if structured_synthesis.session_end:
                event["session_end"] = structured_synthesis.session_end
                if structured_synthesis.session_end_reason:
                    event["session_end_reason"] = structured_synthesis.session_end_reason

        self._write_event(event)

    def log_event(self, event_type: str, data: Dict[str, Any], round_num: int):
        """Log generic game event (cleanup, enemy events, etc)."""
        event = {
            "event_type": event_type,
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "data": data
        }
        self._write_event(event)

    def log_combat_action(
        self,
        round_num: int,
        attacker_id: str,
        attacker_name: str,
        defender_id: str,
        defender_name: str,
        weapon: str,
        attack_roll: Dict[str, Any],
        damage_roll: Optional[Dict[str, Any]] = None,
        wounds_dealt: int = 0,
        defender_state_after: Optional[Dict[str, Any]] = None
    ):
        """
        Log a combat action (attack with damage).

        Args:
            round_num: Current round
            attacker_id: Agent ID of attacker
            attacker_name: Display name of attacker
            defender_id: Agent ID of defender
            defender_name: Display name of defender
            weapon: Weapon/ability used
            attack_roll: Dict with keys: attr, skill, d20, total, dc, hit, margin
            damage_roll: Optional dict with keys: strength, weapon_dmg, d20, total, soak, dealt
            wounds_dealt: Number of wounds inflicted
            defender_state_after: Optional dict with keys: health, max_health, wounds, alive, status
        """
        event = {
            "event_type": "combat_action",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "attacker": {"id": attacker_id, "name": attacker_name},
            "defender": {"id": defender_id, "name": defender_name},
            "weapon": weapon,
            "attack": attack_roll,
            "damage": damage_roll,
            "wounds_dealt": wounds_dealt,
            "defender_state_after": defender_state_after
        }
        self._write_event(event)

    def log_character_state(
        self,
        round_num: int,
        character_id: str,
        character_name: str,
        health: int,
        max_health: int,
        wounds: int,
        void_score: int,
        soulcredit: int,
        position: str,
        conditions: List[str] = None,
        is_defeated: bool = False,
        death_state: str = "alive",
        agent: str = 'player',
        energy: Dict[str, int] = None,
        seeds: Dict[str, int] = None,
        stuns: int = 0
    ):
        """
        Log character state snapshot (typically at round end).

        Args:
            round_num: Current round
            character_id: Agent ID
            character_name: Display name
            health: Current health
            max_health: Maximum health
            wounds: Wound count
            void_score: Current void corruption (0-10)
            soulcredit: Current soulcredit balance
            position: Tactical position (e.g., "Near-PC")
            conditions: List of active conditions (debuffs, buffs)
            is_defeated: Whether character is defeated
            death_state: "alive", "unconscious" (0 HP, wounds < 6, or stuns >= 6), or "dead" (wounds >= 6)
            agent: Agent type ('player', 'enemy', 'npc') for filtering in analysis
            energy: Currency amounts {"breath": 5, "drip": 10, "grain": 3, "spark": 2, "hollow": 0}
            seeds: Seed counts {"raw": 2, "attuned": 1, "hollow": 0}
            stuns: Stun count (separate from wounds; >= 6 is the Beaten/KO threshold that
                   drives death_state="unconscious"). Logged so a stun-KO snapshot is
                   diagnosable — without it, is_defeated=True at full health looks impossible.
        """
        event = {
            "event_type": "character_state",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "character_id": character_id,
            "character_name": character_name,
            "health": health,
            "max_health": max_health,
            "wounds": wounds,
            "void_score": void_score,
            "soulcredit": soulcredit,
            "position": position,
            "conditions": conditions or [],
            "is_defeated": is_defeated,
            "death_state": death_state,  # NEW: Track death vs unconscious
            "stuns": stuns,  # Separate from wounds; >= 6 drives stun-KO (Beaten threshold)
            "agent": agent,
            "energy": energy or {},
            "seeds": seeds or {}
        }
        self._write_event(event)

    def log_enemy_spawn(
        self,
        round_num: int,
        enemy_id: str,
        enemy_name: str,
        template: str,
        stats: Dict[str, Any],
        position: str,
        tactics: str,
        count: int = 1,
        faction: str = "Unknown"
    ):
        """
        Log enemy spawn event.

        Args:
            round_num: Current round
            enemy_id: Unique enemy agent ID
            enemy_name: Display name
            template: Enemy template (grunt, elite, boss, etc.)
            stats: Dict with health, attributes, skills, weapons, armor
            position: Spawn position
            tactics: Tactical behavior (aggressive_melee, tactical_ranged, etc.)
            count: Number of enemies spawned in this group (1-5)
            faction: Enemy faction (e.g., "ACG", "Pantheon Security")
        """
        event = {
            "event_type": "enemy_spawn",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "enemy_id": enemy_id,
            "enemy_name": enemy_name,
            "template": template,
            "faction": faction,
            "stats": stats,
            "position": position,
            "tactics": tactics,
            "count": count
        }
        self._write_event(event)

    def log_enemy_defeat(
        self,
        round_num: int,
        enemy_id: str,
        enemy_name: str,
        defeat_reason: str,
        rounds_survived: int,
        killer_id: str = None,
        killer_name: str = None,
        final_damage: int = None
    ):
        """
        Log enemy defeat/removal.

        Args:
            round_num: Current round
            enemy_id: Enemy agent ID
            enemy_name: Display name
            defeat_reason: Reason for defeat (killed, retreated, despawned, escaped, fled, subdued, convinced)
            rounds_survived: Number of rounds enemy was active
            killer_id: ID of agent who dealt killing blow (for killed defeats)
            killer_name: Name of agent who dealt killing blow
            final_damage: Damage from killing blow
        """
        event = {
            "event_type": "enemy_defeat",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "enemy_id": enemy_id,
            "enemy_name": enemy_name,
            "defeat_reason": defeat_reason,
            "rounds_survived": rounds_survived
        }
        # Add optional killer info for combat kills
        if killer_id:
            event["killer_id"] = killer_id
        if killer_name:
            event["killer_name"] = killer_name
        if final_damage is not None:
            event["final_damage"] = final_damage
        self._write_event(event)

    def log_npc_departure(
        self,
        round_num: int,
        npc_id: str,
        npc_name: str,
        departure_reason: str
    ):
        """
        Log NPC departure/removal from scene.

        Args:
            round_num: Current round
            npc_id: NPC agent ID
            npc_name: Display name
            departure_reason: Reason for departure (fled, hidden, dismissed, left, story_advanced)
        """
        event = {
            "event_type": "npc_departure",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "npc_id": npc_id,
            "npc_name": npc_name,
            "departure_reason": departure_reason
        }
        self._write_event(event)

    def log_agent_conversion(
        self,
        round_num: int,
        agent_id: str,
        agent_name: str,
        from_type: str,
        to_type: str,
        trigger: str,
        state_before: Dict[str, Any],
        state_after: Dict[str, Any]
    ):
        """
        Log agent type conversion (NPC ↔ enemy).

        Args:
            round_num: Current round
            agent_id: Agent ID (stable across conversions)
            agent_name: Display name
            from_type: Original type ("npc" or "enemy")
            to_type: New type ("enemy" or "npc")
            trigger: Reason for conversion ("escalation", "surrender", "intimidation", etc.)
            state_before: State snapshot before conversion (health, wounds, etc.)
            state_after: State snapshot after conversion
        """
        event = {
            "event_type": "agent_conversion",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "from_type": from_type,
            "to_type": to_type,
            "trigger": trigger,
            "state_before": state_before,
            "state_after": state_after
        }
        self._write_event(event)

    def log_targeting_validation(
        self,
        round_num: int,
        agent_id: str,
        original_target: str,
        corrected_target: Optional[str],
        correction_method: str,
        triggered_by: str,
        success: bool,
        confidence: Optional[str] = None,
        reasoning: Optional[str] = None,
        error: Optional[str] = None,
        declared_target: Optional[str] = None,
        effect_type: str = "damage",
        model_used: Optional[str] = None,
        validation_time_ms: Optional[float] = None
    ):
        """
        Log targeting validation event (triggered when DM targeting errors detected).

        Args:
            round_num: Current round
            agent_id: Agent whose action triggered validation
            original_target: Target ID/name in DM's output (invalid)
            corrected_target: Corrected target ID (if successful)
            correction_method: 'mechanical', 'llm_inference', or 'failed'
            triggered_by: Error type ('missing_target', 'invalid_format', 'name_instead_of_id', 'unresolvable_id')
            success: Whether targeting was successfully corrected
            confidence: LLM confidence level ('high', 'medium', 'low') if using LLM
            reasoning: LLM's reasoning for correction if using LLM
            error: Error description if correction failed
            declared_target: Target from action declaration (for comparison)
            effect_type: Type of effect ('damage', 'healing', 'void_change', etc.)
            model_used: LLM model used for correction ('claude-haiku-4', etc.)
            validation_time_ms: Time taken for validation (milliseconds)
        """
        event = {
            "event_type": "targeting_validation",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "agent_id": agent_id,
            "original_target": original_target,
            "declared_target": declared_target,
            "original_effect_type": effect_type,
            "triggered_by": triggered_by,
            "correction_method": correction_method,
            "corrected_target": corrected_target,
            "model_used": model_used,
            "confidence": confidence,
            "reasoning": reasoning,
            "success": success,
            "error_description": error,
            "validation_time_ms": validation_time_ms
        }
        self._write_event(event)

    def log_round_summary(
        self,
        round_num: int,
        summary: Dict[str, Any]
    ):
        """
        Log aggregated round statistics for balance analysis.

        Args:
            round_num: Current round
            summary: Dict with aggregate metrics:
                - action_count: Total actions attempted
                - success_count: Actions that succeeded
                - success_rate: Percentage of successful actions
                - avg_margin: Average success margin
                - damage_dealt_by_players: Total damage dealt by players
                - damage_taken_by_players: Total damage taken by players
                - void_gained: Total void gained this round
                - void_lost: Total void lost this round
                - clocks_advanced: Number of clocks that advanced this round
                - clocks_regressed: Number of clocks that regressed this round
                - clocks_filled: Number of clocks that filled
                - total_ticks_advanced: Total ticks advanced across all clocks
                - total_ticks_regressed: Total ticks regressed across all clocks
                - active_enemies: Enemy count at round end
                - player_wounds_total: Sum of all player wounds
        """
        event = {
            "event_type": "round_summary",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "actions_attempted": summary.get('actions_attempted', 0),
            "success_count": summary.get('success_count', 0),
            "success_rate": summary.get('success_rate', 0.0),
            "average_margin": summary.get('avg_margin', 0.0),
            "damage_dealt_by_players": summary.get('damage_dealt_by_players', 0),
            "damage_taken_by_players": summary.get('damage_taken_by_players', 0),
            "void_gained": summary.get('void_gained', 0),
            "void_lost": summary.get('void_lost', 0),
            "clocks_advanced": summary.get('clocks_advanced', 0),
            "clocks_regressed": summary.get('clocks_regressed', 0),
            "clocks_filled": summary.get('clocks_filled', 0),
            "total_ticks_advanced": summary.get('total_ticks_advanced', 0),
            "total_ticks_regressed": summary.get('total_ticks_regressed', 0),
            "active_enemies": summary.get('active_enemies', 0),
            "player_wounds_total": summary.get('player_wounds_total', 0)
        }
        self._write_event(event)

    def log_purchase_attempt(
        self,
        round_num: int,
        player_id: str,
        character_name: str,
        vendor_id: str,
        vendor_name: str,
        item_id: str,
        item_name: str,
        cost: Dict[str, int],
        player_currency: Dict[str, int],
        success: bool,
        failure_reason: Optional[str] = None,
        shortage: Optional[Dict[str, int]] = None
    ):
        """
        Log purchase attempt (both success and failure).

        Critical for ML training - logs ALL attempts, not just successes.

        Args:
            round_num: Current round
            player_id: Agent ID (e.g., 'player_mira')
            character_name: Character name (e.g., 'Mira Seln')
            vendor_id: Vendor ID (e.g., 'vnd_a1b2')
            vendor_name: Vendor name (e.g., 'Test Shop')
            item_id: Item ID (e.g., 'itm_c3d4')
            item_name: Item name (e.g., 'Health Kit')
            cost: Required currency (e.g., {'drip': 5, 'spark': 1})
            player_currency: Player's current currency (e.g., {'drip': 10, 'spark': 0})
            success: Whether purchase succeeded
            failure_reason: Why it failed (if applicable)
            shortage: How much short (if applicable)

        JSONL Schema:
        ```json
        {
          "event_type": "purchase_attempt",
          "ts": "2025-01-15T10:30:00",
          "session": "session_abc123",
          "round": 2,
          "player_id": "player_mira",
          "character_name": "Mira Seln",
          "vendor_id": "vnd_a1b2",
          "vendor_name": "Test Shop",
          "item_id": "itm_c3d4",
          "item_name": "Health Kit",
          "cost": {"drip": 5},
          "player_currency": {"spark": 0, "drip": 4},
          "success": false,
          "failure_reason": "Insufficient currency: need 5 Drip, have 4 Drip",
          "shortage": {"drip": 1}
        }
        ```
        """
        event = {
            "event_type": "purchase_attempt",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "player_id": player_id,
            "character_name": character_name,
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "item_id": item_id,
            "item_name": item_name,
            "cost": cost,
            "player_currency": player_currency,
            "success": success,
            "failure_reason": failure_reason,
            "shortage": shortage
        }
        self._write_event(event)

    def log_social_deescalation(
        self,
        round_num: int,
        player_id: str,
        player_name: str,
        enemy_id: str,
        enemy_name: str,
        action_type: str,  # "intimidation" or "persuasion"
        skill: str,  # "Intimidation" or "Persuasion"
        roll_total: int,
        dc: int,
        success: bool,
        margin: int,
        outcome: str,  # "surrender", "flee", "resist", "backfire"
        narration: str
    ):
        """
        Log social de-escalation attempt (intimidation/persuasion).

        Args:
            round_num: Current round
            player_id: Player agent ID
            player_name: Player character name
            enemy_id: Target enemy agent ID
            enemy_name: Target enemy name
            action_type: Type of social action ("intimidation", "persuasion")
            skill: Skill used (Intimidation, Persuasion)
            roll_total: Total roll result
            dc: Difficulty class
            success: Whether roll succeeded
            margin: Success margin (positive or negative)
            outcome: Result ("surrender", "flee", "resist", "backfire")
            narration: DM's narrative description
        """
        event = {
            "event_type": "social_deescalation",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "player_id": player_id,
            "player_name": player_name,
            "enemy_id": enemy_id,
            "enemy_name": enemy_name,
            "action_type": action_type,
            "skill": skill,
            "roll": {
                "total": roll_total,
                "dc": dc,
                "success": success,
                "margin": margin
            },
            "outcome": outcome,
            "narration": narration
        }
        self._write_event(event)

    def log_marker_retry(
        self,
        round_num: int,
        marker_type: str,
        invalid_markers: List[str],
        retry_prompt: str
    ):
        """
        Log when DM needs to retry generating a marker due to format errors.

        Args:
            round_num: Current round number
            marker_type: Type of marker ("SPAWN_ENEMY" or "ADVANCE_STORY")
            invalid_markers: List of incomplete marker contents
            retry_prompt: The prompt sent to LLM for retry
        """
        event = {
            "event_type": "marker_retry_attempt",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "marker_type": marker_type,
            "invalid_markers": invalid_markers,
            "retry_prompt": retry_prompt
        }
        self._write_event(event)

    def log_marker_retry_result(
        self,
        round_num: int,
        marker_type: str,
        retry_response: str,
        success: bool
    ):
        """
        Log result of marker retry attempt.

        Args:
            round_num: Current round number
            marker_type: Type of marker ("SPAWN_ENEMY" or "ADVANCE_STORY")
            retry_response: The LLM's corrected response
            success: Whether retry produced valid markers
        """
        event = {
            "event_type": "marker_retry_result",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "marker_type": marker_type,
            "retry_response": retry_response,
            "success": success
        }
        self._write_event(event)

    def log_structured_output_metrics(
        self,
        round_num: int,
        agent_type: str,
        agent_id: str,
        success: bool,
        fallback_triggered: bool,
        validation_warnings: List[str],
        completeness_score: Optional[float] = None
    ):
        """
        Log structured output quality metrics for ML analysis.

        Tracks how well agents are using Pydantic AI structured output vs
        falling back to text parsing or generating incomplete outputs.

        Args:
            round_num: Current round number
            agent_type: 'dm', 'player', or 'enemy'
            agent_id: Specific agent identifier
            success: Whether structured output was generated successfully
            fallback_triggered: Whether fallback system was invoked
            validation_warnings: List of validation warning messages
            completeness_score: Optional 0.0-1.0 score (1.0 = all expected fields populated)

        Example:
            ```python
            logger.log_structured_output_metrics(
                round_num=5,
                agent_type='dm',
                agent_id='dm_narrator',
                success=True,
                fallback_triggered=False,
                validation_warnings=["Missing soulcredit_changes field"],
                completeness_score=0.85
            )
            ```
        """
        event = {
            "event_type": "structured_output_metrics",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "agent_type": agent_type,
            "agent_id": agent_id,
            "structured_output_success": success,
            "fallback_triggered": fallback_triggered,
            "validation_warnings": validation_warnings,
            "validation_issues_count": len(validation_warnings),
            "completeness_score": completeness_score,
            "is_complete": len(validation_warnings) == 0 and not fallback_triggered
        }
        self._write_event(event)

    def log_pydantic_validation_failure(
        self,
        round_num: int,
        agent_type: str,
        agent_id: str,
        schema_name: str,
        exception_type: str,
        error_message: str,
        attempt_number: int,
        max_attempts: int,
        raw_model_response: Optional[str] = None,
        underlying_error: Optional[str] = None,
        action_context: Optional[Dict[str, Any]] = None
    ):
        """
        Log detailed Pydantic AI validation failure for debugging.

        Captures comprehensive information about why structured output failed,
        including the raw model response that couldn't be validated.

        Args:
            round_num: Current round number
            agent_type: 'dm', 'player', or 'enemy'
            agent_id: Specific agent identifier
            schema_name: Pydantic schema that failed (e.g., 'ActionResolution')
            exception_type: Exception class name (e.g., 'UnexpectedModelBehavior')
            error_message: Full error message
            attempt_number: Which retry attempt this was (1-based)
            max_attempts: Maximum retries configured
            raw_model_response: Raw JSON/text from model (if available)
            underlying_error: Underlying Pydantic validation error (if available)
            action_context: Optional context about what was being resolved

        Example:
            ```python
            logger.log_pydantic_validation_failure(
                round_num=5,
                agent_type='dm',
                agent_id='dm_narrator',
                schema_name='ActionResolution',
                exception_type='UnexpectedModelBehavior',
                error_message='Exceeded maximum retries (1) for output validation',
                attempt_number=3,
                max_attempts=4,
                raw_model_response='{"narration": "...", "success_tier": "INVALID_VALUE"}',
                underlying_error='ValidationError: Invalid enum value',
                action_context={'action_type': 'social', 'player_id': 'player_01'}
            )
            ```
        """
        event = {
            "event_type": "pydantic_validation_failure",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "agent_type": agent_type,
            "agent_id": agent_id,
            "schema_name": schema_name,
            "exception_type": exception_type,
            "error_message": error_message[:1000],  # Truncate very long errors
            "attempt_number": attempt_number,
            "max_attempts": max_attempts,
            "is_final_attempt": attempt_number >= max_attempts,
            "raw_model_response": raw_model_response[:2000] if raw_model_response else None,  # Truncate
            "underlying_error": underlying_error[:500] if underlying_error else None,
            "action_context": action_context
        }
        self._write_event(event)

    def log_narrative_memory(
        self,
        round_num: int,
        agent_id: str,
        character_name: str,
        locations_visited: List[str],
        story_beats: List[str],
        story_summary: str
    ):
        """
        Log player narrative memory state (for ML training).

        Logged at end of each round to capture accumulated story context.

        Args:
            round_num: Current round
            agent_id: Player agent ID (e.g., 'player_ash')
            character_name: Display name (e.g., 'Ash')
            locations_visited: List of locations visited so far
            story_beats: List of key story events (max 10)
            story_summary: Rolling summary of story so far

        JSONL Schema:
        ```json
        {
          "event_type": "narrative_memory",
          "ts": "2025-01-15T10:30:00",
          "session": "session_abc123",
          "round": 3,
          "agent_id": "player_ash",
          "character_name": "Ash",
          "memory": {
            "locations_visited": ["Docks", "Transit Hub"],
            "story_beats": ["Fought gang", "Found data chip"],
            "story_summary": "Started at docks, moved to hub after combat."
          }
        }
        ```
        """
        event = {
            "event_type": "narrative_memory",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "agent_id": agent_id,
            "character_name": character_name,
            "memory": {
                "locations_visited": locations_visited,
                "story_beats": story_beats,
                "story_summary": story_summary
            }
        }
        self._write_event(event)


@dataclass
class Condition:
    """A status condition affecting a character."""
    name: str
    type: str  # mental_strain, equipment_damage, wound, stun, etc.
    penalty: int  # modifier to apply to relevant rolls
    description: str
    duration: int = -1  # -1 = until resolved, otherwise number of turns
    affects: List[str] = field(default_factory=list)  # which attributes/skills affected
    protection_amount: Optional[int] = None  # Barrier damage absorption capacity (None = not a barrier)

    def applies_to(self, attribute: str, skill: Optional[str] = None) -> bool:
        """Check if this condition affects the given attribute/skill."""
        if not self.affects:
            return True  # Affects everything
        if attribute in self.affects:
            return True
        if skill and skill in self.affects:
            return True
        return False


@dataclass
class ActionResolution:
    """Result of a resolved action."""
    intent: str
    attribute: str
    skill: Optional[str]
    attribute_value: int
    skill_value: int
    roll: int  # d20 result
    total: int  # attribute × skill + d20 (skilled) or d20 ÷ 2 (unskilled)
    difficulty: int
    margin: int  # total - difficulty
    outcome_tier: OutcomeTier
    success: bool
    narrative: str
    state_effects: Dict[str, Any] = field(default_factory=dict)
    modifiers_applied: List[RollModifier] = field(default_factory=list)  # Roll modifiers for ML logging
    # Formula breakdown (calculated once in resolve_action, used by logging/display)
    ability: int = 0  # attr × skill (0 if unskilled)
    is_unskilled: bool = False  # True if skill_value == 0
    roll_formula: Optional[str] = None  # Human-readable formula string


@dataclass
class SceneClock:
    """
    Progress clock for tracking scene state with semantic guidance.

    Range: 0 to maximum (with optional overflow)
    - Zero is the minimum (no negative values by default)
    - Maximum fills the clock and triggers consequences
    - Can overflow beyond maximum to indicate increasing urgency

    Semantic metadata helps the DM make consistent decisions about when to
    advance/regress the clock and what consequences to narrate.

    Expiration: Clocks automatically expire after timeout_rounds to prevent stagnation.
    - Low clocks (< 50% filled) expire as "crisis averted/opportunity lost"
    - Filled clocks expire with consequences then remove
    - Mid-range clocks expire as "situation escalates or resolves"
    """
    name: str
    current: int = 0
    maximum: int = 6
    description: str = ""
    advance_meaning: str = ""  # What it means to advance (e.g., "Investigation progresses", "Danger increases")
    regress_meaning: str = ""  # What it means to regress (e.g., "Setback in investigation", "Danger reduced")
    filled_consequence: str = ""  # What happens when filled (e.g., "Evidence complete, pivot to confrontation")
    timeout_rounds: int = 5  # Rounds until clock expires (default 5)
    allow_negative: bool = False  # If True, clock can go negative (for bidirectional trackers)
    is_terminal: bool = False  # If True, filling this clock resolves the scene and ends the session
    terminal_outcome: str = "victory"  # Session outcome when a terminal clock fills (victory/defeat/draw)
    _ever_filled: bool = field(default=False, init=False, repr=False)
    _rounds_alive: int = field(default=0, init=False, repr=False)  # Track how long clock has existed

    def advance(self, ticks: int = 1) -> bool:
        """
        Advance clock, return True if filled (at or above max).

        Clocks CAN overflow beyond maximum to indicate increasing urgency.
        For example, a 6/6 clock can advance to 7/6, 8/6, etc.

        Returns:
            True if clock is at or above maximum (indicating consequences needed)
        """
        was_filled = self.current >= self.maximum
        self.current += ticks  # Allow overflow beyond maximum
        is_filled = self.current >= self.maximum

        # Mark as ever filled if we've reached or exceeded maximum
        if is_filled:
            self._ever_filled = True
            return True
        return False

    def regress(self, ticks: int = 1):
        """
        Decrease clock progress.

        By default, clocks clamp at 0 (cannot go negative).
        If allow_negative=True, can go down to -maximum.

        Clocks -- including terminal clocks -- are always regressable: the clock is a
        two-way pressure gauge, not a ratchet. Convergence is enforced by the round-cap
        backstop (which resolves any still-open terminal clock), NOT by making clocks
        monotonic. Driving a DOOM terminal clock (terminal_outcome=defeat) to 0 is a
        legitimate regression that also neutralises the threat -> victory.
        """
        if self.allow_negative:
            # Bidirectional tracker - can go negative
            self.current = max(self.current - ticks, -self.maximum)
        else:
            # Standard clock - clamp at 0
            self.current = max(self.current - ticks, 0)
            if self.current == 0 and ticks > 0:
                logger.debug(f"Clock {self.name} regressed to 0 (clamped, cannot go negative)")

    @property
    def filled(self) -> bool:
        """Check if clock is filled."""
        return self.current >= self.maximum

    @property
    def effective_consequence(self) -> str:
        """
        The in-world consequence to narrate when this clock fills -- never empty.

        Most authored configs leave filled_consequence blank, which made dramatic
        completions meaningless. When it is unset we synthesize a consequence from
        the clock's own advance_meaning (the authored sense of "filling"), then its
        description, so the DM always receives concrete in-world text to render as
        fact rather than improvising a near-miss.
        """
        authored = (self.filled_consequence or "").strip()
        if authored:
            return authored

        advance = (self.advance_meaning or "").strip()
        if advance:
            text = advance[0].upper() + advance[1:]
            if text[-1] not in ".!?":
                text += "."
            return text

        desc = (self.description or "").strip()
        if desc:
            text = desc[0].upper() + desc[1:]
            if text[-1] not in ".!?":
                text += "."
            return text

        return f"{self.name} reaches its breaking point."

    @property
    def ever_filled(self) -> bool:
        """Check if clock has ever been filled (for one-time triggers)."""
        return self._ever_filled

    @property
    def progress_ratio(self) -> float:
        """
        Get progress as a ratio.

        Returns:
            Ratio of current/maximum (0.0 to 1.0+ normally, can be negative if allow_negative=True)
        """
        return self.current / self.maximum if self.maximum > 0 else 0

    def increment_round(self):
        """Increment the rounds_alive counter."""
        self._rounds_alive += 1

    @property
    def is_expired(self) -> bool:
        """Check if clock has exceeded its timeout."""
        return self._rounds_alive >= self.timeout_rounds

    @property
    def expiration_type(self) -> str:
        """
        Determine how this clock should expire based on its current state.

        Returns:
            - "crisis_averted": Clock is low (< 50% filled) - danger passed, opportunity lost
            - "force_resolve": Clock is filled - trigger consequences then remove
            - "escalate": Clock is mid-range (50-99%) - situation must resolve one way or another
        """
        if self.filled:
            return "force_resolve"
        elif self.current < (self.maximum * 0.5):
            return "crisis_averted"
        else:
            return "escalate"


@dataclass
class VoidState:
    """
    Tracks void corruption for an entity with multi-level caps.

    Codex Nexum guidance: Limit automatic void gain per scene (max +3) unless player opts into high-risk rites.
    """
    score: int = 0  # 0-10
    history: List[Dict[str, Any]] = field(default_factory=list)
    _processed_actions: set = field(default_factory=set, init=False, repr=False)
    _round_void_gain: int = field(default=0, init=False, repr=False)
    _scene_void_gain: int = field(default=0, init=False, repr=False)  # Scene-level tracking
    _scene_opted_in_high_risk: bool = field(default=False, init=False, repr=False)  # Opt-in flag

    def add_void(self, amount: int, reason: str, action_id: Optional[str] = None, is_high_risk_ritual: bool = False) -> int:
        """
        Add void corruption, return new score.

        Void is applied directly as specified by the DM through ⚫ Void: markers.
        No automatic caps - DM has full control over void corruption mechanics.

        Args:
            amount: Void to add (applied directly, only capped at max void score of 10)
            reason: Why void is being added
            action_id: Unique action identifier to prevent duplicates
            is_high_risk_ritual: Whether this is a high-risk ritual (kept for compatibility)

        Returns:
            New void score
        """
        # Prevent duplicate void for the same action
        if action_id and action_id in self._processed_actions:
            logger.debug(f"Skipping duplicate void add for action {action_id}")
            return self.score

        # Apply void directly as specified by DM (no caps except max void of 10)
        old_score = self.score
        self.score = min(self.score + amount, 10)
        actual_add = self.score - old_score

        # Track for history and logging
        self._round_void_gain += actual_add
        self._scene_void_gain += actual_add

        if is_high_risk_ritual:
            self._scene_opted_in_high_risk = True

        self.history.append({
            'change': actual_add,
            'reason': reason,
            'old_score': old_score,
            'new_score': self.score,
            'high_risk': is_high_risk_ritual
        })

        if action_id:
            self._processed_actions.add(action_id)

        logger.debug(f"Void added: +{actual_add} (reason: {reason}, new total: {self.score}/10)")
        return self.score

    def reset_round_void(self):
        """Reset round void counter. Call at start of each round."""
        self._round_void_gain = 0
        logger.debug(f"Reset round void counter")

    def reset_scene_void(self):
        """Reset scene void counter. Call at start of new scene."""
        self._scene_void_gain = 0
        self._scene_opted_in_high_risk = False
        logger.debug(f"Reset scene void counter")

    def reduce_void(self, amount: int, reason: str) -> int:
        """Reduce void corruption, return new score."""
        old_score = self.score
        self.score = max(self.score - amount, 0)

        self.history.append({
            'change': -amount,
            'reason': reason,
            'old_score': old_score,
            'new_score': self.score
        })

        return self.score

    @property
    def corruption_level(self) -> str:
        """Get descriptive corruption level."""
        if self.score == 0:
            return "Pure"
        elif self.score <= 2:
            return "Touched"
        elif self.score <= 4:
            return "Shadowed"
        elif self.score <= 6:
            return "Corrupted"
        elif self.score <= 8:
            return "Consumed"
        else:
            return "Lost to Void"


@dataclass
class SoulcreditState:
    """
    Tracks soulcredit (spiritual reputation) for an entity.

    Range: -10 to +10
    Represents trust, honor, and spiritual standing based on contracts, oaths, and social actions.
    """
    score: int = 0  # -10 to +10
    history: List[Dict[str, Any]] = field(default_factory=list)

    def adjust(self, amount: int, reason: str, round_num: Optional[int] = None) -> int:
        """
        Adjust soulcredit and clamp to [-10, +10] range.

        Args:
            amount: Soulcredit delta (can be positive or negative)
            reason: Why soulcredit is changing
            round_num: Which round this change occurred in (for history tracking)

        Returns:
            New soulcredit score
        """
        old_score = self.score
        self.score = max(-10, min(10, self.score + amount))

        if self.score != old_score:
            self.history.append({
                'change': self.score - old_score,
                'reason': reason,
                'old_score': old_score,
                'new_score': self.score,
                'round': round_num
            })
            logger.info(f"Soulcredit: {old_score} → {self.score} ({reason})")

        return self.score

    @property
    def reputation_level(self) -> str:
        """Get descriptive reputation level."""
        if self.score >= 8:
            return "Exemplary"
        elif self.score >= 5:
            return "Honorable"
        elif self.score >= 2:
            return "Trustworthy"
        elif self.score >= -1:
            return "Neutral"
        elif self.score >= -4:
            return "Questionable"
        elif self.score >= -7:
            return "Disreputable"
        else:
            return "Pariah"


def generate_default_bond_matrix(
    character_names: List[str],
    factions: Dict[str, str],
    random_seed: Optional[int] = None,
    min_bonds: int = 2,
    max_bonds: int = 5,
) -> List[Dict[str, Any]]:
    """
    Generate a default bond matrix for a party of characters.

    Creates bond suggestions deterministically using the provided random seed.
    Ensures every character has at least 1 bond (unless Freeborn-constrained).
    Respects Freeborn bond limit (max 1).

    Args:
        character_names: List of character names in the party
        factions: Dict mapping character name to faction string
        random_seed: Random seed for deterministic generation
        min_bonds: Minimum number of bonds to generate
        max_bonds: Maximum number of bonds to generate

    Returns:
        List of bond suggestion dicts with character_a, character_b, bond_type
    """
    if len(character_names) < 2:
        return []

    if random_seed is not None:
        random.seed(random_seed)

    party_size = len(character_names)
    bond_counts = {name: 0 for name in character_names}
    num_bonds = min(max_bonds, max(min_bonds, party_size))

    bonds = []
    attempts = 0
    max_attempts = 100

    while len(bonds) < num_bonds and attempts < max_attempts:
        attempts += 1
        char_a, char_b = random.sample(character_names, 2)

        # Check pair uniqueness
        if (char_a, char_b) in bonds or (char_b, char_a) in bonds:
            continue
        # Check bond limits (max 3 per character)
        if bond_counts[char_a] >= 3 or bond_counts[char_b] >= 3:
            continue
        # Freeborn max 1 bond
        faction_a = factions.get(char_a, '').lower()
        faction_b = factions.get(char_b, '').lower()
        if 'freeborn' in faction_a and bond_counts[char_a] >= 1:
            continue
        if 'freeborn' in faction_b and bond_counts[char_b] >= 1:
            continue

        bonds.append((char_a, char_b))
        bond_counts[char_a] += 1
        bond_counts[char_b] += 1

    # Ensure all characters have at least 1 bond (unless Freeborn-constrained)
    unbonded = [name for name, count in bond_counts.items() if count == 0]
    for char in unbonded:
        faction_lower = factions.get(char, '').lower()
        if 'freeborn' in faction_lower and bond_counts[char] >= 1:
            continue
        candidates = [
            other for other in character_names
            if other != char and bond_counts[other] < 3
            and (char, other) not in bonds and (other, char) not in bonds
        ]
        if candidates:
            partner = random.choice(candidates)
            bonds.append((char, partner))
            bond_counts[char] += 1
            bond_counts[partner] += 1

    # Assign bond types based on faction relationships
    suggestions = []
    for char_a, char_b in bonds:
        bond_type = _suggest_bond_type_for_factions(
            factions.get(char_a, ''), factions.get(char_b, '')
        )
        suggestions.append({
            'character_a': char_a,
            'character_b': char_b,
            'bond_type': bond_type,
        })

    return suggestions


def _suggest_bond_type_for_factions(faction_a: str, faction_b: str) -> str:
    """Suggest bond type based on faction pairing."""
    faction_a_lower = faction_a.lower()
    faction_b_lower = faction_b.lower()
    is_freeborn = ('freeborn' in faction_a_lower or 'freeborn' in faction_b_lower)
    same_faction = (faction_a_lower == faction_b_lower)

    if is_freeborn:
        return random.choice(["kinship", "passion"])
    if same_faction:
        return random.choice(["kinship", "faction"])
    return random.choice(["passion", "debt", "voidward"])


class MechanicsEngine:
    """
    Core mechanics engine for YAGS resolution in Aeonisk.
    Handles dice rolls, rituals, void progression, scene clocks, and conditions.
    """

    # Standard YAGS attributes (imported from constants.py - single source of truth)
    ATTRIBUTES = YAGS_ATTRIBUTES

    def __init__(self, jsonl_logger: Optional[JSONLLogger] = None, shared_state: Optional[Any] = None):
        self.scene_clocks: Dict[str, SceneClock] = {}
        # Clock conservation (corpus v2: median 9 spawns/14 removals per
        # session made clocks disposable set dressing). LLM proposes,
        # these invariants enforce; rejections are logged.
        self.max_active_clocks: int = 6
        self.max_clock_spawns_per_round: int = 2
        self._clock_spawns_this_round: int = 0
        self._clock_spawn_round: int = -1
        self.void_states: Dict[str, VoidState] = {}  # agent_id -> VoidState
        self.soulcredit_states: Dict[str, SoulcreditState] = {}  # agent_id -> SoulcreditState
        self.action_history: List[ActionResolution] = []
        self.conditions: Dict[str, List[Condition]] = {}  # agent_id -> conditions
        self.scene_void_level: int = 0  # 0-10 scene void pressure
        self.jsonl_logger: Optional[JSONLLogger] = jsonl_logger  # Machine-readable event log
        self.current_round: int = 0  # Track current round for logging
        self._last_clock_increment_round: int = -1  # Track last round we incremented clocks
        self.shared_state: Optional[Any] = shared_state  # NEW: For vendor lookup in purchase validation

        # Clock update queue - prevents cascade fills during resolution
        # Queued updates are applied batch during synthesis phase
        self.clock_update_queue: List[Tuple[str, int, str]] = []  # (clock_name, ticks, reason)

        # Clock history - chronological timeline of all clock events
        self.clock_history: List[Dict[str, Any]] = []

        # Terminal completion snapshot - set when a clock flagged is_terminal fills.
        # The session loop reads this to end the session (with the declared outcome)
        # instead of running to the round cap. Also the hook point for the
        # resolve-then-leap continuation: it captures the resolving beat. First
        # terminal clock to fill wins (one ending per session).
        self.terminal_completion: Optional[Dict[str, Any]] = None

    def calculate_dc(
        self,
        intent: str,
        action_type: str = "general",
        is_ritual: bool = False,
        is_extreme: bool = False,
        is_multi_stage: bool = False,
        is_inter_party: bool = False,
        proposed_dc: Optional[int] = None
    ) -> int:
        """
        Calculate appropriate DC for an action based on context.

        Codex Nexum guidance:
        - Routine/pressured checks: 18-22
        - Only 26+ for truly extreme, multi-stage actions
        - Inter-party communication: 10 (easy) unless environmental factors

        Args:
            intent: Action description
            action_type: sensing, technical, ritual, social, investigation, combat
            is_ritual: Whether this is a ritual action
            is_extreme: Whether this is extreme/dangerous
            is_multi_stage: Whether this requires multiple stages
            is_inter_party: Whether this is communication between party members
            proposed_dc: LLM-assessed difficulty (player's structured
                difficulty_estimate). Authoritative within floors; None or
                <=0 falls back to the category table.

        Returns:
            Calculated DC (10-40 range)
        """
        intent_lower = intent.lower()

        # LLM-proposed difficulty: when a proposal is present it is
        # authoritative within one-directional guardrails - proposals may
        # raise difficulty freely but can never drop below the floor that
        # keeps priced mechanics priced (rituals stay CHALLENGING+). The
        # category table below only answers when no proposal is given.
        # Corpus v2 (2026-07-04) showed the table alone yields 91% DC 18:
        # skilled rolls succeed 98%, unskilled 0% - dice as pure theater.
        if proposed_dc and proposed_dc > 0:
            floor = (Difficulty.CHALLENGING.value if is_ritual
                     else Difficulty.TRIVIAL.value)
            base_dc = max(proposed_dc, floor)
        # Inter-party communication is usually easy unless environmental factors
        elif is_inter_party and action_type == "social":
            # Check for environmental complications
            if any(kw in intent_lower for kw in ['shout', 'scream', 'distant', 'far away', 'across', 'noise', 'chaos', 'combat']):
                base_dc = Difficulty.ROUTINE.value  # 18 - complicated communication
            else:
                base_dc = Difficulty.EASY.value  # 10 - normal party communication
        # Base DC by action type
        elif is_ritual:
            base_dc = Difficulty.CHALLENGING.value  # 22 - rituals are always challenging
        elif action_type == "combat":
            base_dc = Difficulty.ROUTINE.value  # 18 - combat is time-pressured
        elif action_type == "social":
            base_dc = Difficulty.ROUTINE.value  # 18 - most social actions
        elif action_type in ["sensing", "investigation"]:
            base_dc = Difficulty.MODERATE.value  # 20 - perception/analysis
        elif action_type == "technical":
            base_dc = Difficulty.MODERATE.value  # 20 - technical work
        else:
            # Default for general actions
            base_dc = Difficulty.ROUTINE.value  # 18

        # Adjust for extreme/multi-stage actions
        if is_extreme or is_multi_stage:
            base_dc = max(base_dc, Difficulty.DIFFICULT.value)  # 26+ for extreme

        # Adjust for void pressure (high void makes everything harder)
        if self.scene_void_level >= 7:
            base_dc += 4  # High void: +4 DC
        elif self.scene_void_level >= 4:
            base_dc += 2  # Moderate void: +2 DC

        # Clamp to reasonable range (10-40)
        return max(10, min(base_dc, 40))

    def resolve_action(
        self,
        intent: str,
        attribute: str,
        skill: Optional[str],
        attribute_value: int,
        skill_value: int,
        difficulty: int,
        modifiers: Dict[str, int] = None,
        agent_id: Optional[str] = None
    ) -> ActionResolution:
        """
        Resolve an action using YAGS mechanics: Attribute × Skill + d20 vs Difficulty.

        Args:
            intent: What the character is trying to do
            attribute: Which attribute is being used
            skill: Which skill (or None for raw attribute check)
            attribute_value: Character's attribute score
            skill_value: Character's skill level (0 if unskilled)
            difficulty: Target number to beat
            modifiers: Optional dict of bonuses/penalties
            agent_id: Agent identifier for condition tracking

        Returns:
            ActionResolution with full results
        """
        # Apply condition penalties and collect modifiers for logging
        if modifiers is None:
            modifiers = {}
        modifiers_applied: List[RollModifier] = []

        if agent_id and agent_id in self.conditions:
            for condition in self.conditions[agent_id]:
                if condition.applies_to(attribute, skill):
                    modifiers[condition.name] = condition.penalty
                    modifiers_applied.append(RollModifier(
                        source="condition",
                        value=condition.penalty,
                        details={"name": condition.name}
                    ))
                    logger.debug(f"Applied condition {condition.name}: {condition.penalty}")

        # Roll d20
        roll = random.randint(1, 20)

        # Calculate base total
        # Track unskilled state for fumble handling
        is_unskilled_attempt = False
        unskilled_fumble = False

        if skill_value > 0:
            # Skilled: Attribute × Skill + d20
            ability = attribute_value * skill_value
            base_total = ability + roll

            # Math verification: ensure calculation is correct
            assert base_total == ability + roll, \
                f"Math error (skilled): {attribute_value}×{skill_value}+{roll} should be {ability}+{roll}={ability+roll}, got {base_total}"
        else:
            # Unskilled attempt (skill_value == 0)
            # YAGS Aeonisk v1.3.0: Raw attribute checks removed - all actions require skills
            # - Knowledge skills: Cannot be attempted untrained at all
            # - Standard skills (including skill=None): d20 ÷ 2, fumble on natural 1-2

            if skill and is_knowledge_skill(skill):
                # Knowledge skills cannot be attempted without training
                # Return automatic critical failure
                logger.warning(f"Attempted Knowledge skill '{skill}' without training - automatic failure")
                return ActionResolution(
                    intent=intent,
                    attribute=attribute,
                    skill=skill,
                    attribute_value=attribute_value,
                    skill_value=0,
                    roll=roll,
                    total=0,
                    difficulty=difficulty,
                    success=False,
                    margin=-difficulty,
                    outcome_tier="critical_failure",
                    narrative=f"Cannot attempt {skill} without proper training.",
                    modifiers_applied=modifiers_applied if modifiers_applied else None,
                    ability=0,
                    is_unskilled=True,
                    roll_formula=f"Knowledge skill '{skill}' requires training - automatic failure"
                )

            # Unskilled Standard skill (or no skill specified): d20 ÷ 2
            is_unskilled_attempt = True
            ability = 0  # No ability bonus for untrained
            base_total = roll // 2
            unskilled_fumble = roll <= 2  # Fumble on natural 1 or 2

            skill_name = skill if skill else "unskilled action"
            logger.debug(f"Unskilled {skill_name}: d20({roll}) ÷ 2 = {base_total}")

        # Apply modifiers and collect non-condition modifiers for logging
        total = base_total
        modifier_sum = 0
        if modifiers:
            for mod_name, mod_value in modifiers.items():
                total += mod_value
                modifier_sum += mod_value
                logger.debug(f"Applied modifier {mod_name}: {mod_value:+d}")
                # Add to modifiers_applied if not already added as a condition
                if not any(m.details and m.details.get("name") == mod_name for m in modifiers_applied):
                    modifiers_applied.append(RollModifier(
                        source=mod_name.lower().replace(" ", "_"),
                        value=mod_value,
                        details=None
                    ))

        # Math verification: ensure modifiers applied correctly
        expected_total = base_total + modifier_sum
        assert total == expected_total, \
            f"Math error (modifiers): {base_total} + modifiers({modifier_sum}) should be {expected_total}, got {total}"

        # Calculate margin and outcome
        margin = total - difficulty

        # Handle unskilled fumble (natural 1-2 on d20 when attempting skill untrained)
        if unskilled_fumble:
            success = False
            outcome_tier = OutcomeTier.CRITICAL_FAILURE
            logger.debug(f"Unskilled fumble (rolled {roll}): automatic critical failure")
        else:
            success = margin >= 0
            outcome_tier = self._determine_outcome_tier(margin)

        # Build formula string once (single source of truth)
        if skill_value > 0:
            # Skilled: Attr × Skill + d20
            roll_formula = f"{attribute} {attribute_value} × {skill} {skill_value} = {ability}; {ability} + d20({roll}) = {total} vs DC {difficulty}"
        else:
            # Unskilled: d20 ÷ 2
            halved = roll // 2
            skill_name = skill if skill else "unskilled"
            roll_formula = f"d20({roll}) ÷ 2 = {halved} ({skill_name}, unskilled) vs DC {difficulty}"

        # Create resolution
        resolution = ActionResolution(
            intent=intent,
            attribute=attribute,
            skill=skill,
            attribute_value=attribute_value,
            skill_value=skill_value,
            roll=roll,
            total=total,
            difficulty=difficulty,
            margin=margin,
            outcome_tier=outcome_tier,
            success=success,
            narrative=self._generate_narrative(intent, outcome_tier, margin),
            modifiers_applied=modifiers_applied,
            ability=ability,
            is_unskilled=is_unskilled_attempt,
            roll_formula=roll_formula
        )

        self.action_history.append(resolution)
        return resolution

    def _determine_outcome_tier(self, margin: int) -> OutcomeTier:
        """Determine outcome quality from margin of success."""
        if margin <= -20:
            return OutcomeTier.CRITICAL_FAILURE
        elif margin < 0:
            return OutcomeTier.FAILURE
        elif margin < 5:
            return OutcomeTier.MARGINAL
        elif margin < 10:
            return OutcomeTier.MODERATE
        elif margin < 15:
            return OutcomeTier.GOOD
        elif margin < 20:
            return OutcomeTier.EXCELLENT
        else:
            return OutcomeTier.EXCEPTIONAL

    def _generate_narrative(self, intent: str, outcome: OutcomeTier, margin: int) -> str:
        """Generate brief narrative description of outcome."""
        outcome_descriptions = {
            OutcomeTier.CRITICAL_FAILURE: "catastrophically fails",
            OutcomeTier.FAILURE: "fails",
            OutcomeTier.MARGINAL: "barely succeeds",
            OutcomeTier.MODERATE: "succeeds adequately",
            OutcomeTier.GOOD: "succeeds well",
            OutcomeTier.EXCELLENT: "succeeds excellently",
            OutcomeTier.EXCEPTIONAL: "achieves exceptional success"
        }

        return f"{intent} {outcome_descriptions[outcome]} (margin: {margin:+d})"

    def resolve_ritual(
        self,
        intent: str,
        willpower: int,
        astral_arts: int,
        difficulty: int,
        has_primary_tool: bool = False,
        has_offering: bool = False,
        sanctified_altar: bool = False,
        agent_id: Optional[str] = None,
        faction: Optional[str] = None
    ) -> Tuple[ActionResolution, Dict[str, Any]]:
        """
        Resolve a ritual action with requirements and consequences.

        NOTE: This should ONLY be called for explicit ritual actions.
        Non-ritual actions (sensing, tech, social) should use resolve_action() instead.

        Args:
            intent: What the ritual aims to accomplish
            willpower: Character's Willpower attribute
            astral_arts: Character's Astral Arts skill
            difficulty: Target difficulty
            has_primary_tool: Whether character has required focus/tool
            has_offering: Whether character made an offering
            sanctified_altar: Whether using a consecrated space
            agent_id: Character identifier for void tracking

        Returns:
            Tuple of (ActionResolution, ritual_effects dict)
        """
        modifiers = {}
        ritual_effects = {
            'void_change': 0,
            'soulcredit_change': 0,
            'consequences': []
        }

        # Apply modifiers for proper preparation (RITUAL-SPECIFIC)
        if has_primary_tool:
            modifiers['primary_tool'] = 2
        else:
            # Missing tool: +1 Void (no tier downgrade, just void)
            ritual_effects['void_change'] += 1
            ritual_effects['consequences'].append("Missing ritual focus (+1 Void)")

        if sanctified_altar:
            modifiers['sanctified_altar'] = 3
            ritual_effects['consequences'].append("Sanctified altar (+3)")

        # OFFERING REQUIREMENT (Codex Nexum canonical)
        # Every ritual must consume an offering OR apply +1 Void and downgrade tier on success
        if has_offering:
            modifiers['offering'] = 1
            ritual_effects['consequences'].append("Offering consumed (+1)")
        else:
            # No offering: +1 Void AND tier downgrade on success
            ritual_effects['void_change'] += 1
            ritual_effects['tier_downgrade'] = True  # Mark for tier downgrade
            ritual_effects['consequences'].append("No offering: +1 Void, tier downgraded")

        # Resolve the action
        resolution = self.resolve_action(
            intent=intent,
            attribute="Willpower",
            skill="Astral Arts",
            attribute_value=willpower,
            skill_value=astral_arts,
            difficulty=difficulty,
            modifiers=modifiers,
            agent_id=agent_id
        )

        # Apply tier downgrade if no offering and successful
        if ritual_effects.get('tier_downgrade') and _resolution_success(resolution):
            # Downgrade outcome tier by one level
            tier_map = {
                OutcomeTier.EXCEPTIONAL: OutcomeTier.EXCELLENT,
                OutcomeTier.EXCELLENT: OutcomeTier.GOOD,
                OutcomeTier.GOOD: OutcomeTier.MODERATE,
                OutcomeTier.MODERATE: OutcomeTier.MARGINAL,
                OutcomeTier.MARGINAL: OutcomeTier.MARGINAL,  # Can't go lower while still success
            }
            if resolution.outcome_tier in tier_map:
                old_tier = resolution.outcome_tier.value
                resolution.outcome_tier = tier_map[resolution.outcome_tier]
                ritual_effects['consequences'].append(f"Tier downgraded: {old_tier} → {resolution.outcome_tier.value}")

        # Calculate potential void consequences based on outcome
        # NOTE: Don't apply void here - let outcome_parser handle it to avoid duplicates
        if resolution.outcome_tier in [OutcomeTier.FAILURE, OutcomeTier.CRITICAL_FAILURE]:
            ritual_effects['void_change'] += 1
            ritual_effects['consequences'].append("Failed ritual: +1 Void")

        # Calculate soulcredit change
        # Pass intent to detect contract/oath fulfillment, cleansing rituals, etc.
        sc_delta, sc_reasons = self.calculate_soulcredit_change(
            resolution=resolution,
            action_type='ritual',
            is_ritual=True,
            has_offering=has_offering,
            faction=faction,
            action_intent=intent,
            action_narration=""  # DM will provide narration in post-resolution phase
        )
        ritual_effects['soulcredit_change'] = sc_delta
        if sc_reasons:
            ritual_effects['consequences'].extend(sc_reasons)

        # Store void change in ritual_effects but don't apply it yet
        # The DM will apply void from outcome_parser to avoid duplicate tracking

        return resolution, ritual_effects

    def calculate_soulcredit_change(
        self,
        resolution: 'ActionResolution',
        action_type: str,
        is_ritual: bool = False,
        has_offering: bool = False,
        faction: str = None,
        action_intent: str = "",
        action_narration: str = ""
    ) -> Tuple[int, List[str]]:
        """
        Calculate soulcredit changes based on social/spiritual actions.

        Soulcredit is spiritual reputation, not ritual quality. It tracks:
        - Fulfilling/breaking contracts, oaths, bonds
        - Upholding/violating faction tenets
        - Intentional cleansing rituals
        - Public witnessed rituals aligned with character principles

        Based on Aeonisk YAGS Module v1.2.2 soulcredit rules.

        Args:
            resolution: Action resolution with success/margin
            action_type: Type of action
            is_ritual: Whether this is a ritual action
            has_offering: Whether offering was provided
            faction: Character's faction (for faction-specific logic)
            action_intent: Player's declared intent (for detecting contracts/oaths)
            action_narration: DM narration (for detecting social outcomes)

        Returns:
            (soulcredit_delta, reasons)
        """
        delta = 0
        reasons = []

        # Combine intent and narration for analysis
        action_text = (action_intent + " " + action_narration).lower()

        # GAINING SOULCREDIT

        # Fulfill Ritual Contract/Oath (+1) - formal, witnessed
        if any(keyword in action_text for keyword in ['fulfill contract', 'fulfill oath', 'complete contract',
                                                        'honor oath', 'uphold contract', 'fulfill agreement']):
            if _resolution_success(resolution):
                delta += 1
                reasons.append("Fulfilled ritual contract/oath (+1 SC)")

        # Aid Another's Ritual with Offering (+1)
        if any(keyword in action_text for keyword in ['aid ritual', 'help ritual', 'assist ritual',
                                                        'support ritual', 'join ritual']):
            if has_offering and _resolution_success(resolution):
                delta += 1
                reasons.append("Aided another's ritual with offering (+1 SC)")

        # Void Cleansing Ritual (+2-3) - intentional SC improvement action
        if any(keyword in action_text for keyword in ['cleanse void', 'purify void', 'remove void',
                                                        'void cleansing', 'spiritual cleansing']):
            if _resolution_success(resolution):
                # +3 for Strong Resonance+ (margin 10+), +2 otherwise
                cleanse_bonus = 3 if resolution.margin >= 10 else 2
                delta += cleanse_bonus
                reasons.append(f"Void cleansing ritual (+{cleanse_bonus} SC)")

        # Public Ritual aligned with Bond/Will (+2) - witnessed, significant, Solid+ margin
        if any(keyword in action_text for keyword in ['public ritual', 'witnessed ritual', 'ceremonial ritual']):
            if _resolution_success(resolution) and resolution.margin >= 5:  # Solid margin
                delta += 2
                reasons.append("Public ritual aligned with principles (+2 SC)")

        # Uphold Faction Tenets at cost (+1)
        # ACG: enforce debt law fairly, uphold contracts
        # Pantheon: uphold law/order, maintain civic trust
        # Tempest: resist commodification, maintain autonomy
        # Communes: community rituals, mutual aid
        if faction:
            faction_keywords = {
                'ACG': ['enforce debt', 'uphold debt law', 'collect debt fairly', 'enforce contract'],
                'Pantheon': ['uphold law', 'enforce order', 'maintain civic', 'protect citizens'],
                'Tempest': ['resist commodification', 'maintain autonomy', 'refuse contract', 'preserve freedom'],
                'Communes': ['community ritual', 'mutual aid', 'share resources', 'collective ritual']
            }

            if faction in faction_keywords:
                if any(keyword in action_text for keyword in faction_keywords[faction]):
                    if _resolution_success(resolution) and 'at cost' in action_text or 'sacrifice' in action_text:
                        delta += 1
                        reasons.append(f"Upheld {faction} tenets at personal cost (+1 SC)")

        # Ritual Success with Strong Resonance+ (+1) - margin 10+
        # NOTE: This is a minor bonus compared to the social actions above
        if is_ritual and _resolution_success(resolution) and resolution.margin >= 10:
            # Only award if not already awarded for cleansing or public ritual
            if not any('cleansing' in r or 'Public ritual' in r for r in reasons):
                delta += 1
                reasons.append("Ritual success with strong resonance (+1 SC)")

        # LOSING SOULCREDIT

        # Break Ritual Contract/Oath/Bond (-2) - formal, witnessed
        if any(keyword in action_text for keyword in ['break contract', 'break oath', 'violate contract',
                                                        'betray bond', 'default on oath', 'abandon contract']):
            delta -= 2
            reasons.append("Broke ritual contract/oath (-2 SC)")

        # Refuse/Default on Ritual Debt (-2) - especially ACG-logged
        if any(keyword in action_text for keyword in ['refuse debt', 'default on debt', 'dodge debt',
                                                        'evade payment', 'skip payment']):
            delta -= 2
            reasons.append("Defaulted on ritual debt (-2 SC)")

        # Betray Declared Guiding Principle (-3) - also costs Void
        if any(keyword in action_text for keyword in ['betray principle', 'violate principle',
                                                        'abandon belief', 'contradict guiding']):
            delta -= 3
            reasons.append("Betrayed guiding principle (-3 SC)")

        # Actions Contradicting Faction Tenets (-1-2)
        if faction:
            faction_violations = {
                'ACG': ['forgive debt', 'waive contract', 'ignore debt law'],
                'Pantheon': ['break law', 'corrupt official', 'abuse authority'],
                'Tempest': ['commodify ritual', 'sell ritual', 'commercialize magic'],
                'Communes': ['hoard resources', 'refuse aid', 'individual gain']
            }

            if faction in faction_violations:
                if any(keyword in action_text for keyword in faction_violations[faction]):
                    delta -= 2
                    reasons.append(f"Contradicted {faction} tenets (-2 SC)")

        # Ritual Failure from Negligence (-1) - GM call
        # Only applies if ritual failed AND there's evidence of lack of preparation
        if is_ritual and not _resolution_success(resolution):
            negligence_indicators = ['unprepared', 'no offering', 'rushed', 'careless', 'negligent']
            if any(indicator in action_text for indicator in negligence_indicators):
                delta -= 1
                reasons.append("Ritual failure from negligence (-1 SC)")

        return (delta, reasons)

    def get_void_state(self, agent_id: str) -> VoidState:
        """Get or create void state for an agent."""
        if agent_id not in self.void_states:
            self.void_states[agent_id] = VoidState()
        return self.void_states[agent_id]

    def get_soulcredit_state(self, agent_id: str, initial_score: int = 0) -> SoulcreditState:
        """Get or create soulcredit state for an agent."""
        if agent_id not in self.soulcredit_states:
            state = SoulcreditState(score=initial_score)
            self.soulcredit_states[agent_id] = state
        return self.soulcredit_states[agent_id]

    def format_character_soulcredit(self, agent_id: str, character_name: str) -> str:
        """Format soulcredit history for the acting character (DM-facing context).

        Returns empty string if no SC history exists or agent is unknown.
        """
        if agent_id not in self.soulcredit_states:
            return ""
        sc_state = self.soulcredit_states[agent_id]
        if not sc_state.history:
            return ""

        # Group history entries by round
        from collections import defaultdict
        by_round = defaultdict(list)
        for entry in sc_state.history:
            r = entry.get('round')
            by_round[r].append(entry)

        # Build per-round summary
        round_parts = []
        for r in sorted(by_round.keys(), key=lambda x: (x is None, x)):
            entries = by_round[r]
            descs = [f"{e['change']:+d} {e['reason']}" for e in entries]
            label = f"R{r}" if r is not None else "R?"
            round_parts.append(f"{label}: {', '.join(descs)}")

        score_str = f"{sc_state.score:+d}" if sc_state.score != 0 else "0"
        return (
            f"ACTING CHARACTER SOULCREDIT:\n"
            f"  {character_name}: {score_str} [{sc_state.reputation_level}] "
            f"({'; '.join(round_parts)})"
        )

    def format_player_soulcredit(self, agent_id: str) -> str:
        """Format soulcredit for player-facing display (Codex kiosk query).

        Shows score, reputation, and per-round history trail.
        """
        if agent_id not in self.soulcredit_states:
            return "Soulcredit: 0 [Neutral]"
        sc_state = self.soulcredit_states[agent_id]

        score_str = f"{sc_state.score:+d}" if sc_state.score != 0 else "0"
        result = f"Soulcredit: {score_str} [{sc_state.reputation_level}]"

        if sc_state.history:
            from collections import defaultdict
            by_round = defaultdict(list)
            for entry in sc_state.history:
                r = entry.get('round')
                by_round[r].append(entry)

            round_parts = []
            for r in sorted(by_round.keys(), key=lambda x: (x is None, x)):
                entries = by_round[r]
                descs = [f"{e['change']:+d} ({e['reason']})" for e in entries]
                label = f"R{r}" if r is not None else "R?"
                round_parts.append(f"{label}: {', '.join(descs)}")

            result += f"\n  {' | '.join(round_parts)}"

        return result

    def has_offering(self, character_state: Any) -> tuple[bool, Optional[str], int]:
        """
        Check if character has any valid offering in inventory.

        Returns:
            tuple: (has_offering: bool, offering_type: str or None, quantity: int)
        """
        if not hasattr(character_state, 'inventory'):
            return (False, None, 0)

        # Check for valid offering items in inventory
        offering_keys = ['incense', 'purification_incense', 'blood_offering']
        for key in offering_keys:
            quantity = character_state.inventory.get(key, 0)
            if quantity > 0:
                return (True, key, quantity)

        return (False, None, 0)

    def consume_offering(self, character_state: Any, offering_type: Optional[str] = None) -> Optional[str]:
        """
        Consume one offering from character's inventory.

        Args:
            character_state: Character state with inventory
            offering_type: Specific offering to consume (or None to auto-select)

        Returns:
            Name of consumed offering, or None if failed
        """
        if not hasattr(character_state, 'inventory'):
            logger.warning(f"Character {getattr(character_state, 'name', 'unknown')} has no inventory")
            return None

        # If no specific offering requested, find any available
        if offering_type is None:
            has_any, offering_type, _ = self.has_offering(character_state)
            if not has_any:
                logger.warning(f"Character {character_state.name} has no offerings to consume")
                return None

        # Verify character has this offering
        quantity = character_state.inventory.get(offering_type, 0)
        if quantity <= 0:
            logger.warning(f"Character {character_state.name} has no {offering_type} to consume")
            return None

        # Consume the offering
        character_state.inventory[offering_type] = quantity - 1
        logger.info(f"Consumed 1 {offering_type} from {character_state.name}'s inventory (remaining: {quantity - 1})")

        return offering_type

    def craft_offering(
        self,
        character_state: Any,
        offering_type: str,
        materials: List[str]
    ) -> tuple[bool, str, Optional[str]]:
        """
        Craft an offering from raw materials using Attunement skill.

        Simple conversion (not full ritual) using Willpower × Attunement vs DC 15.
        Materials are consumed on attempt (success or failure).

        Args:
            character_state: Character attempting crafting
            offering_type: Offering to craft ('blood_offering', 'incense', 'crystals')
            materials: List of material keys to consume (e.g., ['blood_sample', 'herbs'])

        Returns:
            tuple: (success: bool, message: str, offering_name: str or None)

        Examples:
            - blood_sample → blood_offering
            - herbs → incense
            - raw_crystal → crystals
        """
        # Validate inventory exists
        if not hasattr(character_state, 'inventory'):
            return (False, "Character has no inventory", None)

        # Validate offering type is recognized
        valid_offerings = ['blood_offering', 'incense', 'crystals', 'purification_incense']
        if offering_type not in valid_offerings:
            return (False, f"Unknown offering type: {offering_type}", None)

        # Check if character has required materials
        for material in materials:
            if character_state.inventory.get(material, 0) <= 0:
                return (False, f"Missing required material: {material}", None)

        # Get Attunement skill and Willpower attribute
        attunement_skill = character_state.skills.get('attunement', 0)
        willpower_attr = character_state.attributes.get('willpower', 0)

        # Calculate skill pool (Attribute × Skill)
        skill_pool = willpower_attr + attunement_skill

        # Roll 2d8 (YAGS dice pool: 2 dice for skill check)
        die1 = random.randint(1, 8)
        die2 = random.randint(1, 8)
        total = skill_pool + die1 + die2

        # DC 15 base (simple conversion)
        dc = 15

        # Consume materials (happens regardless of success)
        for material in materials:
            character_state.inventory[material] -= 1
            logger.debug(f"Consumed 1 {material} for crafting attempt")

        # Determine success
        success = total >= dc
        margin = total - dc

        if success:
            # Add crafted offering to inventory
            current = character_state.inventory.get(offering_type, 0)
            character_state.inventory[offering_type] = current + 1

            message = f"Successfully crafted {offering_type} (roll: {total} vs DC {dc}, margin: +{margin})"
            logger.info(f"{character_state.name} crafted {offering_type}: {willpower_attr}+{attunement_skill}+{die1}+{die2}={total} vs DC {dc}")

            return (True, message, offering_type)
        else:
            message = f"Failed to craft {offering_type} (roll: {total} vs DC {dc}, margin: {margin}). Materials consumed."
            logger.info(f"{character_state.name} failed crafting {offering_type}: {willpower_attr}+{attunement_skill}+{die1}+{die2}={total} vs DC {dc}")

            return (False, message, None)

    def validate_purchase_request(
        self,
        item_name: str,
        vendor: Optional['Vendor'],
        character_state: Any
    ) -> PurchaseValidation:
        """
        Validate a purchase request BEFORE calling the DM.

        Checks:
        1. Vendor exists and is accessible
        2. Item exists in vendor inventory
        3. Character has sufficient currency
        4. Soulcredit threshold met (vendor-specific)

        Args:
            item_name: Name of item being purchased
            vendor: Vendor object (or None if vendor doesn't exist)
            character_state: Character making purchase

        Returns:
            PurchaseValidation with validation results
        """
        # Check vendor exists
        if vendor is None:
            return PurchaseValidation(
                is_valid=False,
                failure_reason="Vendor not found",
                vendor_accessible=False
            )

        # Check Soulcredit threshold (vendor-specific gating)
        character_sc = getattr(character_state, 'soulcredit', 0)
        vendor_type = getattr(vendor, 'vendor_type', VendorType.HUMAN_TRADER) if VendorType else None

        # SC gating rules
        if vendor_type == VendorType.VENDING_MACHINE:
            # Automated Nexus vendors require SC ≥ -2
            if character_sc < -2:
                return PurchaseValidation(
                    is_valid=False,
                    failure_reason=f"Soulcredit too low for vending machine (need ≥-2, have {character_sc})",
                    sc_blocked=True
                )
        elif hasattr(vendor, 'vendor_type') and str(vendor.vendor_type).lower() == 'tempest_drone':
            # Tempest Supply Drones have INVERTED SC (prefer low SC, block high SC)
            if character_sc >= 2:
                return PurchaseValidation(
                    is_valid=False,
                    failure_reason=f"Soulcredit too high for Tempest drone (need <2, have {character_sc})",
                    sc_blocked=True
                )

        # Find item in vendor inventory
        vendor_item = None
        for item in vendor.inventory:
            if item.name.lower() == item_name.lower():
                vendor_item = item
                break

        if vendor_item is None:
            return PurchaseValidation(
                is_valid=False,
                failure_reason=f"Item '{item_name}' not available from this vendor"
            )

        # Check currency sufficiency
        if not hasattr(character_state, 'energy_purse') or character_state.energy_purse is None:
            return PurchaseValidation(
                is_valid=False,
                failure_reason="Character has no energy purse"
            )

        energy_purse = character_state.energy_purse
        shortage = {}

        # Check each currency type in item cost
        for currency_type, required_amount in vendor_item.cost.items():
            available_amount = getattr(energy_purse, currency_type, 0)
            if available_amount < required_amount:
                shortage[currency_type] = required_amount - available_amount

        if shortage:
            # Build failure message
            shortage_parts = [f"{amt} {curr}" for curr, amt in shortage.items()]
            shortage_str = ", ".join(shortage_parts)
            return PurchaseValidation(
                is_valid=False,
                failure_reason=f"Insufficient currency (need {shortage_str} more)",
                shortage=shortage
            )

        # All checks passed
        return PurchaseValidation(is_valid=True)

    def validate_purchase(
        self,
        character_state: Any,
        vendor_id: str,
        item_id: str
    ) -> PurchaseValidation:
        """
        Validate purchase using vendor_id and item_id (unified vendor-NPC system).

        This is the ID-based validation for the mechanical purchase system.
        Checks BEFORE DM narration to prevent phantom purchases.
        Supports both legacy Vendor objects and unified NPC vendors.

        Args:
            character_state: Character attempting purchase
            vendor_id: Vendor ID (can be NPC agent_id like "npc_xxxx" or legacy "vnd_xxxx")
            item_id: Item ID (itm_xxxx)

        Returns:
            PurchaseValidation with full details for mechanical execution
        """
        # Get vendor by ID from shared state (try NPC vendor first, then legacy vendor)
        vendor = None
        if self.shared_state:
            # Try unified NPC vendor system first
            vendor = self.shared_state.get_npc_by_vendor_id(vendor_id)
            # Fall back to legacy vendor system
            if not vendor:
                vendor = self.shared_state.get_vendor_by_id(vendor_id)

        if vendor is None:
            return PurchaseValidation(
                is_valid=False,
                failure_reason=f"Vendor {vendor_id} not found",
                vendor_accessible=False
            )

        # Get item by ID from vendor (works for both NPC vendors and legacy vendors)
        item = vendor.get_vendor_item_by_id(item_id) if hasattr(vendor, 'get_vendor_item_by_id') else vendor.get_item_by_id(item_id)
        if item is None:
            return PurchaseValidation(
                is_valid=False,
                failure_reason=f"Item {item_id} not in {vendor.name} inventory"
            )

        # Check Soulcredit threshold
        character_sc = getattr(character_state, 'soulcredit', 0)

        # VIII.1 — the Gates: Nexus-aligned institutions check the Codex ledger.
        # Soulcredit -2 and under is cut off from their markets; per-item
        # soulcredit_requirement gates sanctioned/licensed gear. Freeborn /
        # Tempest / Independent markets do not ask. (The buyer knows their own
        # SC; the gate is where it becomes public — a ledger read.)
        from .energy_economy import is_nexus_aligned
        if is_nexus_aligned(getattr(vendor, 'faction', None)):
            if character_sc <= -2:
                return PurchaseValidation(
                    is_valid=False,
                    failure_reason=f"Soulcredit too low: {vendor.name} reads the "
                                   f"Codex ledger and refuses service ({character_sc} "
                                   f"is -2 or below — cut off from Nexus-aligned markets)",
                    sc_blocked=True,
                    item_name=item.name,
                    inventory_key=item.inventory_key
                )
            item_req = getattr(item, 'soulcredit_requirement', 0)
            if item_req and character_sc < item_req:
                return PurchaseValidation(
                    is_valid=False,
                    failure_reason=f"Standing insufficient: {item.name} requires "
                                   f"Soulcredit ≥ {item_req} (have {character_sc}); "
                                   f"the gate reads your ledger and declines",
                    sc_blocked=True,
                    item_name=item.name,
                    inventory_key=item.inventory_key
                )

        # Handle both VendorType enum (legacy) and string (NPC vendors)
        vendor_type_str = vendor.vendor_type.value if hasattr(vendor.vendor_type, 'value') else str(vendor.vendor_type) if vendor.vendor_type else None

        if vendor_type_str == "vending_machine":
            if character_sc < -2:
                return PurchaseValidation(
                    is_valid=False,
                    failure_reason=f"Soulcredit too low for vending machine (need ≥-2, have {character_sc})",
                    sc_blocked=True,
                    item_name=item.name,
                    inventory_key=item.inventory_key
                )

        # Check currency
        if not hasattr(character_state, 'energy_purse') or character_state.energy_purse is None:
            return PurchaseValidation(
                is_valid=False,
                failure_reason="Character has no energy purse",
                item_name=item.name,
                inventory_key=item.inventory_key
            )

        energy_purse = character_state.energy_purse
        cost = item.cost
        player_currency = {
            'spark': energy_purse.spark,
            'grain': energy_purse.grain,
            'drip': energy_purse.drip,
            'breath': energy_purse.breath
        }

        # Check affordability
        shortage = {}
        for currency_type, required_amount in cost.items():
            available_amount = player_currency.get(currency_type, 0)
            if available_amount < required_amount:
                shortage[currency_type] = required_amount - available_amount

        if shortage:
            shortage_parts = [f"{amt} {curr.title()}" for curr, amt in shortage.items()]
            shortage_str = ", ".join(shortage_parts)
            return PurchaseValidation(
                is_valid=False,
                failure_reason=f"Insufficient currency: need {shortage_str}",
                shortage=shortage,
                item_name=item.name,
                inventory_key=item.inventory_key,
                cost=cost,
                player_currency=player_currency
            )

        # Calculate surplus
        surplus = {}
        for currency_type, required_amount in cost.items():
            available_amount = player_currency.get(currency_type, 0)
            surplus[currency_type] = available_amount - required_amount

        # Success!
        return PurchaseValidation(
            is_valid=True,
            item_name=item.name,
            inventory_key=item.inventory_key,
            cost=cost,
            player_currency=player_currency,
            surplus=surplus
        )

    def validate_checkpoint_access(self, character_state: Any, checkpoint: Any) -> 'CheckpointAccess':
        """Gate access to a checkpoint / sector on Soulcredit standing (VIII.1).

        Nexus-aligned checkpoints check the ledger and apply the universal
        Cut-Off (SC <= -6, VIII.2). Any checkpoint may set its own
        soulcredit_requirement floor. Non-aligned checkpoints with no
        requirement do not ask. The holder knows their own SC; the checkpoint
        is where it becomes public — a ledger read.
        """
        from .energy_economy import is_nexus_aligned, SOULCREDIT_CUT_OFF
        character_sc = getattr(character_state, 'soulcredit', 0)
        name = getattr(checkpoint, 'name', 'checkpoint')
        aligned = is_nexus_aligned(getattr(checkpoint, 'faction', None))
        req = getattr(checkpoint, 'soulcredit_requirement', 0)

        if aligned:
            # Nexus-aligned gates require clean standing to walk through lawfully:
            # any negative Soulcredit is refused (floor 0), and an explicit
            # positive requirement raises the bar (e.g. +6 Trusted for a
            # restricted sector). SC <= -6 is the deeper Cut-Off tier (VIII.2).
            floor = max(0, req)
            if character_sc < floor:
                if character_sc <= SOULCREDIT_CUT_OFF:
                    reason = (f"Cut Off (VIII.2): Soulcredit {character_sc} is -6 or "
                              f"below — {name} denies passage; locked out of polite society")
                else:
                    reason = (f"Standing insufficient: {name} requires Soulcredit ≥ "
                              f"{floor} (have {character_sc}); the gate reads your "
                              f"ledger and refuses passage")
                return CheckpointAccess(is_allowed=False, checkpoint_name=name,
                                        sc_blocked=True, failure_reason=reason)
        elif req and character_sc < req:
            # Non-aligned gates only ask when they set an explicit requirement.
            return CheckpointAccess(
                is_allowed=False, checkpoint_name=name, sc_blocked=True,
                failure_reason=f"Standing insufficient: {name} requires Soulcredit "
                               f"≥ {req} (have {character_sc})")

        return CheckpointAccess(is_allowed=True, checkpoint_name=name)

    def validate_transfer(
        self,
        sender_state: Any,
        transfer_target: str,
        transfer_currency: Dict[str, int] = None,
        transfer_items: Dict[str, int] = None,
        sender_position: Any = None
    ) -> TransferValidation:
        """
        Validate energy and/or item transfer using target name/ID and amounts.

        This is pre-validation for the mechanical transfer system.
        Checks BEFORE DM narration to prevent impossible transfers.

        Args:
            sender_state: Character attempting transfer
            transfer_target: Target character name or agent_id
            transfer_currency: Currency amounts to transfer, e.g. {"drip": 5, "spark": 2} (optional)
            transfer_items: Item amounts to transfer, e.g. {"Incense": 2, "Crystals": 1} (optional)
            sender_position: Position object for range checking (optional)

        Returns:
            TransferValidation with full details for mechanical execution
        """
        # Default to empty dicts if not provided
        transfer_currency = transfer_currency or {}
        transfer_items = transfer_items or {}
        from .shared_state import SharedState

        # Get receiver by name, agent_id, or target_id from shared state
        receiver_agent = None
        receiver_state = None

        if self.shared_state:
            # Check for multi-target syntax (commas or semicolons) - not supported
            if ',' in transfer_target or ';' in transfer_target:
                return TransferValidation(
                    is_valid=False,
                    failure_reason=f"Multi-target transfers not supported. Transfer to one recipient at a time. Got: '{transfer_target}'"
                )

            # First, try to resolve target_id if it looks like one (tgt_xxxx format)
            if transfer_target.startswith('tgt_') and self.shared_state.target_id_mapper:
                receiver_agent = self.shared_state.target_id_mapper.resolve_target(transfer_target)
                if receiver_agent:
                    # Successfully resolved target ID to agent
                    receiver_state = receiver_agent.character_state if hasattr(receiver_agent, 'character_state') else None
                # If tgt_ lookup fails, DON'T return failure - fall through to search NPCs
                # This handles vendor NPCs which have agent_ids but not target_ids

            # If not resolved yet, try to find by agent_id or character name
            if receiver_agent is None:
                # Try to find by agent_id or character name in players
                for agent in self.shared_state.player_agents:
                    if agent.agent_id == transfer_target or agent.character_state.name.lower() == transfer_target.lower():
                        receiver_agent = agent
                        receiver_state = agent.character_state
                        break

                # If not found in players, check NPCs
                if receiver_agent is None and hasattr(self.shared_state, 'npc_agents'):
                    for npc in self.shared_state.npc_agents:
                        # NPCs may have .name directly or in .character_state
                        npc_name = getattr(npc, 'name', None)
                        if not npc_name and hasattr(npc, 'character_state'):
                            npc_name = getattr(npc.character_state, 'name', None)

                        if npc.agent_id == transfer_target or (npc_name and npc_name.lower() == transfer_target.lower()):
                            receiver_agent = npc
                            # NPCs may or may not have character_state
                            receiver_state = npc.character_state if hasattr(npc, 'character_state') else npc
                            break

        if receiver_state is None:
            return TransferValidation(
                is_valid=False,
                failure_reason=f"Target character '{transfer_target}' not found"
            )

        # Check range if positions available (only in tactical combat)
        in_range = True
        if sender_position and hasattr(receiver_agent, 'position') and receiver_agent.position:
            # Both must be in same range band for physical transfer
            sender_range = getattr(sender_position, 'ring', None)
            sender_side = getattr(sender_position, 'side', None)
            receiver_range = getattr(receiver_agent.position, 'ring', None)
            receiver_side = getattr(receiver_agent.position, 'side', None)

            # Only enforce range if BOTH have combat positions (ring/side)
            # In non-combat scenarios (marketplace, social), positions may be None
            if sender_range is not None and receiver_range is not None:
                if sender_range != receiver_range or sender_side != receiver_side:
                    in_range = False
                    return TransferValidation(
                        is_valid=False,
                        failure_reason=f"Out of range: {sender_state.name} and {receiver_state.name} are not in same range band",
                        sender_name=sender_state.name,
                        receiver_name=receiver_state.name,
                        receiver_agent_id=receiver_agent.agent_id,
                        in_range=False
                    )

        # Check sender has energy purse (if transferring currency)
        sender_currency = {}
        if transfer_currency:
            if not hasattr(sender_state, 'energy_purse') or sender_state.energy_purse is None:
                return TransferValidation(
                    is_valid=False,
                    failure_reason="Sender has no energy purse",
                    sender_name=sender_state.name,
                    receiver_name=receiver_state.name,
                    receiver_agent_id=receiver_agent.agent_id
                )

            energy_purse = sender_state.energy_purse
            sender_currency = {
                'spark': energy_purse.spark,
                'grain': energy_purse.grain,
                'drip': energy_purse.drip,
                'breath': energy_purse.breath
            }

            # Check sender has sufficient currency
            shortage = {}
            for currency_type, amount in transfer_currency.items():
                available = sender_currency.get(currency_type, 0)
                if available < amount:
                    shortage[currency_type] = amount - available

            if shortage:
                shortage_parts = [f"{amt} {curr.title()}" for curr, amt in shortage.items()]
                shortage_str = ", ".join(shortage_parts)
                return TransferValidation(
                    is_valid=False,
                    failure_reason=f"Insufficient currency: need {shortage_str}",
                    shortage=shortage,
                    sender_name=sender_state.name,
                    receiver_name=receiver_state.name,
                    receiver_agent_id=receiver_agent.agent_id,
                    currency=transfer_currency,
                    sender_currency=sender_currency
                )

        # Check sender has items (if transferring items)
        sender_items = {}
        if transfer_items:
            if not hasattr(sender_state, 'inventory') or sender_state.inventory is None:
                return TransferValidation(
                    is_valid=False,
                    failure_reason="Sender has no inventory",
                    sender_name=sender_state.name,
                    receiver_name=receiver_state.name,
                    receiver_agent_id=receiver_agent.agent_id
                )

            sender_items = dict(sender_state.inventory) if sender_state.inventory else {}

            # Check sender has sufficient items
            item_shortage = {}
            for item_name, amount in transfer_items.items():
                available = sender_items.get(item_name, 0)
                if available < amount:
                    item_shortage[item_name] = amount - available

            if item_shortage:
                shortage_parts = [f"{amt} {item}" for item, amt in item_shortage.items()]
                shortage_str = ", ".join(shortage_parts)
                return TransferValidation(
                    is_valid=False,
                    failure_reason=f"Insufficient items: need {shortage_str}",
                    item_shortage=item_shortage,
                    sender_name=sender_state.name,
                    receiver_name=receiver_state.name,
                    receiver_agent_id=receiver_agent.agent_id,
                    items=transfer_items,
                    sender_items=sender_items
                )

        # Success!
        return TransferValidation(
            is_valid=True,
            sender_name=sender_state.name,
            receiver_name=receiver_state.name,
            receiver_agent_id=receiver_agent.agent_id,
            currency=transfer_currency,
            items=transfer_items,
            sender_currency=sender_currency,
            sender_items=sender_items,
            in_range=in_range
        )

    def validate_attunement(
        self,
        character_state: Any,
        target_energy: Optional[str],
        altar_id: Optional[str] = None,
        use_echo_calibrator: bool = False
    ) -> AttunementValidation:
        """
        Validate seed attunement request BEFORE calling the DM.

        Checks:
        1. Player has at least one Raw Seed
        2. target_energy is specified
        3. If altar_id provided, altar exists and is accessible
        4. If use_echo_calibrator=True, player has Echo-Calibrator
        5. If Echo-Calibrator on 3rd use, player has 1 Drip for upkeep

        Args:
            character_state: Character attempting attunement
            target_energy: Target energy type ("breath", "grain", "drip", "spark")
            altar_id: Optional altar ID for bonus
            use_echo_calibrator: Whether using Echo-Calibrator device

        Returns:
            AttunementValidation with full details for execution
        """
        from .energy_economy import SeedType

        # Check target_energy is specified
        if not target_energy:
            return AttunementValidation(
                is_valid=False,
                failure_reason="Must specify target_energy (breath, grain, drip, or spark)",
                target_energy=target_energy
            )

        # Check player has energy purse
        if not hasattr(character_state, 'energy_purse') or character_state.energy_purse is None:
            return AttunementValidation(
                is_valid=False,
                failure_reason="Character has no energy purse",
                target_energy=target_energy
            )

        energy_purse = character_state.energy_purse

        # Check player has at least one Raw Seed
        raw_seed_count = energy_purse.count_seeds(SeedType.RAW)
        if raw_seed_count == 0:
            return AttunementValidation(
                is_valid=False,
                failure_reason="No Raw Seed available for attunement",
                has_raw_seed=False,
                target_energy=target_energy
            )

        # Initialize validation result
        validation = AttunementValidation(
            is_valid=True,
            has_raw_seed=True,
            target_energy=target_energy
        )

        # Check altar if specified
        if altar_id:
            if not self.shared_state:
                return AttunementValidation(
                    is_valid=False,
                    failure_reason=f"Altar '{altar_id}' not found (no shared state)",
                    has_raw_seed=True,
                    target_energy=target_energy,
                    altar_exists=False,
                    altar_id=altar_id
                )

            altar = self.shared_state.get_altar_by_id(altar_id)
            if not altar:
                return AttunementValidation(
                    is_valid=False,
                    failure_reason=f"Altar '{altar_id}' not found",
                    has_raw_seed=True,
                    target_energy=target_energy,
                    altar_exists=False,
                    altar_id=altar_id
                )

            # Altar exists, calculate bonus
            validation.altar_exists = True
            validation.altar_id = altar_id
            validation.altar_bonus = altar.get_ritual_bonus()

        # Check Echo-Calibrator if specified
        if use_echo_calibrator:
            # First check if player has Echo-Calibrator in inventory (capitalized with hyphen)
            if not hasattr(character_state, 'inventory') or not character_state.inventory:
                return AttunementValidation(
                    is_valid=False,
                    failure_reason="No Echo-Calibrator available (not in inventory)",
                    has_raw_seed=True,
                    target_energy=target_energy,
                    has_echo_calibrator=False,
                    altar_exists=validation.altar_exists,
                    altar_id=altar_id,
                    altar_bonus=validation.altar_bonus
                )

            # Check for all Echo-Calibrator inventory key variants
            # The same item can appear under different keys depending on source:
            # - "Echo-Calibrator" (display name with hyphen)
            # - "Echo Calibrator" (display name with space, shown in console)
            # - "echo_calibrator" (snake_case from session config inventory)
            # - "echo_calibrator_rental" (rental variant, snake_case)
            # - "Echo Calibrator Rental" (rental variant, display format)
            has_purchased = (
                character_state.inventory.get("Echo-Calibrator", 0) > 0 or
                character_state.inventory.get("Echo Calibrator", 0) > 0 or
                character_state.inventory.get("echo_calibrator", 0) > 0
            )
            has_rental = (
                character_state.inventory.get("echo_calibrator_rental", 0) > 0 or
                character_state.inventory.get("Echo Calibrator Rental", 0) > 0
            )

            if not (has_purchased or has_rental):
                return AttunementValidation(
                    is_valid=False,
                    failure_reason="No Echo-Calibrator available (not in inventory)",
                    has_raw_seed=True,
                    target_energy=target_energy,
                    has_echo_calibrator=False,
                    altar_exists=validation.altar_exists,
                    altar_id=altar_id,
                    altar_bonus=validation.altar_bonus
                )

            # Echo-Calibrator exists in inventory
            validation.has_echo_calibrator = True

            # Initialize item_metadata if needed (for usage tracking)
            if not hasattr(character_state, 'item_metadata') or character_state.item_metadata is None:
                character_state.item_metadata = {}
            if "echo_calibrator" not in character_state.item_metadata:
                character_state.item_metadata["echo_calibrator"] = {"usage_count": 0}

            calibrator_data = character_state.item_metadata["echo_calibrator"]
            usage_count = calibrator_data.get("usage_count", 0)
            validation.usage_count = usage_count

            # Check if upkeep required (every 3rd use)
            # Usage count 0, 1 → no upkeep
            # Usage count 2 → next use (3rd) requires upkeep
            if usage_count >= 2 and (usage_count + 1) % 3 == 0:
                validation.upkeep_required = True

                # Check player has 1 Drip for upkeep
                if energy_purse.drip >= 1:
                    validation.has_upkeep_currency = True
                else:
                    return AttunementValidation(
                        is_valid=False,
                        failure_reason="Insufficient Drip for Echo-Calibrator upkeep (need 1 Drip)",
                        has_raw_seed=True,
                        target_energy=target_energy,
                        has_echo_calibrator=True,
                        upkeep_required=True,
                        has_upkeep_currency=False,
                        usage_count=usage_count,
                        altar_exists=validation.altar_exists,
                        altar_id=altar_id,
                        altar_bonus=validation.altar_bonus
                    )

        # All checks passed!
        return validation

    def execute_attunement(
        self,
        character_state: Any,
        validation: AttunementValidation,
        use_echo_calibrator: bool = False
    ) -> 'AttunementEffect':
        """
        Execute seed attunement ritual after validation.

        Process:
        1. Consume 1 Raw Seed from energy purse
        2. Handle Echo-Calibrator check if used (DC 16 Dex+Craft/Tech)
        3. Roll attunement ritual (Willpower × Attunement + d20 + altar_bonus vs DC 20)
        4. On success: Award energy (100 breath, 50 grain, 20 drip, or 5 spark)
        5. On failure: No energy, seed still consumed
        6. Track upkeep and usage

        Args:
            character_state: Character performing attunement
            validation: Pre-validated attunement request
            use_echo_calibrator: Whether using Echo-Calibrator

        Returns:
            AttunementEffect with full ritual outcome
        """
        from .energy_economy import SeedType
        from .schemas.action_effects import AttunementEffect
        import random

        energy_purse = character_state.energy_purse

        # Consume Raw Seed
        seed = None
        for i, s in enumerate(energy_purse.seeds):
            if s.seed_type == SeedType.RAW:
                seed = energy_purse.seeds.pop(i)
                break

        if not seed:
            # This should never happen after validation, but be defensive
            return AttunementEffect(
                success=False,
                seed_consumed=False,
                energy_type=validation.target_energy,
                energy_gained=0,
                void_penalty=0
            )

        # Initialize effect
        effect = AttunementEffect(
            success=False,
            seed_consumed=True,
            energy_type=validation.target_energy,
            energy_gained=0,
            altar_id=validation.altar_id,
            altar_bonus=validation.altar_bonus,
            echo_calibrator_used=use_echo_calibrator
        )

        # Handle Echo-Calibrator if used
        calibrator_check_passed = True
        if use_echo_calibrator:
            # DC 16 Dex + Craft/Tech check
            dex = character_state.attributes.get('Agility', 0)  # Agility = Dex
            craft_tech = max(
                character_state.skills.get('Craft', 0),
                character_state.skills.get('Tech', 0)
            )
            calibrator_roll = random.randint(1, 20)
            calibrator_total = dex + craft_tech + calibrator_roll

            effect.calibrator_check_success = (calibrator_total >= 16)
            calibrator_check_passed = effect.calibrator_check_success

            if not calibrator_check_passed:
                # Failed calibrator check: +1 Void
                effect.calibrator_void = 1
                effect.void_penalty += 1

            # Handle upkeep
            if validation.upkeep_required:
                energy_purse.spend_currency("drip", 1)
                effect.upkeep_paid = True

            # Increment usage count
            if "echo_calibrator" not in character_state.item_metadata:
                character_state.item_metadata["echo_calibrator"] = {"usage_count": 0}
            character_state.item_metadata["echo_calibrator"]["usage_count"] += 1

        # Roll attunement ritual (Willpower × Attunement + d20 + bonuses vs DC 20)
        willpower = character_state.attributes.get('Willpower', 0)
        attunement_skill = character_state.skills.get('Attunement', 0)

        # YAGS standard: skilled = attr × skill, unskilled = d20 ÷ 2 (v1.2.3)
        roll_d20 = random.randint(1, 20)
        bonuses = validation.altar_bonus  # Altar provides bonus

        if attunement_skill > 0:
            ability = willpower * attunement_skill
            roll_total = ability + roll_d20 + bonuses
        else:
            # Unskilled: d20 ÷ 2 only (altar bonus still applies)
            ability = 0
            roll_total = (roll_d20 // 2) + bonuses

        effect.roll_total = roll_total
        effect.roll_margin = roll_total - 20  # DC 20

        # Determine success
        if roll_total >= 20:
            effect.success = True

            # Award energy based on type
            energy_amounts = {
                "breath": 100,
                "grain": 50,
                "drip": 20,
                "spark": 5
            }
            amount = energy_amounts.get(validation.target_energy, 0)
            energy_purse.add_currency(validation.target_energy, amount)
            effect.energy_gained = amount
        else:
            # Failed ritual: seed consumed, no energy
            effect.success = False
            effect.energy_gained = 0

        return effect

    def validate_consumption(
        self,
        character_state: Any,
        item_id: str,
        food_item: Any
    ) -> ConsumptionValidation:
        """
        Validate food consumption BEFORE calling DM.

        Checks:
        1. Item exists in character inventory
        2. Item is food (item_type="food")
        3. Character health < max_health (has room for healing)

        Args:
            character_state: CharacterState with inventory
            item_id: Item ID being consumed (itm_xxxx)
            food_item: VendorItem instance (for validation)

        Returns:
            ConsumptionValidation with is_valid and optional failure_reason
        """
        # Check if item is food
        if food_item.item_type != "food":
            return ConsumptionValidation(
                is_valid=False,
                failure_reason=f"Cannot consume {food_item.name}: item_type is '{food_item.item_type}', must be 'food'"
            )

        # Check if character has item in inventory
        inventory_key = food_item.inventory_key
        quantity = character_state.inventory.get(inventory_key, 0)
        if quantity <= 0:
            return ConsumptionValidation(
                is_valid=False,
                failure_reason=f"Character doesn't have {food_item.name} in inventory"
            )

        # Check if character needs healing
        if character_state.health >= character_state.max_health:
            return ConsumptionValidation(
                is_valid=False,
                failure_reason=f"Character is already at full health ({character_state.health}/{character_state.max_health} HP)"
            )

        # All checks passed
        return ConsumptionValidation(is_valid=True)

    def process_consumption_effect(
        self,
        consumption_effect: Any,
        character_state: Any
    ) -> bool:
        """
        Process food consumption effect.

        Applies healing and removes item from inventory.

        Args:
            consumption_effect: ConsumptionEffect with item_id, inventory_key, healing
            character_state: CharacterState being updated

        Returns:
            True if consumption succeeded
        """
        from .schemas.action_effects import ConsumptionEffect

        # Validate it's a ConsumptionEffect
        if not isinstance(consumption_effect, ConsumptionEffect):
            logger.error(f"Invalid consumption_effect type: {type(consumption_effect)}")
            return False

        # Get inventory key and current quantity
        inventory_key = consumption_effect.inventory_key
        current_quantity = character_state.inventory.get(inventory_key, 0)

        # Validate item exists
        if current_quantity <= 0:
            logger.error(f"Cannot consume {inventory_key}: quantity is {current_quantity}")
            return False

        # Remove item from inventory
        character_state.inventory[inventory_key] = current_quantity - 1
        logger.info(f"{character_state.name} consumed {inventory_key} ({current_quantity - 1} remaining)")

        # Apply healing (capped at max_health)
        hp_before = character_state.health
        character_state.health = min(
            character_state.health + consumption_effect.healing,
            character_state.max_health
        )
        hp_gained = character_state.health - hp_before

        logger.info(
            f"{character_state.name} healed {hp_gained} HP from consuming {inventory_key} "
            f"({hp_before} → {character_state.health}/{character_state.max_health})"
        )

        return True

    def validate_item_discovery(
        self,
        character_state: Any,
        item_effect: Any,
        player_id: str
    ) -> DiscoveryValidation:
        """
        Validate item discovery BEFORE applying ItemEffect.

        Checks configurable daily limits and prevents abuse.

        Configurable limits (via session config discovery_limits):
        - max_seeds_per_session (default: 3)
        - max_currency_per_session (default: 50 drip equivalent)
        - quest_rewards_bypass_limits (default: True)

        Args:
            character_state: CharacterState receiving items
            item_effect: ItemEffect with items_added and source
            player_id: Player ID for tracking daily limits

        Returns:
            DiscoveryValidation with is_valid, failure_reason, and optional capped_items
        """
        from .schemas.action_effects import ItemEffect

        # Validate it's an ItemEffect
        if not isinstance(item_effect, ItemEffect):
            return DiscoveryValidation(
                is_valid=False,
                failure_reason=f"Invalid item_effect type: {type(item_effect)}"
            )

        # Get discovery limits from config (with defaults)
        config = getattr(self.shared_state, 'session_config', {})
        limits = config.get('discovery_limits', {})
        max_seeds_per_session = limits.get('max_seeds_per_session', 3)
        max_currency_per_session = limits.get('max_currency_per_session', 50)
        quest_rewards_bypass = limits.get('quest_rewards_bypass_limits', True)

        # Quest rewards bypass limits
        if quest_rewards_bypass and item_effect.source in ['quest_reward', 'dm_award', 'bonus_for_success']:
            return DiscoveryValidation(is_valid=True, capped_items=item_effect.items_added)

        # Initialize discovery tracking if needed
        if not hasattr(self.shared_state, 'discovery_tracking'):
            self.shared_state.discovery_tracking = {}

        if player_id not in self.shared_state.discovery_tracking:
            self.shared_state.discovery_tracking[player_id] = {
                'seeds_discovered': 0,
                'currency_discovered': 0
            }

        tracking = self.shared_state.discovery_tracking[player_id]
        capped_items = item_effect.items_added.copy()

        # Count seeds in this discovery (only Raw Seeds - attunement creates currency, not Attuned Seeds)
        seed_keys = ['raw_seed_fresh', 'raw_seed_aged']
        seeds_in_discovery = sum(capped_items.get(key, 0) for key in seed_keys if key in capped_items)

        # Check seed limit
        if seeds_in_discovery > 0:
            seeds_after = tracking['seeds_discovered'] + seeds_in_discovery
            if seeds_after > max_seeds_per_session:
                remaining_seeds = max_seeds_per_session - tracking['seeds_discovered']
                if remaining_seeds <= 0:
                    return DiscoveryValidation(
                        is_valid=False,
                        failure_reason=f"Daily seed discovery limit reached ({max_seeds_per_session}/session)"
                    )

                # Cap seeds to remaining limit
                logger.warning(
                    f"{character_state.name} seed discovery capped: {seeds_in_discovery} → {remaining_seeds} "
                    f"(limit: {max_seeds_per_session}/session)"
                )

                # Distribute remaining seeds across seed types (prioritize first keys found)
                seeds_to_distribute = remaining_seeds
                for key in seed_keys:
                    if key in capped_items and seeds_to_distribute > 0:
                        original = capped_items[key]
                        capped_items[key] = min(original, seeds_to_distribute)
                        seeds_to_distribute -= capped_items[key]

        # Count currency (convert all to drip equivalent)
        currency_keys = {'breath': 1, 'grain': 1, 'drip': 1, 'spark': 1, 'hollow': 5}  # hollow = 5 drip
        currency_in_discovery = sum(
            capped_items.get(key, 0) * multiplier
            for key, multiplier in currency_keys.items()
            if key in capped_items
        )

        # Check currency limit
        if currency_in_discovery > 0:
            currency_after = tracking['currency_discovered'] + currency_in_discovery
            if currency_after > max_currency_per_session:
                remaining_currency = max_currency_per_session - tracking['currency_discovered']
                if remaining_currency <= 0:
                    return DiscoveryValidation(
                        is_valid=False,
                        failure_reason=f"Daily currency discovery limit reached ({max_currency_per_session} drip equivalent/session)"
                    )

                # Cap currency proportionally
                logger.warning(
                    f"{character_state.name} currency discovery capped: {currency_in_discovery} → {remaining_currency} drip equivalent "
                    f"(limit: {max_currency_per_session}/session)"
                )

                scale_factor = remaining_currency / currency_in_discovery
                for key in currency_keys.keys():
                    if key in capped_items:
                        capped_items[key] = int(capped_items[key] * scale_factor)

        # All checks passed (with capping applied)
        return DiscoveryValidation(is_valid=True, capped_items=capped_items)

    def validate_bond_formation(
        self,
        character_name: str,
        target_name: str,
        character_bonds: List['Bond'],
        character_void: int,
        target_void: int,
        origin: str,
        witnesses: List[str]
    ) -> Dict[str, Any]:
        """
        Validate bond formation request before creating Bond object.

        Checks:
        - Bond limits (max 3, Freeborn max 1)
        - Void prerequisites (both participants must have Void < 7)
        - Duplicate bond prevention
        - Witnessed requirement (warning if no witnesses)

        Args:
            character_name: Name of character initiating bond
            target_name: Name of bond target
            character_bonds: Current bonds for character
            character_void: Character's current void score
            target_void: Target's current void score
            origin: Character's origin ("freeborn" or other)
            witnesses: List of witness names

        Returns:
            Dict with 'valid' (bool), 'errors' (dict), 'warnings' (dict)
        """
        from .schemas.shared_types import Bond, BondStatus

        errors = {}
        warnings = {}

        # Check bond limits
        # Count all bonds (including dormant/severed) toward limit
        bond_count = len(character_bonds)
        max_bonds = 1 if origin.lower() == "freeborn" else 3

        if bond_count >= max_bonds:
            if origin.lower() == "freeborn":
                errors['bond_limit'] = f"{character_name} is Freeborn and can only have maximum of 1 Bond (currently has {bond_count})"
            else:
                errors['bond_limit'] = f"{character_name} has reached maximum of 3 Bonds (currently has {bond_count})"

        # Check Void prerequisites
        if character_void >= 7:
            errors['void_too_high'] = f"{character_name} has Void ≥ 7 ({character_void}) and cannot form new Bonds (existing Bonds become Dormant)"

        if target_void >= 7:
            errors['void_too_high'] = f"{target_name} has Void ≥ 7 ({target_void}) and cannot form new Bonds"

        # Check for duplicate bonds
        for bond in character_bonds:
            if bond.character_b == target_name:
                if bond.status == BondStatus.SEVERED:
                    errors['severed_bond'] = f"Cannot re-form severed Bond with {target_name}. Requires cleansing ritual first."
                else:
                    errors['duplicate_bond'] = f"Bond already exists with {target_name} (status: {bond.status.value})"
                break

        # Check witnessed requirement (warning only, not hard failure)
        if len(witnesses) == 0:
            warnings['no_witness_warning'] = "Bond formation without witnesses is taboo and may not be Codex-registered"

        # Determine if valid
        is_valid = len(errors) == 0

        return {
            'valid': is_valid,
            'errors': errors,
            'warnings': warnings
        }

    def get_bond_ritual_bonus(
        self,
        caster_name: str,
        caster_bonds: List['Bond'],
        participants: List[str]
    ) -> int:
        """
        Calculate ritual bonus from bonded participants.

        Bonds provide +2 bonus to Ritual Rolls when performing rituals
        together with bonded partners. Only ACTIVE bonds count.

        Args:
            caster_name: Name of ritual caster
            caster_bonds: Caster's current bonds
            participants: List of ritual participants (other characters present)

        Returns:
            +2 if any bonded partner is participating, 0 otherwise
        """
        from .schemas.shared_types import Bond, BondStatus

        # Check if any bonded partner is participating
        for bond in caster_bonds:
            # Only ACTIVE bonds provide benefits
            if bond.status != BondStatus.ACTIVE:
                continue

            # Check if bonded partner is participating
            if bond.character_b in participants:
                return 2

        return 0

    def get_bond_soak_bonus(
        self,
        defender_name: str,
        defender_bonds: List['Bond'],
        attacker_target: str
    ) -> int:
        """
        Calculate Soak bonus from defending bonded partner.

        Bonds provide +1 Soak when defending a bonded partner from attacks.
        Only ACTIVE bonds count. Does NOT apply when defender is the target.

        Args:
            defender_name: Name of character defending
            defender_bonds: Defender's current bonds
            attacker_target: Name of character being attacked

        Returns:
            +1 if defending bonded partner, 0 otherwise
        """
        from .schemas.shared_types import Bond, BondStatus

        # No bonus if defender is being attacked directly
        if attacker_target == defender_name:
            return 0

        # Check if target is a bonded partner
        for bond in defender_bonds:
            # Only ACTIVE bonds provide benefits
            if bond.status != BondStatus.ACTIVE:
                continue

            # Check if target is bonded partner
            if bond.character_b == attacker_target:
                return 1

        return 0

    def process_bond_sacrifice(
        self,
        character_name: str,
        character_bonds: List['Bond'],
        bond_target: str,
        current_round: int
    ) -> Dict[str, Any]:
        """
        Process bond sacrifice for +5 Willpower boost.

        Sacrificing a bond grants:
        - +5 to current Willpower-based roll
        - Bond status → SEVERED
        - +1 Void
        - +1 Soul Debt (owed to severed partner)
        - -1 Empathy penalty for the scene

        Can sacrifice ACTIVE or DORMANT bonds, not SEVERED or VOID_LOCKED.
        Once per session per bond (tracking not yet implemented).

        Args:
            character_name: Name of character sacrificing bond
            character_bonds: Character's current bonds
            bond_target: Name of bonded partner to sever
            current_round: Current round number

        Returns:
            Dict with success, willpower_bonus, costs, and updated bond
        """
        from .schemas.shared_types import Bond, BondStatus

        # Find the bond
        target_bond = None
        for bond in character_bonds:
            if bond.character_b == bond_target:
                target_bond = bond
                break

        # Validation
        if not target_bond:
            return {
                'success': False,
                'error': f"No bond exists with {bond_target}"
            }

        if target_bond.status == BondStatus.SEVERED:
            return {
                'success': False,
                'error': f"Bond with {bond_target} is already severed and cannot be sacrificed again"
            }

        if target_bond.status == BondStatus.VOID_LOCKED:
            return {
                'success': False,
                'error': f"Bond with {bond_target} is Void-Locked and cannot be sacrificed (too corrupted)"
            }

        # Process sacrifice
        # Update bond status
        target_bond.status = BondStatus.SEVERED

        return {
            'success': True,
            'willpower_bonus': 5,
            'void_change': 1,
            'soul_debt_target': bond_target,
            'soul_debt_change': 1,
            'empathy_penalty': -1,
            'empathy_condition': {
                'name': 'Bond Sacrifice Trauma',
                'penalty': -1,
                'duration': 'scene',
                'description': f"Severed bond with {bond_target}, heart is heavy"
            },
            'bond_status': BondStatus.SEVERED,
            'narrative': f"{character_name} sacrificed their bond with {bond_target} for a desperate surge of power"
        }

    def check_bond_dormancy(
        self,
        character_name: str,
        character_bonds: List['Bond'],
        current_void: int,
        previous_void: int
    ) -> Dict[str, Any]:
        """
        Check and update bond statuses based on Void score changes.

        Automatic transitions:
        - Void ≥ 7: ACTIVE → DORMANT (no mechanical benefits)
        - Void < 7: DORMANT → ACTIVE (benefits restored)
        - Void = 10: ACTIVE/DORMANT → VOID_LOCKED (permanent corruption)

        SEVERED bonds never transition (require cleansing ritual to restore).
        VOID_LOCKED bonds never revert (permanent corruption).

        Args:
            character_name: Name of character
            character_bonds: Character's current bonds
            current_void: Current void score (0-10)
            previous_void: Previous void score (for transition detection)

        Returns:
            Dict with status_changed, transitions, reactivations, void_locked, changes (for JSONL)
        """
        from .schemas.shared_types import Bond, BondStatus

        # Early return if no bonds
        if not character_bonds:
            return {
                'status_changed': False,
                'transitions': 0,
                'reactivations': 0,
                'void_locked': False,
                'changes': []
            }

        transitions = 0
        reactivations = 0
        void_locked_count = 0
        changes = []

        # Check each bond for status transitions
        for bond in character_bonds:
            old_status = bond.status

            # VOID_LOCKED and SEVERED bonds never change
            if bond.status in [BondStatus.VOID_LOCKED, BondStatus.SEVERED]:
                continue

            # Void = 10: Lock all non-severed bonds (permanent)
            if current_void == 10:
                bond.status = BondStatus.VOID_LOCKED
                void_locked_count += 1
                changes.append({
                    'bond_id': bond.bond_id,
                    'character_a': bond.character_a,
                    'character_b': bond.character_b,
                    'old_status': old_status,
                    'new_status': BondStatus.VOID_LOCKED,
                    'reason': 'void_corruption',
                    'void_score': current_void
                })

            # Void ≥ 7: ACTIVE → DORMANT
            elif current_void >= 7 and bond.status == BondStatus.ACTIVE:
                bond.status = BondStatus.DORMANT
                transitions += 1
                changes.append({
                    'bond_id': bond.bond_id,
                    'character_a': bond.character_a,
                    'character_b': bond.character_b,
                    'old_status': old_status,
                    'new_status': BondStatus.DORMANT,
                    'reason': 'void_threshold',
                    'void_score': current_void
                })

            # Void < 7: DORMANT → ACTIVE (restoration)
            elif current_void < 7 and bond.status == BondStatus.DORMANT:
                bond.status = BondStatus.ACTIVE
                reactivations += 1
                changes.append({
                    'bond_id': bond.bond_id,
                    'character_a': bond.character_a,
                    'character_b': bond.character_b,
                    'old_status': old_status,
                    'new_status': BondStatus.ACTIVE,
                    'reason': 'void_recovery',
                    'void_score': current_void
                })

        return {
            'status_changed': len(changes) > 0,
            'transitions': transitions,
            'reactivations': reactivations,
            'void_locked': void_locked_count > 0,
            'changes': changes
        }

    def process_item_effect(
        self,
        item_effect: Any,
        character_state: Any,
        player_id: str
    ) -> bool:
        """
        Process ItemEffect from DM structured output.

        Adds items/seeds/currency to character inventory and energy purse.
        Special seed keys are converted to Seed objects.

        Seed keys (converted to Seed objects in energy_purse.seeds):
        - raw_seed_fresh → Seed(RAW, cycles=10-14, origin=source)
        - raw_seed_aged → Seed(RAW, cycles=3-6, origin=source)

        Note: Attunement converts Raw Seeds → Currency (breath/grain/drip/spark), NOT Attuned Seeds.
        Attuned Seeds are legacy/unused in current economy.

        Currency keys (added directly to EnergyPurse attributes):
        - breath, grain, drip, spark, hollow

        Standard items (added to inventory Dict[str, int]):
        - Any other key → item_name: quantity

        Args:
            item_effect: ItemEffect with items_added and source
            character_state: Character receiving items
            player_id: Player ID for tracking discovery limits

        Returns:
            True if processing succeeded
        """
        from .schemas.action_effects import ItemEffect
        from .energy_economy import Seed, SeedType, Element

        # Convert dict to ItemEffect if needed (dm.py passes dict via model_dump())
        if isinstance(item_effect, dict):
            try:
                item_effect = ItemEffect(**item_effect)
                logger.debug(f"Converted dict to ItemEffect: {item_effect}")
            except Exception as e:
                logger.error(f"Failed to convert dict to ItemEffect: {e}")
                return False
        elif not isinstance(item_effect, ItemEffect):
            logger.error(f"Invalid item_effect type: {type(item_effect)}")
            return False

        # Validate discovery (applies daily limits, returns capped items)
        validation = self.validate_item_discovery(character_state, item_effect, player_id)
        if not validation.is_valid:
            logger.error(f"Discovery validation failed for {character_state.name}: {validation.failure_reason}")
            return False

        # Use capped items (after applying limits)
        items_to_add = validation.capped_items

        # Track discovery for limits
        tracking = self.shared_state.discovery_tracking[player_id]
        seed_keys = ['raw_seed_fresh', 'raw_seed_aged']
        currency_keys = {'breath': 1, 'grain': 1, 'drip': 1, 'spark': 1, 'hollow': 5}

        seeds_added = sum(items_to_add.get(key, 0) for key in seed_keys if key in items_to_add)
        currency_added = sum(
            items_to_add.get(key, 0) * mult
            for key, mult in currency_keys.items()
            if key in items_to_add
        )

        tracking['seeds_discovered'] += seeds_added
        tracking['currency_discovered'] += currency_added

        # Process each item
        for item_key, quantity in items_to_add.items():
            if quantity <= 0:
                continue

            # Seed conversion
            if item_key == 'raw_seed_fresh':
                for _ in range(quantity):
                    seed = Seed(
                        seed_type=SeedType.RAW,
                        cycles_remaining=random.randint(10, 14),
                        origin=item_effect.source
                    )
                    character_state.energy_purse.seeds.append(seed)
                logger.info(f"{character_state.name} found {quantity}x Fresh Raw Seeds (source: {item_effect.source})")

            elif item_key == 'raw_seed_aged':
                for _ in range(quantity):
                    seed = Seed(
                        seed_type=SeedType.RAW,
                        cycles_remaining=random.randint(3, 6),
                        origin=item_effect.source
                    )
                    character_state.energy_purse.seeds.append(seed)
                logger.info(f"{character_state.name} found {quantity}x Aged Raw Seeds (source: {item_effect.source})")

            # Currency addition
            elif item_key == 'breath':
                character_state.energy_purse.breath += quantity
                logger.info(f"{character_state.name} found {quantity} Breath (source: {item_effect.source})")

            elif item_key == 'grain':
                character_state.energy_purse.grain += quantity
                logger.info(f"{character_state.name} found {quantity} Grain (source: {item_effect.source})")

            elif item_key == 'drip':
                character_state.energy_purse.drip += quantity
                logger.info(f"{character_state.name} found {quantity} Drip (source: {item_effect.source})")

            elif item_key == 'spark':
                character_state.energy_purse.spark += quantity
                logger.info(f"{character_state.name} found {quantity} Spark (source: {item_effect.source})")

            elif item_key == 'hollow':
                character_state.energy_purse.hollow += quantity
                logger.info(f"{character_state.name} found {quantity} Hollow (source: {item_effect.source})")

            # Standard inventory items
            else:
                current_quantity = character_state.inventory.get(item_key, 0)
                character_state.inventory[item_key] = current_quantity + quantity
                logger.info(
                    f"{character_state.name} found {quantity}x {item_key} "
                    f"({current_quantity} → {current_quantity + quantity}, source: {item_effect.source})"
                )

        return True

    def process_purchase_effect(
        self,
        purchase_effect: Any,
        character_state: Any
    ) -> bool:
        """
        Process a PurchaseEffect from DM structured output.

        Deducts currency and adds items to inventory based on DM adjudication.

        Args:
            purchase_effect: PurchaseEffect object or dict from ActionResolution.effects.purchase
            character_state: Character making the purchase

        Returns:
            True if processing succeeded, False otherwise
        """
        if not purchase_effect:
            logger.debug(f"No purchase effect for {character_state.name}")
            return False

        # Convert dict to PurchaseEffect if needed
        from .schemas.vendor_interaction import PurchaseEffect
        if isinstance(purchase_effect, dict):
            try:
                purchase_effect = PurchaseEffect(**purchase_effect)
                logger.debug(f"Converted dict to PurchaseEffect for {character_state.name}")
            except Exception as e:
                logger.error(f"Failed to convert purchase effect dict to Pydantic model: {e}")
                logger.error(f"Purchase effect data: {purchase_effect}")
                return False

        if not purchase_effect.success:
            logger.info(f"Purchase failed for {character_state.name}: {purchase_effect.failure_reason if purchase_effect.failure_reason else 'Unknown reason'}")
            return False

        # Deduct currency
        for currency_type, amount in purchase_effect.currency_spent.items():
            if hasattr(character_state, 'energy_purse') and character_state.energy_purse:
                success = character_state.energy_purse.spend_currency(currency_type, amount)
                if not success:
                    logger.error(f"Failed to deduct {amount} {currency_type} from {character_state.name} - insufficient funds!")
                    return False
                logger.info(f"Deducted {amount} {currency_type} from {character_state.name}")
            else:
                logger.warning(f"Character {character_state.name} has no energy_purse")
                return False

        # Add items to inventory
        for item_name in purchase_effect.items_purchased:
            inventory_key = self._map_vendor_item_to_inventory_key(item_name)

            if hasattr(character_state, 'inventory'):
                current = character_state.inventory.get(inventory_key, 0)
                character_state.inventory[inventory_key] = current + 1
                logger.info(f"Added {item_name} → {inventory_key} to {character_state.name}'s inventory (now: {current + 1})")
            else:
                logger.warning(f"Character {character_state.name} has no inventory")
                return False

        logger.info(f"Successfully processed purchase for {character_state.name}: {purchase_effect.items_purchased} from {purchase_effect.vendor_name}")
        return True

    # Canonical mapping of vendor item names to inventory keys
    VENDOR_ITEM_TO_INVENTORY = {
        # Ritual items
        "Blood Offering": "blood_offering",
        "Blood Offering (Sanctified)": "blood_offering",
        "Incense Bundle": "incense",
        "Incense": "incense",
        "Raw Crystal": "raw_crystal",
        "Crystals": "raw_crystal",

        # Tech items
        "Echo-Calibrator": "echo_calibrator",
        "Echo Calibrator": "echo_calibrator",
        "Resonance Dampener": "resonance_dampener",
        "Portable Ley Anchor": "portable_ley_anchor",
        "Scrambled ID Chip": "scrambled_id_chip",
        "Data Slate (Encrypted)": "data_slate_encrypted",

        # Medical
        "Health Kit": "med_kit",
        "Medkit": "med_kit",
        "Med Kit": "med_kit",

        # Seeds
        "Attuned Seed (Fire)": "attuned_seed_fire",
        "Attuned Seed (Water)": "attuned_seed_water",
        "Attuned Seed (Earth)": "attuned_seed_earth",
        "Attuned Seed (Air)": "attuned_seed_air",
        "Attuned Seed (Spirit)": "attuned_seed_spirit",
        "Raw Seed": "raw_seed",
        "Hollow Seed": "hollow_seed",

        # Financial
        "Bond Insurance Policy": "bond_insurance_policy",
    }

    def _map_vendor_item_to_inventory_key(self, item_name: str) -> str:
        """
        Map vendor item name to character inventory key.

        Uses canonical mapping table with fallback normalization.

        Args:
            item_name: Vendor's name for the item (e.g., "Echo-Calibrator")

        Returns:
            Inventory key (e.g., "echo_calibrator")
        """
        # Check canonical mapping first
        if item_name in self.VENDOR_ITEM_TO_INVENTORY:
            return self.VENDOR_ITEM_TO_INVENTORY[item_name]

        # Fallback: normalize name
        normalized = item_name.lower().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '')
        logger.debug(f"No canonical mapping for '{item_name}', using normalized: '{normalized}'")
        return normalized

    def process_crafting_effect(
        self,
        crafting_effect: Any,
        character_state: Any
    ) -> bool:
        """
        Process a CraftingAttempt from DM structured output.

        Note: Materials should already be consumed by craft_offering() before DM narration.
        This just logs the outcome and ensures inventory is updated correctly.

        Args:
            crafting_effect: CraftingAttempt object or dict from ActionResolution.effects.crafting
            character_state: Character who attempted crafting

        Returns:
            True if processing succeeded, False otherwise
        """
        if not crafting_effect:
            logger.debug(f"No crafting effect for {character_state.name}")
            return False

        # Convert dict to CraftingAttempt if needed
        from .schemas.vendor_interaction import CraftingAttempt
        if isinstance(crafting_effect, dict):
            try:
                crafting_effect = CraftingAttempt(**crafting_effect)
                logger.debug(f"Converted dict to CraftingAttempt for {character_state.name}")
            except Exception as e:
                logger.error(f"Failed to convert crafting effect dict to Pydantic model: {e}")
                logger.error(f"Crafting effect data: {crafting_effect}")
                return False

        if crafting_effect.success:
            # Verify offering was added (should already be done by craft_offering)
            offering_type = crafting_effect.offering_type
            if hasattr(character_state, 'inventory'):
                quantity = character_state.inventory.get(offering_type, 0)
                logger.info(f"Crafting success verified: {character_state.name} has {quantity} {offering_type}")
                return True
            else:
                logger.warning(f"Character {character_state.name} has no inventory")
                return False
        else:
            # Crafting failed - materials already consumed by craft_offering()
            logger.info(f"Crafting failed for {character_state.name}: {crafting_effect.offering_type}")
            return True  # Still "successful" processing, just failed crafting

    def process_attunement_effect(
        self,
        attunement_effect: Any,
        character_state: Any
    ) -> bool:
        """
        Process an AttunementEffect from DM structured output.

        Consumes seed from inventory and grants energy currency based on DM adjudication.

        Args:
            attunement_effect: AttunementEffect object or dict from ActionResolution.effects.attunement
            character_state: Character performing the attunement

        Returns:
            True if processing succeeded, False otherwise
        """
        if not attunement_effect:
            logger.debug(f"No attunement effect for {character_state.name}")
            return False

        # Convert dict to AttunementEffect if needed
        from .schemas.action_effects import AttunementEffect
        if isinstance(attunement_effect, dict):
            try:
                attunement_effect = AttunementEffect(**attunement_effect)
                logger.debug(f"Converted dict to AttunementEffect for {character_state.name}")
            except Exception as e:
                logger.error(f"Failed to convert attunement effect dict to Pydantic model: {e}")
                logger.error(f"Attunement effect data: {attunement_effect}")
                return False

        # Consume the seed (always happens, even on failure)
        if attunement_effect.seed_consumed:
            # Get energy purse directly from character state
            if not hasattr(character_state, 'energy_purse') or not character_state.energy_purse:
                logger.error(f"No energy purse found for {character_state.name}")
                return False

            energy_purse = character_state.energy_purse

            # Use EnergyPurse.consume_seed() method
            from .energy_economy import SeedType
            seed = energy_purse.consume_seed(SeedType.RAW)
            if seed:
                logger.info(f"Consumed 1 Raw Seed from {character_state.name} (had {seed.cycles_remaining} cycles remaining, origin: {seed.origin})")
            else:
                logger.error(f"Failed to consume seed from {character_state.name} - no Raw Seeds in energy purse!")
                return False

        # Grant energy if successful
        if attunement_effect.success and attunement_effect.energy_gained > 0:
            if not hasattr(character_state, 'energy_purse') or not character_state.energy_purse:
                logger.error(f"No energy purse found for {character_state.name}")
                return False

            energy_purse = character_state.energy_purse
            energy_type = attunement_effect.energy_type
            amount = attunement_effect.energy_gained

            # Use EnergyPurse.add_currency() method
            energy_purse.add_currency(energy_type, amount)
            logger.info(f"Granted {amount} {energy_type} to {character_state.name} from successful attunement")

        # Handle Echo-Calibrator upkeep if paid
        if attunement_effect.upkeep_paid:
            if not hasattr(character_state, 'energy_purse') or not character_state.energy_purse:
                logger.warning(f"No energy purse for upkeep deduction from {character_state.name}")
            else:
                energy_purse = character_state.energy_purse
                success = energy_purse.spend_currency("drip", 1)
                if success:
                    logger.info(f"Deducted 1 Drip upkeep from {character_state.name} for Echo-Calibrator 3rd use")
                else:
                    logger.error(f"Failed to deduct Echo-Calibrator upkeep from {character_state.name}")

        # Log the outcome
        if attunement_effect.success:
            logger.info(
                f"✓ ATTUNEMENT SUCCESS: {character_state.name} converted 1 Raw Seed → {attunement_effect.energy_gained} {attunement_effect.energy_type} "
                f"(altar: {attunement_effect.altar_id if attunement_effect.altar_id else 'none'}, "
                f"bonus: {attunement_effect.altar_bonus if attunement_effect.altar_bonus else 0})"
            )
        else:
            logger.info(
                f"✗ ATTUNEMENT FAILED: {character_state.name} lost 1 Raw Seed, gained 0 energy "
                f"(void penalty: {attunement_effect.void_penalty if attunement_effect.void_penalty else 0})"
            )

        return True

    def check_void_trigger(
        self,
        action: str,
        agent_id: str,
        context: Dict[str, Any]
    ) -> int:
        """
        Check if an action should trigger void gain.

        Returns:
            Amount of void to add (0 if none)
        """
        void_triggers = {
            'void_exposure': 1,
            'ritual_shortcut': 1,
            'bond_betrayal': 2,
            'void_manipulation': 1,
            'corrupted_tech': 1,
        }

        action_lower = action.lower()
        for trigger, amount in void_triggers.items():
            if trigger.replace('_', ' ') in action_lower:
                void_state = self.get_void_state(agent_id)
                void_state.add_void(amount, f"Action: {action}")
                logger.info(f"{agent_id} gained {amount} Void from {action}")
                return amount

        return 0

    def create_scene_clock(
        self,
        name: str,
        maximum: int = 6,
        description: str = "",
        advance_meaning: str = "",
        regress_meaning: str = "",
        filled_consequence: str = "",
        timeout_rounds: int = None,
        is_terminal: bool = False,
        terminal_outcome: str = "victory"
    ) -> SceneClock:
        """
        Create and register a scene clock with semantic metadata.

        Args:
            name: Clock name (e.g., "Evidence Collection")
            maximum: Max ticks before filling
            description: What the clock tracks
            advance_meaning: What it means to advance (e.g., "More evidence discovered")
            regress_meaning: What it means to regress (e.g., "Evidence destroyed")
            filled_consequence: What happens when filled (e.g., "Case ready for prosecution")
            timeout_rounds: Rounds until clock expires (None = auto-calculated based on maximum)
            is_terminal: If True, filling this clock resolves the scene and ends the session
            terminal_outcome: Session outcome when a terminal clock fills (victory/defeat/draw)
        """
        # Clock conservation: replacing an existing clock by name is an
        # update, not a spawn; new spawns respect the concurrent cap and
        # the per-round budget (round 0 = session setup, exempt).
        if name not in self.scene_clocks:
            if len(self.scene_clocks) >= self.max_active_clocks:
                self._log_clock_spawn_rejected(name, "max_active_clocks")
                return None
            if self.current_round >= 1:
                if self._clock_spawn_round != self.current_round:
                    self._clock_spawn_round = self.current_round
                    self._clock_spawns_this_round = 0
                if self._clock_spawns_this_round >= self.max_clock_spawns_per_round:
                    self._log_clock_spawn_rejected(
                        name, "max_clock_spawns_per_round")
                    return None
                self._clock_spawns_this_round += 1

        # Auto-assign varied timeouts to prevent all clocks expiring simultaneously
        if timeout_rounds is None:
            if maximum <= 4:
                timeout_rounds = 4  # Small clocks expire faster (4 rounds)
            elif maximum <= 6:
                timeout_rounds = 6  # Medium clocks get standard time (6 rounds)
            elif maximum <= 8:
                timeout_rounds = 7  # Larger clocks get more time (7 rounds)
            else:
                timeout_rounds = 8  # Very large clocks get longest time (8 rounds)
            logger.debug(f"Clock {name} auto-assigned timeout: {timeout_rounds} rounds (based on max={maximum})")

        clock = SceneClock(
            name=name,
            maximum=maximum,
            description=description,
            advance_meaning=advance_meaning,
            regress_meaning=regress_meaning,
            filled_consequence=filled_consequence,
            timeout_rounds=timeout_rounds,
            is_terminal=is_terminal,
            terminal_outcome=terminal_outcome
        )
        self.scene_clocks[name] = clock
        return clock

    def _log_clock_spawn_rejected(self, name: str, reason: str) -> None:
        logger.warning(f"Clock spawn REJECTED ({reason}): {name} "
                       f"(active={len(self.scene_clocks)}, "
                       f"round_spawns={self._clock_spawns_this_round})")
        if self.jsonl_logger:
            self.jsonl_logger.log_event(
                event_type="clock_spawn_rejected",
                data={"clock_name": name, "reason": reason,
                      "active_clocks": len(self.scene_clocks)},
                round_num=self.current_round
            )

    def _record_terminal_completion(self, clock: 'SceneClock', reason: str = "", outcome_override: str = None):
        """
        Capture the resolving beat when a terminal clock reaches an end state.

        Two triggers:
          * a terminal clock FILLS  -> resolves with the clock's terminal_outcome
            (a goal clock = victory/draw; a doom clock = defeat / catastrophe)
          * a DOOM clock is driven to 0 -> threat neutralised, pass
            outcome_override='victory' (aversion win)

        Sets self.terminal_completion (a snapshot dict) the FIRST time any terminal
        clock resolves; later ones are ignored so the session has exactly one ending.
        The session loop reads this to declare session_end, and the resolve-then-leap
        continuation reads it to know what beat resolved the chapter.
        """
        if not getattr(clock, 'is_terminal', False):
            return
        if self.terminal_completion is not None:
            return  # one ending per session - first terminal clock wins

        self.terminal_completion = {
            'clock_name': clock.name,
            'outcome': outcome_override or getattr(clock, 'terminal_outcome', 'victory'),
            'filled_consequence': clock.filled_consequence,
            'reason': reason or clock.filled_consequence,
            'round': self.current_round,
        }
        logger.info(
            f"🏁 TERMINAL CLOCK RESOLVED: {clock.name} -> session resolves "
            f"({self.terminal_completion['outcome']})"
        )

    def advance_clock(
        self,
        clock_name: str,
        ticks: int = 1,
        reason: str = ""
    ) -> bool:
        """
        Advance a scene clock.

        Returns:
            True if clock is filled (at or above maximum)
        """
        if clock_name not in self.scene_clocks:
            logger.warning(f"Clock {clock_name} does not exist")
            return False

        clock = self.scene_clocks[clock_name]
        was_filled_before = clock.current >= clock.maximum
        filled = clock.advance(ticks)

        if filled:
            overflow = clock.current - clock.maximum
            if overflow > 0:
                # Clock is overflowing - increasing urgency!
                if overflow >= 3:
                    logger.error(f"🚨 Clock {clock_name} CRITICAL OVERFLOW: {clock.current}/{clock.maximum} (+{overflow})! Reason: {reason}")
                elif overflow >= 1:
                    logger.warning(f"⚠️  Clock {clock_name} OVERFLOWING: {clock.current}/{clock.maximum} (+{overflow})! Reason: {reason}")
            elif not was_filled_before:
                # First time filling
                logger.info(f"🔔 Clock {clock_name} FILLED: {clock.current}/{clock.maximum}! Reason: {reason}")
            else:
                # Already filled, but advancing at maximum
                logger.warning(f"⚠️  Clock {clock_name} remains filled: {clock.current}/{clock.maximum}! Reason: {reason}")

            # Trigger consequences (stores for DM synthesis)
            self._trigger_clock_consequences(clock_name, reason)

            # A terminal clock filling resolves the scene -> signal session end
            self._record_terminal_completion(clock, reason)

        return filled

    def _trigger_clock_consequences(self, clock_name: str, reason: str):
        """
        Signal that a clock filled - consequences should be generated by DM.
        Store the filled clock for the DM to narrate consequences.
        """
        # Just log that it filled - the DM will generate consequences
        logger.warning(f"⚠️  CLOCK FILLED: {clock_name} - DM should generate consequences!")

        # Store for DM to handle
        if not hasattr(self, '_filled_clocks_this_round'):
            self._filled_clocks_this_round = []

        # Hand the DM the clock's in-world consequence (never empty) so the
        # synthesis renders the resolution as fact instead of improvising a
        # near-miss. Falls back to a synthesized consequence when unauthored.
        clock = self.scene_clocks.get(clock_name)
        consequence = clock.effective_consequence if clock else ""

        self._filled_clocks_this_round.append({
            'clock_name': clock_name,
            'reason': reason,
            'consequence': consequence,
        })

    def get_and_clear_filled_clocks(self):
        """Get clocks that filled this round and clear the list."""
        filled = getattr(self, '_filled_clocks_this_round', [])
        self._filled_clocks_this_round = []
        return filled

    def get_all_clocks(self) -> List[Dict[str, Any]]:
        """
        Get all active scene clocks as list of dicts.

        Returns:
            List of clock dicts with keys: name, current_ticks, max_ticks, description, filled
        """
        clock_list = []
        for name, clock in self.scene_clocks.items():
            clock_list.append({
                'name': name,
                'current_ticks': clock.current,
                'max_ticks': clock.maximum,
                'description': clock.description,
                'filled': clock.filled  # Include filled flag so conversion check can see it
            })
        return clock_list

    def queue_clock_update(self, clock_name: str, ticks: int, reason: str):
        """
        Queue a clock update to be applied during synthesis phase.

        This prevents cascade fills during action resolution.
        All queued updates are applied at once via apply_queued_clock_updates().

        Args:
            clock_name: Name of the clock to update
            ticks: Number of ticks to advance (positive) or regress (negative)
            reason: Reason for the update
        """
        self.clock_update_queue.append((clock_name, ticks, reason))
        logger.debug(f"Queued clock update: {clock_name} {ticks:+d} ({reason})")

    def apply_queued_clock_updates(self) -> Dict[str, Dict[str, Any]]:
        """
        Apply all queued clock updates at once during synthesis phase.

        This prevents cascade fills - all updates happen simultaneously,
        then we check for fills ONCE at the end.

        Returns:
            Dict of clock_name -> {'before': int, 'after': int, 'maximum': int, 'reason': str, 'direction': str}
        """
        if not self.clock_update_queue:
            return {}

        clock_final_states = {}

        # Group updates by clock name to aggregate them
        aggregated_updates = {}
        for clock_name, ticks, reason in self.clock_update_queue:
            if clock_name not in aggregated_updates:
                aggregated_updates[clock_name] = {'ticks': 0, 'reasons': []}
            aggregated_updates[clock_name]['ticks'] += ticks
            aggregated_updates[clock_name]['reasons'].append(reason)

        # Apply all aggregated updates
        for clock_name, update_data in aggregated_updates.items():
            if clock_name in self.scene_clocks:
                clock = self.scene_clocks[clock_name]
                before = clock.current
                maximum = clock.maximum
                total_ticks = update_data['ticks']
                reasons = update_data['reasons']

                if total_ticks < 0:
                    # Negative ticks = regress (improve)
                    clock.regress(abs(total_ticks))
                    direction = "↓"
                elif total_ticks > 0:
                    # Positive ticks = advance
                    clock.advance(total_ticks)
                    direction = "↑"
                else:
                    # No net change
                    direction = "→"

                after = clock.current

                clock_final_states[clock_name] = {
                    'before': before,
                    'after': after,
                    'maximum': maximum,
                    'reasons': reasons,
                    'direction': direction,
                    'filled': after >= maximum
                }

                # Log clock advancement
                logger.debug(f"Clock {clock_name}: {before}/{maximum} → {after}/{maximum} {direction} (aggregated: {', '.join(reasons)})")

                # JSONL logging for clock advancement (if any change occurred)
                if self.jsonl_logger and before != after:
                    self.jsonl_logger.log_event(
                        event_type="clock_advancement",
                        data={
                            "clock_name": clock_name,
                            "before_ticks": before,
                            "after_ticks": after,
                            "maximum_ticks": maximum,
                            "delta": after - before,
                            "filled": after >= maximum,
                            "reasons": reasons,
                            "direction": direction,
                            "advance_meaning": clock.advance_meaning,
                            "regress_meaning": clock.regress_meaning,
                            "filled_consequence": clock.filled_consequence
                        },
                        round_num=self.current_round
                    )

                # JSONL logging for clock completion (if filled)
                if self.jsonl_logger and after >= maximum:
                    self.jsonl_logger.log_event(
                        event_type="clock_completion",
                        data={
                            "clock_name": clock_name,
                            "final_ticks": after,
                            "maximum_ticks": maximum,
                            "reasons": reasons,
                            "filled_consequence": clock.filled_consequence,
                            "advance_meaning": clock.advance_meaning,
                            "regress_meaning": clock.regress_meaning,
                            "is_terminal": getattr(clock, 'is_terminal', False),
                            "terminal_outcome": getattr(clock, 'terminal_outcome', None) if getattr(clock, 'is_terminal', False) else None
                        },
                        round_num=self.current_round
                    )

                # Terminal end-triggers (not regression blocks):
                #  - any terminal clock FILLING resolves the scene with its outcome
                #  - a DOOM clock (defeat-on-fill) driven down to 0 = threat
                #    neutralised -> aversion victory
                if after >= maximum:
                    self._record_terminal_completion(clock, "; ".join(reasons))
                elif (getattr(clock, 'is_terminal', False)
                      and getattr(clock, 'terminal_outcome', '') == 'defeat'
                      and before > 0 and after <= 0):
                    self._record_terminal_completion(
                        clock, "; ".join(reasons), outcome_override='victory'
                    )

        # Clear the queue
        self.clock_update_queue = []

        return clock_final_states

    def increment_all_clock_rounds(self):
        """
        Increment rounds_alive for all scene clocks.
        Call this at the start of each round.

        Note: Only increments once per round (tracked via current_round).
        """
        # Only increment once per round
        if self._last_clock_increment_round == self.current_round:
            logger.debug(f"Clock rounds already incremented for round {self.current_round}, skipping")
            return

        self._last_clock_increment_round = self.current_round
        logger.debug(f"Incrementing all clock rounds (game round {self.current_round})")

        for clock_name, clock in self.scene_clocks.items():
            clock.increment_round()
            logger.debug(f"Clock {clock_name}: round {clock._rounds_alive}/{clock.timeout_rounds}")

    def check_and_expire_clocks(self) -> List[Dict[str, Any]]:
        """
        Check for expired clocks (both filled and timed out) and mark them for removal.
        Returns list of expired clock data for DM to narrate.

        Should be called after apply_queued_clock_updates() during synthesis.

        Clocks are removed when:
        1. Filled (reached maximum) - triggers filled_consequence, then removed
        2. Timed out (exceeded timeout_rounds) - expires based on expiration_type

        Returns:
            List of dicts with: {
                'clock_name': str,
                'expiration_type': str,  # crisis_averted, force_resolve, escalate
                'current': int,
                'maximum': int,
                'description': str,
                'filled_consequence': str (if applicable),
                'removal_reason': str  # 'filled' or 'timeout'
            }
        """
        expired_clocks = []
        clocks_to_remove = []

        for clock_name, clock in self.scene_clocks.items():
            # Check if clock is filled (reached/exceeded maximum) - remove immediately
            if clock.filled:
                exp_type = clock.expiration_type  # Will be 'force_resolve' for filled clocks

                expired_clocks.append({
                    'clock_name': clock_name,
                    'expiration_type': exp_type,
                    'current': clock.current,
                    'maximum': clock.maximum,
                    'description': clock.description,
                    'filled_consequence': clock.filled_consequence,
                    'advance_meaning': clock.advance_meaning,
                    'regress_meaning': clock.regress_meaning,
                    'removal_reason': 'filled'
                })

                clocks_to_remove.append(clock_name)

                # Track clock filled event
                self.clock_history.append({
                    'round': self.current_round,
                    'event_type': 'filled',
                    'clock_name': clock_name,
                    'description': clock.description,
                    'final_value': f"{clock.current}/{clock.maximum}",
                    'consequence': clock.filled_consequence
                })

                logger.warning(f"🔔 Clock {clock_name} FILLED: {clock.current}/{clock.maximum} - triggering consequences and removing")

            elif clock.is_expired:
                # Timed out without filling
                exp_type = clock.expiration_type

                expired_clocks.append({
                    'clock_name': clock_name,
                    'expiration_type': exp_type,
                    'current': clock.current,
                    'maximum': clock.maximum,
                    'description': clock.description,
                    'filled_consequence': clock.filled_consequence,
                    'advance_meaning': clock.advance_meaning,
                    'regress_meaning': clock.regress_meaning,
                    'removal_reason': 'timeout'
                })

                clocks_to_remove.append(clock_name)

                # Track clock expired event
                self.clock_history.append({
                    'round': self.current_round,
                    'event_type': 'expired',
                    'clock_name': clock_name,
                    'description': clock.description,
                    'final_value': f"{clock.current}/{clock.maximum}",
                    'expiration_type': exp_type
                })

                logger.warning(f"⏰ Clock {clock_name} TIMEOUT after {clock._rounds_alive} rounds (type: {exp_type})")

        # Remove all marked clocks
        for clock_name in clocks_to_remove:
            # Find the expired clock data for this clock
            expired_data = next(e for e in expired_clocks if e['clock_name'] == clock_name)

            # JSONL logging for clock removal
            if self.jsonl_logger:
                self.jsonl_logger.log_event(
                    event_type="clock_removal",
                    data={
                        "clock_name": clock_name,
                        "current_ticks": expired_data['current'],
                        "maximum_ticks": expired_data['maximum'],
                        "description": expired_data['description'],
                        "removal_reason": expired_data['removal_reason'],
                        "expiration_type": expired_data['expiration_type'],
                        "filled": (expired_data['removal_reason'] == 'filled'),
                        "consequence_triggered": (expired_data['removal_reason'] == 'filled')
                    },
                    round_num=self.current_round
                )

            del self.scene_clocks[clock_name]
            logger.info(f"Removed clock: {clock_name}")

        return expired_clocks

    def calculate_initiative(self, agility: int) -> int:
        """Calculate initiative: Agility × 4 + d20."""
        return (agility * 4) + random.randint(1, 20)

    def add_condition(self, agent_id: str, condition: Condition):
        """Add a condition to a character."""
        if agent_id not in self.conditions:
            self.conditions[agent_id] = []

        # Check for duplicate conditions
        for existing in self.conditions[agent_id]:
            if existing.name == condition.name:
                logger.debug(f"Condition {condition.name} already exists for {agent_id}")
                return

        self.conditions[agent_id].append(condition)
        logger.info(f"Applied condition to {agent_id}: {condition.name} ({condition.penalty})")

    def remove_condition(self, agent_id: str, condition_name: str):
        """Remove a condition from a character."""
        if agent_id in self.conditions:
            self.conditions[agent_id] = [
                c for c in self.conditions[agent_id] if c.name != condition_name
            ]
            logger.info(f"Removed condition from {agent_id}: {condition_name}")

    def get_conditions(self, agent_id: str) -> List[Condition]:
        """Get all conditions affecting an agent."""
        return self.conditions.get(agent_id, [])

    def tick_conditions(self, agent_id: str):
        """Decrement duration on temporary conditions.

        Returns:
            List of expired condition names, or empty list if none expired.
        """
        if agent_id not in self.conditions:
            return []

        expired = []
        for condition in self.conditions[agent_id]:
            if condition.duration > 0:
                condition.duration -= 1
                if condition.duration == 0:
                    logger.info(f"Condition expired: {condition.name} for {agent_id}")
                    expired.append(condition.name)

        # Remove expired conditions (duration == 0)
        self.conditions[agent_id] = [
            c for c in self.conditions[agent_id] if c.duration != 0
        ]
        return expired

    def get_difficulty_recommendation(self, context: str) -> int:
        """Recommend a difficulty based on context description."""
        context_lower = context.lower()

        if any(word in context_lower for word in ['trivial', 'simple', 'easy']):
            return Difficulty.EASY.value
        elif any(word in context_lower for word in ['routine', 'normal', 'standard']):
            return Difficulty.ROUTINE.value
        elif any(word in context_lower for word in ['moderate', 'medium']):
            return Difficulty.MODERATE.value
        elif any(word in context_lower for word in ['challenging', 'hard', 'masked', 'hidden']):
            return Difficulty.CHALLENGING.value
        elif any(word in context_lower for word in ['difficult', 'very hard', 'complex']):
            return Difficulty.DIFFICULT.value
        elif any(word in context_lower for word in ['formidable', 'extreme']):
            return Difficulty.FORMIDABLE.value
        else:
            return Difficulty.MODERATE.value  # Default

    def format_resolution_for_narration(self, resolution: ActionResolution, modifiers: dict = None) -> str:
        """
        Format resolution for DM narration with full transparency.

        Codex Nexum guidance: Always emit Attribute × Skill, d20, total, DC, margin, tier.

        Args:
            resolution: ActionResolution object with roll details
            modifiers: Optional dict of situational modifiers (e.g., {"high_ground": 2, "cover": -3})
        """
        # Defensive attribute access for old vs new ActionResolution schema
        skill = getattr(resolution, 'skill', None)
        skill_value = getattr(resolution, 'skill_value', 0)
        attribute = getattr(resolution, 'attribute', 'Unknown')
        attribute_value = getattr(resolution, 'attribute_value', 0)
        roll = getattr(resolution, 'roll', 0)
        intent = getattr(resolution, 'intent', 'Action')

        # Format skill text based on YAGS Aeonisk v1.3.0 rules
        # Raw attribute checks removed - all actions use skills
        if skill and skill_value > 0:
            # Skilled: Attribute × Skill + d20
            skill_text = f"{attribute} × {skill}"
            ability = attribute_value * skill_value
            formula = f"{attribute_value} × {skill_value} + d20({roll})"
        else:
            # Unskilled: d20 ÷ 2 (no ability bonus)
            skill_name = skill if skill else "unskilled"
            skill_text = f"{skill_name} (unskilled)"
            ability = 0
            halved_roll = roll // 2
            formula = f"d20({roll}) ÷ 2 = {halved_roll}"

        # Transparent roll display (with defensive access for new Pydantic schema)
        total = getattr(resolution, 'total', 0)
        difficulty = getattr(resolution, 'difficulty', 0)
        margin = getattr(resolution, 'margin', 0)
        outcome_tier_value = getattr(resolution.outcome_tier, 'value', 'unknown') if hasattr(resolution, 'outcome_tier') else 'unknown'
        success = getattr(resolution, 'success', False)
        narrative = getattr(resolution, 'narrative', getattr(resolution, 'narration', ''))

        # Format modifiers if present
        modifiers_line = ""
        if modifiers:
            modifier_parts = []
            net_modifier = 0
            for name, value in modifiers.items():
                modifier_parts.append(f"{name}: {value:+d}")
                net_modifier += value
            modifiers_line = f"Modifiers: [{', '.join(modifier_parts)}] → Net: {net_modifier:+d}\n"

        return f"""
**{intent}**
Roll: {skill_text}
Calculation: {formula} = **{total}**
{modifiers_line}DC: {difficulty} | Margin: {margin:+d} | Tier: **{outcome_tier_value.upper()}** {'✓' if success else '✗'}
{narrative}
""".strip()

    def get_state_summary(self) -> Dict[str, Any]:
        """Get summary of all tracked state."""
        return {
            'scene_clocks': {
                name: {
                    'current': clock.current,
                    'maximum': clock.maximum,
                    'filled': clock.filled,
                    'progress': f"{clock.current}/{clock.maximum}"
                }
                for name, clock in self.scene_clocks.items()
            },
            'void_states': {
                agent_id: {
                    'score': state.score,
                    'level': state.corruption_level,
                    'changes': len(state.history)
                }
                for agent_id, state in self.void_states.items()
            },
            'recent_actions': [
                {
                    'intent': action.intent,
                    'outcome': action.outcome_tier.value,
                    'margin': action.margin
                }
                for action in self.action_history[-5:]
            ]
        }

    def attempt_seed_attunement(
        self,
        player_id: str,
        element: str,
        method: str = "altar",
        willpower: int = 3,
        astral_arts: int = 3,
        dex: int = 3,
        tech: int = 0
    ) -> Dict[str, Any]:
        """
        Attempt to attune a Raw Seed to an element.

        Two methods:
        - Ritual Altar: Willpower × Astral Arts vs DC 18 (grants +1 soulcredit on success)
        - Echo-Calibrator: Dex × Tech vs DC 16 (more foolproof, no SC bonus, uses 1 Drip per 3 uses)

        Args:
            player_id: Character ID
            element: Target element (fire, water, air, earth, spirit, void)
            method: "altar" or "echo_calibrator"
            willpower: Willpower attribute
            astral_arts: Astral Arts skill
            dex: Dexterity attribute
            tech: Tech skill

        Returns:
            Dict with success, margin, seed_created, void_gain, soulcredit_gain
        """
        if SeedType is None or Element is None or Seed is None:
            return {
                'success': False,
                'error': 'Energy economy module not available',
                'narrative': 'The ritual components are not available.'
            }

        # Normalize element name
        element_map = {
            'fire': Element.FIRE,
            'water': Element.WATER,
            'air': Element.AIR,
            'earth': Element.EARTH,
            'spirit': Element.SPIRIT,
            'void': Element.VOID
        }

        element_lower = element.lower()
        if element_lower not in element_map:
            return {
                'success': False,
                'error': f'Invalid element: {element}',
                'narrative': f'The element "{element}" is not recognized by the ritual.'
            }

        element_enum = element_map[element_lower]

        # Determine method and calculate roll
        if method == "altar":
            # Ritual altar: Willpower × Astral Arts vs DC 18
            ability = willpower * astral_arts
            dc = 18
            roll = random.randint(1, 20)
            total = ability + roll
            margin = total - dc
            success = total >= dc
            grants_sc = True

            action_text = f"Ritual attunement to {element.capitalize()} via altar"
            formula = f"{willpower} × {astral_arts} + d20({roll}) = {total} vs DC {dc}"

        elif method == "echo_calibrator":
            # Echo-Calibrator: Dex × Tech vs DC 16 (more foolproof)
            ability = dex * tech
            dc = 16
            roll = random.randint(1, 20)
            total = ability + roll
            margin = total - dc
            success = total >= dc
            grants_sc = False  # Tech method doesn't grant spiritual credit

            action_text = f"Echo-Calibrator attunement to {element.capitalize()}"
            formula = f"{dex} × {tech} + d20({roll}) = {total} vs DC {dc}"

        else:
            return {
                'success': False,
                'error': f'Invalid method: {method}',
                'narrative': f'The method "{method}" is not recognized.'
            }

        # Calculate outcome tier
        if margin >= 20:
            tier = OutcomeTier.EXCEPTIONAL
        elif margin >= 15:
            tier = OutcomeTier.EXCELLENT
        elif margin >= 10:
            tier = OutcomeTier.GOOD
        elif margin >= 5:
            tier = OutcomeTier.MODERATE
        elif margin >= 0:
            tier = OutcomeTier.MARGINAL
        elif margin >= -20:
            tier = OutcomeTier.FAILURE
        else:
            tier = OutcomeTier.CRITICAL_FAILURE

        result = {
            'success': success,
            'margin': margin,
            'tier': tier.value,
            'formula': formula,
            'void_gain': 0,
            'soulcredit_gain': 0,
            'seed_created': None,
            'action_text': action_text
        }

        # SUCCESS: Create Attuned Seed
        if success:
            # Create the attuned seed
            attuned_seed = Seed(
                seed_type=SeedType.ATTUNED,
                element=element_enum,
                origin=f"attuned_via_{method}"
            )
            result['seed_created'] = attuned_seed

            # Altar method grants soulcredit
            if grants_sc:
                result['soulcredit_gain'] = 1
                result['narrative'] = f"""
**{action_text}** - {tier.value.upper()} ✓
{formula}
Margin: {margin:+d}

The Raw Seed resonates with {element_lower} essence, stabilizing into an Attuned Seed. The ritual reflects your spiritual discipline. (+1 Soulcredit)
""".strip()
            else:
                result['narrative'] = f"""
**{action_text}** - {tier.value.upper()} ✓
{formula}
Margin: {margin:+d}

The Echo-Calibrator hums as it channels {element_lower} resonance into the Raw Seed, stabilizing it into an Attuned Seed through technical precision.
""".strip()

        # FAILURE: Void risk
        else:
            result['seed_created'] = None  # Raw Seed consumed but no Attuned Seed created

            # Calculate void gain based on margin
            if tier == OutcomeTier.CRITICAL_FAILURE:
                void_gain = 2
                consequence = "The ritual collapses catastrophically, void energy flooding the workspace."
            elif margin < -10:
                void_gain = 1
                consequence = "The ritual destabilizes, leaving residual void corruption."
            else:
                void_gain = 0
                consequence = "The attunement fails to stabilize, but you avoid void corruption."

            result['void_gain'] = void_gain

            if method == "altar":
                result['narrative'] = f"""
**{action_text}** - {tier.value.upper()} ✗
{formula}
Margin: {margin:+d}

{consequence} The Raw Seed is consumed in the failed ritual. {f"(+{void_gain} Void)" if void_gain > 0 else ""}
""".strip()
            else:
                result['narrative'] = f"""
**{action_text}** - {tier.value.upper()} ✗
{formula}
Margin: {margin:+d}

{consequence} The Echo-Calibrator overheats, and the Raw Seed shatters. {f"(+{void_gain} Void)" if void_gain > 0 else ""}
""".strip()

            # Apply void gain if any
            if void_gain > 0:
                void_state = self.get_void_state(player_id)
                void_state.add_void(void_gain, f"Failed seed attunement: {action_text}")

        # Log to JSONL if available
        if self.jsonl_logger:
            self.jsonl_logger.log_event(
                'seed_attunement',
                {
                    'player_id': player_id,
                    'element': element_lower,
                    'method': method,
                    'success': success,
                    'margin': margin,
                    'tier': tier.value,
                    'void_gain': result['void_gain'],
                    'soulcredit_gain': result['soulcredit_gain']
                },
                self.current_round
            )

        return result

    def consume_gear_fuel(
        self,
        player_id: str,
        gear_name: str,
        fuel_type: str = "spark",
        fuel_amount: int = 1,
        energy_purse = None
    ) -> Dict[str, Any]:
        """
        Lightweight optional gear fuel consumption.

        Only used for high-tech/powered gear that explicitly requires fuel.
        Most gear doesn't need fuel tracking.

        Args:
            player_id: Character ID
            gear_name: Name of gear being used
            fuel_type: Type of fuel ("spark", "drip", "breath", "grain")
            fuel_amount: Amount of fuel consumed per use
            energy_purse: EnergyPurse instance (from CharacterState)

        Returns:
            Dict with success (bool), consumed (int), narrative (str)
        """
        if energy_purse is None:
            # No inventory provided, assume fuel is not required
            return {
                'success': True,
                'consumed': 0,
                'narrative': f"{gear_name} operates normally."
            }

        # Attempt to spend fuel
        fuel_available = getattr(energy_purse, fuel_type, 0)

        if fuel_available >= fuel_amount:
            # Consume fuel
            success = energy_purse.spend_currency(fuel_type, fuel_amount)

            if success:
                narrative = f"{gear_name} consumes {fuel_amount} {fuel_type.capitalize()} and activates."
            else:
                # Spend failed (shouldn't happen, but handle gracefully)
                narrative = f"{gear_name} has insufficient {fuel_type.capitalize()}."
                success = False
        else:
            # Not enough fuel
            success = False
            narrative = f"{gear_name} requires {fuel_amount} {fuel_type.capitalize()}, but only {fuel_available} available. Cannot activate."

        result = {
            'success': success,
            'consumed': fuel_amount if success else 0,
            'narrative': narrative,
            'fuel_type': fuel_type,
            'fuel_remaining': getattr(energy_purse, fuel_type, 0)
        }

        # Log to JSONL if available
        if self.jsonl_logger and success:
            self.jsonl_logger.log_event(
                'gear_fuel_consumption',
                {
                    'player_id': player_id,
                    'gear_name': gear_name,
                    'fuel_type': fuel_type,
                    'amount': fuel_amount,
                    'remaining': result['fuel_remaining']
                },
                self.current_round
            )

        return result


# =============================================================================
# DAMAGE CALCULATION HELPERS (YAGS Combat)
# =============================================================================

def get_stun_effect(stuns: int) -> Dict[str, Any]:
    """
    Get stun threshold effects per YAGS combat.md:437-456.

    Args:
        stuns: Current stun level

    Returns:
        Dict with name, penalty, and special flags
    """
    STUN_THRESHOLDS = {
        0: {"name": "OK", "penalty": 0, "unconscious_check": False},
        1: {"name": "Light", "penalty": 0, "unconscious_check": False},
        2: {"name": "Light", "penalty": -5, "unconscious_check": False},
        3: {"name": "Moderate", "penalty": -10, "unconscious_check": False},
        4: {"name": "Moderate", "penalty": -10, "unconscious_check": False},
        5: {"name": "Critical", "penalty": -25, "unconscious_check": False},
    }

    # 6+ is Beaten
    if stuns >= 6:
        return {"name": "Beaten", "penalty": -40, "unconscious_check": True}

    return STUN_THRESHOLDS.get(stuns, STUN_THRESHOLDS[0])


def get_wound_effect(wounds: int) -> Dict[str, Any]:
    """
    Get wound threshold effects per YAGS combat.md:390-422.

    Args:
        wounds: Current wound level

    Returns:
        Dict with name, penalty, and special flags
    """
    WOUND_THRESHOLDS = {
        0: {"name": "OK", "penalty": 0, "death_check": False},
        1: {"name": "Scratched", "penalty": 0, "death_check": False},
        2: {"name": "Light", "penalty": -5, "death_check": False},
        3: {"name": "Moderate", "penalty": -10, "death_check": False},
        4: {"name": "Heavy", "penalty": -15, "death_check": False},
        5: {"name": "Critical", "penalty": -25, "death_check": False},
    }

    # 6+ is Fatal
    if wounds >= 6:
        return {"name": "Fatal", "penalty": -40, "death_check": True}

    return WOUND_THRESHOLDS.get(wounds, WOUND_THRESHOLDS[0])


# Beaten (stuns) / Fatal (wounds) threshold: the body has 5 injury levels; the
# 6th triggers the YAGS "health check to remain conscious". Verified against the
# corpus (death_state=='dead' <=> wounds>=6, exactly) and combat.md:419/469.
KO_CHECK_THRESHOLD = 6

# Aeonisk HOUSE RULE: stuns bleed off per round in combat. YAGS proper recovers
# stuns over days ("after the battle"), but ~10-round scenes need faster recovery
# so a Beaten combatant isn't frozen for the whole fight. Tunable. Wounds do NOT
# recover this way — serious injury needs medical aid.
STUN_RECOVERY_PER_ROUND = 2


def resolve_ko_check(stuns: int, wounds: int, health_attr: int,
                     roll: Optional[int] = None) -> Dict[str, Any]:
    """YAGS 'health check to remain conscious enough to act', made each ROUND a
    Beaten (stuns>=6) or Fatally wounded (wounds>=6) character wishes to act
    (combat.md:419, 469).

    This is a per-round *consciousness* gate, not a death roll: it never kills
    (death at the moment of wounding is owned by Player.check_death_save). Pass ->
    the actor may act this round though still Beaten/Fatal; fail -> unconscious
    this round (they get a fresh check next round, since ResolutionState is rebuilt
    each round).

    DC = 20 + 5 * (worse-track-level - 6). Roll = Health*2 + d20 (the same
    convention as check_death_save); a natural 1 auto-fails.

    Returns {required, can_act, status, dc, roll, total} where status is one of
    'ok' (not required), 'acts' (passed), 'unconscious' (failed).
    """
    level = max(int(stuns or 0), int(wounds or 0))
    if level < KO_CHECK_THRESHOLD:
        return {"required": False, "can_act": True, "status": "ok",
                "dc": 0, "roll": None, "total": None}
    dc = 20 + 5 * (level - KO_CHECK_THRESHOLD)
    if roll is None:
        roll = random.randint(1, 20)
    total = (int(health_attr) * 2) + roll
    if roll == 1 or total < dc:
        return {"required": True, "can_act": False, "status": "unconscious",
                "dc": dc, "roll": roll, "total": total}
    return {"required": True, "can_act": True, "status": "acts",
            "dc": dc, "roll": roll, "total": total}


def recover_stuns(stuns: int, per_round: int = STUN_RECOVERY_PER_ROUND) -> int:
    """End-of-round stun recovery (Aeonisk house rule). Returns the new stun count,
    floored at 0. Non-int / non-positive input yields 0."""
    if not isinstance(stuns, (int, float)) or stuns <= 0:
        return 0
    return max(0, int(stuns) - max(0, int(per_round)))


def apply_stun_damage(target: Any, damage_dealt: int) -> Dict[str, Any]:
    """
    Apply stun damage per YAGS non-cumulative rules (combat.md:430-471).

    Stuns are non-cumulative: If new stuns > current, replace.
    Else if new stuns >= half current, +1 stun.

    Args:
        target: Character object with .stuns attribute
        damage_dealt: Damage after soak

    Returns:
        Dict with stuns_dealt, new_total, and effect info
    """
    old_stuns = getattr(target, 'stuns', 0)

    # Non-cumulative logic
    if damage_dealt > old_stuns:
        new_stuns = damage_dealt
        stuns_dealt = new_stuns - old_stuns
    elif damage_dealt >= (old_stuns // 2):
        new_stuns = old_stuns + 1
        stuns_dealt = 1
    else:
        new_stuns = old_stuns
        stuns_dealt = 0

    target.stuns = new_stuns
    effect = get_stun_effect(new_stuns)

    return {
        "stuns_dealt": stuns_dealt,
        "old_stuns": old_stuns,
        "new_stuns": new_stuns,
        "effect": effect,
        "unconscious_check_needed": effect["unconscious_check"]
    }


def apply_wound_damage(target: Any, damage_dealt: int) -> Dict[str, Any]:
    """
    Apply wound damage per YAGS rules (combat.md:390-422).

    Wounds are cumulative: Every 5 points = 1 wound.

    Args:
        target: Character object with .wounds and .health attributes
        damage_dealt: Damage after soak

    Returns:
        Dict with wounds_dealt, new_total, and effect info
    """
    old_wounds = getattr(target, 'wounds', 0)
    wounds_dealt = damage_dealt // 5  # Every 5 points = 1 wound
    new_wounds = old_wounds + wounds_dealt

    target.wounds = new_wounds
    if hasattr(target, 'health'):
        target.health = max(0, target.health - damage_dealt)

    effect = get_wound_effect(new_wounds)

    return {
        "wounds_dealt": wounds_dealt,
        "old_wounds": old_wounds,
        "new_wounds": new_wounds,
        "hp_lost": damage_dealt,
        "effect": effect,
        "death_check_needed": effect["death_check"]
    }


def apply_mixed_damage(target: Any, damage_dealt: int) -> Dict[str, Any]:
    """
    Apply mixed damage per YAGS rules (combat.md:477-482).

    Split damage: First to stuns (cumulative for mixed), then wounds.
    Odd damage goes to stuns.

    Args:
        target: Character object with .stuns, .wounds, .health attributes
        damage_dealt: Damage after soak

    Returns:
        Dict with both stun and wound info
    """
    # Split damage: odd goes to stuns
    stun_damage = (damage_dealt + 1) // 2
    wound_damage = damage_dealt // 2

    # Mixed damage stuns are CUMULATIVE (different from pure stun)
    old_stuns = getattr(target, 'stuns', 0)
    new_stuns = old_stuns + stun_damage
    target.stuns = new_stuns
    stun_effect = get_stun_effect(new_stuns)

    # Wound portion (every 5 points = 1 wound)
    old_wounds = getattr(target, 'wounds', 0)
    wounds_dealt = wound_damage // 5
    new_wounds = old_wounds + wounds_dealt
    target.wounds = new_wounds
    if hasattr(target, 'health'):
        target.health = max(0, target.health - wound_damage)
    wound_effect = get_wound_effect(new_wounds)

    return {
        "stuns_dealt": stun_damage,
        "old_stuns": old_stuns,
        "new_stuns": new_stuns,
        "stun_effect": stun_effect,
        "wounds_dealt": wounds_dealt,
        "old_wounds": old_wounds,
        "new_wounds": new_wounds,
        "hp_lost": wound_damage,
        "wound_effect": wound_effect,
        "unconscious_check_needed": stun_effect["unconscious_check"],
        "death_check_needed": wound_effect["death_check"]
    }


def apply_healing(
    target: Any,
    amount: int,
    heal_type: str  # "stun", "wound", or "hp"
) -> Dict[str, Any]:
    """
    Heal target agent.

    Healing system for NPCs, players, and enemies. Supports three types:
    - "stun": Remove stun damage (fast recovery, field medicine)
    - "wound": Reduce wound penalties (surgery-equivalent, requires tools)
    - "hp": Restore health (medical treatment, bandaging)

    Args:
        target: Agent with health/stuns/wounds attributes
        amount: Amount to heal
        heal_type: Type of healing ("stun", "wound", "hp")

    Returns:
        Dict with healing results (amount_healed, stuns_removed, or wounds_treated)

    Example:
        >>> result = apply_healing(npc, amount=10, heal_type="hp")
        >>> print(result["amount_healed"])  # 10 (or less if at max_health)
    """
    if heal_type == "stun":
        # Remove stun damage
        stuns_before = getattr(target, 'stuns', 0)
        new_stuns = max(0, stuns_before - amount)
        target.stuns = new_stuns
        return {
            "stuns_removed": stuns_before - new_stuns,
            "old_stuns": stuns_before,
            "new_stuns": new_stuns
        }

    elif heal_type == "wound":
        # Reduce wound penalties (surgery-equivalent)
        wounds_before = getattr(target, 'wounds', 0)
        new_wounds = max(0, wounds_before - amount)
        target.wounds = new_wounds
        return {
            "wounds_treated": wounds_before - new_wounds,
            "old_wounds": wounds_before,
            "new_wounds": new_wounds
        }

    elif heal_type == "hp":
        # Restore health (capped at max_health)
        hp_before = getattr(target, 'health', 0)
        max_health = getattr(target, 'max_health', hp_before)
        new_health = min(max_health, hp_before + amount)
        target.health = new_health
        return {
            "amount_healed": new_health - hp_before,
            "old_health": hp_before,
            "new_health": new_health,
            "max_health": max_health
        }

    else:
        raise ValueError(f"Invalid heal_type: {heal_type}. Must be 'stun', 'wound', or 'hp'.")


# ==============================================================================
# Module-level wrappers for testing
# ==============================================================================

def validate_consumption(character_state, item_id, food_item) -> ConsumptionValidation:
    """
    Module-level wrapper for validate_consumption (for testing).

    Creates a temporary MechanicsEngine instance and calls the validation method.
    """
    from .shared_state import SharedState
    shared_state = SharedState()
    mechanics = MechanicsEngine(shared_state=shared_state)
    return mechanics.validate_consumption(character_state, item_id, food_item)


def process_consumption_effect(consumption_effect, character_state) -> bool:
    """
    Module-level wrapper for process_consumption_effect (for testing).

    Creates a temporary MechanicsEngine instance and calls the execution method.
    """
    from .shared_state import SharedState
    shared_state = SharedState()
    mechanics = MechanicsEngine(shared_state=shared_state)
    return mechanics.process_consumption_effect(consumption_effect, character_state)


def validate_item_discovery(character_state, item_effect, player_id) -> DiscoveryValidation:
    """
    Module-level wrapper for validate_item_discovery (for testing).

    Creates a temporary MechanicsEngine instance and calls the validation method.
    """
    from .shared_state import SharedState
    shared_state = SharedState()
    mechanics = MechanicsEngine(shared_state=shared_state)
    return mechanics.validate_item_discovery(character_state, item_effect, player_id)


def process_item_effect(item_effect, character_state, player_id) -> bool:
    """
    Module-level wrapper for process_item_effect (for testing).

    Creates a temporary MechanicsEngine instance and calls the execution method.
    """
    from .shared_state import SharedState
    shared_state = SharedState()
    mechanics = MechanicsEngine(shared_state=shared_state)
    return mechanics.process_item_effect(item_effect, character_state, player_id)


# ==============================================================================
# DEFENSE TOKEN MODIFIER (Spec 04 — Universal defence token mechanic)
# ==============================================================================

def apply_defense_token_modifier(
    attacker_agent_id: str,
    target,
    target_id_mapper=None
) -> Tuple[int, str]:
    """
    Calculate defense token attack modifier.

    The target's defence_token determines the modifier:
    - If target is watching the attacker: attacker gets -2
    - If target is watching someone else or no one: attacker gets +2 (flanking)

    Args:
        attacker_agent_id: The agent_id of the attacker
        target: The target entity (must have .defence_token attribute or lack thereof)
        target_id_mapper: Optional mapper for resolving tgt_xxxx to agent_id

    Returns:
        (modifier, description) -- e.g., (-2, "target watching -2") or (+2, "flanking +2")
    """
    target_defense = getattr(target, 'defence_token', None)

    if target_defense is None:
        return (2, "flanking +2, target not watching anyone")

    # Direct match on agent_id
    if target_defense == attacker_agent_id:
        return (-2, "target watching -2")

    # Check if target's defence_token is the attacker's tgt_xxxx alias
    if target_id_mapper:
        attacker_tgt_id = target_id_mapper.get_target_id(attacker_agent_id)
        if attacker_tgt_id and target_defense == attacker_tgt_id:
            return (-2, "target watching -2")

    return (2, "flanking +2")


# =============================================================================
# STEALTH MECHANICS (Spec 05)
# =============================================================================

def _get_attribute(agent, attr_name: str, default: int = 3) -> int:
    """Get attribute value from any agent type.

    Supports:
    - EnemyAgent / NPCAgent: agent.attributes dict
    - AIPlayerAgent: agent.character_state.attributes dict

    Args:
        agent: Any agent type
        attr_name: Attribute name (e.g., 'Agility', 'Perception')
        default: Default value if not found

    Returns:
        Attribute value as int
    """
    # EnemyAgent / NPCAgent: agent.attributes dict
    if hasattr(agent, 'attributes') and isinstance(agent.attributes, dict):
        return agent.attributes.get(attr_name, default)
    # AIPlayerAgent: agent.character_state.attributes dict
    if hasattr(agent, 'character_state'):
        cs = agent.character_state
        if hasattr(cs, 'attributes') and isinstance(cs.attributes, dict):
            return cs.attributes.get(attr_name, default)
    return default


def _get_skill(agent, skill_name: str, default: int = 0) -> int:
    """Get skill value from any agent type.

    Supports:
    - EnemyAgent / NPCAgent: agent.skills dict
    - AIPlayerAgent: agent.character_state.skills dict

    Args:
        agent: Any agent type
        skill_name: Skill name (e.g., 'Stealth', 'Awareness')
        default: Default value if not found

    Returns:
        Skill value as int
    """
    if hasattr(agent, 'skills') and isinstance(agent.skills, dict):
        return agent.skills.get(skill_name, default)
    if hasattr(agent, 'character_state'):
        cs = agent.character_state
        if hasattr(cs, 'skills') and isinstance(cs.skills, dict):
            return cs.skills.get(skill_name, default)
    return default


def resolve_stealth_check(
    agent,
    environment_dc: int = 15,
    modifiers: int = 0
) -> Dict[str, Any]:
    """
    Resolve a stealth check using YAGS formula.

    Formula: Agility x Stealth + d20 + modifiers vs environment_dc

    Void interaction:
    - void_score == 10: automatic failure (stealth impossible)

    Args:
        agent: The agent attempting to hide (must have attributes and skills)
        environment_dc: Base difficulty (10=dark alley, 15=normal, 20=open ground,
                        25=well-lit, 30=actively searched area)
        modifiers: Situational modifiers (+/- for cover, noise, distractions)

    Returns:
        Dict with:
            success: bool
            stealth_roll: int (total roll value, becomes detection DC if successful)
            d20: int (raw die roll)
            margin: int (roll - dc, negative = failure)
            formula: str (human-readable breakdown)
            agility: int
            stealth_skill: int
    """
    # Void 10: stealth impossible
    void_score = getattr(agent, 'void_score', 0)
    if void_score == 10:
        return {
            'success': False,
            'stealth_roll': 0,
            'd20': 0,
            'margin': -environment_dc,
            'formula': f"VOID 10 - stealth impossible (void corruption visible)",
            'agility': _get_attribute(agent, 'Agility', default=3),
            'stealth_skill': _get_skill(agent, 'Stealth', default=0),
        }

    # Get stats
    agility = _get_attribute(agent, 'Agility', default=3)
    stealth_skill = _get_skill(agent, 'Stealth', default=0)

    # YAGS unskilled penalty
    unskilled_penalty = -5 if stealth_skill == 0 else 0

    d20 = random.randint(1, 20)
    roll_total = (agility * stealth_skill) + d20 + modifiers + unskilled_penalty

    # Minimum roll of 1 (can't go negative)
    roll_total = max(1, roll_total)

    success = roll_total >= environment_dc
    margin = roll_total - environment_dc

    formula = (
        f"Agility {agility} x Stealth {stealth_skill} + d20({d20})"
        f"{f' + modifiers({modifiers})' if modifiers else ''}"
        f"{f' + unskilled({unskilled_penalty})' if unskilled_penalty else ''}"
        f" = {roll_total} vs DC {environment_dc}"
    )

    return {
        'success': success,
        'stealth_roll': roll_total,
        'd20': d20,
        'margin': margin,
        'formula': formula,
        'agility': agility,
        'stealth_skill': stealth_skill,
    }


def resolve_detection_check(
    observer,
    stealth_dc: int,
    modifiers: int = 0
) -> Dict[str, Any]:
    """
    Resolve a detection check against a hidden target.

    Formula: Perception x Awareness + d20 + modifiers vs stealth_dc

    The stealth_dc is the total from the hider's stealth check (their roll becomes
    the DC for detection).

    Void interaction (caller responsibility):
    - Target void_score >= 7: caller should pass modifiers=+5

    Args:
        observer: The agent attempting to detect (must have attributes and skills)
        stealth_dc: DC to beat (from the hider's stealth check result)
        modifiers: Situational modifiers (+5 void aura, +/- for noise, equipment)

    Returns:
        Dict with:
            success: bool (True = detected the hidden agent)
            detection_roll: int
            d20: int
            margin: int
            formula: str
            perception: int
            awareness_skill: int
    """
    perception = _get_attribute(observer, 'Perception', default=3)
    awareness_skill = _get_skill(observer, 'Awareness', default=0)

    unskilled_penalty = -5 if awareness_skill == 0 else 0

    d20 = random.randint(1, 20)
    roll_total = (perception * awareness_skill) + d20 + modifiers + unskilled_penalty
    roll_total = max(1, roll_total)

    success = roll_total >= stealth_dc
    margin = roll_total - stealth_dc

    formula = (
        f"Perception {perception} x Awareness {awareness_skill} + d20({d20})"
        f"{f' + modifiers({modifiers})' if modifiers else ''}"
        f"{f' + unskilled({unskilled_penalty})' if unskilled_penalty else ''}"
        f" = {roll_total} vs DC {stealth_dc}"
    )

    return {
        'success': success,
        'detection_roll': roll_total,
        'd20': d20,
        'margin': margin,
        'formula': formula,
        'perception': perception,
        'awareness_skill': awareness_skill,
    }


def break_stealth_on_attack(agent) -> bool:
    """
    Break stealth when an agent attacks from hidden.

    Automatically sets is_hidden=False and clears stealth_dc.
    Called after combat action resolution for hidden agents.

    Args:
        agent: The agent whose stealth should be broken

    Returns:
        True if stealth was broken (agent was hidden), False otherwise
    """
    if getattr(agent, 'is_hidden', False):
        agent.is_hidden = False
        agent.stealth_dc = None
        logger.info(f"Stealth broken: {getattr(agent, 'agent_id', 'unknown')} attacked from hidden")
        return True
    return False


def get_first_strike_bonus(agent) -> int:
    """
    Get First Strike damage bonus for attacking from hidden.

    Returns +2 damage modifier if agent is currently hidden (attacking from stealth).
    Returns 0 if agent is not hidden.

    Args:
        agent: The attacking agent

    Returns:
        Damage bonus (2 if hidden, 0 if not)
    """
    if getattr(agent, 'is_hidden', False):
        return 2
    return 0


def partition_story_advancement_clocks(
    scene_clocks: Dict[str, 'SceneClock'],
    keep_clocks: List[str],
    persist_fraction: float = 0.75,
) -> Tuple[List[str], List[str]]:
    """Decide which clocks a story advancement may clear.

    Clock conservation: a pivot is not an amnesty. Terminal clocks and
    high-progress clocks (current/maximum >= persist_fraction) follow
    the party through the transition automatically; only low-progress,
    non-terminal clocks not named in the DM's keep_clocks may be
    removed.

    Returns (to_remove, auto_kept) - names in keep_clocks appear in
    neither list (they are DM-kept, handled by the caller as before).
    """
    keep_set = set(keep_clocks or [])
    to_remove: List[str] = []
    auto_kept: List[str] = []
    for name, clock in scene_clocks.items():
        if name in keep_set:
            continue
        maximum = getattr(clock, 'maximum', 0) or 0
        progress = (clock.current / maximum) if maximum else 0.0
        if getattr(clock, 'is_terminal', False) or progress >= persist_fraction:
            auto_kept.append(name)
        else:
            to_remove.append(name)
    return to_remove, auto_kept
