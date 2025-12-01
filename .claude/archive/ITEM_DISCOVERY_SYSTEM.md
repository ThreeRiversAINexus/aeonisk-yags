# Item Discovery System

**Status:** ✅ Implementation Complete (Pending Testing)
**Date:** 2025-11-21
**Branch:** `economy-and-vending`

## Overview

The Item Discovery System allows players to find Raw Seeds, currency, and items through environmental investigation and NPC interactions. This system integrates with the existing energy economy, supporting the attunement ritual flow where Raw Seeds convert directly to currency.

## Core Principle

**DM-Authoritative Discovery via Structured Output**

- DM awards discoveries via `ItemEffect` in `ActionResolution.effects.item_discovery`
- Mechanics layer validates and enforces daily limits (abuse prevention)
- NO keyword detection - all awards via Pydantic schemas

## Economy Flow

```
Environmental Discovery (INVESTIGATE)
    ↓
Raw Seeds (raw_seed_fresh, raw_seed_aged)
    ↓
Attunement Ritual (execute_attunement)
    ↓
Currency (100 breath / 50 grain / 20 drip / 5 spark)

NPC Gifts (SOCIAL)
    ↓
Items, Currency, or Raw Seeds (via ItemEffect)
```

## Discoverable Items

### Raw Seeds (ONLY Discoverable Seed Type)

**CRITICAL:** Attuned Seeds are NOT discoverable. Raw Seeds convert to currency via attunement rituals.

- `raw_seed_fresh` (1-3): Fresh Raw Seeds with 10-14 cycles remaining
  - **Sources**: Healthy leyline plants, untouched caches, NPC gifts
  - **Rarity**: Uncommon (1-2 per discovery)

- `raw_seed_aged` (1-2): Aged Raw Seeds with 3-6 cycles remaining
  - **Sources**: Wilting plants, old stashes, corpse loot
  - **Rarity**: More common than fresh (2-3 per discovery)

**Seed discovery limits**: 3 per player per session (configurable)
**Quest rewards bypass limits**

### Currency (5 Types)

Added directly to `EnergyPurse`:

- `breath` (10-100): Smallest denomination, common finds
- `grain` (5-50): Agricultural currency, moderate value
- `drip` (5-20): Most common currency, universal
- `spark` (1-5): Largest standard unit, rare finds
- `hollow` (1-3): Illicit void energy, dangerous sources only

**Currency discovery limits**: 50 drip-equivalent per session (configurable)
**Quest rewards bypass limits**

### Standard Items

Any item name → quantity (added to inventory `Dict[str, int]`):

- `ration_pack` (1-3): Food items
- `medkit` (1-2): Medical supplies
- `echo_calibrator` (1): Valuable tools (rare!)
- `ritual_incense` (1-2): Ritual consumables
- `ammunition` (5-20): Weapon supplies
- `scrap_metal` (3-10): Crafting materials

## Discovery Sources

### Environmental Discovery (INVESTIGATE Actions)

- **Leyline plants**: 1-2 Raw Seeds (fresh if untouched, aged if wilting)
- **Corpses/defeated enemies**: Currency (drip, hollow), basic items (rations, medkits)
- **Supply caches**: Mixed items + currency (rations, tools, drip)
- **Abandoned containers**: Items left behind (equipment, food, tools)
- **Natural resources**: Forageable items in wilderness/ruins

### NPC Gifts (SOCIAL Actions)

- **Quest rewards**: Significant items/currency for completed tasks
- **Bribes/favors**: Currency or items in exchange for cooperation
- **Gratitude gifts**: Small items/currency from rescued NPCs
- **Information trades**: Items exchanged for secrets/intel

### Random Events (DM Awards)

- **Success bonuses**: Extra items for excellent rolls (margin ≥15)
- **Narrative rewards**: Items that advance the story
- **Lucky finds**: Thematic discoveries during exploration

## Quantity Scaling

Awards scale based on roll margin:

- **Critical success (margin ≥20)**: Maximum quantities (3 seeds, 20 drip, 3 items)
- **Excellent success (margin 15-19)**: High quantities (2 seeds, 15 drip, 2 items)
- **Good success (margin 10-14)**: Moderate quantities (1-2 seeds, 10 drip, 1-2 items)
- **Marginal success (margin 0-4)**: Minimal quantities (1 seed, 5 drip, 1 item)
- **Failure**: No discovery (omit `item_discovery` field entirely)

## Abuse Prevention

### Daily Limits (Configurable via Session Config)

```json
"discovery_limits": {
  "max_seeds_per_session": 3,
  "max_currency_per_session": 50,
  "quest_rewards_bypass_limits": true
}
```

**Defaults:**
- Seeds: 3 per session
- Currency: 50 drip-equivalent per session
- Quest rewards bypass limits

### Tracking

Daily limits tracked per player in `SharedState.discovery_tracking`:

```python
discovery_tracking = {
    "player_01": {
        "seeds_discovered": 2,
        "drip_discovered": 30
    }
}
```

### Farming Prevention

If a player tries to farm discoveries repeatedly:

1. **First discovery**: Full rewards
2. **Second discovery**: Reduced rewards (picked over)
3. **Third+ discovery**: Minimal/no rewards ("nothing left to find")

DM can narratively reflect this: "The area has been thoroughly looted already" or "The leyline plants here are all withered and seedless."

## Implementation

### Schema (action_effects.py)

```python
class ItemEffect(BaseModel):
    """
    Track item/seed/currency discovery and acquisition.

    Seed keys (converted to Seed objects by mechanics layer):
    - "raw_seed_fresh": Raw Seed with 10-14 cycles remaining
    - "raw_seed_aged": Raw Seed with 3-6 cycles remaining

    Currency keys (added directly to EnergyPurse):
    - "breath", "grain", "drip", "spark", "hollow"

    Standard items (added to character inventory Dict[str, int]):
    - Any other key: item name → quantity
    """
    items_added: Dict[str, int] = Field(
        ...,
        description="Items discovered/gifted (item_name → quantity). Use special seed keys for seeds. Empty dict = failed discovery."
    )
    source: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Discovery source: 'environmental_loot', 'leyline_plant', 'corpse_loot', 'npc_gift', 'quest_reward', 'supply_cache', etc."
    )
```

### ActionResolution Integration (action_resolution.py)

```python
class MechanicalEffects(BaseModel):
    # ... existing fields (damage, void, healing, etc.)

    item_discovery: Optional['ItemEffect'] = Field(
        default=None,
        description="Items/seeds/currency discovered or gifted (if action resulted in item acquisition). Used for environmental loot, NPC gifts, quest rewards. NOT for purchases (use purchase field)."
    )
```

### Discovery Validation (mechanics.py)

```python
@dataclass
class DiscoveryValidation:
    """Result of item discovery validation check."""
    is_valid: bool
    failure_reason: Optional[str] = None
    capped_items: Optional[Dict[str, int]] = None  # Items after applying limits

def validate_item_discovery(
    self,
    character_state: Any,
    item_effect: Any,
    player_id: str
) -> DiscoveryValidation:
    """
    Validate item discovery and apply daily limits.

    - Checks max_seeds_per_session (default: 3)
    - Checks max_currency_per_session (default: 50 drip-equivalent)
    - Quest rewards bypass limits
    - Returns validation result with capped quantities
    """
```

### Item Processing (mechanics.py)

```python
def process_item_effect(
    self,
    item_effect: Any,
    character_state: Any,
    player_id: str
) -> bool:
    """
    Process item discovery and add to character state.

    - Validates discovery (applies daily limits)
    - Converts seed keys to Seed objects
    - Adds currency to energy_purse
    - Adds items to inventory
    - Updates discovery tracking
    """
```

**Seed Key Conversion:**

```python
# raw_seed_fresh → Seed(SeedType.RAW, cycles=10-14)
if item_key == 'raw_seed_fresh':
    for _ in range(quantity):
        seed = Seed(
            seed_type=SeedType.RAW,
            cycles_remaining=random.randint(10, 14),
            origin=item_effect.source
        )
        character_state.energy_purse.seeds.append(seed)

# raw_seed_aged → Seed(SeedType.RAW, cycles=3-6)
elif item_key == 'raw_seed_aged':
    for _ in range(quantity):
        seed = Seed(
            seed_type=SeedType.RAW,
            cycles_remaining=random.randint(3, 6),
            origin=item_effect.source
        )
        character_state.energy_purse.seeds.append(seed)
```

**Currency Addition:**

```python
# Currency added directly to purse
currency_keys = ['breath', 'grain', 'drip', 'spark', 'hollow']
if item_key in currency_keys:
    current_value = getattr(character_state.energy_purse, item_key)
    setattr(character_state.energy_purse, item_key, current_value + quantity)
```

**Item Addition:**

```python
# Standard items added to inventory
else:
    current_quantity = character_state.inventory.get(item_key, 0)
    character_state.inventory[item_key] = current_quantity + quantity
```

### Session Integration (session.py)

```python
# Handle item discovery (seeds, currency, items from environment/NPCs)
item_discovery = effects.get('item_discovery') if effects else None
if item_discovery:
    try:
        success = mechanics.process_item_effect(
            item_effect=item_discovery,
            character_state=agent.character_state,
            player_id=agent.agent_id
        )
        if success:
            logger.info(f"Processed item discovery for {agent.character_state.name}")
        else:
            logger.warning(f"Item discovery processing failed for {agent.character_state.name}")
    except Exception as e:
        logger.error(f"Error processing item discovery for {agent.character_state.name}: {e}")
```

## DM Guidance

### Example: Leyline Plant Discovery

**Player action**: "I carefully examine the leyline-corrupted plant for Raw Seeds."

**Good roll (margin +8)**: Award 2 fresh seeds

```python
ActionResolution(
    narration="You find two healthy seed pods...",
    success_tier=SuccessTier.GOOD,
    margin=8,
    effects=MechanicalEffects(
        item_discovery=ItemEffect(
            items_added={"raw_seed_fresh": 2},
            source="leyline_plant"
        )
    )
)
```

**Marginal success (margin +2)**: Award 1 aged seed

```python
item_discovery=ItemEffect(
    items_added={"raw_seed_aged": 1},
    source="leyline_plant"
)
```

### Example: Corpse Loot

**Player action**: "I search the fallen enemy's gear for supplies."

**Success**: Currency + items

```python
item_discovery=ItemEffect(
    items_added={
        "drip": 12,
        "hollow": 2,
        "ration_pack": 1
    },
    source="corpse_loot"
)
```

### Example: NPC Gift

**Player action**: "I offer to help the merchant in exchange for information."

**Success (gratitude)**: Moderate reward

```python
item_discovery=ItemEffect(
    items_added={
        "grain": 30,
        "ritual_incense": 1
    },
    source="npc_gift"
)
```

### Example: Quest Reward

**Player action**: "I complete the bounty and return for payment."

**Success**: Substantial reward (bypasses limits)

```python
item_discovery=ItemEffect(
    items_added={
        "spark": 5,
        "raw_seed_fresh": 2,
        "echo_calibrator": 1
    },
    source="quest_reward"
)
```

## Player Guidance

### Environmental Discovery (INVESTIGATE Actions)

**Example: Leyline Plant Search**

```python
InvestigateAction(
    intent="Search leyline-corrupted plant for Raw Seeds",
    description="I carefully examine the leyline-corrupted plant, looking for intact seed pods. Checking which seeds are still fresh versus withered, avoiding void-corrupted sections that might be dangerous to handle.",
    attribute="Perception",
    skill="Awareness",
    difficulty_estimate=14,
    difficulty_justification="DC 14: Plant is accessible but requires discerning fresh seeds from aged/corrupted ones",
    action_type=ActionType.INVESTIGATE,
    target="tgt_leyline_plant"
)
```

**Example: Corpse Loot**

```python
InvestigateAction(
    intent="Search fallen enemy for supplies",
    description="I quickly pat down the corpse, checking pockets, belt pouches, and any equipment they were carrying. Looking for currency, ammunition, medkits, or anything useful before we need to move.",
    attribute="Perception",
    skill="Awareness",
    difficulty_estimate=10,
    difficulty_justification="DC 10: Basic corpse search, no special concealment",
    action_type=ActionType.INVESTIGATE,
    target="tgt_enemy_fallen"
)
```

### NPC Gifts (SOCIAL Actions)

**Example: Requesting Items**

```python
SocialAction(
    intent="Ask grateful civilian for supplies",
    description="I approach the civilian we just rescued and explain our situation: 'We're trying to help more people, but we're running low on supplies. Do you have any spare rations, medkits, or anything that could help?'",
    attribute="Charisma",
    skill="Charm",
    difficulty_estimate=12,
    difficulty_justification="DC 12: They're grateful for rescue, but supplies are scarce for everyone",
    action_type=ActionType.SOCIAL,
    target="tgt_civilian"
)
```

## Testing

### Unit Tests

**test_item_discovery.py** (21 tests, all passing):
- `TestItemEffectSchema`: Basic schema validation
- `TestSeedKeyConversion`: Seed key format verification
- `TestItemEffectIntegrationWithActionResolution`: Integration tests
- `TestDiscoverySourceTypes`: Source categorization

**test_discovery_validation.py** (structure only):
- `TestSeedKeyConversion`: Raw seed conversion logic
- `TestProcessItemEffect`: Processing flow
- `TestDiscoveryValidation`: Validation logic
- `TestAbusePrevention`: Daily limit enforcement
- `TestItemEffectIntegration`: Character state integration
- `TestDiscoverySourceValidation`: Source validation

### Test Session Config

**session_config_item_discovery_test.json**:
- Leyline garden scenario with multiple discovery opportunities
- Configurable daily limits (3 seeds, 50 drip)
- Tests environmental discovery (leyline plants, corpses, caches)
- Tests NPC gifts via social interactions
- Verifies daily limit enforcement
- 3 rounds, 1 player (Kade - scavenger archetype)

### Running Tests

```bash
# Unit tests
python -m pytest tests/unit/test_item_discovery.py -v
python -m pytest tests/unit/test_discovery_validation.py -v

# Integration test (session)
python3 scripts/run_multiagent_session.py \
  scripts/session_configs/session_config_item_discovery_test.json \
  --log-level INFO
```

### Verification

**Console output:**
```
✓ Loaded discovery limits: 3 seeds, 50 drip per session
✓ Processed item discovery for Kade
```

**Logs:**
```
INFO: Validated item discovery: raw_seed_fresh x2 (source: leyline_plant)
INFO: Converted seed key 'raw_seed_fresh' to Seed(RAW, cycles=12)
INFO: Added 2 Raw Seeds to Kade's energy_purse
```

**JSONL:**
```json
{
  "event_type": "action_resolution",
  "round": 1,
  "agent": "Kade",
  "effects": {
    "item_discovery": {
      "items_added": {"raw_seed_fresh": 2},
      "source": "leyline_plant"
    }
  }
}
```

## Files Modified

### Created Files
- `scripts/aeonisk/multiagent/schemas/action_effects.py:179-231` - ItemEffect class
- `scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_discovery.yaml` - DM guidance (266 lines)
- `scripts/session_configs/session_config_item_discovery_test.json` - Test config
- `tests/unit/test_item_discovery.py` - Schema tests (21 tests)
- `tests/unit/test_discovery_validation.py` - Validation tests (structure)
- `.claude/ITEM_DISCOVERY_SYSTEM.md` - This documentation

### Modified Files
- `scripts/aeonisk/multiagent/schemas/action_resolution.py:153` - Added item_discovery field to MechanicalEffects
- `scripts/aeonisk/multiagent/mechanics.py:136-150` - Added DiscoveryValidation dataclass
- `scripts/aeonisk/multiagent/mechanics.py:3099-3218` - Added validate_item_discovery()
- `scripts/aeonisk/multiagent/mechanics.py:3219-3350` - Added process_item_effect()
- `scripts/aeonisk/multiagent/mechanics.py:3351-3372` - Added module-level wrappers
- `scripts/aeonisk/multiagent/session.py:1460-1473` - Added item_discovery processing
- `scripts/aeonisk/multiagent/prompts/claude/en/player/player_action_investigate.yaml:110-138` - Added discovery examples
- `scripts/aeonisk/multiagent/prompts/claude/en/player/player_action_social.yaml:78-92` - Added NPC gift example

## Known Issues

None currently. System is implemented and unit tests pass. Requires integration testing via session run.

## Future Enhancements

1. **Rarity System**: Item discovery could have rarity tiers (common/uncommon/rare/legendary)
2. **Discovery History**: Track what player has already looted from each location
3. **Location-Based Loot Tables**: Pre-defined discovery tables per location type
4. **Critical Discovery**: Margin ≥20 = bonus rare items (e.g., unique equipment)
5. **Discovery Skills**: Specialized skills for seed hunting, scavenging, etc.

## Related Systems

- **Energy Economy**: Raw Seeds → Attunement → Currency
- **Vendor System**: NPCs with vendor_inventory can sell items (separate from gifts)
- **Consumption System**: Food items discovered can be consumed for +2 HP
- **Transfer System**: Items can be transferred between players
- **Crafting System**: Discovered materials can be used in crafting (future)

## Design Principles

✅ **DM-Authoritative**: DM awards discoveries via structured output
✅ **Structured Output**: All mechanics via Pydantic schemas (no keyword detection)
✅ **Abuse Prevention**: Configurable daily limits with tracking
✅ **Quest Reward Exemption**: Important rewards bypass limits
✅ **Thematic Consistency**: Discovery sources match narrative context
✅ **Quantity Scaling**: Better rolls = more/better items
✅ **Seed Economy Integration**: Only Raw Seeds discoverable, convert to currency via attunement

## Summary

The Item Discovery System provides a robust, abuse-resistant mechanism for players to find Raw Seeds, currency, and items through environmental investigation and NPC interactions. It integrates seamlessly with the existing energy economy and follows the project's core principle of DM-authoritative mechanics via structured output rather than keyword detection.
