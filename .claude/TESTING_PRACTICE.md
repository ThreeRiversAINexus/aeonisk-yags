# Testing practice

How this engine is actually tested, and why. Written after an audit in which
**nine engine defects were found while the suite was green at 4,317 tests** and
three of those tests were actively concealing bugs.

## The one rule

**A check that cannot fail is worse than no check**, because it comes with a
promise attached. Every test family here has been *shown* to fail — deliberately
break the thing it guards, watch it go red, put it back. If you cannot make a
test fail, you have not written a test.

Real examples of checks that could not fail:

| what it looked like | why it could never fail |
|---|---|
| `test_death_save.py` built a character with `Health` **and** `Endurance` | no session config produces that shape, so the bug it covered ran for eight months |
| `config.get(key, 3) == 3` | asserts the test's own default; passes against a deleted implementation |
| `session_invariants.py` printing `Scanned 0 complete sessions … 0 with ERROR` | skipped every session lacking `session_end`, and exited 0 |
| `spawn_from_structured` while `enabled=False` | silent no-op; the test compared two empty rosters |
| `MagicMock()` for an agent | `mock.health > 0` raises, `list(mock.npc_agents)` is empty, so "was every NPC processed?" sees zero and passes |

---

## The six modes

Pick by what you are trying to learn. Most surfaces want two or three of them.

### 1. Extract — real inputs from the corpus
Pull typed values out of recorded sessions and feed them to the real function.

Gives realism, and almost no coverage: 7,193 `character_state` rows collapse to
**134 distinct** `(health, wounds, stuns)` tuples, over half of them the same
starting state. Never sufficient alone.

`scripts/session_extract.py` → `scripts/domain_mine.py` → the committed snapshot
at `tests/fixtures/domains/domain_corpus.json`.

**Chain extract** is the same mode widened from a value to a causal sequence, and
it is the alternative to re-running a session to see whether a fix worked. Lift
the events that actually caused the bug — not the session, the chain — commit
them as a fixture, rebuild the scene *from those events*, drive it through the
real seams, and check the resulting stream with an invariant.

#150 is the worked example: ten events out of ~1,400 (round_start, one
combat_action, three npc_departures, entity_lifecycle, three character_state
rows) reproduce "an NPC shot for 19 wound damage has no `character_state` row"
exactly, in 1.1 seconds and for nothing. Then the same ten drive
`SharedState.remove_npc` and `npcs_to_snapshot` and the invariant goes quiet.

What makes it a test rather than a demo:

1. the fixture is verbatim recorded data, so the bug is a finding, not a
   construction — assert the raw chain still violates;
2. the reconstruction reads its numbers *out of the chain*
   (`defender_state_after`), so a changed fixture changes the scene and nothing
   is quietly hardcoded;
3. an invariant is the oracle, so no rules are restated;
4. rebuild the scene identically with the fix disabled and assert the violation
   returns — without that, any reconstruction that merely *mentions* the victim
   would pass.

Point 4 is the whole thing. It is mutation (mode 5) applied to the fix rather
than to the data.

Chains take modes 2 and 3 as readily as values do, and that is where the
coverage is:

* **recombine a chain** — drive a recorded sequence against a roster it never
  met. The #150 harm-and-depart chain against an escalating NPC that keeps its
  `agent_id` is how `duplicate_character_state` got written, and that pairing
  has never occurred in a real session.
* **extrapolate a chain** — reorder or extend past the observed envelope.
  Departure *before* damage rather than after; four captives instead of three;
  two removals of the same entity. All cheap, none ever recorded.

The corpus supplies the sequence; you supply the arrangement it never took.

### 2. Recombine — real values, unobserved combinations
Cross-product the observed vocabulary. The corpus tells you which *values* are
real; it rarely tells you which *combinations* are.

This is what caught `extract_faction` misparsing 34 of 176 faction × archetype
pairs.

### 3. Extrapolate — past the measured envelope
Deliberately outside what has ever occurred. The snapshot is what makes "we have
never seen this" a measured fact instead of an assumption.

This found the stun-cap clamp bug: `min(new, MAX_STUNS)` *healed* an entity
already above the cap.

### 4. Oracle rows — events that log inputs **and** outputs
The strongest tests in the repo. `ko_check` records `stuns, wounds, health_attr,
roll` **and** `dc, total, can_act, status`, including the injected roll — so the
expected value is the engine's own recorded answer and nothing is invented.

Eight rows, and worth more than the thousands that record one side only. **If
you are adding logging, log both sides.** It costs nothing and creates a test
oracle for free.

### 5. Mutation — perturb a known-good stream
Take a real session, change **one** field, assert the corresponding invariant
fires *and no other*. The mutation is the oracle, so no rules model is needed.

The "no other" half is the valuable half: it is the no-false-positives promise
the invariant module makes, and nothing was checking it.

Base fixture: `tests/fixtures/sessions/mutation_base_clean.jsonl` — complete,
current code, **zero** violations, so assertions are absolute rather than deltas
against legacy debt.

### 6. Property and stateful — `hypothesis`
For sequences, where correctness depends on ordering rather than a single call.
`RuleBasedStateMachine` over generated orderings of spawn/advance/apply/expire.

Use it when the state space is too large to enumerate honestly. Shrinking is the
reason: a failing 40-step sequence is unreadable without a minimal repro.

---

## Standing rules

**Corpus reads go through `session_extract`, never hand-rolled dict access.**
Events come in two shapes — some nested under `data`, older ones flat. An ad-hoc
`e["data"]["character_id"]` silently matches nothing and returns a confident
wrong answer. This produced a reported "22 of 22 entities vanish" where the true
number was 6. `_event_body` handles both.

**Tests read committed artefacts, never the corpus.** `multiagent_output/` and
`bulk_output/` are gitignored and get cleared. A test that breaks when someone
tidies up is not a test.

**Name the fixture; never take `glob(...)[0]`.** `test_balance_analyzers.py`
analysed "any fixture file", meaning whichever one the filesystem returned first.
Adding an unrelated fixture to the directory put a ten-event chain at the front,
and a CSV formatter test failed for reasons that had nothing to do with it. The
dependency was real and invisible: what the module tested changed whenever the
directory did.

**`golden` is a flag, not a filename prefix.** Four fixtures are named
`golden_*`; three of them fail the invariant checkers, one by twelve findings.
The gate is `golden: true` in `tests/fixtures/sessions/MANIFEST.json`, enforced
by `test_golden_fixtures_are_clean.py`: a complete session (`session_end`
present, so the terminal checkers can fire at all) with zero ERROR-severity
findings. Two of fifteen fixtures currently qualify. The gate keeps a
deliberately dirty fixture alongside and asserts it still fails, because a gate
that cannot say no is the "check that cannot fail" in another costume.

**Fixtures are recorded, never regenerated.** Replay was the intended way to
refresh a stale fixture — `ScriptedProvider` serves the recorded responses back,
so the same session runs against new code with no network and no spend. Both
golden fixtures carry complete caches (27 and 50 calls). It does not finish:
`replay_fixture.py --all-cached` on the 99-event fixture was killed at ten
minutes. Treat replay as unavailable for fixture work until that is fixed.

What is left is the split that should probably have been the plan anyway:

* **Debugging and regression** — chain extract, and its recombine/extrapolate
  variants. Free, targeted, seconds to run, and the only technique here that
  found anything. #150 and #153 were both diagnosed and fixed this way without
  a single session being run.
* **Complete-session reference fixtures** — harvested from research runs that
  were happening regardless, never manufactured. The gate decides; nobody pays
  extra.

The cost of this is that a fixture **cannot be repaired, only replaced**. A
recording is a fact about the code that produced it. When an engine fix lands
that changes what gets logged, every earlier fixture is stale by construction —
so record the engine commit, declare the staleness (`stale_findings` in the
MANIFEST), and let the gate retire the exemption when a newer recording arrives.
Do not edit a fixture to make a checker pass; that manufactures agreement.

**Zero findings must mean "nothing wrong", not "nothing visible".** Only 12 of
the 44 complete sessions in the corpus carry
`end_state_snapshot.soulcredit_states`; the other 32 pass `soulcredit_oracle_lag`
because it cannot read them. A fixture promoted on that silence certifies the
checker's blind spot as the standard. The golden gate asserts the checkers can
see the file before it credits them for staying quiet — the same defect as
eleven extracts sitting behind terminal checkers that could never fire on them.

**Harvest merges, never replaces.** `domain_mine.py` unions into the snapshot, so
clearing a corpus directory cannot destroy coverage only that batch had seen.
Counts derive from identified sets — incrementing made a re-harvest of the same
330 files report 660 sessions.

**Extract the seam rather than mocking around it.** Twelve defects were fixed
across #79–#99 and not one is verified by driving a session; each became testable
by extracting a module-level function first. A mock asserts what you *believe* a
collaborator does; an extracted function asserts what the code does. Use
`tests/factories.py`, not `MagicMock`.

**Inject randomness, never patch it.** `resolve_ko_check(..., roll=)` is the
pattern. Patching `random` asserts what you believe the module does; a parameter
asserts what the function does.

**Do not build a generator that reimplements the rules.** Generating synthetic
event streams was tried and rejected: the invariant checkers are consistency
rules *between* fields, so a generator that avoids firing them has to reimplement
them, and the test becomes two copies of one rule agreeing. Mutate real data
instead.

**Tests expose; issues capture; fixes land separately.** A test documents current
behaviour, an issue carries the evidence, the fix is its own reviewable change.
Keeps test PRs green and makes each behaviour change deliberate. Use
`xfail(strict=True)` for a known defect so it flips the moment it is fixed.

**Verify a prompt change with one call, not a session.** A session takes fifteen
minutes, costs real money, and changes a hundred variables at once — so it tells
you *a* narration, not whether your change caused it. Build the payload the
model would receive, make a single call, and diff the output.

#141 is the worked example. A Heavy Machine Gun was narrated as "a crackling
bolt of void energy". Rather than re-run the scenario, the recorded
`applied_outcome` was rebuilt with `weapon` populated and pushed through one
`generate_structured` call on the same model:

| `weapon` | narration |
|---|---|
| `null` | "she hurls a crackling bolt of void energy … the dark lightning streaks toward Corin" |
| `"Heavy Machine Gun"` | "her heavy machine gun roaring to life in a sustained, deafening burst … the rounds slam into Corin" |

One field, one call, a controlled result. The recipe:

1. pull the real event out of a session with `session_extract`, never by hand;
2. rebuild the model object from it (`AppliedOutcome(**body)`);
3. mutate the single field under test;
4. render exactly what the engine renders — for synthesis that is
   `prose_safe_outcome_payload`, not the raw object;
5. one `generate_structured` call, same model and system prompt as production.

Step 4 is the one that bites. **`prose_safe_outcome_payload` is a whitelist**:
a field on `AppliedOutcome` that is not listed there never reaches the narrator,
however faithfully it was populated. #141's fix was one whitelist entry away
from shipping as a no-op with passing tests. Had it been checked by running a
session instead, the prose would still have said "void energy" and the obvious
conclusion — that the fix did not work — would have pointed at the wrong layer
entirely.

Free half first: assert the field survives into the rendered payload as an
ordinary unit test. Only spend the call to see what the model does with it.

---

## Discovery vs verification

They are different jobs and need different tools.

**Verification** — the six modes above. They prove a fix works and stop it
regressing. They do not find anything new.

**Discovery** — reading real output. Every original finding in this audit came
from a live run read carefully, `session_invariants.py` pointed at real JSONL, or
a corpus survey. Reading `game.log` line by line yielded five findings no grep
surfaced.

Grep locates; it does not conclude. The silent bugs sit in ordinary status lines
— faction tables, HP rows, target lists — not in lines containing `ERROR`.

---

## Running it

```bash
source .venv/bin/activate
python -m pytest tests/unit/ -q                       # the suite
python scripts/session_invariants.py multiagent_output bulk_output --warn
python scripts/domain_mine.py --out tests/fixtures/domains/domain_corpus.json
python scripts/session_status.py <output_dir> --wait  # completion/stall, exit-coded
```

`--warn` matters: `clock_without_spawn` is WARN severity, and all 693 instances
were invisible in default runs until someone looked.

## Where things live

| file | role |
|---|---|
| `scripts/session_extract.py` | the only sanctioned way to get numbers out of a session |
| `scripts/domain_mine.py` | harvest the corpus into the committed snapshot |
| `scripts/session_invariants.py` | ~20 cross-event checkers, `check(events, cfg)` |
| `tests/factories.py` | realistic builders; use instead of Mock |
| `tests/unit/test_corpus_domains.py` | modes 1–4 |
| `tests/unit/test_invariant_mutations.py` | mode 5, plus checker fuzzing |
| `tests/unit/test_clock_properties.py` | mode 6 |
| `tests/unit/test_synthesis_validator_properties.py` | mode 6, validator inverse pair |
| `tests/unit/test_pure_function_domains.py` | hand-enumerated domains (guesses; see below) |

Note `test_pure_function_domains.py` uses hand-chosen ranges, and **two of four
were too narrow** — real health reaches 55 against a guess of 30, real stuns
reach 28 against a guess of 10. Prefer the mined domain where one exists.
