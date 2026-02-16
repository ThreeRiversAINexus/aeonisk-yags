# 16: Adjudication Context -- Stateless Resolution Causes Incoherent Soulcredit Scoring

**Priority:** P1
**Status:** Spec Draft
**Dependencies:** None (architectural, independent of other specs)
**Estimated Scope:** Medium-Large (prompt engineering + state tracking + context injection)

---

## Problem Statement

The DM adjudicates every action **statelessly**. Its prompt contains exactly two
messages -- a system prompt with rules and schemas, and a user message with the
current action. No conversation history. No previous rounds. No memory of what
happened earlier in the session.

The DM generates narration, damage, and soulcredit scoring **simultaneously** in
a single structured output. It is not retroactively judging outcomes -- it produces
all of them at once, with no visibility into what came before.

### Why This Matters

Soulcredit scoring requires **moral context** that cannot be derived from a single
action in isolation. The DM sees the current action's attribute, skill, roll
result, target, and scenario description -- but not:

- Prior cooperation arcs (4 rounds of partnership, then betrayal)
- Repeated behavior patterns (character keeps attacking surrendered enemies)
- Whether the same soulcredit penalty was already applied this round
- Escalation/de-escalation trajectories across the session
- Previous narration that established relationships between characters

Without this context, the DM applies soulcredit rules mechanically from faction
labels and scenario descriptions, producing scoring that is locally reasonable
but globally incoherent.

### Concrete Example: Same-Faction "Betrayal" False Positive

From baseline datamining, the DM sees:

```
Acting character: "Enforcer Kael Dren (Pantheon Security)"
Declared target: "DECLARED TARGET: [tgt_jyho] Drifter Sable"
Target list:
  - [tgt_xxxx] Drifter Sable (no tag)
  - [tgt_yyyy] Enforcer Kael Dren (no tag)
  - [tgt_zzzz] Pantheon Patrol Alpha (enemy)
  - [tgt_wwww] Pantheon Patrol Beta (enemy)
Soulcredit rules: "Fighting own faction/allies: -2 (betrayal)"
```

The DM sees Kael (Pantheon Security) and Pantheon Patrols (also Pantheon, tagged
as enemies). It has zero context for **why** Pantheon patrols are tagged as
enemies -- maybe the scenario established a rogue patrol, maybe Kael is
undercover, maybe the patrols turned hostile in R1. The DM can only infer from
the current snapshot, leading to:

1. **False betrayal penalties:** If Kael attacks a patrol that was established as
   hostile in prior rounds, the DM sees "same faction, -2 betrayal" because it
   has no memory of the patrol's aggression.

2. **Missing betrayal penalties:** If a character cooperated with someone for 4
   rounds and then attacks them, the DM has no knowledge of the cooperation arc
   and may score the attack as "justified combat (+0)" instead of recognizing
   the betrayal.

3. **Inconsistent scoring across rounds:** The DM might award +1 soulcredit for
   "restraint" in R3 and then -1 for the same type of action in R5, because it
   has no memory of its own prior scoring.

### Impact on ML Training Data

Soulcredit labels in JSONL training data are used downstream for:

- Moral reasoning evaluation (does the model understand ethical nuance?)
- Reward modeling (soulcredit as a proxy for alignment signal)
- Behavioral clustering (which character archetypes earn/lose soulcredit?)

Stateless scoring produces labels that are **noisy at best, contradictory at
worst**. A model trained on these labels will learn that the same action can
receive +1 or -1 depending on which round it occurs in -- not because of moral
context, but because the DM had no memory.

---

## Current Implementation

### Adjudication Message Structure (2 messages)

**File:** `dm.py:7019-7026` (system prompt), `dm.py:7426-7615` (user prompt)

```python
# dm.py:7019-7026 -- System prompt construction
system_prompt_obj = load_modular_prompt(
    agent_type="dm",
    module_names=required_modules,
    provider="claude",
    language="en",
    variables={"clock_context": clock_context}
)
system_prompt = system_prompt_obj.content
```

```python
# dm.py:7237-7248 -- LLM call with exactly 2 messages
self.llm_logger._log_llm_call(
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ],
    response=resolution_obj.narration,
    ...
)
```

There is no `assistant` message from a prior turn. No conversation history. Each
action resolution is a cold-start LLM call.

### User Prompt Contents (dm.py:6728-6869, _build_dm_narration_prompt)

The user prompt includes:

| Section | Present? | Contains Historical Context? |
|---------|----------|------------------------------|
| Scenario context | Yes | No (static scenario description) |
| Character name + faction | Yes | No (identity only) |
| Party personalities | Yes | No (static character descriptions) |
| Roll result + margin | Yes | No (current action only) |
| Player action description | Yes | No (current action only) |
| Declared target | Yes | No (current action only) |
| Void level | Yes | No (current snapshot) |
| Active clocks | Yes | Partially (tick counts reflect prior actions) |
| Bond matrix | Yes | Partially (bond status reflects prior actions) |
| Combatant list | Yes | No (current state snapshot) |
| Weapon context | Yes | No (static weapon stats) |
| **Prior action summaries** | **No** | -- |
| **Running soulcredit totals** | **No** | -- |
| **Round-by-round narrative** | **No** | -- |
| **Prior soulcredit awards** | **No** | -- |

### Soulcredit Rules in Prompts

**File:** `prompts/claude/en/dm/dm_structured_output_base.yaml:23-26`

The soulcredit guidance is rule-based and context-free:

```
+1: Non-lethal takedown, helping civilians, restraint, healing allies
-1: Excessive force, harming non-combatants, authority abuse
-2: Fighting own faction/allies (betrayal), killing prisoners
 0: Justified combat against hostiles, standard actions
```

These rules assume the DM can evaluate "own faction," "ally," "prisoner," and
"justified" in context. Without session history, the DM falls back to faction
labels (from the combatant list) and scenario description (static text), which
are insufficient for nuanced moral reasoning.

### Where Soulcredit Is Generated

**File:** `schemas/action_resolution.py`

Soulcredit is a field on `ActionResolution`, generated simultaneously with
narration and damage effects in a single structured output call:

```python
class ActionResolution(BaseModel):
    narration: str = Field(...)
    damage_effects: List[DamageEffect] = Field(default_factory=list)
    soulcredit_changes: List[SoulcreditChange] = Field(default_factory=list)
    # ... other fields
```

The DM cannot "wait and see" what the narration says before scoring soulcredit.
It produces all fields at once. If the narration describes restraint but the
soulcredit field says -1 (because of faction label matching), the contradiction
is baked into the output.

---

## Design Decisions

1. **Context injection into user prompt, not conversation history.** Using
   multi-turn conversation history would require maintaining DM state across
   all action resolutions in a session (50+ turns), dramatically increasing
   token cost and latency. Instead, inject a condensed **action digest** into
   the existing user prompt. The DM remains stateless at the LLM level, but
   receives enough context to reason about patterns.

2. **Bounded context window.** The action digest must be size-bounded to prevent
   prompt bloat in long sessions. A rolling window of the last N actions (or
   last N rounds) keeps prompt size predictable. Older context drops off.

3. **Soulcredit ledger is mandatory; narrative recap is optional.** The running
   soulcredit total per character is cheap (one line per character) and directly
   addresses the scoring inconsistency bug. Narrative summaries are more
   expensive but provide richer context for nuanced moral reasoning. Implement
   the ledger first (Phase 1), narrative recap second (Phase 2).

4. **This-round context must include other actions already resolved.** Within
   a single round, the DM resolves 3-5 actions sequentially. Action 3 should
   see the outcomes of Actions 1-2, because in-round events build on each
   other (e.g., "Sera healed Kael" in Action 1 should inform whether Kael's
   aggressive response in Action 3 is "justified" or "ungrateful").

5. **Structured context, not freeform.** The injected context should use a
   structured, parseable format (not freeform narration summaries). This
   prevents the DM from hallucinating context and keeps the signal clear.

---

## Proposed Solution

### Phase 1: Soulcredit Ledger + In-Round Action Recap

**Goal:** Give the DM visibility into (a) running soulcredit totals and (b)
what has already happened this round, at minimal prompt cost.

**New section injected into user prompt (after combatant list, before weapon
context):**

```
== SESSION CONTEXT ==

SOULCREDIT LEDGER (cumulative this session):
  Vessel Sera Karsel: +3 (R1: +1 healed ally, R2: +1 non-lethal takedown, R3: +1 restraint)
  Enforcer Kael Dren: -1 (R2: -1 excessive force, R4: +0 justified combat)
  Drifter Sable: +1 (R1: +1 helped civilian)

THIS ROUND (actions already resolved):
  1. Vessel Sera Karsel: INVESTIGATE (success, margin +6) → discovered hidden passage,
     soulcredit +0
  2. Enforcer Kael Dren: COMBAT vs [tgt_zzzz] Pantheon Patrol Alpha (success, margin +4)
     → engaged hostile patrol that attacked first in R2, soulcredit +0 (justified)

PRIOR ROUND SUMMARY (R4):
  - Pantheon Patrol Alpha attacked party unprovoked (established hostile)
  - Drifter Sable attempted negotiation (failed, margin -3)
  - Enforcer Kael Dren defended Sera from patrol attack (+1 soulcredit for protection)
```

**Fields in the context block:**

| Field | Source | Cost (tokens) |
|-------|--------|---------------|
| Soulcredit ledger | `mechanics.py` soulcredit accumulator (already tracked) | ~10-20 per character |
| This-round actions | Accumulated during round processing in `session.py` | ~30-50 per action |
| Prior round summary | Generated at end of each round (new) | ~50-100 per round |

**Estimated total prompt overhead:** 200-400 tokens per action resolution
(acceptable; current prompts are 3000-6000 tokens).

**Files to modify:**

| File | Change |
|------|--------|
| `dm.py:6728-6869` (`_build_dm_narration_prompt`) | Inject SESSION CONTEXT block |
| `dm.py` or `session.py` | Accumulate this-round action outcomes during sequential resolution |
| `mechanics.py` | Expose `get_soulcredit_ledger()` method (may already be tracked internally) |
| `session.py` | Generate prior-round summary after each round completes |

**Implementation detail -- in-round accumulation:**

```python
# session.py (during sequential action resolution)
round_context = []

for action in declared_actions:
    # Build context including prior actions THIS round
    resolution = dm.resolve_action(action, round_context=round_context)

    # Accumulate for next action's context
    round_context.append({
        "character": action.character_name,
        "action_type": action.action_type,
        "target": action.target,
        "success": resolution.roll.success,
        "margin": resolution.roll.margin,
        "soulcredit": resolution.soulcredit_changes,
        "narration_summary": resolution.narration[:120]  # Truncated
    })
```

### Phase 2: Rolling Narrative Digest

**Goal:** Give the DM a condensed narrative history of the session so far,
enabling it to reason about arcs, patterns, and relationship trajectories.

**New section appended to SESSION CONTEXT:**

```
SESSION NARRATIVE DIGEST (condensed):
  R1: Party arrived at Nexus Junction. Sera and Sable cooperated to calm
      panicked civilians. Kael secured the perimeter. No combat.
  R2: Pantheon Patrol Alpha ambushed the party. Kael returned fire (lethal).
      Sera stabilized a wounded bystander. Sable attempted parley (failed).
  R3: Combat continued. Kael used excessive force on retreating patrol member
      (-1 SC). Sera provided covering fire (non-lethal, +1 SC). Patrol Beta
      arrived as reinforcements.
  R4: Kael defended Sera from Patrol Beta flanking attack (+1 SC, protection).
      Sable discovered the patrols were acting on false intel from a rogue
      Pantheon officer. Sera attempted to contact Pantheon command.
```

**Generation strategy:** At end of each round, the session engine generates a
1-2 sentence summary per round using either:

1. **Extractive:** Pull from RoundSynthesis narration (already generated, free)
2. **LLM-generated:** Separate cheap LLM call to summarize the round (more
   coherent but adds latency and cost)

**Recommendation:** Start with extractive (RoundSynthesis.narration truncated
to 150 chars per round). This is free and provides baseline context. Evaluate
whether LLM-generated summaries improve soulcredit coherence enough to justify
the cost.

**Rolling window:** Keep last 5 rounds of narrative digest. Older rounds
condense further (R1-R3 merge into a single line). This caps the narrative
digest at ~500 tokens regardless of session length.

### Phase 3: Faction Relationship Context

**Goal:** Replace static faction labels with dynamic relationship state that
reflects in-session events.

**New section in SESSION CONTEXT:**

```
FACTION RELATIONSHIPS (dynamic, based on session events):
  Pantheon Security ↔ Party: HOSTILE (Patrol Alpha attacked unprovoked in R2)
  Drifter Sable ↔ Enforcer Kael: ALLIED (cooperated R1-R4, Kael defended Sable in R3)
  Pantheon Patrol Alpha ↔ Pantheon Security: ROGUE (acting on false intel, R4 discovery)
```

This directly addresses the same-faction betrayal false positive. Instead of
the DM inferring relationships from faction labels ("Kael is Pantheon, Patrol
is Pantheon, therefore allies"), it receives an explicit dynamic relationship
state that reflects what actually happened.

**Files to modify:**

| File | Change |
|------|--------|
| `session.py` or new `relationship_tracker.py` | Track faction relationships based on combat events and narration |
| `dm.py` | Inject FACTION RELATIONSHIPS block into user prompt |

**Scope note:** This phase is the most complex and may benefit from IFF/ROE work
in Spec 06. If 06_IFF_ROE is implemented first, relationship tracking can build
on its faction discovery infrastructure.

---

## Test Plan

### Phase 1: Soulcredit Ledger + In-Round Recap

```python
# tests/unit/test_adjudication_context.py

def test_soulcredit_ledger_injected_in_prompt():
    """DM prompt should contain soulcredit ledger when characters have SC history."""
    dm = create_test_dm()
    # Simulate prior soulcredit changes
    dm.shared_state.apply_soulcredit_change("Sera", +1, "healed ally")
    dm.shared_state.apply_soulcredit_change("Kael", -1, "excessive force")

    prompt = dm._build_dm_narration_prompt(action, context)
    assert "SOULCREDIT LEDGER" in prompt
    assert "Sera" in prompt and "+1" in prompt
    assert "Kael" in prompt and "-1" in prompt

def test_soulcredit_ledger_empty_when_no_history():
    """DM prompt should omit ledger section when no SC changes have occurred."""
    dm = create_test_dm()
    prompt = dm._build_dm_narration_prompt(action, context)
    # Either omit entirely or show all zeros -- design decision
    assert "SOULCREDIT LEDGER" not in prompt or "+0" in prompt

def test_in_round_context_shows_prior_actions():
    """DM prompt should include actions already resolved this round."""
    round_context = [
        {"character": "Sera", "action_type": "investigate", "success": True,
         "margin": 6, "soulcredit": [], "narration_summary": "found passage"},
        {"character": "Kael", "action_type": "combat", "success": True,
         "margin": 4, "soulcredit": [], "narration_summary": "engaged patrol"},
    ]
    prompt = dm._build_dm_narration_prompt(action, context, round_context=round_context)
    assert "THIS ROUND" in prompt
    assert "Sera" in prompt and "investigate" in prompt.lower()
    assert "Kael" in prompt and "combat" in prompt.lower()

def test_in_round_context_empty_for_first_action():
    """First action of a round should have empty in-round context."""
    prompt = dm._build_dm_narration_prompt(action, context, round_context=[])
    # Should either omit section or show "No actions resolved yet"
    assert "THIS ROUND" not in prompt or "No actions" in prompt

def test_round_context_passed_through_resolve_action():
    """session.py should pass round_context to DM resolution for each action."""
    session = create_test_session()
    # Mock 3 declared actions
    actions = [mock_action("Sera"), mock_action("Kael"), mock_action("Sable")]

    # After resolving action 0, action 1 should receive context about action 0
    with patch.object(session.dm, '_build_dm_narration_prompt') as mock_build:
        session._resolve_round_actions(actions)

        calls = mock_build.call_args_list
        # First call: empty round_context
        assert calls[0].kwargs.get('round_context', []) == []
        # Second call: contains first action's outcome
        assert len(calls[1].kwargs.get('round_context', [])) == 1
        # Third call: contains first two actions' outcomes
        assert len(calls[2].kwargs.get('round_context', [])) == 2
```

### Phase 2: Narrative Digest

```python
def test_prior_round_summary_generated():
    """End-of-round processing should generate a narrative summary."""
    session = create_test_session()
    session._complete_round(round_num=3, synthesis=mock_synthesis)
    assert session._round_summaries[3] is not None
    assert len(session._round_summaries[3]) <= 200  # Bounded length

def test_narrative_digest_rolling_window():
    """Narrative digest should keep only last 5 rounds."""
    session = create_test_session()
    for r in range(10):
        session._round_summaries[r] = f"Round {r} summary"

    digest = session._build_narrative_digest(current_round=10)
    # Should contain R5-R9 (last 5), not R0-R4
    assert "Round 5" in digest
    assert "Round 9" in digest
    assert "Round 0" not in digest

def test_narrative_digest_injected_in_prompt():
    """DM prompt should contain prior round summary when available."""
    dm = create_test_dm()
    dm._round_summaries = {1: "Party arrived", 2: "Combat started"}
    prompt = dm._build_dm_narration_prompt(action, context)
    assert "PRIOR ROUND SUMMARY" in prompt or "SESSION NARRATIVE" in prompt
```

### Soulcredit Coherence Tests (Integration)

```python
def test_same_faction_attack_with_context_no_false_penalty():
    """DM should not penalize attacking hostile same-faction entities when
    context establishes them as hostile."""
    # Setup: Pantheon patrol attacked party in R2 (established hostile)
    round_context_r2 = [
        {"character": "Pantheon Patrol", "action_type": "combat",
         "target": "Sera", "success": True, "narration_summary": "patrol opened fire"}
    ]
    round_summary_r2 = "Pantheon Patrol Alpha attacked party unprovoked."

    # R3: Kael (Pantheon) attacks Patrol (Pantheon) -- should be +0, not -2
    dm = create_test_dm()
    dm._round_summaries = {2: round_summary_r2}
    dm.shared_state.apply_soulcredit_change("Kael", 0, "justified combat R2")

    prompt = dm._build_dm_narration_prompt(
        action=kael_attacks_patrol,
        context=combat_context,
        round_context=[]
    )

    # Verify the prompt contains enough context for the DM to reason correctly
    assert "attacked" in prompt.lower() or "hostile" in prompt.lower()
    assert "Patrol" in prompt
```

---

## Dependencies

### Hard Dependencies
None. This spec modifies the adjudication prompt pipeline, which is independent
of all other specs.

### Soft Dependencies
- **06_IFF_ROE:** Phase 3 (faction relationships) would benefit from IFF's
  faction discovery infrastructure, but can be implemented independently with
  a simpler relationship tracker.
- **14_CONDITIONS:** If conditions are properly tracked (Spec 14), the in-round
  context can report condition state changes ("Patrol Alpha was Stunned by Sera
  in Action 1"), giving the DM better context for subsequent resolutions.

### Downstream Consumers
- **08_SUPPRESSION:** Soulcredit rewards for restraint (suppressive fire = +1 SC)
  are more meaningful when the DM can see the character's prior behavior. A
  character who has been lethal all session switching to suppression should get
  a larger positive signal than one who has always been restrained.
- **03_TARGET_VALIDATION:** When the DM can see prior round context showing
  "this NPC was converted from an enemy in R3," it is less likely to resolve
  a free-target ID to that NPC for a combat action.

---

## Open Questions

### Q1: Should the narrative digest be extractive or LLM-generated?

**Current recommendation:** Start extractive (truncated RoundSynthesis.narration).
This is free, deterministic, and immediately available. If soulcredit coherence
tests show insufficient improvement, add an LLM-generated summary step.

**Cost concern:** An additional LLM call per round (for summary generation) adds
~0.5s latency and ~500 tokens per round. For a 10-round session, that is 5s and
5000 tokens -- marginal for live play, negligible for batch generation.

### Q2: How many prior rounds of context to include?

**Current recommendation:** 1 prior round summary + full in-round context. This
balances prompt size against context richness. The soulcredit ledger provides
cumulative session-wide context without per-round detail.

**Alternative:** 3 prior rounds. More context but ~300 additional tokens per
action resolution. May be justified if 1-round lookback proves insufficient.

### Q3: Should the soulcredit ledger show reasons or just totals?

**Current recommendation:** Show reasons (compact format). "Sera: +3 (R1: +1
healed ally, R3: +1 restraint, R4: +1 non-lethal)" gives the DM enough to
reason about patterns without reading full narration.

**Alternative:** Totals only ("Sera: +3"). Cheaper (~5 tokens per character)
but loses the reasoning context that makes the ledger valuable.

### Q4: Should in-round context include narration or just mechanics?

**Current recommendation:** Mechanics + truncated narration (120 chars). The DM
needs to know "Sera healed Kael" (narration) as well as "success, margin +8"
(mechanics) to reason about in-round dynamics. Full narration is too expensive;
a 120-char summary captures the key event.

### Q5: How does this interact with the structured output generation?

The DM generates `ActionResolution` (which includes soulcredit_changes) in one
shot. The context injection occurs in the **user prompt** (before generation),
not in a feedback loop (after generation). This means:

- The DM sees context → generates narration + soulcredit together
- Context guides the DM's judgment but does not mechanically constrain it
- The DM can still produce inconsistent soulcredit if it ignores the context

This is consistent with the DM-authoritative design philosophy. The context
provides information; the DM decides how to use it. Post-hoc validation (e.g.,
"DM gave -2 for same-faction attack but context shows the target was
established hostile") could be added as a separate warning system.

---

## Migration Notes

### Prompt Changes
Additive. The SESSION CONTEXT block is a new section in the user prompt. Existing
prompt structure is unchanged. Sessions without context (e.g., round 1, action 1)
simply omit the block.

### JSONL Logging Impact
No new event types required. The context injected into prompts is already derived
from existing logged events (soulcredit_changes, action_resolutions,
round_synthesis). The LLM call log will show the expanded prompt (larger `messages`
field) but no schema changes are needed.

### Backward Compatibility
Full. The context block is injected only when data exists. Round 1, Action 1 of
any session has no prior context and produces the same prompt as the current
implementation. Session configs need no changes. Existing fixtures replay
identically (the replay system caches LLM responses, so the expanded prompt
is irrelevant during cached replay).

### Performance Impact
- **Phase 1:** +200-400 tokens per action resolution (ledger + in-round recap)
- **Phase 2:** +300-500 tokens per action resolution (narrative digest)
- **Phase 3:** +100-200 tokens per action resolution (faction relationships)
- **Total (all phases):** +600-1100 tokens per action (~15-25% increase on
  typical 4000-token prompts)

For batch generation (200 sessions, ~50 actions each): +6M-11M additional input
tokens. At $3/M input tokens (GPT-5-mini), that is $18-33 additional cost per
batch run. Acceptable.
