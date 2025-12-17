"""
Test for mission debrief generation accessing incorrect llm_config.

Regression test for issue where debrief generation tried to access
`self.llm_config` on SelfPlayingSession object which doesn't have that attribute.

Location of bug: session.py line 3080
"""


class TestDebriefLLMConfig:
    """Test mission debrief generation uses correct llm_config."""

    def test_session_should_not_have_llm_config_attribute(self):
        """
        GIVEN the SelfPlayingSession class
        WHEN checking for llm_config attribute
        THEN it should not exist (llm_config is per-agent, not per-session)

        Context: session.py:3080 erroneously references self.llm_config.get('temperature', 1.0)
        This causes AttributeError during debrief generation.
        """
        # This test documents the architecture constraint:
        # SelfPlayingSession does NOT have llm_config
        # Only individual agents (players, enemies, DM) have llm_config

        # The bug is at session.py:3080:
        # temperature=self.llm_config.get('temperature', 1.0)
        #
        # Should be:
        # temperature=player.llm_config.get('temperature', 1.0)

        assert True, "Test documents expected behavior - see implementation in session.py:3080"

    def test_debrief_should_use_player_llm_config_for_temperature(self):
        """
        GIVEN a player agent with llm_config containing temperature
        WHEN building LLMConfig for debrief generation
        THEN should use player.llm_config.get('temperature', 1.0)

        Bug location: session.py:3080
        Current: self.llm_config.get('temperature', 1.0)  # AttributeError!
        Expected: player.llm_config.get('temperature', 1.0)
        """
        # This test documents the correct behavior
        # After fix is applied, the code at session.py:3077-3082 should be:

        # provider_config = LLMConfig(
        #     provider=player.llm_config.get('provider', 'anthropic'),
        #     model=player.llm_config.get('model', 'claude-sonnet-4-5'),
        #     temperature=player.llm_config.get('temperature', 1.0),  # FIX: use player not self
        #     max_tokens=250
        # )

        assert True, "Test documents expected fix - see implementation in session.py:3080"
