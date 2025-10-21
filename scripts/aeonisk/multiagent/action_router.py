"""
Action routing system for Aeonisk YAGS.
Routes actions to appropriate Attribute × Skill combinations.
"""

from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ActionRouter:
    """Routes actions to appropriate attribute + skill based on intent."""

    # Skill routing keywords
    SENSING_KEYWORDS = ['trace', 'sense', 'detect', 'attune', 'calibrate', 'scan', 'perceive', 'feel', 'read']
    RITUAL_KEYWORDS = ['perform a ritual', 'conduct a ritual', 'ritual to', 'begin ritual', 'cast ritual', 'invoke ritual']
    TECH_KEYWORDS = ['interface', 'hack', 'patch', 'contain', 'isolate', 'firewall', 'encrypt', 'debug', 'analyze system']
    DREAMWORK_KEYWORDS = ['dream', 'sleep', 'oneiric', 'lucid', 'nightmare', 'vision', 'memory dive']
    DIALOGUE_KEYWORDS = ['talk to', 'speak to', 'ask', 'tell', 'discuss with', 'question', 'say to', 'converse with']
    SOCIAL_CARE_KEYWORDS = ['counsel', 'comfort', 'guide', 'heal mind', 'therapy', 'support']
    SOCIAL_COMMAND_KEYWORDS = ['order', 'command', 'rally', 'intimidate', 'coordinate', 'organize']
    SOCIAL_GENERAL = ['discuss', 'talk', 'share', 'convince', 'persuade']
    INVESTIGATION_KEYWORDS = ['investigate', 'search', 'examine', 'study', 'research', 'uncover']
    GROUNDING_KEYWORDS = ['ground', 'center', 'meditate', 'calm self', 'focus inward', 'discipline mind']
    PURGE_KEYWORDS = ['purge', 'cleanse', 'dephase', 'filter', 'contain void', 'isolate corruption']

    def route_action(
        self,
        intent: str,
        action_type: str,
        character_skills: dict,
        is_explicit_ritual: bool = False
    ) -> Tuple[str, Optional[str], str]:
        """
        Route an action to the appropriate attribute and skill.

        Args:
            intent: The action intent text
            action_type: Declared action type
            character_skills: Character's skill dict
            is_explicit_ritual: Whether this is explicitly marked as a ritual

        Returns:
            Tuple of (attribute, skill, rationale)
        """
        intent_lower = intent.lower()

        # 1. RECOVERY MOVES (highest priority - help players recover void)
        if any(kw in intent_lower for kw in self.GROUNDING_KEYWORDS):
            if 'Discipline' in character_skills:
                return ('Willpower', 'Discipline', 'Grounding meditation (-1 Void on success)')
            else:
                return ('Willpower', None, 'Grounding meditation (unskilled, -1 Void on success)')

        if any(kw in intent_lower for kw in self.PURGE_KEYWORDS):
            if 'Systems' in character_skills:
                return ('Intelligence', 'Systems', 'Void purging/dephasing (-scene Void on success)')
            else:
                return ('Intelligence', None, 'Void purging (unskilled)')

        # 2. CHARACTER DIALOGUE (inter-character social interaction)
        if any(kw in intent_lower for kw in self.DIALOGUE_KEYWORDS):
            if 'Charm' in character_skills:
                return ('Empathy', 'Charm', 'Dialogue with party member')
            elif 'Counsel' in character_skills:
                return ('Empathy', 'Counsel', 'Dialogue with party member')
            else:
                return ('Empathy', None, 'Dialogue (unskilled)')

        # 3. RITUALS (opt-in only)
        if is_explicit_ritual or action_type == 'ritual':
            return ('Willpower', 'Astral Arts', 'Ritual action')

        # 3. SENSING / ATTUNEMENT
        if any(kw in intent_lower for kw in self.SENSING_KEYWORDS):
            if 'Attunement' in character_skills:
                return ('Perception', 'Attunement', 'Sensing resonance/void currents')
            else:
                return ('Perception', None, 'Raw perception (no Attunement skill)')

        # 4. TECH / SYSTEMS
        if any(kw in intent_lower for kw in self.TECH_KEYWORDS):
            if 'Systems' in character_skills:
                return ('Intelligence', 'Systems', 'Technical system work')
            else:
                return ('Intelligence', None, 'Raw intelligence (no Systems skill)')

        # 5. DREAMWORK
        if any(kw in intent_lower for kw in self.DREAMWORK_KEYWORDS):
            if 'Dreamwork' in character_skills:
                return ('Willpower', 'Dreamwork', 'Oneiric navigation')
            else:
                return ('Empathy', None, 'Raw empathy (no Dreamwork skill)')

        # 6. SOCIAL - CARE
        if any(kw in intent_lower for kw in self.SOCIAL_CARE_KEYWORDS):
            if 'Counsel' in character_skills:
                return ('Empathy', 'Counsel', 'Social care/support')
            elif 'Charm' in character_skills:
                return ('Empathy', 'Charm', 'Social care via charm')
            else:
                return ('Empathy', None, 'Raw empathy')

        # 7. SOCIAL - COMMAND
        if any(kw in intent_lower for kw in self.SOCIAL_COMMAND_KEYWORDS):
            if 'Command' in character_skills:
                return ('Charisma', 'Command', 'Social command/leadership')
            elif 'Guile' in character_skills:
                return ('Charisma', 'Guile', 'Social manipulation')
            else:
                return ('Charisma', None, 'Raw charisma')

        # 8. SOCIAL - GENERAL
        if any(kw in intent_lower for kw in self.SOCIAL_GENERAL):
            if 'Charm' in character_skills:
                return ('Empathy', 'Charm', 'General social interaction')
            elif 'Guile' in character_skills:
                return ('Empathy', 'Guile', 'Social deception')
            else:
                return ('Empathy', None, 'Raw empathy')

        # 9. INVESTIGATION
        if any(kw in intent_lower for kw in self.INVESTIGATION_KEYWORDS):
            if 'Awareness' in character_skills:
                return ('Perception', 'Awareness', 'Investigation/search')
            else:
                return ('Perception', None, 'Raw perception')

        # 10. DEFAULT: Use action_type
        if action_type == 'social':
            return ('Empathy', 'Charm' if 'Charm' in character_skills else None, 'Social action')
        elif action_type == 'investigate':
            return ('Perception', 'Awareness' if 'Awareness' in character_skills else None, 'Investigation')
        elif action_type == 'technical':
            return ('Intelligence', 'Systems' if 'Systems' in character_skills else None, 'Technical action')
        else:
            # Generic explore/perception
            return ('Perception', None, 'Generic observation')

    def is_explicit_ritual(self, intent: str) -> bool:
        """Check if intent explicitly declares a ritual."""
        intent_lower = intent.lower()
        return any(phrase in intent_lower for phrase in self.RITUAL_KEYWORDS)
