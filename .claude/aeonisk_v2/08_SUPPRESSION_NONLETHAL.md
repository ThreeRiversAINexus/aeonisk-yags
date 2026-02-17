# 08: Suppression & Non-Lethal Resolution

**Priority:** P1
**Status:** Proposed (Treatment v1 partially built)
**Branch:** `intention-lethality-mismatch` (active)
**Dependencies:** 11_EXPERIMENT_INFRA (for A/B config generation, soft dependency)

---

## Problem Statement

There is a 100% intention-lethality mismatch in the current system: when a player declares suppressive fire, the DM resolves it with wound damage identical to lethal attacks. The DM LLM has no structured signal that the player intended non-lethal resolution, and all combat resolution examples in `dm_resolution_combat.yaml` demonstrate lethal damage output.

### Evidence from Baseline Datamining (20 sessions x 4 models)

From `.claude/baseline_datamining/` analysis (2026-02-14):

| Model | Non-Lethal Intent % | TPK Rate | Paradox |
|-------|---------------------|----------|---------|
| DeepSeek V3.2 | 52% | 80% | Highest intent, highest kills |
| GPT-5.2 | 28% | 60% | Moderate both |
| Gemini 2.5 Pro | 18% | 60% | Low intent, moderate kills |
| Grok 4 | 4.5% | 60% | Lowest intent, best survival |

Key findings:
- **Suppressive fire uses same base_damage as lethal attacks** -- the DM generates `DamageEffect(base_damage=12-18, damage_type="wound")` regardless of player intent
- **Shock baton correctly deals stun damage** -- damage_type="stun" in weapon context works; the problem is specific to intent-based lethality (not weapon-based)
- **DeepSeek paradox:** 52% of player declarations express non-lethal intent (suppressive fire, warning shots, restraint), but 80% TPK rate. The DM LLM resolves non-lethal intent with lethal mechanics
- **Grok paradox:** Only 4.5% non-lethal intent, but best survival (60% TPK). Players who declare lethal intent produce more predictable outcomes
- **3/5 PC-on-NPC attacks were DM free-target misbinding** (tgt_xxxx resolved to wrong entity), not player intent -- separate issue from suppression

### Root Cause Analysis

From `.claude/LETHALITY_MISMATCH_AUDIT.md`:

1. **No `intended_lethality` field in CombatAction** (player_action.py:336-380). The player's intent to suppress vs. kill is expressed only in freeform `intent` and `description` text. No structured signal reaches the DM.

2. **SupportAction explicitly routes suppression to COMBAT** (player_action.py:465-467). The docstring says "Direct suppressing fire should use CombatAction with target=enemy, not SupportAction." Both lethal and suppressive attacks use the same schema path.

3. **All DM combat resolution examples are lethal** (dm_resolution_combat.yaml). Zero examples of non-lethal combat resolution. LLMs default to demonstrated patterns.

4. **ActionResolution separates narration from effects without linking** (action_resolution.py:276-305). The DM can narrate "forcing them behind cover" while simultaneously outputting `DamageEffect(dealt=12)`. No schema field connects narrative restraint to mechanical restraint.

5. **Enemy agents have explicit Suppress action; PCs do not** (enemy_combat.py:1231-1408). The enemy `_execute_suppress()` method applies conditions (Suppressed, Hunker Down) without lethal damage. PCs lack an equivalent pathway.

---

## Current Implementation

### CombatAction Schema (player_action.py:336-380)

```python
# player_action.py:336-380
class CombatAction(PlayerActionBase):
    """COMBAT action: Attacks, defensive maneuvers, tactical combat."""
    action_type: Literal[ActionType.COMBAT] = ActionType.COMBAT
    target: str = Field(..., description="REQUIRED: Target ID for attack")
    target_position: Optional[Position] = Field(default=None)
    situational_modifiers: Dict[str, int] = Field(default_factory=dict)
    # No: intended_lethality field
    # No: structured suppression flag
```

### DM Combat Resolution Prompt (dm_resolution_combat.yaml)

The resolution prompt contains three examples, all with lethal damage:

```yaml
# dm_resolution_combat.yaml:84-123 (two of three examples)
# Example 1: base_damage=15, damage_type="wound" -- lethal
# Example 2: base_damage=10, damage_type="wound" -- lethal
# Example 3: base_damage=18, damage_type="wound" -- lethal
```

Zero examples of condition-based resolution (Suppressed, Pinned) without lethal damage.

### Treatment Prompt (dm_resolution_combat_suppression.yaml, UNCOMMITTED)

A treatment prompt already exists at `scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_combat_suppression.yaml` (107 lines). It provides:

```yaml
# dm_resolution_combat_suppression.yaml:13-17
# Margin-based suppression scaling:
# Margin 0-5:  Suppressed (-2), base_damage 0-2
# Margin 6-10: Pinned (-4),     base_damage 0-3
# Margin 11+:  Full Suppression, base_damage 0-5
```

Two structured output examples showing condition-based resolution with minimal damage.

### Experiment Config Loading (dm.py:803-809)

```python
# dm.py:803-809
if action_type and action_type.lower() in ('combat', 'attack', 'brawl'):
    session_cfg = getattr(self, 'session_config', {})
    experiment = session_cfg.get('experiment', {}) if session_cfg else {}
    if experiment.get('include_suppression_resolution_example', False):
        modules.append('dm_resolution_combat_suppression')
        logger.debug("DM: Loading suppression resolution example (experiment flag)")
```

The infrastructure to conditionally load the suppression prompt based on session config `experiment.include_suppression_resolution_example` already exists.

### Session Config (session_config_combat_ambush.json:8-11)

```json
"experiment": {
    "condition": "treatment_1",
    "include_suppression_resolution_example": true
}
```

The combat ambush config already has the treatment flag set. Control configs (in `lethality_test_combat_ambush/control/`) omit this flag.

### Enemy Suppress Execution (enemy_combat.py:1231-1408)

```python
# enemy_combat.py:1231-1408
def _execute_suppress(self, enemy, declaration, player_agents, mechanics_engine, resolution_state):
    """
    Execute enemy Suppress action.
    Suppress (Tactical Module v1.2.3):
    - Requires weapon with RoF >= 3
    - On successful hit: target must choose Dive or Hunker Down
    """
    # ... range calculation, attack roll ...
    if hit:
        result['narration'] += f" - SUPPRESSED! {target_name} must choose: Dive or Hunker Down"
        result['effect'] = 'suppressed'
        result['choices'] = ['Dive', 'Hunker Down']
    # NOTE: No damage dealt. Only conditions applied.
```

Enemy suppression is already non-lethal. The fix is to give PCs an equivalent pathway.

**However, enemy suppression has two additional bugs that prevent it from ever executing:**

### Bug: `rate_of_fire` Field Name Mismatch (enemy_combat.py:1337-1346)

```python
# enemy_combat.py line 1338
weapon_rof = getattr(weapon, 'rate_of_fire', 0)  # BUG: field is 'rof', not 'rate_of_fire'
if weapon_rof < 3:
    return {..., 'result': 'insufficient_rof', ...}
```

The `Weapon` dataclass (weapons.py:53) defines the field as `rof`, not `rate_of_fire`. `getattr(weapon, 'rate_of_fire', 0)` **always returns 0** (the default), so the `< 3` check **always fails**. No enemy can ever suppress, regardless of weapon.

### Bug: Asymmetric RoF Gate (enemy_combat.py vs DM structured output)

Even with the field name fixed, the RoF >= 3 restriction creates an asymmetry:
- **Enemies:** Hard-gated at RoF >= 3. Only 4 weapons qualify: Rifle (3), Heavy Weapon (5), SMG (3), Sawn-Off Shotgun (3). Grunts carry Pistol (rof=2) and Baton (rof=1) — they can never suppress.
- **Players:** No RoF check whatsoever. Player suppression goes through the DM structured output path, which has no mechanical prerequisite validation. A player with a Pistol (rof=2) can declare and resolve suppressive fire.

**Design decision:** Remove the RoF >= 3 gate for enemies. While YAGS core rules require RoF >= 3 for suppression, the player path has no equivalent check, creating an unfair asymmetry. Any ranged weapon should be able to suppress. The RoF restriction can be revisited when symmetric enforcement is implemented for both sides. The `rate_of_fire` → `rof` field name fix is also required.

### DamageEffect Schema (shared_types.py:254-292)

```python
# shared_types.py:254-277
class DamageEffect(BaseModel):
    target: str = Field(...)
    base_damage: int = Field(..., ge=0, description="Damage before soak")
    soak: Optional[int] = Field(default=None, ge=0)
    dealt: int = Field(..., ge=0, description="Final damage dealt after soak")
    damage_type: Optional[str] = Field(
        default=None,
        description="YAGS damage type: 'stun', 'wound', or 'mixed'"
    )
```

The schema already supports `base_damage=0` and `damage_type="stun"`. The DM just never generates these values for PC combat actions because no examples demonstrate it.

---

## Design Decisions

1. **Phased approach: prompt-first, schema-later.** Treatment v1 uses prompt examples only (cheapest intervention). Treatment v2 adds schema fields. Treatment v3 adds graduated damage guidance. This mirrors the A/B experiment methodology -- measure the cheapest intervention first.

2. **Suppress is not a separate action type.** Suppressive fire remains a `CombatAction` with `target=enemy`. The lethality signal is either in `intended_lethality` (v2) or inferred from intent text by the DM (v1). This avoids fragmenting the action type space and keeps ML training data comparable.

3. **Stun damage_type for suppressive intent.** When a player declares suppressive fire and the DM resolves it non-lethally, `damage_type` should be "stun" (not "wound"), and `base_damage` should be 0-5. The weapon's mechanical damage_type (from WEAPON CONTEXT) remains "wound" for ballistic weapons -- the suppression YAML explicitly says to keep damage_type="wound" but use low base_damage values. This is revisited in v3 where we may override to "stun".

4. **Soulcredit reward for restraint.** The suppression YAML awards `SoulcreditChange(amount=1)` for showing restraint. This creates a positive mechanical incentive for non-lethal resolution without punishing lethal resolution.

---

## Proposed Solution

### Treatment v1: Prompt Example Only (PARTIALLY BUILT)

**Goal:** Add one non-lethal combat resolution example to the DM prompt when experiment flag is set. Measure whether a single demonstrated example shifts behavior.

**Status:** Mostly complete. The YAML exists, the loading code exists, the config flag exists. Remaining work:

**Files to modify:**
- `dm_resolution_combat_suppression.yaml` -- already written (107 lines, uncommitted)
- `dm.py:803-809` -- already implemented
- Session configs -- treatment configs already generated

**Remaining work:**
1. Commit the suppression YAML to the branch
2. Generate treatment_v1 bulk run configs for all 5 providers (control already generated)
3. Run 20 sessions per provider per condition (control vs treatment_v1)
4. Analyze with datamining scripts (same methodology as baseline)

**Expected measurement:**
- Compare `base_damage` distribution for suppressive-intent declarations between control and treatment
- Compare TPK rates between conditions
- Compare Suppressed/Pinned condition frequency between conditions

### Treatment v2: Schema Field (intended_lethality)

**Goal:** Add `intended_lethality` field to CombatAction so the DM receives a structured signal about player intent, not just freeform text.

**Files to modify:**
- `schemas/player_action.py:336-380` (CombatAction)
- `schemas/player_action.py:779-991` (legacy PlayerAction)
- Player action prompts (to teach the LLM about the new field)
- DM resolution prompts (to read and respect the field)

**Implementation:**

```python
# schemas/player_action.py CombatAction addition
class CombatAction(PlayerActionBase):
    action_type: Literal[ActionType.COMBAT] = ActionType.COMBAT
    target: str = Field(...)
    target_position: Optional[Position] = Field(default=None)
    situational_modifiers: Dict[str, int] = Field(default_factory=dict)

    # NEW: Structured lethality signal
    intended_lethality: Optional[Literal["lethal", "non_lethal", "suppressive"]] = Field(
        default=None,
        description=(
            "Your intended level of force:\n"
            "- lethal: Kill or critically wound the target\n"
            "- non_lethal: Subdue, incapacitate, or knock out without killing\n"
            "- suppressive: Pin down, deny movement, force behind cover (condition-based)\n"
            "If not specified, DM interprets from your intent/description."
        )
    )
```

**DM prompt injection:**

```python
# dm.py (in weapon context or resolution context)
if action.get('intended_lethality') == 'suppressive':
    lethality_guidance = (
        "\n**LETHALITY INTENT: SUPPRESSIVE**\n"
        "The attacker declared SUPPRESSIVE fire. Primary effect is CONDITIONS, not damage.\n"
        "- base_damage: 0-5 (incidental, regardless of margin)\n"
        "- Apply: Suppressed (-2), Pinned (-4), or Full Suppression (-6)\n"
        "- Scale condition severity with margin, NOT damage\n"
        "- Award +1 soulcredit for restraint\n"
    )
elif action.get('intended_lethality') == 'non_lethal':
    lethality_guidance = (
        "\n**LETHALITY INTENT: NON-LETHAL**\n"
        "The attacker declared NON-LETHAL intent. Reduce damage, prefer stun/conditions.\n"
        "- base_damage: 50% of normal (weapon stats / 2)\n"
        "- damage_type: 'stun' (unless weapon is already stun type)\n"
        "- Narrate: subduing, restraining, knocking out (not killing)\n"
    )
else:
    lethality_guidance = ""  # Default: DM interprets freely
```

**Backward compatibility:** `intended_lethality` is `Optional` with `default=None`. Existing CombatAction instances are unaffected. Old session replays parse correctly. DM falls back to current behavior when field is absent.

### Treatment v3: Graduated Damage Guidance

**Goal:** Provide explicit base_damage guidance tables in the DM prompt that vary by `intended_lethality`. This builds on Phase 2 weapon stats from 07_INVENTORY_EQUIPMENT.

**Files to modify:**
- DM resolution prompts (expanded damage tables)
- `dm.py` (build lethality-specific weapon context)
- `dm_resolution_combat.yaml` (add non-lethal example alongside lethal examples)

**Implementation:**

```python
# dm.py (expanded weapon context with lethality scaling)
if weapon_obj and action.get('intended_lethality'):
    lethality = action['intended_lethality']
    base = attacker_strength + weapon_obj.damage

    if lethality == 'suppressive':
        weapon_context += (
            f"\n**SUPPRESSIVE DAMAGE TABLE:**\n"
            f"| Margin | base_damage | Primary Effect |\n"
            f"|--------|-------------|----------------|\n"
            f"| 0-5    | 0-2         | Suppressed (-2, 1 round) |\n"
            f"| 6-10   | 0-3         | Pinned (-4, 1 round) |\n"
            f"| 11+    | 0-5         | Full Suppression (-6, 2 rounds) |\n"
            f"\ndo NOT scale damage with margin. Scale CONDITIONS instead.\n"
        )
    elif lethality == 'non_lethal':
        weapon_context += (
            f"\n**NON-LETHAL DAMAGE TABLE:**\n"
            f"| Margin | base_damage | damage_type |\n"
            f"|--------|-------------|-------------|\n"
            f"| 0-4    | {max(0, base // 2 - 2)} | stun |\n"
            f"| 5-9    | {base // 2} | stun |\n"
            f"| 10-14  | {base // 2 + 2} | stun |\n"
            f"| 15+    | {base // 2 + 4} | stun |\n"
        )
    else:  # lethal (default)
        weapon_context += (
            f"\n**LETHAL DAMAGE TABLE:**\n"
            f"| Margin | base_damage |\n"
            f"|--------|-------------|\n"
            f"| 0-4    | {base} |\n"
            f"| 5-9    | {base + 3} |\n"
            f"| 10-14  | {base + 6} |\n"
            f"| 15+    | {base + 10} |\n"
        )
```

---

## Files to Modify

| File | Change | Treatment |
|------|--------|-----------|
| `prompts/claude/en/dm/dm_resolution_combat_suppression.yaml` | Commit existing file | v1 |
| `dm.py:803-809` | Already implemented (no change) | v1 |
| `enemy_combat.py:1337-1346` | Fix `rate_of_fire` → `rof` field name; remove RoF >= 3 gate | v1 |
| `enemy_prompts.py:690` | Update suppress description: remove "requires RoF >= 3", replace with "requires ranged weapon" | v1 |
| Session configs (treatment_v1/) | Already generated (no change) | v1 |
| `schemas/player_action.py:336-380` | Add `intended_lethality` to CombatAction | v2 |
| `schemas/player_action.py:779-991` | Add `intended_lethality` to legacy PlayerAction | v2 |
| `prompts/claude/en/player/player_action_combat.yaml` | Add lethality field guidance | v2 |
| `dm.py` (resolution context) | Read and inject lethality guidance | v2 |
| `dm.py:7580-7590` | Lethality-specific damage tables | v3 |
| `dm_resolution_combat.yaml` | Add non-lethal example | v3 |

---

## Test Plan

### Treatment v1: Prompt Example Tests

```python
# tests/unit/test_suppression_module.py

def test_suppression_module_loads_with_experiment_flag():
    """Suppression YAML should load when experiment flag is set."""
    dm = create_test_dm(session_config={
        "experiment": {"include_suppression_resolution_example": True}
    })
    modules = dm._get_resolution_modules(action_type="combat")
    assert "dm_resolution_combat_suppression" in modules

def test_suppression_module_skipped_without_flag():
    """Suppression YAML should NOT load without experiment flag."""
    dm = create_test_dm(session_config={})
    modules = dm._get_resolution_modules(action_type="combat")
    assert "dm_resolution_combat_suppression" not in modules

def test_suppression_module_only_for_combat():
    """Suppression YAML should only load for combat/attack action types."""
    dm = create_test_dm(session_config={
        "experiment": {"include_suppression_resolution_example": True}
    })
    modules = dm._get_resolution_modules(action_type="investigate")
    assert "dm_resolution_combat_suppression" not in modules

def test_suppression_yaml_parseable():
    """Suppression YAML should parse without errors."""
    from ..prompt_loader import load_agent_prompt
    content = load_agent_prompt("dm_resolution_combat_suppression")
    assert "SUPPRESSIVE FIRE RESOLUTION" in content
    assert "base_damage" in content
    assert "Pinned" in content
```

### Enemy Suppress Bug Fix Tests

```python
# tests/unit/test_enemy_suppress_rof.py

def test_enemy_suppress_with_pistol_succeeds():
    """Enemy with Pistol (rof=2) should be able to suppress after RoF gate removal."""
    enemy = make_enemy(weapons=[WEAPON_LIBRARY['pistol']])  # rof=2
    result = resolver._execute_suppress(enemy, declaration, players, mechanics, rs)
    assert result.get('result') != 'insufficient_rof', \
        "Pistol should be able to suppress (RoF gate removed)"

def test_enemy_suppress_with_rifle_succeeds():
    """Enemy with Rifle (rof=3) should be able to suppress."""
    enemy = make_enemy(weapons=[WEAPON_LIBRARY['rifle']])  # rof=3
    result = resolver._execute_suppress(enemy, declaration, players, mechanics, rs)
    assert result.get('result') != 'insufficient_rof'

def test_enemy_suppress_requires_ranged_weapon():
    """Enemy with melee-only weapon should not be able to suppress."""
    enemy = make_enemy(weapons=[WEAPON_LIBRARY['baton']])  # melee, not ranged
    result = resolver._execute_suppress(enemy, declaration, players, mechanics, rs)
    # Should fail with 'no valid ranged weapon' or similar (not 'insufficient_rof')
```

### Treatment v2: Schema Field Tests

```python
# tests/unit/test_intended_lethality.py

def test_combat_action_accepts_lethal():
    """CombatAction should accept intended_lethality='lethal'."""
    action = CombatAction(
        intent="Fire rifle at enemy commander",
        description="Taking aim at the squad leader's center mass to eliminate the threat.",
        attribute="Agility",
        skill="Guns",
        difficulty_estimate=18,
        difficulty_justification="Moving target, partial cover",
        target="tgt_7a3f",
        intended_lethality="lethal"
    )
    assert action.intended_lethality == "lethal"

def test_combat_action_accepts_suppressive():
    """CombatAction should accept intended_lethality='suppressive'."""
    action = CombatAction(
        intent="Lay down covering fire to pin enemies",
        description="Firing in controlled bursts to keep the hostiles behind cover.",
        attribute="Agility",
        skill="Guns",
        difficulty_estimate=15,
        difficulty_justification="Suppression, not accuracy",
        target="tgt_7a3f",
        intended_lethality="suppressive"
    )
    assert action.intended_lethality == "suppressive"

def test_combat_action_accepts_non_lethal():
    """CombatAction should accept intended_lethality='non_lethal'."""
    action = CombatAction(
        intent="Subdue the guard with baton strike",
        description="Swinging the shock baton at the guard's legs to bring them down without killing.",
        attribute="Agility",
        skill="Brawl",
        difficulty_estimate=16,
        difficulty_justification="Close quarters, guard is alert",
        target="tgt_2k9m",
        intended_lethality="non_lethal"
    )
    assert action.intended_lethality == "non_lethal"

def test_combat_action_defaults_to_none():
    """CombatAction should default to intended_lethality=None (backward compat)."""
    action = CombatAction(
        intent="Attack the enemy",
        description="Engaging the hostile with available weapons.",
        attribute="Agility",
        skill="Guns",
        difficulty_estimate=15,
        difficulty_justification="Standard engagement",
        target="tgt_7a3f"
    )
    assert action.intended_lethality is None

def test_combat_action_rejects_invalid_lethality():
    """CombatAction should reject invalid intended_lethality values."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CombatAction(
            intent="Attack the enemy",
            description="Engaging the hostile with available weapons.",
            attribute="Agility",
            skill="Guns",
            difficulty_estimate=15,
            difficulty_justification="Standard engagement",
            target="tgt_7a3f",
            intended_lethality="murder"  # Invalid value
        )

def test_legacy_player_action_accepts_lethality():
    """Legacy PlayerAction should also accept intended_lethality."""
    action = PlayerAction(
        intent="Fire suppressive burst at enemy position",
        description="Laying down covering fire to pin the hostiles behind the barricade.",
        attribute="Agility",
        skill="Guns",
        difficulty_estimate=15,
        difficulty_justification="Suppression, area denial",
        action_type=ActionType.COMBAT,
        target="tgt_7a3f",
        intended_lethality="suppressive"
    )
    assert action.intended_lethality == "suppressive"
```

### Treatment v3: Damage Guidance Tests

```python
# tests/unit/test_suppressive_damage_guidance.py

def test_suppressive_damage_table_in_weapon_context():
    """Suppressive lethality should produce condition-focused damage table."""
    context = build_weapon_context_with_lethality(
        weapon_obj=get_weapon("rifle"),
        attacker_strength=3,
        intended_lethality="suppressive"
    )
    assert "SUPPRESSIVE DAMAGE TABLE" in context
    assert "0-2" in context  # Low base_damage for marginal success
    assert "Pinned" in context
    assert "do NOT scale damage with margin" in context

def test_lethal_damage_table_in_weapon_context():
    """Lethal lethality should produce standard damage table."""
    context = build_weapon_context_with_lethality(
        weapon_obj=get_weapon("rifle"),
        attacker_strength=3,
        intended_lethality="lethal"
    )
    assert "LETHAL DAMAGE TABLE" in context
    # Str(3) + Weapon(7) = 10 base for marginal
    assert "10" in context

def test_non_lethal_damage_type_is_stun():
    """Non-lethal damage table should specify stun damage_type."""
    context = build_weapon_context_with_lethality(
        weapon_obj=get_weapon("rifle"),
        attacker_strength=3,
        intended_lethality="non_lethal"
    )
    assert "NON-LETHAL DAMAGE TABLE" in context
    assert "stun" in context

def test_no_lethality_produces_no_table():
    """Missing intended_lethality should produce no lethality-specific table."""
    context = build_weapon_context_with_lethality(
        weapon_obj=get_weapon("rifle"),
        attacker_strength=3,
        intended_lethality=None
    )
    assert "SUPPRESSIVE DAMAGE TABLE" not in context
    assert "NON-LETHAL DAMAGE TABLE" not in context
    assert "LETHAL DAMAGE TABLE" not in context
```

### A/B Experiment Validation Tests

```python
# tests/unit/test_experiment_config.py

def test_treatment_configs_have_experiment_flag():
    """Treatment v1 configs should have include_suppression_resolution_example=true."""
    import json
    config_path = "scripts/session_configs/experiment/lethality_test_combat_ambush/treatment_v1/"
    for config_file in glob.glob(f"{config_path}*.json"):
        with open(config_file) as f:
            config = json.load(f)
        assert config.get("experiment", {}).get("include_suppression_resolution_example") == True, \
            f"Treatment config {config_file} missing experiment flag"

def test_control_configs_lack_experiment_flag():
    """Control configs should NOT have include_suppression_resolution_example."""
    import json
    config_path = "scripts/session_configs/experiment/lethality_test_combat_ambush/control/"
    for config_file in glob.glob(f"{config_path}*.json"):
        with open(config_file) as f:
            config = json.load(f)
        assert not config.get("experiment", {}).get("include_suppression_resolution_example", False), \
            f"Control config {config_file} should not have experiment flag"

def test_treatment_and_control_identical_except_experiment():
    """Treatment and control configs should differ ONLY in experiment block."""
    # Ensures clean A/B comparison
    pass
```

---

## Dependencies

### Hard Dependencies
None. Treatment v1 is self-contained.

### Soft Dependencies
- **11_EXPERIMENT_INFRA** -- for automated A/B config generation (`generate_multi_llm_configs.py`). Treatment v1 configs were manually generated and already exist in `lethality_test_combat_ambush/treatment_v1/`. Future treatments can use the automated infrastructure.

### Hard Dependencies (Treatment v3 only)
- **07_INVENTORY_EQUIPMENT Phase 2** -- weapon stats in DM prompt feed into treatment v3's graduated damage tables. Without weapon stats, the graduated damage tables cannot scale by weapon class. This is a hard dependency for v3 — do NOT implement v3 before Phase 2 of Spec 07 is complete. (Treatments v1 and v2 are unaffected.)

---

## Open Questions

### Q0: PC base_damage is ungrounded in weapon stats (known gap)

**Issue:** The WEAPON CONTEXT injected into the DM prompt (`dm.py:7580-7590`) only passes weapon **name** and **damage_type**. It does NOT pass weapon stats (damage bonus, attack bonus) or attacker attributes. The DM's `base_damage` for PC attacks is entirely DM-inferred from context and prompt examples.

Meanwhile, enemy attacks use a hardcoded formula: `base_damage = Strength + weapon.damage + d20_roll` (enemy_combat.py:1067-1073). This creates an asymmetry: enemy damage is formula-driven, PC damage is DM-inferred. Note: the enemy formula's use of Strength as a flat damage modifier may not accurately reflect YAGS combat rules — needs verification against YAGS core.

**Consequence for treatment v1/v2:** Both the lethal table (8-12 / 12-16 / 16-22) and suppression table (0-2 / 0-3 / 0-5) are flat ranges independent of weapon. This is intentional — keeping the variable constant isolates the effect of the classification gate and anchor removal.

**Direction for v3:** Pass YAGS weapon stats and damage formulas to the DM in WEAPON CONTEXT so the DM can reason about appropriate damage. The goal is to provide formulas as *input* (how YAGS damage works), NOT tables that dictate output values. The DM should do the math and choose the final number — we're testing its reasoning ability, not replacing it with lookup tables. This requires a code change in `dm.py` and verification of YAGS damage mechanics.

**Decision:** Do NOT change in v1/v2. Keep flat tables for experimental consistency.

### Q1: Should damage_type override to "stun" for suppressive attacks?

**Current recommendation (v1-v2):** No. The suppression YAML (line 105) explicitly says: "The damage_type stays 'wound' (matching WEAPON CONTEXT for ballistic weapons). The differentiation is entirely in base_damage (very low) and conditions (the primary effect)."

**Rationale:** A rifle's bullets are still bullets. Even suppressive fire can wound. The restraint is in base_damage (0-5 vs 12-18), not in changing the physics of the weapon.

**Counterargument for v3:** Changing damage_type to "stun" for suppressive fire would mechanically prevent wound accumulation on the wound ladder, which is the lethality vector. base_damage=3 wound damage still inflicts wounds (if it exceeds soak). base_damage=3 stun damage does not.

**Decision needed before v3 implementation.**

### Q2: Should intended_lethality be required or optional for CombatAction?

**Current recommendation:** Optional with `default=None`. This preserves backward compatibility and allows gradual adoption. Player prompts can encourage filling it, but validation should not reject actions without it.

**Alternative:** Required. Force every combat declaration to explicitly state lethality intent. This produces cleaner ML training data but risks confusing LLMs that have not been prompted about the field, leading to validation failures and retries.

### Q3: Should the DM be able to override player lethality intent?

**Current recommendation:** Yes. The DM-authoritative principle means the DM can narrate lethal outcomes even for suppressive intent (e.g., "the suppressive burst catches them in the open -- lethal hit despite the intended restraint"). The schema provides intent as guidance, not hard constraint. This creates interesting ML training data about intent vs. outcome divergence.

### Q4: How to handle DeepSeek's 52% non-lethal paradox?

DeepSeek V3.2 declared non-lethal intent most often but had the highest TPK rate. Two possible causes:
1. **DM ignores intent:** DeepSeek's DM agent resolves everything lethally regardless of player intent (same root cause as other models, just with more non-lethal declarations to contrast against)
2. **Overcorrection:** DeepSeek's player agents declare non-lethal too often, leaving enemies alive to deal cumulative damage, causing attrition TPK

**Measurement:** Treatment v2 (structured intent field) will disambiguate. If the DM respects `intended_lethality="suppressive"` but the player still gets TPK'd due to attrition, cause 2 is confirmed. If the DM still outputs lethal damage despite the structured field, cause 1 persists (and we need v3 enforcement).

### Q5: How to validate that suppressive resolution actually happened?

**Automated detection for A/B analysis:**

```python
# Suppressive intent detection (in JSONL analysis)
def is_suppressive_intent(action_resolution_event):
    """Check if a resolved action was suppressive in intent."""
    # v1: Keyword detection in intent/description (imperfect)
    intent = event.get('intent', '').lower()
    return any(kw in intent for kw in [
        'suppress', 'cover', 'pin', 'warning shot', 'covering fire'
    ])

# Suppressive resolution detection
def is_suppressive_resolution(action_resolution_event):
    """Check if resolution used suppressive mechanics."""
    effects = event.get('effects', {})
    damage = effects.get('damage', [])
    conditions = effects.get('conditions', [])

    # Suppressive = has conditions AND low/no damage
    has_suppressive_conditions = any(
        c.get('name', '').lower() in ['suppressed', 'pinned', 'shaken']
        for c in conditions
    )
    low_damage = all(d.get('base_damage', 99) <= 5 for d in damage) if damage else True

    return has_suppressive_conditions and low_damage
```

---

## Experiment Design

### Conditions

| Condition | Description | Config Flag |
|-----------|-------------|-------------|
| Control | Standard combat resolution (lethal examples only) | `include_suppression_resolution_example: false` or absent |
| Treatment v1 | Add suppression YAML to DM prompt | `include_suppression_resolution_example: true` |
| Treatment v2 | v1 + `intended_lethality` schema field | `intended_lethality_enabled: true` (future) |
| Treatment v3 | v2 + graduated damage tables | `graduated_damage_guidance: true` (future) |

### Metrics

| Metric | Definition | Expected Direction |
|--------|------------|-------------------|
| Suppressive base_damage mean | Mean base_damage for suppressive-intent actions | Control: 12-18, Treatment: 0-5 |
| Condition frequency | % of combat resolutions with Suppressed/Pinned conditions | Control: ~0%, Treatment: >30% |
| TPK rate | % of sessions ending in total party kill | Treatment should decrease |
| Soulcredit per session | Total soulcredit changes per session | Treatment should increase (+1 per suppression) |
| Narration-mechanics alignment | % of actions where narration sentiment matches damage level | Treatment should increase |

### Sample Size

Per baseline methodology: 20 sessions per provider per condition. 5 providers x 2 conditions x 20 sessions = 200 sessions total for v1 A/B.

---

## Migration Notes

### Session Config Changes

Treatment v1: No schema changes. Uses existing `experiment.include_suppression_resolution_example` flag.

Treatment v2: New optional field in CombatAction. Old configs and replays unaffected (field defaults to None).

### JSONL Logging Impact

Treatment v2 adds `intended_lethality` to `action_declaration` events:

```json
{
    "event_type": "action_declaration",
    "data": {
        "action_type": "combat",
        "intent": "Lay down suppressive fire on enemy position",
        "intended_lethality": "suppressive",
        "target": "tgt_7a3f"
    }
}
```

Additive change. No existing event schemas modified.

### Backward Compatibility

All three treatments are additive:
- v1: Extra prompt module loaded conditionally (no code change beyond YAML)
- v2: Optional schema field with None default
- v3: Expanded prompt content (no schema change beyond v2)

Old sessions replay identically. Old test fixtures remain valid.
