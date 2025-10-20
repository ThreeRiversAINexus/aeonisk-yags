"""Tests for multi-agent voice diversification utilities."""

from aeonisk.multiagent.voice_profiles import VoiceLibrary


def test_voice_library_returns_distinct_profiles():
    """Voice profiles should have unique lexicons and agendas."""
    library = VoiceLibrary()

    profiles = library.all_profiles()
    assert len(profiles) >= 3

    lexicons = {profile.lexicon_signature for profile in profiles}
    assert len(lexicons) == len(profiles)

    # Each profile should embed faction or philosophy markers to avoid clones
    assert all(profile.faction_anchor for profile in profiles)


def test_voice_prompt_enrichment():
    """Voice library should annotate prompts with persona directives."""
    library = VoiceLibrary()
    scholar = library.get_profile("ritual_scholar")

    prompt = library.enrich_prompt("Discuss the ritual", scholar, previous_turns=["Void surges threaten"], shared_state={"void_spikes": 2})

    assert "Void surges threaten" in prompt
    assert "ritual_scholar" in prompt
    assert "void_spikes" in prompt
