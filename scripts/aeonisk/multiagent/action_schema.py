"""
Action schema and validation for multi-agent gameplay.
Ensures agents provide structured mechanical information with each action.
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ActionDeclaration:
    """
    Structured action declaration that agents must provide.
    Forces mechanical thinking and prevents vague narration.
    """
    # Core action definition
    intent: str  # Concise verb phrase describing what character does
    description: str  # 1-2 sentence narrative description

    # Mechanical components
    attribute: str  # Which attribute (Strength, Agility, etc.)
    skill: Optional[str]  # Which skill, or None for raw attribute check
    difficulty_estimate: int  # Estimated target number
    difficulty_justification: str  # Why this difficulty?

    # Character state
    character_name: str
    agent_id: str

    # Action type categorization
    action_type: str  # explore, investigate, ritual, social, combat, technical

    # Tactical positioning (for combat)
    target_position: Optional[str] = None  # Engaged/Near-PC/Far-PC/etc. - applied during execution
    target_enemy: Optional[str] = None  # Enemy ID or name when attacking

    # Optional ritual-specific fields
    is_ritual: bool = False
    has_primary_tool: bool = False
    has_offering: bool = False
    ritual_components: Optional[str] = None

    # Optional modifiers
    situational_modifiers: Dict[str, int] = None

    # Metadata
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
        if self.situational_modifiers is None:
            self.situational_modifiers = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def validate(self) -> List[str]:
        """
        Validate the action declaration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not self.intent or len(self.intent) < 3:
            errors.append("Intent must be a clear action description")

        if not self.description or len(self.description) < 10:
            errors.append("Description must be at least 10 characters")

        valid_attributes = [
            "Strength", "Agility", "Endurance", "Perception",
            "Intelligence", "Empathy", "Willpower", "Charisma"
        ]
        if self.attribute not in valid_attributes:
            errors.append(f"Attribute must be one of: {', '.join(valid_attributes)}")

        if self.difficulty_estimate < 5 or self.difficulty_estimate > 50:
            errors.append("Difficulty estimate must be between 5 and 50")

        if not self.difficulty_justification:
            errors.append("Must provide justification for difficulty estimate")

        valid_action_types = [
            "explore", "investigate", "ritual", "social",
            "combat", "technical", "perception", "custom"
        ]
        if self.action_type not in valid_action_types:
            errors.append(f"Action type must be one of: {', '.join(valid_action_types)}")

        # Removed overly restrictive ritual validation
        # Rituals CAN use Astral Arts, but other skills (Magick Theory, Attunement, Systems)
        # can also interact with void/spiritual phenomena in different ways
        # The action router handles appropriate skill selection

        return errors

    def get_summary(self) -> str:
        """Get a brief summary for logging."""
        # Never show "×None" - only show skill if it's a valid non-None value
        if self.skill and self.skill.lower() != 'none':
            skill_text = f" × {self.skill}"
        else:
            skill_text = ""
        return f"{self.character_name}: {self.intent} ({self.attribute}{skill_text} vs ~{self.difficulty_estimate})"


class IntentDeduplicator:
    """
    Prevents agents from spamming the same action repeatedly.
    Tracks recent intents and suggests alternatives.
    """

    def __init__(self, window_size: int = 3):
        self.window_size = window_size
        self.agent_history: Dict[str, List[str]] = {}  # agent_id -> recent intents

    def check_duplicate(self, agent_id: str, intent: str, threshold: float = 0.7) -> bool:
        """
        Check if intent is too similar to recent actions.

        Args:
            agent_id: Agent identifier
            intent: Current intent to check
            threshold: Similarity threshold (0-1)

        Returns:
            True if this is a duplicate/too similar
        """
        if agent_id not in self.agent_history:
            self.agent_history[agent_id] = []
            return False

        recent = self.agent_history[agent_id]

        # Simple similarity check: word overlap
        intent_words = set(intent.lower().split())

        for past_intent in recent:
            past_words = set(past_intent.lower().split())
            if len(intent_words) == 0 or len(past_words) == 0:
                continue

            # Jaccard similarity
            intersection = len(intent_words & past_words)
            union = len(intent_words | past_words)
            similarity = intersection / union if union > 0 else 0

            if similarity >= threshold:
                logger.warning(
                    f"Agent {agent_id} attempting duplicate action. "
                    f"Current: '{intent}' vs Recent: '{past_intent}' "
                    f"(similarity: {similarity:.2f})"
                )
                return True

        return False

    def record_intent(self, agent_id: str, intent: str):
        """Record an intent in the agent's history."""
        if agent_id not in self.agent_history:
            self.agent_history[agent_id] = []

        self.agent_history[agent_id].append(intent)

        # Keep only recent history
        if len(self.agent_history[agent_id]) > self.window_size:
            self.agent_history[agent_id] = self.agent_history[agent_id][-self.window_size:]

    def suggest_alternatives(
        self,
        agent_id: str,
        character_name: str,
        scenario_context: str
    ) -> List[str]:
        """
        Suggest alternative actions to break repetition loop.

        Returns:
            List of suggested action prompts
        """
        recent = self.agent_history.get(agent_id, [])

        suggestions = []

        # Check what types of actions were used
        used_investigation = any('scan' in i.lower() or 'investigate' in i.lower() for i in recent)
        used_ritual = any('ritual' in i.lower() or 'harmoniz' in i.lower() for i in recent)
        used_social = any('ask' in i.lower() or 'talk' in i.lower() or 'interact' in i.lower() for i in recent)

        if used_investigation and not used_social:
            suggestions.append(
                f"{character_name} could question NPCs or other characters about their observations"
            )

        if used_ritual and not used_investigation:
            suggestions.append(
                f"{character_name} could use technical or forensic methods to gather evidence"
            )

        if not used_ritual:
            suggestions.append(
                f"{character_name} could attempt a ritual to reveal hidden information"
            )

        # Location-based suggestions
        if 'chamber' in scenario_context.lower() and not any('chamber' in i.lower() for i in recent):
            suggestions.append(
                f"{character_name} could physically search specific chambers or areas"
            )

        # Default suggestions
        if len(suggestions) < 3:
            suggestions.extend([
                f"{character_name} could change their approach entirely",
                f"{character_name} could collaborate with another character",
                f"{character_name} could try a high-risk, proactive action"
            ])

        return suggestions[:3]

    def get_recent_intents(self, agent_id: str) -> List[str]:
        """Get agent's recent intent history."""
        return self.agent_history.get(agent_id, [])

    def clear_history(self, agent_id: Optional[str] = None):
        """Clear history for one or all agents."""
        if agent_id:
            self.agent_history[agent_id] = []
        else:
            self.agent_history = {}


class ActionValidator:
    """Validates and enriches action declarations."""

    def __init__(self):
        self.deduplicator = IntentDeduplicator(window_size=2)

    def validate_action(
        self,
        action: ActionDeclaration,
        allow_duplicates: bool = True
    ) -> tuple[bool, List[str]]:
        """
        Validate an action declaration.

        Args:
            action: The action to validate
            allow_duplicates: Whether to allow duplicate intents (default: True to allow repeated combat actions)

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        # Structural validation
        structural_errors = action.validate()
        issues.extend(structural_errors)

        # Check for duplicates (disabled by default for combat scenarios)
        if not allow_duplicates:
            if self.deduplicator.check_duplicate(action.agent_id, action.intent):
                issues.append(
                    f"Action too similar to recent intents: {self.deduplicator.get_recent_intents(action.agent_id)}"
                )
                suggestions = self.deduplicator.suggest_alternatives(
                    action.agent_id,
                    action.character_name,
                    action.description
                )
                issues.append(f"Suggested alternatives: {'; '.join(suggestions)}")

        is_valid = len(issues) == 0

        # Record valid, non-duplicate intents
        if is_valid or allow_duplicates:
            self.deduplicator.record_intent(action.agent_id, action.intent)

        return is_valid, issues

    def create_from_dict(self, data: Dict[str, Any]) -> ActionDeclaration:
        """Create ActionDeclaration from dictionary."""
        return ActionDeclaration(**data)

    def parse_llm_response(self, response: str, agent_id: str, character_name: str) -> Optional[ActionDeclaration]:
        """
        Attempt to parse an action from LLM text response.
        This is a fallback for when structured output isn't available.

        Returns:
            ActionDeclaration if parseable, None otherwise
        """
        # This is simplified - in production, use better parsing
        lines = response.strip().split('\n')

        action_data = {
            'agent_id': agent_id,
            'character_name': character_name,
            'intent': 'unknown action',
            'description': response[:200],
            'attribute': 'Perception',  # Default
            'skill': None,
            'difficulty_estimate': 20,  # Default moderate
            'difficulty_justification': 'estimated from context',
            'action_type': 'custom'
        }

        # Try to extract intent from first meaningful line
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                action_data['intent'] = line[:100]
                break

        try:
            return ActionDeclaration(**action_data)
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return None


def create_action_prompt_template() -> str:
    """
    Return a template prompt that guides agents to provide structured actions.
    """
    return """
When declaring an action, you MUST provide:

1. **Intent**: Clear, concise description of what you're doing (verb phrase)
2. **Attribute**: Which attribute you're using (Strength, Agility, Endurance, Perception, Intelligence, Empathy, Willpower, Charisma)
3. **Skill**: Which skill applies (or "None" for raw attribute check)
4. **Difficulty Estimate**: Your guess at the target number (10=Easy, 20=Moderate, 25=Challenging, 30=Difficult, 35+=Very Difficult)
5. **Justification**: Brief explanation of why you chose that difficulty
6. **Action Type**: explore | investigate | ritual | social | combat | technical | perception

For **Rituals** specifically, also specify:
- **Primary Tool**: Do you have the required ritual focus/tool? (yes/no)
- **Offering**: Are you making an offering? (yes/no)
- **Components**: What materials/components are you using?

**IMPORTANT**: Do NOT repeat actions you've already attempted in the last 2 turns. Try different approaches, angles, tools, or locations.

**Recent Actions You've Taken**: {recent_intents}

Format your response as:
```
INTENT: [brief action description]
ATTRIBUTE: [attribute name]
SKILL: [skill name or None]
DIFFICULTY: [number] - [justification]
ACTION_TYPE: [type]
DESCRIPTION: [1-2 sentence narrative description]
```
""".strip()
