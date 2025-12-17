# Offering System Design

## Current Implementation (v1.0 - MVP)

### How It Works

**Schema:**
```python
# PlayerAction schema
has_offering: bool = Field(default=False, description="...")
offering_type: Optional[Literal["blood_offering", "incense", "crystals"]] = Field(...)
```

**Offering Types (Hardcoded Categories):**
- `blood_offering` - Generic blood offering category
- `incense` - Generic incense category
- `crystals` - Generic crystal category

**Selection Logic (mechanics.py:consume_offering):**
1. Player sets `has_offering=True` + optional `offering_type="incense"`
2. If `offering_type` specified: Use first item in inventory matching that category
3. If `offering_type` NOT specified: Use first available offering (any category)

**Inventory Matching (mechanics.py):**
```python
# Fuzzy matching - checks if category keyword appears in item name
if offering_type == "incense":
    # Matches: "Purification Incense", "Consecrated Incense", "incense stick"
    item_key = next(key for key in inventory if 'incense' in key.lower())

elif offering_type == "blood_offering":
    # Matches: "blood_offering", "Blood Vial", "Sacrificial Blood"
    item_key = next(key for key in inventory if 'blood' in key.lower())

elif offering_type == "crystals":
    # Matches: "crystals", "Crystal Shard", "Void Crystal"
    item_key = next(key for key in inventory if 'crystal' in key.lower())
```

**Consumption Flow:**
1. Player declares action with `has_offering=True` (in action_declaration)
2. DM receives action, calls `mechanics.consume_offering(character_state, offering_type)` BEFORE narration
3. Offering removed from inventory, item name returned
4. DM receives `action['offering_consumed']=True` and `action['offering_item']="Purification Incense"` as context
5. DM narrates what actually happened (including which offering was used)
6. JSONL logs `effects.inventory_changes` with consumption details

### Limitations

**1. Category-Based, Not Item-Specific**
- Player can only choose category ("incense"), not specific item ("Purification Incense" vs "Corrupted Incense")
- No way to distinguish between different qualities/types within a category
- Example problem: Player has both "Purification Incense" (safe) and "Void-Tainted Incense" (dangerous) but can't choose which

**2. Fuzzy String Matching**
- Uses substring matching (`'incense' in key.lower()`) which is brittle
- Could have false positives (e.g., "Incense Burner" matched as offering when it's a tool)
- No validation that matched item is actually consumable

**3. No Multi-Item Offerings**
- Some rituals might require multiple offerings (e.g., "blood + incense + crystal")
- Current schema only supports single offering consumption per action

**4. No Offering Quality/Potency**
- All "incense" items treated identically
- Can't model "rare incense" being more effective than "common incense"
- No way to give offerings different void-reduction values

**5. Limited Player Agency**
- Player writes narrative: "I carefully select the Purification Incense from my ritual pouch"
- System uses: First item matching 'incense' (might be different item!)
- Disconnect between narrative and mechanics

### Why This Design?

**Pragmatic MVP approach:**
- ✅ Fixes the bug (offerings actually consumed now!)
- ✅ Simple schema (3 categories vs. hundreds of possible items)
- ✅ Works with existing inventory system (no refactoring needed)
- ✅ Backward compatible (old sessions with no `offering_type` still work)
- ✅ Reduces LLM validation failures (Literal enum vs free text)

**Trade-offs accepted:**
- ❌ Less player agency (can't pick specific items)
- ❌ Less narrative flexibility (can't distinguish item qualities)
- ❌ Fuzzy matching fragility (substring checks)

---

## Future Enhancement (v2.0 - Full Item Selection)

### Desired Behavior

**Player Intent:**
```
description: "I carefully select the Purification Incense from my ritual pouch, avoiding the void-tainted samples. This consecrated incense was blessed by the Arcanists Guild - perfect for this cleansing ritual."
```

**Ideal Schema:**
```python
# PlayerAction schema (hypothetical v2.0)
has_offering: bool = Field(default=False)
offering_items: List[str] = Field(
    default_factory=list,
    description="Specific item names from your inventory to consume as offerings. Example: ['Purification Incense', 'Crystal Shard']. Must match inventory exactly."
)
```

**Enhanced Selection Logic:**
```python
# mechanics.py (hypothetical v2.0)
def consume_offerings(character_state, offering_items: List[str]) -> List[str]:
    """
    Consume specific items from inventory.

    Args:
        character_state: Character with inventory
        offering_items: Exact item names to consume (e.g., ["Purification Incense"])

    Returns:
        List of actually consumed items (might be fewer if items missing)
    """
    consumed = []
    for item_name in offering_items:
        if item_name in character_state.inventory:
            if character_state.inventory[item_name] > 0:
                character_state.inventory[item_name] -= 1
                consumed.append(item_name)
                logger.info(f"Consumed offering: {item_name}")
            else:
                logger.warning(f"Player declared {item_name} but quantity is 0")
        else:
            logger.warning(f"Player declared {item_name} but item not in inventory")

    return consumed
```

### Implementation Challenges

**1. Inventory Name Validation**
- Player must know exact item names in their inventory
- Typos cause validation failures ("purification incense" vs "Purification Incense")
- Need fuzzy matching OR exact name list in prompt

**2. Prompt Complexity**
- Player prompt already massive (~15k tokens)
- Adding full inventory listing increases token usage significantly
- Solution: Dynamic inventory injection (only show relevant items?)

**3. LLM Compliance**
- Player LLM might invent items not in inventory ("I use my Sacred Incense" when they only have "Purification Incense")
- Need strong prompt guidance + schema validation
- Risk of more validation failures → worse player experience

**4. Backward Compatibility**
- Existing sessions/fixtures use category-based system
- Need migration path or support both systems

**5. Multi-Item Offerings**
- If allowing multiple items, need clear rules:
  - Do ALL items need to be consumed for ritual to work?
  - Partial consumption = partial bonus?
  - What if player lists 5 items but only 2 are in inventory?

### Recommended Approach

**Phase 1 (Current - MVP):**
- ✅ Use category-based system (`blood_offering`, `incense`, `crystals`)
- ✅ Get basic offering consumption working
- ✅ Gather data on how players actually use offerings

**Phase 2 (Incremental - Hybrid System):**
- Add optional `specific_offering_item: Optional[str]` field
- If specified, consume that exact item (with fuzzy fallback)
- If not specified, fall back to category system
- Best of both worlds: precision when needed, simplicity as default

**Phase 3 (Full Enhancement - v2.0):**
- Replace categories with `offering_items: List[str]`
- Add inventory display to player prompt (dynamic injection)
- Implement exact-match validation with helpful error messages
- Support multi-item offerings with clear rules

### Decision: Stay with v1.0 for Now

**Why wait:**
1. Need to test if category system is actually problematic in practice
2. Want to avoid premature optimization (YAGNI - You Ain't Gonna Need It)
3. Player prompt already at token limits
4. Can gather ML training data on offering usage patterns first
5. v1.0 fixes the core bug (offerings not consumed) - that's the priority

**When to revisit:**
- When players report: "I wanted to use X but system used Y"
- When we see LLM-generated narratives don't match consumption logs
- When implementing high-stakes rituals where offering choice matters mechanically
- When inventory system gets item quality/rarity attributes

---

## Migration Path (v1.0 → v2.0)

### Schema Evolution

**v1.0 (Current):**
```python
has_offering: bool = False
offering_type: Optional[Literal["blood_offering", "incense", "crystals"]] = None
```

**v1.5 (Hybrid):**
```python
has_offering: bool = False
offering_type: Optional[Literal["blood_offering", "incense", "crystals"]] = None
offering_item: Optional[str] = None  # NEW: Specific item name (overrides offering_type)
```

**v2.0 (Full Item Selection):**
```python
has_offering: bool = False
offering_items: List[str] = []  # Replaces offering_type + offering_item
```

### Code Changes Required

**v1.0 → v1.5:**
1. Add `offering_item` field to PlayerAction schema
2. Update `consume_offering()` to check `offering_item` first, fall back to `offering_type`
3. Add fuzzy matching for item names (e.g., "purification incense" → "Purification Incense")
4. No prompt changes needed (field is optional)

**v1.5 → v2.0:**
1. Replace `offering_type` + `offering_item` with `offering_items: List[str]`
2. Update `consume_offering()` → `consume_offerings()` (plural, loop through list)
3. Add inventory display to player prompt (dynamic)
4. Add schema validation for item names
5. Update DM prompt to handle multi-item offerings
6. Update JSONL logging for multiple `inventory_changes` entries

### Fixture Compatibility

**v1.0 fixtures:**
```json
{
  "has_offering": true,
  "offering_type": "incense"
}
```

**v1.5 fixtures (backward compatible):**
```json
{
  "has_offering": true,
  "offering_type": "incense",
  "offering_item": null  // Optional, defaults to category-based
}
```

**v2.0 fixtures (breaking change):**
```json
{
  "has_offering": true,
  "offering_items": ["Purification Incense"]  // Must migrate old fixtures
}
```

---

## Implementation Notes

### Current Code Locations

**Offering consumption logic:**
- `scripts/aeonisk/multiagent/mechanics.py:consume_offering()` - Core consumption function
- `scripts/aeonisk/multiagent/dm.py:2281-2298` - Pre-narration consumption (path 1)
- `scripts/aeonisk/multiagent/dm.py:3128-3145` - Pre-narration consumption (path 2)

**Schema definitions:**
- `scripts/aeonisk/multiagent/schemas/player_action.py:117-125` - Player action fields
- `scripts/aeonisk/multiagent/schemas/action_resolution.py:27-50` - InventoryChange model

**Prompt guidance:**
- `scripts/aeonisk/multiagent/prompts/claude/en/player.yaml:280-285` - Mandatory field rules
- `scripts/aeonisk/multiagent/prompts/claude/en/player.yaml:358-376` - Offering requirements
- `scripts/aeonisk/multiagent/prompts/claude/en/player.yaml:317-318` - Example with inline comments

### Testing Strategy

**Unit tests needed (v2.0):**
- Test exact-match item consumption
- Test fuzzy-match fallback
- Test multi-item consumption
- Test partial consumption (some items missing)
- Test item name validation

**Integration tests needed (v2.0):**
- Test player LLM correctly lists exact item names
- Test DM narration reflects actual items consumed
- Test JSONL logging for multiple offerings

**Regression tests:**
- Ensure v1.0 fixtures still work in v1.5/v2.0
- Ensure category-based fallback still works

---

## Open Questions

1. **Item naming convention:** Should we enforce canonical item names or allow aliases?
   - Example: "Purification Incense" vs "purification incense" vs "incense (purification)"

2. **Offering effectiveness:** Should different items have different mechanical effects?
   - Example: "Rare Incense" → Void -2, "Common Incense" → Void -1

3. **Offering combinations:** Should some rituals require specific combinations?
   - Example: "Blood + Crystal" for binding rituals, "Incense only" for divination

4. **Inventory visibility:** Should player always see full inventory or filtered by context?
   - Pro: Full list → Player aware of all options
   - Con: Full list → Prompt bloat, irrelevant items (why list "Medkit" during ritual?)

5. **Failed consumption handling:** What happens if player declares offering but doesn't have it?
   - Current: Mechanics return `None`, DM applies +1 void penalty
   - Alternative: Force player to re-declare action (validation failure)

---

## Decision Log

**2025-11-02:** Implemented category-based system (v1.0) to fix core bug. Punted full item selection to future enhancement after gathering usage data.

**Next decision point:** After 50-100 sessions with v1.0, analyze:
- How often do players specify `offering_type`?
- Do LLM-generated narratives mention specific items?
- Are there cases where category system fails player intent?

If yes to above → prioritize v1.5 (hybrid). If no → stick with v1.0 (YAGNI principle).
