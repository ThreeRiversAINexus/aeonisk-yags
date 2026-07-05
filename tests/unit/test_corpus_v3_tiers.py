"""
Tests for corpus v3 competence-tier transforms.

Controlled-variable contract: apply_tier changes ONLY stat sheets and
identifying metadata. Names, goals, personalities, scenario_hint,
starting_clocks, inventories, and LLM config must be byte-identical
across tiers.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from corpus_v3_tiers import apply_tier, to_competent, to_hapless, TIERS


def make_config():
    return {
        "session_name": "Test Scenario",
        "max_turns": 8,
        "party_size": 2,
        "scenario_hint": "A test of moral pressure.",
        "starting_clocks": [{"name": "Doom", "current_ticks": 0,
                             "max_ticks": 8, "advance_meaning": "worse",
                             "regress_meaning": "better"}],
        "agents": {
            "dm": {"llm": {"provider": "openai", "model": "gpt-5.4-mini"}},
            "players": [
                {"name": "Renna", "faction": "Freeborn",
                 "llm": {"provider": "openai", "model": "gpt-5.4-mini"},
                 "personality": {"riskTolerance": 7},
                 "goals": ["Run the con"],
                 "attributes": {"Agility": 4, "Perception": 5,
                                "Intelligence": 4, "Empathy": 3},
                 "skills": {"Investigation": 6, "Charm": 5, "Guns": 5,
                            "Awareness": 4, "Stealth": 3}},
                {"name": "Ivo", "faction": "Freeborn",
                 "llm": {"provider": "openai", "model": "gpt-5.4-mini"},
                 "personality": {"riskTolerance": 5},
                 "goals": ["Keep the forgery consistent"],
                 "attributes": {"Intelligence": 5, "Perception": 4},
                 "skills": {"Systems": 6, "Investigation": 5}},
            ],
        },
    }


class TestCompetentTransform:

    def test_attrs_capped_with_one_specialty(self):
        attrs, _ = to_competent({"Perception": 5, "Agility": 4,
                                 "Empathy": 3}, {})
        assert attrs["Perception"] == 4  # best attr keeps 4
        assert attrs["Agility"] == 3
        assert attrs["Empathy"] == 3

    def test_skills_scaled_into_2_4_band(self):
        _, skills = to_competent({}, {"Investigation": 6, "Charm": 5,
                                      "Stealth": 3, "Guns": 2})
        assert skills["Investigation"] == 4
        assert skills["Charm"] == 3
        assert skills["Stealth"] == 2
        assert skills["Guns"] == 1
        assert max(skills.values()) <= 4


class TestHaplessTransform:

    def test_only_top_two_skills_survive_at_2(self):
        _, skills = to_hapless({}, {"Investigation": 6, "Charm": 5,
                                    "Guns": 5, "Awareness": 4})
        assert len(skills) == 2
        assert skills == {"Investigation": 2, "Charm": 2}

    def test_attrs_capped_at_3(self):
        attrs, _ = to_hapless({"Perception": 5, "Agility": 4}, {})
        assert max(attrs.values()) <= 3


class TestApplyTier:

    def test_expert_sheets_unchanged(self):
        config = make_config()
        variant = apply_tier(config, "expert")
        assert variant['agents']['players'][0]['skills'] == \
            config['agents']['players'][0]['skills']

    def test_mixed_keeps_player_one_expert(self):
        variant = apply_tier(make_config(), "mixed")
        players = variant['agents']['players']
        assert players[0]['skills']['Investigation'] == 6  # expert kept
        assert players[1]['skills']['Systems'] == 4        # competent

    def test_only_stats_and_metadata_change(self):
        config = make_config()
        for tier in TIERS:
            variant = apply_tier(config, tier)
            for original, changed in zip(config['agents']['players'],
                                         variant['agents']['players']):
                assert changed['name'] == original['name']
                assert changed['goals'] == original['goals']
                assert changed['personality'] == original['personality']
                assert changed['llm'] == original['llm']
            assert variant['scenario_hint'] == config['scenario_hint']
            assert variant['starting_clocks'] == config['starting_clocks']

    def test_tier_metadata_stamped(self):
        variant = apply_tier(make_config(), "hapless")
        assert variant['_corpus_v3']['party_tier'] == "hapless"
        assert "[hapless]" in variant['session_name']

    def test_source_config_not_mutated(self):
        config = make_config()
        import json as j
        before = j.dumps(config, sort_keys=True)
        apply_tier(config, "hapless")
        assert j.dumps(config, sort_keys=True) == before
