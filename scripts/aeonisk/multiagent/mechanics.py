"""
YAGS mechanical resolution system for Aeonisk multi-agent gameplay.
Implements core dice mechanics, rituals, void progression, and scene clocks.
"""

import random
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Import energy economy types for seed attunement
try:
    from .energy_economy import SeedType, Element, Seed
except ImportError:
    logger.warning("energy_economy module not found, seed attunement will not be available")
    SeedType = None
    Element = None
    Seed = None


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

    def __init__(self, session_id: str, output_dir: str = "./output", config: Dict[str, Any] = None):
        self.session_id = session_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.log_file = self.output_dir / f"session_{session_id}.jsonl"

        # Initialize log file with session start event
        self._write_event({
            "event_type": "session_start",
            "ts": datetime.now().isoformat(),
            "session": session_id,
            "config": config or {},
            "version": "1.0.0"
        })

    def _write_event(self, event: Dict[str, Any]):
        """Write a single event as a JSON line."""
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(event, default=str) + '\n')

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
        context: Dict[str, Any] = None
    ):
        """
        Log a complete action resolution event.

        Schema matches Codex Nexum specification:
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
          "economy": {"void_delta": +1, "soulcredit_delta": 0,
                      "offering_used": false, "bonds_applied": []},
          "clocks": {"core_access": "7/8", "infection": "2/6"},
          "effects": ["Barrier fails; backlash ripples"]
        }
        """
        # Calculate ability score
        if resolution.skill and resolution.skill_value > 0:
            ability = resolution.attribute_value * resolution.skill_value
        else:
            ability = resolution.attribute_value - 5  # Unskilled penalty

        event = {
            "event_type": "action_resolution",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "phase": phase,
            "agent": agent_name,
            "action": action,
            "context": context or {},
            "roll": {
                "attr": resolution.attribute,
                "attr_val": resolution.attribute_value,
                "skill": resolution.skill,
                "skill_val": resolution.skill_value,
                "ability": ability,
                "d20": resolution.roll,
                "total": resolution.total,
                "dc": resolution.difficulty,
                "margin": resolution.margin,
                "tier": resolution.outcome_tier.value,
                "success": resolution.success
            },
            "economy": economy_changes,
            "clocks": clock_states,
            "effects": effects
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

    def log_session_end(self, final_state: Dict[str, Any]):
        """Log session end event with final state."""
        event = {
            "event_type": "session_end",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "final_state": final_state
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

    def log_clock_spawn(self, clock_name: str, max_ticks: int, description: str):
        """Log spawning of a new scene clock."""
        event = {
            "event_type": "clock_spawn",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "clock_name": clock_name,
            "max_ticks": max_ticks,
            "description": description
        }
        self._write_event(event)

    def log_synthesis(self, round_num: int, synthesis: str):
        """Log round synthesis narrative."""
        event = {
            "event_type": "round_synthesis",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "synthesis": synthesis
        }
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
        is_defeated: bool = False
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
            "is_defeated": is_defeated
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
        tactics: str
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
        """
        event = {
            "event_type": "enemy_spawn",
            "ts": datetime.now().isoformat(),
            "session": self.session_id,
            "round": round_num,
            "enemy_id": enemy_id,
            "enemy_name": enemy_name,
            "template": template,
            "stats": stats,
            "position": position,
            "tactics": tactics
        }
        self._write_event(event)

    def log_enemy_defeat(
        self,
        round_num: int,
        enemy_id: str,
        enemy_name: str,
        defeat_reason: str,
        rounds_survived: int
    ):
        """
        Log enemy defeat/removal.

        Args:
            round_num: Current round
            enemy_id: Enemy agent ID
            enemy_name: Display name
            defeat_reason: Reason for defeat (killed, retreated, despawned, escaped)
            rounds_survived: Number of rounds enemy was active
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
                - clocks_advanced: Number of clock advancement events
                - clocks_filled: Number of clocks that filled
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
            "clocks_filled": summary.get('clocks_filled', 0),
            "active_enemies": summary.get('active_enemies', 0),
            "player_wounds_total": summary.get('player_wounds_total', 0)
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
    total: int  # attribute × skill + d20
    difficulty: int
    margin: int  # total - difficulty
    outcome_tier: OutcomeTier
    success: bool
    narrative: str
    state_effects: Dict[str, Any] = field(default_factory=dict)


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
    advance_means: str = ""  # What it means to advance (e.g., "Investigation progresses", "Danger increases")
    regress_means: str = ""  # What it means to regress (e.g., "Setback in investigation", "Danger reduced")
    filled_consequence: str = ""  # What happens when filled (e.g., "Evidence complete, pivot to confrontation")
    timeout_rounds: int = 5  # Rounds until clock expires (default 5)
    allow_negative: bool = False  # If True, clock can go negative (for bidirectional trackers)
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
        Add void corruption with multi-level caps, return new score.

        Caps (Codex Nexum canonical):
        - Max +1 void per action
        - Max +2 void per round per character
        - Max +3 void per scene (automatic) - unless player opts into high-risk rituals

        Args:
            amount: Void to add (will be capped)
            reason: Why void is being added
            action_id: Unique action identifier to prevent duplicates
            is_high_risk_ritual: Whether this is an opt-in high-risk ritual (bypasses scene cap)

        Returns:
            New void score
        """
        # Prevent duplicate void for the same action
        if action_id and action_id in self._processed_actions:
            logger.debug(f"Skipping duplicate void add for action {action_id}")
            return self.score

        # Cap per action: max +1
        capped_amount = min(amount, 1)

        # Cap per round: max +2 total
        if self._round_void_gain >= 2 and not is_high_risk_ritual:
            logger.info(f"Round void cap reached (already +{self._round_void_gain}/2)")
            return self.score

        # Cap per scene: max +3 automatic (unless opted into high-risk)
        if self._scene_void_gain >= 3 and not is_high_risk_ritual:
            logger.warning(f"Scene void cap reached (already +{self._scene_void_gain}/3 automatic). Use high-risk ritual to opt-in for more.")
            return self.score

        # Apply remaining room in caps
        remaining_round = 2 - self._round_void_gain
        remaining_scene = 3 - self._scene_void_gain if not is_high_risk_ritual else 10
        actual_add = min(capped_amount, remaining_round, remaining_scene)

        if actual_add <= 0:
            return self.score

        self._round_void_gain += actual_add
        self._scene_void_gain += actual_add

        if is_high_risk_ritual:
            self._scene_opted_in_high_risk = True

        old_score = self.score
        self.score = min(self.score + actual_add, 10)

        self.history.append({
            'change': actual_add,
            'reason': reason,
            'old_score': old_score,
            'new_score': self.score,
            'high_risk': is_high_risk_ritual
        })

        if action_id:
            self._processed_actions.add(action_id)

        logger.info(f"Void added: +{actual_add} (requested {amount}, round {self._round_void_gain}/2, scene {self._scene_void_gain}/{3 if not is_high_risk_ritual else '∞'})")
        return self.score

    def reset_round_void(self):
        """Reset round void counter. Call at start of each round."""
        self._round_void_gain = 0
        logger.debug(f"Reset round void counter")

    def reset_scene_void(self):
        """Reset scene void counter. Call at start of new scene."""
        self._scene_void_gain = 0
        self._scene_opted_in_high_risk = False
        logger.info(f"Reset scene void counter")

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

    def adjust(self, amount: int, reason: str) -> int:
        """
        Adjust soulcredit and clamp to [-10, +10] range.

        Args:
            amount: Soulcredit delta (can be positive or negative)
            reason: Why soulcredit is changing

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
                'new_score': self.score
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


class MechanicsEngine:
    """
    Core mechanics engine for YAGS resolution in Aeonisk.
    Handles dice rolls, rituals, void progression, scene clocks, and conditions.
    """

    # Standard YAGS attributes
    ATTRIBUTES = [
        "Strength", "Agility", "Endurance", "Perception",
        "Intelligence", "Empathy", "Willpower", "Charisma"
    ]

    def __init__(self, jsonl_logger: Optional[JSONLLogger] = None):
        self.scene_clocks: Dict[str, SceneClock] = {}
        self.void_states: Dict[str, VoidState] = {}  # agent_id -> VoidState
        self.soulcredit_states: Dict[str, SoulcreditState] = {}  # agent_id -> SoulcreditState
        self.action_history: List[ActionResolution] = []
        self.conditions: Dict[str, List[Condition]] = {}  # agent_id -> conditions
        self.scene_void_level: int = 0  # 0-10 scene void pressure
        self.jsonl_logger: Optional[JSONLLogger] = jsonl_logger  # Machine-readable event log
        self.current_round: int = 0  # Track current round for logging
        self._last_clock_increment_round: int = -1  # Track last round we incremented clocks

        # Clock update queue - prevents cascade fills during resolution
        # Queued updates are applied batch during synthesis phase
        self.clock_update_queue: List[Tuple[str, int, str]] = []  # (clock_name, ticks, reason)

    def calculate_dc(
        self,
        intent: str,
        action_type: str = "general",
        is_ritual: bool = False,
        is_extreme: bool = False,
        is_multi_stage: bool = False,
        is_inter_party: bool = False
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

        Returns:
            Calculated DC (10-40 range)
        """
        intent_lower = intent.lower()

        # Inter-party communication is usually easy unless environmental factors
        if is_inter_party and action_type == "social":
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
        # Apply condition penalties
        if modifiers is None:
            modifiers = {}

        if agent_id and agent_id in self.conditions:
            for condition in self.conditions[agent_id]:
                if condition.applies_to(attribute, skill):
                    modifiers[condition.name] = condition.penalty
                    logger.debug(f"Applied condition {condition.name}: {condition.penalty}")

        # Roll d20
        roll = random.randint(1, 20)

        # Calculate base total
        if skill_value > 0:
            # Skilled: Attribute × Skill + d20
            ability = attribute_value * skill_value
            base_total = ability + roll

            # Math verification: ensure calculation is correct
            assert base_total == ability + roll, \
                f"Math error (skilled): {attribute_value}×{skill_value}+{roll} should be {ability}+{roll}={ability+roll}, got {base_total}"
        else:
            # Unskilled: Attribute + d20 - 5 (unskilled penalty)
            ability = attribute_value - 5
            base_total = attribute_value + roll - 5

            # Math verification: ensure calculation is correct
            assert base_total == ability + roll, \
                f"Math error (unskilled): {attribute_value}+{roll}-5 should be {ability}+{roll}={ability+roll}, got {base_total}"

        # Apply modifiers
        total = base_total
        modifier_sum = 0
        if modifiers:
            for mod_name, mod_value in modifiers.items():
                total += mod_value
                modifier_sum += mod_value
                logger.debug(f"Applied modifier {mod_name}: {mod_value:+d}")

        # Math verification: ensure modifiers applied correctly
        expected_total = base_total + modifier_sum
        assert total == expected_total, \
            f"Math error (modifiers): {base_total} + modifiers({modifier_sum}) should be {expected_total}, got {total}"

        # Calculate margin and outcome
        margin = total - difficulty
        success = margin >= 0
        outcome_tier = self._determine_outcome_tier(margin)

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
            narrative=self._generate_narrative(intent, outcome_tier, margin)
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
        if ritual_effects.get('tier_downgrade') and resolution.success:
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
            if resolution.success:
                delta += 1
                reasons.append("Fulfilled ritual contract/oath (+1 SC)")

        # Aid Another's Ritual with Offering (+1)
        if any(keyword in action_text for keyword in ['aid ritual', 'help ritual', 'assist ritual',
                                                        'support ritual', 'join ritual']):
            if has_offering and resolution.success:
                delta += 1
                reasons.append("Aided another's ritual with offering (+1 SC)")

        # Void Cleansing Ritual (+2-3) - intentional SC improvement action
        if any(keyword in action_text for keyword in ['cleanse void', 'purify void', 'remove void',
                                                        'void cleansing', 'spiritual cleansing']):
            if resolution.success:
                # +3 for Strong Resonance+ (margin 10+), +2 otherwise
                cleanse_bonus = 3 if resolution.margin >= 10 else 2
                delta += cleanse_bonus
                reasons.append(f"Void cleansing ritual (+{cleanse_bonus} SC)")

        # Public Ritual aligned with Bond/Will (+2) - witnessed, significant, Solid+ margin
        if any(keyword in action_text for keyword in ['public ritual', 'witnessed ritual', 'ceremonial ritual']):
            if resolution.success and resolution.margin >= 5:  # Solid margin
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
                    if resolution.success and 'at cost' in action_text or 'sacrifice' in action_text:
                        delta += 1
                        reasons.append(f"Upheld {faction} tenets at personal cost (+1 SC)")

        # Ritual Success with Strong Resonance+ (+1) - margin 10+
        # NOTE: This is a minor bonus compared to the social actions above
        if is_ritual and resolution.success and resolution.margin >= 10:
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
        if is_ritual and not resolution.success:
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
        advance_means: str = "",
        regress_means: str = "",
        filled_consequence: str = "",
        timeout_rounds: int = None
    ) -> SceneClock:
        """
        Create and register a scene clock with semantic metadata.

        Args:
            name: Clock name (e.g., "Evidence Collection")
            maximum: Max ticks before filling
            description: What the clock tracks
            advance_means: What it means to advance (e.g., "More evidence discovered")
            regress_means: What it means to regress (e.g., "Evidence destroyed")
            filled_consequence: What happens when filled (e.g., "Case ready for prosecution")
            timeout_rounds: Rounds until clock expires (None = auto-calculated based on maximum)
        """
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
            logger.info(f"Clock {name} auto-assigned timeout: {timeout_rounds} rounds (based on max={maximum})")

        clock = SceneClock(
            name=name,
            maximum=maximum,
            description=description,
            advance_means=advance_means,
            regress_means=regress_means,
            filled_consequence=filled_consequence,
            timeout_rounds=timeout_rounds
        )
        self.scene_clocks[name] = clock
        return clock

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

        self._filled_clocks_this_round.append({
            'clock_name': clock_name,
            'reason': reason
        })

    def get_and_clear_filled_clocks(self):
        """Get clocks that filled this round and clear the list."""
        filled = getattr(self, '_filled_clocks_this_round', [])
        self._filled_clocks_this_round = []
        return filled

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
                logger.info(f"Clock {clock_name}: {before}/{maximum} → {after}/{maximum} {direction} (aggregated: {', '.join(reasons)})")

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
        logger.info(f"Incrementing all clock rounds (game round {self.current_round})")

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
                    'advance_means': clock.advance_means,
                    'regress_means': clock.regress_means,
                    'removal_reason': 'filled'
                })

                clocks_to_remove.append(clock_name)

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
                    'advance_means': clock.advance_means,
                    'regress_means': clock.regress_means,
                    'removal_reason': 'timeout'
                })

                clocks_to_remove.append(clock_name)

                logger.warning(f"⏰ Clock {clock_name} TIMEOUT after {clock._rounds_alive} rounds (type: {exp_type})")

        # Remove all marked clocks
        for clock_name in clocks_to_remove:
            del self.scene_clocks[clock_name]
            logger.info(f"Removed clock: {clock_name}")

        return expired_clocks

    def update_clocks_from_action(self, resolution: ActionResolution, context: Dict[str, Any]):
        """Update scene clocks based on action resolution."""
        intent_lower = resolution.intent.lower()

        # Sanctuary/Void Corruption - advances on failures, especially with void/ritual
        if "Sanctuary Corruption" in self.scene_clocks:
            if resolution.outcome_tier in [OutcomeTier.FAILURE, OutcomeTier.CRITICAL_FAILURE]:
                # Any failed ritual or void manipulation risks corruption
                if any(kw in intent_lower for kw in ['ritual', 'void', 'channel', 'attune', 'harmoniz', 'astral']):
                    ticks = 2 if resolution.outcome_tier == OutcomeTier.CRITICAL_FAILURE else 1
                    self.advance_clock("Sanctuary Corruption", ticks, f"Failed: {resolution.intent}")

        # Saboteur Exposure - advances on successful investigation/detection
        if "Saboteur Exposure" in self.scene_clocks:
            if resolution.success:
                # Broad investigation keywords
                investigation_keywords = [
                    'investigate', 'analyze', 'trace', 'scan', 'search', 'examine',
                    'detect', 'identify', 'track', 'follow', 'sense', 'perceive',
                    'study', 'inspect', 'observe', 'scrutinize', 'signature',
                    'pattern', 'resonance', 'echo', 'void resonance', 'sabotage'
                ]
                if any(kw in intent_lower for kw in investigation_keywords):
                    # Better success = more progress
                    ticks = 2 if resolution.margin >= 10 else 1
                    self.advance_clock("Saboteur Exposure", ticks, f"Investigation: {resolution.intent}")

        # Communal Stability - degrades on failures, improves on healing/stabilization successes
        if "Communal Stability" in self.scene_clocks:
            # Success at healing/stabilizing improves stability
            healing_keywords = ['stabiliz', 'heal', 'mend', 'repair', 'bond', 'harmoniz', 'protective', 'barrier']
            if resolution.success and any(kw in intent_lower for kw in healing_keywords):
                # Stability clock tracks degradation, so successful healing REGRESSES it (improves stability)
                self.scene_clocks["Communal Stability"].regress(1)
            # Failures at healing or any critical failure degrades stability
            elif resolution.outcome_tier in [OutcomeTier.FAILURE, OutcomeTier.CRITICAL_FAILURE]:
                if any(kw in intent_lower for kw in healing_keywords + ['social', 'group', 'commune', 'meditat']):
                    ticks = 2 if resolution.outcome_tier == OutcomeTier.CRITICAL_FAILURE else 1
                    self.advance_clock("Communal Stability", ticks, f"Social/healing failure: {resolution.intent}")

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
        """Decrement duration on temporary conditions."""
        if agent_id not in self.conditions:
            return

        for condition in self.conditions[agent_id]:
            if condition.duration > 0:
                condition.duration -= 1
                if condition.duration == 0:
                    logger.info(f"Condition expired: {condition.name} for {agent_id}")

        # Remove expired conditions
        self.conditions[agent_id] = [
            c for c in self.conditions[agent_id] if c.duration != 0
        ]

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

    def format_resolution_for_narration(self, resolution: ActionResolution) -> str:
        """
        Format resolution for DM narration with full transparency.

        Codex Nexum guidance: Always emit Attribute × Skill, d20, total, DC, margin, tier.
        """
        # Format skill text - never show "×None"
        if resolution.skill and resolution.skill_value > 0:
            skill_text = f"{resolution.attribute} × {resolution.skill}"
            ability = resolution.attribute_value * resolution.skill_value
            formula = f"{resolution.attribute_value} × {resolution.skill_value} + d20({resolution.roll})"
        else:
            skill_text = f"{resolution.attribute} (unskilled)"
            ability = resolution.attribute_value - 5
            formula = f"{resolution.attribute_value} + d20({resolution.roll}) - 5"

        # Transparent roll display
        return f"""
**{resolution.intent}**
Roll: {skill_text}
Calculation: {formula} = **{resolution.total}**
DC: {resolution.difficulty} | Margin: {resolution.margin:+d} | Tier: **{resolution.outcome_tier.value.upper()}** {'✓' if resolution.success else '✗'}
{resolution.narrative}
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
            self.jsonl_logger.log_event({
                'event_type': 'seed_attunement',
                'player_id': player_id,
                'element': element_lower,
                'method': method,
                'success': success,
                'margin': margin,
                'tier': tier.value,
                'void_gain': result['void_gain'],
                'soulcredit_gain': result['soulcredit_gain']
            })

        return result

    def consume_gear_fuel(
        self,
        player_id: str,
        gear_name: str,
        fuel_type: str = "spark",
        fuel_amount: int = 1,
        energy_inventory = None
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
            energy_inventory: EnergyInventory instance (from CharacterState)

        Returns:
            Dict with success (bool), consumed (int), narrative (str)
        """
        if energy_inventory is None:
            # No inventory provided, assume fuel is not required
            return {
                'success': True,
                'consumed': 0,
                'narrative': f"{gear_name} operates normally."
            }

        # Attempt to spend fuel
        fuel_available = getattr(energy_inventory, fuel_type, 0)

        if fuel_available >= fuel_amount:
            # Consume fuel
            success = energy_inventory.spend_currency(fuel_type, fuel_amount)

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
            'fuel_remaining': getattr(energy_inventory, fuel_type, 0)
        }

        # Log to JSONL if available
        if self.jsonl_logger and success:
            self.jsonl_logger.log_event({
                'event_type': 'gear_fuel_consumption',
                'player_id': player_id,
                'gear_name': gear_name,
                'fuel_type': fuel_type,
                'amount': fuel_amount,
                'remaining': result['fuel_remaining']
            })

        return result
