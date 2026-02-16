# Spec 12: Display & Observability Improvements

**Priority:** P3 (Wave 4 -- Parallel After Wave 2)
**Status:** Not started
**Dependencies:** 10_ENV_OBJECTS (for environmental object display section)
**Estimated Scope:** Small-Medium

---

## Problem Statement

The round status display (`session.py:_display_round_status`) is the primary
human-readable output during session execution. It is the only way a human
observer can understand the tactical state of a combat encounter at a glance.
Currently, the display has significant information gaps across all combatant
types, inconsistent formatting, and missing sections for key game systems.

### Gap 1: Missing Information by Combatant Type

**PCs (lines 3514-3654):** Most complete. Shows initiative, name, HP, position,
void score, faction, equipped weapons, carried weapons, inventory, energy purse,
seeds, and soulcredit. Does NOT show: active conditions/status effects, wounds,
stuns, or bonds.

**Enemies (lines 3656-3669):** Minimal display. Shows only initiative, name, HP,
and position. Does NOT show: void score (enemies have `void_score` field at
`enemy_agent.py:329`), weapons (enemies have `weapons` list at
`enemy_agent.py:335`), status effects (enemies have `status_effects` list at
`enemy_agent.py:343`), conditions, faction, stuns, wounds, or armor.

**NPCs (lines 3671-3693):** Shows initiative as `[--]` (hardcoded placeholder)
instead of actual initiative value. NPCs DO have real initiative values --
they are calculated at `session.py:1372` as `15 + random.randint(1, 20)` and
stored in `self._current_initiative[npc.agent_id]`. The display simply ignores
this and prints `[--]`. Also shows: name, HP, disposition with emoji, faction,
threat level. Does NOT show: void score, conditions, weapons, skills.

### Gap 2: Missing Display Sections

**No conditions section:** No combatant type shows active conditions (Stunned,
Prone, Inspired, Astral Barrier, etc.). Conditions are tracked per-agent
(`npc_agent.py:285` has `conditions: List[Condition]`, enemies have
`status_effects: List[str]`) but never displayed in the round status.

**No environmental objects section:** Environmental objects (doors, terminals,
barriers) are tracked in `shared_state.current_env_objects` but not shown in
the round status. Players see them in their entity prompt, but the human
observer does not.

**No target ID mapping table:** When free targeting mode is active (default),
all combatants have `tgt_xxxx` IDs. The human observer has no way to map
these IDs to actual names without reading debug logs. A target ID mapping
table would show `tgt_7a3f -> Tempest Enforcer (enemy)` for quick reference.

### Gap 3: Formatting Inconsistencies

- PC initiative is right-aligned in 2 digits: `[14]`. Enemy initiative uses
  the same format. NPC initiative is hardcoded `[--]`.
- PC health uses `12/27 HP` format. Enemy health uses same format. No
  inconsistency here, but wounds/stuns are never shown for any type.
- Disposition emojis for NPCs use a hardcoded dict at line 3685. Same dict
  is duplicated at line 1377 for initiative display.

---

## Current Implementation

### _display_round_status (`session.py:3505-3703`)

The method signature:

```python
def _display_round_status(
    self,
    initiative_order: List[tuple],    # [(init, agent_type, agent), ...]
    mechanics,                         # MechanicsEngine (for clocks)
    player_agents: List               # List of player agents
):
```

The method groups combatants by type:

```python
pcs = [(init, agent) for init, agent_type, agent in initiative_order if agent_type == 'player']
enemies = [(init, agent) for init, agent_type, agent in initiative_order if agent_type == 'enemy']
npcs = [(init, agent) for init, agent_type, agent in initiative_order if agent_type == 'npc']
```

Then displays each group in order: PCs -> Enemies -> NPCs -> Scene Clocks.

### PC Display Block (lines 3514-3654)

Extensive display with multiple sub-lines using `\u2514\u2500` (corner + line)
tree characters:

```
  Player Characters:
    [14] Vessel Sera Karsel     | 27/27 HP     | Near-PC         | Void 3/10
         +-- Faction: Sovereign Nexus
         +-- Equipped: Pulse Pistol [WOUND] | Shock Baton [STUN]
         +-- Inventory: Blood:1 | Incense:2
         +-- Energy: Drip:5 | Breath:3
         +-- Seeds: Raw (Fresh):2 | Hollows:1
         +-- Soulcredit: +5/10 (Good Standing)
```

### Enemy Display Block (lines 3656-3669)

Minimal single-line display:

```
  Enemies:
    [18] Tempest Enforcer       | 23/23 HP     | Near-Enemy
```

No sub-lines. No faction, weapons, void, conditions, or status effects.

### NPC Display Block (lines 3671-3693)

Two-line display with hardcoded `[--]` initiative:

```
  NPCs (Non-Combatants):
    [--] Surrendered Guard      | 15/23 HP     | friendly        [INACTIVE]
         +-- Faction: Tempest | Threat: non_combatant
```

NPC initiative is calculated at line 1372 (`15 + random.randint(1, 20)`) and
stored in `self._current_initiative[npc.agent_id]` at line 1374. The value
exists but is not passed to the display method.

### Scene Clocks Block (lines 3695-3701)

Simple display:

```
  Scene Clocks:
    * Ambush Chaos: 3/6
    * Civilian Exposure: 2/4 [FILLED]
```

---

## Design Decisions (User Confirmed)

1. **NPCs should always have initiative and display it.** The `[--]` hardcode
   must be replaced with the actual initiative value from
   `self._current_initiative`.

2. **All display improvements in one spec.** This spec covers all stdout
   display changes rather than spreading them across multiple specs.

---

## Proposed Solution

### Change 1: NPC Initiative Display

#### Problem

NPC initiative is calculated and stored but displayed as `[--]`.

#### Fix (`session.py:3692`)

Replace the hardcoded `[--]` with the actual initiative value:

```python
# Before (line 3692):
print(f"    [--] {npc.name:20s} | {health_str:12s} | {status_str:15s}{active_indicator}")

# After:
# Get actual initiative from the stored values
npc_init = self._current_initiative.get(npc.agent_id, 0)
print(f"    [{npc_init:2d}] {npc.name:20s} | {health_str:12s} | {status_str:15s}{active_indicator}")
```

Note: `_display_round_status` does not currently have access to `self` (it is
a method of the session class and DOES have self). The `_current_initiative`
dict is an attribute of the session instance. Since `_display_round_status` is
called from within the session's `_run_combat_round`, `self._current_initiative`
is accessible.

However, the method signature only receives `initiative_order`, `mechanics`,
and `player_agents`. The NPC initiative is already embedded in the
`initiative_order` tuples as the first element:

```python
npcs = [(init, agent) for init, agent_type, agent in initiative_order if agent_type == 'npc']
```

So `init` already contains the NPC's initiative value. The fix is simply:

```python
for init, npc in npcs:
    # ... existing code ...
    print(f"    [{init:2d}] {npc.name:20s} | {health_str:12s} | {status_str:15s}{active_indicator}")
```

The `init` variable is already available from the tuple unpacking at line 3674
but is never used in the format string. This is a one-line fix.

### Change 2: Enemy Detail Display

#### Problem

Enemy display shows only name, HP, and position. Missing: void score, weapons,
status effects, faction, wounds, stuns, conditions.

#### Fix (`session.py:3656-3669`)

Expand the enemy block to match PC display depth:

```python
# Display Enemies
if enemies:
    print("\n  Enemies:")
    for init, agent in enemies:
        # Health
        health = getattr(agent, 'health', '?')
        max_health = getattr(agent, 'max_health', '?')
        health_str = f"{health}/{max_health} HP"

        # Position
        position = getattr(agent, 'position', 'Unknown')
        position_str = str(position) if position != 'Unknown' else 'Unknown'

        # Void score (enemies have void_score at enemy_agent.py:329)
        void_score = getattr(agent, 'void_score', 0)
        void_str = f"Void {void_score}/10" if void_score > 0 else ""

        # Wounds and stuns
        wounds = getattr(agent, 'wounds', 0)
        stuns = getattr(agent, 'stuns', 0)
        damage_str = ""
        if wounds > 0 or stuns > 0:
            parts = []
            if wounds > 0:
                parts.append(f"{wounds}w")
            if stuns > 0:
                parts.append(f"{stuns}s")
            damage_str = f" ({', '.join(parts)})"

        # Main line
        void_suffix = f" | {void_str}" if void_str else ""
        print(f"    [{init:2d}] {agent.name:20s} | {health_str:12s}{damage_str} | {position_str:15s}{void_suffix}")

        # Faction
        faction = getattr(agent, 'faction', 'Unknown')
        if faction != "Unknown":
            print(f"         +-- Faction: {faction}")

        # Weapons (enemies have weapons list at enemy_agent.py:335)
        weapons = getattr(agent, 'weapons', [])
        if weapons:
            weapon_strs = []
            for wpn in weapons[:3]:  # Show first 3 weapons
                dmg_type = getattr(wpn, 'damage_type', 'wound').upper()
                weapon_strs.append(f"{wpn.name} [{dmg_type}]")
            print(f"         +-- Weapons: {' | '.join(weapon_strs)}")

        # Status effects (enemies have status_effects: List[str])
        status_effects = getattr(agent, 'status_effects', [])
        if status_effects:
            effects_str = ", ".join(status_effects[:5])  # Show first 5
            print(f"         +-- Status: {effects_str}")

        # Conditions (Condition objects, if the enemy has them)
        conditions = getattr(agent, 'conditions', [])
        if conditions:
            cond_strs = []
            for cond in conditions[:3]:
                if hasattr(cond, 'name') and hasattr(cond, 'penalty'):
                    penalty_str = f"{cond.penalty:+d}" if cond.penalty != 0 else ""
                    duration_str = f" ({cond.duration}r)" if hasattr(cond, 'duration') and cond.duration > 0 else ""
                    cond_strs.append(f"{cond.name}{penalty_str}{duration_str}")
            if cond_strs:
                print(f"         +-- Conditions: {', '.join(cond_strs)}")
```

### Change 3: Condition Display for PCs

#### Problem

PCs do not show active conditions in the round status. Conditions are tracked
via the structured output system (applied via `ActionResolution.effects.conditions`)
but never surfaced to the human observer.

#### Fix

PC conditions are stored differently from NPC/enemy conditions. PCs do not
have a `conditions` list on their agent object -- conditions are applied
through the mechanics engine and stored in session-level tracking. This
requires investigation of where PC conditions are currently stored.

Pseudocode for the common case (conditions stored on player agent):

```python
# After soulcredit display (line 3654):
conditions = getattr(agent, 'conditions', [])
if not conditions and hasattr(agent, 'character_state'):
    conditions = getattr(agent.character_state, 'conditions', [])
if conditions:
    cond_strs = []
    for cond in conditions[:5]:
        if hasattr(cond, 'name') and hasattr(cond, 'penalty'):
            penalty_str = f"{cond.penalty:+d}" if cond.penalty != 0 else ""
            duration_str = f" ({cond.duration}r)" if hasattr(cond, 'duration') else ""
            cond_strs.append(f"{cond.name}{penalty_str}{duration_str}")
        elif isinstance(cond, str):
            cond_strs.append(cond)
    if cond_strs:
        print(f"         +-- Conditions: {', '.join(cond_strs)}")
```

### Change 4: Environmental Objects Section

#### Problem

Environmental objects tracked in `shared_state.current_env_objects` are not
shown in the round status display.

#### Fix

Add a new section after Scene Clocks:

```python
# Display environmental objects if present
if (self.shared_state and self.shared_state.current_env_objects):
    print("\n  Environmental Objects:")
    for env_obj in self.shared_state.current_env_objects:
        # Object type label
        type_label = env_obj.object_type.value.upper()

        # Health (if destructible)
        health_str = ""
        if hasattr(env_obj, 'health') and env_obj.health is not None:
            max_hp = getattr(env_obj, 'max_health', env_obj.health)
            health_str = f" | {env_obj.health}/{max_hp} HP"
            if hasattr(env_obj, 'is_destroyed') and env_obj.is_destroyed:
                health_str += " [DESTROYED]"

        # Target ID (if assigned via 10_ENV_OBJECTS spec)
        id_str = ""
        if hasattr(env_obj, 'target_id') and env_obj.target_id:
            id_str = f" [{env_obj.target_id}]"
        else:
            id_str = f" [{env_obj.object_id}]"

        # State summary (key state flags)
        state_str = ""
        if env_obj.state:
            state_parts = []
            for key, value in env_obj.state.items():
                if key in ('destroyed', 'functional'):
                    continue  # Skip meta-state, shown via [DESTROYED]
                if isinstance(value, bool):
                    if value:
                        state_parts.append(key)
                else:
                    state_parts.append(f"{key}={value}")
            if state_parts:
                state_str = f" ({', '.join(state_parts)})"

        print(f"    {type_label:10s}{id_str} {env_obj.name}{health_str}{state_str}")
```

Example output:

```
  Environmental Objects:
    DOOR       [tgt_k3r8] Blast Door Alpha | 30/30 HP (locked)
    TERMINAL   [env_m2f5] Control Console (powered)
    BARRIER    [tgt_p9q1] Makeshift Barricade | 35/50 HP
```

### Change 5: Target ID Mapping Table

#### Problem

When free targeting mode is active, the human observer cannot easily map
`tgt_xxxx` IDs to actual character names without reading debug logs.

#### Fix

Add a target ID reference table at the end of the round status:

```python
# Display target ID mapping table (when free targeting is active)
if self.shared_state:
    target_id_mapper = self.shared_state.get_target_id_mapper()
    if target_id_mapper and target_id_mapper.enabled:
        all_ids = target_id_mapper.get_all_target_ids()
        if all_ids:
            print("\n  Target ID Reference:")
            for tid in sorted(all_ids):
                info = target_id_mapper.get_combatant_info(tid)
                if info:
                    type_label = info.get('type', 'unknown')
                    name = info.get('name', 'Unknown')
                    # Color-code by type for quick scanning
                    if type_label == 'player':
                        type_tag = "PC"
                    elif type_label == 'enemy':
                        type_tag = "ENEMY"
                    elif type_label == 'npc':
                        type_tag = "NPC"
                    elif type_label == 'vendor':
                        type_tag = "VENDOR"
                    elif type_label == 'env_object':
                        type_tag = "OBJECT"
                    else:
                        type_tag = type_label.upper()

                    print(f"    {tid} -> {name:25s} ({type_tag})")
```

Example output:

```
  Target ID Reference:
    tgt_3f8a -> Vessel Sera Karsel        (PC)
    tgt_7k2m -> Tempest Enforcer          (ENEMY)
    tgt_9p1q -> Surrendered Guard          (NPC)
    tgt_k3r8 -> Blast Door Alpha           (OBJECT)
```

### Change 6: Wounds and Stuns for All Types

#### Problem

Wounds and stuns are tracked for PCs (via mechanics engine), enemies
(`enemy_agent.py:301-302`), and NPCs (`npc_agent.py:283-284`) but never
displayed for any type.

#### Fix for PCs (extend line ~3521)

```python
# After health_str:
wounds = getattr(agent, 'wounds', 0)
stuns = getattr(agent, 'stuns', 0)
wound_str = ""
if wounds > 0:
    wound_str += f" | {wounds} wound{'s' if wounds != 1 else ''}"
if stuns > 0:
    wound_str += f" | {stuns} stun{'s' if stuns != 1 else ''}"

# Append to health display:
print(f"    [{init:2d}] {agent.character_state.name:20s} | {health_str:12s}{wound_str} | ...")
```

#### Fix for NPCs (extend line ~3692)

```python
wounds = getattr(npc, 'wounds', 0)
stuns = getattr(npc, 'stuns', 0)
damage_str = ""
if wounds > 0 or stuns > 0:
    parts = []
    if wounds > 0:
        parts.append(f"{wounds}w")
    if stuns > 0:
        parts.append(f"{stuns}s")
    damage_str = f" ({', '.join(parts)})"

print(f"    [{init:2d}] {npc.name:20s} | {health_str:12s}{damage_str} | ...")
```

### Change 7: Enemy Reasoning and Shared Intel in Stdout

#### Problem

Enemy declarations print a compact one-liner (session.py:1604) showing action,
target, weapon, HP, and position:

```
[Tempest Enforcer] (Init 18) Attack → Vessel Sera Karsel (tgt_3f8a) [Pulse Rifle] | 23/23 HP | Near-Enemy
```

But the enemy's **tactical reasoning** and **shared intel** — two of the most
interesting outputs of the enemy AI system — are invisible to the human observer.
The `reasoning` field explains *why* the enemy chose this action (e.g., "Target
is wounded and in the open — pressing the attack for a kill"), and `shared_intel`
shows what the enemy broadcasts to allies (e.g., "Moving to far position, provide
suppressing fire"). Both fields exist on `EnemyDeclaration` (enemy_combat.py:55-56)
and are populated by the enemy LLM, but only appear in JSONL logs and debug output.

The reasoning is truncated to 100 chars in the broadcast message (session.py:1630)
and to 50 chars in debug logs (enemy_combat.py:628, 835). The full text is never
shown to the human observer at any log level.

#### Fix (`session.py:1604`)

Print reasoning and shared_intel as sub-lines below the enemy declaration, matching
the tree-character format used for PC detail lines:

```python
# After the existing one-liner (line 1604):
print(f"\n[{agent.name}] (Init {initiative_score}) {action} → {target_display} [{weapon}] | {health_str} | {position_str}")

# NEW: Show reasoning (full, not truncated)
reasoning = declaration.get('reasoning', '')
if reasoning:
    print(f"         +-- Reasoning: {reasoning}")

# NEW: Show shared intel (what this enemy broadcasts to allies)
shared_intel = declaration.get('shared_intel')
if shared_intel:
    print(f"         +-- Shared Intel: {shared_intel}")
```

Example output:

```
[Tempest Enforcer] (Init 18) Attack → Vessel Sera Karsel (tgt_3f8a) [Pulse Rifle] | 23/23 HP | Near-Enemy
         +-- Reasoning: Target is wounded and exposed at Near-PC. Pressing the attack while they lack cover.
         +-- Shared Intel: Focus fire on the wounded target — they're nearly down.
```

This gives the human observer full visibility into enemy AI decision-making
without requiring debug log levels. The reasoning and intel are the primary
outputs that demonstrate whether enemy agents are making intelligent tactical
decisions, which is critical for evaluating the tactical module.

### Change 8: Disposition Emoji Deduplication

#### Problem

The disposition -> emoji mapping dict is duplicated at lines 1377 and 3685.

#### Fix

Extract to a module-level constant:

```python
# At module level in session.py:
NPC_DISPOSITION_EMOJI = {
    "friendly": "[F]",
    "neutral": "[N]",
    "wary": "[W]",
    "prisoner": "[P]"
}
```

Note: The current implementation uses unicode emojis. Consider whether
terminal compatibility requires fallback to ASCII indicators. The emoji
approach works in modern terminals but may not render correctly in all log
viewers.

---

## Files to Modify

| File | Change |
|------|--------|
| `scripts/aeonisk/multiagent/session.py` | All changes in `_display_round_status()` (lines 3505-3703). NPC initiative fix (one-line). Enemy detail expansion. Condition display. Env object section. Target ID table. Wounds/stuns for all types. Disposition dedup. |

---

## Test Plan

### Unit Tests (`tests/unit/test_display_round_status.py` -- new file)

Testing display output requires capturing stdout. Use `io.StringIO` with
`contextlib.redirect_stdout`, or mock `print()`.

```python
import io
from contextlib import redirect_stdout

def test_npc_initiative_shows_number():
    """NPC initiative shows actual value, not [--]."""
    # Setup: Create initiative_order with NPC entry (init=23)
    # Call _display_round_status
    # Capture stdout
    # Assert: "[23]" appears, "[--]" does not appear
    output = _capture_display_output(initiative_order, mechanics, players)
    assert "[23]" in output
    assert "[--]" not in output

def test_enemy_shows_weapons():
    """Enemy display includes weapon names and damage types."""
    # Setup: Enemy with weapons=[Weapon(name="Assault Rifle", damage_type="wound")]
    output = _capture_display_output(...)
    assert "Assault Rifle" in output
    assert "WOUND" in output

def test_enemy_shows_void_score():
    """Enemy display includes void score when non-zero."""
    # Setup: Enemy with void_score=5
    output = _capture_display_output(...)
    assert "Void 5/10" in output

def test_enemy_shows_status_effects():
    """Enemy display includes active status effects."""
    # Setup: Enemy with status_effects=["stunned", "suppressed"]
    output = _capture_display_output(...)
    assert "stunned" in output
    assert "suppressed" in output

def test_enemy_shows_wounds_stuns():
    """Enemy display includes wound and stun counts."""
    # Setup: Enemy with wounds=2, stuns=1
    output = _capture_display_output(...)
    assert "2w" in output
    assert "1s" in output

def test_pc_shows_wounds():
    """PC display includes wound count when non-zero."""
    # Setup: Player agent with wounds=1
    output = _capture_display_output(...)
    assert "1 wound" in output

def test_pc_shows_conditions():
    """PC display includes active conditions with penalties."""
    # Setup: Player with conditions=[Condition(name="Stunned", penalty=-3, duration=2)]
    output = _capture_display_output(...)
    assert "Stunned" in output
    assert "-3" in output

def test_env_objects_section_displayed():
    """Environmental objects section appears when objects exist."""
    # Setup: shared_state with current_env_objects containing a door
    output = _capture_display_output(...)
    assert "Environmental Objects:" in output
    assert "Blast Door" in output
    assert "DOOR" in output

def test_env_objects_section_hidden_when_empty():
    """Environmental objects section does not appear when no objects."""
    # Setup: shared_state with empty current_env_objects
    output = _capture_display_output(...)
    assert "Environmental Objects:" not in output

def test_target_id_table_displayed():
    """Target ID reference table appears when free targeting is active."""
    # Setup: target_id_mapper with assigned IDs
    output = _capture_display_output(...)
    assert "Target ID Reference:" in output
    assert "tgt_" in output
    assert "PC" in output or "ENEMY" in output

def test_target_id_table_hidden_when_disabled():
    """Target ID table does not appear when free targeting is disabled."""
    # Setup: target_id_mapper.enabled = False
    output = _capture_display_output(...)
    assert "Target ID Reference:" not in output

def test_npc_shows_faction_and_threat():
    """NPC display includes faction and threat level."""
    # Already passes (existing behavior at line 3693)
    output = _capture_display_output(...)
    assert "Faction:" in output
    assert "Threat:" in output

def test_scene_clocks_displayed():
    """Scene clocks section appears with correct format."""
    # Already passes (existing behavior at lines 3696-3701)
    output = _capture_display_output(...)
    assert "Scene Clocks:" in output

def test_enemy_shows_faction():
    """Enemy display includes faction when known."""
    # Setup: Enemy with faction="Tempest Coalition"
    output = _capture_display_output(...)
    assert "Tempest Coalition" in output

def test_enemy_declaration_shows_reasoning():
    """Enemy declaration stdout includes full reasoning text."""
    # Setup: Enemy declaration with reasoning="Target is wounded and exposed"
    # Capture stdout during declaration phase
    output = _capture_declaration_output(...)
    assert "Reasoning:" in output
    assert "Target is wounded and exposed" in output

def test_enemy_declaration_shows_shared_intel():
    """Enemy declaration stdout includes shared intel broadcast."""
    # Setup: Enemy declaration with shared_intel="Focus fire on wounded target"
    output = _capture_declaration_output(...)
    assert "Shared Intel:" in output
    assert "Focus fire on wounded target" in output

def test_enemy_declaration_hides_empty_intel():
    """Shared intel line not shown when shared_intel is None."""
    # Setup: Enemy declaration with shared_intel=None
    output = _capture_declaration_output(...)
    assert "Shared Intel:" not in output

def test_enemy_reasoning_not_truncated():
    """Reasoning in stdout should show full text, not truncated to 100 chars."""
    # Setup: Enemy declaration with reasoning longer than 100 chars
    long_reasoning = "A" * 150
    output = _capture_declaration_output(reasoning=long_reasoning)
    assert long_reasoning in output  # Full text, not truncated
```

### Helper for Tests

```python
def _capture_display_output(session, initiative_order, mechanics, player_agents):
    """Capture stdout from _display_round_status."""
    f = io.StringIO()
    with redirect_stdout(f):
        session._display_round_status(initiative_order, mechanics, player_agents)
    return f.getvalue()
```

---

## Open Questions

1. **Condition storage for PCs:** Where exactly are PC conditions stored?
   The Condition model is applied via ActionResolution, but the storage
   location on the player agent is not clear. NPCs have `conditions: List`
   on the dataclass. Do PCs have an equivalent, or are conditions tracked
   elsewhere (e.g., mechanics engine)?

2. **Terminal width:** The current display assumes wide terminals (80+
   columns). Enemy detail expansion adds more sub-lines. Should there be a
   compact mode for narrow terminals?

3. **Color support:** Should the display use ANSI color codes for type
   differentiation (green for PCs, red for enemies, yellow for NPCs)? This
   improves scannability but breaks log file readability.

4. **Environmental object display dependency:** The env object section
   requires fields from 10_ENV_OBJECTS (health, target_id, is_destroyed).
   If this spec is implemented before 10_ENV_OBJECTS, the env object section
   should display with graceful fallbacks (show objects without health info).

5. **Disposition emoji vs ASCII:** Current NPCs use unicode emojis for
   disposition. Should this be replaced with ASCII indicators (e.g., `[F]`
   for friendly) for better cross-terminal compatibility?

6. **Bond display:** Should the round status show active bonds between PCs?
   This would complement the bond_matrix that the DM sees in its prompt.
   Deferred to 13_BONDS_VENDORS or included here?

---

## Migration Notes

### JSONL Logging Impact

No new JSONL event types are needed. All changes in this spec are display-only
(`_display_round_status` stdout output). The JSONL logging system is unaffected
and `LOGGING_IMPLEMENTATION.md` does not need updates for this spec.

### Backward Compatibility

All changes are purely additive to the display output. No existing information
is removed -- only new sections and sub-lines are added. The display method
signature does not change.

The NPC initiative fix changes `[--]` to `[23]` (or whatever the actual value
is). This is a bug fix, not a behavior change -- the initiative was always
calculated and stored, just never displayed.

### Performance

The display method is called once per round. Adding target ID table and
env object iteration adds negligible overhead (iterating small lists).
No API calls or file I/O.
