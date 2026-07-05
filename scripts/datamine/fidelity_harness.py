"""Render, run-prep, and score rules-fidelity eval items.

Pure functions only — no network. Live sweeps are driven from the CLI by
emitting provider batch files (OpenAI Batch API / Anthropic Message Batches)
or by an external runner; this module renders prompts, parses model
responses, and scores predictions against item targets.

Rule texts are frozen copies: models must be judged against the same rules
the engine and DM operated under when the corpus was generated, even if the
live prompts evolve later.
"""

import json
import re
from typing import Any, Dict, Iterable, List, Optional

# --- Frozen rule texts ------------------------------------------------------

# Mirror of mechanics.py resolve_action / _determine_outcome_tier (v1.3.0)
ROLL_RULES = """\
YAGS Aeonisk v1.3.0 action resolution rules:

1. Skilled check (skill value >= 1):
   ability = attribute value x skill value
   total = ability + d20 + sum of modifiers
2. Unskilled check (skill value 0) on a Standard skill:
   ability = 0
   total = (d20 / 2, rounded down) + sum of modifiers
   A natural 1 or 2 on the d20 is a fumble: automatic critical_failure,
   success = false, regardless of margin.
3. Unskilled check on a Knowledge skill is impossible: total = 0,
   margin = -DC, success = false, tier = critical_failure.
   Knowledge skills: Magic Theory, Ritual Lore, Science, History,
   Area Lore, Void Theory, Debt Law.
4. margin = total - DC. success = (margin >= 0) unless a rule above
   forces failure.
5. Outcome tier from margin:
   margin <= -20: critical_failure
   -19 to -1:     failure
   0 to 4:        marginal
   5 to 9:        moderate
   10 to 14:      good
   15 to 19:      excellent
   20 or more:    exceptional"""

DAMAGE_RULES = """\
Damage resolution: damage dealt = base damage - soak, minimum 0."""

# Frozen from prompts/claude/en/dm/dm_state_tracking.yaml (the guidance the
# DM adjudicated the corpus under). Soulcredit is scored from the Sovereign
# Nexus perspective — the setting's codified legal-moral framework.
from aeonisk.multiagent.nexus_law import OPERATIONAL_RUBRIC as NEXUS_LAW  # noqa: E402
# The law is rendered from content/supplemental/NEXUS_LAW.md via
# aeonisk.multiagent.nexus_law - one statute, every court.


# --- Rendering --------------------------------------------------------------

def _render_roll(item: Dict[str, Any]) -> Dict[str, str]:
    inputs = item["inputs"]
    modifiers = inputs.get("modifier_total") or 0
    system = (
        "You are the mechanical rules engine for the Aeonisk YAGS tabletop "
        "system. Apply the rules exactly as written and answer with JSON "
        "only.\n\n" + ROLL_RULES
    )
    user = (
        f"Character: {inputs.get('agent')}\n"
        f"Declared action: {inputs.get('action')}\n"
        f"Action type: {inputs.get('action_type')}\n\n"
        f"Roll: {inputs.get('attribute')} {inputs.get('attribute_value')} x "
        f"{inputs.get('skill')} {inputs.get('skill_value')}\n"
        f"d20 result: {inputs.get('d20')}\n"
        f"Modifier total: {modifiers:+d}\n"
        f"DC: {inputs.get('dc')}\n\n"
        "Resolve this action. Respond with a single JSON object and nothing "
        "else:\n"
        '{"ability": <int>, "total": <int>, "margin": <int>, '
        '"success": <bool>, "tier": "<tier>"}'
    )
    return {"system": system, "user": user}


def _render_damage(item: Dict[str, Any]) -> Dict[str, str]:
    inputs = item["inputs"]
    system = (
        "You are the mechanical rules engine for the Aeonisk YAGS tabletop "
        "system. Apply the rules exactly as written and answer with JSON "
        "only.\n\n" + DAMAGE_RULES
    )
    user = (
        f"An attack hits for base damage {inputs.get('base_damage')} "
        f"({inputs.get('damage_type')}). The target's soak is "
        f"{inputs.get('soak')}.\n\n"
        "How much damage is dealt? Respond with a single JSON object and "
        'nothing else:\n{"dealt": <int>}'
    )
    return {"system": system, "user": user}


def _render_soulcredit(item: Dict[str, Any]) -> Dict[str, str]:
    inputs = item["inputs"]
    outcome = inputs.get("outcome") or {}
    system = (
        "You are the adjudicator of the Sovereign Nexus soulcredit ledger "
        "in the world of Aeonisk. Judge the action below strictly according "
        "to the codified framework and answer with JSON only.\n\n"
        + NEXUS_LAW
    )
    user = (
        f"Actor: {inputs.get('agent')} (faction: {inputs.get('faction')})\n"
        f"Declared action: {inputs.get('action')}\n"
        f"Actor's description of intent: {inputs.get('description')}\n"
        f"Action type: {inputs.get('action_type')}"
        f"{' (ritual)' if inputs.get('is_ritual') else ''}\n"
        f"Mechanical outcome: success={outcome.get('success')}, "
        f"tier={outcome.get('tier')}, margin={outcome.get('margin')}\n\n"
        "Adjudicate the soulcredit and void consequences of this action. "
        "Respond with a single JSON object and nothing else:\n"
        '{"soulcredit_delta": <int>, "void_delta": <int>, '
        '"reason": "<brief justification>"}'
    )
    return {"system": system, "user": user}


_RENDERERS = {
    "roll_resolution": _render_roll,
    "damage_soak": _render_damage,
    "soulcredit_adjudication": _render_soulcredit,
}


def render_item(item: Dict[str, Any]) -> Dict[str, str]:
    """Render one eval item to a prompt: {item_id, task, system, user}."""
    renderer = _RENDERERS[item["task"]]
    prompt = renderer(item)
    return {
        "item_id": item["item_id"],
        "task": item["task"],
        "system": prompt["system"],
        "user": prompt["user"],
    }


# --- Response parsing -------------------------------------------------------

def parse_response(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Extract the first valid JSON object from a model response."""
    if not text:
        return None
    # Strip common code fences before scanning
    cleaned = re.sub(r"```(?:json)?", "", text)
    depth = 0
    start = None
    for index, char in enumerate(cleaned):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                candidate = cleaned[start:index + 1]
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
                start = None
    return None


# --- Scoring ----------------------------------------------------------------

_TASK_FIELDS = {
    "roll_resolution": ["ability", "total", "margin", "success", "tier"],
    "damage_soak": ["dealt"],
    "soulcredit_adjudication": ["soulcredit_delta", "void_delta"],
}

_DIRECTION_FIELDS = {
    "soulcredit_adjudication": ["soulcredit_delta", "void_delta"],
}


def _coerce(predicted: Any, target: Any) -> Any:
    """Coerce a predicted value to the target's type for fair comparison."""
    if isinstance(target, bool):
        if isinstance(predicted, bool):
            return predicted
        if isinstance(predicted, str):
            lowered = predicted.strip().lower()
            if lowered in ("true", "yes"):
                return True
            if lowered in ("false", "no"):
                return False
        return predicted
    if isinstance(target, int) and not isinstance(target, bool):
        try:
            return int(predicted)
        except (TypeError, ValueError):
            return predicted
    if isinstance(target, str) and isinstance(predicted, str):
        return predicted.strip().lower()
    return predicted


def _sign(value: Any) -> Optional[int]:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return (value > 0) - (value < 0)


def score_items(
    items: List[Dict[str, Any]],
    predictions: Dict[str, Any],
) -> Dict[str, Any]:
    """Score predictions against item targets.

    predictions maps item_id -> parsed dict (or raw response string,
    which is parsed here). Returns a report with per-task accuracy,
    per-field accuracy, direction accuracy for delta fields, and
    skilled/unskilled + per-tier slices for roll items.
    """
    tasks: Dict[str, Dict[str, Any]] = {}

    for item in items:
        task = item["task"]
        bucket = tasks.setdefault(task, {
            "n": 0, "answered": 0, "missing": 0, "correct": 0,
            "field_correct": {f: 0 for f in _TASK_FIELDS[task]},
            "direction_correct": {f: 0 for f in
                                  _DIRECTION_FIELDS.get(task, [])},
            "_slices": {},
        })
        bucket["n"] += 1

        raw = predictions.get(item["item_id"])
        predicted = parse_response(raw) if isinstance(raw, str) else raw
        all_correct = False
        if predicted is None:
            bucket["missing"] += 1
        else:
            bucket["answered"] += 1
            targets = item["targets"]
            fields_ok = []
            for field_name in _TASK_FIELDS[task]:
                target = targets.get(field_name)
                ok = _coerce(predicted.get(field_name), target) == target
                fields_ok.append(ok)
                if ok:
                    bucket["field_correct"][field_name] += 1
            for field_name in _DIRECTION_FIELDS.get(task, []):
                if _sign(predicted.get(field_name)) == _sign(
                        item["targets"].get(field_name)):
                    bucket["direction_correct"][field_name] += 1
            all_correct = all(fields_ok)
            if all_correct:
                bucket["correct"] += 1

        if task == "roll_resolution":
            skilled = (item["inputs"].get("skill_value") or 0) > 0
            for slice_name in ("skilled" if skilled else "unskilled",
                               f"tier:{item['targets'].get('tier')}"):
                slice_bucket = bucket["_slices"].setdefault(
                    slice_name, {"n": 0, "correct": 0})
                slice_bucket["n"] += 1
                if all_correct:
                    slice_bucket["correct"] += 1

    report: Dict[str, Any] = {"tasks": {}}
    for task, bucket in tasks.items():
        n = bucket["n"]
        answered = bucket["answered"]
        entry: Dict[str, Any] = {
            "n": n,
            "answered": answered,
            "missing": bucket["missing"],
            "all_correct": bucket["correct"] / n if n else 0.0,
            "field_accuracy": {
                f: (c / answered if answered else 0.0)
                for f, c in bucket["field_correct"].items()
            },
        }
        if bucket["direction_correct"]:
            entry["direction_accuracy"] = {
                f: (c / answered if answered else 0.0)
                for f, c in bucket["direction_correct"].items()
            }
        if bucket["_slices"]:
            entry["slices"] = {
                name: {"n": s["n"],
                       "all_correct": s["correct"] / s["n"] if s["n"] else 0.0}
                for name, s in bucket["_slices"].items()
            }
        report["tasks"][task] = entry
    return report


# --- Provider batch files ---------------------------------------------------

def to_openai_batch_line(prompt: Dict[str, str], model: str,
                         max_tokens: int = 300,
                         reasoning_effort: Optional[str] = None) -> Dict[str, Any]:
    """One line of an OpenAI Batch API input file (/v1/chat/completions)."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
        ],
        "max_completion_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    return {
        "custom_id": prompt["item_id"],
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": body,
    }


def to_anthropic_batch_line(prompt: Dict[str, str], model: str,
                            max_tokens: int = 300) -> Dict[str, Any]:
    """One line of an Anthropic Message Batches input file."""
    return {
        "custom_id": prompt["item_id"],
        "params": {
            "model": model,
            "max_tokens": max_tokens,
            "system": prompt["system"],
            "messages": [
                {"role": "user", "content": prompt["user"]},
            ],
        },
    }


def responses_from_openai_batch(
        lines: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    """Map custom_id -> content from OpenAI batch output lines."""
    responses: Dict[str, str] = {}
    for line in lines:
        response = line.get("response") or {}
        if response.get("status_code") != 200:
            continue
        try:
            content = response["body"]["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            continue
        responses[line["custom_id"]] = content
    return responses


def responses_from_anthropic_batch(
        lines: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    """Map custom_id -> text from Anthropic message batch result lines."""
    responses: Dict[str, str] = {}
    for line in lines:
        result = line.get("result") or {}
        if result.get("type") != "succeeded":
            continue
        blocks = (result.get("message") or {}).get("content") or []
        text = "".join(b.get("text", "") for b in blocks
                       if b.get("type") == "text")
        if text:
            responses[line["custom_id"]] = text
    return responses


# --- Cost estimation --------------------------------------------------------

def _count_tokens(text: str) -> int:
    try:
        from token_utils import count_text_tokens
        return count_text_tokens(text)
    except ImportError:
        return max(1, len(text) // 4)


def estimate_run(prompts: List[Dict[str, str]], model: str,
                 pricing: Dict[str, Dict[str, float]],
                 max_output_tokens: int = 200) -> Dict[str, Any]:
    """Estimate token usage and cost for one model over rendered prompts."""
    input_tokens = sum(
        _count_tokens(p["system"]) + _count_tokens(p["user"])
        for p in prompts
    )
    output_tokens = len(prompts) * max_output_tokens
    rates = pricing.get(model) or {}
    cost = (
        input_tokens * rates.get("input_per_1m", 0.0)
        + output_tokens * rates.get("output_per_1m", 0.0)
    ) / 1_000_000
    return {
        "model": model,
        "n_prompts": len(prompts),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 4),
    }
