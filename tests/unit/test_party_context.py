"""
Tests for party context: capability block + party-chatter salience.

Corpus v2 findings (2026-07-04): players see teammates' names and words
but zero capability data - task routing is informationally impossible
(330 futile unskilled rolls). Ambient speech reaches teammates (21% of
declarations carry it) but content is pure mood ("stay sharp") because
the prompt frames it as decorative and received lines drown in the
narration buffer.

Contract:
- _render_party_capabilities: teammates' top skills + best attribute,
  excludes self, PC-only, empty string for solo parties or flag off
- party chatter: party-directed ambient speech lands in a dedicated
  buffer, renders as its own block, rotates at round boundaries
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from aeonisk.multiagent.party_context import (
    render_party_capabilities,
    render_party_chatter,
    is_party_chatter,
)


def make_agent(name, faction="Freeborn", attributes=None, skills=None):
    return SimpleNamespace(
        agent_id=f"player_{name.split()[0].lower()}",
        character_state=SimpleNamespace(
            name=name,
            faction=faction,
            attributes=attributes or {"Empathy": 5, "Agility": 3},
            skills=skills or {"Charm": 6, "Counsel": 5, "Insight": 4,
                              "Investigation": 3, "Athletics": 2},
        ),
    )


class TestRenderPartyCapabilities:

    def test_renders_teammates_with_top_skills(self):
        me = make_agent("Renna Volt")
        ivo = make_agent("Ivo Lann", skills={"Systems": 6, "Investigation": 5,
                                             "Science": 4, "Guile": 2},
                         attributes={"Intelligence": 5, "Strength": 2})
        block = render_party_capabilities(me.agent_id, [me, ivo])

        assert "Ivo Lann" in block
        assert "Systems 6" in block
        assert "Intelligence 5" in block
        assert "Renna Volt" not in block  # never lists self

    def test_top_skills_ordered_and_capped(self):
        me = make_agent("Renna Volt")
        ivo = make_agent("Ivo Lann", skills={"Systems": 6, "Investigation": 5,
                                             "Science": 4, "Guile": 3,
                                             "Athletics": 2})
        block = render_party_capabilities(me.agent_id, [me, ivo])
        assert "Athletics" not in block  # 5th skill trimmed
        assert block.index("Systems") < block.index("Science")

    def test_solo_party_renders_empty(self):
        me = make_agent("Renna Volt")
        assert render_party_capabilities(me.agent_id, [me]) == ""

    def test_agents_without_character_state_skipped(self):
        me = make_agent("Renna Volt")
        broken = SimpleNamespace(agent_id="x")
        assert render_party_capabilities(me.agent_id, [me, broken]) == ""


class TestPartyChatter:

    def test_party_targeted_speech_is_chatter(self):
        assert is_party_chatter({"line": "Ivo, terminal is yours",
                                 "target_type": "party",
                                 "delivery": "spoken"})

    def test_comms_to_teammate_is_chatter(self):
        assert is_party_chatter({"line": "On my mark", "target_type": "npc",
                                 "delivery": "comms"})

    def test_spoken_to_enemy_is_not_chatter(self):
        assert not is_party_chatter({"line": "Drop it!",
                                     "target_type": "enemy",
                                     "delivery": "spoken"})

    def test_empty_line_is_not_chatter(self):
        assert not is_party_chatter({"line": "", "target_type": "party"})

    def test_render_block_with_entries(self):
        block = render_party_chatter(
            last_round=[("Renna Volt", "Ivo, the terminal is yours")],
            this_round=[("Cass Derev", "Engine's hot, move")],
        )
        assert "Party chatter" in block
        assert "terminal is yours" in block
        assert "just now" in block.lower() or "this round" in block.lower()

    def test_render_block_empty_when_no_chatter(self):
        assert render_party_chatter([], []) == ""


class TestPromptGuidanceGuard:
    """Send-side: ambient speech guidance must invite coordination, not
    frame the channel as decorative."""

    PLAYER_YAML = (Path(__file__).parent.parent.parent /
                   "scripts/aeonisk/multiagent/prompts/claude/en/player.yaml")

    def test_guidance_mentions_coordination_uses(self):
        content = self.PLAYER_YAML.read_text().lower()
        assert "delegate" in content or "call targets" in content, (
            "ambient speech guidance should name coordination uses")

    def test_intent_template_has_party_slots(self):
        intent = (Path(__file__).parent.parent.parent /
                  "scripts/aeonisk/multiagent/prompts/claude/en/player/"
                  "player_intent.yaml").read_text()
        assert "{party_capabilities}" in intent
        assert "{party_chatter}" in intent
