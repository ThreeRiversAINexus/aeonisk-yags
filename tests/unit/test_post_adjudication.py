"""
Tests for the config-gated, observe-only post-resolution adjudication
experiment (in-session leniency: call-architecture vs role-deep).

Contract: default OFF (original behavior byte-identical); rulings are
logged, never applied to game state; module is removable cleanly.
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from aeonisk.multiagent.post_adjudication import (
    PostRuling,
    PostRulings,
    rulings_event_data,
)

PROMPT = (Path(__file__).parent.parent.parent /
          "scripts/aeonisk/multiagent/prompts/claude/en/dm/"
          "dm_post_adjudication.yaml")


class TestSchema:

    def test_ruling_bounds(self):
        with pytest.raises(Exception):
            PostRuling(character_name="X", action_summary="forged papers",
                       soulcredit_delta=-5, reason="way out of schema range")

    def test_event_data_is_observe_only(self):
        rulings = PostRulings(rulings=[PostRuling(
            character_name="Renna", action_summary="maintained the bluff",
            soulcredit_delta=-2, reason="deception of customs authority")])
        data = rulings_event_data(rulings)
        assert data["applied_to_state"] is False
        assert data["experiment"] == "post_resolution_adjudication"
        assert data["rulings"][0]["soulcredit_delta"] == -2


class TestPromptGuards:

    def test_prompt_loads(self):
        data = yaml.safe_load(PROMPT.read_text())
        assert "{resolution_summary}" in data["post_adjudication_prompt"]

    def test_rendered_rubric_covers_negative_and_zero_and_positive(self):
        from aeonisk.multiagent.nexus_law import OPERATIONAL_RUBRIC
        assert "-2" in OPERATIONAL_RUBRIC and "+1" in OPERATIONAL_RUBRIC

    def test_failed_deception_still_deception(self):
        """The moral-luck guard lives in the statute's rendered rubric."""
        from aeonisk.multiagent.nexus_law import OPERATIONAL_RUBRIC
        assert "failed deception is still\ndeception" in OPERATIONAL_RUBRIC \
            or "failed deception is still deception" in OPERATIONAL_RUBRIC


class TestConfigGate:

    def test_flag_defaults_off_in_session_source(self):
        """The experiment must be opt-in: the session hook reads the flag
        with a False default."""
        src = (Path(__file__).parent.parent.parent /
               "scripts/aeonisk/multiagent/session.py").read_text()
        assert "post_resolution_adjudication', False" in src


class TestFullContextMode:

    def test_prompt_has_scene_context_slot(self):
        data = yaml.safe_load(PROMPT.read_text())
        assert "{scene_context}" in data["post_adjudication_prompt"]

    def test_session_treats_full_context_as_mode(self):
        src = (Path(__file__).parent.parent.parent /
               "scripts/aeonisk/multiagent/session.py").read_text()
        assert "== 'full_context'" in src
