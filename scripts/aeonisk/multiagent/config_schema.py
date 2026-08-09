"""Declarative config-schema registry — the single source of truth for the
session-config surface.

Historically the ~session config was an undocumented bag of keys read via scattered
`config.get('key', default)` calls across session.py / dm.py / launch_config.py, each
with its own inline default. This module makes that surface explicit and declarative so
that:

  * `launch_config.validate_session_config` derives its checks from ONE place;
  * `scripts/audit_session_configs.py` can report which shipped configs deviate from the
    research-recommended shape (tactical/enemy/outcome-first should be ON), use deprecated
    keys, set engine-ignored (vestigial) options, or contain typos;
  * a future interactive scenario-builder skill can walk the fields as a Q&A.

Design rules (Phase 1 — additive, no behavior change):
  * `default` mirrors the CODE's current inline default, not the README's claim. Where the
    two disagree the code wins and the discrepancy is recorded in `note` (see
    `free_targeting_mode`).
  * A few keys are read with different inline defaults at different call sites
    (`output_dir`, the LLM `model` fallback). Those record the CANONICAL value and are
    listed in `KNOWN_DIVERGENT` so the drift test does not assert equality; reconciling the
    call sites is a follow-up, not part of Phase 1.
  * `status="vestigial"` marks keys that configs set but the engine never reads. Verified by
    grep at authoring time; re-verify before trusting.

Nothing here changes runtime behavior — it only describes it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


class _Unset:
    """Sentinel distinct from None/False so 'no recommendation' is unambiguous."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):  # pragma: no cover - cosmetic
        return "<UNSET>"

    def __bool__(self):
        return False


UNSET = _Unset()


@dataclass(frozen=True)
class FieldSpec:
    """One config leaf.

    `path` is dotted, with `[]` for list-of-object elements, e.g.
    ``scenario.void_level`` or ``persistent_vendors[].inventory[].price_spark``.
    """

    path: str
    category: str          # identity|agents|party|mechanics|scenario|clocks|checkpoints|enemies|economy|bonds|names|meta
    type: str              # bool|int|str|float|list|dict|enum
    default: Any = UNSET   # code's current inline default (UNSET when read without one / required)
    status: str = "active"  # active|deprecated|vestigial
    recommended: Any = UNSET
    required: bool = False
    deprecated_by: Optional[str] = None
    depends_on: Optional[str] = None
    choices: Optional[list] = None
    help: str = ""
    note: str = ""

    @property
    def top_level(self) -> bool:
        """True if this is a root key (no nesting / list element)."""
        return "." not in self.path and "[" not in self.path


# Keys read with divergent inline defaults across call sites; the drift test skips
# default-equality for these. See module docstring.
KNOWN_DIVERGENT: set = {
    "output_dir",          # './multiagent_output' (session.py:877) vs './output' (session.py:1166/6080)
    "agents.dm.llm.model",  # 'claude-sonnet-4-5' / 'gpt-4' / 'claude-3-5-sonnet-20241022' by site; canonical 'gpt-5-mini'
}

# `_`-prefixed and provenance keys the engine ignores — the audit whitelists these as
# documentation rather than flagging them "unknown".
META_KEY_PREFIXES = ("_",)
META_KEYS_EXACT: set = {
    "corpus_id", "notes", "mechanics_tested", "ml_training_value", "model_policy",
    "party_tier", "controlled_variable", "description",
}


def _f(*args, **kwargs) -> FieldSpec:
    return FieldSpec(*args, **kwargs)


CONFIG_SCHEMA: list[FieldSpec] = [
    # ---- identity / core -------------------------------------------------
    _f("session_name", "identity", "str", required=True,
       help="Human-readable name for this session."),
    _f("max_turns", "identity", "int", default=50, required=True,
       help="Round cap before the session force-ends.",
       note="Validator-required though a runtime default (50) also exists."),
    _f("party_size", "identity", "int", default=2, required=True,
       help="Number of player characters.",
       note="Validator-required though a runtime default (2) also exists."),
    _f("output_dir", "identity", "str", default="./multiagent_output",
       note="Divergent: read as './output' at session.py:1166/6080.",
       help="Where JSONL logs and dm_notes are written."),
    _f("socket_path", "identity", "str", default=None,
       help="Optional UNIX socket for the human interface."),
    _f("enable_human_interface", "identity", "bool", default=True,
       help="Allow a human to drive/observe via the interface."),
    _f("resume_state", "identity", "dict", default=None,
       help="Reconstructed state to resume a session from divergence."),

    # ---- agents ----------------------------------------------------------
    _f("agents", "agents", "dict", required=True,
       help="Container for dm / players / enemies / npcs agent configs."),
    _f("agents.dm", "agents", "dict", required=True,
       help="The Dungeon Master agent config."),
    _f("agents.dm.llm", "agents", "dict",
       help="LLM config block for the DM."),
    _f("agents.dm.llm.provider", "agents", "str", default="openai",
       note="Some sites default 'anthropic'.",
       help="LLM provider: openai | anthropic | batch_proxy."),
    _f("agents.dm.llm.model", "agents", "str", default="gpt-5-mini",
       note="Stale inline fallbacks exist (gpt-4, claude-sonnet-4-5, claude-3-5-sonnet-20241022); canonical is gpt-5-mini.",
       help="Model id for this agent."),
    _f("agents.dm.llm.temperature", "agents", "float", default=1.0,
       help="Sampling temperature."),
    _f("agents.dm.llm.max_tokens", "agents", "int", default=6000,
       help="Max output tokens."),
    _f("agents.dm.narrative_style", "agents", "str", default="",
       help="Freeform DM narrative-style guidance."),
    _f("agents.dm.tone_guidance", "agents", "str", default="",
       help="Freeform DM tone guidance."),
    _f("agents.players", "agents", "list", required=True,
       help="Non-empty list of player character configs."),
    _f("agents.players[].name", "party", "str", required=True,
       help="Character name."),
    _f("agents.players[].faction", "party", "str", required=True,
       help="Character faction."),
    _f("agents.players[].llm", "party", "dict", required=True,
       help="LLM config block for this player."),
    _f("agents.players[].llm.provider", "party", "str", required=True,
       help="LLM provider for this player."),
    _f("agents.players[].llm.model", "party", "str", required=True,
       help="Model id for this player."),
    _f("agents.players[].archetype", "party", "str", default="Unknown",
       help="Archetype label (Investigator/Diplomat/Combat/Tech/...)."),
    _f("agents.players[].void", "party", "int", default=0, choices=list(range(0, 11)),
       help="Starting Void score (0-10)."),
    _f("agents.players[].void_score", "party", "int", status="deprecated", deprecated_by="void",
       help="DEPRECATED alias of 'void'."),
    _f("agents.players[].personality", "party", "dict",
       help="Personality block."),
    _f("agents.players[].personality.description", "party", "str",
       help="Non-empty personality description string."),
    _f("agents.players[].pronouns", "party", "str",
       help="Advisory pronouns (she/her, they/them, ...)."),
    _f("agents.players[].character_ref", "party", "str",
       help="Reference into a shared character library; skips inline validation."),
    _f("agents.players[].equipped_weapons", "party", "dict",
       help="{slot: weapon_id}; ids must exist in WEAPON_LIBRARY."),
    _f("agents.players[].carried_weapons", "party", "list",
       help="[weapon_id]; ids must exist in WEAPON_LIBRARY."),
    # --- player sheet (read in player.py while building CharacterState) ---
    _f("agents.players[].attributes", "party", "dict", default={},
       note="player.py:418", help="The 8 YAGS attributes (Strength..Willpower), each an int."),
    _f("agents.players[].skills", "party", "dict", default={},
       note="player.py:419 (also skill_mapping.py:378)", help="{skill_name: rating 0-8}."),
    _f("agents.players[].soulcredit", "party", "int", default=None,
       note="player.py:421 — absent default is random.randint(4,7)",
       help="Starting Soulcredit (−10..+10). If omitted, randomized 4-7."),
    _f("agents.players[].bonds", "party", "list", default=[],
       note="player.py:422", help="Pre-existing Bonds for this character."),
    _f("agents.players[].goals", "party", "list", default=[],
       note="player.py:423 (read in dm.py:1652, 2999)", help="Character goals/drives (list of str)."),
    _f("agents.players[].inventory", "party", "dict", default={},
       note="player.py:413/425", help="{item_id: count}; no defaults, all from config."),
    _f("agents.players[].starting_currency", "party", "dict", default=None,
       note="player.py:429", help="Override the starting EnergyPurse (breath/grain/drip/spark/hollow)."),
    _f("agents.players[].personality.riskTolerance", "party", "int",
       note="personality dict read at player.py:303", help="0-10 (advisory, steers the agent)."),
    _f("agents.players[].personality.voidCuriosity", "party", "int",
       note="player.py:303", help="0-10 (advisory)."),
    _f("agents.players[].personality.bondPreference", "party", "str",
       note="player.py:303", help="e.g. 'avoids' / 'seeks' (advisory)."),
    _f("agents.players[].personality.ritualConservatism", "party", "int",
       note="player.py:303", help="0-10 (advisory)."),
    _f("agents.enemies", "agents", "dict",
       help="Enemy-agent config (llm block)."),
    _f("agents.enemies.llm", "agents", "dict",
       help="LLM config for enemy agents; falls back to dm."),
    _f("agents.enemy_agents", "agents", "dict", status="deprecated", deprecated_by="agents.enemies",
       help="DEPRECATED legacy shape for enemy llm config."),
    _f("agents.npcs", "agents", "dict",
       help="NPC-agent config (llm block)."),
    _f("agents.npcs.llm", "agents", "dict",
       help="LLM config for NPC agents; falls back to enemies then dm."),

    # ---- mechanics / feature flags --------------------------------------
    _f("tactical_module_enabled", "mechanics", "bool", default=False, recommended=True,
       help="Enable the tactical combat module. Research default: ON (avoid confounding).",
       note="No inline .get default; absence is falsy."),
    _f("enemy_agents_enabled", "mechanics", "bool", default=False, recommended=True,
       depends_on="tactical_module_enabled",
       help="Enable autonomous enemy agents. Requires tactical_module_enabled. Research default: ON."),
    _f("outcome_first_narration", "mechanics", "bool", default=False, recommended=True,
       help="Use the outcome-first resolution pipeline. Research default: ON (active direction)."),
    _f("outcome_synthesis_attempts", "mechanics", "int", default=3,
       help="Retry budget for outcome-first synthesis."),
    _f("bonds_enabled", "mechanics", "bool", default=True,
       help="Enable the Bond system."),
    _f("dm_assessment_enabled", "mechanics", "bool", default=True,
       help="One authoritative DM difficulty/framing call per round."),
    _f("party_capabilities_enabled", "party", "bool", default=True,
       help="Show teammates' top skills/attributes in player prompts."),
    _f("party_chat_enabled", "party", "bool", default=True,
       help="Render party-directed ambient speech as a chatter block."),
    _f("iff_enabled", "mechanics", "bool", default=False, recommended=True,
       help="IFF/ROE mode (Spec 06). Recommended ON: since free_targeting lets anyone "
            "be targeted, IFF makes friend/foe identification a live measured variable."),
    _f("post_resolution_adjudication", "mechanics", "str", default=False, recommended="enforce",
       choices=[False, True, "full_context", "enforce"],
       help="Adjudication regime. Recommended 'enforce': a dedicated post-resolution "
            "magistrate writes the statute-faithful SC/Void ledger instead of the lenient "
            "narrator (the accuracy-seeking arm). 'enforce' needs authored 'teeth' "
            "(SC-gated checkpoint / contract-lock weapon) to actually deter.",
       note="Read as truthiness, =='full_context', and =='enforce'. 'enforce' suppresses "
            "narrator-driven economy deltas so the magistrate is the sole ledger writer."),

    # ---- scenario (generation + mechanical) -----------------------------
    _f("scenario", "scenario", "dict", default={},
       help="Scenario block; when populated, used directly instead of LLM-generated."),
    _f("scenario.theme", "scenario", "str", default="Unknown",
       help="Scenario theme."),
    _f("scenario.location", "scenario", "str", default="Unknown Location",
       help="Scenario location."),
    _f("scenario.situation", "scenario", "str", default="Something mysterious is happening",
       help="Opening situation description."),
    _f("scenario.void_level", "scenario", "int", default=0,
       help="Environmental void level for the scene."),
    _f("scenario.initial_clocks", "scenario", "list", default=[], status="deprecated",
       deprecated_by="starting_clocks",
       help="DEPRECATED in-scenario clocks; use root-level starting_clocks."),
    _f("scenario.initial_clocks[].name", "scenario", "str", default="Unknown", status="deprecated",
       deprecated_by="starting_clocks[].name"),
    _f("scenario.initial_clocks[].max", "scenario", "int", default=6, status="deprecated",
       deprecated_by="starting_clocks[].max_ticks"),
    _f("scenario.initial_clocks[].current", "scenario", "int", default=0, status="deprecated",
       deprecated_by="starting_clocks[].current_ticks"),
    _f("scenario.initial_clocks[].description", "scenario", "str", default="", status="deprecated",
       deprecated_by="starting_clocks[].description"),
    _f("scenario.altars", "scenario", "list", default=[],
       help="Persistent ritual altars in the scene."),
    _f("scenario.altars[].altar_type", "scenario", "str", default="ritual_altar",
       help="Altar type (maps to AltarType enum)."),
    _f("scenario.altars[].quality", "scenario", "int", default=5, choices=list(range(1, 11)),
       help="Altar quality 1-10 (ritual bonus)."),
    _f("scenario.altars[].location", "scenario", "str", default="Unknown",
       help="Altar location label."),
    _f("scenario.altars[].altar_id", "scenario", "str", default=None,
       help="Explicit id, else auto-generated."),
    _f("scenario_hint", "scenario", "str", default="",
       help="DM scenario-generation guidance (canonical key)."),
    _f("_scenario_hint", "scenario", "str", default="", status="deprecated",
       deprecated_by="scenario_hint",
       help="DEPRECATED alias; scenario_hint wins when both present."),
    _f("force_scenario", "scenario", "str", default=None,
       help="Testing override: force a named scenario."),
    _f("force_combat", "scenario", "bool", default=False,
       help="Force the DM to generate a combat scenario."),
    _f("combat_scenario_index", "scenario", "int", default=None,
       help="Select a specific hardcoded combat template by index."),
    _f("force_vendor_gate", "scenario", "bool", default=False,
       help="Force a vendor-gated scenario."),
    _f("use_scenario_context", "scenario", "bool", default=True,
       help="(under generate_bonds) use scenario_hint as bond-generation context.",
       note="Canonical read path is generate_bonds.use_scenario_context."),

    # ---- clocks (root, NewClock schema) ---------------------------------
    _f("starting_clocks", "clocks", "list", default=[],
       help="Scene clocks loaded at session start (NewClock schema)."),
    _f("starting_clocks[].name", "clocks", "str", required=True,
       help="Unique clock name (3-50 chars)."),
    _f("starting_clocks[].max_ticks", "clocks", "int", required=True, choices=list(range(1, 13)),
       help="Ticks to fill (1-12, 4-8 recommended)."),
    _f("starting_clocks[].current_ticks", "clocks", "int", default=0,
       help="Starting tick count (usually 0)."),
    _f("starting_clocks[].max", "clocks", "int", status="deprecated", deprecated_by="starting_clocks[].max_ticks",
       help="Legacy alias of max_ticks (validator accepts current/max)."),
    _f("starting_clocks[].current", "clocks", "int", status="deprecated", deprecated_by="starting_clocks[].current_ticks",
       help="Legacy alias of current_ticks."),
    _f("starting_clocks[].description", "clocks", "str", required=True,
       help="What the clock represents (10-200 chars)."),
    _f("starting_clocks[].advance_meaning", "clocks", "str", required=True,
       help="What advancing the clock means."),
    _f("starting_clocks[].regress_meaning", "clocks", "str", required=True,
       help="What regressing the clock means."),
    _f("starting_clocks[].filled_consequence", "clocks", "str", default="",
       help="What happens when the clock fills (required if any terminal clock exists)."),
    _f("starting_clocks[].is_terminal_clock", "clocks", "bool", default=False,
       help="At most one clock may be terminal."),
    _f("starting_clocks[].terminal_outcome", "clocks", "enum", default="victory",
       choices=["victory", "defeat", "draw"],
       help="Outcome polarity when a terminal clock fills."),
    _f("starting_clocks[].direction", "clocks", "enum", status="vestigial",
       choices=["countup", "countdown"],
       note="Set in ~157 configs but never read; NewClock drops it. Polarity is computed "
            "from tick movement, terminality from is_terminal_clock/terminal_outcome.",
       help="Cosmetic only — the engine ignores it; do not rely on it."),

    # ---- checkpoints -----------------------------------------------------
    _f("starting_checkpoints", "checkpoints", "list", default=[],
       help="Soulcredit-gated checkpoints active from session start."),
    _f("starting_checkpoints[].name", "checkpoints", "str", required=True,
       help="Checkpoint name."),
    _f("starting_checkpoints[].checkpoint_id", "checkpoints", "str", default=None,
       help="Explicit id, else derived from name."),
    _f("starting_checkpoints[].faction", "checkpoints", "str", default="Neutral",
       help="Owning faction."),
    _f("starting_checkpoints[].soulcredit_requirement", "checkpoints", "int", default=0,
       help="Minimum SC to pass."),
    _f("starting_checkpoints[].description", "checkpoints", "str", default="",
       help="Checkpoint description."),

    # ---- enemies ---------------------------------------------------------
    _f("enemy_agent_config", "enemies", "dict", default={},
       help="Enemy-agent tuning block."),
    _f("enemy_agent_config.free_targeting_mode", "enemies", "bool", default=True,
       note="README documents default 'false' but code default is True (enemy_combat.py:588, player.py:2802).",
       help="Generic tgt_xxxx ids for all combatants (IFF/ROE testing)."),
    _f("enemy_agent_config.allow_groups", "enemies", "bool", default=None, status="vestigial",
       note="Set in ~184 configs but never read to drive behavior."),
    _f("enemy_agent_config.max_enemies_per_combat", "enemies", "int", default=None, status="vestigial",
       note="Set in ~184 configs but never read to drive behavior."),
    _f("enemy_agent_config.shared_intel_enabled", "enemies", "bool", default=None, status="vestigial",
       note="Set in ~183 configs but never read to drive behavior."),
    _f("enemy_agent_config.auto_execute_reactions", "enemies", "bool", default=None, status="vestigial",
       note="Set in ~183 configs but never read to drive behavior."),
    _f("enemy_agent_config.loot_suggestions_enabled", "enemies", "bool", default=None, status="vestigial",
       note="Set in ~182 configs but never read to drive behavior."),
    _f("enemy_agent_config.void_tracking_enabled", "enemies", "bool", default=None, status="vestigial",
       note="Set in ~182 configs but never read to drive behavior."),
    _f("initial_enemies", "enemies", "list", default=[],
       help="Enemies pre-spawned at session start."),
    # --- initial_enemies[] entries (parsed in initial_spawns.py:82-102; a
    #     prisoner/friendly/neutral disposition reroutes the entry to an NPC) ---
    _f("initial_enemies[].name", "enemies", "str", default="Unknown Enemy", note="initial_spawns.py:85"),
    _f("initial_enemies[].template", "enemies", "str", default="grunt",
       note="initial_spawns.py:93 (mapped via _TEMPLATE_MAP)", help="Enemy template id, e.g. grunt."),
    _f("initial_enemies[].faction", "enemies", "str", default="Hostile", note="initial_spawns.py:96"),
    _f("initial_enemies[].archetype", "enemies", "str", default=None,
       note="initial_spawns.py:97 — defaults to name"),
    _f("initial_enemies[].count", "enemies", "int", default=1, note="initial_spawns.py:88/98"),
    _f("initial_enemies[].disposition", "enemies", "str", default=None,
       note="initial_spawns.py:83 — prisoner/friendly/neutral reroutes to an NPC spawn"),
    _f("initial_enemies[].position", "enemies", "str", default="Far-Enemy", note="initial_spawns.py:100"),
    _f("initial_enemies[].spawn_reason", "enemies", "str", default=None, note="initial_spawns.py:99"),
    _f("initial_enemies[].tactics", "enemies", "str", default=None,
       note="initial_spawns.py:101 → EnemySpawn.custom_traits"),
    _f("initial_enemies[].threat_level", "enemies", "str", default="non_combatant",
       note="initial_spawns.py:52/109 (used when rerouted to NPC)"),
    _f("initial_enemies[].health", "enemies", "int", default=20, note="initial_spawns.py:55/112"),
    _f("initial_enemies[].soak", "enemies", "int", default=0, note="initial_spawns.py:56/113"),
    _f("initial_enemies[].skills", "enemies", "dict", default={}, note="initial_spawns.py:57"),
    _f("initial_enemies[].description", "enemies", "str", default=None, note="initial_spawns.py:46"),
    _f("initial_npcs", "enemies", "list", default=[],
       help="NPCs pre-spawned at session start."),
    # --- initial_npcs[] entries (parsed in initial_spawns.py:104-114) ---
    _f("initial_npcs[].name", "enemies", "str", default="Unknown NPC", note="initial_spawns.py:106"),
    _f("initial_npcs[].faction", "enemies", "str", default="Unknown", note="initial_spawns.py:107"),
    _f("initial_npcs[].entity_type", "enemies", "str", default="neutral", note="initial_spawns.py:108"),
    _f("initial_npcs[].threat_level", "enemies", "str", default="non_combatant", note="initial_spawns.py:109"),
    _f("initial_npcs[].disposition", "enemies", "str", default="neutral", note="initial_spawns.py:110"),
    _f("initial_npcs[].description", "enemies", "str", default=None, note="initial_spawns.py:111"),
    _f("initial_npcs[].health", "enemies", "int", default=20, note="initial_spawns.py:112"),
    _f("initial_npcs[].soak", "enemies", "int", default=0, note="initial_spawns.py:113"),
    _f("initial_npcs[].skills", "enemies", "dict", default={}, note="initial_spawns.py:114"),
    _f("initial_npcs[].position", "enemies", "str", default=None, note="initial_spawns.py (npc.position)"),

    # ---- economy / vendors ----------------------------------------------
    _f("vendor_spawn_frequency", "economy", "int", default=3,
       help="Spawn a vendor every N rounds; -1 = never, 0 = off (legacy)."),
    _f("persistent_vendors", "economy", "list", default=[],
       help="Vendors that persist across all rounds."),
    _f("persistent_vendors[].name", "economy", "str", required=True,
       help="Vendor name."),
    _f("persistent_vendors[].faction", "economy", "str", default="Neutral",
       help="Vendor faction."),
    _f("persistent_vendors[].vendor_type", "economy", "str", default="human_trader",
       help="Vendor type (maps to VendorType enum)."),
    _f("persistent_vendors[].greeting", "economy", "str", default="Looking to trade?",
       help="Vendor greeting line."),
    _f("persistent_vendors[].vendor_id", "economy", "str", default=None,
       help="Explicit id, else auto-generated."),
    _f("persistent_vendors[].inventory", "economy", "list", default=[],
       help="Items the vendor sells."),
    _f("persistent_vendors[].inventory[].name", "economy", "str", required=True,
       help="Item name."),
    _f("persistent_vendors[].inventory[].description", "economy", "str", required=True,
       help="Item description."),
    _f("persistent_vendors[].inventory[].item_id", "economy", "str", default=None,
       help="Explicit id, else auto-generated."),
    _f("persistent_vendors[].inventory[].price_spark", "economy", "int", default=0),
    _f("persistent_vendors[].inventory[].price_grain", "economy", "int", default=0),
    _f("persistent_vendors[].inventory[].price_drip", "economy", "int", default=0),
    _f("persistent_vendors[].inventory[].price_breath", "economy", "int", default=0),
    _f("persistent_vendors[].inventory[].seed_barter", "economy", "bool", default=False),
    _f("persistent_vendors[].inventory[].item_type", "economy", "str", default="consumable"),
    _f("persistent_vendors[].inventory[].buys_from_players", "economy", "bool", default=False),
    _f("persistent_vendors[].inventory[].buy_prices", "economy", "dict", default={}),

    # ---- bonds -----------------------------------------------------------
    _f("starting_bonds", "bonds", "list",
       help="Bonds established at session start."),
    _f("starting_bonds[].character_a", "bonds", "str", required=True),
    _f("starting_bonds[].character_b", "bonds", "str", required=True),
    _f("starting_bonds[].bond_type", "bonds", "str", required=True,
       help="Kinship|Ascendancy|Debt|Voidward|Passion|Faction."),
    _f("starting_bonds[].witnessed_by", "bonds", "list", default=[]),
    _f("starting_bonds[].narrative", "bonds", "str", default=""),
    _f("generate_bonds", "bonds", "dict", default={},
       help="Auto-generate a bond network via LLM."),
    _f("generate_bonds.enabled", "bonds", "bool", default=False,
       help="Turn on auto bond generation."),
    _f("generate_bonds.min_bonds", "bonds", "int", default=2),
    _f("generate_bonds.max_bonds", "bonds", "int", default=5),
    _f("generate_bonds.use_scenario_context", "bonds", "bool", default=True,
       help="Feed scenario_hint into bond narrative generation."),

    # ---- discovery limits (read in mechanics.py:3880) -------------------
    _f("discovery_limits", "economy", "dict", default={},
       help="Caps on item/currency discovery per session."),
    _f("discovery_limits.max_seeds_per_session", "economy", "int", default=3,
       help="Max seed items discoverable per session."),
    _f("discovery_limits.max_currency_per_session", "economy", "int", default=50,
       help="Max currency (drip) discoverable per session."),
    _f("discovery_limits.quest_rewards_bypass_limits", "economy", "bool", default=True,
       help="Quest/DM-award rewards bypass the discovery caps."),

    # ---- names MCP -------------------------------------------------------
    _f("names_mcp", "names", "dict", default={},
       help="Aeonisk-names MCP integration for NPC naming."),
    _f("names_mcp.enabled", "names", "bool", default=False,
       help="Replace DM-hallucinated NPC names with canon Pattern-B names."),
    _f("names_mcp.from_pool", "names", "bool", default=True,
       help="Draw from the reserved name pool."),

    # ---- experiment toggles ----------------------------------------------
    # Real, live config surface that the registry simply never learned about,
    # so 19 configs audited as carrying an "unknown" key. dm.py reads it.
    _f("experiment", "experiment", "dict", default={},
       help="Per-run experiment toggles that swap engine behaviour for a study."),
    _f("experiment.include_suppression_resolution_example", "experiment", "bool",
       default=False,
       help="Swap the combat resolution prompt module for the suppression-inclusive "
            "variant (dm.py:_build_module_list). Used by the suppression study."),
]


# --------------------------------------------------------------------------
# Accessors
# --------------------------------------------------------------------------
_BY_PATH = {fs.path: fs for fs in CONFIG_SCHEMA}


def by_path(path: str) -> Optional[FieldSpec]:
    return _BY_PATH.get(path)


def by_category(category: str) -> list[FieldSpec]:
    return [fs for fs in CONFIG_SCHEMA if fs.category == category]


def top_level_specs() -> list[FieldSpec]:
    return [fs for fs in CONFIG_SCHEMA if fs.top_level]


def top_level_keys() -> set:
    return {fs.path for fs in CONFIG_SCHEMA if fs.top_level}


def defaults() -> dict:
    """Top-level {key: default} for every top-level spec that has a concrete default."""
    return {fs.path: fs.default for fs in CONFIG_SCHEMA
            if fs.top_level and fs.default is not UNSET}


def recommended_overrides() -> dict:
    """Top-level {key: recommended} where a research-recommended value differs from default."""
    return {fs.path: fs.recommended for fs in CONFIG_SCHEMA
            if fs.recommended is not UNSET}


def required_top_level() -> list[str]:
    return [fs.path for fs in CONFIG_SCHEMA if fs.top_level and fs.required]


def deprecations() -> dict:
    """{deprecated_path: replacement_path} for every deprecated spec."""
    return {fs.path: fs.deprecated_by for fs in CONFIG_SCHEMA
            if fs.status == "deprecated" and fs.deprecated_by}


def vestigial_keys() -> list[str]:
    return [fs.path for fs in CONFIG_SCHEMA if fs.status == "vestigial"]


def is_meta_key(key: str) -> bool:
    """True if a config key is documentation/provenance the engine ignores."""
    return key.startswith(META_KEY_PREFIXES) or key in META_KEYS_EXACT


# --------------------------------------------------------------------------
# Behavioral helpers (used by the audit and the scenario-builder skill)
# --------------------------------------------------------------------------
def _effective(config: dict, key: str):
    """Config's value for a top-level key, or the registry default if absent."""
    spec = by_path(key)
    return config.get(key, spec.default if spec else None)


def has_teeth(config: dict) -> bool:
    """True if the scenario has a Soulcredit-gating surface that makes 'enforce' bite:
    an SC-gated checkpoint, or a player holding a soulcredit-locked contract weapon.
    (Standing-gated vendors exist too but aren't reliably detectable structurally.)

    Teeth are optional and often DM-introduced in play — enforce-without-teeth is a
    valid, expected state, not a defect.
    """
    if config.get("starting_checkpoints"):
        return True
    try:  # weapon library is optional at import time
        from aeonisk.multiagent.weapons import WEAPON_LIBRARY
    except ImportError:  # pragma: no cover
        WEAPON_LIBRARY = {}
    agents = config.get("agents") or {}
    for player in (agents.get("players") or []):
        if not isinstance(player, dict):
            continue
        weapon_ids = list((player.get("equipped_weapons") or {}).values())
        weapon_ids += list(player.get("carried_weapons") or [])
        for wid in weapon_ids:
            weapon = WEAPON_LIBRARY.get(wid)
            if weapon and "soulcredit_locked" in (getattr(weapon, "special", None) or []):
                return True
    return False


def explain_config(config: dict) -> str:
    """Plain-language 'what this session WILL and WON'T do', driven by the registry.

    Truthful by construction — reads effective values (the config's value or the code
    default). Meant to give an author confidence about a config's behavior before running.
    """
    will: list[str] = []
    wont: list[str] = []
    notes: list[str] = []

    def flag(key, will_text, wont_text):
        (will if _effective(config, key) else wont).append(will_text if _effective(config, key) else wont_text)

    flag("tactical_module_enabled",
         "resolve tactical combat (positioning, range, cover)",
         "run tactical combat — actions resolve narratively only")
    flag("enemy_agents_enabled",
         "run enemies as autonomous agents each round",
         "spawn autonomous enemies (opposition is DM-narrated only)")
    flag("outcome_first_narration",
         "use the outcome-first pipeline (mechanics settled before prose)",
         "use outcome-first (legacy narration-first ordering)")
    flag("iff_enabled",
         "expose faction IFF + selective enemy intel (friend/foe is a live variable)",
         "run IFF/ROE (enemies share intel globally; no IFF probing)")
    flag("dm_assessment_enabled",
         "set authoritative per-round difficulty before any dice",
         "run the per-round DM difficulty assessment")
    flag("bonds_enabled", "track Bonds and their Void-driven transitions",
         "track the Bond system")

    # Adjudication regime (three-way)
    adj = _effective(config, "post_resolution_adjudication")
    if adj == "enforce":
        will.append("write the SC/Void ledger via a post-resolution magistrate "
                    "(statute-faithful), suppressing the narrator's inline economy deltas")
        if not has_teeth(config):
            notes.append("SC is enforced but no gating surface is authored — this records the "
                         "ledger without deterrence; the DM may add teeth (checkpoints / "
                         "SC-locked gear) spontaneously in play")
    elif adj in ("full_context", True) or (adj and adj is not False):
        will.append("log magistrate SC rulings each round (observe-only — NOT applied)")
    else:
        wont.append("run post-resolution adjudication (the narrator writes the SC/Void "
                    "ledger inline — the lenient default)")

    # Structural facts
    enemies = config.get("initial_enemies") or []
    if enemies:
        will.append(f"start with {len(enemies)} enemy(ies) pre-spawned")
    vendors = config.get("persistent_vendors") or []
    (will if vendors else wont).append(
        f"have {len(vendors)} persistent vendor(s)" if vendors else "include persistent vendors")
    checkpoints = config.get("starting_checkpoints") or []
    if checkpoints:
        will.append(f"gate movement at {len(checkpoints)} SC checkpoint(s)")
    if (config.get("names_mcp") or {}).get("enabled"):
        will.append("name NPCs from the canon names pool")

    clocks = config.get("starting_clocks") or []
    if clocks:
        names = [c.get("name", "?") for c in clocks if isinstance(c, dict)]
        terminal = [c.get("name") for c in clocks
                    if isinstance(c, dict) and c.get("is_terminal_clock")]
        term_txt = (f"terminal: {terminal[0]} "
                    f"({clocks[[c.get('name') for c in clocks].index(terminal[0])].get('terminal_outcome', 'victory')})"
                    if terminal else "no terminal clock")
        will.append(f"run {len(clocks)} scene clock(s) [{', '.join(names)}] — {term_txt}")

    lines = _shape_lines(config)
    lines += ["", "This session WILL:"]
    lines += [f"  • {w}" for w in will] or ["  • (nothing notable enabled)"]
    lines += ["", "This session will NOT:"]
    lines += [f"  • {w}" for w in wont] or ["  • (no notable disables)"]
    if notes:
        lines += ["", "Notes:"]
        lines += [f"  • {n}" for n in notes]
    return "\n".join(lines)


def _shape_lines(config: dict) -> list:
    """Size and cost shape: rounds, party, and which model each agent actually uses.

    Read off the config rather than narrated by an agent, so an author cannot be
    told one thing and run another.
    """
    name = config.get("session_name", "(unnamed)")
    rounds = _effective(config, "max_turns")
    agents = config.get("agents") or {}
    players = agents.get("players") or []
    party = config.get("party_size", len(players))

    scale = "smoke-sized" if isinstance(rounds, int) and rounds <= 3 else "full-length"
    lines = [f"{name}: {rounds} round(s) max, {party} player(s) — {scale}."]

    def model_of(block):
        llm = (block or {}).get("llm") or {}
        provider, model = llm.get("provider", "?"), llm.get("model", "?")
        if provider == "batch_proxy":
            provider = f"proxy→{llm.get('underlying_provider', '?')}"
        return f"{provider}/{model}"

    used = {}
    used.setdefault(model_of(agents.get("dm")), []).append("DM")
    for player in players:
        if isinstance(player, dict) and not player.get("character_ref"):
            used.setdefault(model_of(player), []).append(player.get("name", "player"))
    lines += [f"Models: " + "; ".join(f"{m} ({', '.join(who)})" for m, who in used.items())]

    if _effective(config, "enable_human_interface"):
        lines.append("Interactive: opens an '[Observer]>' stdin prompt — not suitable "
                     "for an unattended or piped run.")
    return lines
