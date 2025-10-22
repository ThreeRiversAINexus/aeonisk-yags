"""
Comprehensive skill descriptions for YAGS + Aeonisk.
Used to generate player prompts with appropriate detail levels.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class SkillInfo:
    """Information about a skill."""
    name: str
    attribute: str
    description: str
    use_cases: List[str]
    category: str
    note: Optional[str] = None
    is_talent: bool = False  # YAGS Talents start at level 2


# Comprehensive skill database
SKILL_DATABASE: Dict[str, SkillInfo] = {
    # ======================
    # YAGS BASE TALENTS (start at 2)
    # ======================

    "Athletics": SkillInfo(
        name="Athletics",
        attribute="Agility",
        description="Running, climbing, jumping, acrobatics, physical feats",
        use_cases=["Chasing or fleeing", "Climbing obstacles", "Acrobatic maneuvers", "Physical stunts"],
        category="Movement",
        is_talent=True
    ),

    "Awareness": SkillInfo(
        name="Awareness",
        attribute="Perception",
        description="Noticing details, searching, perception, investigation",
        use_cases=["Investigating scenes", "Spotting clues", "Searching areas", "Noticing hidden things"],
        category="Investigation",
        is_talent=True
    ),

    "Brawl": SkillInfo(
        name="Brawl",
        attribute="Agility",
        description="Unarmed combat, punching, kicking, wrestling, dodging",
        use_cases=["Fighting unarmed", "Wrestling", "Dodging attacks", "Grappling"],
        category="Combat",
        is_talent=True
    ),

    "Charm": SkillInfo(
        name="Charm",
        attribute="Empathy",
        description="Persuasion, making friends, social influence (sincere or manipulative)",
        use_cases=["Befriending NPCs", "Negotiating peacefully", "Earning trust", "Social manipulation"],
        category="Social",
        is_talent=True,
        note="Can be sincere or insincere - it's about getting people to like you"
    ),

    "Guile": SkillInfo(
        name="Guile",
        attribute="Empathy",
        description="Deception, lying, reading lies, cunning misdirection",
        use_cases=["Bluffing", "Hiding intentions", "Spotting deception", "Cunning plans"],
        category="Social",
        is_talent=True,
        note="The 'dark side' of social skills - deception and manipulation"
    ),

    "Sleight": SkillInfo(
        name="Sleight",
        attribute="Dexterity",
        description="Pickpocketing, sleight of hand, manual dexterity tricks",
        use_cases=["Pickpocketing", "Palming objects", "Card tricks", "Manual dexterity"],
        category="Movement",
        is_talent=True
    ),

    "Stealth": SkillInfo(
        name="Stealth",
        attribute="Agility",
        description="Sneaking, hiding, moving quietly, avoiding detection",
        use_cases=["Sneaking past guards", "Hiding", "Moving silently", "Ambushing"],
        category="Movement",
        is_talent=True
    ),

    "Throw": SkillInfo(
        name="Throw",
        attribute="Dexterity",
        description="Throwing weapons, grenades, accuracy with thrown objects",
        use_cases=["Throwing grenades", "Knife throwing", "Tossing objects accurately"],
        category="Combat",
        is_talent=True
    ),

    # ======================
    # YAGS COMBAT SKILLS
    # ======================

    "Melee": SkillInfo(
        name="Melee",
        attribute="Dexterity",
        description="Swords, knives, clubs, hand-to-hand weapon combat",
        use_cases=["Fighting with melee weapons", "Sword combat", "Knife fighting", "Close combat"],
        category="Combat"
    ),

    "Guns": SkillInfo(
        name="Guns",
        attribute="Perception",
        description="Firearms, pistols, rifles, shotguns, targeting",
        use_cases=["Shooting firearms", "Aimed shots", "Suppressing fire", "Weapon handling"],
        category="Combat"
    ),

    # ======================
    # YAGS TECHNICAL/SUPPORT SKILLS
    # ======================

    "Tech/Craft": SkillInfo(
        name="Tech/Craft",
        attribute="Intelligence",
        description="Engineering, repair, building devices, crafting",
        use_cases=["Repairing equipment", "Building devices", "Engineering solutions", "Crafting items"],
        category="Technical"
    ),

    "Systems": SkillInfo(
        name="Systems",
        attribute="Intelligence",
        description="Operating technical systems, computers, ship controls",
        use_cases=["Using ship controls", "Computer interfaces", "System diagnostics", "Operating machinery"],
        category="Technical"
    ),

    "Counsel": SkillInfo(
        name="Counsel",
        attribute="Empathy",
        description="Emotional support, therapy, guidance, understanding trauma",
        use_cases=["Providing therapy", "Emotional support", "Helping with trauma", "Guidance"],
        category="Social"
    ),

    "Healing": SkillInfo(
        name="Healing",
        attribute="Intelligence",
        description="Medical treatment, first aid, surgery, treating injuries",
        use_cases=["Treating wounds", "First aid", "Surgery", "Diagnosing illness"],
        category="Technical"
    ),

    # ======================
    # YAGS KNOWLEDGE SKILLS
    # ======================

    "Science": SkillInfo(
        name="Science",
        attribute="Intelligence",
        description="Scientific knowledge, physics, chemistry, biology",
        use_cases=["Scientific analysis", "Understanding phenomena", "Lab work", "Research"],
        category="Knowledge",
        note="Broad knowledge skill - can specialize in specific sciences"
    ),

    "History": SkillInfo(
        name="History",
        attribute="Intelligence",
        description="Historical knowledge, past events, cultural context",
        use_cases=["Recalling historical events", "Understanding cultural context", "Dating artifacts"],
        category="Knowledge",
        note="Broad knowledge skill - can specialize in specific periods/regions"
    ),

    "Area Lore": SkillInfo(
        name="Area Lore",
        attribute="Intelligence",
        description="Local knowledge, geography, customs, notable locations",
        use_cases=["Navigating cities", "Knowing local customs", "Finding services", "Cultural awareness"],
        category="Knowledge",
        note="Specific to regions - may have multiple Area Lore skills"
    ),

    # ======================
    # YAGS VEHICLE SKILLS
    # ======================

    "Drive": SkillInfo(
        name="Drive",
        attribute="Dexterity",
        description="Driving ground vehicles, cars, motorcycles, trucks",
        use_cases=["Driving cars", "Chase scenes", "Evasive driving", "Vehicle control"],
        category="Technical",
        note="May require familiarities for different vehicle types"
    ),

    # ======================
    # AEONISK-SPECIFIC SKILLS
    # ======================

    "Astral Arts": SkillInfo(
        name="Astral Arts",
        attribute="Willpower",
        description="Channeling, resisting, and shaping spiritual energies; void manipulation rituals",
        use_cases=["Performing energy-based rituals", "Binding entities", "Void cleansing", "Spiritual channeling"],
        category="Ritual",
        note="Default ritual skill for most void/energy work. Uses Willpower, not Empathy."
    ),

    "Intimacy Ritual": SkillInfo(
        name="Intimacy Ritual",
        attribute="Empathy",
        description="Emotionally-powered or Bond-based rituals; creating connections",
        use_cases=["Strengthening Bonds", "Emotional connection rituals", "Intimidation rituals", "Empathic magic"],
        category="Ritual",
        note="Use for rituals involving emotions or Bonds, NOT void manipulation. Can use Willpower if very intense."
    ),

    "Magick Theory": SkillInfo(
        name="Magick Theory",
        attribute="Intelligence",
        description="Knowledge of glyphs, ritual systems, sacred mechanics, Aeons",
        use_cases=["Analyzing rituals", "Researching glyphs", "Understanding ritual mechanics", "Academic study"],
        category="Knowledge",
        note="For UNDERSTANDING rituals, not PERFORMING them. Use Intelligence, not Willpower."
    ),

    "Corporate Influence": SkillInfo(
        name="Corporate Influence",
        attribute="Empathy",
        description="Navigating faction politics, extracting favors, reading corporate intentions",
        use_cases=["Faction negotiations", "Corporate politics", "Extracting favors", "Reading power dynamics"],
        category="Social",
        note="Aeonisk-specific - understanding the faction power structures"
    ),

    "Debt Law": SkillInfo(
        name="Debt Law",
        attribute="Intelligence",
        description="Understanding/manipulating contracts, oaths, Soulcredit systems, legal frameworks",
        use_cases=["Contract negotiation", "Understanding legal obligations", "Soulcredit manipulation", "Oath interpretation"],
        category="Knowledge",
        note="Aeonisk-specific - the legal side of spiritual economy"
    ),

    "Pilot": SkillInfo(
        name="Pilot",
        attribute="Agility",
        description="Vehicles, EVA, slipstream jumps, docking, ship maneuvering",
        use_cases=["Piloting ships", "EVA maneuvers", "Docking procedures", "Slipstream navigation"],
        category="Technical",
        note="Aeonisk-specific - replaces/supplements Drive for spacecraft"
    ),

    "Drone Operation": SkillInfo(
        name="Drone Operation",
        attribute="Intelligence",
        description="Remote drone control, spark-burst, EMP, mapping, hacking via drones",
        use_cases=["Deploying drones", "Remote hacking", "EMP strikes", "Reconnaissance", "Tactical mapping"],
        category="Technical",
        note="Aeonisk-specific - operating remote spark-drones"
    ),
}


def get_skill_info(skill_name: str) -> Optional[SkillInfo]:
    """
    Get skill information by name (case-insensitive).

    Args:
        skill_name: Name of skill to look up

    Returns:
        SkillInfo object or None if not found
    """
    # Normalize skill name
    from .skill_mapping import normalize_skill
    normalized = normalize_skill(skill_name)

    if normalized and normalized in SKILL_DATABASE:
        return SKILL_DATABASE[normalized]

    # Try direct lookup
    if skill_name in SKILL_DATABASE:
        return SKILL_DATABASE[skill_name]

    return None


def format_skill_full(skill_name: str, skill_level: int) -> str:
    """
    Format a skill with full details (for skills the character has).

    Args:
        skill_name: Name of skill
        skill_level: Character's level in this skill

    Returns:
        Formatted skill description
    """
    info = get_skill_info(skill_name)
    if not info:
        # Fallback for unknown skills
        return f"- **{skill_name} ({skill_level})**"

    lines = [f"- **{info.name} ({skill_level})** [{info.attribute}]: {info.description}"]

    if info.use_cases:
        use_cases_str = ", ".join(info.use_cases[:3])  # Limit to 3 use cases
        lines.append(f"  → Use when: {use_cases_str}")

    if info.note:
        lines.append(f"  ℹ️  {info.note}")

    return "\n".join(lines)


def format_skill_brief(skill_name: str) -> str:
    """
    Format a skill with brief details (for skills the character doesn't have).

    Args:
        skill_name: Name of skill

    Returns:
        Brief formatted skill description
    """
    info = get_skill_info(skill_name)
    if not info:
        return f"- {skill_name}"

    return f"- **{info.name}** [{info.attribute}]: {info.description}"


def get_all_skills_by_category() -> Dict[str, List[str]]:
    """
    Get all skills organized by category.

    Returns:
        Dict mapping category name to list of skill names
    """
    categories: Dict[str, List[str]] = {}

    for skill_name, info in SKILL_DATABASE.items():
        if info.category not in categories:
            categories[info.category] = []
        categories[info.category].append(skill_name)

    # Sort skills within each category
    for category in categories:
        categories[category].sort()

    return categories


def get_talents() -> List[str]:
    """
    Get list of YAGS Talent skills (which start at level 2).

    Returns:
        List of talent skill names
    """
    return [name for name, info in SKILL_DATABASE.items() if info.is_talent]
