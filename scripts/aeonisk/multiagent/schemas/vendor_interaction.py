"""
Vendor Interaction and Offering Crafting Schemas

Structured output for purchases and crafting, eliminating keyword detection.

Philosophy:
- Purchases processed via DM adjudication (like combat actions)
- Crafting uses simple Attunement skill check (no complex ritual)
- All currency changes logged explicitly
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, List


class PurchaseEffect(BaseModel):
    """
    DM-adjudicated purchase outcome (part of ActionResolution.effects).

    Replaces keyword parsing ("buy", "purchase") in player.py with structured output.
    DM validates vendor availability, currency sufficiency, and narrates transaction.
    """
    success: bool = Field(
        ...,
        description="Whether purchase succeeded (True) or failed (False)"
    )

    vendor_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Vendor name (e.g., 'Scribe Orven Tylesh', 'S4CU Vending Node')"
    )

    items_purchased: List[str] = Field(
        default_factory=list,
        description="Item names purchased (e.g., ['Echo-Calibrator', 'Incense Stick (x2)']). Empty if failed."
    )

    currency_spent: Dict[str, int] = Field(
        default_factory=dict,
        description="Currency spent per type (e.g., {'spark': 2, 'drip': 5}). Uses Breath/Drip/Grain/Spark (NOT 'credits'). Empty if failed."
    )

    narrative: str = Field(
        ...,
        min_length=20,
        max_length=500,
        description="DM narration of transaction (e.g., 'The vending machine whirrs, dispensing the Echo-Calibrator into your hands')"
    )

    failure_reason: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Why purchase failed (e.g., 'Insufficient currency', 'Vendor not present', 'Item out of stock'). Null if successful."
    )


class CraftingAttempt(BaseModel):
    """
    Player crafts offering from materials using Attunement skill.

    Simple conversion (not full ritual) per design spec.
    Examples:
    - blood_sample → blood_offering
    - herbs → incense
    - raw_crystal → crystals
    """
    offering_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Offering being crafted (e.g., 'blood_offering', 'incense', 'crystals')"
    )

    materials_used: List[str] = Field(
        ...,
        min_items=1,
        max_items=5,
        description="Materials consumed in attempt (e.g., ['blood_sample', 'purification_salt'])"
    )

    success: bool = Field(
        ...,
        description="Whether crafting succeeded (True) or failed (False). Based on Attunement skill check."
    )

    roll_total: Optional[int] = Field(
        default=None,
        description="Skill check total (Willpower × Attunement vs DC 15)"
    )

    quality: Optional[str] = Field(
        default=None,
        pattern="^(basic|enhanced|corrupted)$",
        description="Offering quality tier (future feature). Null for v1.0 (all offerings identical)."
    )

    narrative: str = Field(
        ...,
        min_length=20,
        max_length=300,
        description="DM narration of crafting attempt (success or failure)"
    )


class CurrencyTransfer(BaseModel):
    """
    Player-to-player currency transfer (pooling resources).

    Tracked for JSONL logging (currently invisible in training data).
    """
    from_character: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Character giving currency"
    )

    to_character: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Character receiving currency"
    )

    currency_type: str = Field(
        ...,
        pattern="^(breath|drip|grain|spark)$",
        description="Currency type transferred (Breath/Drip/Grain/Spark, NOT 'credits')"
    )

    amount: int = Field(
        ...,
        ge=1,
        description="Amount transferred (must be positive)"
    )

    purpose: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Why transferring (e.g., 'Pooling funds for Echo-Calibrator purchase')"
    )
