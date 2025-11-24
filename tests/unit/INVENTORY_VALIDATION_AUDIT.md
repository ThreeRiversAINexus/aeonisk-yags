# Inventory Validation Audit

**Date:** 2025-11-20
**Purpose:** Comprehensive audit of inventory-dependent actions to identify validation gaps
**Trigger:** Seed attunement bug (players attempting to attune without seeds)

## Summary

All major inventory-dependent actions with **hard requirements** are now validated at the session level before DM adjudication:

✅ **Purchase** - Currency validation (session.py:3484-3558)
✅ **Transfer** - Item/currency validation (session.py:3559-3701)
✅ **Attunement** - Seed/equipment validation (session.py:3460-3506) **[NEWLY ADDED]**

## Action Type Analysis

### EXPLORE
- **Inventory Requirements:** None
- **Validation Needed:** ❌ No

### INVESTIGATE
- **Inventory Requirements:** None
- **Validation Needed:** ❌ No

### RITUAL
- **Inventory Requirements:** Optional (has_primary_tool, has_offering)
- **Validation Needed:** ❌ No - **INTENTIONAL DESIGN**
- **Rationale:** Players CAN perform rituals without tools/offerings. The system applies void corruption penalties but doesn't block the action. This is core game design.
- **Implementation:** player.py:740-745 marks flags, mechanics.py:1912-1925 applies DC penalties

### SOCIAL
- **Inventory Requirements:** None
- **Validation Needed:** ❌ No

### COMBAT
- **Inventory Requirements:** Optional (weapons improve effectiveness)
- **Validation Needed:** ❌ No
- **Rationale:** Weapon usage is narrative, not mechanically enforced. Players can attack unarmed or with improvised weapons. DM adjudicates effectiveness.

### TECHNICAL
- **Inventory Requirements:** None (tools are narrative)
- **Validation Needed:** ❌ No

### PERCEPTION
- **Inventory Requirements:** None
- **Validation Needed:** ❌ No

### SUPPORT
- **Inventory Requirements:** Optional (medkits, equipment)
- **Validation Needed:** ❌ No
- **Rationale:** Support actions don't mechanically consume items. Medkit usage is narrative flavor. If items are transferred as part of support, transfer validation handles it.

### PURCHASE
- **Inventory Requirements:** HARD (must have sufficient currency)
- **Validation Needed:** ✅ **ALREADY IMPLEMENTED**
- **Location:** session.py:3484-3558
- **Validates:**
  - Vendor exists
  - Item exists
  - Player has sufficient currency (breath, drip, grain, spark)
  - Soulcredit threshold met
- **Behavior:** Pre-executes transaction before DM narration if valid, marks as failed if invalid

### TRANSFER
- **Inventory Requirements:** HARD (must have items/currency to transfer)
- **Validation Needed:** ✅ **ALREADY IMPLEMENTED**
- **Location:** session.py:3559-3701
- **Validates:**
  - Target exists
  - Player has sufficient currency/items
  - Range check (in combat)
- **Behavior:** Pre-executes transfer before DM narration if valid, marks as failed if invalid

### ATTUNE
- **Inventory Requirements:** HARD (must have Raw Seeds)
- **Validation Needed:** ✅ **NEWLY IMPLEMENTED** (2025-11-20)
- **Location:** session.py:3460-3506
- **Validates:**
  - Player has at least one Raw Seed
  - target_energy specified
  - Altar exists (if altar_id provided)
  - Echo-Calibrator in inventory (if use_echo_calibrator=True)
  - Sufficient Drip for upkeep (every 3rd calibrator use)
- **Behavior:** Rejects action before buffering if invalid, prevents DM from seeing it
- **Related Changes:**
  - player.py:1119-1128 - Warning in seeds_display when raw_count==0
  - player_action_attune.yaml:16-22 - Prerequisite check documentation
  - tests/unit/test_attunement_validation_integration.py - Integration tests

### CUSTOM
- **Inventory Requirements:** Variable (depends on narrative)
- **Validation Needed:** ❌ No
- **Rationale:** Custom actions are freeform. DM adjudicates feasibility based on narrative context. Inventory checks are part of DM judgment.

## Consumables (Medkits, Grenades, etc.)

**Finding:** Consumables are NOT a distinct action type.

**Usage Patterns:**
1. **Transferred between characters** → Validated by TRANSFER validation
2. **Used in narrative actions** (SUPPORT, CUSTOM, COMBAT) → DM adjudicates
3. **Enemy grenade throws** → Enemy-specific mechanics (enemy_combat.py:1738)

**Validation Status:** ✅ Covered by existing transfer validation when mechanically consumed

## Recommendations

### Immediate (Completed)
- ✅ Add attunement validation (session.py)
- ✅ Enhance player prompts for zero-seed warning (player.py)
- ✅ Document prerequisite in attunement prompt (player_action_attune.yaml)

### Future Enhancements (Optional)
1. **Player re-declaration mechanism**: Currently, rejected actions cause player to effectively pass turn. Future work could implement message-based re-declaration request.

2. **Ritual tool/offering warnings**: Consider adding soft warnings (like void warnings) when players have low offerings. This doesn't block action but guides LLM decision-making.

3. **Enemy grenade inventory tracking**: Enemy prompts reference grenade availability (enemy_prompts.py:649-651) but this is TODO. Consider implementing ammo tracking if grenades become frequent.

4. **Weapon inventory tracking**: Currently narrative-only. If weapons become mechanically distinct (durability, ammo), add validation.

### Do NOT Implement
- ❌ Blocking ritual actions when missing tools/offerings (violates game design)
- ❌ Hard validation for narrative consumables (medkits in support actions - DM decides)
- ❌ Combat action weapon requirements (breaks improvised combat philosophy)

## Validation Pattern

All hard-requirement validations follow this pattern:

```python
# 1. Detect action type
action_type = message.payload.get('action_type')

if action_type == 'TARGET_TYPE':
    # 2. Get mechanics engine
    if self.shared_state and self.shared_state.mechanics_engine:
        mechanics = self.shared_state.mechanics_engine
        player_agent = next((a for a in self.agents if a.agent_id == agent_id), None)

        if player_agent:
            try:
                # 3. Extract parameters from payload
                param1 = message.payload.get('param1')
                param2 = message.payload.get('param2')

                # 4. Call validation function
                validation = mechanics.validate_XXX(
                    character_state=player_agent.character_state,
                    param1=param1,
                    param2=param2
                )

                # 5. Handle validation result
                if not validation.is_valid:
                    # REJECT - don't buffer, don't send to DM
                    logger.warning(f"❌ {ACTION} REJECTED: {validation.failure_reason}")
                    print(f"\n❌ [{player_agent.character_state.name}] {validation.failure_reason}\n")
                    return  # Early exit prevents buffering

            except Exception as e:
                logger.error(f"Error validating {action_type}: {e}")
                return  # Reject on validation error

# 6. If we get here, buffer the action (valid or no validation needed)
```

## Test Coverage

- **Unit tests:** `tests/unit/test_attunement.py` (validate_attunement function)
- **Integration tests:** `tests/unit/test_attunement_validation_integration.py` (session flow)
- **Session config tests:** `tests/unit/test_session_config_validation.py` (config validation)

## Files Modified (2025-11-20)

1. **session.py:3460-3506** - Added attunement validation hook
2. **player.py:1119-1128** - Added zero-seed warning to seeds_display
3. **player_action_attune.yaml:16-22** - Added prerequisite check section
4. **test_attunement_validation_integration.py** - NEW FILE - Integration tests

## Conclusion

**All inventory-dependent actions with hard requirements are now validated.**

The three actions that mechanically consume resources (purchase, transfer, attune) all validate inventory before reaching the DM, preventing phantom operations and confusing error states.

Other action types intentionally allow missing inventory for game design reasons (rituals apply penalties) or use narrative adjudication (consumables, weapons).

**No further validation gaps identified.**
