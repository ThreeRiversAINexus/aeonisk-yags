"""
Shared Pydantic types used across multiple schemas.

These models represent common game mechanics that appear in multiple contexts
(DM resolutions, player actions, enemy decisions, etc.).
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, List, Dict, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SuccessTier(str, Enum):
    """Action outcome tiers."""
    CRITICAL_FAILURE = "critical_failure"
    FAILURE = "failure"
    MARGINAL = "marginal"
    MODERATE = "moderate"
    GOOD = "good"
    EXCELLENT = "excellent"
    EXCEPTIONAL = "exceptional"


class ActionType(str, Enum):
    """Action categorization."""
    EXPLORE = "explore"
    INVESTIGATE = "investigate"
    RITUAL = "ritual"
    SOCIAL = "social"
    COMBAT = "combat"
    TECHNICAL = "technical"
    PERCEPTION = "perception"
    SUPPORT = "support"
    PURCHASE = "purchase"  # Vendor transactions (separate from social for ML training)
    TRANSFER = "transfer"  # Energy currency transfers between characters
    ATTUNE = "attune"  # Seed attunement rituals (separate from general RITUAL for ML training)
    CONSUME = "consume"  # Food/consumable usage for +2 HP healing (separate from SUPPORT for ML training)
    CUSTOM = "custom"


class Position(str, Enum):
    """
    Tactical positioning.

    Automatically normalizes Unicode hyphen variants (non-breaking hyphen U+2011, etc.)
    to regular ASCII hyphen (-) to handle LLM output variations.
    """
    ENGAGED = "Engaged"
    NEAR_PC = "Near-PC"
    NEAR_ENEMY = "Near-Enemy"
    FAR_PC = "Far-PC"
    FAR_ENEMY = "Far-Enemy"
    EXTREME_PC = "Extreme-PC"
    EXTREME_ENEMY = "Extreme-Enemy"

    @classmethod
    def _missing_(cls, value):
        """
        Normalize Unicode hyphen variants and handle invalid position values gracefully.

        OpenAI models sometimes generate non-breaking hyphens (U+2011 ‑) or other
        hyphen variants instead of regular ASCII hyphens (U+002D -), causing
        validation errors like:

        Input: "Near‑PC" (with U+2011 non-breaking hyphen)
        Expected: "Near-PC" (with U+002D ASCII hyphen)

        Also handles completely invalid values (like "cover") by logging a warning
        and returning None, which Pydantic will then handle as a validation error.

        This hook normalizes all hyphen-like characters to regular hyphens before lookup.
        """
        if isinstance(value, str):
            # Replace common hyphen variants with regular ASCII hyphen
            # U+2011: non-breaking hyphen ‑
            # U+2010: hyphen ‐
            # U+2012: figure dash ‒
            # U+2013: en dash –
            # U+2014: em dash —
            # U+2212: minus sign −
            normalized = value.replace('\u2011', '-')  # non-breaking hyphen
            normalized = normalized.replace('\u2010', '-')  # hyphen
            normalized = normalized.replace('\u2012', '-')  # figure dash
            normalized = normalized.replace('\u2013', '-')  # en dash
            normalized = normalized.replace('\u2014', '-')  # em dash
            normalized = normalized.replace('\u2212', '-')  # minus sign

            # Try direct member lookup with normalized value (avoid recursion)
            for member in cls:
                if member.value == normalized:
                    return member

            # Log warning for completely invalid values (not just hyphen issues)
            valid_values = [e.value for e in cls]
            logger.warning(
                f"Invalid Position value '{value}' (normalized: '{normalized}'). "
                f"Valid values: {valid_values}. This position_change will be skipped."
            )

        # Return None - Pydantic will raise a validation error
        return None


class VoidChange(BaseModel):
    """
    Void corruption change to a specific character (positive = corruption, negative = cleansing).

    **CRITICAL: This field must be populated when void-triggering events occur.**

    **When to populate void_changes:**
    - Ritual failures (missing offerings, missing tools, critical failure)
    - Void exposure (breaches, corrupted areas, cosmic horror encounters)
    - Corrupted technology interaction
    - Void manipulation without proper safeguards
    - Cleansing rituals (negative amounts)

    **When NOT to populate (leave empty list):**
    - Regular combat failures (shooting, melee)
    - Social failures (negotiation, intimidation)
    - Investigation failures (unless void-related)
    - Technical failures (unless corrupted tech)
    - Proper rituals with offerings consumed

    **Empty list means NO void changes occurred (explicit choice, not unspecified).**

    Examples:
    - VoidChange(character_name="Ash Vex", amount=2, reason="Failed ritual without offering")
    - VoidChange(character_name="Riven", amount=-3, reason="Powerful purification ritual")
    - VoidChange(character_name="Kade", amount=1, reason="Touched void breach without protection")

    IMPORTANT: character_name must be a specific player character name.
    For environmental/area void effects, use scene clocks instead of VoidChange.
    """
    character_name: str = Field(..., description="Name of specific character affected (NOT 'Environmental Void' or abstract targets - use scene clocks for those)")
    amount: int = Field(..., description="Void change: +X corruption, -X cleansing")
    reason: str = Field(..., min_length=5, description="Why this void change occurred")

    @field_validator('character_name')
    @classmethod
    def validate_not_environmental(cls, v: str) -> str:
        """Prevent environmental/abstract targets in character void changes."""
        environmental_keywords = ['environmental', 'environment', 'area', 'ambient', 'scene', 'location']
        v_lower = v.lower()

        if any(keyword in v_lower for keyword in environmental_keywords):
            raise ValueError(
                f"Invalid character name '{v}' - environmental void effects should be tracked "
                f"via scene clocks, not character void. Use specific character names only."
            )

        return v


class SoulcreditChange(BaseModel):
    """
    Soulcredit economy change - REQUIRED FOR EVERY SINGLE ACTION.

    Soulcredit tracks trustworthiness and moral choices. Even neutral actions
    must explicitly log amount=0 to show intentional moral assessment.

    Examples:
    - SoulcreditChange(character_name="Echo", amount=-2, reason="Created Hollow Seed")
    - SoulcreditChange(character_name="Thresh", amount=1, reason="Void creature defeated")
    - SoulcreditChange(character_name="Ash", amount=0, reason="Justified combat, morally neutral")
    - SoulcreditChange(character_name="Riven", amount=0, reason="Normal investigation, no moral choice")
    """
    character_name: str = Field(..., description="Name of character affected")
    amount: int = Field(..., description="Soulcredit change: +X gain, -X cost, or 0 for neutral")
    reason: str = Field(..., min_length=5, description="Why this change occurred (even if +0)")


class ClockUpdate(BaseModel):
    """
    Progress clock advancement/regression.

    Examples:
    - ClockUpdate(clock_name="Enemy Reinforcements", ticks=2, reason="Alarm triggered")
    - ClockUpdate(clock_name="Passenger Safety", ticks=-1, reason="Evacuation successful")
    """
    clock_name: str = Field(..., description="Exact name of clock to update")
    ticks: int = Field(..., description="Ticks to add (+) or regress (-)")
    reason: str = Field(..., min_length=5, description="Why this clock changed")


class RollModifier(BaseModel):
    """
    Individual modifier applied to a roll.

    Tracks the source and value of each modifier that affected a roll's total,
    enabling ML training data analysis of penalty/bonus effects.

    Examples:
    - RollModifier(source="void_penalty", value=-2, details={"void_level": 2})
    - RollModifier(source="condition", value=-3, details={"name": "Stunned"})
    - RollModifier(source="altar_bonus", value=3, details={"altar_id": "alt_sanctified"})
    - RollModifier(source="no_offering", value=-2)
    """
    source: str = Field(..., description="Modifier source: void_penalty, condition, altar_bonus, no_offering, situational, etc.")
    value: int = Field(..., description="Modifier value: positive=bonus, negative=penalty")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional context: void_level, condition_name, altar_id, etc.")


class Condition(BaseModel):
    """
    Status effect or condition applied to character.

    IMPORTANT: Always specify the penalty value explicitly!
    - Negative penalties are DEBUFFS (e.g., penalty=-3 for Stunned = -3 to rolls)
    - Positive penalties are BUFFS (e.g., penalty=2 for Inspired = +2 to rolls)
    - Use penalty=0 ONLY for purely narrative conditions with no mechanical effect

    TARGET FIELD (Optional):
    - If omitted: Condition applies to the acting character (self-buff/debuff)
    - If specified: Condition applies to the target (e.g., enemy you intimidated)
    - For multi-target actions: Create multiple Condition entries, one per target

    PROTECTION_AMOUNT (Optional - for barriers/shields):
    - If specified: Condition acts as damage-absorbing barrier
    - Value = damage absorption capacity (depletes as damage is blocked)
    - When protection_amount reaches 0, barrier is removed
    - Typically used with penalty=0 (barriers don't modify rolls, they absorb damage)

    Examples:
    - Condition(name="Stunned", penalty=-3, duration=2, description="Cannot act next round, -3 to all rolls")
    - Condition(name="Inspired", penalty=2, duration=3, description="+2 to all rolls for 3 rounds")
    - Condition(name="Wavering", target="tgt_abc1", penalty=-2, duration=1, description="Hesitant after intimidation")
    - Condition(name="Astral Barrier", target="tgt_7a3f", penalty=0, duration=2, description="Blocks 10 damage", protection_amount=10)
    - Multi-target: [Condition(target="tgt_abc1", ...), Condition(target="tgt_def2", ...), Condition(target="tgt_ghi3", ...)]
    """
    name: str = Field(..., description="Condition name (e.g., Stunned, Prone, Inspired, Astral Barrier)")
    penalty: int = Field(..., description="REQUIRED: Penalty/bonus to rolls. Negative = debuff (e.g., -3), positive = buff (e.g., +2), 0 = narrative only or protection barrier")
    duration: int = Field(default=1, ge=0, description="Rounds this condition lasts (0 = instant/already applied, 1+ = lasts that many rounds)")
    description: str = Field(..., min_length=5, description="What this condition does")
    target: Optional[str] = Field(default=None, description="Who receives the condition. If omitted, applies to actor. For multi-target actions, create multiple Condition entries.")
    protection_amount: Optional[int] = Field(default=None, ge=0, description="Damage absorption capacity for barriers/shields. If present, this condition blocks incoming damage up to this amount. Depletes as damage is absorbed. Use with penalty=0.")

    @field_validator('target')
    @classmethod
    def validate_single_target(cls, v: Optional[str]) -> Optional[str]:
        """Reject multi-target syntax (semicolons/commas) - create multiple Condition entries instead."""
        if v and (';' in v or ',' in v):
            raise ValueError(
                f"Invalid target format: '{v}'. "
                f"Condition.target must specify a SINGLE target. "
                f"For multi-target conditions, create multiple Condition entries (one per target). "
                f"Example: [Condition(target='tgt_abc1', ...), Condition(target='tgt_def2', ...)]"
            )
        return v


class DamageEffect(BaseModel):
    """
    Damage dealt to a target.

    For enemy → player attacks: Full breakdown with soak.
    For player → enemy attacks: Simplified (DM infers enemy soak).

    Examples:
    - DamageEffect(target="Thresh Ireveth", base_damage=14, soak=10, dealt=4)
    - DamageEffect(target="tgt_7a3f", base_damage=12, dealt=12)  # Enemy (soak unknown)
    """
    target: str = Field(..., description="Target character name or target ID (tgt_xxxx format: tgt_ followed by exactly 4 lowercase alphanumeric characters)")
    base_damage: int = Field(..., ge=0, description="Damage before soak")
    soak: Optional[int] = Field(default=None, ge=0, description="Damage soaked (if known)")
    dealt: int = Field(..., ge=0, description="Final damage dealt after soak")
    damage_type: Optional[str] = Field(
        default=None,
        description=(
            "YAGS damage type: 'stun' (non-lethal knockout), "
            "'wound' (lethal, HP loss + wounds), or 'mixed' (split stun/wound). "
            "Must match the weapon's damage type from WEAPON CONTEXT."
        )
    )

    @field_validator('target')
    @classmethod
    def validate_target_id_format(cls, v: str) -> str:
        """Validate target ID format in free targeting mode."""
        # If target starts with tgt_, enforce proper format
        if v.startswith('tgt_'):
            import re
            # Pattern: tgt_ followed by exactly 4 lowercase alphanumeric chars
            if not re.match(r'^tgt_[a-z0-9]{4}$', v):
                raise ValueError(
                    f"Invalid target ID format: '{v}'. "
                    f"Target IDs must be 'tgt_' followed by exactly 4 lowercase alphanumeric characters (e.g., 'tgt_7a3f'). "
                    f"Do NOT use enemy names like 'tgt_heavy_gunners' - use the assigned ID from the combatant list instead."
                )
        return v


class PositionChange(BaseModel):
    """
    Character movement to new tactical position.

    Examples:
    - PositionChange(character_name="Ash Vex", new_position="Near-PC", reason="Rushed forward")
    """
    character_name: str = Field(..., description="Character that moved")
    new_position: Position = Field(..., description="New tactical position")
    reason: str = Field(..., min_length=5, description="Why/how they moved")


class BondType(str, Enum):
    """
    Bond types in Aeonisk (formal metaphysical connections between sapient beings).

    From YAGS Module v1.2.2 Section 8.1-8.4:
    - Kinship: Ancestral/chosen family bonds (e.g., Matron bonds, siblings)
    - Ascendancy: Subordination to higher Will (mentor, master, deity)
    - Debt: Spiritual/material obligation (often ACG-brokered)
    - Voidward: Alignment with Void forces (Tempest entities, Dissolution theorists)
    - Passion: Emotional/creative entanglement (lovers, rivals, artistic collaborators)
    - Faction: Formal allegiance to institution (Pantheon, ACG, Freeborn collective)
    """
    KINSHIP = "kinship"
    ASCENDANCY = "ascendancy"
    DEBT = "debt"
    VOIDWARD = "voidward"
    PASSION = "passion"
    FACTION = "faction"


class BondStatus(str, Enum):
    """
    Bond status states.

    - ACTIVE: Full mechanical benefits (+2 ritual bonus, +1 Soak defending, sacrifice available)
    - DORMANT: Strained or Void ≥ 7, no bonuses (can be restored)
    - SEVERED: Broken (costs -2 Soulcredit, narrative crisis)
    - VOID_LOCKED: Void = 10, potentially corrupted/twisted by Void
    """
    ACTIVE = "active"
    DORMANT = "dormant"
    SEVERED = "severed"
    VOID_LOCKED = "void_locked"


class BondTargetType(str, Enum):
    """
    Type of entity the bond is formed with.

    - CHARACTER: Standard character-character bond (default, 99% of bonds)
    - OBJECT: Rare/taboo bond with object (e.g., sanitation automata, relics)
    - ENTITY: Rare bond with non-character sapient (AI overseer, Tempest entity, spirit)

    Note: "Bonded weapons" (attuned gear) are NOT Bonds (capital B). They are
    separate attunement mechanics that don't count toward the 3-Bond limit.
    """
    CHARACTER = "character"
    OBJECT = "object"
    ENTITY = "entity"


class Bond(BaseModel):
    """
    Formal metaphysical connection between two beings (or rarely, being and object).

    Bonds are witnessed, recorded in the Codex, and provide mechanical benefits:
    - +2 bonus to Ritual Rolls when performing rituals together
    - +1 Soak when defending a Bonded partner from attacks
    - Can sacrifice Bond once/session for +5 to Willpower roll (costs: +1 Void, +1 Soul Debt, -1 Empathy for scene)

    Formation requirements:
    - Intimacy Ritual skill check (Empathy × Intimacy Ritual + d20)
    - Must be witnessed by at least one other character (standard practice)
    - Registered in the Codex (Sovereign Nexus metaphysical ledger)
    - Both participants must have Void < 7

    Limits:
    - Maximum 3 Bonds per character
    - Freeborn origin: Maximum 1 Bond only
    - Cannot form new Bonds if Void ≥ 7 (existing Bonds become Dormant)

    Examples:
    - Bond(bond_id="bond_001", character_a="Sera Karsel", character_b="Thane Vael", bond_type=BondType.KINSHIP, status=BondStatus.ACTIVE, formed_round=0, witnessed_by=["Kael Rift"])
    - Bond(bond_id="bond_002", character_a="Kaelen", character_b="Sanitation Automata Unit-7", bond_type=BondType.PASSION, status=BondStatus.ACTIVE, formed_round=1, witnessed_by=[], bond_target_type=BondTargetType.OBJECT, codex_registered=False)
    """
    bond_id: str = Field(..., description="Unique bond identifier (e.g., 'bond_001', 'bond_matron_sera_thane')")
    character_a: str = Field(..., description="First participant in the bond (character name)")
    character_b: str = Field(..., description="Second participant in the bond (character name or object/entity description)")
    bond_type: BondType = Field(..., description="Type of bond (Kinship, Ascendancy, Debt, Voidward, Passion, Faction)")
    status: BondStatus = Field(..., description="Current status (Active, Dormant, Severed, Void-Locked)")
    formed_round: int = Field(..., ge=0, description="Round when bond was formed (0 for pre-story bonds)")
    witnessed_by: List[str] = Field(..., description="Characters who witnessed the bond formation (can be empty for taboo bonds)")
    bond_target_type: BondTargetType = Field(default=BondTargetType.CHARACTER, description="What kind of entity is character_b (character/object/entity)")
    codex_registered: bool = Field(default=True, description="Whether bond is officially registered in the Codex (false for taboo bonds)")
    narrative_description: str = Field(default="", description="How the bond was formed, emotional context, oath spoken (generated by LLM for pre-story bonds)")


class StealthChange(BaseModel):
    """
    Change to an agent's stealth state (Spec 05).

    Used in MechanicalEffects.stealth_changes to track when agents hide or are detected.
    The DM sets is_hidden via this structured output field during action resolution.

    Examples:
    - StealthChange(agent_id="player_01", is_hidden=True, stealth_dc=22, reason="Successfully ghosted through shadows behind cargo")
    - StealthChange(agent_id="enemy_grunt_01", is_hidden=False, stealth_dc=None, reason="Detected by Scan action from allied forces")
    """
    agent_id: str = Field(
        ...,
        description="Agent whose stealth state changes"
    )
    is_hidden: bool = Field(
        ...,
        description="True = agent is now hidden; False = agent revealed"
    )
    stealth_dc: Optional[int] = Field(
        default=None,
        description="DC to detect this agent (set by stealth check result, None when revealed)"
    )
    reason: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Why stealth state changed (e.g., 'Slipped into shadows while guards distracted')"
    )
