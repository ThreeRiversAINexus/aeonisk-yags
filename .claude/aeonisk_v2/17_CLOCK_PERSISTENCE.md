# Spec 17: Clock Persistence Across Story Advancement

**Priority:** P1 (Wave 2 -- Parallel, no dependencies)
**Status:** Not started
**Dependencies:** None
**Estimated Scope:** Small

---

## Problem Statement

When a story advances (`StoryAdvancement.should_advance=True`), **all scene clocks
are unconditionally cleared** at `session.py:5209`:

```python
mechanics.scene_clocks.clear()  # Blanket wipe
```

Every clock is destroyed regardless of narrative relevance. A "Corporate Pursuit"
clock tracking a faction hunting the party across multiple locations gets wiped the
moment the party moves to a new scene. A "Courier's Dying Breath" clock that was
just introduced two rounds ago gets wiped if the DM decides to pivot the story.

This kills multi-scene story arcs. Clocks are the primary mechanical representation
of ongoing narrative tension, and blanket clearing forces every arc to be
scene-local. The DM cannot maintain persistent threats, ticking timebombs, or
long-running objectives across scene boundaries.

### The Asymmetry

`ScenePivot` (minor scene changes) already has selective clock clearing:

```python
class ScenePivot(BaseModel):
    clear_specific_clocks: List[str] = Field(
        default_factory=list,
        description="Specific clock names to clear (selective). Empty = keep all clocks."
    )
```

And the session code at `session.py:5464-5496` implements it correctly — only the
named clocks are removed, everything else persists.

`StoryAdvancement` has no equivalent. The schema has no field for the DM to express
"keep these clocks." The session code does not check — it calls `.clear()`.

| | ScenePivot | StoryAdvancement |
|--|-----------|-----------------|
| Clock clearing | Selective (`clear_specific_clocks`) | Blanket (`.clear()`) |
| Default behavior | Keep all clocks | Remove all clocks |
| DM control | Full | None |

### Impact on Gameplay

- **Short-lived clocks:** Clocks rarely survive more than 2-3 rounds because DMs
  advance the story frequently. This makes clocks feel disposable.
- **No persistent threats:** "ACG Lockdown" or "Void Storm Approaching" clocks
  that should span an entire session get wiped on the first scene change.
- **DM workaround:** The DM sometimes re-creates the same clock in `new_clocks`
  after advancement, but loses the tick progress. A clock at 4/8 becomes 0/8.
- **ML training data:** Clock lifecycle events show artificial patterns — clocks
  are always created and destroyed within the same scene, never carried forward.
  Models trained on this data learn that clocks are scene-scoped, not arc-scoped.

---

## Current Implementation

### StoryAdvancement Schema (`schemas/story_events.py:183-277`)

```python
class StoryAdvancement(BaseModel):
    should_advance: bool
    location: Optional[str]
    situation: Optional[str]
    new_void_level: Optional[int]
    clear_all_enemies: bool = True
    new_clocks: List[NewClock]
    vendor_departures: List[str]
    altar_removals: List[str]
    # ❌ No clock persistence field
```

Note that `clear_all_enemies` already demonstrates the pattern — a boolean that
defaults to clearing but allows the DM to override. Clocks need the same treatment.

### Blanket Clearing Code (`session.py:5179-5210`)

```python
# Clear clocks (always happens on story advancement)
if mechanics and mechanics.scene_clocks:
    for clock_name, clock in mechanics.scene_clocks.items():
        if mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_event(
                event_type="clock_removal",
                data={
                    "clock_name": clock_name,
                    "current_ticks": clock.current,
                    "maximum_ticks": clock.maximum,
                    "description": clock.description,
                    "removal_reason": "story_advancement"
                },
                round_num=mechanics.current_round
            )
        mechanics.clock_history.append({...})

    archived_clocks = list(mechanics.scene_clocks.keys())
    mechanics.scene_clocks.clear()  # <-- THE PROBLEM
```

### ScenePivot Selective Clearing (`session.py:5464-5496`)

Already works correctly. Only clears named clocks:

```python
if pivot.clear_specific_clocks and mechanics:
    for clock_name in pivot.clear_specific_clocks:
        if clock_name in mechanics.scene_clocks:
            clock = mechanics.scene_clocks[clock_name]
            # Log removal...
            del mechanics.scene_clocks[clock_name]
```

### DM Prompt Guidance (`dm.py:~4065`)

Current guidance tells the DM that clocks always clear on advancement:

```
**What happens:** Clocks clear, location updates, enemies despawn
(unless `clear_all_enemies=False`), new clocks spawn.
```

No mention of clock persistence. The DM has no reason to think it can keep clocks.

---

## Proposed Solution

### Approach: Opt-In Persistence (keep_clocks)

Add a `keep_clocks` field to `StoryAdvancement`. Default behavior remains "clear
all" for backward compatibility. The DM explicitly names clocks that should survive
the transition.

**Why opt-in (keep) rather than opt-out (clear_specific)?**

Story advancement is a major transition. The default assumption that most clocks
are scene-local is reasonable — "Breach Containment" doesn't make sense after
leaving the facility. The DM should actively decide which clocks carry forward,
not which ones to drop. This matches how `clear_all_enemies` works (default: clear,
opt-out to keep).

`ScenePivot` uses the inverse (`clear_specific_clocks`, default: keep all) because
minor scene changes should preserve state by default. The asymmetry is intentional
and correct.

### Change 1: Schema Addition (`schemas/story_events.py`)

```python
class StoryAdvancement(BaseModel):
    # ... existing fields ...

    keep_clocks: List[str] = Field(
        default_factory=list,
        description=(
            "Clock names to preserve across story advancement (e.g., "
            "['Corporate Pursuit', 'Void Storm Approaching']). "
            "Clocks NOT in this list are cleared. Empty list = clear all clocks "
            "(current default behavior). Preserved clocks retain their current "
            "tick progress."
        )
    )
```

### Change 2: Conditional Clearing (`session.py:5179-5210`)

Replace the blanket clear with selective removal:

```python
if mechanics and mechanics.scene_clocks:
    keep_set = set(getattr(adv, 'keep_clocks', []) or [])

    clocks_to_remove = [
        name for name in mechanics.scene_clocks
        if name not in keep_set
    ]

    for clock_name in clocks_to_remove:
        clock = mechanics.scene_clocks[clock_name]
        if mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_event(
                event_type="clock_removal",
                data={
                    "clock_name": clock_name,
                    "current_ticks": clock.current,
                    "maximum_ticks": clock.maximum,
                    "description": clock.description,
                    "removal_reason": "story_advancement"
                },
                round_num=mechanics.current_round
            )
        mechanics.clock_history.append({
            'name': clock_name,
            'final_ticks': clock.current,
            'max_ticks': clock.maximum,
            'removed_reason': 'story_advancement'
        })

    # Remove only non-kept clocks
    for clock_name in clocks_to_remove:
        del mechanics.scene_clocks[clock_name]

    kept_count = len(keep_set & set(mechanics.scene_clocks.keys()))
    removed_count = len(clocks_to_remove)
    if kept_count > 0:
        kept_names = [n for n in mechanics.scene_clocks.keys()]
        logger.info(
            f"🗑️  Cleared {removed_count} clocks for story advancement, "
            f"kept {kept_count}: {kept_names}"
        )
    else:
        logger.info(f"🗑️  Cleared {removed_count} clocks for story advancement")
```

### Change 3: DM Prompt Update

Update the story advancement guidance in the DM prompt to explain clock persistence:

```
**What happens:** Location updates, enemies despawn (unless
`clear_all_enemies=False`), new clocks spawn. Clocks NOT listed in
`keep_clocks` are cleared. Use `keep_clocks` to carry forward ongoing
threats, objectives, or timers that span multiple scenes (e.g., a
faction pursuit clock, a ticking void storm, a dying NPC's countdown).
Preserved clocks keep their current tick progress.
```

### Change 4: JSONL Logging Enhancement

Log kept clocks alongside removed clocks for ML visibility:

```python
# After clearing, log which clocks were kept and why
for clock_name in keep_set:
    if clock_name in mechanics.scene_clocks:
        clock = mechanics.scene_clocks[clock_name]
        if mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_event(
                event_type="clock_update",
                data={
                    "clock_name": clock_name,
                    "current_ticks": clock.current,
                    "maximum_ticks": clock.maximum,
                    "description": clock.description,
                    "update_reason": "persisted_through_story_advancement"
                },
                round_num=mechanics.current_round
            )
```

---

## Files to Modify

| File | Change |
|------|--------|
| `schemas/story_events.py` | Add `keep_clocks: List[str]` to `StoryAdvancement` |
| `session.py:5179-5210` | Replace blanket `.clear()` with selective removal respecting `keep_clocks` |
| `dm.py:~4065` | Update DM prompt guidance to explain `keep_clocks` |

---

## Test Plan

```python
# tests/unit/test_clock_persistence.py

def test_story_advancement_clears_all_clocks_by_default():
    """Default behavior unchanged: empty keep_clocks clears everything."""
    adv = StoryAdvancement(
        should_advance=True,
        location="Transit Hub",
        situation="..." ,
        keep_clocks=[]  # default
    )
    # Setup: 3 active clocks
    # Apply story advancement
    # Assert: all 3 clocks removed
    assert len(mechanics.scene_clocks) == 0

def test_story_advancement_keeps_named_clocks():
    """Clocks listed in keep_clocks survive story advancement."""
    adv = StoryAdvancement(
        should_advance=True,
        location="Transit Hub",
        situation="...",
        keep_clocks=["Corporate Pursuit"]
    )
    # Setup: clocks = {"Corporate Pursuit": 4/8, "Breach Containment": 3/6, "Alarm": 2/4}
    # Apply story advancement
    # Assert: only "Corporate Pursuit" remains
    assert "Corporate Pursuit" in mechanics.scene_clocks
    assert "Breach Containment" not in mechanics.scene_clocks
    assert "Alarm" not in mechanics.scene_clocks

def test_kept_clocks_retain_tick_progress():
    """Preserved clocks keep their current tick count, not reset to 0."""
    adv = StoryAdvancement(
        should_advance=True,
        location="Transit Hub",
        situation="...",
        keep_clocks=["Corporate Pursuit"]
    )
    # Setup: "Corporate Pursuit" at 4/8
    # Apply story advancement
    assert mechanics.scene_clocks["Corporate Pursuit"].current == 4
    assert mechanics.scene_clocks["Corporate Pursuit"].maximum == 8

def test_keep_clocks_ignores_nonexistent_names():
    """Naming a clock that doesn't exist in keep_clocks is a no-op, not an error."""
    adv = StoryAdvancement(
        should_advance=True,
        location="Transit Hub",
        situation="...",
        keep_clocks=["Nonexistent Clock"]
    )
    # Setup: clocks = {"Alarm": 2/4}
    # Apply story advancement
    # Assert: "Alarm" cleared (not in keep list), no error for nonexistent
    assert len(mechanics.scene_clocks) == 0

def test_keep_all_clocks():
    """Listing every clock in keep_clocks preserves all of them."""
    adv = StoryAdvancement(
        should_advance=True,
        location="Transit Hub",
        situation="...",
        keep_clocks=["Clock A", "Clock B", "Clock C"]
    )
    # Setup: 3 clocks matching the keep list
    # Apply story advancement
    assert len(mechanics.scene_clocks) == 3

def test_clock_removal_logged_for_cleared_clocks():
    """Cleared clocks emit clock_removal JSONL events."""
    # Setup: 2 clocks, keep 1
    # Apply story advancement
    # Assert: 1 clock_removal event logged with removal_reason="story_advancement"

def test_clock_persistence_logged_for_kept_clocks():
    """Kept clocks emit clock_update JSONL events with persistence reason."""
    # Setup: 2 clocks, keep 1
    # Apply story advancement
    # Assert: 1 clock_update event logged with update_reason="persisted_through_story_advancement"

def test_schema_backward_compatible():
    """StoryAdvancement without keep_clocks field deserializes with empty list."""
    # Simulate old-format JSON without keep_clocks
    data = {
        "should_advance": True,
        "location": "Transit Hub",
        "situation": "A" * 50,  # min_length=50
    }
    adv = StoryAdvancement(**data)
    assert adv.keep_clocks == []

def test_new_clocks_spawn_after_selective_clearing():
    """new_clocks are added after clearing, coexisting with kept clocks."""
    adv = StoryAdvancement(
        should_advance=True,
        location="Transit Hub",
        situation="...",
        keep_clocks=["Corporate Pursuit"],
        new_clocks=[NewClock(name="Courier's Life", max_ticks=6, description="...")]
    )
    # Setup: "Corporate Pursuit" at 4/8, "Alarm" at 2/4
    # Apply story advancement
    # Assert: "Corporate Pursuit" kept (4/8), "Alarm" cleared, "Courier's Life" spawned (0/6)
    assert "Corporate Pursuit" in mechanics.scene_clocks
    assert "Courier's Life" in mechanics.scene_clocks
    assert "Alarm" not in mechanics.scene_clocks
```

---

## Open Questions

1. **Clock name fuzzy matching?** If the DM writes `keep_clocks=["Corporate pursuit"]`
   (lowercase p) but the clock is named `"Corporate Pursuit"`, should we fuzzy match?
   Conservative approach: exact match only, log a warning if a keep_clocks entry
   doesn't match any active clock. Same philosophy as the name matching system
   (Spec note: `name_matching.py` already exists for character names — could be
   reused for clocks if fuzzy matching is desired).

2. **Max kept clocks?** Should there be a cap on how many clocks persist? Unbounded
   accumulation across many scene changes could bloat clock state. Recommendation:
   no hard cap — the DM prompt naturally limits this since the DM must explicitly
   name each clock. If it becomes a problem, cap at 6 (matching typical max active
   clocks).

---

## Migration Notes

### Backward Compatibility

Full. `keep_clocks` defaults to empty list, which preserves current blanket-clear
behavior. Old session configs, old fixtures, and old LLM-generated StoryAdvancement
outputs all work unchanged.

### JSONL Logging Impact

No new event types. Uses existing `clock_removal` and `clock_update` event types.
Adds `"persisted_through_story_advancement"` as a new `update_reason` value.
`LOGGING_IMPLEMENTATION.md` should document this reason value.

### Performance

Negligible. Iterates the clock dict (typically 2-5 entries) one extra time for
set membership check.
