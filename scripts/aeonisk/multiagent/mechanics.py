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

    def advance(self, ticks: int = 1) -> bool:
        """Advance clock, return True if filled."""
        self.current = min(self.current + ticks, self.maximum)
        return self.current >= self.maximum

    def regress(self, ticks: int = 1):
        """Decrease clock progress."""
        self.current = max(self.current - ticks, 0)

    @property
    def filled(self) -> bool:
        """Check if clock is filled."""
        return self.current >= self.maximum

    @property
    def progress_ratio(self) -> float:
        """Get progress as a ratio."""
        return self.current / self.maximum if self.maximum > 0 else 0


@dataclass
class VoidState:
    """Tracks void corruption for an entity."""
    score: int = 0  # 0-10
    history: List[Dict[str, Any]] = field(default_factory=list)

    def add_void(self, amount: int, reason: str) -> int:
        """Add void corruption, return new score."""
        old_score = self.score
        self.score = min(self.score + amount, 10)

        self.history.append({
            'change': amount,
            'reason': reason,
            'old_score': old_score,
            'new_score': self.score
        })

        return self.score

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
    Handles dice rolls, rituals, void progression, and scene clocks.
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

    def resolve_action(
        self,
        intent: str,
        attribute: str,
        skill: Optional[str],
        attribute_value: int,
        skill_value: int,
        difficulty: int,
        modifiers: Dict[str, int] = None
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

        Returns:
            ActionResolution with full results
        """
        # Roll d20
        roll = random.randint(1, 20)

        # Calculate base total
        if skill_value > 0:
            base_total = (attribute_value * skill_value) + roll
        else:
            # Unskilled: just attribute + roll (with penalty)
            base_total = attribute_value + roll - 5  # Unskilled penalty

        # Apply modifiers
        total = base_total
        if modifiers:
            for mod_name, mod_value in modifiers.items():
                total += mod_value
                logger.debug(f"Applied modifier {mod_name}: {mod_value:+d}")

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

        # Apply modifiers for proper preparation
        if has_primary_tool:
            modifiers['primary_tool'] = 2
        else:
            ritual_effects['void_change'] += 1
            ritual_effects['consequences'].append("No primary tool: +1 Void risk")

        if sanctified_altar:
            modifiers['sanctified_altar'] = 3
        elif not has_offering:
            ritual_effects['void_change'] += 1
            ritual_effects['consequences'].append("No offering: +1 Void")
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

        # Apply void consequences based on outcome
        if resolution.outcome_tier in [OutcomeTier.FAILURE, OutcomeTier.CRITICAL_FAILURE]:
            ritual_effects['void_change'] += 1
            ritual_effects['consequences'].append("Failed ritual: +1 Void")

        # Track void changes
        if agent_id and ritual_effects['void_change'] != 0:
            void_state = self.get_void_state(agent_id)
            void_state.add_void(
                ritual_effects['void_change'],
                f"Ritual: {intent}"
            )
            resolution.state_effects['void_score'] = void_state.score

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
        # Example clock advancement logic
        if "Sanctuary Corruption" in self.scene_clocks:
            if resolution.outcome_tier in [OutcomeTier.FAILURE, OutcomeTier.CRITICAL_FAILURE]:
                if "scan" in resolution.intent.lower() or "ritual" in resolution.intent.lower():
                    self.advance_clock("Sanctuary Corruption", 1, f"Failed: {resolution.intent}")

        if "Saboteur Exposure" in self.scene_clocks:
            if resolution.success and "investigate" in resolution.intent.lower():
                margin_ticks = 1 if resolution.margin < 10 else 2
                self.advance_clock("Saboteur Exposure", margin_ticks, f"Investigation success")

        if "Communal Stability" in self.scene_clocks:
            if "harmoniz" in resolution.intent.lower():
                if resolution.success:
                    self.scene_clocks["Communal Stability"].regress(1)  # Stability improves
                else:
                    self.scene_clocks["Communal Stability"].advance(1)  # Stability degrades

    def calculate_initiative(self, agility: int) -> int:
        """Calculate initiative: Agility × 4 + d20."""
        return (agility * 4) + random.randint(1, 20)

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
        skill_text = f"({resolution.attribute} × {resolution.skill})" if resolution.skill else f"({resolution.attribute})"

        return f"""
**{resolution.intent}**
Roll: {skill_text} + d20
Result: {resolution.attribute_value} × {resolution.skill_value} + {resolution.roll} = **{resolution.total}** vs DC {resolution.difficulty}
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
