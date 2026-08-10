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
