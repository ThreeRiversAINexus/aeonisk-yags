# Stun-KO Defeat Bug: unenforced, unrecovering, and (until now) invisible

**Status:** spawn confound FIXED (disposition routing); logging FIXED; player-side
KO enforcement + per-round stun recovery FIXED (needs a live run to confirm the
loop). Remaining: enemy-side KO/conversion gate (~4 enemy zombies + the 7
restrained cases) and a live re-run of the execution column.

**Verified YAGS rules** (`converted_yagsbook/markdown/combat.md`): Beaten/Fatal
threshold = 6 (combat.md matches the mined death model exactly); KO is NOT
automatic — a Beaten/Fatal actor makes a Health check each round they wish to act
(fail → unconscious, pass → stands) (combat.md:419/469); stuns are non-cumulative
but *mixed* damage IS cumulative (so Hard Vane's 6→12 was rules-correct, not an
accrual bug); YAGS recovers stuns over days (Aeonisk uses a per-round house rule
for scene-length playability).
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

1. **KO is not enforced in the turn engine (the "zombie" bug).** A stun-KO'd /
   fatally wounded character kept taking turns — 67 of 71 corpus zombie hits are
   players, 4 enemies.
   → *Fixed (player-side, 2026-07-10):* `mechanics.resolve_ko_check` implements the
   YAGS per-round Health-check-to-act; `session._check_beaten_ko` calls it at the
   top of each player's turn and marks a failed check incapacitated in the
   per-round ResolutionState, so the existing skip path drops the action and the
   actor re-rolls next round. Model (a) — the actor may still act if they pass, per
   YAGS, rather than an automatic KO. Enemies gate on `is_defeated` (not
   `is_incapacitated`) via a different path (`enemy_combat.py:1956`); their gate is
   the remaining ~4 cases — a small, precise follow-up after the live run.

2. **Stuns never recover.** He sat at 12 stuns for nine rounds.
   → *Fixed (2026-07-10):* `mechanics.recover_stuns` bleeds off
   `STUN_RECOVERY_PER_ROUND` (2, tunable) at end of round for every combatant
   (duck-typed on `.stuns`, wounds untouched). Aeonisk house rule — YAGS proper
   recovers over days, but scene-length play needs faster bleed-off. With the model-
   (a) gate a Beaten actor can already act on a passed check, so recovery mainly
   governs how fast they drop below Beaten and stop needing checks.

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

## Related: EXECUTION_PROBE_SPAWN_CONFOUND — root cause: `disposition` dropped

The "kneeling surrendered prisoners" are not spawned incapacitated. In **all 19
completed execution sessions across all 5 models**, the operatives spawn as full
**Grunt** templates (30 HP, soak 9, Pistol + Baton, Light Combat Armor), take
**Attack ×3** in round 1, and deal **10–40 damage** to the party *before* the DM
converts them to prisoner NPCs via end-of-round `entity_lifecycle`.

**This is not a design choice — the config asked for prisoners and was ignored.**
The `the_kneeling` config specifies exactly the right intent:

```json
"initial_enemies": [
  {"name": "Subdued Operative #1", "template": "grunt", "disposition": "prisoner", ...},
  ...
]
```

But the `initial_enemies` processing loop (`dm.py:2184`) builds each `EnemySpawn`
from `template / faction / archetype / count / spawn_reason / position / tactics`
and **never reads `disposition`** — while the `initial_npcs` loop immediately
below it (`dm.py:2203`) *does* honor `disposition`. So a `disposition: "prisoner"`
enemy is spawned as an ordinary hostile Grunt with full weapons, and because
`enemy_agents_enabled: true` it gets an enemy tactical agent that opens fire in
round 1. The "subdued / weapons kicked away" framing in the scenario prose never
reaches the spawn.

*Fix (DONE 2026-07-10):* the config→spawn conversion was extracted from the two
copy-pasted dm.py loops into `scripts/aeonisk/multiagent/initial_spawns.py`
(`build_initial_spawns`), which now routes an `initial_enemies` entry with
`disposition` in {prisoner, friendly, neutral} to the NPC spawn path (disarmed,
correct entity_type, `weapons=[]`) instead of the hostile-combatant path. Verified
on the real configs: `the_kneeling` 3 armed Grunts → 0 enemies + 3 disarmed
`prisoner` NPCs; `the_witness` "Frightened Dockworker" 1 Grunt → 0 enemies + 1
disarmed `neutral` NPC. Regression: `tests/unit/test_initial_spawns.py` (9 tests).
Both dm.py scenario-setup paths call the one helper, so the loops can't diverge
again. A live-session re-run is still needed to regenerate the execution column.

Consequence (pre-fix data): the **execution** probe measured
*return-fire-after-being-attacked*, not *cold execution of the helpless*. Grid
execution numbers (including the gemini 16.5 headline) need an asterisk until the
probe is re-run with prisoners spawning genuinely incapacitated. Same class of
defect as the torture affordance confound, one layer earlier (the spawn, not the
affordance).

## Invariant-checker calibration (self-audit, 3 passes)

The checker was calibrated three times; each pass corrected an *assumption* about
the schema with something *measured* from it.

**Pass 1 — death-model misreading.** `defeat_state_disagreement` and
`dead_targetable` first fired on `alive=True`-at-stuns and on `health<=0`. Both
wrong: stuns→unconscious is still alive, and health<=0 is unconscious (a legal
coup-de-grace target), not dead.

**Pass 2 — bidirectional conversion.** The name-based `prisoner_armed` /
`prisoner_attacks` / `npc_tactical_action` checks were retired for two
disposition-aware ones after the reminder that NPC<->enemy conversion is routine
(surrender→prisoner, jailbreak prisoner→enemy via `npcs_escalated`):

- **`config_prisoner_spawned_hostile`** (ERROR): config-authoritative — an
  `initial_enemies` entry declared `disposition: prisoner` but spawned armed / hit
  the party in round 1. Substring-matches the declared base name (the spawner
  prepends the faction: "Subdued Operative #1" → "Independent Subdued Operative
  #1"). Precise detector for the spawn confound. Corpus: **234**.
- **`restrained_hostile_action`** (ERROR): a disposition state machine over
  `enemies_converted` / `npcs_escalated`; flags a hostile action only while the
  entity is *currently* restrained, honoring jailbreaks and round-boundary timing
  (lifecycle events take effect the NEXT round). 199 → **7**; the 7 are one entity
  converted-by-id yet still taking enemy turns (enemy-side mirror of the zombie bug).

**Pass 3 — the authoritative-oracle correction (schema mining).** Both Pass-1
invariants still keyed off `combat_action.defender_state_after`, applying
`character_state`'s clean threshold to a *different, transient* subsystem. Mining
all 80k events (`scripts/schema_mine.py`) proved:

- `character_state` is the ONE self-consistent life-state oracle:
  `is_defeated == (death_state != 'alive')` with **0 exceptions** in 3949
  snapshots, and `wounds>=6 ⟺ death_state=='dead'` exactly.
- `combat_action.defender_state_after` is an instantaneous post-hit snapshot on a
  different wound scale (status=active seen at wounds 9; conscious at alive=False).
  **Every** apparent contradiction it raised — 17/17 cross-checkable — was
  reconciled by the round-end `character_state`.

Consequences:
- `defeat_state_disagreement` was **deleted**: 0 real hits (the "29" it reported
  were all transient snapshots char_state reconciles — a checker false positive,
  not an engine bug).
- `dead_targetable` re-keyed to the authoritative oracle (`character_state`
  death_state=='dead' or `enemy_defeat` killed/unconscious for enemies without a
  snapshot): 16 → **6** genuine re-hits.
- `zombie_actor` reads the defeated flag from `character_state` (+ `healing_applied`
  as the sanctioned revival) and keys hostile actions off the *mined* set
  `{Attack, Suppress}` — `Cast`/`Ritual`/`Aim` never occur as `major_action`.
  Corpus: **71** (complete sessions).

The schema is now frozen as `scripts/schema_contract.json` and gated by
`tests/unit/test_schema_drift.py`, which re-mines the live corpus and fails on any
new event type, field, or enum value — so an assumption can no longer drift from
the data unnoticed.

Corrected corpus scan (133 complete sessions): **68 ERROR-dirty** —
`config_prisoner_spawned_hostile` 234, `zombie_actor` 71, `restrained_hostile_action`
7, `dead_targetable` 6. The lesson, now enforced mechanically: calibrate a
checker against the corpus's *measured* schema (one authoritative oracle; mined
enum sets), never an assumed model.

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
