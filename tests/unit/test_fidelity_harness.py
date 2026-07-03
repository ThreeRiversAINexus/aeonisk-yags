"""Tests for the rules-fidelity eval harness (datamine.fidelity_harness).

The harness turns extracted eval items into model prompts, parses model
responses, and scores predictions against ground truth. All pure — live
API calls live outside these tests.
"""

import json
import sys
from pathlib import Path

import pytest

scripts_dir = Path(__file__).parent.parent.parent / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from datamine.fidelity_harness import (
    render_item,
    parse_response,
    score_items,
    to_openai_batch_line,
    to_anthropic_batch_line,
    responses_from_openai_batch,
    responses_from_anthropic_batch,
    estimate_run,
)


def roll_item(**target_overrides):
    targets = {"ability": 20, "total": 28, "margin": 10,
               "success": True, "tier": "good"}
    targets.update(target_overrides)
    return {
        "item_id": "abc-r1-e5-roll",
        "task": "roll_resolution",
        "verifier": "deterministic",
        "source": {"session": "abc", "round": 1},
        "inputs": {
            "agent": "Enforcer Kael Dren",
            "action": "Stun the nearest thug",
            "action_type": "combat",
            "attribute": "Agility", "attribute_value": 4,
            "skill": "Combat", "skill_value": 5,
            "d20": 8, "modifiers": None, "modifier_total": 0, "dc": 18,
        },
        "targets": targets,
    }


def soul_item():
    return {
        "item_id": "abc-r1-e5-soul",
        "task": "soulcredit_adjudication",
        "verifier": "canonical",
        "source": {"session": "abc", "round": 1},
        "inputs": {
            "agent": "Enforcer Kael Dren",
            "faction": "Pantheon Security",
            "action": "Intimidate raiders into surrender",
            "description": "Shield the dock worker while demanding surrender.",
            "action_type": "social",
            "is_ritual": False,
            "outcome": {"success": True, "tier": "excellent", "margin": 16},
        },
        "targets": {"soulcredit_delta": 1, "void_delta": 0,
                    "soulcredit_reasons": ["enforced lawful surrender"],
                    "void_triggers": []},
    }


def damage_item():
    return {
        "item_id": "abc-r1-e5-dmg0",
        "task": "damage_soak",
        "verifier": "deterministic",
        "source": {"session": "abc", "round": 1},
        "inputs": {"base_damage": 15, "soak": 3, "damage_type": "wound"},
        "targets": {"dealt": 12},
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

class TestRenderItem:
    def test_roll_prompt_contains_inputs_and_rules(self):
        prompt = render_item(roll_item())
        assert prompt["item_id"] == "abc-r1-e5-roll"
        text = prompt["system"] + prompt["user"]
        # The model must see the stats and dice, and the rules to apply
        for needle in ("Agility", "4", "Combat", "5", "8", "18",
                       "d20", "JSON"):
            assert needle in text
        # Rules text covers the edge cases
        assert "unskilled" in text.lower()
        assert "knowledge" in text.lower()
        # Never leak the answer
        assert "\"total\": 28" not in text
        assert "margin" in prompt["user"] or "margin" in prompt["system"]

    def test_soulcredit_prompt_contains_nexus_law(self):
        prompt = render_item(soul_item())
        text = prompt["system"] + prompt["user"]
        assert "Sovereign Nexus" in text
        assert "Intimidate raiders" in text
        # Outcome context is provided (adjudication happens post-roll)
        assert "excellent" in text
        # Never leak the adjudicated delta
        assert "enforced lawful surrender" not in text

    def test_damage_prompt(self):
        prompt = render_item(damage_item())
        text = prompt["system"] + prompt["user"]
        assert "15" in text and "3" in text
        assert "soak" in text.lower()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_parses_clean_json(self):
        out = parse_response('{"total": 28, "margin": 10, "success": true, '
                             '"tier": "good", "ability": 20}')
        assert out["total"] == 28
        assert out["success"] is True

    def test_parses_json_in_prose_and_fences(self):
        text = ('Sure! Here is my answer:\n```json\n'
                '{"total": 28, "margin": 10}\n```\nHope that helps.')
        out = parse_response(text)
        assert out == {"total": 28, "margin": 10}

    def test_returns_none_on_garbage(self):
        assert parse_response("I cannot compute that.") is None
        assert parse_response("") is None
        assert parse_response(None) is None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestScoreItems:
    def test_perfect_roll_prediction(self):
        item = roll_item()
        report = score_items(
            [item],
            {"abc-r1-e5-roll": {"ability": 20, "total": 28, "margin": 10,
                                "success": True, "tier": "good"}},
        )
        roll = report["tasks"]["roll_resolution"]
        assert roll["n"] == 1
        assert roll["all_correct"] == 1.0
        assert roll["field_accuracy"]["total"] == 1.0
        assert roll["field_accuracy"]["tier"] == 1.0

    def test_partial_roll_prediction(self):
        item = roll_item()
        report = score_items(
            [item],
            {"abc-r1-e5-roll": {"ability": 20, "total": 28, "margin": 10,
                                "success": True, "tier": "excellent"}},
        )
        roll = report["tasks"]["roll_resolution"]
        assert roll["all_correct"] == 0.0
        assert roll["field_accuracy"]["total"] == 1.0
        assert roll["field_accuracy"]["tier"] == 0.0

    def test_missing_and_unparseable_counted(self):
        report = score_items([roll_item()], {})
        roll = report["tasks"]["roll_resolution"]
        assert roll["missing"] == 1
        assert roll["all_correct"] == 0.0

    def test_soulcredit_scoring_exact_and_direction(self):
        item = soul_item()
        report = score_items(
            [item], {"abc-r1-e5-soul": {"soulcredit_delta": 2, "void_delta": 0}})
        soul = report["tasks"]["soulcredit_adjudication"]
        assert soul["field_accuracy"]["soulcredit_delta"] == 0.0
        assert soul["direction_accuracy"]["soulcredit_delta"] == 1.0  # sign +
        assert soul["field_accuracy"]["void_delta"] == 1.0

    def test_roll_slices_by_skilled(self):
        skilled = roll_item()
        unskilled = roll_item(ability=0, total=7, margin=-11,
                              success=False, tier="failure")
        unskilled["item_id"] = "abc-r1-e6-roll"
        unskilled["inputs"]["skill_value"] = 0
        unskilled["inputs"]["d20"] = 15
        report = score_items(
            [skilled, unskilled],
            {
                "abc-r1-e5-roll": {"ability": 20, "total": 28, "margin": 10,
                                   "success": True, "tier": "good"},
                "abc-r1-e6-roll": {"ability": 0, "total": 15, "margin": -3,
                                   "success": False, "tier": "failure"},
            },
        )
        slices = report["tasks"]["roll_resolution"]["slices"]
        assert slices["skilled"]["all_correct"] == 1.0
        assert slices["unskilled"]["all_correct"] == 0.0  # halving missed

    def test_boolean_string_coercion(self):
        # Models sometimes answer "true"/"TRUE" instead of JSON booleans
        item = roll_item()
        report = score_items(
            [item],
            {"abc-r1-e5-roll": {"ability": "20", "total": 28, "margin": 10,
                                "success": "true", "tier": "Good"}},
        )
        roll = report["tasks"]["roll_resolution"]
        assert roll["all_correct"] == 1.0


# ---------------------------------------------------------------------------
# Batch-file emit + response ingestion
# ---------------------------------------------------------------------------

class TestBatchFiles:
    def test_openai_batch_line(self):
        prompt = render_item(roll_item())
        line = to_openai_batch_line(prompt, model="gpt-5-mini",
                                    max_tokens=300)
        assert line["custom_id"] == "abc-r1-e5-roll"
        assert line["url"] == "/v1/chat/completions"
        body = line["body"]
        assert body["model"] == "gpt-5-mini"
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][1]["role"] == "user"

    def test_anthropic_batch_line(self):
        prompt = render_item(roll_item())
        line = to_anthropic_batch_line(prompt, model="claude-haiku-4-5-20251001",
                                       max_tokens=300)
        assert line["custom_id"] == "abc-r1-e5-roll"
        params = line["params"]
        assert params["system"]
        assert params["messages"][0]["role"] == "user"

    def test_openai_batch_response_ingestion(self):
        raw = {
            "custom_id": "abc-r1-e5-roll",
            "response": {"status_code": 200, "body": {"choices": [
                {"message": {"content": '{"total": 28}'}}]}},
        }
        responses = responses_from_openai_batch([raw])
        assert responses == {"abc-r1-e5-roll": '{"total": 28}'}

    def test_anthropic_batch_response_ingestion(self):
        raw = {
            "custom_id": "abc-r1-e5-roll",
            "result": {"type": "succeeded", "message": {
                "content": [{"type": "text", "text": '{"total": 28}'}]}},
        }
        responses = responses_from_anthropic_batch([raw])
        assert responses == {"abc-r1-e5-roll": '{"total": 28}'}


class TestEstimateRun:
    def test_estimates_tokens_and_cost(self):
        prompts = [render_item(roll_item()), render_item(soul_item())]
        pricing = {"gpt-5-mini": {"input_per_1m": 0.25, "output_per_1m": 2.0}}
        est = estimate_run(prompts, model="gpt-5-mini", pricing=pricing,
                           max_output_tokens=200)
        assert est["n_prompts"] == 2
        assert est["input_tokens"] > 100
        assert est["output_tokens"] == 400
        assert est["cost_usd"] > 0
        assert est["cost_usd"] < 1.0
