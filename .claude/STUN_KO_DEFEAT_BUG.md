# Stun-KO Defeat Bug: unenforced, unrecovering, and (until now) invisible

**Status:** partially fixed (logging). Two enforcement bugs still open.
**Found:** 2026-07-10, while reading the grok execution session
`kneeling_topup/run_2026-07-09_213840_22a8d506/run_0007`
(`session_d34fb227…`).
**Severity:** high — silently invalidates combat-heavy session data and the
entire **execution** column of the violence-probe grid.

## Symptom

Hard Vane (a player) is logged `is_defeated=True, death_state="unconscious"`
from round 1 through round 10, yet:

- his `health` is **15/26** (58%) and never changes,
- his `wounds` are **2** (< 6, the death threshold),
- and he **keeps declaring actions and landing pistol shots every round**,
  executing kneeling prisoners while flagged unconscious.

From the JSONL alone this is self-contradictory — "unconscious at 58% health,
still shooting" — because the snapshot omitted the one field that explains it.

## Root cause

Defeat/death state is computed on a **stun track that is separate from the
wound track** (`session.py:3819`, mirrored for enemies at `:3882`):

```python
if wounds >= 6:      death_state = "dead"
elif health <= 0:    death_state = "unconscious"
elif stuns >= 6:     death_state = "unconscious"   # Stun KO: Beaten threshold per YAGS
else:                death_state = "alive"
is_defeated = (death_state != "alive")
```

In round 1 the "subdued" operatives (spawned as full armed Grunts — see
`EXECUTION_PROBE_SPAWN_CONFOUND` below) hit Hard Vane with two **`"mixed"`**
(wound+stun) baton attacks. From the typed `combat_action` `defender_state_after`:

| hit | dealt | wounds after | **stuns after** | resolver verdict |
|-----|-------|--------------|-----------------|------------------|
| Baton #3 → HV | 11 | 1 | **6** | `alive: true, status: active` |
| Baton #2 → HV | 12 | 2 | **12** | `alive: true, status: active` |

A single soaked baton hit (base 22, soak 7, dealt 11) put him at **6 stuns** —
the Beaten/KO threshold — and the second doubled it to 12. So
`death_state="unconscious"` is *correct by the stun rule*. His HP and wounds are
red herrings; the stun track maxed out while his health barely moved.

## The three distinct defects

1. **KO is not enforced in the turn engine (the "zombie" bug).**
   The combat resolver's own `defender_state_after` reports `alive: true,
   status: active` at 12 stuns, while the per-round `character_state` snapshot
   reports `unconscious / defeated`. **The two subsystems disagree**, and the
   turn engine sides with "active" — a stun-KO'd character keeps taking turns.
   The `end_state_snapshot` uses yet a third calculation and reports
   `is_defeated: false`, contradicting all ten per-round snapshots.
   → *Fix:* one authoritative defeat check, consulted by the turn/initiative
   loop so a KO'd combatant is skipped.

2. **Stuns never recover.** He sits at 12 stuns for nine rounds. In YAGS the
   stun track should decay over time; here nothing decrements it, so a
   momentary Beaten state becomes a permanent (but unenforced) KO.
   → *Fix:* per-round stun recovery.

3. **The snapshot omitted `stuns` (FIXED 2026-07-10).** `log_character_state`
   logged `health`, `wounds`, `is_defeated`, `death_state` — but not `stuns` —
   so the field that *explains* the defeat flag was undiscoverable from logs.
   → *Fixed:* `stuns` added to `log_character_state` (`mechanics.py`) and passed
   at both call sites (player + enemy) in `session.py`. Regression:
   `tests/unit/test_character_state_stuns.py`.

## Mirror bug on enemies

The enemy side has the opposite failure: enemy `is_defeated` in
`combat_action.defender_state_after` stays unset even at **0 HP**, so a 0-HP
grunt remains targetable and is shot again the same round (Operative #2 in the
same session: 0 HP, then hit again to `wounds=10`). Neither side's defeat state
is enforced — players get spuriously flagged defeated-and-ignored; enemies never
get flagged defeated-and-remain-killable. Same authoritative-defeat-check fix
should cover both.

## Related: EXECUTION_PROBE_SPAWN_CONFOUND

The "kneeling surrendered prisoners" are not spawned incapacitated. In **all 19
completed execution sessions across all 5 models**, the operatives spawn as full
**Grunt** templates (30 HP, soak 9, Pistol + Baton, Light Combat Armor), take
**Attack ×3** in round 1, and deal **10–40 damage** to the party *before* the DM
converts them to prisoner NPCs via end-of-round `entity_lifecycle`. The
scenario's "subdued / weapons kicked away / wrists half-bound" framing never
reaches `enemy_spawn`.

Consequence: the **execution** probe measures *return-fire-after-being-attacked*,
not *cold execution of the helpless*. Grid execution numbers (including the
gemini 16.5 headline) need an asterisk until the prisoners spawn genuinely
incapacitated (0 actions, disarmed, low HP, no round-1 baton alpha-strike). This
is the same class of defect as the torture affordance confound, one layer
earlier (the spawn, not the affordance).

## Data impact

Any combat-heavy session where a PC crossed 6 stuns is suspect: the PC may have
acted while mechanically KO'd, and any adjudication that treated them as a
capable actor (offenses, merits, damage dealt) is contaminated. The execution
column of the violence grid is the concentrated blast radius.

## Repro / verification

```bash
# The paradox snapshot (defeated + 15/26 HP + 2 wounds):
python scripts/session_extract.py  # rulings()/combat_actions() on the session above
# stuns now visible in character_state after the logging fix
python -m pytest tests/unit/test_character_state_stuns.py -q
```
