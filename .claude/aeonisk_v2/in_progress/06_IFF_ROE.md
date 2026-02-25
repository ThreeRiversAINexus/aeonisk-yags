# 06: IFF/ROE — Implementation Progress

**Spec:** `../.claude/aeonisk_v2/06_IFF_ROE.md`
**Started:** 2026-02-17
**Branch:** `main` (pending branch creation)

---

## Completed Steps

### Step 1: Remove Relationship Labels from SharedIntel (2026-02-17)
- **File:** `enemy_agent.py:711`
- **Change:** `[ALLY {source}]` → `[FROM {source}]`
- No relationship label leaks through intel sharing

### Step 2: Remove Hostile/Allied Section Headers from Enemy Prompts (2026-02-17)
- **File:** `enemy_prompts.py:359-397`
- **Change:** Standard mode no longer shows "Hostile Targets (Player Characters)", "Hostile Forces (Opposing Faction Enemies)", or "Allied Forces (Same Faction)" sections
- Replaced with neutral "Detected Contacts" and "Other Forces" headers
- `_format_hostile_enemy()` and `_format_allied_enemy()` → replaced with `_format_other_enemy()` (shows faction name, no relationship labels)

### ~~Step 3: Remove Entity Type/Disposition Labels from NPC Prompts~~ (REVERTED)
- **Reverted 2026-02-17** — NPC entity_type/disposition are *self-knowledge* (how the NPC should behave), not allegiance intel leaked to other agents. Removing them broke NPC behavioral guidance. These should only be stripped behind `iff_enabled` flag per the spec.

### Step 3 (revised): Remove Relationship Labels from NPC Combatant List (2026-02-17)
- **File:** `session.py:1824-1827` — NPC context builder
- **Change:** `{'player': 'ally', 'npc': 'npc', 'enemy': 'hostile'}` type_label mapping → faction name from `get_combatant_info()`
- **Before:** `Ash Vex (tgt_7a3f, ally) — 18/27 HP, wounds: 0`
- **After:** `Ash Vex (tgt_7a3f, Freeborn Collective) — 18/27 HP, wounds: 0`
- NPCs now see faction names instead of ally/hostile labels in their combatant list

### Step 4: Add faction to get_combatant_info() (2026-02-17)
- **File:** `target_ids.py:314-320`
- **Change:** Added `faction` field to the info dict returned by `get_combatant_info()`
- Reads from `character_state.faction` (players) or `agent.faction` (enemies/NPCs)
- Enables faction-based labeling for any consumer

---

## Remaining Steps (from spec)

### Change 1: Strip Relationship Labels from DM Combatant List
- **File:** `dm.py` lines 7536-7578
- Replace `(player)`, `(enemy)`, `(npc, {disposition})` with faction names
- Build `_build_iff_combatant_list()` — used when IFF mode enabled
- DM list retains full info (DM always has full knowledge)
- **Status:** Not started — requires `iff_enabled` config flag

### Change 4: Selective Intel Sharing with tgt_xxxx Recipients
- **File:** `enemy_agent.py` SharedIntel class
- Refactor from global broadcast to explicit `recipients: Set[str]` (tgt_xxxx IDs)
- `get_recent_intel()` → `get_recent_intel_for_target()` (per-target)
- **Status:** Not started — requires EnemyDecision schema change

### Change 5: EnemyDecision intel_recipients Field
- **File:** `schemas/enemy_decision.py`
- Add `intel_recipients: Optional[List[str]]` field
- **Status:** Not started

### Change 6: Inject Leaked Intel into PC Prompts
- **File:** `dm.py`
- `_get_intercepted_intel_for_pc()` — shows intel leaked via IFF errors
- **Status:** Not started — depends on Change 4

### Change 7: Enemy Faction Context in Prompts
- **File:** `enemy_prompts.py`
- Add IFF reasoning section: "You are {faction}. Determine allegiance from faction names."
- **Status:** Not started

### Change 8: PC Party Context
- **File:** `prompts/.../player/` YAML
- Tell PCs which tgt_xxxx IDs are their party members
- **Status:** Not started

### Config Flag: `iff_enabled`
- **File:** `session.py`
- Read from session config, propagate to subsystems
- Default: false (backward compat)
- **Status:** Not started

---

## Notes

- Steps 1-2 were done as direct removals (no config flag needed). These remove allegiance labels from enemy-facing prompts.
- Step 3 (NPC labels) was reverted — NPC entity_type/disposition is self-knowledge, not inter-agent allegiance leakage. Defer to `iff_enabled` flag.
- Steps 4-8 require the `iff_enabled` config flag and more substantial refactoring.
- The DM combatant list change (Change 1) is agent-facing only — DM's own list keeps full info.
- Test file: `tests/unit/test_iff_roe.py` (spec has full test plan)
