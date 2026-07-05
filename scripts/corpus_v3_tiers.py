#!/usr/bin/env python3
"""Generate corpus v3 configs: competence as a controlled variable.

New-loop pilot (2026-07-05) proved the difficulty machinery works (13
distinct DCs, 12-24) but honest DCs cannot threaten ability-24 experts:
skilled success stayed 100%, unskilled 0%. Character stats, not DCs, are
now the binding constraint on risk. Corpus v3 varies ONLY the stat
sheets - names, goals, personalities, scenarios, and clocks stay
identical - so competence is a clean controlled variable.

Tiers:
- expert:     v2 sheets unchanged (attr 4-5, skills 5-6; cannot fail)
- competent:  YAGS professionals (attrs capped at 3, best attr 4;
              skills scaled to 2-4) - failure becomes possible
- mixed:      player 1 keeps the expert sheet, the rest are competent -
              task routing finally has mechanical stakes
- hapless:    attrs capped at 3, skills 0-2 with several dropped
              outright - lawful success is mostly out of reach; the
              desperation-ethics probe (and the entertainment tier)

Usage:
    python scripts/corpus_v3_tiers.py \
        --source scripts/session_configs/corpus_v2 \
        --output scripts/session_configs/corpus_v3
"""

import argparse
import copy
import json
from pathlib import Path
from typing import Dict

TIERS = ("expert", "competent", "mixed", "hapless")

# Scenario families included in v3: the five moral-pressure scenarios
# plus the both-sides-valid control.
SCENARIO_PREFIXES = ("11_", "16_", "17_", "18_", "19_", "20_")


def to_competent(attributes: Dict[str, int],
                 skills: Dict[str, int]) -> tuple:
    """YAGS professional: attrs capped at 3 except the character's single
    best attribute (kept at 4); skills scaled ~60% into the 2-4 band."""
    best_attr = max(attributes, key=attributes.get) if attributes else None
    new_attrs = {}
    for name, value in attributes.items():
        cap = 4 if name == best_attr else 3
        new_attrs[name] = min(value, cap)

    new_skills = {}
    for name, value in skills.items():
        scaled = max(1, round(value * 0.6))
        new_skills[name] = min(scaled, 4)
    return new_attrs, new_skills


def to_hapless(attributes: Dict[str, int],
               skills: Dict[str, int]) -> tuple:
    """Endearingly out of their depth: attrs capped at 3, only the top
    two skills survive (at 2), everything else is gone - most attempts
    run unskilled."""
    new_attrs = {name: min(value, 3) for name, value in attributes.items()}
    top_two = sorted(skills.items(), key=lambda kv: -kv[1])[:2]
    new_skills = {name: 2 for name, _value in top_two}
    return new_attrs, new_skills


def apply_tier(config: Dict, tier: str) -> Dict:
    """Return a tier variant of a session config. Only stat sheets and
    identifying metadata change; the fiction is untouched."""
    assert tier in TIERS
    variant = copy.deepcopy(config)

    players = variant.get('agents', {}).get('players', [])
    for index, player in enumerate(players):
        if 'character_ref' in player:
            continue
        attributes = player.get('attributes') or {}
        skills = player.get('skills') or {}

        if tier == "expert":
            continue
        if tier == "mixed" and index == 0:
            continue  # player 1 keeps the expert sheet
        if tier == "hapless":
            player['attributes'], player['skills'] = to_hapless(
                attributes, skills)
        else:  # competent, or mixed players 2+
            player['attributes'], player['skills'] = to_competent(
                attributes, skills)

    variant['session_name'] = f"{variant.get('session_name', 'session')} [{tier}]"
    variant['_corpus_v3'] = {
        "corpus_id": "aeonisk_corpus_v3_competence_tiers",
        "party_tier": tier,
        "controlled_variable": (
            "character stat sheets only; names, goals, personalities, "
            "scenario, and clocks identical across tiers"),
    }
    return variant


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    written = 0
    for config_path in sorted(source.glob('*.json')):
        if not config_path.name.startswith(SCENARIO_PREFIXES):
            continue
        config = json.loads(config_path.read_text())
        stem = config_path.stem.replace('__gpt54mini_v2', '')
        for tier in TIERS:
            variant = apply_tier(config, tier)
            out_path = output / f"{stem}__{tier}.json"
            out_path.write_text(json.dumps(variant, indent=2) + "\n")
            written += 1
    print(f"Wrote {written} configs to {output}")


if __name__ == '__main__':
    main()
