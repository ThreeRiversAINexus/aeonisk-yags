"""
Tests for prompt_eval_harness.py

Tests cover:
- ModuleSwapper: loading, detection, swapping, variant handling
- SessionExtractor: case extraction, filtering, condition inference
- MechanicalExtractor: JSON parsing, field extraction
- Scorers: damage comparison, suppression table, soulcredit
- ReportGenerator: report formatting
- CLI: argument parsing
- ResultStore: save/load/resume
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

# Add scripts dir to path
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from prompt_eval_harness import (
    ModuleSwapper,
    SessionExtractor,
    MechanicalExtractor,
    EvalCase,
    ReplayResult,
    DamageComparisonScorer,
    SuppressionTableScorer,
    SoulcreditScorer,
    ReportGenerator,
    ResultStore,
    SelfJudge,
    parse_model_spec,
    parse_args,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir(tmp_path):
    """Temporary directory for test files."""
    return tmp_path


@pytest.fixture
def mock_dm_prompts(tmp_dir):
    """Create mock DM prompt YAML files."""
    dm_dir = tmp_dir / "dm"
    dm_dir.mkdir()

    # Module A
    with open(dm_dir / "dm_resolution_combat.yaml", "w") as f:
        yaml.dump({
            "version": "2.0.0",
            "module": "dm_resolution_combat",
            "description": "Combat resolution",
            "content": "# COMBAT ACTION RESOLUTION\n\nYou are resolving a **COMBAT** action.\n\n## DAMAGE TABLE\nMargin 0-5: base_damage = 5",
        }, f)

    # Module B (variant)
    with open(dm_dir / "dm_resolution_combat_with_suppression.yaml", "w") as f:
        yaml.dump({
            "version": "2.0.0",
            "module": "dm_resolution_combat_with_suppression",
            "description": "Combat with suppression",
            "content": "# COMBAT ACTION RESOLUTION WITH SUPPRESSION\n\nClassify intent first.\n\n## SUPPRESSION TABLE\nMargin 0-5: base_damage = 0",
        }, f)

    # Module C
    with open(dm_dir / "dm_core.yaml", "w") as f:
        yaml.dump({
            "version": "2.0.0",
            "module": "dm_core",
            "description": "Core DM instructions",
            "content": "# CORE DM RULES\n\nYou are the Dungeon Master.",
        }, f)

    return dm_dir


@pytest.fixture
def replacement_module(tmp_dir):
    """Create a replacement module YAML file."""
    path = tmp_dir / "new_combat.yaml"
    with open(path, "w") as f:
        yaml.dump({
            "version": "3.0.0",
            "module": "dm_resolution_combat",
            "description": "New combat resolution",
            "content": "# NEW COMBAT RESOLUTION\n\nImproved damage tables.\n\n## DAMAGE TABLE v3\nMargin 0-5: base_damage = 2",
        }, f)
    return str(path)


@pytest.fixture
def sample_system_prompt(mock_dm_prompts):
    """Build a system prompt containing mock module content."""
    swapper = ModuleSwapper(mock_dm_prompts)
    parts = [
        swapper._modules["dm_core"],
        swapper._modules["dm_resolution_combat"],
    ]
    return "\n\n".join(parts)


@pytest.fixture
def sample_llm_call_event():
    """A sample llm_call event as it appears in JSONL."""
    response = json.dumps({
        "narration": "Your kinetic round punches through the guard's shoulder, spinning them sideways. " * 5,
        "success_tier": "GOOD",
        "margin": 12,
        "effects": {
            "damage": [{
                "target": "tgt_7a3f",
                "base_damage": 15,
                "soak": 7,
                "dealt": 8,
                "damage_type": "wound",
            }],
            "conditions": [{
                "name": "Off-Balance",
                "penalty": -2,
                "duration": 1,
                "description": "next attack at -2",
            }],
            "soulcredit_changes": [{
                "character_name": "Riven",
                "amount": 0,
                "reason": "justified combat",
            }],
            "void_changes": [],
            "clock_updates": [],
        },
        "roll_details": "Agility 4 x Guns 5 + d20(12) = 32 vs DC 20",
    })
    return {
        "event_type": "llm_call",
        "ts": "2026-02-15T10:00:00Z",
        "session": "test-session-123",
        "round": 3,
        "agent_id": "dm_01",
        "agent_type": "dm",
        "call_sequence": 5,
        "prompt": [
            {"role": "system", "content": "# CORE DM RULES\n\nYou are the Dungeon Master.\n\n# COMBAT ACTION RESOLUTION\n\nYou are resolving a **COMBAT** action.\n\n## DAMAGE TABLE\nMargin 0-5: base_damage = 5"},
            {"role": "user", "content": "Resolve the following action:\nAction type: combat\nPlayer action: fire suppressive shots at the guards\nMargin: 12"},
        ],
        "response": response,
        "model": "deepseek-ai/DeepSeek-V3.2",
        "temperature": 0.7,
        "tokens": {"input": 5000, "output": 800},
    }


@pytest.fixture
def sample_jsonl_file(tmp_dir, sample_llm_call_event):
    """Create a sample JSONL session file."""
    session_dir = tmp_dir / "sessions" / "treatment_v2" / "run_001"
    session_dir.mkdir(parents=True)
    jsonl_path = session_dir / "session_test.jsonl"

    events = [
        # Non-DM event (should be skipped)
        {"event_type": "llm_call", "agent_type": "player", "prompt": [], "response": "I attack"},
        # DM event without ActionResolution (should be skipped)
        {"event_type": "llm_call", "agent_type": "dm", "prompt": [
            {"role": "system", "content": "DM rules"},
            {"role": "user", "content": "Describe the scene"},
        ], "response": "The room is dark.", "model": "gpt-5-mini"},
        # Valid DM resolution event
        sample_llm_call_event,
        # Another valid event (combat, different margin)
        {
            **sample_llm_call_event,
            "round": 4,
            "call_sequence": 7,
            "response": json.dumps({
                "narration": "The shot goes wide, sparking off the wall beside the target. " * 5,
                "success_tier": "FAILURE",
                "margin": -3,
                "effects": {
                    "damage": [],
                    "conditions": [],
                    "soulcredit_changes": [{"character_name": "Riven", "amount": 0, "reason": "attempted combat"}],
                    "void_changes": [],
                    "clock_updates": [],
                },
            }),
        },
    ]

    with open(jsonl_path, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")

    return jsonl_path


def _make_eval_case(**overrides):
    """Helper to create an EvalCase with defaults."""
    defaults = {
        "case_id": "test_case_1",
        "session_file": "/tmp/test.jsonl",
        "condition": "treatment_v2",
        "round_num": 3,
        "original_model": "gpt-5-mini",
        "system_prompt": "system prompt here",
        "user_prompt": "user prompt here",
        "response_text": '{"narration": "test", "effects": {}}',
        "action_type": "combat",
        "player_action_text": "fire suppressive shots",
        "margin": 12,
    }
    defaults.update(overrides)
    return EvalCase(**defaults)


# ---------------------------------------------------------------------------
# ModuleSwapper tests
# ---------------------------------------------------------------------------

class TestModuleSwapper:
    def test_loads_all_modules(self, mock_dm_prompts):
        swapper = ModuleSwapper(mock_dm_prompts)
        assert len(swapper.module_names) == 3
        assert "dm_resolution_combat" in swapper.module_names
        assert "dm_core" in swapper.module_names

    def test_detect_modules_in_system_prompt(self, mock_dm_prompts, sample_system_prompt):
        swapper = ModuleSwapper(mock_dm_prompts)
        detected = swapper.detect_modules(sample_system_prompt)
        assert "dm_core" in detected
        assert "dm_resolution_combat" in detected
        # Suppression variant should NOT be detected
        assert "dm_resolution_combat_with_suppression" not in detected

    def test_swap_module_replaces_content(self, mock_dm_prompts, sample_system_prompt):
        swapper = ModuleSwapper(mock_dm_prompts)
        new_content = "# REPLACED MODULE\nNew stuff here."
        modified = swapper.swap_module(sample_system_prompt, "dm_resolution_combat", new_content)

        assert "# REPLACED MODULE" in modified
        assert "New stuff here." in modified
        # Original content should be gone
        assert "## DAMAGE TABLE" not in modified
        # Other modules should be preserved
        assert "# CORE DM RULES" in modified

    def test_swap_module_variant_fallback(self, mock_dm_prompts):
        """When dm_resolution_combat not found, try dm_resolution_combat_with_suppression."""
        swapper = ModuleSwapper(mock_dm_prompts)
        # Build a prompt with the suppression variant
        prompt_with_suppression = (
            swapper._modules["dm_core"] + "\n\n" +
            swapper._modules["dm_resolution_combat_with_suppression"]
        )
        new_content = "# REPLACED SUPPRESSION MODULE"
        modified = swapper.swap_module(prompt_with_suppression, "dm_resolution_combat", new_content)
        assert "# REPLACED SUPPRESSION MODULE" in modified
        assert "# COMBAT ACTION RESOLUTION WITH SUPPRESSION" not in modified

    def test_swap_module_not_found_raises(self, mock_dm_prompts):
        swapper = ModuleSwapper(mock_dm_prompts)
        with pytest.raises(ValueError, match="not found"):
            swapper.swap_module("completely different text", "dm_resolution_combat", "new")

    def test_load_replacement(self, mock_dm_prompts, replacement_module):
        swapper = ModuleSwapper(mock_dm_prompts)
        name, content = swapper.load_replacement(replacement_module)
        assert name == "dm_resolution_combat"
        assert "# NEW COMBAT RESOLUTION" in content

    def test_load_replacement_missing_file(self, mock_dm_prompts):
        swapper = ModuleSwapper(mock_dm_prompts)
        with pytest.raises(FileNotFoundError):
            swapper.load_replacement("/nonexistent/module.yaml")

    def test_load_replacement_no_content(self, mock_dm_prompts, tmp_dir):
        path = tmp_dir / "empty.yaml"
        with open(path, "w") as f:
            yaml.dump({"module": "test", "version": "1.0"}, f)
        swapper = ModuleSwapper(mock_dm_prompts)
        with pytest.raises(ValueError, match="no 'content' field"):
            swapper.load_replacement(str(path))

    def test_missing_prompts_dir_warns(self, tmp_dir):
        """Missing prompts dir should warn, not crash."""
        swapper = ModuleSwapper(tmp_dir / "nonexistent")
        assert len(swapper.module_names) == 0


# ---------------------------------------------------------------------------
# MechanicalExtractor tests
# ---------------------------------------------------------------------------

class TestMechanicalExtractor:
    def test_parse_raw_json(self):
        response = json.dumps({
            "narration": "Shot hits the target.",
            "margin": 12,
            "effects": {"damage": [{"base_damage": 15, "dealt": 8}]},
        })
        parsed = MechanicalExtractor.parse_response(response)
        assert parsed["margin"] == 12

    def test_parse_markdown_fenced_json(self):
        response = '```json\n{"narration": "test", "margin": 5, "effects": {}}\n```'
        parsed = MechanicalExtractor.parse_response(response)
        assert parsed["margin"] == 5

    def test_parse_json_with_surrounding_text(self):
        response = 'Here is my response:\n{"narration": "test", "margin": 7, "effects": {}}\nEnd.'
        parsed = MechanicalExtractor.parse_response(response)
        assert parsed["margin"] == 7

    def test_parse_empty_response(self):
        parsed = MechanicalExtractor.parse_response("")
        assert parsed == {}

    def test_parse_invalid_json(self):
        parsed = MechanicalExtractor.parse_response("not json at all")
        assert parsed == {}

    def test_parse_trailing_comma(self):
        response = '{"narration": "test", "margin": 3, "effects": {},}'
        parsed = MechanicalExtractor.parse_response(response)
        assert parsed["margin"] == 3

    def test_extract_mechanical_fields_full(self):
        parsed = {
            "narration": "x" * 500,
            "success_tier": "GOOD",
            "margin": 12,
            "effects": {
                "damage": [
                    {"target": "tgt_1", "base_damage": 15, "soak": 7, "dealt": 8, "damage_type": "wound"},
                    {"target": "tgt_2", "base_damage": 5, "soak": 3, "dealt": 2, "damage_type": "stun"},
                ],
                "conditions": [
                    {"name": "Pinned", "penalty": -4},
                ],
                "void_changes": [
                    {"character_name": "Ash", "amount": 2},
                ],
                "soulcredit_changes": [
                    {"character_name": "Ash", "amount": -1},
                ],
                "clock_updates": [
                    {"clock_name": "Ambush", "ticks": 1},
                ],
            },
        }
        fields = MechanicalExtractor.extract_mechanical_fields(parsed)
        assert fields["narration_length"] == 500
        assert fields["margin"] == 12
        assert fields["damage_count"] == 2
        assert fields["total_base_damage"] == 20
        assert fields["total_dealt"] == 10
        assert fields["total_soak"] == 10
        assert fields["condition_count"] == 1
        assert fields["total_void_change"] == 2
        assert fields["total_soulcredit"] == -1
        assert fields["clock_update_count"] == 1

    def test_extract_mechanical_fields_empty(self):
        parsed = {"narration": "", "effects": {}}
        fields = MechanicalExtractor.extract_mechanical_fields(parsed)
        assert fields["damage_count"] == 0
        assert fields["total_base_damage"] == 0
        assert fields["condition_count"] == 0

    def test_extract_damage_as_dict_not_list(self):
        """Handle case where damage is a single dict instead of list."""
        parsed = {
            "narration": "hit",
            "effects": {
                "damage": {"base_damage": 10, "dealt": 5, "soak": 5},
            },
        }
        fields = MechanicalExtractor.extract_mechanical_fields(parsed)
        assert fields["damage_count"] == 1
        assert fields["total_base_damage"] == 10


# ---------------------------------------------------------------------------
# Scorer tests
# ---------------------------------------------------------------------------

class TestDamageComparisonScorer:
    def test_basic_comparison(self):
        scorer = DamageComparisonScorer()
        original = {"total_base_damage": 15}
        replay = {"total_base_damage": 3}
        case = _make_eval_case()
        result = scorer.score(original, replay, case)
        assert result["original_base_damage"] == 15
        assert result["replay_base_damage"] == 3
        assert result["delta"] == -12
        assert result["zero_damage"] is False

    def test_zero_damage(self):
        scorer = DamageComparisonScorer()
        result = scorer.score({"total_base_damage": 10}, {"total_base_damage": 0}, _make_eval_case())
        assert result["zero_damage"] is True


class TestSuppressionTableScorer:
    def test_in_range_low_margin(self):
        scorer = SuppressionTableScorer()
        replay = {"total_base_damage": 0, "margin": 3, "condition_count": 1, "conditions": [{"name": "Suppressed"}]}
        result = scorer.score({}, replay, _make_eval_case(margin=3))
        assert result["in_range"] is True
        assert result["has_condition"] is True

    def test_out_of_range_high_damage(self):
        scorer = SuppressionTableScorer()
        replay = {"total_base_damage": 15, "margin": 3, "condition_count": 0, "conditions": []}
        result = scorer.score({}, replay, _make_eval_case(margin=3))
        assert result["in_range"] is False

    def test_margin_from_case_fallback(self):
        """When replay doesn't have margin, fall back to case.margin."""
        scorer = SuppressionTableScorer()
        replay = {"total_base_damage": 2, "condition_count": 1, "conditions": [{"name": "Pinned"}]}
        result = scorer.score({}, replay, _make_eval_case(margin=8))
        assert result["margin"] == 8
        assert result["in_range"] is True


class TestSoulcreditScorer:
    def test_basic(self):
        scorer = SoulcreditScorer()
        result = scorer.score(
            {"total_soulcredit": 0},
            {"total_soulcredit": -1},
            _make_eval_case(),
        )
        assert result["delta"] == -1


# ---------------------------------------------------------------------------
# SessionExtractor tests
# ---------------------------------------------------------------------------

class TestSessionExtractor:
    def test_infer_condition(self):
        extractor = SessionExtractor()
        assert extractor.infer_condition(Path("/data/control/session.jsonl")) == "control"
        assert extractor.infer_condition(Path("/data/treatment_v1/session.jsonl")) == "treatment_v1"
        assert extractor.infer_condition(Path("/data/treatment_v2/session.jsonl")) == "treatment_v2"
        assert extractor.infer_condition(Path("/data/other/session.jsonl")) == "unknown"

    def test_extract_cases_from_file(self, sample_jsonl_file, mock_dm_prompts):
        extractor = SessionExtractor(session_dirs=[sample_jsonl_file.parent.parent.parent])
        swapper = ModuleSwapper(mock_dm_prompts)

        cases = extractor.extract_cases(module_swapper=swapper)
        # Should find 2 valid DM resolution events
        assert len(cases) == 2

        # Check first case
        case = cases[0]
        assert case.condition == "treatment_v2"
        assert case.original_model == "deepseek-ai/DeepSeek-V3.2"
        assert case.round_num == 3
        assert case.margin == 12
        assert len(case.system_prompt) > 0
        assert len(case.user_prompt) > 0

    def test_action_type_filter(self, sample_jsonl_file, mock_dm_prompts):
        extractor = SessionExtractor(session_dirs=[sample_jsonl_file.parent.parent.parent])
        cases = extractor.extract_cases(action_type_filter="combat")
        assert len(cases) == 2  # Both are combat

        cases = extractor.extract_cases(action_type_filter="investigate")
        assert len(cases) == 0

    def test_intent_filter(self, sample_jsonl_file, mock_dm_prompts):
        extractor = SessionExtractor(session_dirs=[sample_jsonl_file.parent.parent.parent])
        cases = extractor.extract_cases(intent_filter="suppress")
        # "suppress" appears in the user prompt action text
        assert len(cases) == 2  # Both have "suppressive" in user prompt

    def test_max_cases(self, sample_jsonl_file, mock_dm_prompts):
        extractor = SessionExtractor(session_dirs=[sample_jsonl_file.parent.parent.parent])
        cases = extractor.extract_cases(max_cases=1)
        assert len(cases) == 1

    def test_margin_range_filter(self, sample_jsonl_file, mock_dm_prompts):
        extractor = SessionExtractor(session_dirs=[sample_jsonl_file.parent.parent.parent])
        # First case has margin 12, second has margin -3
        cases = extractor.extract_cases(margin_range=(10, 99))
        assert len(cases) == 1
        assert cases[0].margin == 12


# ---------------------------------------------------------------------------
# ReportGenerator tests
# ---------------------------------------------------------------------------

class TestReportGenerator:
    def test_empty_results(self):
        report, scores = ReportGenerator.generate([], "test_module", [])
        assert "No results" in report

    def test_damage_comparison_report(self):
        results = [
            ReplayResult(
                case_id="c1", condition="treatment_v2", round_num=1,
                action_type="combat", original_model="gpt-5-mini",
                eval_model="openai:gpt-5-mini", margin=12,
                original={"total_base_damage": 15},
                replay={"total_base_damage": 3},
                scores={"damage_comparison": {
                    "original_base_damage": 15, "replay_base_damage": 3,
                    "delta": -12, "zero_damage": False,
                }},
            ),
            ReplayResult(
                case_id="c2", condition="treatment_v2", round_num=2,
                action_type="combat", original_model="gpt-5-mini",
                eval_model="openai:gpt-5-mini", margin=8,
                original={"total_base_damage": 10},
                replay={"total_base_damage": 0},
                scores={"damage_comparison": {
                    "original_base_damage": 10, "replay_base_damage": 0,
                    "delta": -10, "zero_damage": True,
                }},
            ),
        ]
        scorer = DamageComparisonScorer()
        report, scores = ReportGenerator.generate(results, "test_module", [scorer])
        assert "openai:gpt-5-mini" in report
        assert "damage_comparison" in report
        assert "damage_comparison" in scores
        assert "openai:gpt-5-mini" in scores["damage_comparison"]

    def test_error_results_reported(self):
        results = [
            ReplayResult(
                case_id="c1", condition="x", round_num=1,
                action_type="combat", original_model="m", eval_model="m",
                margin=0, original={}, replay={}, scores={},
                error="Connection timeout",
            ),
        ]
        report, _ = ReportGenerator.generate(results, "test", [])
        assert "Errors (1)" in report
        assert "Connection timeout" in report


# ---------------------------------------------------------------------------
# ResultStore tests
# ---------------------------------------------------------------------------

class TestResultStore:
    def test_save_and_load(self, tmp_dir):
        path = str(tmp_dir / "results.jsonl")
        store = ResultStore(path)

        results = [
            ReplayResult(
                case_id="c1", condition="treatment_v2", round_num=1,
                action_type="combat", original_model="gpt-5-mini",
                eval_model="openai:gpt-5-mini", margin=12,
                original={"total_base_damage": 15},
                replay={"total_base_damage": 3},
                scores={"damage_comparison": {"delta": -12}},
            ),
            ReplayResult(
                case_id="c2", condition="control", round_num=2,
                action_type="investigate", original_model="gpt-5-mini",
                eval_model="deepinfra:deepseek-ai/DeepSeek-V3.2", margin=5,
                original={}, replay={},
                scores={},
            ),
        ]

        store.save_results(results)

        # Load completed keys
        keys = store.load_completed_keys()
        assert ("c1", "openai:gpt-5-mini") in keys
        assert ("c2", "deepinfra:deepseek-ai/DeepSeek-V3.2") in keys
        assert len(keys) == 2

    def test_append_mode(self, tmp_dir):
        path = str(tmp_dir / "results.jsonl")
        store = ResultStore(path)

        r1 = ReplayResult(
            case_id="c1", condition="x", round_num=1,
            action_type="combat", original_model="m", eval_model="m1",
            margin=0, original={}, replay={}, scores={},
        )
        r2 = ReplayResult(
            case_id="c2", condition="x", round_num=2,
            action_type="combat", original_model="m", eval_model="m2",
            margin=0, original={}, replay={}, scores={},
        )

        store.save_results([r1])
        store.save_results([r2], append=True)

        keys = store.load_completed_keys()
        assert len(keys) == 2

    def test_save_with_prompts(self, tmp_dir):
        path = str(tmp_dir / "results.jsonl")
        store = ResultStore(path)

        r = ReplayResult(
            case_id="c1", condition="x", round_num=1,
            action_type="combat", original_model="m", eval_model="m",
            margin=0, original={}, replay={}, scores={},
            system_prompt="system here",
            user_prompt="user here",
            replay_response="response here",
        )
        store.save_results([r])

        with open(path, "r") as f:
            data = json.loads(f.readline())
        assert data["system_prompt"] == "system here"
        assert data["user_prompt"] == "user here"
        assert data["replay_response"] == "response here"

    def test_streaming_append_result(self, tmp_dir):
        """Results are written to disk immediately as they complete."""
        path = str(tmp_dir / "streaming.jsonl")
        store = ResultStore(path)
        store.open()

        r1 = ReplayResult(
            case_id="c1", condition="x", round_num=1,
            action_type="combat", original_model="m", eval_model="m1",
            margin=5, original={"total_base_damage": 10},
            replay={"total_base_damage": 3}, scores={},
        )
        store.append_result(r1)

        # File should exist and contain one line already (before close)
        with open(path, "r") as f:
            lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["case_id"] == "c1"

        r2 = ReplayResult(
            case_id="c2", condition="y", round_num=2,
            action_type="investigate", original_model="m", eval_model="m2",
            margin=8, original={}, replay={}, scores={},
        )
        store.append_result(r2)
        store.close()

        # Both results should be on disk
        keys = store.load_completed_keys()
        assert len(keys) == 2
        assert ("c1", "m1") in keys
        assert ("c2", "m2") in keys

    def test_streaming_creates_parent_dirs(self, tmp_dir):
        """open() creates parent directories that don't exist yet."""
        path = str(tmp_dir / "nested" / "deep" / "results.jsonl")
        store = ResultStore(path)
        store.open()
        store.close()
        assert Path(path).exists()

    def test_streaming_context_manager(self, tmp_dir):
        """ResultStore can be used as a context manager."""
        path = str(tmp_dir / "ctx.jsonl")
        store = ResultStore(path)
        store.open()
        with store:
            r = ReplayResult(
                case_id="c1", condition="x", round_num=1,
                action_type="combat", original_model="m", eval_model="m",
                margin=0, original={}, replay={}, scores={},
            )
            store.append_result(r)
        # File should be closed and flushed
        keys = store.load_completed_keys()
        assert len(keys) == 1


# ---------------------------------------------------------------------------
# Provider inference tests
# ---------------------------------------------------------------------------

class TestParseModelSpec:
    def test_valid_specs(self):
        assert parse_model_spec("openai:gpt-5-mini") == ("openai", "gpt-5-mini")
        assert parse_model_spec("anthropic:claude-sonnet-4-5") == ("anthropic", "claude-sonnet-4-5")
        assert parse_model_spec("deepinfra:deepseek-ai/DeepSeek-V3.2") == ("deepinfra", "deepseek-ai/DeepSeek-V3.2")
        assert parse_model_spec("grok:grok-4-latest") == ("grok", "grok-4-latest")
        assert parse_model_spec("gemini:gemini-2.5-pro") == ("gemini", "gemini-2.5-pro")

    def test_no_colon_raises(self):
        with pytest.raises(ValueError, match="provider:model"):
            parse_model_spec("gpt-5-mini")

    def test_empty_provider_raises(self):
        with pytest.raises(ValueError, match="Both provider and model"):
            parse_model_spec(":gpt-5-mini")

    def test_empty_model_raises(self):
        with pytest.raises(ValueError, match="Both provider and model"):
            parse_model_spec("openai:")


# ---------------------------------------------------------------------------
# CLI argument parsing tests
# ---------------------------------------------------------------------------

class TestCLIParsing:
    def test_minimal_args(self):
        args = parse_args(["--swap-module", "path/to/module.yaml"])
        assert args.swap_module == "path/to/module.yaml"
        assert args.models == ["openai:gpt-5-mini"]
        assert args.workers == 4
        assert args.scan_only is False
        assert args.dry_run is False

    def test_full_args(self):
        args = parse_args([
            "--swap-module", "module.yaml",
            "--models", "openai:gpt-5-mini", "deepinfra:deepseek-ai/DeepSeek-V3.2",
            "--workers", "8",
            "--proxy", "http://localhost:8000",
            "--batch",
            "--action-type", "combat",
            "--intent-filter", "suppress",
            "--max-cases", "50",
            "--scorers", "suppression_table", "damage_comparison",
            "--output-dir", "results/my_eval",
            "--save-prompts",
            "--temperature", "0.5",
        ])
        assert args.models == ["openai:gpt-5-mini", "deepinfra:deepseek-ai/DeepSeek-V3.2"]
        assert args.workers == 8
        assert args.proxy == "http://localhost:8000"
        assert args.batch is True
        assert args.action_type == "combat"
        assert args.intent_filter == "suppress"
        assert args.max_cases == 50
        assert args.scorers == ["suppression_table", "damage_comparison"]
        assert args.output_dir == "results/my_eval"
        assert args.save_prompts is True
        assert args.temperature == 0.5

    def test_self_judge_args(self):
        args = parse_args([
            "--swap-module", "module.yaml",
            "--self-judge",
            "--goal-file", "goals.yaml",
            "--judge-model", "anthropic:claude-sonnet-4-5",
            "--max-iterations", "3",
            "--confirm-each-iteration",
        ])
        assert args.self_judge is True
        assert args.goal_file == "goals.yaml"
        assert args.judge_model == "anthropic:claude-sonnet-4-5"
        assert args.max_iterations == 3
        assert args.confirm_each_iteration is True

    def test_scan_only(self):
        args = parse_args(["--swap-module", "m.yaml", "--scan-only"])
        assert args.scan_only is True

    def test_dry_run(self):
        args = parse_args(["--swap-module", "m.yaml", "--dry-run"])
        assert args.dry_run is True

    def test_resume(self):
        args = parse_args(["--swap-module", "m.yaml", "--resume", "--output-dir", "results/prev_run"])
        assert args.resume is True
        assert args.output_dir == "results/prev_run"


# ---------------------------------------------------------------------------
# Output directory tests
# ---------------------------------------------------------------------------

class TestCreateOutputDir:
    def test_creates_timestamped_dir(self, tmp_dir):
        """Should create results/eval_<timestamp>_<uuid>/ with metadata + copied swap module."""
        from prompt_eval_harness import _create_output_dir

        # Create a source swap module YAML to copy from
        src_yaml = tmp_dir / "source_module.yaml"
        with open(src_yaml, "w") as f:
            yaml.dump(
                {"module": "dm_resolution_combat", "content": "prompt content here"},
                f, default_flow_style=False,
            )

        args = argparse.Namespace(
            output_dir=str(tmp_dir / "results"),
            resume=False,
            swap_module=str(src_yaml),
            action_type="combat",
            intent_filter="suppress",
            original_model=None,
            margin_range=None,
            max_cases=None,
            scorers=["damage_comparison"],
            workers=4,
            proxy=None,
            batch=False,
            temperature=0.7,
            max_tokens=4000,
            save_prompts=False,
            sessions=None,
        )

        output_dir = _create_output_dir(args, "dm_resolution_combat", "prompt content here", [("openai", "gpt-5-mini")])

        assert output_dir.exists()
        assert "eval_" in output_dir.name
        assert (output_dir / "metadata.json").exists()
        # Original YAML copied with its original filename
        assert (output_dir / "source_module.yaml").exists()

        # Check metadata contents
        with open(output_dir / "metadata.json") as f:
            meta = json.load(f)
        assert meta["module_name"] == "dm_resolution_combat"
        assert meta["models"] == ["openai:gpt-5-mini"]
        assert meta["action_type"] == "combat"

        # Check original module is an exact copy
        with open(output_dir / "source_module.yaml") as f:
            swap = yaml.safe_load(f)
        assert swap["module"] == "dm_resolution_combat"
        assert swap["content"] == "prompt content here"

    def test_resume_reuses_existing_dir(self, tmp_dir):
        """--resume with existing eval dir (has metadata.json) should reuse it."""
        from prompt_eval_harness import _create_output_dir

        # Create existing eval dir
        eval_dir = tmp_dir / "results" / "eval_2026-02-17_120000_abc12345"
        eval_dir.mkdir(parents=True)
        with open(eval_dir / "metadata.json", "w") as f:
            json.dump({"module_name": "test"}, f)

        args = argparse.Namespace(
            output_dir=str(eval_dir),
            resume=True,
            swap_module="m.yaml", action_type=None, intent_filter=None,
            original_model=None, margin_range=None, max_cases=None,
            scorers=[], workers=4, proxy=None, batch=False,
            temperature=0.7, max_tokens=4000, save_prompts=False, sessions=None,
        )

        result = _create_output_dir(args, "m", "c", [("openai", "gpt-5-mini")])
        assert result == eval_dir  # Reused, not new


# ---------------------------------------------------------------------------
# Integration-style tests (no LLM calls)
# ---------------------------------------------------------------------------

class TestScanOnly:
    """Test the scan-only flow end-to-end (no LLM calls)."""

    def test_scan_finds_cases(self, sample_jsonl_file, mock_dm_prompts, capsys):
        """Scan should find cases and print summary."""
        from prompt_eval_harness import main

        result = main([
            "--swap-module", str(mock_dm_prompts / "dm_resolution_combat.yaml"),
            "--sessions", str(sample_jsonl_file.parent.parent.parent),
            "--scan-only",
        ])

        assert result == 0
        captured = capsys.readouterr()
        assert "Found 2 eval cases" in captured.out
        assert "treatment_v2" in captured.out


class TestDryRun:
    """Test dry-run flow."""

    def test_dry_run_shows_output(self, sample_jsonl_file, mock_dm_prompts, capsys):
        """Dry run should complete without error and show output for each case."""
        from prompt_eval_harness import main

        result = main([
            "--swap-module", str(mock_dm_prompts / "dm_resolution_combat.yaml"),
            "--sessions", str(sample_jsonl_file.parent.parent.parent),
            "--dry-run",
            "--max-cases", "1",
        ])

        assert result == 0
        captured = capsys.readouterr()
        # Should show dry run header
        assert "Dry run" in captured.out
        # Should process at least one case (even if swap fails, it prints info)
        assert "session_" in captured.out

    def test_dry_run_with_matching_module(self, tmp_path, capsys):
        """Dry run with system prompt that actually contains the module content."""
        from prompt_eval_harness import main

        # Create module YAML
        module_content = "# TEST MODULE CONTENT\nThis is the module to swap."
        new_module_content = "# NEW MODULE CONTENT\nReplacement content."

        module_yaml = tmp_path / "original.yaml"
        with open(module_yaml, "w") as f:
            yaml.dump({"module": "test_module", "content": module_content}, f)

        replacement_yaml = tmp_path / "replacement.yaml"
        with open(replacement_yaml, "w") as f:
            yaml.dump({"module": "test_module", "content": new_module_content}, f)

        # Create DM prompts dir with the module
        dm_dir = tmp_path / "dm_prompts"
        dm_dir.mkdir()
        with open(dm_dir / "test_module.yaml", "w") as f:
            yaml.dump({"module": "test_module", "content": module_content}, f)

        # Create JSONL with system prompt containing the module
        system_prompt = f"Preamble text\n\n{module_content}\n\nPostamble text"
        event = {
            "event_type": "llm_call",
            "agent_type": "dm",
            "round": 1,
            "model": "gpt-5-mini",
            "prompt": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Resolve combat action"},
            ],
            "response": json.dumps({
                "narration": "x" * 200,
                "success_tier": "GOOD",
                "margin": 10,
                "effects": {"damage": [{"base_damage": 5}]},
            }),
        }
        session_dir = tmp_path / "sessions"
        session_dir.mkdir()
        jsonl_path = session_dir / "test.jsonl"
        with open(jsonl_path, "w") as f:
            f.write(json.dumps(event) + "\n")

        # Patch DM_PROMPTS_DIR so ModuleSwapper loads our test module
        with patch("prompt_eval_harness.DM_PROMPTS_DIR", dm_dir):
            result = main([
                "--swap-module", str(replacement_yaml),
                "--sessions", str(session_dir),
                "--dry-run",
                "--max-cases", "1",
            ])

        assert result == 0
        captured = capsys.readouterr()
        assert "Case:" in captured.out
        assert "Swapped region" in captured.out


# ---------------------------------------------------------------------------
# SelfJudge target checking tests
# ---------------------------------------------------------------------------

class TestSelfJudgeTargets:
    def test_check_targets_all_met(self, tmp_dir):
        goal_file = tmp_dir / "goals.yaml"
        with open(goal_file, "w") as f:
            yaml.dump({
                "description": "Test goals",
                "targets": {
                    "suppression_table": {"in_range_pct": 80},
                    "damage_comparison": {"zero_damage_pct": 50},
                },
            }, f)

        from prompt_eval_harness import SelfJudge
        judge = SelfJudge(str(goal_file))

        score_dict = {
            "suppression_table": {"gpt-5-mini": {"in_range_pct": 90}},
            "damage_comparison": {"gpt-5-mini": {"zero_damage_pct": 60}},
        }

        all_met, details = judge.check_targets(score_dict)
        assert all_met is True
        assert all(d["met"] for d in details.values())

    def test_check_targets_not_met(self, tmp_dir):
        goal_file = tmp_dir / "goals.yaml"
        with open(goal_file, "w") as f:
            yaml.dump({
                "description": "Test goals",
                "targets": {
                    "suppression_table": {"in_range_pct": 80},
                },
            }, f)

        from prompt_eval_harness import SelfJudge
        judge = SelfJudge(str(goal_file))

        score_dict = {
            "suppression_table": {"gpt-5-mini": {"in_range_pct": 50}},
        }

        all_met, details = judge.check_targets(score_dict)
        assert all_met is False

    def test_check_targets_max_metric(self, tmp_dir):
        """max_avg_base_damage should use max across models and check <=."""
        goal_file = tmp_dir / "goals.yaml"
        with open(goal_file, "w") as f:
            yaml.dump({
                "description": "Test goals",
                "targets": {
                    "damage_comparison": {"max_avg_base_damage": 5},
                },
            }, f)

        from prompt_eval_harness import SelfJudge
        judge = SelfJudge(str(goal_file))

        score_dict = {
            "damage_comparison": {
                "gpt-5-mini": {"max_avg_base_damage": 3},
                "deepseek": {"max_avg_base_damage": 7},
            },
        }

        all_met, details = judge.check_targets(score_dict)
        assert all_met is False  # max(3, 7) = 7 > 5


# ---------------------------------------------------------------------------
# Self-Judge Improvements tests
# ---------------------------------------------------------------------------

def _make_scored_results(n_in_range, n_has_condition, n_total=10, model="openai:gpt-5-mini"):
    """Create replay results with controlled in_range and has_condition ratios."""
    results = []
    for i in range(n_total):
        in_range = i < n_in_range
        has_cond = i < n_has_condition
        bd = 0 if in_range else 15
        results.append(ReplayResult(
            case_id=f"c{i}", condition="x", round_num=1,
            action_type="combat", original_model="m", eval_model=model,
            margin=5,
            original={"total_base_damage": 10},
            replay={"total_base_damage": bd, "margin": 5, "condition_count": 1 if has_cond else 0,
                     "conditions": [{"name": "Pinned"}] if has_cond else []},
            scores={
                "suppression_table": {
                    "base_damage": bd,
                    "margin": 5,
                    "expected_range": [0, 0],
                    "in_range": in_range,
                    "has_condition": has_cond,
                    "condition_names": ["Pinned"] if has_cond else [],
                },
            },
            replay_response='{"narration": "test shot", "effects": {}}',
            player_action_text="fire suppressive shots at the guards",
        ))
    return results


class TestSelfJudgeImprovements:
    """Tests for self-judge iteration improvements (iteration history, rollback, two-phase)."""

    def test_judge_prompt_includes_iteration_history(self, tmp_dir):
        """History table rendered with correct scores and transitions."""
        goal_file = tmp_dir / "goals.yaml"
        with open(goal_file, "w") as f:
            yaml.dump({
                "description": "Test goals",
                "targets": {
                    "suppression_table": {"in_range_pct": 80},
                },
            }, f)

        judge = SelfJudge(str(goal_file))

        iteration_history = [
            {
                "iteration": 1,
                "score_pct": 0.0,
                "targets_met": 0,
                "targets_total": 1,
                "details": {
                    "suppression_table.in_range_pct": {"target": 80, "actual": 50.0, "met": False},
                },
            },
            {
                "iteration": 2,
                "score_pct": 100.0,
                "targets_met": 1,
                "targets_total": 1,
                "details": {
                    "suppression_table.in_range_pct": {"target": 80, "actual": 85.0, "met": True},
                },
            },
        ]

        prompt = judge.build_judge_prompt(
            current_module_content="# TEST MODULE\nContent here",
            score_dict={"suppression_table": {"gpt-5-mini": {"in_range_pct": 85.0}}},
            target_details={
                "suppression_table.in_range_pct": {"target": 80, "actual": 85.0, "met": True},
            },
            failed_examples=[],
            iteration_history=iteration_history,
        )

        assert "Iteration History" in prompt
        assert "| Iter |" in prompt  # Table header
        assert "50.0" in prompt  # First iteration's actual value
        assert "85.0" in prompt  # Second iteration's actual value
        assert "FAIL" in prompt  # First iteration failed
        assert "PASS" in prompt  # Second iteration passed

    def test_judge_prompt_includes_player_action(self, tmp_dir):
        """Failed examples show player action text."""
        goal_file = tmp_dir / "goals.yaml"
        with open(goal_file, "w") as f:
            yaml.dump({"description": "Test", "targets": {}}, f)

        judge = SelfJudge(str(goal_file))

        failed = [
            ReplayResult(
                case_id="c1", condition="x", round_num=1,
                action_type="combat", original_model="m", eval_model="m",
                margin=12, original={"total_base_damage": 10},
                replay={"total_base_damage": 15, "conditions": []},
                scores={"suppression_table": {"in_range": False}},
                player_action_text="fire suppressive shots at the guards",
            ),
        ]

        prompt = judge.build_judge_prompt(
            current_module_content="# MODULE",
            score_dict={},
            target_details={},
            failed_examples=failed,
        )

        assert "fire suppressive shots at the guards" in prompt

    def test_judge_prompt_includes_success_examples(self, tmp_dir):
        """Up to 3 passing cases shown before failures."""
        goal_file = tmp_dir / "goals.yaml"
        with open(goal_file, "w") as f:
            yaml.dump({"description": "Test", "targets": {}}, f)

        judge = SelfJudge(str(goal_file))

        successes = [
            ReplayResult(
                case_id=f"s{i}", condition="x", round_num=i,
                action_type="combat", original_model="m", eval_model="m",
                margin=8, original={"total_base_damage": 3},
                replay={"total_base_damage": 0, "conditions": [{"name": "Pinned"}]},
                scores={"suppression_table": {"in_range": True, "has_condition": True}},
                player_action_text="fire warning shots",
            )
            for i in range(5)
        ]

        prompt = judge.build_judge_prompt(
            current_module_content="# MODULE",
            score_dict={},
            target_details={},
            failed_examples=[],
            success_examples=successes,
        )

        assert "Successful Examples" in prompt
        # Should show at most 3
        assert "s0" in prompt
        assert "s1" in prompt
        assert "s2" in prompt
        assert "s4" not in prompt  # Only 3 shown

    def test_judge_prompt_includes_original_comparison(self, tmp_dir):
        """Failed examples show original vs replay comparison."""
        goal_file = tmp_dir / "goals.yaml"
        with open(goal_file, "w") as f:
            yaml.dump({"description": "Test", "targets": {}}, f)

        judge = SelfJudge(str(goal_file))

        failed = [
            ReplayResult(
                case_id="c1", condition="x", round_num=1,
                action_type="combat", original_model="m", eval_model="m",
                margin=12,
                original={"total_base_damage": 5, "conditions": []},
                replay={"total_base_damage": 15, "conditions": [{"name": "Pinned"}]},
                scores={"suppression_table": {"in_range": False}},
                player_action_text="fire suppressive shots",
            ),
        ]

        prompt = judge.build_judge_prompt(
            current_module_content="# MODULE",
            score_dict={},
            target_details={},
            failed_examples=failed,
        )

        # Should show original → replay for base_damage
        assert "5" in prompt  # original base_damage
        assert "15" in prompt  # replay base_damage
        # Both should appear in a comparison context
        assert "Original" in prompt or "original" in prompt

    def test_rollback_on_regression(self, tmp_dir):
        """After worse score, current_content resets to best_content."""
        goal_file = tmp_dir / "goals.yaml"
        with open(goal_file, "w") as f:
            yaml.dump({
                "description": "Test rollback",
                "max_iterations": 3,
                "eval_subset": {"action_type": "combat", "max_cases": 10},
                "targets": {
                    "suppression_table": {
                        "in_range_pct": 90,
                        "has_condition_pct": 60,
                    },
                },
                "convergence": {"min_improvement": 2},
            }, f)

        judge = SelfJudge(str(goal_file), max_iterations=3)

        # Track what content the judge receives
        judge_prompt_contents = []
        judge_call_count = [0]

        def mock_call_judge(prompt):
            judge_call_count[0] += 1
            judge_prompt_contents.append(prompt)
            return f"rewrite_{judge_call_count[0]}" * 50  # Long enough (>100 chars)

        judge.call_judge = mock_call_judge

        # Iteration results: 50% → 0% (regression) → 100%
        iter_results = [
            _make_scored_results(7, 8),   # 70% in_range (FAIL), 80% has_cond (PASS) → 1/2 = 50%
            _make_scored_results(3, 4),   # 30% in_range (FAIL), 40% has_cond (FAIL) → 0/2 = 0%
            _make_scored_results(9, 9),   # 90% in_range (PASS), 90% has_cond (PASS) → 2/2 = 100%
        ]
        replay_call_count = [0]

        mock_engine = MagicMock()
        def mock_replay_batch(*args, **kwargs):
            idx = replay_call_count[0]
            replay_call_count[0] += 1
            return iter_results[idx]
        mock_engine.replay_batch.side_effect = mock_replay_batch

        mock_swapper = MagicMock()
        mock_swapper.load_replacement.return_value = ("test_mod", "initial content here")
        swap_contents = []
        def mock_swap(prompt, name, content):
            swap_contents.append(content)
            return f"swapped:{content}"
        mock_swapper.swap_module.side_effect = mock_swap

        mock_extractor = MagicMock()
        mock_extractor.extract_cases.return_value = [
            _make_eval_case(case_id=f"c{i}") for i in range(10)
        ]

        best_path = judge.run(
            initial_module_path="dummy.yaml",
            module_swapper=mock_swapper,
            session_extractor=mock_extractor,
            replay_engine=mock_engine,
            scorers=[SuppressionTableScorer()],
            model_specs=[("openai", "gpt-5-mini")],
            output_dir=str(tmp_dir / "output"),
        )

        # After iteration 2 regressed (0% < 50%), rollback should have occurred.
        # The second judge call should receive the best content ("initial content here"),
        # NOT "rewrite_1" (which caused the regression).
        assert len(judge_prompt_contents) >= 2
        assert "initial content here" in judge_prompt_contents[1]

        # The final module should contain the best content (rewrite_2, used in iter 3 which scored 100%)
        with open(best_path) as f:
            final_content = f.read()
        assert "rewrite_2" in final_content

    def test_convergence_checks_against_best(self, tmp_dir):
        """Oscillating scores should not trigger premature convergence."""
        goal_file = tmp_dir / "goals.yaml"
        with open(goal_file, "w") as f:
            yaml.dump({
                "description": "Test convergence",
                "max_iterations": 5,
                "eval_subset": {"action_type": "combat", "max_cases": 10},
                "targets": {
                    "suppression_table": {
                        "in_range_pct": 95,  # Very high, never met
                        "has_condition_pct": 60,
                    },
                },
                "convergence": {"min_improvement": 2},
            }, f)

        judge = SelfJudge(str(goal_file), max_iterations=5)

        call_count = [0]
        def mock_call_judge(prompt):
            call_count[0] += 1
            return f"rewrite_{call_count[0]}" * 50
        judge.call_judge = mock_call_judge

        # Scores: 50% → 0% → 50% → 0% → 50%
        # Large oscillation between consecutive iterations prevents convergence
        iter_results = [
            _make_scored_results(7, 8),   # 50%
            _make_scored_results(3, 4),   # 0%
            _make_scored_results(7, 8),   # 50%
            _make_scored_results(3, 4),   # 0%
            _make_scored_results(7, 8),   # 50%
        ]
        replay_idx = [0]

        mock_engine = MagicMock()
        def mock_replay_batch(*args, **kwargs):
            idx = replay_idx[0]
            replay_idx[0] += 1
            return iter_results[idx]
        mock_engine.replay_batch.side_effect = mock_replay_batch

        mock_swapper = MagicMock()
        mock_swapper.load_replacement.return_value = ("test_mod", "initial content")
        mock_swapper.swap_module.side_effect = lambda p, n, c: f"swapped:{c}"

        mock_extractor = MagicMock()
        mock_extractor.extract_cases.return_value = [
            _make_eval_case(case_id=f"c{i}") for i in range(10)
        ]

        judge.run(
            initial_module_path="dummy.yaml",
            module_swapper=mock_swapper,
            session_extractor=mock_extractor,
            replay_engine=mock_engine,
            scorers=[SuppressionTableScorer()],
            model_specs=[("openai", "gpt-5-mini")],
            output_dir=str(tmp_dir / "output"),
        )

        # All 5 iterations should run (oscillation prevents convergence)
        assert mock_engine.replay_batch.call_count == 5

    def test_two_phase_runs_validation(self, tmp_dir):
        """Goal with validation config triggers Phase 2 with all cases."""
        goal_file = tmp_dir / "goals.yaml"
        with open(goal_file, "w") as f:
            yaml.dump({
                "description": "Test two-phase",
                "max_iterations": 1,
                "eval_subset": {"action_type": "combat", "max_cases": 5},
                "targets": {
                    "suppression_table": {"in_range_pct": 80},
                },
                "validation": {"use_all_cases": True},
            }, f)

        judge = SelfJudge(str(goal_file), max_iterations=1)
        judge.call_judge = lambda prompt: "rewritten content " * 20

        # Phase 1 results (subset)
        phase1_results = _make_scored_results(4, 4, n_total=5)
        # Phase 2 results (validation, all cases)
        phase2_results = _make_scored_results(8, 8, n_total=10)

        replay_idx = [0]
        mock_engine = MagicMock()
        def mock_replay_batch(*args, **kwargs):
            idx = replay_idx[0]
            replay_idx[0] += 1
            if idx == 0:
                return phase1_results
            else:
                return phase2_results
        mock_engine.replay_batch.side_effect = mock_replay_batch

        mock_swapper = MagicMock()
        mock_swapper.load_replacement.return_value = ("test_mod", "initial content")
        mock_swapper.swap_module.side_effect = lambda p, n, c: f"swapped:{c}"

        # extract_cases called twice: once for subset (max_cases=5), once for validation (no limit)
        mock_extractor = MagicMock()
        mock_extractor.extract_cases.side_effect = [
            [_make_eval_case(case_id=f"c{i}") for i in range(5)],   # Phase 1 subset
            [_make_eval_case(case_id=f"v{i}") for i in range(10)],  # Phase 2 all cases
        ]

        judge.run(
            initial_module_path="dummy.yaml",
            module_swapper=mock_swapper,
            session_extractor=mock_extractor,
            replay_engine=mock_engine,
            scorers=[SuppressionTableScorer()],
            model_specs=[("openai", "gpt-5-mini")],
            output_dir=str(tmp_dir / "output"),
        )

        # Phase 2 replay should have been called
        assert mock_engine.replay_batch.call_count == 2  # Phase 1 + Phase 2

        # Validation artifacts should exist
        output_path = tmp_dir / "output"
        assert (output_path / "validation_results.jsonl").exists()
        assert (output_path / "validation_report.txt").exists()

    def test_two_phase_skipped_without_config(self, tmp_dir):
        """Goal without validation key skips Phase 2."""
        goal_file = tmp_dir / "goals.yaml"
        with open(goal_file, "w") as f:
            yaml.dump({
                "description": "Test no validation",
                "max_iterations": 1,
                "eval_subset": {"action_type": "combat", "max_cases": 5},
                "targets": {
                    "suppression_table": {"in_range_pct": 80},
                },
                # No "validation" key
            }, f)

        judge = SelfJudge(str(goal_file), max_iterations=1)
        judge.call_judge = lambda prompt: "rewritten content " * 20

        mock_engine = MagicMock()
        mock_engine.replay_batch.return_value = _make_scored_results(4, 4, n_total=5)

        mock_swapper = MagicMock()
        mock_swapper.load_replacement.return_value = ("test_mod", "initial content")
        mock_swapper.swap_module.side_effect = lambda p, n, c: f"swapped:{c}"

        mock_extractor = MagicMock()
        mock_extractor.extract_cases.return_value = [
            _make_eval_case(case_id=f"c{i}") for i in range(5)
        ]

        judge.run(
            initial_module_path="dummy.yaml",
            module_swapper=mock_swapper,
            session_extractor=mock_extractor,
            replay_engine=mock_engine,
            scorers=[SuppressionTableScorer()],
            model_specs=[("openai", "gpt-5-mini")],
            output_dir=str(tmp_dir / "output"),
        )

        # Only Phase 1 replay, no Phase 2
        assert mock_engine.replay_batch.call_count == 1

        # No validation artifacts
        output_path = tmp_dir / "output"
        assert not (output_path / "validation_results.jsonl").exists()
        assert not (output_path / "validation_report.txt").exists()
