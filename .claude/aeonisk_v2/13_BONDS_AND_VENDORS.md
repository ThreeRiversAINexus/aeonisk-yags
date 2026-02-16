# Spec 13: Bond System Completion & Vendor Spawning

**Priority:** P3 (Wave 4 -- Parallel After Wave 2)
**Status:** Not started
**Dependencies:** None
**Estimated Scope:** Medium

---

## Problem Statement

Two independent subsystems are each approximately 90% complete but have gaps
that prevent them from appearing in live sessions naturally.

### Bond System Gaps

The bond system has comprehensive mechanics (71 tests passing), Pydantic
schemas, auto-transitions (Void 7 -> DORMANT, Void <7 -> ACTIVE, Void 10 ->
VOID_LOCKED), sacrifice mechanics (+5 Willpower, -2 SC), and DM prompt
integration. However:

1. **Characters start without bonds by default.** Unless the session config
   explicitly specifies pre-story bonds, characters have no `bonds` attribute
   initialized. The bond matrix generator (`session.py:850-933`) creates bonds
   during session setup, but it is only invoked when the session config
   requests it. A character that arrives without bonds has no empty list --
   the attribute may not exist at all on the character state.

2. **No opt-out config flag.** There is no `bonds_enabled: bool` in the
   session config to disable bond generation for experiments that do not
   need it. The bond matrix generator always runs if party_size >= 2 and
   bonds are configured, but there is no way to suppress it without removing
   the config section entirely.

3. **Bond formation is narrative-only.** Players cannot declare "I want to
   form a bond with X" as an explicit action. The `ActionType` enum
   (`shared_types.py:27-41`) has no `BOND_FORMATION` or equivalent type.
   Bond formation requires an Intimacy Ritual skill check
   (Empathy x Intimacy Ritual + d20) per the design doc, but this is not
   wired into the action resolution pipeline. Bonds can only be created
   pre-story via the matrix generator or via DM fiat in RoundSynthesis.

4. **Bond breaking is narrative-only.** The sacrifice mechanic
   (`mechanics.py:3719-3795`) sets a bond to SEVERED status, but there is no
   explicit player action to break a bond. Breaking would cost -2 SC and
   trigger a narrative crisis, but the action type does not exist.

5. **Auto-transitions untested in live sessions.** The `check_bond_dormancy()`
   method (`mechanics.py:3797-3839`) is unit-tested but has never been
   triggered in a live session. The wiring between void_change application and
   bond dormancy checking may have integration gaps.

### Vendor Spawning Gaps

Vendors work when pre-configured via `persistent_vendors` in the session
config (`session.py:303-361`) or when NPCs are spawned with `is_vendor: true`.
However:

1. **DM never spontaneously spawns vendors.** During downtime or market
   scenes, the DM has no prompt guidance to spawn a vendor NPC. The DM prompt
   for scenario generation mentions "safe zones" and "markets" but does not
   instruct the DM to create vendor NPCs with inventory. The only vendor
   spawning path is config-driven.

2. **No vendor spawn instruction in DM synthesis YAML.** The RoundSynthesis
   schema (`schemas/story_events.py`) has `npc_spawns` but no guidance telling
   the DM to populate vendor fields (`is_vendor`, `vendor_inventory`,
   `accepts_purchases`) when spawning a market NPC.

3. **NPC vendor inventory is empty by default.** When an NPC is spawned with
   `is_vendor: true` but no `vendor_inventory`, the NPC claims to sell things
   but has nothing to sell. The DM must populate the inventory, but there is
   no prompt guidance for what items/prices to generate.

---

## Current Implementation

### Bond System

#### Bond Schema (`schemas/shared_types.py:307-392`)

Complete Pydantic model with:
- `BondType` enum (6 types): KINSHIP, ASCENDANCY, DEBT, VOIDWARD, PASSION, FACTION
- `BondStatus` enum (4 states): ACTIVE, DORMANT, SEVERED, VOID_LOCKED
- `BondTargetType` enum (3 types): CHARACTER, OBJECT, ENTITY
- `Bond` model: bond_id, character_a, character_b, bond_type, status,
  formed_round, witnessed_by, bond_target_type, codex_registered,
  narrative_description

#### Bond Matrix Generator (`session.py:835-933`)

- Called during session setup when party_size >= 2
- `_generate_bond_matrix()` (line 935): Creates bond network structure
  deterministically using random seed
- `_generate_bond_narratives()`: LLM generates backstory narratives for bonds
- Bonds are appended to `character_state.bonds` (lines 916-919)
- Characters must already have a `bonds` attribute (list) on character_state

#### Bond Mechanics (`mechanics.py:3690-3900+`)

- `get_bond_soak_bonus()` (line ~3700): +1 Soak when defending bonded partner
- `process_bond_sacrifice()` (line 3719): Sacrifice bond for +5 Willpower,
  sets SEVERED, +1 Void, +1 Soul Debt, -1 Empathy
- `check_bond_dormancy()` (line 3797): Auto-transitions based on Void score
  - Void >= 7: ACTIVE -> DORMANT
  - Void < 7: DORMANT -> ACTIVE
  - Void = 10: any -> VOID_LOCKED (permanent)

#### Bond Validation (`mechanics.py`)

- `validate_bond_formation()`: Checks Void < 7, bond count < 3 (or < 1 for
  Freeborn), not already bonded to target
- Used by unit tests but not wired into any player action pipeline

#### DM Bond Context (`dm.py:7497-7528, 7921-7952`)

Two locations build bond_matrix strings for DM prompts:
- Lines 7497-7528: For action resolution prompts
- Lines 7921-7952: For synthesis/scenario prompts

Format:
```
Active Party Bonds:
  [check] Sera Karsel <-> Thane Vael (kinship) - Shared blood oath
  [circle] Kaelen <-> Unit-7 (passion) - DORMANT (Void >= 7)
Bond Status: check=ACTIVE, circle=DORMANT, x=SEVERED, warning=VOID_LOCKED
```

#### Bond Prompt YAML

`dm_bond_mechanics.yaml` exists in `prompts/claude/en/dm/` but loading
conditions and content were not examined.

#### BondStatusChange in RoundSynthesis (`schemas/story_events.py:519+`)

```python
class BondStatusChange(BaseModel):
    character_name: str
    bond_partner: str
    bond_type: Literal["kinship", "ascendancy", "debt", "voidward", "passion", "faction"]
    new_status: Literal["active", "dormant", "severed", "void_locked"]
    reason: str
```

This is available in the RoundSynthesis schema for the DM to declare bond
transitions, but it is passive -- the DM must decide to include it.

### Vendor System

#### Persistent Vendors (`session.py:303-361`)

`_initialize_persistent_vendors()` reads `config['persistent_vendors']` and
creates `Vendor` objects with inventory, greeting, and type. Vendors are added
to `shared_state.current_vendors`.

#### NPC Vendor Fields (`npc_agent.py:308-314`)

```python
is_vendor: bool = False
vendor_inventory: List = field(default_factory=list)
vendor_greeting: Optional[str] = None
vendor_type: Optional[str] = None
accepts_purchases: bool = False
energy_purse: Optional['EnergyPurse'] = None
```

NPC vendors are the modern path (replacing legacy Vendor objects). They can
hold inventory, accept purchases, and dialogue with players.

#### DM Scenario Hints (`dm.py:2422-2429`)

The DM scenario generation has keyword-based location classification:

```python
safe_keywords = ['market', 'social', 'gathering', 'festival', 'ceremony',
                 'negotiation', 'diplomatic', 'downtime']
```

When a scenario matches safe keywords, the DM gets a 70% chance of spawning
"Human traders." But this is in the scenario GENERATION phase, not in the
round-by-round synthesis. No vendor NPCs are actually created -- it just
influences the scenario description.

---

## Design Decisions (User Confirmed)

1. **Bonds exist by default (empty list).** Characters always have
   `bonds: [] = Field(default_factory=list)` on their character state. No
   attribute-missing errors.

2. **Bond matrices generated by default (opt-out).** Bond matrix generation
   runs automatically during session setup. A `bonds_enabled: bool = True`
   config flag allows opting out.

3. **Forming bonds is an explicit action.** Players can declare bond
   formation as an action, triggering the Intimacy Ritual skill check.

4. **Breaking bonds is an explicit action.** Players can declare bond
   breaking, which costs -2 SC and sets the bond to SEVERED.

5. **Agents prompted with bond context.** Player agents see their own bonds
   in their action prompt (who they are bonded with, bond status, available
   sacrifice). DM sees the full bond matrix.

6. **DM prompted to spawn vendors during downtime.** DM synthesis prompts
   include vendor spawn suggestions when the scenario is in a safe zone or
   market area.

---

## Proposed Solution

### Phase 1: Bond Default Initialization

#### 1.1 Character state always has bonds list

Ensure every character state object has a `bonds` attribute initialized to
an empty list. This may require changes in the character state model (likely
in the session config loading code or character creation).

Find where `character_state` objects are created and ensure `bonds = []` is
always present:

```python
# In character state creation (wherever character_state is built from config):
character_state.bonds = getattr(character_state, 'bonds', [])
```

If `character_state` is a Pydantic model, add the field:

```python
bonds: List[Bond] = Field(default_factory=list, description="Active bonds")
```

If `character_state` is a dict-like object, ensure the key exists:

```python
if 'bonds' not in character_state:
    character_state['bonds'] = []
```

#### 1.2 Opt-out config flag

Add `bonds_enabled` to session config schema:

```json
{
  "bonds_enabled": true,
  "bonds_config": {
    "min_bonds": 2,
    "max_bonds": 4,
    "generate_backstories": true
  }
}
```

The session setup code checks this flag:

```python
# In session setup, before bond matrix generation:
bonds_enabled = self.config.get('bonds_enabled', True)  # Default: ON

if bonds_enabled and len(player_agents) >= 2:
    await self._generate_party_bonds(player_agents, ...)
else:
    logger.info(f"Bond generation skipped (bonds_enabled={bonds_enabled})")
```

### Phase 2: Bond Formation as Explicit Action

#### 2.1 Add BOND_FORMATION action type

Extend the `ActionType` enum (`shared_types.py:27-41`):

```python
class ActionType(str, Enum):
    # ... existing types ...
    BOND_FORMATION = "bond_formation"  # Intimacy Ritual to form new bond
    BOND_SACRIFICE = "bond_sacrifice"  # Sacrifice bond for Willpower surge
```

#### 2.2 Bond formation in action resolution

When the DM resolves a `BOND_FORMATION` action:

1. Check prerequisites via `validate_bond_formation()` (already exists in
   mechanics.py)
2. Roll Empathy x Intimacy Ritual + d20
3. On success: Create Bond object, add to both participants' bonds lists
4. On failure: No bond formed, possible Void consequence

The DM's `ActionResolution` structured output already supports arbitrary
action types. The key change is that the resolution pipeline must:

a. Detect `action_type == "bond_formation"` in the adjudication phase
b. Extract the bond target from the action
c. Call `validate_bond_formation()` to check prerequisites
d. If valid, create and register the bond after successful resolution

```python
# In dm.py adjudicate() method, after resolution:
if action.get('action_type') == 'bond_formation':
    bond_target_name = action.get('target_character')
    character_name = action.get('character_name')

    # Find both agents
    char_agent = self._find_agent_by_name(character_name)
    target_agent = self._find_agent_by_name(bond_target_name)

    if char_agent and target_agent and _resolution_success(resolution):
        # Create bond
        bond = Bond(
            bond_id=f"bond_live_{mechanics.current_round}_{character_name[:3]}_{bond_target_name[:3]}",
            character_a=character_name,
            character_b=bond_target_name,
            bond_type=BondType.KINSHIP,  # DM determines type in narration
            status=BondStatus.ACTIVE,
            formed_round=mechanics.current_round,
            witnessed_by=[],  # Witness tracking deferred
            narrative_description=resolution.narrative[:200]
        )

        # Add to both characters
        char_agent.character_state.bonds.append(bond)
        target_agent.character_state.bonds.append(bond)

        logger.info(f"Bond formed: {character_name} <-> {bond_target_name} ({bond.bond_type.value})")
```

#### 2.3 Bond sacrifice as explicit action

When a player declares a sacrifice action:

1. Find the bond with the specified partner
2. Call `process_bond_sacrifice()` (already exists in mechanics.py:3719)
3. Apply effects: +5 Willpower bonus, +1 Void, +1 Soul Debt, -1 Empathy,
   bond -> SEVERED

```python
if action.get('action_type') == 'bond_sacrifice':
    bond_target_name = action.get('target_character')
    character_name = action.get('character_name')
    char_agent = self._find_agent_by_name(character_name)

    if char_agent:
        result = mechanics.process_bond_sacrifice(
            character_name=character_name,
            character_bonds=char_agent.character_state.bonds,
            bond_target=bond_target_name,
            current_round=mechanics.current_round
        )

        if result['success']:
            # Apply void change
            char_agent.character_state.void_score += result['void_change']
            # Apply soulcredit penalty (-2 SC)
            if self.shared_state:
                self.shared_state.adjust_soulcredit(
                    -2, reason=f"Bond sacrifice: {character_name} severed bond with {bond_target_name}"
                )
            logger.info(f"Bond sacrificed: {character_name} severed bond with {bond_target_name}")
```

### Phase 3: Bond Auto-Transition Wiring

#### 3.1 Wire void changes to bond dormancy checks

After every void_change application, call `check_bond_dormancy()`:

```python
# In the void_change application code (dm.py or mechanics.py):
# After applying void change to character:

if hasattr(char_agent.character_state, 'bonds') and char_agent.character_state.bonds:
    dormancy_result = mechanics.check_bond_dormancy(
        character_name=char_agent.character_state.name,
        character_bonds=char_agent.character_state.bonds,
        current_void=char_agent.character_state.void_score,
        previous_void=previous_void_score
    )

    if dormancy_result['status_changed']:
        for change in dormancy_result['changes']:
            logger.info(
                f"Bond transition: {char_agent.character_state.name} <-> "
                f"{change['partner']} : {change['old_status']} -> {change['new_status']}"
            )
            # Log to JSONL
            if mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_bond_status_change(
                    round_num=mechanics.current_round,
                    character_name=char_agent.character_state.name,
                    bond_partner=change['partner'],
                    old_status=change['old_status'],
                    new_status=change['new_status'],
                    reason=change.get('reason', 'void_threshold')
                )
```

Find all code locations where `void_score` is modified and add this check.
Key locations:

- `dm.py`: After void_change from ActionResolution effects
- `mechanics.py`: After void_change from environmental void exposure
- `dm.py`: After void_change from RoundSynthesis

### Phase 4: Player Bond Context in Prompts

#### 4.1 Show bonds in player action prompt

Players should see their own bonds when deciding actions:

```python
# In player.py, when building the action declaration prompt:

bond_context = ""
if hasattr(self.character_state, 'bonds') and self.character_state.bonds:
    bond_lines = []
    for bond in self.character_state.bonds:
        status_icon = {
            "active": "[ACTIVE]",
            "dormant": "[DORMANT]",
            "severed": "[SEVERED]",
            "void_locked": "[VOID-LOCKED]"
        }.get(bond.status.value, "[?]")

        benefits = ""
        if bond.status == BondStatus.ACTIVE:
            benefits = " -- +2 ritual bonus, +1 soak defending them, sacrifice available"

        bond_lines.append(
            f"  - {bond.character_b} ({bond.bond_type.value}) {status_icon}{benefits}"
        )

    bond_context = "Your Bonds:\n" + "\n".join(bond_lines)
```

### Phase 5: Vendor Spawn Prompting

#### 5.1 DM synthesis prompt for vendor spawning

Add vendor spawn guidance to the DM synthesis YAML prompts. Create or extend
a prompt module that loads during synthesis when the scenario is in a safe
zone:

```yaml
# prompts/claude/en/dm/dm_synthesis_vendor_guidance.yaml
load_when: "synthesis_phase and scenario_is_safe_zone"

content: |
  ## Vendor Spawning (Optional)

  If this round takes place in a market, safe zone, or social hub, consider
  spawning a vendor NPC. Vendors provide essential game loop elements:
  currency flow, item acquisition, and social interaction.

  To spawn a vendor, include in npc_spawns:
  - Set is_vendor: true
  - Set vendor_type: "human_trader", "vending_machine", or "supply_drone"
  - Populate vendor_inventory with 3-5 items (name, description, prices)
  - Set accepts_purchases: true
  - Set vendor_greeting with a flavorful market pitch

  Item price guidelines (in energy currency):
  - Consumable food (+2 HP): 1-2 Grain
  - Ritual offering (blood/incense): 2-3 Drip
  - Basic tool: 3-5 Spark
  - Equipment upgrade: 5-8 Spark
  - Rare/exotic item: 3+ Breath

  Do NOT spawn vendors in:
  - Active combat zones
  - Void-corrupted areas (Void >= 7)
  - Hostile territory with no neutral NPCs
```

#### 5.2 Vendor spawn detection in synthesis processing

When the DM includes `is_vendor: true` in an `npc_spawns` entry in
RoundSynthesis, the session processing code should set up the NPC with
vendor capabilities:

```python
# In session.py synthesis processing, when spawning NPCs:
if npc_spawn.get('is_vendor', False):
    npc.is_vendor = True
    npc.accepts_purchases = True
    npc.vendor_type = npc_spawn.get('vendor_type', 'human_trader')
    npc.vendor_greeting = npc_spawn.get('vendor_greeting', 'Looking to trade?')

    # Parse vendor inventory from synthesis
    vendor_items = npc_spawn.get('vendor_inventory', [])
    for item_data in vendor_items:
        from .energy_economy import VendorItem
        item = VendorItem(
            name=item_data['name'],
            description=item_data.get('description', ''),
            price_spark=item_data.get('price_spark', 0),
            price_grain=item_data.get('price_grain', 0),
            price_drip=item_data.get('price_drip', 0),
            price_breath=item_data.get('price_breath', 0)
        )
        npc.vendor_inventory.append(item)

    logger.info(f"Vendor NPC spawned: {npc.name} with {len(npc.vendor_inventory)} items")
```

#### 5.3 Module routing for vendor prompt

In `dm.py`'s `_get_required_dm_modules()` method, add a condition to load the
vendor guidance prompt during synthesis when appropriate:

```python
def _get_required_dm_modules(self, phase: str, context: dict) -> List[str]:
    modules = []
    # ... existing module routing ...

    if phase == "synthesis":
        # Load vendor guidance in safe zones
        scenario_keywords = context.get('scenario_description', '').lower()
        safe_zone = any(kw in scenario_keywords for kw in [
            'market', 'social', 'gathering', 'festival', 'downtime',
            'neutral zone', 'safe zone', 'trading post'
        ])
        if safe_zone:
            modules.append("dm_synthesis_vendor_guidance")

    return modules
```

---

## Files to Modify

| File | Change |
|------|--------|
| `scripts/aeonisk/multiagent/schemas/shared_types.py` | Add `BOND_FORMATION` and `BOND_SACRIFICE` to ActionType enum. |
| `scripts/aeonisk/multiagent/session.py` | Check `bonds_enabled` config flag. Ensure character_state.bonds initialized to []. Wire bond formation/sacrifice in adjudication. Wire void->dormancy check. Vendor spawn processing in synthesis. |
| `scripts/aeonisk/multiagent/dm.py` | Handle `bond_formation` and `bond_sacrifice` action types in adjudicate(). Update `_get_required_dm_modules()` for vendor guidance. |
| `scripts/aeonisk/multiagent/mechanics.py` | No changes needed -- `validate_bond_formation()`, `process_bond_sacrifice()`, and `check_bond_dormancy()` already exist. |
| `scripts/aeonisk/multiagent/player.py` | Add bond context to player action prompts. |
| `scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_synthesis_vendor_guidance.yaml` | New file: vendor spawn guidance for DM synthesis. |
| `scripts/aeonisk/multiagent/jsonl_logger.py` | Add `log_bond_status_change()` and `log_bond_formation()` methods. |

---

## Test Plan

### Unit Tests

#### Bond Defaults (`tests/unit/test_bond_defaults.py` -- new file)

```python
def test_character_state_has_bonds_list():
    """Character state always has bonds attribute as empty list."""
    # Create character state from minimal config
    # Assert: character_state.bonds == []
    # Assert: isinstance(character_state.bonds, list)

def test_bonds_enabled_default_true():
    """bonds_enabled defaults to True when absent from config."""
    config = {"session_name": "test", "agents": {"dm": {}}}
    assert config.get('bonds_enabled', True) is True

def test_bonds_disabled_skips_generation():
    """bonds_enabled=False prevents bond matrix generation."""
    config = {"bonds_enabled": False}
    # Mock session setup, verify _generate_party_bonds not called

def test_bonds_enabled_runs_generation():
    """bonds_enabled=True (or absent) runs bond matrix generation."""
    config = {}  # No key = default True
    # Mock session setup, verify _generate_party_bonds called
```

#### Bond Formation Action (`tests/unit/test_bond_formation.py` -- new file)

```python
def test_bond_formation_action_type_exists():
    """ActionType enum has BOND_FORMATION value."""
    from scripts.aeonisk.multiagent.schemas.shared_types import ActionType
    assert ActionType.BOND_FORMATION == "bond_formation"

def test_bond_sacrifice_action_type_exists():
    """ActionType enum has BOND_SACRIFICE value."""
    from scripts.aeonisk.multiagent.schemas.shared_types import ActionType
    assert ActionType.BOND_SACRIFICE == "bond_sacrifice"

def test_bond_formation_creates_bond():
    """Successful bond formation action creates Bond on both characters."""
    # Setup: Two characters with bonds=[], Void < 7, bond count < 3
    # Simulate successful resolution of bond_formation action
    # Assert: Both characters have one bond in their bonds list
    # Assert: Bond references both characters

def test_bond_formation_fails_high_void():
    """Bond formation fails when either character has Void >= 7."""
    # Setup: Character A with void_score=7
    # Call validate_bond_formation()
    # Assert: Failure result

def test_bond_formation_fails_at_limit():
    """Bond formation fails when character already has 3 bonds."""
    # Setup: Character with 3 existing bonds
    # Call validate_bond_formation()
    # Assert: Failure result

def test_bond_sacrifice_severs_bond():
    """Bond sacrifice sets bond status to SEVERED."""
    # Setup: Character with one ACTIVE bond
    # Call process_bond_sacrifice()
    # Assert: Bond status == SEVERED

def test_bond_sacrifice_applies_costs():
    """Bond sacrifice applies +1 Void, +1 Soul Debt, -1 Empathy."""
    # Already tested in existing test_bond_sacrifice tests
    # Verify integration with adjudication pipeline

def test_bond_sacrifice_dormant_bond():
    """Can sacrifice a DORMANT bond (not only ACTIVE)."""
    # Setup: Character with one DORMANT bond
    # Call process_bond_sacrifice()
    # Assert: Success, bond -> SEVERED
```

#### Bond Auto-Transitions (`tests/unit/test_bond_transitions_integration.py`)

```python
def test_void_increase_triggers_dormancy():
    """Void change from 6->7 triggers ACTIVE->DORMANT transition."""
    # Setup: Character with ACTIVE bond, void_score=6
    # Apply void change +1 (to 7)
    # Call check_bond_dormancy()
    # Assert: Bond status == DORMANT

def test_void_decrease_triggers_reactivation():
    """Void change from 7->6 triggers DORMANT->ACTIVE transition."""
    # Setup: Character with DORMANT bond, void_score=7
    # Apply void change -1 (to 6)
    # Call check_bond_dormancy()
    # Assert: Bond status == ACTIVE

def test_void_10_triggers_void_lock():
    """Void reaching 10 triggers ACTIVE->VOID_LOCKED (permanent)."""
    # Setup: Character with ACTIVE bond, void_score=9
    # Apply void change +1 (to 10)
    # Call check_bond_dormancy()
    # Assert: Bond status == VOID_LOCKED

def test_void_locked_never_reverts():
    """VOID_LOCKED bond does not revert to ACTIVE even if Void decreases."""
    # Setup: Character with VOID_LOCKED bond, void_score=10
    # Apply void change -3 (to 7)
    # Call check_bond_dormancy()
    # Assert: Bond status == VOID_LOCKED (unchanged)

def test_severed_bond_not_affected_by_void():
    """SEVERED bonds are not affected by void transitions."""
    # Setup: Character with SEVERED bond, void_score=5
    # Apply void change +3 (to 8)
    # Call check_bond_dormancy()
    # Assert: Bond status == SEVERED (unchanged)
```

#### Player Bond Context (`tests/unit/test_player_bond_prompts.py`)

```python
def test_player_sees_bond_context():
    """Player action prompt includes bond information."""
    # Setup: Player agent with 2 bonds (one ACTIVE, one DORMANT)
    # Build action prompt
    # Assert: Prompt contains bond partner names
    # Assert: Prompt contains "[ACTIVE]" and "[DORMANT]"
    # Assert: Prompt contains "+2 ritual bonus" for ACTIVE bond

def test_player_no_bonds_no_context():
    """Player with empty bonds list does not see bond section."""
    # Setup: Player agent with bonds=[]
    # Build action prompt
    # Assert: "Your Bonds" not in prompt
```

#### Vendor Spawning (`tests/unit/test_vendor_spawn_prompts.py`)

```python
def test_vendor_prompt_loads_in_safe_zone():
    """DM synthesis loads vendor guidance when scenario is safe zone."""
    # Setup: scenario_description containing "market"
    # Call _get_required_dm_modules(phase="synthesis", context=...)
    # Assert: "dm_synthesis_vendor_guidance" in modules

def test_vendor_prompt_not_loaded_in_combat():
    """DM synthesis does NOT load vendor guidance in combat zones."""
    # Setup: scenario_description containing "ambush"
    # Call _get_required_dm_modules(phase="synthesis", context=...)
    # Assert: "dm_synthesis_vendor_guidance" not in modules

def test_vendor_npc_spawn_processing():
    """NPC spawn with is_vendor=True creates functional vendor."""
    # Setup: npc_spawn dict with is_vendor=True and vendor_inventory
    # Process spawn
    # Assert: NPC has is_vendor=True
    # Assert: NPC has vendor_inventory populated
    # Assert: NPC has accepts_purchases=True

def test_vendor_npc_spawn_empty_inventory():
    """NPC vendor spawn with no inventory creates vendor with empty list."""
    # Setup: npc_spawn dict with is_vendor=True, no vendor_inventory
    # Process spawn
    # Assert: NPC has is_vendor=True
    # Assert: NPC has vendor_inventory == []
    # Assert: Warning logged about empty inventory
```

---

## Open Questions

1. **Bond type in live formation:** When a player declares "I want to form a
   bond with X," how does the system determine the bond type? Options:
   a. Player specifies type in their action description
   b. DM determines type in ActionResolution narration
   c. System infers from faction relationships and character archetypes
   The spec currently assigns KINSHIP as default. The DM should determine type.

2. **Witness requirement enforcement:** Bond formation requires a witness per
   the design doc. Should the system enforce this (check that a third character
   is present in the scene) or trust the DM to narrate it?

3. **Bond formation skill check:** The Intimacy Ritual skill check
   (Empathy x Intimacy Ritual + d20) needs a DC. What is the base DC for
   bond formation? The design doc says it is a skill check but does not
   specify difficulty. Suggestion: DC 15 (moderate), reduced by -2 if both
   characters share a faction, increased by +3 if cross-faction.

4. **Bond breaking vs sacrifice:** Are these the same action or different?
   Currently, sacrifice (process_bond_sacrifice) gives +5 Willpower. Should
   "break bond" be a separate action that just severs without the Willpower
   bonus but also without the +1 Void cost?

5. **Vendor spawn frequency:** How often should the DM be prompted to spawn
   vendors? Every synthesis in a safe zone? Only when no vendors are present?
   A cooldown (max one vendor spawn per 3 rounds)?

6. **Vendor inventory generation:** Should the DM generate vendor inventory
   via structured output fields in the NPC spawn, or should the system
   generate inventory from templates based on vendor_type? The former gives
   DM creative control; the latter ensures balanced pricing.

7. **NPC energy_purse initialization:** Currently NPCs have
   `energy_purse: Optional[EnergyPurse] = None`. Should vendor NPCs
   automatically get an energy purse (so they can receive payment and give
   change)? This was noted as a gap in MEMORY.md: "currency transfers to
   NPCs silently fail (no purse)."

---

## Migration Notes

### Backward Compatibility

- `bonds_enabled` defaults to `True`. Existing configs without this field
  behave identically to today.
- `ActionType.BOND_FORMATION` and `BOND_SACRIFICE` are new enum values.
  Existing action types are unchanged. Player agents using older prompts
  will not generate these types unless their prompts are updated.
- Character states that already have `bonds` attributes are unaffected.
  Character states without `bonds` get an empty list default.
- Vendor spawning is additive -- it only occurs when the DM includes vendor
  fields in npc_spawns. No existing behavior changes.

### Test Coverage

| Area | Existing Tests | New Tests Needed |
|------|---------------|-----------------|
| Bond mechanics | 71 passing (test_bond*.py) | Bond default init, formation action, sacrifice action |
| Bond transitions | check_bond_dormancy unit tests | Void->dormancy integration wiring |
| Player prompts | test_player_prompts.py | Bond context in prompts |
| Vendor spawn | test_npc_vendor_purchases.py (12 tests) | DM synthesis vendor guidance, spawn processing |
| Config validation | test_session_config_validation.py | bonds_enabled flag |
