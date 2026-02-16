# Spec 11: Experiment Infrastructure

**Priority:** P2 (Wave 3 -- Parallel After Wave 1)
**Status:** Not started
**Dependencies:** None
**Estimated Scope:** Medium-Large

---

## Problem Statement

The experiment infrastructure has two structural gaps that limit the usefulness
of multi-model comparisons and create ongoing maintenance burden.

### Gap 1: Per-Role Model Configuration

`generate_multi_llm_configs.py` replaces ALL agent LLM blocks with the same
provider:model pair. Every agent in the session -- DM, all players, all
enemies, all NPCs -- uses an identical model. This prevents the most
interesting experiment designs:

- **DM model comparison with fixed player behavior:** Hold players constant
  (e.g., GPT-5-mini) while varying the DM model across GPT-5.2, Claude Opus 4.6,
  Grok 4, etc. This isolates DM resolution quality from player action quality.
- **Player model comparison with fixed DM:** Hold DM constant while varying
  the player model. This isolates player decision quality.
- **Enemy AI model comparison:** Use a frontier model for DM and players but
  vary the enemy decision model to test tactical sophistication.
- **Cost-tiered configs:** Use a cheap model (GPT-4o-mini) for players and
  enemies but a frontier model for the DM, reducing cost per session by 60%.

Additionally, enemies and NPCs do not have their own LLM config sections in
the session config schema. They inherit from the DM at runtime:
- Enemies: `EnemyCombatManager.__init__()` reads `agents.dm.llm` (line 236)
- NPCs: Use `self.enemy_combat.llm_provider` passed through at spawn time

There is no way to specify a different model for enemies or NPCs in the
session config.

### Gap 2: Legacy Code Path Audit

The codebase contains two parallel resolution pipelines:

1. **Structured output pipeline** (current, Pydantic-based): Activated when
   `_last_structured_resolution` is not None. Generates `ActionResolution`
   schema via LLM, applies effects deterministically.

2. **Legacy text parsing pipeline** (deprecated but active): Activated when
   `_last_structured_resolution` is None. Parses DM narration text using
   `parse_state_changes()`, `parse_combat_triplet()`, and
   `parse_mechanical_effect()` to extract damage, void changes, and conditions.

Both pipelines run simultaneously in some code paths. The legacy pipeline is
gated by `_last_structured_resolution` checks, but these checks are scattered
across `dm.py` with no central router or documentation of which code paths
they affect. This creates:

- **Double-damage bugs:** Both pipelines can apply damage to the same target
  in the same resolution (partially fixed in commit `d94a6ce` but still
  fragile).
- **Maintenance burden:** Every new feature must consider both pipelines.
- **Experiment ambiguity:** When a session uses structured output, the legacy
  path still runs for combat triplet parsing (line 5366). It is unclear which
  pipeline is authoritative for which effects.

---

## Current Implementation

### generate_multi_llm_configs.py (`scripts/generate_multi_llm_configs.py`)

Full file (174 lines). Key function:

```python
def generate_config(base_config, provider, model, proxy_url=None):
    """Deep-copy base config and replace provider/model in ALL agent LLM blocks."""
    config = copy.deepcopy(base_config)

    # Update DM LLM block (line 57-61)
    if "agents" in config and "dm" in config["agents"]:
        if "llm" in config["agents"]["dm"]:
            config["agents"]["dm"]["llm"] = update_llm_block(...)

    # Update all player LLM blocks (line 64-67)
    if "agents" in config and "players" in config["agents"]:
        for player in config["agents"]["players"]:
            if "llm" in player:
                player["llm"] = update_llm_block(...)

    # NO enemy LLM block update (enemies not in config schema)
    # NO NPC LLM block update (NPCs not in config schema)
```

The tool only supports `--providers` as a positional list. All agents get
the same model from each provider spec.

### Enemy LLM inheritance (`enemy_combat.py:225-252`)

```python
# EnemyCombatManager.__init__:
dm_config = session_config.get('agents', {}).get('dm', {})
llm_config = dm_config.get('llm', {})
config = LLMConfig.from_dict(llm_config, max_tokens=4000)
self.llm_provider = create_provider(config)
```

Enemies ALWAYS inherit the DM's LLM config. There is no `agents.enemies.llm`
section in the config schema.

### NPC LLM inheritance (`npc_agent.py:305-306`)

NPCs receive an `llm_provider` at construction time, which comes from
`self.enemy_combat.llm_provider` in the session code. Same inheritance chain
as enemies.

### Legacy code path gating (`dm.py`)

The `_last_structured_resolution` attribute is checked at these locations:

| Line | Context | What it gates |
|------|---------|--------------|
| 2978-3009 | `_check_combat_outcome()` | Outcome tier extraction from structured vs text |
| 4657 | `_apply_failed_resolution()` | Sets failed resolution for error handling |
| 5299-5370 | `adjudicate()` (PC actions) | Structured extraction vs `parse_state_changes()` |
| 5370 | `adjudicate()` | Suppresses legacy damage when structured output active |
| 6051-6052 | `_process_awareness()` | Extracts `aware_agents` from structured output |
| 6243-6266 | `adjudicate()` (second path, ritual actions) | Same extraction logic, duplicated |
| 6582-6591 | `_check_combat_outcome()` (second path) | Same as 2978, duplicated |

Legacy text parsing functions called when `_last_structured_resolution` is None:

| Function | Called at | What it parses |
|----------|----------|---------------|
| `parse_state_changes()` | dm.py:5363, dm.py:6266 | Void changes, clock triggers, soulcredit from narration |
| `parse_combat_triplet()` | dm.py:5366 | Attack/defense/damage from `[COMBAT_TRIPLET]` markers |
| `parse_mechanical_effect()` | dm.py:5373 | `[MECHANICAL_EFFECT]` blocks for damage, debuffs, status |

Note: `parse_combat_triplet()` at line 5366 runs UNCONDITIONALLY (even when
structured output is active). The guard at line 5389 only suppresses the
damage effect application, not the parsing itself.

---

## Design Decisions (User Confirmed)

1. **Per-role model separation must be first-class.** The config generator
   must support `--dm-model`, `--player-model`, `--enemy-model`, and
   `--npc-model` independently.

2. **Legacy paths: audit and decide remove vs reframe.** The legacy text
   parsing pipeline should be documented with a formal inventory. Each code
   path gets a disposition: "remove" (dead code), "keep as fallback"
   (structured output can fail), or "keep as primary" (no structured
   equivalent exists yet).

---

## Proposed Solution

### Phase 1: Per-Role Config Sections

#### 1.1 Extend session config schema

Add optional `agents.enemies.llm` and `agents.npcs.llm` sections:

```json
{
  "agents": {
    "dm": {
      "llm": {
        "provider": "anthropic",
        "model": "claude-opus-4-6",
        "temperature": 0.7
      }
    },
    "players": [
      {
        "name": "Sera Karsel",
        "llm": {
          "provider": "openai",
          "model": "gpt-5-mini",
          "temperature": 0.8
        }
      }
    ],
    "enemies": {
      "llm": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.5
      }
    },
    "npcs": {
      "llm": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.6
      }
    }
  }
}
```

**Fallback chain:**
1. `agents.enemies.llm` if present
2. `agents.dm.llm` if `agents.enemies.llm` is absent (current behavior)

Same for NPCs:
1. `agents.npcs.llm` if present
2. `agents.enemies.llm` if present (enemies and NPCs share a tier)
3. `agents.dm.llm` as final fallback

#### 1.2 Update EnemyCombatManager (`enemy_combat.py:225-252`)

```python
def __init__(self, session_config: Dict[str, Any]):
    # ...existing code...

    # NEW: Read per-role enemy LLM config with fallback
    enemy_llm_config = (
        session_config.get('agents', {}).get('enemies', {}).get('llm')
        or session_config.get('agents', {}).get('dm', {}).get('llm')
    )

    if enemy_llm_config:
        from .llm_provider import LLMConfig
        config = LLMConfig.from_dict(enemy_llm_config, max_tokens=4000)
        self.llm_provider = create_provider(config)
        logger.debug(
            f"EnemyCombatManager: Using {'per-role enemy' if enemy_specific else 'DM fallback'} "
            f"LLM config ({config.provider}:{config.model})"
        )
```

#### 1.3 Update NPC spawn path (`session.py`)

When NPCs are created (via conversion or spawn), pass the NPC-specific LLM
config if available:

```python
# In _spawn_npc() or equivalent:
npc_llm_config = (
    self.config.get('agents', {}).get('npcs', {}).get('llm')
    or self.config.get('agents', {}).get('enemies', {}).get('llm')
    or self.config.get('agents', {}).get('dm', {}).get('llm')
)

if npc_llm_config:
    from .llm_provider import LLMConfig, create_provider
    config = LLMConfig.from_dict(npc_llm_config, max_tokens=2000)
    npc.llm_provider = create_provider(config)
```

### Phase 2: Config Generator Enhancement

#### 2.1 Add per-role flags to generate_multi_llm_configs.py

```python
parser.add_argument(
    "--dm-model",
    default=None,
    help='Override DM model only (e.g., "anthropic:claude-opus-4-6")'
)
parser.add_argument(
    "--player-model",
    default=None,
    help='Override all player models (e.g., "openai:gpt-5-mini")'
)
parser.add_argument(
    "--enemy-model",
    default=None,
    help='Override enemy model (e.g., "openai:gpt-4o-mini")'
)
parser.add_argument(
    "--npc-model",
    default=None,
    help='Override NPC model (e.g., "openai:gpt-4o-mini")'
)
```

**Behavior matrix:**

| Flag Present | Effect |
|-------------|--------|
| `--providers "openai:gpt-5-mini"` | All roles get gpt-5-mini (current behavior, backward compatible) |
| `--dm-model "anthropic:claude-opus-4-6"` | DM only. Players/enemies/NPCs unchanged from base config. |
| `--dm-model X --player-model Y` | DM gets X, all players get Y. Enemies/NPCs inherit from base. |
| `--providers X --enemy-model Y` | All agents get X, then enemy overridden to Y. |
| `--dm-model X --player-model Y --enemy-model Z` | Each role gets its own model. NPCs inherit from enemy. |

When `--enemy-model` is specified, the generator adds the `agents.enemies.llm`
section to the output config. When `--npc-model` is specified, adds
`agents.npcs.llm`.

#### 2.2 Update generate_config() function

```python
def generate_config(
    base_config: dict,
    provider: str = None,
    model: str = None,
    dm_spec: str = None,       # "provider:model" for DM
    player_spec: str = None,   # "provider:model" for players
    enemy_spec: str = None,    # "provider:model" for enemies
    npc_spec: str = None,      # "provider:model" for NPCs
    proxy_url: str = None
) -> dict:
    config = copy.deepcopy(base_config)

    # Legacy: --providers sets all roles to same model
    if provider and model:
        # Update DM
        if "agents" in config and "dm" in config["agents"]:
            config["agents"]["dm"]["llm"] = update_llm_block(
                config["agents"]["dm"].get("llm", {}), provider, model, proxy_url
            )
        # Update players
        if "agents" in config and "players" in config["agents"]:
            for player in config["agents"]["players"]:
                player["llm"] = update_llm_block(
                    player.get("llm", {}), provider, model, proxy_url
                )
        # NEW: Update enemies
        config.setdefault("agents", {}).setdefault("enemies", {})["llm"] = \
            update_llm_block({}, provider, model, proxy_url)
        # NEW: Update NPCs
        config.setdefault("agents", {}).setdefault("npcs", {})["llm"] = \
            update_llm_block({}, provider, model, proxy_url)

    # Per-role overrides (take precedence over --providers)
    if dm_spec:
        dm_provider, dm_model = dm_spec.split(":", 1)
        config["agents"]["dm"]["llm"] = update_llm_block(
            config["agents"]["dm"].get("llm", {}), dm_provider, dm_model, proxy_url
        )

    if player_spec:
        player_provider, player_model = player_spec.split(":", 1)
        for player in config.get("agents", {}).get("players", []):
            player["llm"] = update_llm_block(
                player.get("llm", {}), player_provider, player_model, proxy_url
            )

    if enemy_spec:
        enemy_provider, enemy_model = enemy_spec.split(":", 1)
        config.setdefault("agents", {}).setdefault("enemies", {})["llm"] = \
            update_llm_block({}, enemy_provider, enemy_model, proxy_url)

    if npc_spec:
        npc_provider, npc_model = npc_spec.split(":", 1)
        config.setdefault("agents", {}).setdefault("npcs", {})["llm"] = \
            update_llm_block({}, npc_provider, npc_model, proxy_url)

    return config
```

#### 2.3 Update session_name generation

When per-role models are specified, the session name should reflect which
models are in use:

```python
# Example: "combat_ambush_dm-claude-opus-4-6_players-gpt5mini"
name_parts = [base_name]
if dm_spec:
    dm_model = dm_spec.split(":", 1)[1]
    name_parts.append(f"dm-{sanitize_model_name(dm_model)}")
if player_spec:
    player_model = player_spec.split(":", 1)[1]
    name_parts.append(f"pc-{sanitize_model_name(player_model)}")
if enemy_spec:
    enemy_model = enemy_spec.split(":", 1)[1]
    name_parts.append(f"enemy-{sanitize_model_name(enemy_model)}")
config["session_name"] = "_".join(name_parts)
```

### Phase 3: Legacy Code Path Audit

#### 3.1 Create formal inventory

Document every `_last_structured_resolution` check and every legacy parsing
function call in a structured audit table. Each entry gets a disposition:

| Code Path | Location | Disposition | Rationale |
|-----------|----------|-------------|-----------|
| `parse_state_changes()` | dm.py:5363 | **Keep as fallback** | If structured output generation fails (LLM error, schema validation failure), the legacy path is the only way to extract any mechanical data from the narration. Without it, failed structured output = no game effects at all. |
| `parse_combat_triplet()` | dm.py:5366 | **Remove** | Always runs, even with structured output. Damage is already handled by `_process_structured_damage_effects()`. The triplet parsing is dead code when structured output is active. Guard at line 5389 suppresses the damage, but the parsing itself is wasted computation. |
| `parse_mechanical_effect()` | dm.py:5373 | **Remove** | Same as combat triplet. Structured output `effects.damage` and `effects.conditions` handle all mechanical effects. The `[MECHANICAL_EFFECT]` block format is a legacy prompt artifact. |
| `extract_from_structured_resolution()` | dm.py:5307, 6251 | **Keep as primary** | This IS the structured output path. Not legacy. |
| Outcome tier extraction | dm.py:2978-3009 | **Keep as primary** | Structured output path for outcome tiers. |
| Awareness extraction | dm.py:6051-6052 | **Keep as primary** | Structured output `aware_agents` field. |
| Duplicate adjudicate path | dm.py:6243-6266 | **Audit for consolidation** | Nearly identical to dm.py:5299-5370. Appears to handle ritual actions separately. Should be consolidated into single adjudication path. |
| Duplicate combat outcome check | dm.py:6582-6591 | **Audit for consolidation** | Same pattern as dm.py:2978-3009, duplicated for a second resolution context. |

#### 3.2 Add code-path router

Instead of scattered `if hasattr(self, '_last_structured_resolution')` checks,
introduce a single routing function:

```python
def _get_resolution_pipeline(self) -> str:
    """
    Determine which resolution pipeline to use.

    Returns:
        "structured" -- Use Pydantic structured output (preferred)
        "legacy" -- Use text parsing fallback
    """
    if (hasattr(self, '_last_structured_resolution')
            and self._last_structured_resolution is not None):
        return "structured"
    return "legacy"
```

All gating checks in `adjudicate()` and `_check_combat_outcome()` are
rewritten to call this method:

```python
# Before (scattered):
if hasattr(self, '_last_structured_resolution') and self._last_structured_resolution is not None:
    state_changes = extract_from_structured_resolution(...)
else:
    state_changes = parse_state_changes(...)

# After (centralized):
pipeline = self._get_resolution_pipeline()
if pipeline == "structured":
    state_changes = extract_from_structured_resolution(...)
elif pipeline == "legacy":
    state_changes = parse_state_changes(...)
```

This makes the routing explicit, searchable, and easier to eventually remove
the legacy branch.

#### 3.3 Add pipeline logging

Log which pipeline is used for each resolution:

```python
logger.info(f"Resolution pipeline: {pipeline} for {action.get('agent', 'unknown')}")
```

This enables post-hoc analysis of how often structured output fails and falls
back to legacy parsing across different models.

---

## Files to Modify

| File | Change |
|------|--------|
| `scripts/generate_multi_llm_configs.py` | Add `--dm-model`, `--player-model`, `--enemy-model`, `--npc-model` flags. Update `generate_config()` for per-role specs. Update session_name generation. |
| `scripts/aeonisk/multiagent/enemy_combat.py` | Read `agents.enemies.llm` config with fallback to `agents.dm.llm` (lines 225-252). |
| `scripts/aeonisk/multiagent/session.py` | Pass NPC-specific LLM config when spawning NPCs. Read `agents.npcs.llm` with fallback chain. |
| `scripts/aeonisk/multiagent/npc_agent.py` | No structural changes needed -- already accepts `llm_provider` parameter (line 306). |
| `scripts/aeonisk/multiagent/dm.py` | Add `_get_resolution_pipeline()` method. Refactor scattered `_last_structured_resolution` checks to use router. Add pipeline logging. Remove unconditional `parse_combat_triplet()` call when structured output active. |
| `tests/unit/test_session_config_validation.py` | Add tests for `agents.enemies.llm` and `agents.npcs.llm` optional sections. |

---

## Test Plan

### Unit Tests

#### Config Generation (`tests/unit/test_multi_llm_config.py` -- new file)

```python
def test_providers_flag_sets_all_roles():
    """--providers sets DM, players, enemies, and NPCs to same model."""
    base_config = {
        "session_name": "test",
        "agents": {
            "dm": {"llm": {"provider": "openai", "model": "gpt-4o-mini"}},
            "players": [
                {"name": "Sera", "llm": {"provider": "openai", "model": "gpt-4o-mini"}}
            ]
        }
    }
    result = generate_config(base_config, provider="anthropic", model="claude-opus-4-6")
    assert result["agents"]["dm"]["llm"]["model"] == "claude-opus-4-6"
    assert result["agents"]["players"][0]["llm"]["model"] == "claude-opus-4-6"
    assert result["agents"]["enemies"]["llm"]["model"] == "claude-opus-4-6"
    assert result["agents"]["npcs"]["llm"]["model"] == "claude-opus-4-6"

def test_dm_model_override_only():
    """--dm-model overrides DM only, leaves players unchanged."""
    base_config = {
        "session_name": "test",
        "agents": {
            "dm": {"llm": {"provider": "openai", "model": "gpt-5-mini"}},
            "players": [
                {"name": "Sera", "llm": {"provider": "openai", "model": "gpt-5-mini"}}
            ]
        }
    }
    result = generate_config(base_config, dm_spec="anthropic:claude-opus-4-6")
    assert result["agents"]["dm"]["llm"]["model"] == "claude-opus-4-6"
    assert result["agents"]["dm"]["llm"]["provider"] == "anthropic"
    assert result["agents"]["players"][0]["llm"]["model"] == "gpt-5-mini"  # Unchanged

def test_per_role_all_different():
    """Each role can have a different model."""
    base_config = {
        "session_name": "test",
        "agents": {
            "dm": {"llm": {"provider": "openai", "model": "gpt-4o-mini"}},
            "players": [
                {"name": "Sera", "llm": {"provider": "openai", "model": "gpt-4o-mini"}}
            ]
        }
    }
    result = generate_config(
        base_config,
        dm_spec="anthropic:claude-opus-4-6",
        player_spec="openai:gpt-5-mini",
        enemy_spec="openai:gpt-4o-mini",
        npc_spec="openai:gpt-4o-mini"
    )
    assert result["agents"]["dm"]["llm"]["model"] == "claude-opus-4-6"
    assert result["agents"]["players"][0]["llm"]["model"] == "gpt-5-mini"
    assert result["agents"]["enemies"]["llm"]["model"] == "gpt-4o-mini"
    assert result["agents"]["npcs"]["llm"]["model"] == "gpt-4o-mini"

def test_enemy_model_creates_config_section():
    """--enemy-model creates agents.enemies.llm section even if absent in base."""
    base_config = {
        "session_name": "test",
        "agents": {
            "dm": {"llm": {"provider": "openai", "model": "gpt-5-mini"}},
            "players": []
        }
    }
    result = generate_config(base_config, enemy_spec="openai:gpt-4o-mini")
    assert "enemies" in result["agents"]
    assert result["agents"]["enemies"]["llm"]["model"] == "gpt-4o-mini"

def test_session_name_includes_role_models():
    """Session name reflects per-role model choices."""
    base_config = {"session_name": "combat_ambush", "agents": {"dm": {"llm": {}}}}
    result = generate_config(
        base_config,
        dm_spec="anthropic:claude-opus-4-6",
        player_spec="openai:gpt-5-mini"
    )
    assert "dm-claudeopus46" in result["session_name"] or "dm-" in result["session_name"]
    assert "pc-" in result["session_name"]

def test_proxy_applied_to_per_role_models():
    """Proxy URL wraps per-role configs in batch_proxy routing."""
    base_config = {"session_name": "test", "agents": {"dm": {"llm": {}}}}
    result = generate_config(
        base_config,
        dm_spec="anthropic:claude-opus-4-6",
        proxy_url="http://localhost:8000"
    )
    assert result["agents"]["dm"]["llm"]["provider"] == "batch_proxy"
    assert result["agents"]["dm"]["llm"]["underlying_provider"] == "anthropic"
    assert result["agents"]["dm"]["llm"]["model"] == "claude-opus-4-6"
```

#### Enemy LLM Config (`tests/unit/test_enemy_llm_config.py` -- new file)

```python
def test_enemy_uses_own_config_when_present():
    """EnemyCombatManager reads agents.enemies.llm when available."""
    config = {
        "tactical_module_enabled": True,
        "enemy_agents_enabled": True,
        "agents": {
            "dm": {"llm": {"provider": "anthropic", "model": "claude-opus-4-6"}},
            "enemies": {"llm": {"provider": "openai", "model": "gpt-4o-mini"}}
        }
    }
    # Mock create_provider to capture which config is used
    # Assert: enemy provider uses gpt-4o-mini, not claude-opus-4-6

def test_enemy_falls_back_to_dm_when_absent():
    """EnemyCombatManager falls back to agents.dm.llm when no enemy config."""
    config = {
        "tactical_module_enabled": True,
        "enemy_agents_enabled": True,
        "agents": {
            "dm": {"llm": {"provider": "anthropic", "model": "claude-opus-4-6"}}
        }
    }
    # Assert: enemy provider uses claude-opus-4-6 (DM fallback)

def test_npc_fallback_chain():
    """NPC LLM config follows fallback: npcs -> enemies -> dm."""
    # Test all three levels of the fallback chain
```

#### Session Config Validation (`tests/unit/test_session_config_validation.py` -- extend)

```python
def test_enemies_llm_section_optional():
    """agents.enemies.llm is optional; absence does not cause errors."""
    # Existing configs without agents.enemies should load fine

def test_npcs_llm_section_optional():
    """agents.npcs.llm is optional; absence does not cause errors."""

def test_enemies_llm_section_validates():
    """agents.enemies.llm must have provider and model if present."""
```

#### Legacy Pipeline Router (`tests/unit/test_dm_resolution_pipeline.py` -- new file)

```python
def test_structured_pipeline_when_resolution_set():
    """_get_resolution_pipeline returns 'structured' when resolution exists."""
    dm = AIDMAgent(...)
    dm._last_structured_resolution = MockResolution()
    assert dm._get_resolution_pipeline() == "structured"

def test_legacy_pipeline_when_resolution_none():
    """_get_resolution_pipeline returns 'legacy' when no structured resolution."""
    dm = AIDMAgent(...)
    dm._last_structured_resolution = None
    assert dm._get_resolution_pipeline() == "legacy"

def test_combat_triplet_not_called_in_structured_mode():
    """parse_combat_triplet() is not called when structured output is active."""
    # Mock and verify parse_combat_triplet is not invoked
```

---

## Open Questions

1. **Per-player model variation:** Should individual players be able to have
   different models from each other? Current design updates all players to
   the same `--player-model`. Supporting per-player variation would require
   a more complex CLI (e.g., `--player-0-model`, `--player-1-model`) or a
   YAML config file instead of CLI flags.

2. **Legacy path removal timeline:** Should the legacy text parsing functions
   be removed in this spec, or should they remain as fallbacks until
   structured output is proven stable across all providers? The audit creates
   the inventory; removal is a separate decision.

3. **Cost reporting:** When per-role models are used, the bulk runner should
   report estimated cost per session broken down by role. This requires
   knowing token costs per model per provider. Is this in scope?

4. **Validation of model availability:** Should the config generator validate
   that the specified provider:model pairs are actually available (e.g., check
   that the API key supports the model)? Or is that the bulk runner's job?

5. **Backward compatibility of `--providers`:** Should `--providers` continue
   to set ALL roles (including the new enemies/npcs sections), or should it
   only set DM + players (matching current behavior)? The spec proposes setting
   all roles for maximum consistency, but this changes behavior for existing
   scripts that use `--providers`.

6. **Duplicate adjudication paths:** `dm.py` lines 5299-5370 and 6243-6266
   contain nearly identical structured output extraction logic. Should this
   spec consolidate them into a single function, or is that a separate
   refactoring effort?

---

## Migration Notes

### Backward Compatibility

- `generate_multi_llm_configs.py` with only `--providers` flag works exactly
  as before (all agents get same model). New flags are additive.
- Session configs without `agents.enemies.llm` or `agents.npcs.llm` work
  exactly as before (enemies/NPCs inherit from DM).
- The `_get_resolution_pipeline()` method centralizes existing behavior
  without changing the actual pipeline selection logic. No behavior change.
- All existing tests continue to pass because no resolution logic changes --
  only the routing pattern is refactored.

### New Session Config Fields

```json
{
  "agents": {
    "enemies": {
      "llm": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.5
      }
    },
    "npcs": {
      "llm": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.6
      }
    }
  }
}
```

Both sections are entirely optional. When absent, the existing fallback chain
applies.
