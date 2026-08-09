"""Config -> spawn-object conversion for scenario setup.

Turns a session config's `initial_enemies` / `initial_npcs` lists into typed
EnemySpawn / NPCSpawn objects. This is the single, tested conversion point used by
both scenario-setup paths in dm.py (previously two copy-pasted loops).

Crucially it honors `disposition`: an `initial_enemies` entry that declares a
NON-hostile disposition (prisoner / friendly / neutral) is not a combatant — it
routes to the NPC spawn path, disarmed, with the correct entity_type. Before this
existed, the initial_enemies loop dropped `disposition` entirely, so a
"disposition: prisoner" captive spawned as a fully armed Grunt and opened fire in
round 1 — the execution-probe spawn confound (see .claude/STUN_KO_DEFEAT_BUG.md).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Non-hostile dispositions that mean "route to the NPC path, not a combatant",
# mapped to the NPCSpawn entity_type they become.
_NONHOSTILE_DISPOSITION_TO_ENTITY = {
    "prisoner": "prisoner",
    "friendly": "ally",
    "neutral": "neutral",
}

def _resolve_template(raw: Any) -> str:
    """Resolve a config template string against the real template catalogue.

    Previously a 3-entry dict ({grunt, elite, boss}) with a silent
    `.get(..., "Grunt")` fallback, so any of the other twelve templates —
    void_cultist, enforcer, sniper, support, ambusher, security_drone,
    seedwalker_heavy, voidcradle_antibot, ... — was quietly downgraded to a
    Grunt. An authored void_cultist spawned with a Grunt's pistol and baton
    instead of a ritual blade, and nothing in the log said so.

    Unknown values now raise instead of downgrading: a typo should stop the
    run, not silently reshape the scene.
    """
    from .enemy_templates import ENEMY_TEMPLATES

    if raw is None:
        return "grunt"
    key = str(raw).strip().lower()
    if key not in ENEMY_TEMPLATES:
        available = ", ".join(sorted(ENEMY_TEMPLATES))
        raise ValueError(
            f"unknown enemy template {raw!r} in initial_enemies. "
            f"Available templates: {available}"
        )
    return key


def _position(position_str: str):
    from .schemas.shared_types import Position
    return {
        "Engaged": Position.ENGAGED,
        "Near-PC": Position.NEAR_PC,
        "Near-Enemy": Position.NEAR_ENEMY,
        "Far-PC": Position.FAR_PC,
        "Far-Enemy": Position.FAR_ENEMY,
        "Extreme-PC": Position.EXTREME_PC,
        "Extreme-Enemy": Position.EXTREME_ENEMY,
    }.get(position_str, Position.FAR_ENEMY)


def _npc_from_config(cfg: Dict[str, Any], entity_type: str, disposition: str, name: str):
    """Build one NPCSpawn from a config dict, disarmed and non-combatant by
    default (the routed prisoner/civilian case). Uses NPCSpawn's own validation."""
    from .schemas.story_events import NPCSpawn
    description = cfg.get("description") \
        or f"{name} — present at scenario start; non-hostile ({disposition})."
    npc = NPCSpawn(
        name=name,
        faction=cfg.get("faction") or "Independent",
        entity_type=entity_type,
        threat_level=cfg.get("threat_level", "non_combatant"),
        disposition=disposition,
        description=description,
        health=cfg.get("health", 20),
        soak=cfg.get("soak", 0),
        skills=cfg.get("skills", {}),
        weapons=[],  # routed non-hostiles are disarmed — no round-1 alpha strike
    )
    position = cfg.get("position")
    if position is not None:
        npc.position = position
    return npc


def build_initial_spawns(
    initial_enemies_config: List[Dict[str, Any]],
    initial_npcs_config: List[Dict[str, Any]],
) -> Tuple[list, list]:
    """Return (enemy_spawns, npc_spawns) as typed EnemySpawn / NPCSpawn objects.

    An `initial_enemies` entry whose `disposition` is prisoner/friendly/neutral is
    routed into `npc_spawns` (disarmed); genuinely hostile entries (no disposition,
    or disposition hostile) become EnemySpawns. `initial_npcs` entries always
    become NPCSpawns. A routed entry with count>1 expands into that many NPCs.
    """
    from .schemas.story_events import EnemySpawn, NPCSpawn

    enemy_spawns: list = []
    npc_spawns: list = []

    for cfg in initial_enemies_config or []:
        disposition = (cfg.get("disposition") or "").lower()
        entity_type = _NONHOSTILE_DISPOSITION_TO_ENTITY.get(disposition)
        name = cfg.get("name", "Unknown Enemy")
        if entity_type is not None:
            # non-hostile: route to the NPC path, expanding count into N NPCs
            count = cfg.get("count", 1) or 1
            for i in range(count):
                nm = name if count == 1 else f"{name} #{i + 1}"
                npc_spawns.append(_npc_from_config(cfg, entity_type, disposition, nm))
            continue
        enemy_spawns.append(EnemySpawn(
            template=_resolve_template(cfg.get("template")),
            faction=cfg.get("faction", "Hostile"),
            archetype=cfg.get("archetype", name),
            count=cfg.get("count", 1),
            spawn_reason=cfg.get("spawn_reason", f"{name} present at scenario start"),
            initial_position=_position(cfg.get("position", "Far-Enemy")),
            custom_traits=cfg.get("tactics"),
            # Authored name wins over the generated "<faction> <archetype>" form.
            # Dropping it meant a named antagonist could not be authored at all.
            name=cfg.get("name") or "",
        ))

    for cfg in initial_npcs_config or []:
        npc_spawns.append(NPCSpawn(
            name=cfg.get("name", "Unknown NPC"),
            faction=cfg.get("faction", "Unknown"),
            entity_type=cfg.get("entity_type", "neutral"),
            threat_level=cfg.get("threat_level", "non_combatant"),
            disposition=cfg.get("disposition", "neutral"),
            description=cfg.get("description", f"{cfg.get('name', 'NPC')} present at scenario start"),
            health=cfg.get("health", 20),
            soak=cfg.get("soak", 0),
            skills=cfg.get("skills", {}),
            weapons=cfg.get("weapons", []),
        ))

    return enemy_spawns, npc_spawns
