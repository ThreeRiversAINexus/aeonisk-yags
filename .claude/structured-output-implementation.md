# Structured Output Implementation - Phase 1 Complete

**Branch:** `revamp-structured-output`
**Date:** 2025-10-29
**Status:** ✅ Phase 1 Foundation Complete

## Summary

Successfully migrated from text parsing + keyword detection to **Pydantic AI structured output** for type-safe, multi-provider LLM responses.

**Philosophy:** Keep narration freeform (500-1500 chars creative storytelling), but structure the mechanics (damage, void, clocks, conditions).

## What Was Built

### 1. Schema System (`scripts/aeonisk/multiagent/schemas/`)

**7 new files:**
- `__init__.py` - Package exports
- `shared_types.py` - Common Pydantic models (VoidChange, DamageEffect, ClockUpdate, etc.)
- `action_resolution.py` - DM action resolution schema
- `player_action.py` - Player action declaration schema
- `enemy_decision.py` - Enemy tactical decision schema
- `story_events.py` - Story advancement, clocks, enemy spawns
- `README.md` - Comprehensive documentation

**Key schemas:**
```python
class ActionResolution(BaseModel):
    narration: str  # 200-2000 chars freeform
    success_tier: SuccessTier
    margin: int
    effects: MechanicalEffects  # Structured mechanics

class MechanicalEffects(BaseModel):
    damage: Optional[DamageEffect]
    void_changes: List[VoidChange]
    clock_updates: List[ClockUpdate]
    conditions: List[Condition]
    # ... more
```

### 2. LLM Provider Extension

**Modified:** `llm_provider.py`

**New method:** `ClaudeProvider.generate_structured()`
- Uses Pydantic AI `Agent` with `result_type` parameter
- Inherits retry/backoff/rate-limiting from existing code
- Returns validated Pydantic model instance
- Multi-provider ready (Claude, GPT-4, local models)

**Example usage:**
```python
from llm_provider import create_claude_provider
from schemas.action_resolution import ActionResolution

provider = create_claude_provider(model="claude-sonnet-4-5")

resolution: ActionResolution = await provider.generate_structured(
    prompt="Resolve action: ...",
    result_type=ActionResolution,
    system_prompt="You are the DM..."
)

# resolution is validated, no text parsing needed
print(resolution.effects.void_changes[0].amount)  # Direct access
```

### 3. Test Suite

**New file:** `test_structured_output.py`

**Tests:**
1. Manual schema creation (validates structure)
2. ActionResolution with Claude API
3. PlayerAction with Claude API

**Run:**
```bash
cd scripts/aeonisk
source .venv/bin/activate
python3 multiagent/test_structured_output.py
```

### 4. Dependencies

**Added to:** `scripts/aeonisk/benchmark/requirements.txt`
```
pydantic-ai>=0.0.13  # Structured output with multi-provider support
```

**Install:**
```bash
cd scripts/aeonisk
source .venv/bin/activate
pip install pydantic-ai
```

## Why This Matters

### Problems Solved

**1. Keyword Detection Eliminated**
- ❌ Old: "center mass" → "center" → false "grounding meditation" match
- ✅ New: `effects.void_changes=[VoidChange(...)]` explicit

**2. Multi-Provider Support**
- ❌ Old: Tied to Claude's marker format (`⚫ Void: +1`)
- ✅ New: Same schemas work with Claude, GPT-4, local models

**3. Type Safety**
- ❌ Old: Silent parsing failures (missing marker = no effect)
- ✅ New: Pydantic validation catches malformed output

**4. Better ML Training**
- ❌ Old: Parse markers from text (ambiguous, brittle)
- ✅ New: Structured fields (clean, explicit, easy to train on)

### What's Preserved

**Narrative creativity:** LLM still writes 500-1500 char freeform stories
**Backward compat:** All schemas provide `to_legacy_dict()` for gradual migration
**Existing code:** Works alongside current system during transition

## Implementation Details

### Hybrid Approach

```
┌─────────────────────────────────────────┐
│    LLM Response (ActionResolution)      │
├─────────────────────────────────────────┤
│ narration: str (FREEFORM, 500-1500 chars)│  ← Creative storytelling
│ "Echo's neural interface crackles..."   │
│                                         │
│ effects: MechanicalEffects {           │  ← Validated mechanics
│   void_changes: [                      │
│     VoidChange(                        │
│       character_name="Echo",           │
│       amount=1,                        │
│       reason="Interface feedback"      │
│     )                                  │
│   ]                                    │
│ }                                      │
└─────────────────────────────────────────┘
```

**Key insight:** Narration stays creative, mechanics are structured.

### Design Philosophy

> "I hate keyword detection as a mechanic and want the DM to interpret it during resolution."

**Old approach:**
1. LLM writes: "Echo's scan succeeds! ⚫ Void: +1 (interface feedback)"
2. Parser searches for `⚫ Void: +1` marker
3. If marker malformed → silent failure (no void change!)

**New approach:**
1. LLM generates structured `ActionResolution` object
2. Pydantic validates: `effects.void_changes` must be `List[VoidChange]`
3. If invalid → validation error, can retry with feedback
4. If valid → direct access to typed data

**Result:** No keywords, no parsing, no false positives.

## Next Steps

### Phase 2: DM Resolution Migration
- [ ] Refactor `dm.py._build_dm_narration_prompt()` to use `ActionResolution`
- [ ] Update `outcome_parser.py` for dual mode (legacy + structured)
- [ ] Run test sessions comparing old vs new output
- [ ] Fix any validation issues

### Phase 3: Player Actions
- [ ] Refactor `player.py._declare_action()` to use `PlayerAction`
- [ ] Remove skill routing logic (agents choose skills explicitly)
- [ ] Test action variety and quality

### Phase 4: Enemies & Story
- [ ] Refactor `enemy_combat.py` to use `EnemyDecision`
- [ ] Refactor `session.py` to use `StoryEvent` schemas
- [ ] Full integration test
- [ ] Multi-provider validation (Claude + OpenAI)

## Files Created

**New files (9):**
1. `scripts/aeonisk/multiagent/schemas/__init__.py`
2. `scripts/aeonisk/multiagent/schemas/shared_types.py`
3. `scripts/aeonisk/multiagent/schemas/action_resolution.py`
4. `scripts/aeonisk/multiagent/schemas/player_action.py`
5. `scripts/aeonisk/multiagent/schemas/enemy_decision.py`
6. `scripts/aeonisk/multiagent/schemas/story_events.py`
7. `scripts/aeonisk/multiagent/schemas/README.md`
8. `scripts/aeonisk/multiagent/test_structured_output.py`
9. `.claude/current-work/structured-output-implementation.md` (this file)

**Modified files (2):**
1. `scripts/aeonisk/benchmark/requirements.txt` - Added pydantic-ai
2. `scripts/aeonisk/multiagent/llm_provider.py` - Added `generate_structured()` method

## Testing

**Manual schema creation:**
```python
from schemas.action_resolution import create_combat_resolution

resolution = create_combat_resolution(
    narration="Ash's void beam strikes true...",
    margin=12,
    target="Void Scanner Alpha",
    base_damage=15,
    soak=8,
    dealt=7
)

print(resolution.effects.damage.dealt)  # 7
```

**API testing:**
```bash
cd scripts/aeonisk
source .venv/bin/activate

# Run test suite
python3 multiagent/test_structured_output.py

# Manual test
python3 -c "
import asyncio
from multiagent.llm_provider import create_claude_provider
from multiagent.schemas.player_action import PlayerAction, ActionType

async def test():
    provider = create_claude_provider()
    action = await provider.generate_structured(
        prompt='Declare an action',
        result_type=PlayerAction,
        system_prompt='You are Ash Vex. Declare a void cleansing ritual.'
    )
    print(action.get_summary())

asyncio.run(test())
"
```

## Examples

### Example 1: DM Resolution (Combat)
```python
resolution = ActionResolution(
    narration="""Thresh's rifle barks once, twice. The first shot shatters
    the scanner's optical array in a spray of crystalline fragments. The second
    punches clean through its power core. Sparks cascade as the device staggers,
    teeters, then collapses with a metallic shriek.""",

    success_tier=SuccessTier.EXCELLENT,
    margin=17,

    effects=MechanicalEffects(
        damage=DamageEffect(
            target="Void Scanner Alpha",
            base_damage=18,
            soak=8,
            dealt=10
        ),
        clock_updates=[
            ClockUpdate(
                clock_name="Enemy Reinforcements",
                ticks=1,
                reason="Gunfire alerts nearby patrols"
            )
        ]
    )
)
```

### Example 2: Player Action (Ritual)
```python
action = PlayerAction(
    intent="Perform void purification ritual on Ash Vex",
    description="Channel cleansing energy through astral focus at ley intersection to purge Ash's void corruption",

    attribute="Willpower",
    skill="Astral Arts",
    difficulty_estimate=28,
    difficulty_justification="Very difficult: target has void 9, no offering, hostile environment",

    action_type=ActionType.RITUAL,
    character_name="Riven Shard",
    agent_id="player_riven",
    target="Ash Vex",

    is_ritual=True,
    has_primary_tool=True,
    has_offering=False,
    ritual_components="Astral focus, ley line resonance"
)
```

### Example 3: Story Advancement
```python
advancement = StoryAdvancement(
    should_advance=True,
    location="Collapsed Transit Tunnel - Junction B-7",
    situation="The void surge stabilizes, but junction B-7's tunnel has collapsed. Through the rubble, you hear voices - survivors trapped on the other side, and something else moving in the dark.",

    new_clocks=[
        NewClock(
            name="Survivor Rescue",
            max_ticks=8,
            description="Dig through rubble before oxygen runs out",
            advance_meaning="survivors rescued",
            regress_meaning="tunnel stability failing"
        ),
        NewClock(
            name="Void Manifestation",
            max_ticks=6,
            description="Something awakening in the void-saturated rubble",
            advance_meaning="manifestation emerges",
            regress_meaning="void energy contained"
        )
    ]
)
```

## Multi-Provider Testing

**Ready for:**
```python
# Anthropic Claude
provider = create_claude_provider(model="claude-sonnet-4-5")

# OpenAI GPT-4 (future - Phase 6)
provider = create_openai_provider(model="gpt-4-turbo-preview")

# Local Ollama (future - Phase 6)
provider = create_local_provider(model="llama3.1")

# All use same API
resolution = await provider.generate_structured(
    prompt=prompt,
    result_type=ActionResolution,
    system_prompt=system_prompt
)
```

## Documentation

**Comprehensive docs:**
- `schemas/README.md` - Full schema documentation with examples
- `test_structured_output.py` - Runnable tests with usage examples
- This file - Implementation summary

**Key points:**
1. **Why:** Eliminates keyword detection, multi-provider ready, type-safe
2. **What:** 7 schema files + llm_provider extension + test suite
3. **How:** Pydantic AI `Agent` with `result_type` parameter
4. **Migration:** Gradual, backward compatible via `to_legacy_dict()`

## Success Criteria (Phase 1) ✅

- ✅ **No keyword detection** - Mechanical effects are explicit structured fields
- ✅ **Type validation** - Pydantic catches schema errors before game state corruption
- ✅ **Multi-provider ready** - Schemas work with any Pydantic AI provider
- ✅ **Narration preserved** - 500-1500 char freeform storytelling maintained
- ✅ **Backward compat** - `to_legacy_dict()` methods for gradual migration
- ✅ **Tests passing** - Manual + API tests validate structure and integration

## Notes for Next Developer

**Starting Phase 2?**

1. Read `schemas/README.md` first (comprehensive guide)
2. Run `test_structured_output.py` to verify setup
3. Start with `dm.py._build_dm_narration_prompt()`:
   ```python
   # Old:
   response = self.llm_client.messages.create(...)
   narration = response.content[0].text
   state_changes = parse_state_changes(narration, ...)

   # New:
   resolution = await self.llm_provider.generate_structured(
       prompt=prompt,
       result_type=ActionResolution,
       system_prompt=system_prompt
   )
   # resolution.narration, resolution.effects ready to use
   ```

4. Update `outcome_parser.py` for dual mode:
   ```python
   if isinstance(resolution, ActionResolution):
       # Use structured output
       return extract_from_structured(resolution.effects)
   else:
       # Fall back to legacy marker parsing
       return extract_from_markers(narration)
   ```

**Questions?**
- Check `schemas/README.md` FAQ
- Review test examples in `test_structured_output.py`
- See `CLAUDE.md` for project context

---

**Branch:** `revamp-structured-output`
**Phase 1:** ✅ Complete (Foundation)
**Phase 2:** ⏳ Ready to start (DM resolution migration)
**Estimated effort:** ~2-3 days per phase (4 phases total)
