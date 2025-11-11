# Mechanical Purchase Architecture

**Created:** 2025-01-10
**Completed:** 2025-01-10
**Status:** ✅ **FULLY IMPLEMENTED & TESTED**

**Purpose:** Make purchases deterministic and mechanical (not LLM-adjudicated) using vendor/item IDs

---

## ✅ IMPLEMENTATION COMPLETE

**Summary:** All phases implemented successfully. Purchase system now uses:
- Pre-validated vendor_id/item_id system (like combat targeting)
- Mechanical execution BEFORE DM narration
- Specialized LLM prompt (`dm_purchase.yaml`) for atmospheric narration only
- NO dice rolls for simple purchases
- Full JSONL logging for ML training

**Verification:**
- Session `1dddd8a0-1d85-44e8-b623-cae5b1c7866d`: 6 purchases across 3 rounds, 100% success rate
- All purchases show `roll.total: 0` (no dice)
- LLM generates creative narration without mechanical variance
- 8/8 unit tests passing (test_purchase_dm_integration_bugs.py)

**Key Files:**
- `scripts/aeonisk/multiagent/dm.py:2896-3035` - Specialized purchase handler
- `scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_purchase.yaml` - Purchase-specific prompt
- `scripts/aeonisk/multiagent/session.py:797-830` - Pre-validation & mechanical execution
- `scripts/aeonisk/multiagent/mechanics.py:2108-2190` - Purchase validation logic

---

## Problem Statement

**Current Bug** (session 340bd80e):
```
DM narrates: "You purchase Echo-Calibrator for 2 Spark"
DM populates: effects.purchase = {success: true, currency_spent: {spark: 2}}
Mechanics: ERROR - Mira has 0 Spark, needed 2!
Result: Purchase "happened" in narrative but failed mechanically
```

**Root Cause:**
- DM LLM adjudicates purchases WITHOUT seeing player currency
- DM can narrate successful purchases when player can't afford them
- Mechanics code runs AFTER narration (too late to prevent bad state)
- Parsing item names from narration is janky ("Echo-Calibrator" vs "Echo Calibrator (Field-Grade)")

---

## Solution: Vendor/Item IDs (Like Combat Targeting)

### Design Principle from PURCHASE_VENDING_SYSTEM_DESIGN.md

> **Simple Purchase (Deterministic):**
> - **Pre-validation occurs** BEFORE DM is called
> - System checks: `player.energy_purse.{energy_type} >= item.price`
> - System injects **constraint** into DM prompt
> - DM **MUST** narrate based on constraint (success or failure)

### ID-Based Architecture

**Just like combat targeting:**
- Combat: `[tgt_7a3f] Security Guard #1` → Player uses `tgt_7a3f`
- Vendors: `[vnd_a3kf] Scribe Orven Tylesh` → Player uses `vnd_a3kf`
- Items: `[itm_c9x2] Echo-Calibrator (8 Spark)` → Player uses `itm_c9x2`

**Player Action Schema:**
```python
class PlayerAction(BaseModel):
    # ... existing fields ...

    # Purchase fields (only used when action_type = "purchase")
    vendor_id: Optional[str] = None  # "vnd_xxxx" from vendor list
    item_id: Optional[str] = None    # "itm_xxxx" from vendor inventory
```

**Player sees:**
```
💰 VENDORS PRESENT:

**Scribe Orven Tylesh** [vnd_a3kf] (Neutral human_trader)
"Seeking clarity? I trade in resonance and remembrance."

Inventory:
- [itm_c9x2] Echo-Calibrator - 8 Spark
- [itm_f1k7] Purification Incense (Bundle) - 8 Drip
- [itm_m4n8] Talisman Blanks (x5) - 1 Spark
- [itm_w9p3] Attuned Seed (Fire) - 2 Spark
```

**Player declares:**
```python
PlayerAction(
    intent="Purchase Echo-Calibrator from Scribe Orven Tylesh",
    attribute="Charisma",
    skill="Corporate Influence",
    action_type=ActionType.PURCHASE,  # NEW: explicit purchase type
    vendor_id="vnd_a3kf",  # ID from vendor list
    item_id="itm_c9x2",    # ID from inventory
    description="I approach the Scribe and purchase the Echo-Calibrator using my Spark"
)
```

---

## Flow: Pre-Validated Mechanical Purchase

### 1. Player Declaration (Structured)

Player selects vendor ID + item ID from prompt.

**Session.py receives:**
- `action.action_type = "purchase"`
- `action.vendor_id = "vnd_a3kf"`
- `action.item_id = "itm_c9x2"`

### 2. Pre-Validation (BEFORE DM)

```python
# session.py - BEFORE calling DM LLM
if action.action_type == ActionType.PURCHASE:
    validation = mechanics.validate_purchase(
        character=agent.character_state,
        vendor_id=action.vendor_id,
        item_id=action.item_id
    )

    if validation.can_afford:
        # Inject SUCCESS constraint into DM prompt
        dm_context = {
            "purchase_validation": {
                "status": "SUCCESS",
                "constraint": "MUST narrate successful purchase",
                "item_name": validation.item_name,
                "cost": validation.cost,
                "player_surplus": validation.surplus
            }
        }
    else:
        # Inject FAILURE constraint into DM prompt
        dm_context = {
            "purchase_validation": {
                "status": "FAILED",
                "constraint": "MUST narrate insufficient funds. MAY suggest alternatives.",
                "item_name": validation.item_name,
                "required": validation.cost,
                "player_has": validation.player_currency,
                "shortage": validation.shortage
            }
        }
```

### 3. Mechanical Transaction (BEFORE DM narration)

```python
# session.py - Execute transaction BEFORE DM narrates
if validation.can_afford:
    # Deduct currency
    for currency_type, amount in validation.cost.items():
        agent.character_state.energy_purse.spend_currency(currency_type, amount)

    # Add item to inventory
    inventory_key = mechanics.get_inventory_key(validation.item_id)
    agent.character_state.inventory[inventory_key] = agent.character_state.inventory.get(inventory_key, 0) + 1

    logger.info(f"✓ {agent.character_state.name} purchased {validation.item_name} for {validation.cost}")
```

### 4. DM Narrates (Outcome Already Decided)

**DM prompt:**
```yaml
player_action: "I purchase Echo-Calibrator from Scribe Orven Tylesh"
action_type: PURCHASE

purchase_validation:
  status: FAILED
  constraint: "MUST narrate insufficient funds. MAY suggest alternatives."
  item_name: "Echo-Calibrator"
  required: {spark: 8}
  player_has: {spark: 0, drip: 4, grain: 1, breath: 20}
  shortage: {spark: 8}
```

**DM narrates based on constraint:**
> "You approach Scribe Orven Tylesh, but when you check your energy purse, you realize you don't have any Spark. The Echo-Calibrator costs 8 Spark, and you're completely out. The Scribe notices your predicament. 'I could offer a field-grade model on credit if you have ACG backing, or perhaps you'd like to pool resources with your companion?'"

**DM does NOT populate effects.purchase** - purchase already happened (or failed) mechanically!

---

## Benefits of ID-Based System

### 1. **No Keyword Parsing**
```python
# ❌ OLD: Janky parsing
item_name = "Echo-Calibrator (Field-Grade)"  # vs "Echo Calibrator"?
inventory_key = item_name.lower().replace(' ', '_').replace('-', '_')  # Fragile!

# ✅ NEW: Direct lookup
item_id = "itm_c9x2"
item_metadata = vendor.get_item_by_id(item_id)
inventory_key = item_metadata.inventory_key  # "echo_calibrator"
```

### 2. **Validation Before Narration**
```python
# ❌ OLD: DM narrates first, then mechanics check
DM: "You hand over 8 Spark and receive the Echo-Calibrator"
Mechanics: ERROR - player has 0 Spark!

# ✅ NEW: Validate first, then constrain DM
Mechanics: Player has 0 Spark, need 8
DM (constrained): "You check your purse - you need 8 Spark but have none"
```

### 3. **Deterministic Simple Purchases**
```
Player has 8 Spark → Purchase ALWAYS succeeds (no LLM variance)
Player has 0 Spark → Purchase ALWAYS fails (no LLM hallucination)
```

### 4. **LLM Only Narrates Social/Flavor**
```python
# Mechanics: Already deducted 8 Spark, added echo_calibrator to inventory
# DM: Just adds narrative flavor
"The Scribe's chrome-laced fingers finalize the transaction on his dataslate.
The field-grade Echo-Calibrator slides across the counter, humming with calibrated resonance."
```

---

## Implementation Plan

### Phase 1: Add IDs to Vendor System

**VendorItem schema:**
```python
@dataclass
class VendorItem:
    item_id: str  # NEW: "itm_xxxx"
    name: str
    description: str
    inventory_key: str  # NEW: Direct mapping to character inventory
    price_spark: int = 0
    price_grain: int = 0
    price_drip: int = 0
    price_breath: int = 0
```

**Vendor schema:**
```python
@dataclass
class Vendor:
    vendor_id: str  # NEW: "vnd_xxxx"
    name: str
    faction: str
    vendor_type: VendorType
    inventory: List[VendorItem]

    def get_item_by_id(self, item_id: str) -> Optional[VendorItem]:
        return next((item for item in self.inventory if item.item_id == item_id), None)
```

**ID generation:**
```python
def generate_vendor_id() -> str:
    """Generate unique vendor ID: vnd_xxxx"""
    return f"vnd_{generate_random_suffix(4)}"

def generate_item_id() -> str:
    """Generate unique item ID: itm_xxxx"""
    return f"itm_{generate_random_suffix(4)}"
```

### Phase 2: Update Player Prompts

**Round status display:**
```
💰 VENDORS PRESENT:

**Scribe Orven Tylesh** [vnd_a3kf] (Neutral human_trader)
"Seeking clarity? I trade in resonance and remembrance."

Inventory:
- [itm_c9x2] Echo-Calibrator - 8 Spark
- [itm_f1k7] Purification Incense - 8 Drip

💡 To purchase: Set action_type=PURCHASE, vendor_id="vnd_a3kf", item_id="itm_c9x2"
```

**PlayerAction schema:**
```python
class PlayerAction(BaseModel):
    # ... existing fields ...

    # Purchase-specific fields
    vendor_id: Optional[str] = Field(
        None,
        description="Vendor ID from vendor list (vnd_xxxx). Required when action_type=PURCHASE"
    )
    item_id: Optional[str] = Field(
        None,
        description="Item ID from vendor inventory (itm_xxxx). Required when action_type=PURCHASE"
    )
```

### Phase 3: Implement Pre-Validation

**mechanics.py:**
```python
@dataclass
class PurchaseValidation:
    can_afford: bool
    item_name: str
    inventory_key: str
    cost: Dict[str, int]
    player_currency: Dict[str, int]
    shortage: Optional[Dict[str, int]] = None
    surplus: Optional[Dict[str, int]] = None

def validate_purchase(
    self,
    character: Any,
    vendor_id: str,
    item_id: str
) -> PurchaseValidation:
    """
    Validate purchase BEFORE DM narration.

    Returns validation result with enough info to:
    1. Execute transaction if valid
    2. Constrain DM narration with exact shortage/surplus
    """
    # Lookup vendor
    vendor = self.shared_state.get_vendor_by_id(vendor_id)
    if not vendor:
        raise ValueError(f"Vendor {vendor_id} not found")

    # Lookup item
    item = vendor.get_item_by_id(item_id)
    if not item:
        raise ValueError(f"Item {item_id} not in {vendor.name} inventory")

    # Check affordability
    cost = item.cost  # {spark: 8}
    player_currency = character.energy_purse.to_dict()  # {spark: 0, drip: 4, ...}

    shortage = {}
    for currency_type, amount in cost.items():
        player_has = player_currency.get(currency_type, 0)
        if player_has < amount:
            shortage[currency_type] = amount - player_has

    can_afford = len(shortage) == 0

    return PurchaseValidation(
        can_afford=can_afford,
        item_name=item.name,
        inventory_key=item.inventory_key,
        cost=cost,
        player_currency=player_currency,
        shortage=shortage if not can_afford else None,
        surplus={k: player_currency[k] - cost.get(k, 0) for k in cost} if can_afford else None
    )
```

### Phase 4: Execute Transaction Before DM

**session.py - in action resolution flow:**
```python
# BEFORE calling DM LLM
if action.action_type == ActionType.PURCHASE:
    validation = mechanics.validate_purchase(
        character=agent.character_state,
        vendor_id=action.vendor_id,
        item_id=action.item_id
    )

    # Execute transaction if valid
    if validation.can_afford:
        # Deduct currency
        for currency_type, amount in validation.cost.items():
            agent.character_state.energy_purse.spend_currency(currency_type, amount)

        # Add item to inventory
        agent.character_state.inventory[validation.inventory_key] = \
            agent.character_state.inventory.get(validation.inventory_key, 0) + 1

        logger.info(f"✓ Purchase: {agent.character_state.name} bought {validation.item_name}")

    # Inject constraint into DM prompt
    dm_context["purchase_validation"] = {
        "status": "SUCCESS" if validation.can_afford else "FAILED",
        "constraint": "MUST narrate based on status",
        "item_name": validation.item_name,
        "cost": validation.cost,
        "player_currency": validation.player_currency,
        "shortage": validation.shortage,
        "surplus": validation.surplus
    }
```

### Phase 5: Update DM Prompt

**dm_state_tracking.yaml:**
```yaml
purchase_handling: |
  ## PURCHASE ACTIONS - MECHANICAL SYSTEM

  When you receive a purchase action with `purchase_validation` in context:

  **SUCCESS (transaction already completed):**
  - Currency ALREADY deducted from player
  - Item ALREADY added to inventory
  - You ONLY provide narrative flavor
  - Focus on: vendor interaction, item quality, social atmosphere
  - DO NOT re-process transaction mechanically

  Example:
  ```
  purchase_validation:
    status: SUCCESS
    item_name: "Echo-Calibrator"
    cost: {spark: 8}
    surplus: {spark: 2}
  ```

  Narrate:
  "The Scribe accepts your 8 Spark with practiced efficiency. The Echo-Calibrator
  slides across the counter, humming with calibrated resonance. You still have
  2 Spark remaining for emergencies."

  **FAILURE (transaction blocked):**
  - Currency check ALREADY failed
  - Item NOT in inventory
  - You MUST narrate shortage clearly
  - MAY suggest alternatives (credit, barter, cheaper items)

  Example:
  ```
  purchase_validation:
    status: FAILED
    item_name: "Echo-Calibrator"
    required: {spark: 8}
    player_has: {spark: 0, drip: 4}
    shortage: {spark: 8}
  ```

  Narrate:
  "You check your energy purse - you need 8 Spark but have none. The Scribe
  notices. 'I could offer credit if you have ACG backing, or perhaps pool
  resources with your companion?'"
```

---

## JSONL Logging

**CRITICAL:** All purchase attempts (success AND failure) must be logged to JSONL for ML training.

### Purchase Attempt Event Schema

```python
{
  "event_type": "purchase_attempt",
  "ts": "2025-01-10T...",
  "session": "...",
  "round": 1,
  "phase": "action_declaration",
  "agent": "Freeborn Trader Mira Seln",
  "purchase": {
    "vendor_id": "vnd_a3kf",
    "vendor_name": "Test Vend-O-Mat",
    "vendor_type": "vending_machine",
    "item_id": "itm_c9x2",
    "item_name": "Echo-Calibrator",
    "cost": {"spark": 8},
    "player_currency": {"spark": 0, "drip": 4, "grain": 1, "breath": 20},
    "success": false,
    "failure_reason": "Insufficient currency: need 8 Spark, have 0 Spark",
    "shortage": {"spark": 8}
  }
}
```

**Success case:**
```python
{
  "event_type": "purchase_attempt",
  # ... same fields ...
  "purchase": {
    "vendor_id": "vnd_a3kf",
    "item_id": "itm_c9x2",
    "cost": {"spark": 8},
    "player_currency": {"spark": 10, "drip": 4, ...},
    "success": true,
    "failure_reason": null,
    "surplus": {"spark": 2}
  }
}
```

### Why Log Failures?

1. **ML Training:** Agents need to learn when NOT to attempt purchases
2. **Economic Behavior:** Track how often players try to buy things they can't afford
3. **Vendor Interaction Patterns:** Understand which items are desirable but out of reach
4. **Debugging:** Clear audit trail of all purchase attempts

---

## Testing Strategy

### Use Vending Machines for Testing (Not Human Traders)

**Rationale:**
- Vending machines are **deterministic** (no negotiation, credit, or creative solutions)
- Focuses tests on core mechanics (validation, currency deduction, inventory)
- Avoids LLM variance in test results
- Human traders tested separately after core system works

### Unit Tests

**test_mechanical_purchase.py:**
```python
def test_vendor_item_id_generation():
    """Test that IDs are unique and well-formed."""
    vendor_id = generate_vendor_id()
    assert vendor_id.startswith("vnd_")
    assert len(vendor_id) == 8  # vnd_xxxx

def test_validate_purchase_success_vending_machine():
    """Test pre-validation for affordable purchase from vending machine."""
    character = create_test_character(spark=10)
    vendor = create_vending_machine_vendor()  # NOT human trader
    item_id = "itm_test1"  # Echo-Calibrator, 8 Spark

    validation = mechanics.validate_purchase(character, vendor.vendor_id, item_id)

    assert validation.can_afford == True
    assert validation.cost == {"spark": 8}
    assert validation.surplus == {"spark": 2}
    assert validation.shortage is None

def test_validate_purchase_failure_vending_machine():
    """Test pre-validation for unaffordable purchase from vending machine."""
    character = create_test_character(spark=0)
    vendor = create_vending_machine_vendor()  # NOT human trader
    item_id = "itm_test1"  # Echo-Calibrator, 8 Spark

    validation = mechanics.validate_purchase(character, vendor.vendor_id, item_id)

    assert validation.can_afford == False
    assert validation.shortage == {"spark": 8}
    assert validation.surplus is None

def test_mechanical_purchase_before_dm_vending_machine():
    """Test that transaction executes BEFORE DM narration."""
    character = create_test_character(spark=10)
    vendor = create_vending_machine_vendor()
    item_id = "itm_test1"

    # Pre-validate
    validation = mechanics.validate_purchase(character, vendor.vendor_id, item_id)
    assert validation.can_afford == True

    # Execute transaction
    character.energy_purse.spend_currency("spark", validation.cost["spark"])
    character.inventory[validation.inventory_key] = 1

    # Verify state BEFORE any DM call
    assert character.energy_purse.spark == 2
    assert character.inventory["echo_calibrator"] == 1

def test_purchase_failure_logged_to_jsonl():
    """Test that failed purchase attempts are logged."""
    character = create_test_character(spark=0)
    vendor = create_vending_machine_vendor()
    item_id = "itm_test1"  # Costs 8 Spark

    # Mock JSONL logger
    logger = MockJSONLLogger()

    # Attempt purchase
    validation = mechanics.validate_purchase(character, vendor.vendor_id, item_id)
    assert validation.can_afford == False

    # Log the failure
    logger.log_purchase_attempt(
        agent="Mira Seln",
        vendor_id=vendor.vendor_id,
        vendor_name=vendor.name,
        item_id=item_id,
        validation=validation
    )

    # Verify logged
    events = logger.get_events()
    assert len(events) == 1
    assert events[0]["event_type"] == "purchase_attempt"
    assert events[0]["purchase"]["success"] == False
    assert events[0]["purchase"]["shortage"] == {"spark": 8}

def test_purchase_success_logged_to_jsonl():
    """Test that successful purchases are logged."""
    character = create_test_character(spark=10)
    vendor = create_vending_machine_vendor()
    item_id = "itm_test1"

    logger = MockJSONLLogger()

    # Attempt purchase
    validation = mechanics.validate_purchase(character, vendor.vendor_id, item_id)
    assert validation.can_afford == True

    # Execute and log
    character.energy_purse.spend_currency("spark", 8)
    character.inventory["echo_calibrator"] = 1
    logger.log_purchase_attempt(
        agent="Mira Seln",
        vendor_id=vendor.vendor_id,
        item_id=item_id,
        validation=validation
    )

    events = logger.get_events()
    assert events[0]["purchase"]["success"] == True
    assert events[0]["purchase"]["surplus"] == {"spark": 2}
```

### Test Vendor Creation Helper

```python
def create_vending_machine_vendor() -> Vendor:
    """
    Create test vending machine vendor (NOT human trader).

    Vending machines are deterministic - no negotiation, credit, or creative solutions.
    """
    return Vendor(
        vendor_id="vnd_test1",
        name="Test Vend-O-Mat",
        faction="Nexus",
        vendor_type=VendorType.VENDING_MACHINE,  # ← Key: machine, not human
        greeting="Welcome to automated trading terminal.",
        inventory=[
            VendorItem(
                item_id="itm_test1",
                name="Echo-Calibrator",
                description="Attunes Raw Seeds",
                inventory_key="echo_calibrator",
                price_spark=8
            ),
            VendorItem(
                item_id="itm_test2",
                name="Health Kit",
                description="Restores 10 HP",
                inventory_key="med_kit",
                price_drip=5
            )
        ]
    )
```

### Integration Test (Fixture-Based)

**Use session 340bd80e as regression test:**
```python
def test_session_340bd80e_purchase_failure():
    """
    Regression test: Mira tried to purchase with 0 Spark.

    OLD behavior: DM narrated success, mechanics rejected
    NEW behavior: Pre-validation fails, DM narrates shortage
    """
    # Setup from session
    mira = create_character("Mira", spark=0, drip=4)
    vendor = create_vendor("Scribe Orven Tylesh", items=[
        VendorItem(item_id="itm_echo", name="Echo-Calibrator",
                   inventory_key="echo_calibrator", price_spark=8)
    ])

    # Player declares purchase
    action = PlayerAction(
        intent="Purchase Echo-Calibrator",
        action_type=ActionType.PURCHASE,
        vendor_id=vendor.vendor_id,
        item_id="itm_echo"
    )

    # Pre-validation SHOULD fail
    validation = mechanics.validate_purchase(mira, vendor.vendor_id, "itm_echo")

    assert validation.can_afford == False
    assert validation.shortage == {"spark": 8}

    # Transaction should NOT execute
    assert mira.energy_purse.spark == 0  # Unchanged
    assert "echo_calibrator" not in mira.inventory
```

---

## Migration Path

### Backward Compatibility

**Keep old system working during transition:**
1. Add `vendor_id` and `item_id` fields to PlayerAction (optional)
2. If IDs present → use new mechanical system
3. If IDs absent → fall back to old DM-adjudicated system
4. Log deprecation warnings for old system
5. Remove old system after migration period

### Player Prompt Updates

**Add vendor/item IDs to existing session configs:**
```python
# Update vendor display in session.py
def format_vendor_for_prompt(vendor: Vendor) -> str:
    output = f"**{vendor.name}** [{vendor.vendor_id}] ({vendor.faction} {vendor.vendor_type.value})\n"
    output += f'"{vendor.greeting}"\n\n'
    output += "Inventory:\n"
    for item in vendor.inventory:
        cost_str = ", ".join(f"{amount} {curr.title()}"
                             for curr, amount in item.cost.items() if amount > 0)
        output += f"- [{item.item_id}] {item.name} - {cost_str}\n"
    return output
```

---

## Success Criteria

✅ **Mechanical Determinism:**
- Player has currency → purchase ALWAYS succeeds
- Player lacks currency → purchase ALWAYS fails
- No LLM variance in simple transactions

✅ **No Keyword Parsing:**
- Item lookup by ID, not string matching
- Direct inventory_key mapping
- No fragile normalization logic

✅ **Pre-Validation:**
- Check affordability BEFORE DM narrates
- Inject constraints into DM prompt
- DM narrates based on mechanical reality

✅ **Inventory Integrity:**
- Items appear in inventory after successful purchase
- Currency deducted correctly
- No phantom purchases (narrated but not executed)

✅ **Regression Test:**
- Session 340bd80e scenario → pre-validation catches 0 Spark
- DM narrates shortage instead of success
- No ERROR logs from mechanics
