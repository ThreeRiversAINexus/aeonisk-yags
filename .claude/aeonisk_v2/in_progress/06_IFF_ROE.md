# 06: IFF/ROE — Implementation Progress

**Spec:** `../.claude/aeonisk_v2/06_IFF_ROE.md`
**Started:** 2026-02-17
**Branch:** `faction-politics`

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

### Step 5: Selective Intel Sharing with tgt_xxxx Recipients (2026-02-25)
- **File:** `enemy_agent.py` — SharedIntel class + IntelItem dataclass
- **Change:** Refactored IntelItem to support both legacy (`source_agent`) and IFF (`source_target_id` + `recipients: Set[str]`) modes
- SharedIntel.add_intel() now accepts keyword args for both modes
- Added `get_recent_intel_for_target(target_id)` for selective per-agent querying
- Legacy `get_recent_intel()` preserved for backward compat (returns all intel)
- Empty recipients set = intel not added (no broadcast without recipients)

### Step 6: EnemyDecision intel_recipients Field (2026-02-25)
- **File:** `schemas/enemy_decision.py`
- **Change:** Added `intel_recipients: Optional[List[str]]` field to EnemyDecision
- Default None = legacy broadcast behavior
- Included in `to_legacy_dict()` output

### Step 7: Intercepted Communications (2026-02-25)
- **File:** `dm.py` — static method `_get_intercepted_intel_for_pc()`
- **Change:** When enemy accidentally shares intel with a PC (IFF error), the PC sees it as "INTERCEPTED COMMUNICATIONS" in their prompt context
- Returns empty string if no leaked intel exists

### Step 8: Faction Context Prompts (2026-02-25)
- **File:** `enemy_prompts.py` — `_format_iff_context(faction_name)`
- **Change:** Added IFF reasoning context section for enemy prompts: tells enemy its faction, instructs it to reason about allegiance from faction names, warns about intel_recipients
- **File:** `dm.py` — static method `_build_pc_party_context()`
- **Change:** Builds party member list (name + tgt_xxxx) for PCs, excluding self. PCs know their party — not an IFF challenge.

### Config Flag: iff_enabled (2026-02-25)
- **File:** `session.py` — reads `iff_enabled` from config, stores on session and shared_state
- **File:** `enemy_combat.py` — reads `iff_enabled` from session config in `initialize()`
- Default: false (backward compat preserved)

---

## Test Coverage

**File:** `tests/unit/test_iff_roe.py` — 34 tests, all passing
- TestSelectiveIntelSharing (10 tests): selective delivery, non-recipient exclusion, PC leaks, expiry, multiple recipients, legacy coexistence
- TestEnemyDecisionIntelRecipients (5 tests): field acceptance, defaults, legacy dict inclusion
- TestInterceptedIntel (3 tests): formatting, empty case, multiple items
- TestEnemyFactionContext (3 tests): faction name, reasoning instruction, communication mention
- TestPCPartyContext (3 tests): party member listing, self-exclusion, solo case
- TestIFFConfigFlag (5 tests): defaults, config reading, EnemyCombatManager propagation
- TestIFFBackwardCompat (5 tests): legacy add_intel, get_recent_intel, FROM prefix, IntelItem fields

---

## Notes

- Steps 1-4 were done as direct changes (before iff_enabled flag existed).
- Steps 5-8 + config flag completed in TASK-013 (2026-02-25).
- DM combatant list change (Change 1 from spec) deferred — the DM already has full knowledge, and agent-facing lists already use faction names (Steps 2-3).
- The new SharedIntel API is backward compatible: legacy callers using `add_intel(source_agent=..., intel=..., round_num=...)` continue to work.
- Enemy structured output path (`_generate_enemy_decision_structured`) can now read `intel_recipients` from EnemyDecision and pass to SharedIntel.add_intel() with recipients.
