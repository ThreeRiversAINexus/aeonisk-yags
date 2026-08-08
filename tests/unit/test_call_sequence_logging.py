"""call_sequence must be unique and contiguous per agent — the replay-cache key.

Bug: the stamp and the increment were decoupled. Some paths did
`_log_llm_call(call_sequence=call_count)` then a *batched* `call_count += 2`
(the two-phase player declaration), so both calls read the same count and
collided (recorded 0,0,2,2,… — odd sequences never emitted). Since the replay
cache is keyed by (agent_id, call_sequence), colliding stamps overwrite one real
call and MockMessages (which walks 0,1,2,…) misses on the 2nd call → crash.

Fix: `_log_llm_call` is the single authority — it stamps the current count and
increments atomically, ignoring any externally-passed call_sequence.
"""
import types

from aeonisk.multiagent.llm_logger import LLMCallLogger


def _logger():
    captured = []
    jl = types.SimpleNamespace(write_event=lambda e: captured.append(e))
    lg = LLMCallLogger(agent_id="player_01", agent_type="player", jsonl_logger=jl, session_id="s")
    return lg, captured


def _log(lg, tag, seq_arg):
    lg._log_llm_call(messages=[{"role": "user", "content": tag}], response=tag,
                     model="m", temperature=0.7, tokens={}, current_round=1,
                     call_sequence=seq_arg)


def test_each_call_gets_unique_monotonic_sequence():
    lg, cap = _logger()
    for i in range(4):
        _log(lg, f"c{i}", seq_arg=999)  # a bogus passed value must be ignored
    assert [e["call_sequence"] for e in cap] == [0, 1, 2, 3]


def test_two_phase_pattern_does_not_collide():
    # the exact shape that produced 0,0: two logs, NO manual increment between them
    lg, cap = _logger()
    _log(lg, "phase1_short", seq_arg=lg.call_count)
    _log(lg, "phase2_long", seq_arg=lg.call_count)
    assert [e["call_sequence"] for e in cap] == [0, 1]  # was [0, 0]


def test_call_count_advances_exactly_once_per_log():
    lg, _ = _logger()
    assert lg.call_count == 0
    _log(lg, "a", seq_arg=0)
    assert lg.call_count == 1
    _log(lg, "b", seq_arg=0)
    assert lg.call_count == 2


def test_sequences_are_a_valid_cache_key_set():
    # the property replay needs: N calls -> exactly {0..N-1}, no dupes, no gaps
    lg, cap = _logger()
    for i in range(6):
        _log(lg, f"c{i}", seq_arg=i * 7)
    seqs = [e["call_sequence"] for e in cap]
    assert seqs == list(range(6))
    assert len(set(seqs)) == len(seqs)  # unique => no cache overwrite
