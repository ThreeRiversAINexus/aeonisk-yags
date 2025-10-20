"""Tests for guiding principle trigger guidance."""

from aeonisk.onboarding.guiding_principle import GuidingPrincipleCrisisLibrary


def test_guiding_principle_crises():
    """Library should surface multiple crisis prompts with cadence guidance."""
    library = GuidingPrincipleCrisisLibrary()

    cadence = library.recommended_cadence()
    assert cadence["check_every_sessions"] == 2
    assert cadence["void_threshold_trigger"] == 3

    crises = library.sample_crises()
    assert len(crises) >= 3
    assert all("trigger" in crisis and "fallout" in crisis for crisis in crises)

    # Ensure crises reference factional or bond tension for dramatic pacing
    assert any("faction" in crisis["trigger"].lower() for crisis in crises)
