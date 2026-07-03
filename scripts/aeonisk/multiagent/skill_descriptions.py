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
    # STRENGTH SKILLS (NEW)
    # ======================

    "Climbing": SkillInfo(
        name="Climbing",
        attribute="Strength",
        description="Power climbing, rope climbing, scaling walls with raw strength",
        use_cases=[
            "Climbing ropes with equipment",
            "Scaling sheer walls",
            "Ascending vertical surfaces with strength",
            "Climbing under load (carrying equipment/wounded)"
        ],
        category="Movement",
        note="Uses raw power; Athletics covers agile parkour-style climbing"
    ),

    "Swimming": SkillInfo(
        name="Swimming",
        attribute="Strength",
        description="Swimming, diving, fighting currents with power",
        use_cases=[
            "Swimming long distances",
            "Diving underwater",
            "Fighting strong currents",
            "Swimming while burdened"
        ],
        category="Movement",
        note="Endurance for marathon swimming, Strength for power/currents"
    ),

    "Lifting": SkillInfo(
        name="Lifting",
        attribute="Strength",
        description="Lifting, carrying, moving heavy objects, breaking obstacles",
        use_cases=[
            "Breaking down doors",
            "Moving heavy obstacles",
            "Carrying wounded allies",
            "Forcing open jammed exits"
        ],
        category="Physical",
        note="Raw strength application"
    ),

    # ======================
    # ENDURANCE SKILLS (NEW)
    # ======================

    "Resistance": SkillInfo(
        name="Resistance",
        attribute="Endurance",
        description="Resisting toxins, disease, radiation, environmental hazards",
        use_cases=[
            "Poison resistance",
            "Disease immunity",
            "Radiation exposure",
            "Environmental extremes (heat, cold)"
        ],
        category="Survival",
        note="YAGS standard endurance skill"
    ),

    "Stamina": SkillInfo(
        name="Stamina",
        attribute="Endurance",
        description="Sustained physical effort, prolonged exertion, marathon endurance",
        use_cases=[
            "Prolonged combat (4+ rounds)",
            "Extended exertion",
            "Marathon activities",
            "Resisting fatigue"
        ],
        category="Physical",
        note="For extended effort; Athletics is for short bursts"
    ),

    "Running": SkillInfo(
        name="Running",
        attribute="Endurance",
        description="Cross-country running, long-distance pursuits, sustained flight",
        use_cases=[
            "Marathon running",
            "Long-distance chases",
            "Sustained fleeing",
            "Cross-country movement"
        ],
        category="Movement",
        note="Endurance running; Athletics is for sprints"
    ),

    # ======================
    # AEONISK-SPECIFIC SKILLS (NEW)
    # ======================

    "Insight": SkillInfo(
        name="Insight",
        attribute="Empathy",
        description="Reading people emotionally, understanding motivations, empathic perception",
        use_cases=[
            "Reading emotional states",
            "Understanding motivations",
            "Detecting lies emotionally (vs Guile analytically)",
            "Empathic perception"
        ],
        category="Social",
        note="Empathy-based; Investigation is Perception-based analytical"
    ),

    "Void Lore": SkillInfo(
        name="Void Lore",
        attribute="Intelligence",
        description="Knowledge of void phenomena, corruption mechanics, void entities",
        use_cases=[
            "Identifying void corruption",
            "Understanding void entities",
            "Void ritual knowledge",
            "Predicting void effects"
        ],
        category="Knowledge",
        note="Aeonisk-specific knowledge skill"
    ),

    "Hacking": SkillInfo(
        name="Hacking",
        attribute="Intelligence",
        description="Computer intrusion, network exploitation, security breaking",
        use_cases=[
            "Breaking into systems",
            "Exploiting security vulnerabilities",
            "Network infiltration",
            "Bypassing encryption"
        ],
        category="Technical",
        note="Intrusion skill; Systems is for operation/maintenance"
    ),

    "Tactics": SkillInfo(
        name="Tactics",
        attribute="Intelligence",
        description="Combat planning, strategic thinking, tactical analysis",
        use_cases=[
            "Planning combat strategies",
            "Analyzing enemy tactics",
            "Coordinating team actions",
            "Predicting opponent moves"
        ],
        category="Combat",
        note="Planning skill; Combat is execution skill"
    ),

    "Ritual Lore": SkillInfo(
        name="Ritual Lore",
        attribute="Intelligence",
        description="Knowledge of ritual mechanics, procedures, requirements",
        use_cases=[
            "Understanding ritual requirements",
            "Identifying ritual components",
            "Ritual theory knowledge",
            "Predicting ritual outcomes"
        ],
        category="Knowledge",
        note="Knowledge skill; Astral Arts is execution skill"
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

    "Magic Theory": SkillInfo(
        name="Magic Theory",
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

    "Attunement": SkillInfo(
        name="Attunement",
        attribute="Perception",
        description="Sensing void currents, energy resonance, spiritual patterns, reading auras",
        use_cases=["Detecting void anomalies", "Sensing energy flows", "Reading spiritual signatures", "Tracking resonance patterns"],
        category="Investigation",
        note="Aeonisk-specific - perceiving the spiritual/energetic layer of reality"
    ),

    "Intimidation": SkillInfo(
        name="Intimidation",
        attribute="Willpower",
        description="Threatening, coercing, dominating through force of will or implied violence",
        use_cases=["Extracting information", "Forcing compliance", "Breaking morale", "Establishing dominance"],
        category="Social",
        note="Uses Willpower (mental dominance) not Empathy. Can be backed by physical presence or reputation."
    ),

    "Investigation": SkillInfo(
        name="Investigation",
        attribute="Perception",
        description="Analytical investigation, deduction, forensics, piecing together clues",
        use_cases=["Crime scene analysis", "Following leads", "Deductive reasoning", "Forensic investigation"],
        category="Investigation",
        note="More analytical than Awareness (which is raw perception). Use for detective work and systematic investigation."
    ),

    "Discipline": SkillInfo(
        name="Discipline",
        attribute="Willpower",
        description="Mental fortitude, void resistance, grounding meditation, resisting corruption",
        use_cases=["Grounding meditation (-1 Void)", "Resisting void corruption", "Mental discipline", "Maintaining composure"],
        category="Ritual",
        note="Aeonisk-specific - essential for void recovery. Success on DC 20+ reduces void by 1."
    ),

    "Dreamwork": SkillInfo(
        name="Dreamwork",
        attribute="Willpower",
        description="Navigating dreamscapes, memory diving, oneiric manipulation, lucid dreaming",
        use_cases=["Memory extraction", "Dream navigation", "Oneiric rituals", "Shared dreamscapes"],
        category="Ritual",
        note="Aeonisk-specific - manipulating the dreamscape/memory layer"
    ),

    "Medicine": SkillInfo(
        name="Medicine",
        attribute="Intelligence",
        description="Medical diagnosis, treatment, surgery, biological sciences",
        use_cases=["Treating injuries", "Diagnosing illness", "Surgery", "Medical research"],
        category="Technical",
        note="More comprehensive than Healing - includes diagnosis and advanced procedures"
    ),

    "Combat": SkillInfo(
        name="Combat",
        attribute="Agility",
        description="Generic combat skill covering weapons and tactics (prefer Brawl/Melee/Guns for specificity)",
        use_cases=["Armed combat", "Tactical fighting", "Weapon handling", "Combat maneuvers"],
        category="Combat",
        note="Generic skill - prefer specific skills (Brawl, Melee, Guns) for better mechanical clarity"
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
