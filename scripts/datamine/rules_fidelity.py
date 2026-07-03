"""Extract rules-fidelity eval items from session JSONL logs.

Each item pairs the inputs a model would see (character stats, declared
action, dice) with ground truth. Two verifier classes:

- "deterministic": targets recomputed from YAGS Aeonisk v1.3.0 resolution
  rules (mirror of mechanics.py resolve_action / _determine_outcome_tier).
  Logged events that disagree with the mirror are quarantined, never emitted.
- "canonical": DM-adjudicated targets (soulcredit/void deltas) that have no
  closed-form answer; ground truth is the ruling the game engine accepted.

Tasks:
- roll_resolution: attr/skill/d20/DC -> ability, total, margin, success, tier
- damage_soak: base_damage/soak -> dealt
- soulcredit_adjudication: action + outcome -> soulcredit/void deltas + reasons
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

ALL_TASKS = {"roll_resolution", "damage_soak", "soulcredit_adjudication"}

# Knowledge skills cannot be attempted untrained (auto critical failure).
# Kept in sync with skill_descriptions.SKILL_DATABASE via is_knowledge_skill
# when the aeonisk package is importable; this list is the fallback.
_KNOWLEDGE_SKILLS_FALLBACK = {
    "Magic Theory", "Ritual Lore", "Science", "History", "Area Lore",
    "Void Theory", "Debt Law",
}


def _is_knowledge_skill(skill: Optional[str]) -> bool:
    try:
        from aeonisk.multiagent.mechanics import is_knowledge_skill
        return is_knowledge_skill(skill)
    except ImportError:
        return skill in _KNOWLEDGE_SKILLS_FALLBACK


def determine_tier(margin: int) -> str:
    """Mirror of mechanics.MechanicsEngine._determine_outcome_tier."""
    if margin <= -20:
        return "critical_failure"
    elif margin < 0:
        return "failure"
    elif margin < 5:
        return "marginal"
    elif margin < 10:
        return "moderate"
    elif margin < 15:
        return "good"
    elif margin < 20:
        return "excellent"
    else:
        return "exceptional"


def derive_roll_targets(
    attribute_value: int,
    skill_value: int,
    d20: int,
    dc: int,
    modifier_total: int = 0,
    skill: Optional[str] = None,
) -> Dict[str, Any]:
    """Recompute resolution targets from first principles.

    Mirror of mechanics.MechanicsEngine.resolve_action:
    - skilled (skill_value > 0): total = attr*skill + d20 + modifiers
    - unskilled standard skill: total = d20 // 2 + modifiers; natural 1-2 fumbles
    - unskilled Knowledge skill: automatic critical failure, total 0
    """
    if skill_value > 0:
        ability = attribute_value * skill_value
        total = ability + d20 + modifier_total
        margin = total - dc
        success = margin >= 0
        tier = determine_tier(margin)
    elif _is_knowledge_skill(skill):
        ability = 0
        total = 0
        margin = -dc
        success = False
        tier = "critical_failure"
    else:
        ability = 0
        total = d20 // 2 + modifier_total
        margin = total - dc
        if d20 <= 2:  # unskilled fumble
            success = False
            tier = "critical_failure"
        else:
            success = margin >= 0
            tier = determine_tier(margin)

    return {
        "ability": ability,
        "total": total,
        "margin": margin,
        "success": success,
        "tier": tier,
    }


@dataclass
class ExtractionResult:
    items: List[Dict[str, Any]] = field(default_factory=list)
    quarantined: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


def _source(event: Dict[str, Any], source_file: Optional[str],
            event_index: int) -> Dict[str, Any]:
    return {
        "session": event.get("session"),
        "file": source_file,
        "event_index": event_index,
        "round": event.get("round"),
        "ts": event.get("ts"),
        "agent": event.get("agent"),
    }


def _item_id(event: Dict[str, Any], event_index: int, suffix: str) -> str:
    session = (event.get("session") or "unknown")[:8]
    return f"{session}-r{event.get('round')}-e{event_index}-{suffix}"


def _extract_roll(event: Dict[str, Any], source_file: Optional[str],
                  event_index: int, result: ExtractionResult) -> None:
    roll = event.get("roll") or {}
    if roll.get("d20") is None or roll.get("dc") is None:
        return  # enemy fixed-behavior actions log null rolls

    modifier_total = roll.get("modifier_total") or 0
    derived = derive_roll_targets(
        attribute_value=roll.get("attr_val") or 0,
        skill_value=roll.get("skill_val") or 0,
        d20=roll["d20"],
        dc=roll["dc"],
        modifier_total=modifier_total,
        skill=roll.get("skill"),
    )

    logged = {
        "ability": roll.get("ability"),
        "total": roll.get("total"),
        "margin": roll.get("margin"),
        "success": roll.get("success"),
        "tier": roll.get("tier"),
    }
    mismatched = [
        key for key, value in logged.items()
        if value is not None and value != derived[key]
    ]
    if mismatched:
        result.quarantined.append({
            "item_id": _item_id(event, event_index, "roll"),
            "task": "roll_resolution",
            "mismatched_fields": mismatched,
            "logged": logged,
            "derived": derived,
            "source": _source(event, source_file, event_index),
        })
        return

    context = event.get("context") or {}
    result.items.append({
        "item_id": _item_id(event, event_index, "roll"),
        "task": "roll_resolution",
        "verifier": "deterministic",
        "source": _source(event, source_file, event_index),
        "inputs": {
            "agent": event.get("agent"),
            "action": event.get("action"),
            "action_type": context.get("action_type"),
            "attribute": roll.get("attr"),
            "attribute_value": roll.get("attr_val"),
            "skill": roll.get("skill"),
            "skill_value": roll.get("skill_val"),
            "d20": roll["d20"],
            "modifiers": roll.get("modifiers"),
            "modifier_total": modifier_total,
            "dc": roll["dc"],
        },
        "targets": derived,
    })


def _extract_damage(event: Dict[str, Any], source_file: Optional[str],
                    event_index: int, result: ExtractionResult) -> None:
    context = event.get("context") or {}
    for effect_index, effect in enumerate(context.get("damage_effects") or []):
        base = effect.get("base_damage")
        soak = effect.get("soak")
        dealt = effect.get("dealt")
        if base is None or soak is None or dealt is None:
            continue
        derived_dealt = max(0, base - soak)
        if dealt != derived_dealt:
            result.quarantined.append({
                "item_id": _item_id(event, event_index, f"dmg{effect_index}"),
                "task": "damage_soak",
                "mismatched_fields": ["dealt"],
                "logged": {"dealt": dealt},
                "derived": {"dealt": derived_dealt},
                "source": _source(event, source_file, event_index),
            })
            continue
        result.items.append({
            "item_id": _item_id(event, event_index, f"dmg{effect_index}"),
            "task": "damage_soak",
            "verifier": "deterministic",
            "source": _source(event, source_file, event_index),
            "inputs": {
                "base_damage": base,
                "soak": soak,
                "damage_type": effect.get("damage_type"),
            },
            "targets": {"dealt": dealt},
        })


def _extract_soulcredit(event: Dict[str, Any], source_file: Optional[str],
                        event_index: int, result: ExtractionResult) -> None:
    economy = event.get("economy")
    if not economy:
        return
    roll = event.get("roll") or {}
    context = event.get("context") or {}
    result.items.append({
        "item_id": _item_id(event, event_index, "soul"),
        "task": "soulcredit_adjudication",
        "verifier": "canonical",
        "source": _source(event, source_file, event_index),
        "inputs": {
            "agent": event.get("agent"),
            "faction": context.get("faction"),
            "action": event.get("action"),
            "description": context.get("description"),
            "action_type": context.get("action_type"),
            "is_ritual": context.get("is_ritual"),
            "outcome": {
                "success": roll.get("success"),
                "tier": roll.get("tier"),
                "margin": roll.get("margin"),
            },
        },
        "targets": {
            "soulcredit_delta": economy.get("soulcredit_delta", 0),
            "void_delta": economy.get("void_delta", 0),
            "soulcredit_reasons": economy.get("soulcredit_reasons") or [],
            "void_triggers": economy.get("void_triggers") or [],
        },
    })


def extract_items(
    events: Iterable[Dict[str, Any]],
    source_file: Optional[str] = None,
    tasks: Optional[Set[str]] = None,
) -> ExtractionResult:
    """Walk parsed JSONL events and produce eval items + quarantine list."""
    tasks = tasks or ALL_TASKS
    result = ExtractionResult()
    resolutions = 0
    for event_index, event in enumerate(events):
        if event.get("event_type") != "action_resolution":
            continue
        resolutions += 1
        if "roll_resolution" in tasks:
            _extract_roll(event, source_file, event_index, result)
        if "damage_soak" in tasks:
            _extract_damage(event, source_file, event_index, result)
        if "soulcredit_adjudication" in tasks:
            _extract_soulcredit(event, source_file, event_index, result)

    by_task: Dict[str, int] = {}
    for item in result.items:
        by_task[item["task"]] = by_task.get(item["task"], 0) + 1
    nonzero_soul = sum(
        1 for i in result.items
        if i["task"] == "soulcredit_adjudication"
        and (i["targets"]["soulcredit_delta"] or i["targets"]["void_delta"])
    )
    result.stats = {
        "resolutions_seen": resolutions,
        "items": len(result.items),
        "items_by_task": by_task,
        "quarantined": len(result.quarantined),
        "soulcredit_items_with_nonzero_delta": nonzero_soul,
    }
    return result


def extract_from_file(path, tasks: Optional[Set[str]] = None) -> ExtractionResult:
    path = Path(path)
    events = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return extract_items(events, source_file=path.name, tasks=tasks)


def write_items(items: List[Dict[str, Any]], output_path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
