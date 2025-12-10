"""
Character validation system for YAGS + Aeonisk conformance.

Validates:
- Attributes conform to YAGS standard (8 attributes)
- Skills map to correct attributes from SKILL_DATABASE
- Attribute values are in valid range (1-6 for humans, up to 8 for exceptional)
- Skill values follow YAGS rules (Talents start at 2, regular skills at 0)
- Total attribute points are within reasonable bounds
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import logging

try:
    # Try relative import (when run as module)
    from .skill_descriptions import SKILL_DATABASE
    from .constants import YAGS_ATTRIBUTES, YAGS_SECONDARY_STATS
except ImportError:
    # Fallback for direct script execution
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from skill_descriptions import SKILL_DATABASE
    from constants import YAGS_ATTRIBUTES, YAGS_SECONDARY_STATS

logger = logging.getLogger(__name__)

# Attribute value ranges
ATTRIBUTE_MIN = 1  # Minimum for any human
ATTRIBUTE_TYPICAL_MAX = 5  # Typical human maximum
ATTRIBUTE_EXCEPTIONAL_MAX = 8  # Exceptional (cinematic) maximum

# Point budgets (approximate)
ATTRIBUTE_BUDGET_MIN = 20  # Weak character (avg 2.5)
ATTRIBUTE_BUDGET_TYPICAL = 24  # Typical character (avg 3.0)
ATTRIBUTE_BUDGET_HEROIC = 28  # Heroic character (avg 3.5)
ATTRIBUTE_BUDGET_MAX = 40  # Maximum reasonable (avg 5.0)


@dataclass
class ValidationIssue:
    """A single validation issue."""
    severity: str  # 'error', 'warning', 'info'
    category: str  # 'attribute', 'skill', 'budget', 'schema'
    message: str
    field: Optional[str] = None  # Which field has the issue


@dataclass
class ValidationResult:
    """Result of character validation."""
    is_valid: bool  # False if any errors
    issues: List[ValidationIssue]
    character_name: str

    def get_errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == 'error']

    def get_warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == 'warning']

    def get_info(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == 'info']

    def summary(self) -> str:
        errors = len(self.get_errors())
        warnings = len(self.get_warnings())
        status = "INVALID" if not self.is_valid else "VALID"
        return f"{self.character_name}: {status} ({errors} errors, {warnings} warnings)"


class CharacterValidator:
    """Validates character definitions against YAGS + Aeonisk standards."""

    def __init__(self, strict: bool = False):
        """
        Initialize validator.

        Args:
            strict: If True, warnings become errors
        """
        self.strict = strict

    def validate_character(self, character_data: Dict[str, Any]) -> ValidationResult:
        """
        Validate a character definition.

        Args:
            character_data: Character dict from session config

        Returns:
            ValidationResult with all issues found
        """
        issues = []
        character_name = character_data.get('name', 'Unknown')

        # 1. Schema validation
        issues.extend(self._validate_schema(character_data))

        # 2. Attribute validation
        attributes = character_data.get('attributes', {})
        issues.extend(self._validate_attributes(attributes))

        # 3. Skill validation
        skills = character_data.get('skills', {})
        issues.extend(self._validate_skills(skills, attributes))

        # 4. Budget validation
        issues.extend(self._validate_budget(attributes))

        # Determine if valid (no errors)
        has_errors = any(i.severity == 'error' for i in issues)

        return ValidationResult(
            is_valid=not has_errors,
            issues=issues,
            character_name=character_name
        )

    def _validate_schema(self, character_data: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate basic schema structure."""
        issues = []

        # Required fields
        if 'name' not in character_data:
            issues.append(ValidationIssue(
                severity='error',
                category='schema',
                message="Missing required field: 'name'",
                field='name'
            ))

        if 'attributes' not in character_data:
            issues.append(ValidationIssue(
                severity='error',
                category='schema',
                message="Missing required field: 'attributes'",
                field='attributes'
            ))

        if 'skills' not in character_data:
            issues.append(ValidationIssue(
                severity='warning',
                category='schema',
                message="Missing 'skills' field (character has no skills)",
                field='skills'
            ))

        return issues

    def _validate_attributes(self, attributes: Dict[str, int]) -> List[ValidationIssue]:
        """Validate attribute conformance to YAGS."""
        issues = []

        if not attributes:
            issues.append(ValidationIssue(
                severity='error',
                category='attribute',
                message="No attributes defined",
                field='attributes'
            ))
            return issues

        # Check for YAGS conformance
        for attr_name in attributes.keys():
            if attr_name not in YAGS_ATTRIBUTES:
                # Check if it's a valid secondary stat (like Size)
                if attr_name in YAGS_SECONDARY_STATS:
                    # Size is valid, just note it
                    issues.append(ValidationIssue(
                        severity='info',
                        category='attribute',
                        message=f"'{attr_name}' is a YAGS secondary stat (not a core attribute)",
                        field=attr_name
                    ))
                    continue

                # Check for common mistakes
                suggestions = []
                if attr_name == "Charisma":
                    suggestions.append("Replace 'Charisma' with 'Empathy' (YAGS standard)")
                elif attr_name == "Health":
                    suggestions.append("Replace 'Health' with 'Endurance' (Aeonisk uses Endurance)")
                elif attr_name == "Will":
                    suggestions.append("Replace 'Will' with 'Willpower' (Aeonisk uses Willpower)")

                suggestion_text = f" Suggestion: {suggestions[0]}" if suggestions else ""
                issues.append(ValidationIssue(
                    severity='error',
                    category='attribute',
                    message=f"Invalid attribute '{attr_name}' (not in YAGS standard).{suggestion_text}",
                    field=attr_name
                ))

        # Check for missing attributes
        for attr_name in YAGS_ATTRIBUTES:
            if attr_name not in attributes:
                severity = 'warning' if attr_name == 'Dexterity' else 'error'
                # Dexterity is only a warning since many configs predate it
                issues.append(ValidationIssue(
                    severity=severity,
                    category='attribute',
                    message=f"Missing attribute '{attr_name}'",
                    field=attr_name
                ))

        # Check attribute value ranges
        for attr_name, attr_value in attributes.items():
            if attr_name not in YAGS_ATTRIBUTES:
                continue  # Already reported above

            if not isinstance(attr_value, int):
                issues.append(ValidationIssue(
                    severity='error',
                    category='attribute',
                    message=f"Attribute '{attr_name}' value must be integer, got {type(attr_value).__name__}",
                    field=attr_name
                ))
                continue

            if attr_value < ATTRIBUTE_MIN:
                issues.append(ValidationIssue(
                    severity='error',
                    category='attribute',
                    message=f"Attribute '{attr_name}' value {attr_value} below minimum ({ATTRIBUTE_MIN})",
                    field=attr_name
                ))

            if attr_value > ATTRIBUTE_EXCEPTIONAL_MAX:
                issues.append(ValidationIssue(
                    severity='error',
                    category='attribute',
                    message=f"Attribute '{attr_name}' value {attr_value} exceeds exceptional max ({ATTRIBUTE_EXCEPTIONAL_MAX})",
                    field=attr_name
                ))
            elif attr_value > ATTRIBUTE_TYPICAL_MAX:
                issues.append(ValidationIssue(
                    severity='info',
                    category='attribute',
                    message=f"Attribute '{attr_name}' value {attr_value} is exceptional (typical max is {ATTRIBUTE_TYPICAL_MAX})",
                    field=attr_name
                ))

        return issues

    def _validate_skills(self, skills: Dict[str, int], attributes: Dict[str, int]) -> List[ValidationIssue]:
        """Validate skill definitions and attribute mappings."""
        issues = []

        if not skills:
            # No skills is valid (all unskilled)
            return issues

        for skill_name, skill_value in skills.items():
            # Check if skill exists in SKILL_DATABASE
            if skill_name not in SKILL_DATABASE:
                issues.append(ValidationIssue(
                    severity='warning',
                    category='skill',
                    message=f"Unknown skill '{skill_name}' (not in SKILL_DATABASE)",
                    field=skill_name
                ))
                continue

            skill_info = SKILL_DATABASE[skill_name]

            # Check if character has the required attribute
            required_attr = skill_info.attribute
            if required_attr not in attributes:
                issues.append(ValidationIssue(
                    severity='error',
                    category='skill',
                    message=f"Skill '{skill_name}' requires attribute '{required_attr}' (missing from character)",
                    field=skill_name
                ))

            # Check skill value validity
            if not isinstance(skill_value, int):
                issues.append(ValidationIssue(
                    severity='error',
                    category='skill',
                    message=f"Skill '{skill_name}' value must be integer, got {type(skill_value).__name__}",
                    field=skill_name
                ))
                continue

            # Check skill value range
            if skill_value < 0:
                issues.append(ValidationIssue(
                    severity='error',
                    category='skill',
                    message=f"Skill '{skill_name}' value {skill_value} cannot be negative",
                    field=skill_name
                ))

            if skill_value > 10:
                issues.append(ValidationIssue(
                    severity='warning',
                    category='skill',
                    message=f"Skill '{skill_name}' value {skill_value} is exceptionally high (typical max is 6-8)",
                    field=skill_name
                ))

            # Check talent starting values (should be at least 2)
            if skill_info.is_talent and skill_value < 2:
                issues.append(ValidationIssue(
                    severity='info',
                    category='skill',
                    message=f"Talent '{skill_name}' has value {skill_value} (talents typically start at 2)",
                    field=skill_name
                ))

        return issues

    def _validate_budget(self, attributes: Dict[str, int]) -> List[ValidationIssue]:
        """Validate attribute point budget."""
        issues = []

        # Only validate YAGS-conformant attributes
        valid_attrs = {k: v for k, v in attributes.items() if k in YAGS_ATTRIBUTES}

        if not valid_attrs:
            return issues

        total_points = sum(valid_attrs.values())

        if total_points < ATTRIBUTE_BUDGET_MIN:
            issues.append(ValidationIssue(
                severity='warning',
                category='budget',
                message=f"Total attribute points ({total_points}) below typical minimum ({ATTRIBUTE_BUDGET_MIN})",
                field='attributes'
            ))

        if total_points > ATTRIBUTE_BUDGET_MAX:
            issues.append(ValidationIssue(
                severity='warning',
                category='budget',
                message=f"Total attribute points ({total_points}) exceeds maximum ({ATTRIBUTE_BUDGET_MAX})",
                field='attributes'
            ))

        # Info messages for point budget ranges
        if ATTRIBUTE_BUDGET_MIN <= total_points < ATTRIBUTE_BUDGET_TYPICAL:
            issues.append(ValidationIssue(
                severity='info',
                category='budget',
                message=f"Character has {total_points} attribute points (weak/average character)",
                field='attributes'
            ))
        elif ATTRIBUTE_BUDGET_TYPICAL <= total_points < ATTRIBUTE_BUDGET_HEROIC:
            issues.append(ValidationIssue(
                severity='info',
                category='budget',
                message=f"Character has {total_points} attribute points (typical/competent character)",
                field='attributes'
            ))
        elif ATTRIBUTE_BUDGET_HEROIC <= total_points <= ATTRIBUTE_BUDGET_MAX:
            issues.append(ValidationIssue(
                severity='info',
                category='budget',
                message=f"Character has {total_points} attribute points (heroic/elite character)",
                field='attributes'
            ))

        return issues

    def validate_session_config(self, config_data: Dict[str, Any]) -> List[ValidationResult]:
        """
        Validate all characters in a session config.

        Args:
            config_data: Full session config JSON

        Returns:
            List of ValidationResult, one per character
        """
        results = []

        # Get characters from config (handle different structures)
        all_characters = []

        # New structure: agents.players
        agents = config_data.get('agents', {})
        players = agents.get('players', [])
        all_characters.extend(players)

        # Old structure: party (for backwards compatibility)
        party = config_data.get('party', [])
        all_characters.extend(party)

        # NPCs
        npcs = config_data.get('npcs', [])
        all_characters.extend(npcs)

        if not all_characters:
            logger.warning("No characters found in session config")
            return results

        for character_data in all_characters:
            result = self.validate_character(character_data)
            results.append(result)

        return results


def validate_config_file(config_path: str, strict: bool = False) -> Tuple[bool, List[ValidationResult]]:
    """
    Validate a session config file.

    Args:
        config_path: Path to session config JSON
        strict: If True, warnings become errors

    Returns:
        Tuple of (all_valid, list of ValidationResult)
    """
    import json
    from pathlib import Path

    config_file = Path(config_path)
    if not config_file.exists():
        logger.error(f"Config file not found: {config_path}")
        return (False, [])

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {config_path}: {e}")
        return (False, [])

    validator = CharacterValidator(strict=strict)
    results = validator.validate_session_config(config_data)

    all_valid = all(r.is_valid for r in results)

    return (all_valid, results)


if __name__ == '__main__':
    import sys
    import argparse

    parser = argparse.ArgumentParser(description='Validate character definitions in session configs')
    parser.add_argument('config_path', help='Path to session config JSON')
    parser.add_argument('--strict', action='store_true', help='Treat warnings as errors')
    parser.add_argument('--verbose', action='store_true', help='Show info messages')

    args = parser.parse_args()

    all_valid, results = validate_config_file(args.config_path, strict=args.strict)

    print(f"\n{'='*60}")
    print(f"Validating: {args.config_path}")
    print(f"{'='*60}\n")

    for result in results:
        print(result.summary())

        errors = result.get_errors()
        warnings = result.get_warnings()
        infos = result.get_info()

        if errors:
            print("  ERRORS:")
            for issue in errors:
                print(f"    ❌ {issue.message}")

        if warnings:
            print("  WARNINGS:")
            for issue in warnings:
                print(f"    ⚠️  {issue.message}")

        if args.verbose and infos:
            print("  INFO:")
            for issue in infos:
                print(f"    ℹ️  {issue.message}")

        print()

    print(f"{'='*60}")
    print(f"Overall: {'✅ ALL VALID' if all_valid else '❌ VALIDATION FAILED'}")
    print(f"{'='*60}\n")

    sys.exit(0 if all_valid else 1)
