# 5. Mechanics, State, and JSONL

## 5.1 The YAGS check

The central check is an attribute × skill value plus a d20 against a difficulty:

```text
total  = attribute_value × skill_value + d20
margin = total - difficulty
success when total ≥ difficulty
```

For example, attribute 4, skill 4, and a roll of 14 produce 30. Against difficulty 25, the margin is +5. The exact outcome tier and narrative consequence are determined by the active mechanics/adjudication path; do not infer them solely from a README table if the code or schema has changed.

The mechanics layer records enough inputs to reproduce a check: actor, attribute, skill, values, difficulty, roll, total, margin, success, and downstream effects. Preserve that provenance when adding mechanics.

## 5.2 Outcome tiers and narrative degree

Aeonisk uses graduated outcomes rather than a binary result. A resolution can be a catastrophic failure, ordinary failure, marginal success, moderate success, good success, or exceptional success depending on the active contract. The important design principle is that margin controls consequence degree. A model should not narrate an exceptional breakthrough from a barely successful check unless the rules explicitly allow it.

The outcome pipeline (`outcome_pipeline.py`, `outcome_parser.py`, and the related schemas) exists to keep action resolution, effects, and narrative aligned. If a new effect is added, update the structured effect schema and the pipeline tests rather than relying on a prose convention.

## 5.3 Combat model

Combat uses tactical range rings rather than a full grid. Common positions include `Engaged`, `Near`, `Far`, and `Extreme`, with PC/Enemy sides represented in serialized positions such as `Near-PC` and `Far-Enemy`. Tactical positions are runtime objects; schema position enums are not interchangeable with them.

The combat path includes:

- attacks and defenses;
- movement and intra-round position updates;
- weapons and damage breakdowns;
- wounds and stuns;
- conditions and penalties;
- cover/dodge bonuses;
- defeat and beaten/fatal consciousness checks;
- surrender, morale, retreat, and conversion;
- target invalidation after defeat or incapacitation.

A frequent bug shape is using the wrong position type. Resuming a recorded string must restore the tactical `enemy_agent.Position` object, not a plain string and not the schema `Position` enum.

## 5.4 Conditions and incapacitation

Conditions live in mechanics state and may affect rolls or action eligibility. A high enough penalty can incapacitate an actor for the round. Separately, enemies or players who are beaten/fatally wounded may receive a per-round consciousness check. The session’s `ResolutionState` tracks whether an actor is defeated, surrendered, incapacitated, or already checked so later declarations are invalidated consistently.

Death, defeat, and “cannot act this round” are different states. Preserve those distinctions in code and logs.

## 5.5 Scene clocks

Scene clocks represent progress or danger. A scenario can have multiple clocks—investigation progress, corruption spread, exposure, stability, countdowns, and so on. Clocks can advance or regress based on action outcomes and can trigger story advancement or terminal session outcomes.

Clock state is shared between DM context, mechanics, snapshots, and end-condition logic. If a clock changes but the DM is not told, the next round may make an incoherent decision. If the clock fills but the session-end checker does not see the terminal designation, the session can run past its intended conclusion.

## 5.6 Void, soulcredit, and the four-element economy

Aeonisk adds systems beyond the base YAGS check:

- **Void score/spikes:** tracks corruption and significant void events per character/session.
- **Soulcredit/faction consequences:** shared state records adjustments and reasons.
- **Energy economy:** elemental seeds/energy are used for ritual, attunement, purchases, and related effects.
- **Vendors and inventory:** transactions require validation and should be reflected in both entity state and events.
- **Rituals/altars:** setup and action resolution can advance ritual progress or apply bonuses/requirements.

The LLM may suggest a purchase, offering, ritual, or attunement, but the state-changing implementation must verify prerequisites and apply the effect exactly once.

## 5.7 JSONL is an event stream, not a transcript

The logger writes one JSON object per line. Events combine narrative and mechanics, but each event should answer a specific question: what happened, to whom, when, with which inputs, and what changed?

Typical event families include:

| Family | Why it matters |
|---|---|
| Session/scenario setup | Reconstruct the starting world and configuration. |
| Action declaration | Preserve the actor’s intent and selected mechanics before adjudication. |
| Action resolution | Preserve roll, difficulty, margin, tier, and effects. |
| Combat action/damage | Analyze weapon, target, damage, wounds, stuns, and position. |
| Character/entity update | Reconstruct state transitions. |
| Clock/void/economy events | Track domain-specific consequences. |
| Round synthesis | Pair mechanical results with DM narrative. |
| Round summary/session end | Explain progression and terminal status. |
| LLM call/agent logs | Audit prompt, provider, model, token/cost, and response behavior where enabled. |

The repository has evolved its event taxonomy. Use `JSONLLogger` in `mechanics.py`, current schema tests, and fixture logs as the final authority rather than copying an old “10 event types” or “19 event types” statement.

## 5.8 State ownership checklist

For any field, answer these questions:

1. Is it configuration, agent-local state, shared state, mechanics state, or derived display data?
2. Who is allowed to mutate it?
3. When is it serialized?
4. Can it be reconstructed from JSONL?
5. Does it affect prompt context?
6. What happens when the entity is defeated, converted, or resumed?

This checklist prevents the most common vibe-coded failure: a value is added in one object and then silently disappears at a boundary.
