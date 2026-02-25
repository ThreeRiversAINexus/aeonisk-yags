"""
Player Action Declaration Schema (Two-Phase Architecture)

Phase 1: ActionIntent - Lightweight action type selection
Phase 2: Action-Specific Schemas - Discriminated union with required fields per action type

This architecture solves the problem of optional fields that are "required for specific actions":
- Old: Single PlayerAction with 20+ optional fields (sparse data)
- New: 12 specialized schemas with truly required fields (dense data)

Benefits:
- Type safety: Cannot create invalid combinations (e.g., COMBAT action with vendor_id)
- Better ML training data: No null fields for action-specific requirements
- Clearer validation: Required fields enforced at schema level, not model validators
- Token efficiency: Phase 1 prompt is lightweight, Phase 2 loads only relevant guidance
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Dict, Literal, Union, Annotated
from .shared_types import ActionType, Position
from ..constants import YAGS_ATTRIBUTES, ATTRIBUTES_STRING


# ==============================================================================
# PHASE 1: ACTION INTENT (Lightweight LLM call for action type selection)
# ==============================================================================

class ActionIntent(BaseModel):
    """
    Phase 1 output: Action type selection with minimal narrative intent.

    Used by lightweight LLM prompt to select which action type the character
    wants to perform. The action_type then routes to the appropriate
    action-specific prompt and schema for Phase 2.

    Example:
    ```python
    intent = ActionIntent(
        intent="Scan void corruption patterns on terminal",
        action_type=ActionType.TECHNICAL,
        reasoning="Technical skills best suited for analyzing anomalous data"
    )
    ```
    """

    intent: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Clear, concise description of what you're doing (10-200 chars)"
    )

    action_type: ActionType = Field(
        ...,
        description="Action category that best fits your intent"
    )

    reasoning: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Why you chose this action type (for ML training)"
    )

    @field_validator('action_type', mode='before')
    @classmethod
    def normalize_action_type_case(cls, v):
        """Normalize action_type to lowercase (OpenAI sometimes returns uppercase)."""
        if isinstance(v, str):
            return v.lower()
        return v


# ==============================================================================
# BASE SCHEMA (Shared fields across all action-specific schemas)
# ==============================================================================

class PlayerActionBase(BaseModel):
    """
    Base schema with fields shared across all action types.

    All action-specific schemas (ExploreAction, CombatAction, etc.) inherit
    from this base and add their action-specific required fields.

    Shared fields:
    - Core: intent, description, attribute, skill, difficulty
    - System: character_name, agent_id (populated after LLM generation)
    - ML: reasoning (optional, for ML training)
    """

    # Core action definition
    intent: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Clear, concise description of what you're doing (10-200 chars)"
    )

    description: str = Field(
        ...,
        min_length=50,
        max_length=800,
        description="1-3 sentence narrative description with context (50-800 chars)"
    )

    # Mechanical components
    attribute: str = Field(
        ...,
        description=f"Attribute used: {ATTRIBUTES_STRING}"
    )

    skill: Optional[str] = Field(
        default=None,
        description="Skill used (or None for raw attribute check, -5 unskilled penalty)"
    )

    difficulty_estimate: int = Field(
        ...,
        ge=5,
        le=50,
        description="Estimated target DC: 10=Easy, 15=Moderate, 20=Challenging, 25=Hard, 30+=Very Hard"
    )

    difficulty_justification: str = Field(
        ...,
        min_length=10,
        max_length=300,
        description="Why you chose this difficulty estimate (10-300 chars)"
    )

    # Character identification (populated by system after LLM generation)
    character_name: Optional[str] = Field(
        default=None,
        description="Full character name (populated by system)",
        json_schema_extra={"exclude_from_llm": True}
    )

    agent_id: Optional[str] = Field(
        default=None,
        description="Agent identifier (populated by system)",
        json_schema_extra={"exclude_from_llm": True}
    )

    # Metadata
    reasoning: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Internal reasoning for this action choice (for ML training)"
    )

    # Tactical positioning (defence token)
    defence_token: Optional[str] = Field(
        default=None,
        description=(
            "COMBAT ONLY: Target ID (tgt_xxxx) of the combatant you are watching. "
            "That combatant gets -2 to attack you; all others get +2 flanking. "
            "Choose the biggest threat. Leave null for non-combat situations."
        )
    )

    @field_validator('attribute')
    @classmethod
    def validate_attribute(cls, v: str) -> str:
        """Validate attribute is one of the canonical 8."""
        valid_attributes = set(YAGS_ATTRIBUTES)
        if v not in valid_attributes:
            raise ValueError(
                f"Attribute must be one of: {', '.join(sorted(valid_attributes))}"
            )
        return v

    @field_validator('skill')
    @classmethod
    def validate_skill(cls, v: Optional[str]) -> Optional[str]:
        """Allow None or normalize skill name."""
        if v is None or v.lower() == 'none':
            return None
        return v


# ==============================================================================
# PHASE 2: ACTION-SPECIFIC SCHEMAS (Discriminated Union)
# ==============================================================================

class ExploreAction(PlayerActionBase):
    """
    EXPLORE action: Movement and environmental navigation.

    Optional fields:
    - target_position: Desired tactical position after movement

    Example:
    ```python
    action = ExploreAction(
        intent="Search northwest corridor for exit",
        description="Moving carefully through darkened hallway, checking for corruption.",
        attribute="Perception",
        skill="Investigation",
        difficulty_estimate=15,
        difficulty_justification="Poor lighting but straightforward",
        action_type=ActionType.EXPLORE,
        target_position=Position.NEAR_PC
    )
    ```
    """

    action_type: Literal[ActionType.EXPLORE] = ActionType.EXPLORE

    target_position: Optional[Position] = Field(
        default=None,
        description="Desired tactical position after movement (if applicable)"
    )


class InvestigateAction(PlayerActionBase):
    """
    INVESTIGATE action: Examining objects, gathering information.

    Optional fields:
    - target: Object or entity being investigated (tgt_xxxx or name)
    - target_position: Movement during investigation

    Example:
    ```python
    action = InvestigateAction(
        intent="Analyze void corruption terminal",
        description="Using technical knowledge to examine corrupted data logs.",
        attribute="Intelligence",
        skill="Systems",
        difficulty_estimate=22,
        difficulty_justification="Complex technical analysis under pressure",
        action_type=ActionType.INVESTIGATE,
        target="tgt_terminal_01"
    )
    ```
    """

    action_type: Literal[ActionType.INVESTIGATE] = ActionType.INVESTIGATE

    target: Optional[str] = Field(
        default=None,
        description="Target ID (tgt_xxxx) or entity name for investigation"
    )

    target_position: Optional[Position] = Field(
        default=None,
        description="Movement during investigation (if applicable)"
    )


class RitualAction(PlayerActionBase):
    """
    RITUAL action: Magical rituals and astral arts.

    Required fields:
    - is_ritual: Must be True (distinguishes from other action types)

    Optional fields:
    - has_primary_tool: Whether you have the required ritual focus
    - has_offering: Whether you're using offerings (reduces void risk)
    - offering_type: Specific offering type (blood, incense, crystals)
    - ritual_components: Description of materials used

    Example:
    ```python
    action = RitualAction(
        intent="Perform void cleansing ritual",
        description="Drawing protective circle with incense, invoking cleansing mantras.",
        attribute="Willpower",
        skill="Astral Arts",
        difficulty_estimate=25,
        difficulty_justification="High-power ritual in corrupted zone",
        action_type=ActionType.RITUAL,
        is_ritual=True,
        has_primary_tool=True,
        has_offering=True,
        offering_type="incense",
        ritual_components="Incense, blessed salt, protective circle"
    )
    ```
    """

    action_type: Literal[ActionType.RITUAL] = ActionType.RITUAL

    is_ritual: Literal[True] = Field(
        default=True,
        description="Must be True for ritual actions"
    )

    has_primary_tool: bool = Field(
        default=False,
        description="Do you have the required ritual focus/tool?"
    )

    has_offering: bool = Field(
        default=False,
        description="Using offering (incense, blood, crystals)? Reduces void risk, consumed."
    )

    offering_type: Optional[Literal["blood_offering", "incense", "crystals"]] = Field(
        default=None,
        description="If has_offering=True, specify which offering. Auto-selected if not specified."
    )

    ritual_components: Optional[str] = Field(
        default=None,
        max_length=200,
        description="What materials/components are you using?"
    )

    bond_formation_target: Optional[str] = Field(
        default=None,
        description="If this ritual is for bond formation, specify the target character name or object. Used for Intimacy Ritual bond formation."
    )


class SocialAction(PlayerActionBase):
    """
    SOCIAL action: Diplomacy, intimidation, deception, persuasion.

    Optional fields:
    - target: Character being targeted (for single-target social actions)

    Example:
    ```python
    action = SocialAction(
        intent="Negotiate with gang leader",
        description="Using diplomatic skills to de-escalate confrontation.",
        attribute="Empathy",
        skill="Diplomacy",
        difficulty_estimate=20,
        difficulty_justification="Hostile faction, tense situation",
        action_type=ActionType.SOCIAL,
        target="tgt_gang_leader"
    )
    ```
    """

    action_type: Literal[ActionType.SOCIAL] = ActionType.SOCIAL

    target: Optional[str] = Field(
        default=None,
        description="Target character (if directed at specific individual)"
    )


class CombatAction(PlayerActionBase):
    """
    COMBAT action: Attacks, defensive maneuvers, tactical combat.

    Required fields:
    - target: Enemy or entity being attacked (tgt_xxxx or name)

    Optional fields:
    - target_position: Tactical movement during combat
    - situational_modifiers: Bonuses/penalties (e.g., high_ground: 2)

    Example:
    ```python
    action = CombatAction(
        intent="Fire plasma rifle at enemy commander",
        description="Taking careful aim at enemy leader's center mass.",
        attribute="Agility",
        skill="Firearms",
        difficulty_estimate=18,
        difficulty_justification="Moving target with partial cover",
        action_type=ActionType.COMBAT,
        target="tgt_enemy_01",
        target_position=Position.NEAR_ENEMY,
        situational_modifiers={"high_ground": 2}
    )
    ```
    """

    action_type: Literal[ActionType.COMBAT] = ActionType.COMBAT

    target: str = Field(
        ...,
        description="REQUIRED: Target ID (tgt_xxxx) or character name for attack"
    )

    target_position: Optional[Position] = Field(
        default=None,
        description="Desired tactical position after action"
    )

    situational_modifiers: Dict[str, int] = Field(
        default_factory=dict,
        description="Situational bonuses/penalties (e.g., {'high_ground': 2, 'darkness': -3})"
    )


class TechnicalAction(PlayerActionBase):
    """
    TECHNICAL action: Hacking, systems manipulation, engineering.

    Optional fields:
    - target: Device or system being manipulated
    - target_position: Movement during technical work

    Example:
    ```python
    action = TechnicalAction(
        intent="Hack security terminal",
        description="Bypassing security protocols using neural interface.",
        attribute="Intelligence",
        skill="Systems",
        difficulty_estimate=22,
        difficulty_justification="Advanced security, time pressure",
        action_type=ActionType.TECHNICAL,
        target="tgt_security_terminal"
    )
    ```
    """

    action_type: Literal[ActionType.TECHNICAL] = ActionType.TECHNICAL

    target: Optional[str] = Field(
        default=None,
        description="Device or system being manipulated (if applicable)"
    )

    target_position: Optional[Position] = Field(
        default=None,
        description="Movement during technical work (if applicable)"
    )


class PerceptionAction(PlayerActionBase):
    """
    PERCEPTION action: Awareness checks, detecting hidden threats.

    No action-specific required fields beyond base schema.

    Example:
    ```python
    action = PerceptionAction(
        intent="Scan area for hidden threats",
        description="Using enhanced senses to detect concealed enemies.",
        attribute="Perception",
        skill="Awareness",
        difficulty_estimate=18,
        difficulty_justification="Poor visibility, active concealment",
        action_type=ActionType.PERCEPTION
    )
    ```
    """

    action_type: Literal[ActionType.PERCEPTION] = ActionType.PERCEPTION

    search_for_hidden: bool = Field(
        default=False,
        description="True if actively searching for hidden agents (triggers opposed "
                    "Perception x Awareness check vs hidden targets' stealth_dc)"
    )


class SupportAction(PlayerActionBase):
    """
    SUPPORT action: Healing, coordination, assistance to allies.

    Required fields:
    - target: Ally being supported (character name or agent_id)

    Optional fields:
    - target_position: Tactical movement to support position

    Example (Tactical Coordination):
    ```python
    action = SupportAction(
        intent="Coordinate tactical advance for Thresh",
        description="I call out enemy positions and timing to Thresh, watching for openings in their fire patterns and directing their movement to safer cover positions.",
        attribute="Perception",
        skill="Combat",
        difficulty_estimate=14,
        difficulty_justification="DC 14: Standard tactical coordination, clear sightlines but multiple enemies to track",
        action_type=ActionType.SUPPORT,
        target="Thresh Ireveth"
    )
    ```

    NOTE: Direct suppressing fire (laying down fire on enemy positions) should use
    CombatAction with target=enemy, not SupportAction. See player_action_combat.yaml
    for suppressing fire examples.
    """

    action_type: Literal[ActionType.SUPPORT] = ActionType.SUPPORT

    target: str = Field(
        ...,
        description="REQUIRED: Ally character name or agent_id being supported"
    )

    target_position: Optional[Position] = Field(
        default=None,
        description="Tactical movement to support position (if applicable)"
    )


class PurchaseAction(PlayerActionBase):
    """
    PURCHASE action: Vendor transactions, buying items/energy.

    Required fields:
    - vendor_id: Vendor identifier (vnd_xxxx)
    - item_id: Item identifier (itm_xxxx)

    Example:
    ```python
    action = PurchaseAction(
        intent="Buy Incense from marketplace vendor",
        description="Approaching vendor stall and negotiating for ritual incense.",
        attribute="Empathy",
        skill="Charm",
        difficulty_estimate=12,
        difficulty_justification="Routine transaction at established market",
        action_type=ActionType.PURCHASE,
        vendor_id="vnd_marketplace_01",
        item_id="itm_incense"
    )
    ```
    """

    action_type: Literal[ActionType.PURCHASE] = ActionType.PURCHASE

    vendor_id: str = Field(
        ...,
        description="REQUIRED: Vendor ID (vnd_xxxx) for purchase"
    )

    item_id: str = Field(
        ...,
        description="REQUIRED: Item ID (itm_xxxx) being purchased"
    )


class TransferAction(PlayerActionBase):
    """
    TRANSFER action: Transferring energy currency or items between characters.

    Required fields:
    - transfer_target: Character receiving transfer (name or agent_id)

    Optional fields (at least one required):
    - transfer_currency: Energy amounts (e.g., {"drip": 5, "spark": 2})
    - transfer_items: Item amounts (e.g., {"Incense": 2, "Crystals": 1})

    Example:
    ```python
    action = TransferAction(
        intent="Transfer 5 drip to Thresh",
        description="Handing over 5 drip energy tokens to Thresh for rituals.",
        attribute="Empathy",
        skill=None,
        difficulty_estimate=10,
        difficulty_justification="Simple friendly transfer",
        action_type=ActionType.TRANSFER,
        transfer_target="Thresh Ireveth",
        transfer_currency={"drip": 5}
    )
    ```
    """

    action_type: Literal[ActionType.TRANSFER] = ActionType.TRANSFER

    transfer_target: str = Field(
        ...,
        description="REQUIRED: Character name or agent_id to transfer to"
    )

    transfer_currency: Optional[Dict[str, int]] = Field(
        default=None,
        description="Currency amounts to transfer (e.g., {'drip': 5, 'spark': 2})"
    )

    transfer_items: Optional[Dict[str, int]] = Field(
        default=None,
        description="Item amounts to transfer (e.g., {'Incense': 2})"
    )

    @model_validator(mode='after')
    def validate_transfer_contents(self) -> 'TransferAction':
        """At least one of transfer_currency or transfer_items must be provided."""
        if not self.transfer_currency and not self.transfer_items:
            raise ValueError(
                "At least one of transfer_currency or transfer_items must be provided for TRANSFER actions"
            )
        return self


class AttuneAction(PlayerActionBase):
    """
    ATTUNE action: Seed attunement rituals to create energy currency.

    Required fields:
    - target_energy: Energy type (breath, grain, drip, spark)

    Optional fields:
    - altar_id: Altar identifier (alt_xxxx) for bonus (+1 to DC reduction)
    - use_echo_calibrator: Using portable Echo-Calibrator instead of altar

    Example:
    ```python
    action = AttuneAction(
        intent="Attune Raw Seed to Drip at basic altar",
        description="Placing Raw Seed on altar, focusing willpower to channel drip energy.",
        attribute="Willpower",
        skill="Attunement",
        difficulty_estimate=19,
        difficulty_justification="DC 20 base reduced to 19 with altar bonus",
        action_type=ActionType.ATTUNE,
        target_energy="drip",
        altar_id="alt_marketplace_01",
        use_echo_calibrator=False
    )
    ```
    """

    action_type: Literal[ActionType.ATTUNE] = ActionType.ATTUNE

    target_energy: Literal["breath", "grain", "drip", "spark"] = Field(
        ...,
        description="REQUIRED: Target energy type (breath, grain, drip, or spark)"
    )

    altar_id: Optional[str] = Field(
        default=None,
        description="Altar ID (alt_xxxx) for attunement bonus (if using altar)"
    )

    use_echo_calibrator: bool = Field(
        default=False,
        description="Use Echo-Calibrator for portable attunement (no altar needed)"
    )


class ConsumeAction(PlayerActionBase):
    """
    CONSUME action: Eating food or using consumables for +2 HP healing.

    Required fields:
    - item_id: Item identifier (itm_xxxx) being consumed

    Food items grant fixed +2 HP healing when consumed.
    Only items with item_type="food" can be consumed via this action.

    Example:
    ```python
    action = ConsumeAction(
        intent="Eat Ration Pack to recover health",
        description="Taking a quick break to eat field rations and restore energy.",
        attribute="Endurance",
        skill=None,  # Eating typically doesn't require a skill check
        difficulty_estimate=10,
        difficulty_justification="Simple consumption, no complications expected",
        action_type=ActionType.CONSUME,
        item_id="itm_ration_pack_01"
    )
    ```

    Note: Unlike SUPPORT actions (which heal variable amounts based on Medicine checks),
    CONSUME actions provide fixed +2 HP and remove the food item from inventory.
    """

    action_type: Literal[ActionType.CONSUME] = ActionType.CONSUME

    item_id: str = Field(
        ...,
        description="REQUIRED: Item ID (itm_xxxx) being consumed. Must be a food item (item_type='food')."
    )


class CustomAction(PlayerActionBase):
    """
    CUSTOM action: Unique, improvised actions that don't fit other categories.

    No action-specific required fields beyond base schema.

    Example:
    ```python
    action = CustomAction(
        intent="Improvise unique solution to unstable reactor",
        description="Using creative thinking to solve problem in unexpected way.",
        attribute="Intelligence",
        skill=None,
        difficulty_estimate=20,
        difficulty_justification="Novel approach, uncertain outcome",
        action_type=ActionType.CUSTOM
    )
    ```
    """

    action_type: Literal[ActionType.CUSTOM] = ActionType.CUSTOM


# ==============================================================================
# DISCRIMINATED UNION (Routes to correct schema based on action_type)
# ==============================================================================

PlayerActionDetails = Annotated[
    Union[
        ExploreAction,
        InvestigateAction,
        RitualAction,
        SocialAction,
        CombatAction,
        TechnicalAction,
        PerceptionAction,
        SupportAction,
        PurchaseAction,
        TransferAction,
        AttuneAction,
        ConsumeAction,
        CustomAction,
    ],
    Field(discriminator='action_type')
]
"""
Discriminated union that automatically routes to the correct action schema
based on the action_type field.

When parsing JSON/dict with action_type='attune', Pydantic will automatically
instantiate AttuneAction and enforce its required fields (target_energy).

Example:
```python
data = {
    "intent": "Attune Raw Seed to Drip",
    "description": "Using altar to channel drip energy...",
    "attribute": "Willpower",
    "skill": "Attunement",
    "difficulty_estimate": 19,
    "difficulty_justification": "Altar reduces DC",
    "action_type": "attune",  # ← Routes to AttuneAction
    "target_energy": "drip"   # ← Required by AttuneAction
}

action = PlayerActionDetails(**data)  # Returns AttuneAction instance
assert isinstance(action, AttuneAction)
assert action.target_energy == "drip"
```
"""


# ==============================================================================
# SCHEMA ROUTING MAP (For programmatic routing in player agent)
# ==============================================================================

ACTION_TYPE_SCHEMA_MAP = {
    ActionType.EXPLORE: ExploreAction,
    ActionType.INVESTIGATE: InvestigateAction,
    ActionType.RITUAL: RitualAction,
    ActionType.SOCIAL: SocialAction,
    ActionType.COMBAT: CombatAction,
    ActionType.TECHNICAL: TechnicalAction,
    ActionType.PERCEPTION: PerceptionAction,
    ActionType.SUPPORT: SupportAction,
    ActionType.PURCHASE: PurchaseAction,
    ActionType.TRANSFER: TransferAction,
    ActionType.ATTUNE: AttuneAction,
    ActionType.CONSUME: ConsumeAction,
    ActionType.CUSTOM: CustomAction,
}
"""
Map from ActionType enum to corresponding schema class.

Used by player agent to programmatically select the correct schema
for Phase 2 structured output based on Phase 1 action_type result.

Example:
```python
# Phase 1 result
intent = ActionIntent(
    intent="Attune Raw Seed to Drip",
    action_type=ActionType.ATTUNE,
    reasoning="Need drip energy for ritual"
)

# Phase 2: Route to correct schema
schema_class = ACTION_TYPE_SCHEMA_MAP[intent.action_type]
assert schema_class == AttuneAction

# Generate Phase 2 structured output
result = await llm.generate_structured(
    result_type=schema_class,
    prompt=action_specific_prompt
)
```
"""


# ==============================================================================
# LEGACY COMPATIBILITY (Old PlayerAction schema for backward compatibility)
# ==============================================================================

class PlayerAction(BaseModel):
    """
    LEGACY: Original monolithic PlayerAction schema.

    **DEPRECATED:** Use two-phase ActionIntent → PlayerActionDetails instead.

    This schema is maintained for backward compatibility with:
    - Existing test fixtures
    - Session replay functionality
    - Any code that hasn't been migrated to two-phase architecture

    New code should use:
    1. Phase 1: ActionIntent (lightweight action type selection)
    2. Phase 2: PlayerActionDetails (discriminated union → action-specific schema)
    """

    # Core action definition
    intent: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Clear, concise description of what you're doing (10-200 chars)"
    )

    description: str = Field(
        ...,
        min_length=50,
        max_length=800,
        description="1-3 sentence narrative description with context (50-800 chars)"
    )

    # Mechanical components
    attribute: str = Field(
        ...,
        description=f"Attribute used: {ATTRIBUTES_STRING}"
    )

    skill: Optional[str] = Field(
        default=None,
        description="Skill used (or None for raw attribute check). Agent chooses skill explicitly - no automatic routing."
    )

    difficulty_estimate: int = Field(
        ...,
        ge=5,
        le=50,
        description="Estimated target DC: 10=Easy, 15=Moderate, 20=Challenging, 25=Hard, 30+=Very Hard"
    )

    difficulty_justification: str = Field(
        ...,
        min_length=10,
        max_length=300,
        description="Why you chose this difficulty estimate (10-300 chars)"
    )

    # Action categorization
    action_type: ActionType = Field(
        ...,
        description="Action category for context"
    )

    # Character identification (populated by system after LLM generation, not by LLM)
    character_name: Optional[str] = Field(
        default=None,
        description="Full character name (populated by system)",
        json_schema_extra={"exclude_from_llm": True}
    )

    agent_id: Optional[str] = Field(
        default=None,
        description="Agent identifier (populated by system)",
        json_schema_extra={"exclude_from_llm": True}
    )

    # Tactical components (optional)
    target_position: Optional[Position] = Field(
        default=None,
        description="Desired tactical position after movement (if applicable)"
    )

    target: Optional[str] = Field(
        default=None,
        description="Target ID (tgt_xxxx) or character name for targeted actions"
    )

    # Purchase-specific fields (optional)
    vendor_id: Optional[str] = Field(
        default=None,
        description="Vendor ID (vnd_xxxx) for purchase actions"
    )

    item_id: Optional[str] = Field(
        default=None,
        description="Item ID (itm_xxxx) for purchase actions"
    )

    # Transfer-specific fields (optional)
    transfer_target: Optional[str] = Field(
        default=None,
        description="Character name or agent_id to transfer energy/items to (for action_type=TRANSFER)"
    )

    transfer_currency: Optional[Dict[str, int]] = Field(
        default=None,
        description="Currency amounts to transfer, e.g. {'drip': 5, 'spark': 2} (for action_type=TRANSFER)"
    )

    transfer_items: Optional[Dict[str, int]] = Field(
        default=None,
        description="Item amounts to transfer, e.g. {'Incense': 2, 'Crystals': 1} (for action_type=TRANSFER)"
    )

    # Attunement-specific fields (optional)
    target_energy: Optional[Literal["breath", "grain", "drip", "spark"]] = Field(
        default=None,
        description="REQUIRED when action_type='attune'. Target energy type: breath, grain, drip, or spark. Must be specified for all attunement actions.",
        json_schema_extra={
            "x-required-when": {"action_type": "attune"},
            "x-validation-error": "target_energy is REQUIRED when action_type='attune'"
        }
    )

    altar_id: Optional[str] = Field(
        default=None,
        description="Altar ID (alt_xxxx) for attunement bonus (for action_type=ATTUNE)"
    )

    use_echo_calibrator: bool = Field(
        default=False,
        description="Use Echo-Calibrator for portable attunement (for action_type=ATTUNE)"
    )

    # Ritual-specific fields (optional)
    is_ritual: bool = Field(
        default=False,
        description="Whether this is a ritual action"
    )

    has_primary_tool: bool = Field(
        default=False,
        description="Do you have the required ritual focus/tool?"
    )

    has_offering: bool = Field(
        default=False,
        description="Set to True if you're using an offering (incense, blood, crystals) in this ritual. Offerings reduce void risk and are consumed. Set to False if not using offerings (you'll get -10 penalty and +1 void)."
    )

    offering_type: Optional[Literal["blood_offering", "incense", "crystals"]] = Field(
        default=None,
        description="IMPORTANT: If has_offering=True, optionally specify which offering type. Valid: 'blood_offering', 'incense', 'crystals'. If not specified, first available offering will be used automatically."
    )

    ritual_components: Optional[str] = Field(
        default=None,
        max_length=200,
        description="What materials/components are you using? (if ritual)"
    )

    # Optional modifiers
    situational_modifiers: Dict[str, int] = Field(
        default_factory=dict,
        description="Situational bonuses/penalties (e.g., {'high_ground': 2, 'darkness': -3})"
    )

    # Metadata
    reasoning: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Internal reasoning for this action choice (for ML training)"
    )

    # Tactical positioning (defence token)
    defence_token: Optional[str] = Field(
        default=None,
        description=(
            "Target ID (tgt_xxxx) of the combatant you are watching/covering. "
            "That combatant gets -2 to attack you; others get +2 flanking."
        )
    )

    @field_validator('attribute')
    @classmethod
    def validate_attribute(cls, v: str) -> str:
        """Validate attribute is one of the canonical 8."""
        valid_attributes = set(YAGS_ATTRIBUTES)
        if v not in valid_attributes:
            raise ValueError(
                f"Attribute must be one of: {', '.join(sorted(valid_attributes))}"
            )
        return v

    @field_validator('skill')
    @classmethod
    def validate_skill(cls, v: Optional[str]) -> Optional[str]:
        """Allow None or normalize skill name."""
        if v is None or v.lower() == 'none':
            return None
        return v

    @field_validator('ritual_components')
    @classmethod
    def validate_ritual_components(cls, v: Optional[str], info) -> Optional[str]:
        """Ritual components only allowed if is_ritual=True."""
        if v and not info.data.get('is_ritual', False):
            raise ValueError("ritual_components can only be set if is_ritual=True")
        return v

    @model_validator(mode='after')
    def validate_attunement_fields(self) -> 'PlayerAction':
        """Enforce required fields for attunement actions."""
        action_type_value = self.action_type.value if isinstance(self.action_type, ActionType) else self.action_type

        if action_type_value == "attune":
            if not self.target_energy:
                raise ValueError(
                    "target_energy is REQUIRED for action_type='attune'. "
                    "Must specify: breath, grain, drip, or spark"
                )

        return self

    def get_summary(self) -> str:
        """Get brief action summary for logging."""
        skill_text = f" × {self.skill}" if self.skill else ""
        target_text = f" → {self.target}" if self.target else ""
        return f"{self.character_name}: {self.intent} ({self.attribute}{skill_text} vs ~{self.difficulty_estimate}){target_text}"

    def to_legacy_dict(self) -> Dict:
        """
        Convert to legacy dict format for backward compatibility.

        Returns dict matching the old ActionDeclaration format.
        """
        return {
            'intent': self.intent,
            'description': self.description,
            'attribute': self.attribute,
            'skill': self.skill,
            'difficulty_estimate': self.difficulty_estimate,
            'difficulty_justification': self.difficulty_justification,
            'action_type': self.action_type.value if isinstance(self.action_type, ActionType) else self.action_type,
            'character_name': self.character_name,
            'agent_id': self.agent_id,
            'target_position': self.target_position.value if self.target_position else None,
            'target': self.target,
            'vendor_id': self.vendor_id,
            'item_id': self.item_id,
            'target_energy': self.target_energy,
            'altar_id': self.altar_id,
            'use_echo_calibrator': self.use_echo_calibrator,
            'is_ritual': self.is_ritual,
            'has_primary_tool': self.has_primary_tool,
            'has_offering': self.has_offering,
            'ritual_components': self.ritual_components,
            'situational_modifiers': self.situational_modifiers,
            'defence_token': self.defence_token,
        }


class FreeAction(BaseModel):
    """
    Free actions (dialogue, coordination, minor interactions).

    Simpler than full PlayerAction - no difficulty estimates or mechanical components.

    Example:
    ```python
    free_action = FreeAction(
        intent="Share tactical data with Thresh",
        description="Transmit neural scan results showing enemy weak point at junction B-7",
        character_name="Echo Resonance",
        agent_id="player_echo",
        target="Thresh Ireveth"
    )
    ```
    """

    intent: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="What you're doing/saying"
    )

    description: str = Field(
        ...,
        min_length=20,
        max_length=500,
        description="Details of the free action"
    )

    character_name: Optional[str] = Field(
        default=None,
        description="Character taking action (populated by system)",
        json_schema_extra={"exclude_from_llm": True}
    )

    agent_id: Optional[str] = Field(
        default=None,
        description="Agent identifier (populated by system)",
        json_schema_extra={"exclude_from_llm": True}
    )

    target: Optional[str] = Field(
        default=None,
        description="Target character (if directed at someone)"
    )

    is_coordination: bool = Field(
        default=False,
        description="Is this a coordination action that grants bonus to ally?"
    )

    coordination_bonus: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description="Bonus granted if is_coordination=True"
    )

    def get_summary(self) -> str:
        """Get brief summary."""
        target_text = f" → {self.target}" if self.target else ""
        coord_text = f" [+{self.coordination_bonus}]" if self.is_coordination else ""
        return f"{self.character_name}: {self.intent}{target_text}{coord_text}"
