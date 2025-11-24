# Purchase System Bugs - Session Analysis

**Session:** `fa4d5e03-fee7-469a-8079-fdcc8e3efaf4`
**Date:** 2025-01-09
**Issue:** Players attempted purchases but items never appeared in inventory

**Status:** ✅ **ALL BUGS FIXED** (2025-01-10)

---

## Bug Summary

| Bug # | Description | Impact | Status |
|-------|-------------|--------|--------|
| **#1** | DM marks valid transactions as "pending confirmation" | Purchase fails when it should succeed | ✅ FIXED - Pre-validation prevents DM adjudication |
| **#2** | DM sets `purchase: null` when item unavailable | No structured feedback about failure | ✅ FIXED - Pre-validation catches all failures |
| **#3** | DM doesn't structure alternate item suggestions | Lost opportunity for fallback purchases | ✅ FIXED - Not applicable (vendor IDs handle this) |
| **#4** | Inventory processing works but DM doesn't trigger it | Items never reach inventory | ✅ FIXED - Mechanical execution before DM |
| **#5** | DM rolls dice for purchases (Charisma × Charm) | Adds false difficulty to transactions | ✅ FIXED - Specialized pathway, no rolls |
| **#6** | Keyword parsing fragile ("Echo-Calibrator" vs "Echo Calibrator") | Items don't match inventory keys | ✅ FIXED - Item IDs direct mapping |
| **#7** | Currency validation happens AFTER narration | Phantom purchases narrated | ✅ FIXED - Pre-validation architecture |
| **#8** | DM lacks player currency visibility | Can't narrate realistic failures | ✅ FIXED - Validation data injected into DM prompt |

**Fix Implementation:** Mechanical Purchase Architecture (vendor_id/item_id system)
- Pre-validation before DM narration
- Mechanical execution (currency deduction, inventory addition)
- Specialized LLM prompt for atmospheric narration only
- No dice rolls for routine purchases
- Full JSONL logging

**Verification:** Session `1dddd8a0-1d85-44e8-b623-cae5b1c7866d` - 6 successful purchases, 0 bugs

---

## Detailed Bug Analysis

### Bug #1: "Pending Confirmation" Pattern

**Session Evidence** (Line 12):

```json
{
  "agent": "Freeborn Trader Mira Seln",
  "action": "Approach \"Cipher\" to inquire about Echo-Calibrator availability",
  "narration": "...Five Spark, and I'll throw in advice... Their hand extends, the Calibrator gleaming...",
  "effects": {
    "purchase": {
      "success": false,
      "vendor_name": "Cipher (Masked Freeborn Vendor)",
      "items_purchased": [],
      "currency_spent": {},
      "narrative": "Cipher offers Echo-Calibrator for 5 Spark - transaction pending player confirmation of purchase",
      "failure_reason": "Transaction offered but not yet completed - awaiting player decision to spend 5 Spark"
    }
  }
}
```

**What Happened:**
- Player declared: "I need an Echo-Calibrator urgently... I can pay well"
- DM narrated successful negotiation: vendor offers item for 5 Spark
- DM marked as FAILED purchase with "pending confirmation"

**Why This Is Wrong:**
- Player's action declaration IS the confirmation
- When player says "I purchase X", they're committing to the transaction
- DM shouldn't require additional confirmation step

**Additional Issue:**
- Mira had 0 Spark, not 5 Spark!
- Purchase SHOULD have failed with "Insufficient funds: need 5 Spark, have 0 Spark"
- Instead failed with "pending confirmation" (wrong failure reason)

**Expected Behavior:**
```json
{
  "success": false,
  "failure_reason": "Insufficient currency: need 5 Spark, have 0 Spark",
  "shortage": {"spark": 5},
  "narrative": "Cipher offers the Echo-Calibrator for 5 Spark, but you check your pouch and realize you don't have enough."
}
```

---

### Bug #2: Null Purchase Effect for Unavailable Items

**Session Evidence** (Line 16):

```json
{
  "agent": "ACG Auditor Kress Valen",
  "action": "Purchase Echo-Calibrator from Test Vend-O-Mat to stabilize degrading Seeds",
  "narration": "...INVENTORY DEPLETED - LAST UNIT SOLD 47 SECONDS AGO...",
  "effects": {
    "purchase": null  // ← BUG: Should be populated with failure info
  }
}
```

**What Happened:**
- Player declared: "Purchase Echo-Calibrator from Test Vend-O-Mat"
- DM narrated: item is out of stock
- DM set `purchase: null` instead of structured failure

**Why This Is Wrong:**
- `null` means "no purchase attempt"
- But player explicitly attempted purchase
- Should populate with `success: false` and clear failure reason

**Expected Behavior:**
```json
{
  "success": false,
  "vendor_name": "Test Vend-O-Mat",
  "items_purchased": [],
  "currency_spent": {},
  "narrative": "The vending machine displays: INVENTORY DEPLETED - LAST UNIT SOLD 47 SECONDS AGO",
  "failure_reason": "Item not in vendor inventory: Echo-Calibrator (sold out)"
}
```

---

### Bug #3: Alternate Items Not Structured

**Session Evidence** (Line 16 narration):

> "...you scan alternate equipment categories, finding a **Resonance Dampener** (2 Spark) that could slow Seed degradation by 30%, and a **Portable Ley Anchor** (3 Spark) designed for emergency node stabilization."

**What Happened:**
- DM identified 2 alternate items in narration
- DM priced them (2 Spark, 3 Spark)
- But `effects.purchase: null` - no structured data about alternates

**Why This Is Wrong:**
- Player can't programmatically know alternates exist
- Would need to parse DM narration (brittle, error-prone)
- Can't automatically suggest "buy Dampener instead?"

**Expected Behavior:**
```json
{
  "success": false,
  "vendor_name": "Test Vend-O-Mat",
  "items_purchased": [],
  "currency_spent": {},
  "narrative": "Echo-Calibrator out of stock. Alternate items available: Resonance Dampener (2 Spark), Portable Ley Anchor (3 Spark)",
  "failure_reason": "Requested item unavailable",
  "alternates": [  // NEW FIELD
    {"name": "Resonance Dampener", "price_spark": 2},
    {"name": "Portable Ley Anchor", "price_spark": 3}
  ]
}
```

---

### Bug #4: Process Chain Breaks

**The Process That SHOULD Happen:**

```
1. Player declares: "I purchase Echo-Calibrator"
2. DM adjudicates action
3. DM populates effects.purchase:
   - success: true/false
   - items_purchased: ["Echo-Calibrator"]
   - currency_spent: {"spark": 5}
4. Session.py receives ACTION_RESOLVED
5. Session.py calls mechanics.process_purchase_effect()
6. Mechanics deducts currency
7. Mechanics adds item to inventory
8. RESULT: character.inventory["echo_calibrator"] += 1
```

**What Actually Happened:**

```
1. Player declares: "I purchase Echo-Calibrator" ✓
2. DM adjudicates action ✓
3. DM populates effects.purchase:
   - success: FALSE (should be validation error)
   - OR: null (should be failure with reason)
4. Session.py receives ACTION_RESOLVED ✓
5. process_purchase_effect() sees success=false ✗
   - Returns False immediately (line 2037-2039)
   - Never reaches inventory processing
6. RESULT: No inventory update
```

**The Code Is Correct:**

```python
# mechanics.py lines 2053-2072
for item_name in purchase_effect.items_purchased:
    inventory_key = item_name.lower().replace(' ', '_').replace('(', '').replace(')', '')

    # Mappings
    if 'echo_calibrator' in inventory_key:
        inventory_key = 'echo_calibrator'

    if hasattr(character_state, 'inventory'):
        current = character_state.inventory.get(inventory_key, 0)
        character_state.inventory[inventory_key] = current + 1  # ← This WOULD work!
        logger.info(f"Added {inventory_key} to {character_state.name}'s inventory")
```

**The Problem:** DM never creates `success: true` purchases with `items_purchased: ["Echo-Calibrator"]`

---

## Root Cause Analysis

### Why DM Isn't Populating Purchase Effects Correctly

**Hypothesis 1: DM Prompt Doesn't Emphasize Purchase Structured Output**
- DM may not be instructed to populate `PurchaseEffect` for buy/sell actions
- Needs explicit guidance in `dm_state_tracking.yaml`

**Hypothesis 2: No Pre-Validation**
- DM doesn't know player's actual currency before narrating
- Can't make informed decision about success/failure
- Guesses based on action description

**Hypothesis 3: Purchase Actions Classified as "Social"**
- Both purchase attempts marked as `action_type: "social"`
- DM may treat social actions differently than purchase actions
- Should be `action_type: "purchase"` or `"economic"`?

---

## Required Fixes

### Fix #1: Add Pre-Validation to DM Flow

**Before DM Narration:**
```python
# In dm.py, before calling LLM for action resolution:
if player_action_involves_purchase(action):
    validation = mechanics.validate_purchase_request(
        character=character,
        vendor_name=extract_vendor_name(action),
        item_name=extract_item_name(action)
    )

    # Inject into DM prompt:
    if not validation.is_valid:
        prompt += f"\nPURCHASE VALIDATION: Player cannot afford this. {validation.failure_reason}"
    else:
        prompt += f"\nPURCHASE VALIDATION: Player has sufficient funds. Proceed with transaction."
```

**Benefits:**
- DM knows affordability BEFORE narrating
- Prevents "pending confirmation" pattern
- Ensures correct failure reasons

### Fix #2: Update DM Prompt Template

**Add to `dm_state_tracking.yaml`:**

```yaml
purchase_guidance: |
  ## PURCHASE & ECONOMIC TRANSACTIONS

  When a player declares a purchase action ("I buy X", "I purchase Y"):

  1. **Check Vendor Availability:**
     - Is the vendor present in the scenario?
     - Does vendor have the item in stock?

  2. **Check Player Affordability:**
     - Does player have required currency?
     - Use pre-validation result if provided

  3. **Populate effects.purchase:**
     - **Success Case:**
       ```
       success: true
       vendor_name: "Vendor Name"
       items_purchased: ["Item Name"]
       currency_spent: {"spark": 5}
       narrative: "You hand over 5 Spark and receive the Echo-Calibrator"
       ```

     - **Failure Case (Out of Stock):**
       ```
       success: false
       vendor_name: "Vendor Name"
       items_purchased: []
       currency_spent: {}
       narrative: "The vendor checks their inventory - the item is sold out"
       failure_reason: "Item not in vendor inventory"
       ```

     - **Failure Case (Insufficient Funds):**
       ```
       success: false
       vendor_name: "Vendor Name"
       items_purchased: []
       currency_spent: {}
       narrative: "You check your currency pouch - you need 5 Spark but only have 2"
       failure_reason: "Insufficient currency: need 5 Spark, have 2 Spark"
       ```

  4. **NEVER use "pending confirmation":**
     - Player's action declaration IS the confirmation
     - If they said "I buy X", treat it as a committed transaction attempt

  5. **Structure Alternate Items:**
     - If requested item unavailable, check vendor for similar items
     - Include in failure_reason: "Alternates: Item1, Item2"
```

### Fix #3: Enhance PurchaseEffect Schema

**Add `alternates` field:**

```python
# schemas/vendor_interaction.py

class PurchaseEffect(BaseModel):
    success: bool
    vendor_name: str
    items_purchased: List[str] = Field(default_factory=list)
    currency_spent: Dict[str, int] = Field(default_factory=dict)
    narrative: str = Field(min_length=20)
    failure_reason: Optional[str] = None
    alternates: Optional[List[Dict[str, Any]]] = None  # NEW
```

**Usage:**
```json
{
  "success": false,
  "failure_reason": "Echo-Calibrator out of stock",
  "alternates": [
    {"name": "Resonance Dampener", "price_spark": 2},
    {"name": "Portable Ley Anchor", "price_spark": 3}
  ]
}
```

### Fix #4: Improve Item Name Mapping

**Current mapping is fragile:**
```python
inventory_key = item_name.lower().replace(' ', '_').replace('(', '').replace(')', '')
```

**Better approach - Canonical Mapping Table:**
```python
VENDOR_ITEM_TO_INVENTORY = {
    # Ritual items
    "Blood Offering": "blood_offering",
    "Incense Bundle": "incense",
    "Raw Crystal": "raw_crystal",

    # Tech items
    "Echo-Calibrator": "echo_calibrator",
    "Resonance Dampener": "resonance_dampener",
    "Portable Ley Anchor": "portable_ley_anchor",

    # Medical
    "Health Kit": "med_kit",
    "Medkit": "med_kit",

    # Seeds
    "Attuned Seed (Fire)": "attuned_seed_fire",
    "Raw Seed": "raw_seed",
}

def map_vendor_item_to_inventory_key(item_name: str) -> str:
    """Map vendor item name to inventory key with fallback."""
    if item_name in VENDOR_ITEM_TO_INVENTORY:
        return VENDOR_ITEM_TO_INVENTORY[item_name]

    # Fallback: normalize
    return item_name.lower().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '')
```

---

## Test Coverage

**New Test File:** `test_purchase_dm_integration_bugs.py`

- ✅ Bug #1: Pending confirmation pattern
- ✅ Bug #2: Null purchase for unavailable items
- ✅ Bug #3: Alternate items not structured
- ✅ Bug #4: Inventory processing (code works, DM doesn't trigger it)
- ✅ Pre-validation architecture
- ✅ Item name normalization
- ✅ Inventory key mappings

**Total:** 8 tests documenting expected behavior

---

## Implementation Priority

### Phase 1: Quick Wins (Can Do Now)
1. ✅ Document bugs in tests
2. ✅ Verify inventory processing code works
3. ⏸️ Add canonical item mapping table
4. ⏸️ Add `alternates` field to PurchaseEffect schema

### Phase 2: DM Integration (Requires Prompt Engineering)
1. ⏸️ Add purchase guidance to `dm_state_tracking.yaml`
2. ⏸️ Implement pre-validation in DM flow
3. ⏸️ Test with real LLM calls

### Phase 3: Validation (After Phase 2)
1. ⏸️ Run economic scenario again
2. ⏸️ Verify purchases complete correctly
3. ⏸️ Verify items appear in inventory

---

## Conclusion

**The Good News:**
- Inventory processing code (`process_purchase_effect`) is fully implemented
- Currency deduction works
- Item mapping logic exists

**The Bad News:**
- DM isn't populating `effects.purchase` correctly
- No pre-validation before DM narration
- DM treats purchases as social negotiation, not transactions

**The Fix:**
- Add purchase guidance to DM prompts
- Implement pre-validation in DM action resolution flow
- Enhance PurchaseEffect schema with alternates field

**Estimated Effort:**
- Phase 1 (mapping table): 1 hour
- Phase 2 (DM integration): 4-6 hours
- Phase 3 (testing): 2 hours

**Total:** ~1 day of focused work to fully fix purchase system
