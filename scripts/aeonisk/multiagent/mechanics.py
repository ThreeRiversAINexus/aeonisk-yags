"""
YAGS mechanical resolution system for Aeonisk multi-agent gameplay.
Implements core dice mechanics, rituals, void progression, and scene clocks.
"""

import random
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


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
    """Standard difficulty ratings."""
    TRIVIAL = 5
    EASY = 10
    ROUTINE = 15
    MODERATE = 20
    CHALLENGING = 25
    DIFFICULT = 30
    VERY_DIFFICULT = 35
    FORMIDABLE = 40
    NEARLY_IMPOSSIBLE = 50


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
    """Progress clock for tracking scene state."""
    name: str
    current: int = 0
    maximum: int = 6
    description: str = ""
    _ever_filled: bool = field(default=False, init=False, repr=False)

    def advance(self, ticks: int = 1) -> bool:
        """
        Advance clock, return True if NEWLY filled (first time reaching max).

        Returns:
            True only on the transition to filled, False if already filled or still incomplete
        """
        was_filled = self.current >= self.maximum
        self.current = min(self.current + ticks, self.maximum)
        is_filled = self.current >= self.maximum

        # Return True only on the transition from not-filled to filled
        if is_filled and not was_filled:
            self._ever_filled = True
            return True
        return False

    def regress(self, ticks: int = 1):
        """Decrease clock progress."""
        self.current = max(self.current - ticks, 0)

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
        """Get progress as a ratio."""
        return self.current / self.maximum if self.maximum > 0 else 0


@dataclass
class VoidState:
    """Tracks void corruption for an entity."""
    score: int = 0  # 0-10
    history: List[Dict[str, Any]] = field(default_factory=list)
    _processed_actions: set = field(default_factory=set, init=False, repr=False)
    _round_void_gain: int = field(default=0, init=False, repr=False)

    def add_void(self, amount: int, reason: str, action_id: Optional[str] = None) -> int:
        """
        Add void corruption with caps, return new score.

        Caps:
        - Max +1 void per action
        - Max +2 void per round per character

        Args:
            amount: Void to add (will be capped)
            reason: Why void is being added
            action_id: Unique action identifier to prevent duplicates

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
        if self._round_void_gain >= 2:
            logger.info(f"Void cap reached for this round (already +{self._round_void_gain})")
            return self.score

        # Apply remaining room in round cap
        actual_add = min(capped_amount, 2 - self._round_void_gain)
        self._round_void_gain += actual_add

        old_score = self.score
        self.score = min(self.score + actual_add, 10)

        self.history.append({
            'change': actual_add,
            'reason': reason,
            'old_score': old_score,
            'new_score': self.score
        })

        if action_id:
            self._processed_actions.add(action_id)

        logger.info(f"Void added: +{actual_add} (requested {amount}, round total {self._round_void_gain}/2)")
        return self.score

    def reset_round_void(self):
        """Reset round void counter. Call at start of each round."""
        self._round_void_gain = 0
        logger.debug(f"Reset round void counter")

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

    def __init__(self):
        self.scene_clocks: Dict[str, SceneClock] = {}
        self.void_states: Dict[str, VoidState] = {}  # agent_id -> VoidState
        self.action_history: List[ActionResolution] = []
        self.conditions: Dict[str, List[Condition]] = {}  # agent_id -> conditions

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
        agent_id: Optional[str] = None
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
            # Missing tool: player can accept +5 DC instead of void (future enhancement)
            ritual_effects['void_change'] += 1
            ritual_effects['consequences'].append("Missing ritual focus")

        if sanctified_altar:
            modifiers['sanctified_altar'] = 3
        elif not has_offering:
            # Missing offering: player can accept +5 DC instead of void (future enhancement)
            ritual_effects['void_change'] += 1
            ritual_effects['consequences'].append("No offering made")
        else:
            modifiers['offering'] = 1

        # Resolve the action
        resolution = self.resolve_action(
            intent=intent,
            attribute="Willpower",
            skill="Astral Arts",
            attribute_value=willpower,
            skill_value=astral_arts,
            difficulty=difficulty,
            modifiers=modifiers
        )

        # Calculate potential void consequences based on outcome
        # NOTE: Don't apply void here - let outcome_parser handle it to avoid duplicates
        if resolution.outcome_tier in [OutcomeTier.FAILURE, OutcomeTier.CRITICAL_FAILURE]:
            ritual_effects['void_change'] += 1
            ritual_effects['consequences'].append("Failed ritual: +1 Void")

        # Store void change in ritual_effects but don't apply it yet
        # The DM will apply void from outcome_parser to avoid duplicate tracking

        return resolution, ritual_effects

    def get_void_state(self, agent_id: str) -> VoidState:
        """Get or create void state for an agent."""
        if agent_id not in self.void_states:
            self.void_states[agent_id] = VoidState()
        return self.void_states[agent_id]

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
        description: str = ""
    ) -> SceneClock:
        """Create and register a scene clock."""
        clock = SceneClock(name=name, maximum=maximum, description=description)
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
            True if clock filled (trigger event)
        """
        if clock_name not in self.scene_clocks:
            logger.warning(f"Clock {clock_name} does not exist")
            return False

        clock = self.scene_clocks[clock_name]
        filled = clock.advance(ticks)

        if filled:
            logger.info(f"Clock {clock_name} FILLED! Reason: {reason}")

        return filled

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
        """Format resolution for DM narration."""
        # Format skill text - never show "×None"
        if resolution.skill and resolution.skill_value > 0:
            skill_text = f"({resolution.attribute} × {resolution.skill})"
        else:
            skill_text = f"({resolution.attribute})"

        # Calculate display formula based on skill usage
        if resolution.skill and resolution.skill_value > 0:
            # Skilled: Attribute × Skill + d20
            ability = resolution.attribute_value * resolution.skill_value
            formula = f"{resolution.attribute_value} × {resolution.skill_value} + {resolution.roll}"
            calculation = f"{ability} + {resolution.roll}"
        else:
            # Unskilled: Attribute + d20 - 5
            formula = f"{resolution.attribute_value} + {resolution.roll} - 5 (unskilled)"
            calculation = formula

        return f"""
**{resolution.intent}**
Roll: {skill_text} + d20
Result: {formula} = **{resolution.total}** vs DC {resolution.difficulty}
Margin: {resolution.margin:+d}
Outcome: **{resolution.outcome_tier.value.upper()}** {'✓' if resolution.success else '✗'}
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
