"""
Vendor Interaction and Offering Crafting Schemas

Structured output for purchases and crafting, eliminating keyword detection.

Philosophy:
- Purchases processed via DM adjudication (like combat actions)
- Crafting uses simple Attunement skill check (no complex ritual)
- All currency changes logged explicitly
"""

from pydantic import BaseModel, Field, model_validator
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

    Supports multi-currency transfers (e.g., 15 drip + 1 grain in single action).
    At least one currency field must be > 0.
    Tracked for JSONL logging.
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

    # Multi-currency support (at least one must be > 0)
    spark: int = Field(
        default=0,
        ge=0,
        description="Spark transferred (0 if not transferring Spark)"
    )

    grain: int = Field(
        default=0,
        ge=0,
        description="Grain transferred (0 if not transferring Grain)"
    )

    drip: int = Field(
        default=0,
        ge=0,
        description="Drip transferred (0 if not transferring Drip)"
    )

    breath: int = Field(
        default=0,
        ge=0,
        description="Breath transferred (0 if not transferring Breath)"
    )

    purpose: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Why transferring (e.g., 'Pooling funds for Echo-Calibrator purchase')"
    )

    @model_validator(mode='after')
    def validate_at_least_one_currency(self) -> 'CurrencyTransfer':
        """Ensure at least one currency type has amount > 0."""
        total = self.spark + self.grain + self.drip + self.breath
        if total == 0:
            raise ValueError(
                "At least one currency type must have amount > 0 for transfer"
            )
        return self


class ItemTransfer(BaseModel):
    """
    Player-to-player item transfer (sharing equipment, supplies).

    Supports multi-item transfers (e.g., 2 medkits + 1 scanner in single action).
    At least one item must have quantity > 0.
    Tracked for JSONL logging.
    """
    from_character: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Character giving items"
    )

    to_character: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Character receiving items"
    )

    items: Dict[str, int] = Field(
        ...,
        description="Items transferred with quantities (e.g., {'Medkit': 2, 'Scanner': 1}). Item names as keys, quantities as values."
    )

    purpose: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Why transferring (e.g., 'Sharing medical supplies with wounded ally')"
    )

    @model_validator(mode='after')
    def validate_at_least_one_item(self) -> 'ItemTransfer':
        """Ensure at least one item has quantity > 0."""
        if not self.items:
            raise ValueError("Items dict must contain at least one item for transfer")

        total = sum(qty for qty in self.items.values() if qty > 0)
        if total == 0:
            raise ValueError(
                "At least one item must have quantity > 0 for transfer"
            )
        return self
