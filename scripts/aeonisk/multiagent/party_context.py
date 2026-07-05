"""Party context rendering: teammate capabilities and party chatter.

Corpus v2 (2026-07-04) showed why agents mimic instead of coordinating:
player prompts contained teammates' names and declared words but zero
capability information ("coordinate with allies who have better skills"
was advice the context made unanswerable), and party-directed ambient
speech - the channel that replaced free actions in f48dfb7 - drowned in
the 20-entry narration buffer and was framed as decorative.

These helpers are pure functions so the rendered blocks are unit-testable
(content-guard pattern: prompt plumbing fails silently otherwise).
"""

from typing import Any, Dict, List, Optional, Tuple

TOP_SKILLS_SHOWN = 4


def render_party_capabilities(own_agent_id: str, player_agents: List[Any]) -> str:
    """Render teammates' capabilities for task routing.

    One line per OTHER player character: faction, top skills by value,
    strongest attribute. PC-only by construction (callers pass
    shared_state.player_agents; enemies and NPCs never appear here).
    Returns "" when there are no renderable teammates.
    """
    lines = []
    for agent in player_agents or []:
        if getattr(agent, 'agent_id', None) == own_agent_id:
            continue
        state = getattr(agent, 'character_state', None)
        if state is None:
            continue
        skills = getattr(state, 'skills', None) or {}
        attributes = getattr(state, 'attributes', None) or {}

        top_skills = sorted(skills.items(), key=lambda kv: -kv[1])[:TOP_SKILLS_SHOWN]
        skills_text = ", ".join(f"{name} {value}" for name, value in top_skills)
        best_attr = max(attributes.items(), key=lambda kv: kv[1], default=None)
        attr_text = f" | {best_attr[0]} {best_attr[1]}" if best_attr else ""

        lines.append(f"- {state.name} ({getattr(state, 'faction', '?')}): "
                     f"{skills_text}{attr_text}")

    if not lines:
        return ""
    return ("**Your crew (capabilities - route tasks to whoever is best "
            "equipped; unskilled attempts fail):**\n" + "\n".join(lines))


def is_party_chatter(ambient_speech: Optional[Dict[str, Any]]) -> bool:
    """True if an ambient_speech dict is party-directed communication:
    aimed at the party, or delivered over comms."""
    if not isinstance(ambient_speech, dict):
        return False
    if not (ambient_speech.get('line') or '').strip():
        return False
    return (ambient_speech.get('target_type') == 'party'
            or ambient_speech.get('delivery') == 'comms')


def render_party_chatter(last_round: List[Tuple[str, str]],
                         this_round: List[Tuple[str, str]]) -> str:
    """Render the dedicated party-chatter block.

    this_round entries were spoken by slower teammates earlier in the
    current declaration phase - the telegraphing design extended to
    speech, so faster declarers can act on them immediately.
    """
    if not last_round and not this_round:
        return ""
    lines = ["**Party chatter:**"]
    for speaker, line in last_round:
        lines.append(f'- [last round] {speaker}: "{line}"')
    for speaker, line in this_round:
        lines.append(f'- [just now] {speaker}: "{line}"')
    return "\n".join(lines)
