"""Tests for shared state tooling used by the multi-agent orchestration."""

from aeonisk.multiagent.shared_state import SharedState


def test_shared_state_tracks_resources():
    """Shared state should record communal pools and ritual progress."""
    state = SharedState()

    state.adjust_soulcredit(3, reason="community tithe")
    state.record_void_spike("Glyph well ruptured")
    state.advance_ritual("Beacon Calibration", progress=2)

    snapshot = state.snapshot()

    assert snapshot["soulcredit_pool"] == 3
    assert snapshot["void_spikes"] == [
        {
            "reason": "Glyph well ruptured",
            "severity": 1,
        }
    ]
    assert snapshot["rituals"]["Beacon Calibration"] == 2


def test_shared_state_thresholds_trigger_guidance():
    """Crossing thresholds should surface GM cues for escalation."""
    state = SharedState(void_threshold=3)

    cues = []
    cues.append(state.adjust_soulcredit(-5, reason="Void bargain"))
    state.record_void_spike("Unauthorized pact", severity=2)
    cue = state.record_void_spike("Second rupture", severity=2)
    if cue:
        cues.append(cue)

    assert any(cue and "escalate" in cue.lower() for cue in cues if cue)
