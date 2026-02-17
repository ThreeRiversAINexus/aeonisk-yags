# 06: IFF/ROE -- Faction-Based Allegiance Reasoning and Selective Intel

**Priority:** P1
**Status:** Spec Draft (v2 -- simplified)
**Dependencies:** None (stealth interaction deferred)
**Estimated Scope:** Medium (combatant list refactor, SharedIntel refactor, prompt changes)

---

## Problem Statement

The current free targeting system assigns randomized `tgt_xxxx` IDs to hide agent
allegiance from LLMs, enabling IFF (Identification Friend or Foe) testing. However,
explicit relationship labels are displayed directly in the combatant list, defeating
the purpose:

- **Players see** `(player)` next to PCs, `(enemy)` next to enemies, and
  `(npc, friendly)` next to NPCs.
- **Enemies see** PC names with explicit relationship labels, health, weapons, and
  position -- full intel from the start.
- **NPCs see** everyone's relationship labels via the system prompt.

The relationship labels (`player`, `enemy`, `npc`, `ally`, `friendly`, `hostile`)
tell LLMs exactly who is friend and foe. This bypasses any IFF reasoning. Agents
know allegiance from the first round. SharedIntel broadcasts to all enemies globally
-- there is no selective sharing. This means:

1. **No IFF challenge.** LLMs never need to reason about friend vs foe because the
   system tells them via relationship labels. The randomized `tgt_xxxx` IDs are
   cosmetic only.

2. **No fog of war.** All agents have perfect battlefield awareness of allegiance.
   An enemy sniper at Extreme range knows exactly which targets are allies vs enemies.

3. **No intel asymmetry.** Enemy squads who have never encountered the party know
   all PC names, health, and weapons. Reinforcements arriving mid-combat have
   perfect knowledge.

4. **SharedIntel is global.** When one enemy shares intel, ALL enemies receive it
   immediately. There is no communication cost, range limitation, or selective
   targeting of intel recipients.

5. **ML training data lacks IFF signals.** Training data shows agents always knowing
   allegiance, so models learn no IFF reasoning. This is the primary motivation for
   the feature -- producing training data where models must reason about whether a
   given faction is friend or foe.

**Design Decisions (confirmed):**
- Remove relationship labels (`player`/`enemy`/`npc`/`ally`/`hostile`/`friendly`) from
  combatant lists. Faction NAMES (e.g., "ACG", "Freeborn", "Tempest") remain visible --
  faction affiliation is observable (uniforms, insignia, known groups).
- The IFF challenge: the LLM sees faction names and must reason about whether that
  faction is friend, foe, or neutral. The system does NOT tell it.
- All other info (name, health, weapons, position) remains visible. No progressive
  identity discovery -- the complexity is in allegiance reasoning, not identity
  discovery.
- PCs know each other by default (they are a party).
- Intel sharing is selective -- enemies specify recipients by `tgt_xxxx`. Recipients
  can be ANY target, including PCs (enabling accidental intel leaks from IFF errors).
- Player communication uses existing free dialogue (social action), not a structured
  intel pool.

---

## Current Implementation

### Combatant List Builder -- Full Relationship Display

**File:** `scripts/aeonisk/multiagent/dm.py` lines 7536-7578

The DM combatant list builder shows relationship type for all agents:

```python
# Player entries (line 7553)
combatant_lines.append(
    f"  - [{tid}] {info['name']} ({pronouns}, {health_text}{wounds_text})"
)

# NPC entries (line 7564)
combatant_lines.append(
    f"  - [{tid}] {info['name']} ({pronouns}, npc, {disposition})"
)

# Enemy entries (line 7567)
combatant_lines.append(
    f"  - [{tid}] {info['name']} ({pronouns}, {info['type']})"
)
```

Every agent sees every other agent's type (player/enemy/npc) and disposition. This
makes IFF trivial -- the system does the identification for them.

### Enemy Prompts -- Full PC Information

**File:** `scripts/aeonisk/multiagent/enemy_prompts.py` lines 440-483

The `_format_pc_target_info()` function gives enemies complete PC information:

```python
return f"""- {pc_name} [{pc_id}]
  Position: {pc_position} ({range_name.upper()} RANGE, {range_penalty} penalty)
  Health: {health_str}
  Defence Token: {watching_str}
  Weapons: {weapons_str}
  Threat Level: {threat_level}"""
```

Enemies know PC names, exact health percentages, weapons, and positions from the
first round. No discovery needed.

### Enemy Prompts -- Target Priority with Full Knowledge

**File:** `scripts/aeonisk/multiagent/enemy_prompts.py` lines 740-767

The `_format_target_priorities()` function sorts PCs by threat level:

```python
for i, (threat, pc_name, range_name, is_watching) in enumerate(threat_order[:3]):
    priority_label = ["PRIMARY", "SECONDARY", "TERTIARY"][i]
    section += f"\n{i+1}. {priority_label} THREAT: {pc_name} - {threat}"
```

Enemies receive a pre-sorted priority target list. They never need to assess targets
themselves.

### SharedIntel -- Global Broadcast

**File:** `scripts/aeonisk/multiagent/enemy_agent.py` lines 678-728 (SharedIntel class)

```python
class SharedIntel:
    def __init__(self):
        self.intel_pool: List[IntelItem] = []

    def add_intel(self, source_agent: str, intel: str, round_num: int):
        item = IntelItem(source_agent=source_agent, intel=intel, round=round_num)
        self.intel_pool.append(item)

    def get_recent_intel(self, current_round: int, lookback: int = 2):
        return [f"[ALLY {item.source_agent}] {item.intel}"
                for item in self.intel_pool
                if current_round - item.round <= lookback]
```

All enemies share a single `SharedIntel` pool. When enemy A adds intel, enemy B sees
it in the next round regardless of distance, line of sight, or communication ability.

**File:** `scripts/aeonisk/multiagent/enemy_combat.py` line 165

```python
self.shared_intel = SharedIntel()  # Single global pool
```

One pool for all enemies.

### TargetIDMapper -- Type Information Exposed

**File:** `scripts/aeonisk/multiagent/target_ids.py` lines 281-345

`get_combatant_info()` returns full type information:

```python
info = {
    'target_id': target_id,
    'agent_id': entity_id,
    'type': entity_type  # "player", "enemy", "npc", "vendor"
}
```

Any agent querying combatant info gets the full type classification.

### NPC System Prompt -- Relationship Displayed

**File:** `scripts/aeonisk/multiagent/npc_agent.py` lines 571-643

NPC system prompt includes full relationship information and stance:

```python
return f"""You are {self.npc.name}, a {self.npc.entity_type} NPC...
- Entity Type: {self.npc.entity_type} (neutral/ally/prisoner)
- Disposition: {self.npc.disposition} (friendly/neutral/wary/prisoner)
- Faction: {self.npc.faction}
{self._get_faction_context()}
"""
```

NPCs know their own faction and have a stance toward all other factions. They also
receive explicit relationship labels (`entity_type`, `disposition`) that tell them
who is friend and foe.

---

## Design Decisions

1. **Faction visible, relationship hidden.** All agents can see faction names (e.g.,
   "ACG", "Freeborn", "Tempest") for all targets. Faction affiliation is observable
   (uniforms, insignia, known groups). What the system does NOT provide is relationship
   labels: `player`, `enemy`, `npc`, `ally`, `hostile`, `friendly`. The LLM must
   reason about whether "Freeborn" is a threat or an ally based on its own faction
   knowledge and the scenario context.

2. **Full tactical info visible.** Name, health, weapons, and position are visible
   to all agents. There is no progressive identity discovery. The IFF challenge is
   purely about allegiance reasoning ("is this faction friend or foe?"), not about
   discovering who someone is.

3. **PCs know each other.** Party members know they are a party. The system can
   tell PCs which other targets are their party members (this is not an IFF challenge
   -- they traveled together).

4. **Selective intel sharing with tgt_xxxx recipients.** Enemies specify intel
   recipients by target_id, not by agent_id or relationship. Since the enemy LLM
   doesn't know which target_ids are allies vs enemies, it must reason from faction
   names. If it reasons wrong, intel leaks to the wrong side. This is a feature --
   IFF errors in communication produce valuable ML training signal.

5. **Asymmetric communication model.** Enemies use structured `shared_intel` field
   with explicit `intel_recipients` (list of target_ids). Players communicate via
   existing free dialogue (social action). Player dialogue appears in round narration
   that all PCs see. No structured intel pool needed for PCs.

6. **Leaked intel appears as intercepted communication.** When an enemy accidentally
   shares intel with a PC (wrong faction reasoning), the PC sees it in their prompt
   as an intercepted/overheard communication. The PC's LLM then reasons about what
   to do with it.

7. **DM always has full knowledge.** The DM sees all agents' true factions, names,
   types, and relationships. The DM's combatant list retains full information
   including relationship labels. Only agent-facing lists are stripped.

8. **Session config opt-in.** IFF is enabled per-session via `"iff_enabled": true`.
   Default false for backward compatibility. When disabled, current behavior is
   preserved (relationship labels shown, SharedIntel broadcasts globally).

---

## Proposed Solution

### Change 1: Strip Relationship Labels from Combatant Lists

**File:** `scripts/aeonisk/multiagent/dm.py` lines 7536-7578

When IFF is enabled, the combatant list shown to agents replaces relationship labels
with faction names. The DM's own list is unchanged.

**Current format (relationship labels):**
```
VALID TARGET IDS:
  - [tgt_7a3f] Ash Vex (she/her, 18/27 HP, 2w)          ← PC, no label but implied
  - [tgt_9b2c] ACG Enforcer (they/them, enemy)            ← explicit "enemy"
  - [tgt_4d1e] Captured Guard (he/him, npc, prisoner)     ← explicit "npc, prisoner"
  - [tgt_2f8a] Tempest Liaison (she/her, npc, friendly)   ← explicit "npc, friendly"
```

**New format (faction names, no relationship labels):**
```
DETECTED CONTACTS:
  - [tgt_7a3f] Ash Vex (she/her, Freeborn, 18/27 HP, 2w)
  - [tgt_9b2c] ACG Enforcer (they/them, ACG, 15/20 HP)
  - [tgt_4d1e] Captured Guard (he/him, ACG, prisoner)
  - [tgt_2f8a] Tempest Liaison (she/her, Tempest, 12/12 HP)
```

Key differences:
- `enemy` → faction name (e.g., `ACG`)
- `npc, friendly` → faction name only (e.g., `Tempest`)
- `player` label removed entirely, replaced with faction name
- Health info visible for all entities (not just PCs)
- `prisoner` status retained (observable physical state, not a relationship label)
- State tags from Spec 03 (`[ACTIVE]`, `[PRISONER]`, etc.) still apply

**Implementation:**

```python
def _build_iff_combatant_list(self, target_id_mapper, shared_state) -> str:
    """
    Build combatant list with faction names instead of relationship labels.
    Used when IFF mode is enabled.
    """
    all_target_ids = target_id_mapper.get_all_target_ids()
    if not all_target_ids:
        return ""

    combatant_lines = []
    for tid in sorted(all_target_ids):
        info = target_id_mapper.get_combatant_info(tid)
        if not info:
            continue

        name = info.get('name', 'Unknown')
        pronouns = info.get('pronouns', 'they/them')
        faction = info.get('faction', 'Unknown')
        health = info.get('health')
        max_health = info.get('max_health')

        # Health string (if available)
        health_str = f", {health}/{max_health} HP" if health is not None else ""

        # Wounds (if any)
        wounds = info.get('wounds', 0)
        wounds_str = f", {wounds}w" if wounds > 0 else ""

        # Observable state (prisoner, wounded, etc.) -- from Spec 03
        state_tag = _get_combatant_state_tag(info, tid, shared_state)

        line = f"  - [{tid}] {name} ({pronouns}, {faction}{health_str}{wounds_str}) {state_tag}"
        combatant_lines.append(line)

    header = "\n\n**DETECTED CONTACTS:**\n"
    return header + "\n".join(combatant_lines)
```

**DM list is unchanged.** The DM still sees `(player)`, `(enemy)`, `(npc, friendly)`
in its own resolution prompts. Only agent-facing prompts use the IFF format.

### Change 2: Strip Relationship Labels from Enemy Prompts

**File:** `scripts/aeonisk/multiagent/enemy_prompts.py` lines 440-483

Modify `_format_pc_target_info()` to show faction instead of implying "this is a PC
target":

**Current:**
```python
return f"""- {pc_name} [{pc_id}]
  Position: {pc_position} ({range_name.upper()} RANGE, {range_penalty} penalty)
  Health: {health_str}
  Defence Token: {watching_str}
  Weapons: {weapons_str}
  Threat Level: {threat_level}"""
```

The function name itself (`_format_pc_target_info`) and the section header
("PC TARGETS" or "THREAT ASSESSMENT") tell the enemy these are PCs. This must
be neutralized.

**New:** Merge all targets (PCs, enemies from other factions, NPCs) into a single
"DETECTED CONTACTS" list. No separate "PC TARGETS" section.

```python
def _format_contact_info_iff(
    target_name: str,
    target_id: str,
    faction: str,
    position: str,
    range_name: str,
    range_penalty: str,
    health_str: str,
    weapons_str: str,
    watching_str: str,
) -> str:
    """Format a single contact's info for IFF mode. No relationship labels."""
    return f"""- {target_name} [{target_id}]
  Faction: {faction}
  Position: {position} ({range_name.upper()} RANGE, {range_penalty} penalty)
  Health: {health_str}
  Defence Token: {watching_str}
  Weapons: {weapons_str}"""
```

**Remove `_format_target_priorities()`.** The pre-sorted PRIMARY/SECONDARY/TERTIARY
threat list tells enemies who to attack without reasoning. In IFF mode, the enemy
LLM must assess threats itself based on observed faction, weapons, and behavior.

### Change 3: Strip Relationship Labels from NPC Prompts

**File:** `scripts/aeonisk/multiagent/npc_agent.py` lines 571-643

When IFF is enabled, remove `entity_type` (neutral/ally/prisoner) from the NPC's
self-description. Keep faction. The NPC knows its own faction but must reason about
relationships to other factions.

**Current:**
```python
- Entity Type: {self.npc.entity_type} (neutral/ally/prisoner)
- Disposition: {self.npc.disposition} (friendly/neutral/wary/prisoner)
```

**New (IFF mode):**
```python
- Faction: {self.npc.faction}
```

`entity_type` and `disposition` are relationship labels relative to the party. In
IFF mode, the NPC reasons from faction context instead.

**Exception:** `prisoner` status is retained as observable physical state (bound,
restrained), not a relationship label.

### Change 4: Selective Intel Sharing with tgt_xxxx Recipients

**File:** `scripts/aeonisk/multiagent/enemy_agent.py` lines 678-728

Refactor SharedIntel from enemy-only global broadcast to a battlefield-wide pool
with explicit recipients specified by target_id.

```python
@dataclass
class IntelItem:
    """Single piece of shared tactical intelligence."""
    source_target_id: str      # tgt_xxxx of the sender (NOT agent_id)
    intel: str
    round: int
    recipients: Set[str]       # Set of tgt_xxxx IDs. REQUIRED -- no broadcast.


class SharedIntel:
    """
    Battlefield-wide intel sharing pool.

    Any agent can post intel with explicit recipient target_ids.
    Recipients can be ANY target -- the sender must reason about who
    is an ally based on faction names. If they reason wrong, intel
    leaks to the wrong side.
    """

    def __init__(self):
        self.intel_pool: List[IntelItem] = []

    def add_intel(
        self,
        source_target_id: str,
        intel: str,
        round_num: int,
        recipients: Set[str]
    ):
        """Add intelligence with explicit recipients."""
        if intel and intel.strip() and recipients:
            item = IntelItem(
                source_target_id=source_target_id,
                intel=intel.strip(),
                round=round_num,
                recipients=recipients
            )
            self.intel_pool.append(item)

    def get_recent_intel_for_target(
        self,
        target_id: str,
        current_round: int,
        lookback: int = 2
    ) -> List[str]:
        """Get intel addressed to a specific target_id."""
        recent = []
        for item in self.intel_pool:
            if current_round - item.round > lookback:
                continue
            if target_id in item.recipients:
                recent.append(
                    f"[FROM {item.source_target_id}] {item.intel}"
                )
        return recent
```

Key changes:
- `source_agent` → `source_target_id` (uses tgt_xxxx, not internal agent_id)
- `recipients` is REQUIRED (no more `None` = broadcast to all)
- `get_recent_intel` → `get_recent_intel_for_target` (queries by tgt_xxxx)
- Removed `[ALLY ...]` prefix -- sender might not be an ally
- The pool is battlefield-wide, not enemy-only

### Change 5: Extend EnemyDecision for tgt_xxxx Recipients

**File:** `scripts/aeonisk/multiagent/schemas/enemy_decision.py`

```python
class EnemyDecision(BaseModel):
    # ... existing fields ...

    shared_intel: Optional[str] = Field(
        default=None,
        max_length=300,
        description="Tactical observation to share with allies"
    )

    intel_recipients: Optional[List[str]] = Field(
        default=None,
        description=(
            "Target IDs (tgt_xxxx) of contacts you want to share intel with. "
            "Choose recipients from the DETECTED CONTACTS list based on faction "
            "allegiance. Only share with targets you believe are allies."
        )
    )
```

The enemy LLM must pick target_ids it believes are allies. If it picks a PC's
target_id by mistake (wrong faction reasoning), the intel leaks.

### Change 6: Inject Leaked Intel into PC Prompts

**File:** `scripts/aeonisk/multiagent/dm.py` (round context building)

When building a PC's prompt context, check if any intel items in the SharedIntel
pool list this PC's target_id as a recipient. If so, inject it:

```python
def _get_intercepted_intel_for_pc(
    self,
    pc_target_id: str,
    shared_intel: SharedIntel,
    current_round: int
) -> str:
    """
    Get any intel that was addressed to this PC by enemy agents.

    This happens when an enemy incorrectly identifies the PC as an ally
    (IFF error) and shares tactical intel with them.
    """
    intel_items = shared_intel.get_recent_intel_for_target(
        pc_target_id, current_round
    )
    if not intel_items:
        return ""

    lines = ["\n**INTERCEPTED COMMUNICATIONS:**"]
    lines.append("(You overheard the following from nearby contacts)")
    for item in intel_items:
        lines.append(f"  {item}")
    return "\n".join(lines)
```

### Change 7: Enemy Faction Context in Prompts

**File:** `scripts/aeonisk/multiagent/enemy_prompts.py`

Add a faction context section to the enemy system prompt that tells the enemy its
own faction and lets it reason about others:

```yaml
iff_context: |-
  ## Your Faction
  You are {faction_name}. You recognize fellow {faction_name} operatives as allies.

  ## Allegiance
  The DETECTED CONTACTS list shows all visible contacts with their faction.
  You must determine who is hostile, neutral, or friendly based on faction.
  The system will NOT tell you who is an ally or enemy -- you must reason
  from your knowledge of faction relationships.

  ## Communication
  Use shared_intel + intel_recipients to communicate with contacts you
  believe are allies. Specify their target IDs (tgt_xxxx) as recipients.
  WARNING: If you share intel with the wrong contact, they will receive it.
```

### Change 8: PC Party Context

**File:** `scripts/aeonisk/multiagent/prompts/claude/en/player/` (relevant YAML)

PCs need to know who their party members are. This is not IFF reasoning -- they
know their party. Inject party member target_ids so PCs can distinguish party
from unknown contacts:

```yaml
party_context: |-
  ## Your Party
  You are traveling with the following party members:
  {party_member_list}

  Other contacts on the DETECTED CONTACTS list are NOT party members.
  Determine their allegiance from their faction and observed behavior.
```

---

## Files to Modify

| File | Change |
|------|--------|
| `dm.py` | `_build_iff_combatant_list()` -- faction-based list when IFF enabled |
| `dm.py` | `_get_intercepted_intel_for_pc()` -- inject leaked intel into PC prompts |
| `dm.py` | Session config check for `iff_enabled` flag |
| `enemy_prompts.py` | Merge all targets into neutral "DETECTED CONTACTS" format |
| `enemy_prompts.py` | Remove `_format_target_priorities()` in IFF mode |
| `enemy_prompts.py` | Add faction context / IFF reasoning section |
| `npc_agent.py` | Strip `entity_type`/`disposition` labels in IFF mode |
| `enemy_agent.py` | Refactor SharedIntel: tgt_xxxx recipients, battlefield-wide pool |
| `enemy_combat.py` | Use new SharedIntel API (target_id-based) |
| `schemas/enemy_decision.py` | Add `intel_recipients` field (list of tgt_xxxx) |
| `target_ids.py` | Add `faction` to `get_combatant_info()` return dict |
| `session.py` | Read `iff_enabled` from session config, propagate to subsystems |
| `prompts/.../enemy.yaml` | IFF faction context section |
| `prompts/.../player.yaml` | Party context section |

---

## Test Plan

### Unit Tests

**File:** `tests/unit/test_iff_roe.py`

```python
class TestIFFCombatantList:
    """Combatant list format with IFF enabled."""

    def test_no_player_label_in_iff_list(self):
        """IFF combatant list must not contain 'player' relationship label."""
        line = build_iff_combatant_line(
            tid="tgt_7a3f", name="Ash Vex", faction="Freeborn",
            health=18, max_health=27, pronouns="she/her"
        )
        assert "player" not in line.lower()
        assert "Freeborn" in line
        assert "Ash Vex" in line

    def test_no_enemy_label_in_iff_list(self):
        """IFF combatant list must not contain 'enemy' relationship label."""
        line = build_iff_combatant_line(
            tid="tgt_9b2c", name="ACG Enforcer", faction="ACG",
            health=15, max_health=20, pronouns="they/them"
        )
        assert "enemy" not in line.lower()
        assert "ACG" in line

    def test_no_npc_label_in_iff_list(self):
        """IFF combatant list must not contain 'npc' or 'friendly' labels."""
        line = build_iff_combatant_line(
            tid="tgt_2f8a", name="Tempest Liaison", faction="Tempest",
            health=12, max_health=12, pronouns="she/her"
        )
        assert "npc" not in line.lower()
        assert "friendly" not in line.lower()
        assert "Tempest" in line

    def test_prisoner_state_retained(self):
        """Prisoner is an observable physical state, not a relationship label."""
        line = build_iff_combatant_line(
            tid="tgt_4d1e", name="Captured Guard", faction="ACG",
            health=8, max_health=20, pronouns="he/him",
            state_tag="[PRISONER]"
        )
        assert "PRISONER" in line
        assert "ACG" in line

    def test_faction_visible_for_all_entities(self):
        """All entity types should show faction name."""
        for entity in [
            {"name": "PC", "faction": "Freeborn"},
            {"name": "Enemy", "faction": "ACG"},
            {"name": "NPC", "faction": "Tempest"},
        ]:
            line = build_iff_combatant_line(
                tid="tgt_0000", name=entity["name"],
                faction=entity["faction"],
                health=10, max_health=10, pronouns="they/them"
            )
            assert entity["faction"] in line


class TestSelectiveIntel:
    """Selective intel sharing with tgt_xxxx recipients."""

    def test_intel_delivered_to_recipient(self):
        """Intel should be visible to specified recipient target_id."""
        intel = SharedIntel()
        intel.add_intel("tgt_1111", "Flanking left", round_num=1,
                        recipients={"tgt_2222"})
        result = intel.get_recent_intel_for_target("tgt_2222", current_round=1)
        assert len(result) == 1
        assert "Flanking left" in result[0]

    def test_intel_not_visible_to_non_recipient(self):
        """Intel should NOT be visible to targets not in recipients."""
        intel = SharedIntel()
        intel.add_intel("tgt_1111", "Secret plan", round_num=1,
                        recipients={"tgt_2222"})
        result = intel.get_recent_intel_for_target("tgt_3333", current_round=1)
        assert len(result) == 0

    def test_intel_leak_to_pc(self):
        """Enemy intel addressed to a PC target_id should be visible to that PC."""
        intel = SharedIntel()
        # Enemy tgt_1111 thinks tgt_9999 is an ally, but it's a PC
        intel.add_intel("tgt_1111", "Attack the Freeborn on the left",
                        round_num=1, recipients={"tgt_9999"})
        # PC queries their intel
        result = intel.get_recent_intel_for_target("tgt_9999", current_round=1)
        assert len(result) == 1
        assert "Attack the Freeborn" in result[0]

    def test_no_broadcast_without_recipients(self):
        """Intel with empty recipients should not be delivered to anyone."""
        intel = SharedIntel()
        intel.add_intel("tgt_1111", "Hello", round_num=1,
                        recipients=set())
        result = intel.get_recent_intel_for_target("tgt_2222", current_round=1)
        assert len(result) == 0

    def test_intel_expires_after_lookback(self):
        """Intel older than lookback rounds should not appear."""
        intel = SharedIntel()
        intel.add_intel("tgt_1111", "Old info", round_num=1,
                        recipients={"tgt_2222"})
        result = intel.get_recent_intel_for_target("tgt_2222",
                                                    current_round=5,
                                                    lookback=2)
        assert len(result) == 0

    def test_multiple_recipients(self):
        """Intel can be addressed to multiple targets."""
        intel = SharedIntel()
        intel.add_intel("tgt_1111", "Group intel", round_num=1,
                        recipients={"tgt_2222", "tgt_3333", "tgt_4444"})
        assert len(intel.get_recent_intel_for_target("tgt_2222", 1)) == 1
        assert len(intel.get_recent_intel_for_target("tgt_3333", 1)) == 1
        assert len(intel.get_recent_intel_for_target("tgt_4444", 1)) == 1
        assert len(intel.get_recent_intel_for_target("tgt_5555", 1)) == 0


class TestInterceptedIntel:
    """PC receiving accidentally leaked enemy intel."""

    def test_intercepted_intel_formatted(self):
        """Leaked intel should appear as intercepted communication."""
        intel = SharedIntel()
        intel.add_intel("tgt_1111", "Focus fire on the rifleman",
                        round_num=1, recipients={"tgt_9999"})
        text = build_intercepted_intel_section("tgt_9999", intel, current_round=1)
        assert "INTERCEPTED" in text
        assert "Focus fire on the rifleman" in text

    def test_no_intercepted_section_when_empty(self):
        """No intercepted section when PC has no leaked intel."""
        intel = SharedIntel()
        text = build_intercepted_intel_section("tgt_9999", intel, current_round=1)
        assert text == ""


class TestEnemyDecisionIntelRecipients:
    """EnemyDecision schema with intel_recipients field."""

    def test_intel_recipients_accepts_target_ids(self):
        """intel_recipients should accept a list of tgt_xxxx strings."""
        decision = EnemyDecision(
            action="attack",
            target="tgt_7a3f",
            shared_intel="Target is flanking",
            intel_recipients=["tgt_2222", "tgt_3333"]
        )
        assert decision.intel_recipients == ["tgt_2222", "tgt_3333"]

    def test_intel_recipients_defaults_to_none(self):
        """intel_recipients should default to None (backward compat)."""
        decision = EnemyDecision(
            action="attack",
            target="tgt_7a3f"
        )
        assert decision.intel_recipients is None
```

### Integration Tests

**File:** `tests/integration/test_iff_integration.py`

1. **IFF combatant list format:** Build a combatant list with IFF enabled. Verify
   no `player`, `enemy`, `npc`, `friendly`, `hostile`, or `ally` labels appear.
   Verify all entries show faction names.

2. **Enemy prompt neutralized:** Build enemy prompt with IFF enabled. Verify no
   "PC TARGETS" section header. Verify all contacts in a single "DETECTED CONTACTS"
   list. Verify no pre-sorted threat priorities.

3. **Intel leak scenario:** Enemy posts intel with a PC's tgt_xxxx as recipient.
   Verify the PC's prompt includes the leaked intel in "INTERCEPTED COMMUNICATIONS".

4. **Intel isolation:** Enemy posts intel with only fellow enemy tgt_xxxx as
   recipients. Verify PC prompt does NOT include the intel.

5. **IFF disabled backward compat:** With `iff_enabled: false`, verify combatant
   list uses original format with relationship labels. Verify SharedIntel uses
   original global broadcast behavior.

---

## Migration Notes

- SharedIntel refactor changes the API signature. `add_intel()` now requires
  `source_target_id` (was `source_agent`) and `recipients` (was optional).
  `get_recent_intel()` → `get_recent_intel_for_target()`. All callers in
  `enemy_combat.py` must be updated.

- When IFF is disabled (`iff_enabled: false` or absent), SharedIntel falls back
  to legacy behavior: `recipients=None` broadcasts to all enemies. This requires
  a compatibility shim in the transition period.

- EnemyDecision gains optional `intel_recipients` field with default=None.
  Backward compatible.

- `get_combatant_info()` in `target_ids.py` must include `faction` in the returned
  dict. Currently it returns `type` but not `faction`. The faction must be extracted
  from the underlying agent object.

- Session config adds `"iff_enabled": true` field. Default false.

---

## Open Questions

1. **Should the DM's combatant list also strip labels?**
   **Current answer:** No. The DM needs full relationship info to correctly
   adjudicate actions (e.g., knowing whether a target is an NPC prisoner vs an
   active enemy for soulcredit adjudication). Only agent-facing lists are stripped.

2. **Should enemy faction context include explicit ally/enemy faction lists?**
   **Current answer:** No. The enemy prompt says "You are ACG" and lets the LLM
   reason. Providing a list of "hostile factions: Freeborn, Tempest" would
   bypass the IFF challenge. The LLM must reason from world knowledge or
   scenario context.

3. **What happens when enemies have no same-faction allies on the field?**
   The enemy must decide whether contacts from other factions are potential
   allies or threats. This is the most interesting IFF scenario. No special
   handling needed -- the LLM reasons from context.

4. **Should NPC `prisoner` disposition be visible in IFF mode?**
   **Current answer:** Yes. "Prisoner" is an observable physical state (bound,
   restrained, under guard), not a relationship label. An agent can see someone
   is a prisoner without knowing their allegiance.

5. **Friendly fire from IFF errors -- should the system prevent it?**
   **Current answer:** No. Friendly fire from misidentification is a valid ML
   training signal. The system should not mechanically prevent it. If an enemy
   attacks a same-faction ally because it couldn't reason correctly about
   allegiance, that's training data about IFF failure modes.

6. **How does this interact with the `_format_target_priorities()` removal?**
   Without pre-sorted threat priorities, enemy agents must assess targets
   themselves. This is intentional -- threat assessment is part of the IFF
   reasoning challenge. However, it may increase enemy decision latency and
   reduce tactical coherence. Monitor in initial test sessions.

7. **SharedIntel backward compatibility during transition.**
   The SharedIntel API change (required recipients, tgt_xxxx IDs) breaks the
   current callers. During transition, maintain a compatibility mode where
   `recipients=None` broadcasts to all same-faction enemies (legacy behavior).
   Remove the compat mode after all callers are updated.
