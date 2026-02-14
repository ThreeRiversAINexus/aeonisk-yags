# Enemy Template Pipeline: Bugs & Future Spec

**Date:** 2026-02-12
**Branch:** intention-lethality-mismatch

## Current State

- 11 combat templates in `enemy_templates.py`: grunt, elite, boss, enforcer, sniper, support, ambusher, void_cultist, security_drone, seedwalker_heavy, voidcradle_antibot
- Templates are **immutable stat packages** — weapons, armor, attributes, skills all locked at template definition time
- `EnemySpawn.custom_traits` exists but only overrides **tactics**, not loadout
- NPCs have no template system — fully freeform (health, soak, skills all custom)
- When NPCs escalate to enemies, they keep their NPC weapons (no template weapon override)
- `desperate_fighter` is used as a personality label for NPC→enemy escalation, not a template lookup — no crash risk

## Bug 1: Prompt Contradicts Itself (dm_conversion_check.yaml:614)

**File:** `scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_conversion_check.yaml`

Line 571 lists valid templates:
> `"grunt", "elite", "boss", "enforcer", "sniper", "support", "ambusher", "void_cultist", "security_drone", "seedwalker_heavy", "voidcradle_antibot"`

Line 614 lists DIFFERENT names as examples:
> `"thug", "raider", "enforcer", "heavy_gunner", "elite_operative", "void_cultist"`

LLMs learn from examples more than rules — so it mimics the invalid names.

**Fix:** Replace line 614 with reference to valid list above, or repeat the correct names.

## Bug 2: 3-Entry template_map in dm.py

**File:** `scripts/aeonisk/multiagent/dm.py` (lines 1367-1372 and 1600-1605)

```python
template_map = {
    'grunt': 'Grunt',
    'elite': 'Elite',
    'boss': 'Boss'
}
template = template_map.get(template_raw, 'Grunt')
```

Any template not in this map (enforcer, sniper, security_drone, etc.) from `initial_enemies` config silently falls back to Grunt. Mid-session DM spawns bypass this (they go directly to spawn pipeline).

**Fix:** Replace with validated passthrough. `template_raw` is already `.lower()`'d and `ENEMY_TEMPLATES` keys are lowercase, so direct passthrough works. Add validation against `ENEMY_TEMPLATES` dict with warning + grunt fallback for unknown templates.

## Not a Bug: Scenario Context (Problem 3)

`_scenario_hint` says "street gang ambush" so LLM picks grunts. This is normal — scenario context drives template selection. Not fixing.

## Future Spec: Loadout Customization

### Proposed: `weapon_override` field on EnemySpawn

```python
class EnemySpawn(BaseModel):
    # ... existing fields ...
    weapon_override: Optional[List[str]] = Field(
        None,
        description="Override template weapons with specific weapon keys from WEAPON_LIBRARY. "
                    "If not specified, uses template's default weapons."
    )
```

**Pipeline change in `enemy_spawner.spawn_enemy()`:**
```python
# Current:
weapon_keys = template["weapons"]

# Proposed:
weapon_keys = weapon_override if weapon_override else template["weapons"]
```

**DM prompt guidance would add:**
```yaml
Optional:
- weapon_override: List of weapon keys to replace template defaults.
  Valid keys: "pistol", "rifle", "shotgun", "sniper_rifle", "baton", "combat_knife", etc.
  Example: weapon_override=["rifle", "combat_knife"] gives grunts rifles instead of pistols.
  Only use when narrative requires non-standard loadouts.
```

### Design Rationale

- Templates define **power level** (HP, soak, attributes, skills, armor) — the "tier"
- Weapons become **narrative flavor** — a grunt with a rifle is still grunt-tier
- Backwards compatible — field is optional, defaults to template weapons
- Minimal code change — only `spawn_enemy()` and schema need updating

### Risks

- LLM might over-use it, creating unbalanced combatants
- Weapon skill mismatch — grunt has Melee 3 and Guns 3, but sniper_rifle needs high Perception
- More cognitive load on DM LLM during spawn decisions

### Mitigation

- Validate weapon skill compatibility (warn if template lacks skill for weapon's skill type)
- Prompt guidance: "Only use when narrative requires non-standard loadouts"

## Files to Modify (When Implementing Bugs)

| File | Change |
|------|--------|
| `scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_conversion_check.yaml` | Fix line 614 invalid template names |
| `scripts/aeonisk/multiagent/dm.py` | Expand template_map at lines ~1367 and ~1600 |
| `tests/unit/test_enemy_templates.py` | Add template passthrough validation test |
