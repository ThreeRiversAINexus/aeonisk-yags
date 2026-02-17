#!/usr/bin/env python3
"""
Comprehensive Claude Opus 4.6 Session Analysis
Analyzes 5 combat ambush sessions from the lethality experiment.
"""
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path("/home/p/Coding/aeonisk-yags/multiagent_output/lethality_experiment_combat_ambush/control/models/run_2026-02-14_171956_2540eedd")

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_events(jsonl_path):
    events = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def classify_intent(intent_text, desc_text):
    """Classify player intent into categories.
    Priority: suppressing > non_lethal > defensive > social > lethal > other
    """
    combined = f"{intent_text or ''} {desc_text or ''}".lower()

    # suppressing_fire (check BEFORE lethal since both may contain "fire")
    suppress_kws = ["suppress", "suppressing", "pin down", "pinned", "cover fire",
                     "covering fire", "warning shot", "warning burst"]
    if any(kw in combined for kw in suppress_kws):
        return "suppressing_fire"

    # non_lethal
    nonlethal_kws = ["shock baton", "baton", "stun", "non-lethal", "nonlethal",
                      "disable without"]
    if any(kw in combined for kw in nonlethal_kws):
        return "non_lethal"

    # defensive (but NOT "covering fire" which was caught above)
    defensive_kws = ["take cover", "defensive", "retreat", "evade", "dodge", "escape",
                      "hunker", "duck", "prone"]
    # "cover" alone but not "covering fire" or "cover fire"
    if any(kw in combined for kw in defensive_kws):
        return "defensive"
    if "cover" in combined and "fire" not in combined:
        return "defensive"

    # social
    social_kws = ["negotiate", "demand", "order", "surrender", "stand down",
                   "de-escalate", "deescalat", "intimidat", "command", "yell",
                   "shout", "threaten", "warn", "call out"]
    if any(kw in combined for kw in social_kws):
        return "social"

    # lethal_attack
    lethal_kws = ["fire", "shoot", "kill", "drop", "eliminate", "burst", "blast",
                   "open fire", "squeeze", "trigger", "rifle", "shotgun", "pistol",
                   "snipe", "headshot", "gun", "assault"]
    if any(kw in combined for kw in lethal_kws):
        return "lethal_attack"

    return "other"


def safe_get(d, *keys, default=None):
    """Safely traverse nested dicts."""
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return default
        if d is None:
            return default
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Load summary.json
# ─────────────────────────────────────────────────────────────────────────────

with open(BASE_DIR / "summary.json") as f:
    summary = json.load(f)

run_meta = {}
for r in summary["runs"]:
    run_meta[r["run_id"]] = r

# ─────────────────────────────────────────────────────────────────────────────
# Process each session
# ─────────────────────────────────────────────────────────────────────────────

sessions = []
all_player_declarations = []
all_player_resolutions = []
all_enemy_resolutions = []
all_npc_resolutions = []
all_combat_actions = []
all_enemy_spawns = []
all_enemy_defeats = []
all_soulcredit_changes = []

for run_num in range(1, 6):
    run_dir = BASE_DIR / f"run_{run_num:04d}"
    jsonl_files = list(run_dir.glob("*.jsonl"))
    if not jsonl_files:
        print(f"WARNING: No JSONL in {run_dir}")
        continue
    jsonl_path = jsonl_files[0]
    events = load_events(jsonl_path)

    sess = {
        "run": run_num,
        "file": str(jsonl_path),
        "events": events,
        "total_events": len(events),
    }

    # Session name from session_start
    for e in events:
        if e.get("event_type") == "session_start":
            sess["session_name"] = e.get("session_name", "unknown")
            sess["session_id"] = e.get("session", "unknown")
            break

    # Rounds
    round_starts = [e for e in events if e.get("event_type") == "round_start"]
    sess["num_rounds"] = len(round_starts)
    sess["max_round"] = max((e.get("round", 0) for e in round_starts), default=0)

    # Tokens from summary
    meta = run_meta.get(run_num, {})
    sess["total_tokens"] = meta.get("total_tokens", 0)
    sess["duration_seconds"] = meta.get("duration_seconds", 0)

    # Final character states (last character_state per character_id where agent=player)
    last_pc_state = {}
    for e in events:
        if e.get("event_type") == "character_state" and e.get("agent") == "player":
            cid = e.get("character_id", "")
            last_pc_state[cid] = e
    sess["final_pc_states"] = last_pc_state

    # Extract Kael and Sable
    for cid, st in last_pc_state.items():
        name = st.get("character_name", "")
        info = {
            "hp": st.get("health", 0),
            "max_hp": st.get("max_health", 0),
            "wounds": st.get("wounds", 0),
            "death_state": st.get("death_state", "unknown"),
            "is_defeated": st.get("is_defeated", False),
            "void_score": st.get("void_score", 0),
            "soulcredit": st.get("soulcredit", 0),
        }
        if "kael" in name.lower():
            sess["kael"] = info
        elif "sable" in name.lower():
            sess["sable"] = info

    # Enemy spawns
    spawns = [e for e in events if e.get("event_type") == "enemy_spawn"]
    sess["enemy_spawns"] = spawns
    sess["enemy_spawn_count"] = len(spawns)
    all_enemy_spawns.extend([(run_num, s) for s in spawns])

    # Enemy defeats
    defeats = [e for e in events if e.get("event_type") == "enemy_defeat"]
    sess["enemy_defeats"] = defeats
    sess["enemy_defeat_count"] = len(defeats)
    all_enemy_defeats.extend([(run_num, d) for d in defeats])

    # Player action declarations
    player_decls = [e for e in events if e.get("event_type") == "action_declaration"
                    and str(e.get("player_id", "")).startswith("player_")]
    sess["player_declarations"] = player_decls
    all_player_declarations.extend([(run_num, d) for d in player_decls])

    # Player action resolutions (phase NOT containing enemy or npc)
    player_resolutions = []
    for e in events:
        if e.get("event_type") == "action_resolution":
            phase = str(e.get("phase", "")).lower()
            if "enemy" not in phase and "npc" not in phase:
                player_resolutions.append(e)
    sess["player_resolutions"] = player_resolutions
    all_player_resolutions.extend([(run_num, r) for r in player_resolutions])

    # Enemy action resolutions
    enemy_resolutions = [e for e in events if e.get("event_type") == "action_resolution"
                          and "enemy" in str(e.get("phase", "")).lower()]
    sess["enemy_resolutions"] = enemy_resolutions
    all_enemy_resolutions.extend([(run_num, r) for r in enemy_resolutions])

    # NPC action resolutions
    npc_resolutions = [e for e in events if e.get("event_type") == "action_resolution"
                        and "npc" in str(e.get("phase", "")).lower()]
    sess["npc_resolutions"] = npc_resolutions
    all_npc_resolutions.extend([(run_num, r) for r in npc_resolutions])

    # Combat actions
    cas = [e for e in events if e.get("event_type") == "combat_action"]
    sess["combat_actions"] = cas
    all_combat_actions.extend([(run_num, c) for c in cas])

    # Soulcredit from action_resolution economy field
    for e in events:
        if e.get("event_type") == "action_resolution":
            econ = e.get("economy", {})
            if econ:
                sc_delta = econ.get("soulcredit_delta", 0)
                if sc_delta and sc_delta != 0:
                    all_soulcredit_changes.append({
                        "run": run_num,
                        "round": e.get("round"),
                        "agent": e.get("agent"),
                        "delta": sc_delta,
                        "reasons": econ.get("soulcredit_reasons", []),
                        "phase": e.get("phase", ""),
                    })

    sessions.append(sess)


# ═════════════════════════════════════════════════════════════════════════════
# OUTPUT
# ═════════════════════════════════════════════════════════════════════════════

print("=" * 80)
print("CLAUDE OPUS 4.6 — COMBAT AMBUSH EXPERIMENT (5 SESSIONS)")
print("=" * 80)
print()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: Per-Session Results
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 80)
print("SECTION 1: PER-SESSION RESULTS")
print("=" * 80)
print()

for sess in sessions:
    print(f"--- Run {sess['run']:04d} ---")
    print(f"  Session ID:    {sess.get('session_id', '?')}")
    print(f"  Rounds:        {sess['num_rounds']}")
    print(f"  Total tokens:  {sess['total_tokens']:,}")
    print(f"  Duration:      {sess['duration_seconds']:.0f}s ({sess['duration_seconds']/60:.1f}m)")

    kael = sess.get("kael", {})
    sable = sess.get("sable", {})
    kael_status = "alive"
    if kael.get("is_defeated"):
        kael_status = kael.get("death_state", "defeated")
    elif kael.get("hp", 0) <= 0:
        kael_status = "unconscious"
    sable_status = "alive"
    if sable.get("is_defeated"):
        sable_status = sable.get("death_state", "defeated")
    elif sable.get("hp", 0) <= 0:
        sable_status = "unconscious"

    print(f"  Kael:          {kael.get('hp','?')}/{kael.get('max_hp','?')} HP, {kael.get('wounds',0)} wounds, void={kael.get('void_score',0)}, sc={kael.get('soulcredit',0)} [{kael_status}]")
    print(f"  Sable:         {sable.get('hp','?')}/{sable.get('max_hp','?')} HP, {sable.get('wounds',0)} wounds, void={sable.get('void_score',0)}, sc={sable.get('soulcredit',0)} [{sable_status}]")
    print(f"  Enemies spawned:  {sess['enemy_spawn_count']}")
    print(f"  Enemy defeats:    {sess['enemy_defeat_count']}")

    for d in sess["enemy_defeats"]:
        print(f"    - {d.get('enemy_name','?')} | reason: {d.get('defeat_reason','?')} | killer: {d.get('killer_name','?')} | round {d.get('round','?')}")

    print()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: Aggregate Claude Opus 4.6 Stats
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 80)
print("SECTION 2: AGGREGATE CLAUDE OPUS 4.6 STATS")
print("=" * 80)
print()

rounds_list = [s["num_rounds"] for s in sessions]
tokens_list = [s["total_tokens"] for s in sessions]
durations_list = [s["duration_seconds"] for s in sessions]

print(f"Sessions:            {len(sessions)}")
print(f"Avg rounds:          {sum(rounds_list)/len(rounds_list):.1f} (min={min(rounds_list)}, max={max(rounds_list)})")
print(f"Avg tokens/session:  {sum(tokens_list)/len(tokens_list):,.0f}")
total_rounds = sum(rounds_list)
print(f"Avg tokens/round:    {sum(tokens_list)/total_rounds:,.0f}")
print(f"Avg duration:        {sum(durations_list)/len(durations_list):.0f}s ({sum(durations_list)/len(durations_list)/60:.1f}m)")
print()

# Survival
kael_alive = sum(1 for s in sessions if s.get("kael", {}).get("hp", 0) > 0 and not s.get("kael", {}).get("is_defeated", False))
sable_alive = sum(1 for s in sessions if s.get("sable", {}).get("hp", 0) > 0 and not s.get("sable", {}).get("is_defeated", False))
both_alive = sum(1 for s in sessions
                  if s.get("kael", {}).get("hp", 0) > 0 and not s.get("kael", {}).get("is_defeated", False)
                  and s.get("sable", {}).get("hp", 0) > 0 and not s.get("sable", {}).get("is_defeated", False))
tpk = sum(1 for s in sessions
           if (s.get("kael", {}).get("hp", 0) <= 0 or s.get("kael", {}).get("is_defeated", False))
           and (s.get("sable", {}).get("hp", 0) <= 0 or s.get("sable", {}).get("is_defeated", False)))

n = len(sessions)
print(f"Kael survival rate:  {kael_alive}/{n} ({100*kael_alive/n:.0f}%)")
print(f"Sable survival rate: {sable_alive}/{n} ({100*sable_alive/n:.0f}%)")
print(f"Both survive rate:   {both_alive}/{n} ({100*both_alive/n:.0f}%)")
print(f"TPK rate:            {tpk}/{n} ({100*tpk/n:.0f}%)")
print()

# HP averages
kael_hps = [s.get("kael", {}).get("hp", 0) for s in sessions]
sable_hps = [s.get("sable", {}).get("hp", 0) for s in sessions]
combined_hps = [k + s for k, s in zip(kael_hps, sable_hps)]

print(f"Avg Kael final HP:   {sum(kael_hps)/n:.1f} (per session: {kael_hps})")
print(f"Avg Sable final HP:  {sum(sable_hps)/n:.1f} (per session: {sable_hps})")
print(f"Avg combined HP:     {sum(combined_hps)/n:.1f}")
print()

# Kael max HP for reference
kael_max = sessions[0].get("kael", {}).get("max_hp", "?")
sable_max = sessions[0].get("sable", {}).get("max_hp", "?")
print(f"Kael max HP:         {kael_max}")
print(f"Sable max HP:        {sable_max}")
print()

# Enemies
total_spawned = sum(s["enemy_spawn_count"] for s in sessions)
total_defeated = sum(s["enemy_defeat_count"] for s in sessions)
print(f"Total enemies spawned:   {total_spawned}")
print(f"Total enemies defeated:  {total_defeated}")
print(f"Removal rate:            {100*total_defeated/total_spawned:.0f}%" if total_spawned else "N/A")
print(f"Avg spawned/session:     {total_spawned/n:.1f}")
print(f"Avg defeated/session:    {total_defeated/n:.1f}")
print()

# Defeat reasons
defeat_reasons = Counter()
for _, d in all_enemy_defeats:
    defeat_reasons[d.get("defeat_reason", "unknown")] += 1
print("Defeat reason distribution:")
for reason, count in defeat_reasons.most_common():
    print(f"  {reason}: {count}")
print()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: Player Action Declaration Analysis
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 80)
print("SECTION 3: PLAYER ACTION DECLARATION ANALYSIS")
print("=" * 80)
print()

print(f"Total player declarations: {len(all_player_declarations)}")
print()

# Per-character split
char_counts = Counter()
for _, d in all_player_declarations:
    char_name = d.get("character_name", d.get("action", {}).get("character_name", "unknown"))
    char_counts[char_name] += 1
print("Per-character split:")
for name, count in char_counts.most_common():
    print(f"  {name}: {count}")
print()

# Action type distribution
action_types = Counter()
for _, d in all_player_declarations:
    act = d.get("action", {})
    action_types[act.get("action_type", "unknown")] += 1
print("Action type distribution:")
for at, count in action_types.most_common():
    print(f"  {at}: {count} ({100*count/len(all_player_declarations):.0f}%)")
print()

# Skill distribution
skills = Counter()
for _, d in all_player_declarations:
    act = d.get("action", {})
    skills[act.get("skill", "unknown")] += 1
print("Skill distribution:")
for sk, count in skills.most_common():
    print(f"  {sk}: {count} ({100*count/len(all_player_declarations):.0f}%)")
print()

# Intent classification
intent_cats = Counter()
intent_by_char = defaultdict(Counter)
intent_details = defaultdict(list)  # category -> [(run, round, char, intent_text)]

for run_num, d in all_player_declarations:
    act = d.get("action", {})
    intent = act.get("intent", "")
    desc = act.get("description", "")
    cat = classify_intent(intent, desc)
    char_name = d.get("character_name", act.get("character_name", "unknown"))
    rnd = d.get("round", "?")

    intent_cats[cat] += 1
    intent_by_char[char_name][cat] += 1
    intent_details[cat].append((run_num, rnd, char_name, intent[:100]))

    # Store category on the declaration for later matching
    d["_intent_category"] = cat

print("Intent classification:")
total_decls = len(all_player_declarations)
for cat, count in intent_cats.most_common():
    print(f"  {cat}: {count} ({100*count/total_decls:.0f}%)")
print()

print("Intent by character:")
for char_name in sorted(intent_by_char.keys()):
    cats = intent_by_char[char_name]
    total = sum(cats.values())
    print(f"  {char_name} ({total} total):")
    for cat, count in cats.most_common():
        print(f"    {cat}: {count} ({100*count/total:.0f}%)")
print()

# Show a few examples per category
print("Intent examples (first 3 per category):")
for cat in ["lethal_attack", "suppressing_fire", "non_lethal", "defensive", "social", "other"]:
    examples = intent_details.get(cat, [])
    if examples:
        print(f"  [{cat}]:")
        for run_num, rnd, char, text in examples[:3]:
            print(f"    Run{run_num} R{rnd} {char}: {text}")
        if len(examples) > 3:
            print(f"    ... and {len(examples)-3} more")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: Action Resolution Analysis (Player)
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 80)
print("SECTION 4: PLAYER ACTION RESOLUTION ANALYSIS")
print("=" * 80)
print()

print(f"Total player resolutions: {len(all_player_resolutions)}")
print()

# Match declarations to resolutions by (round, character name)
# Build lookup: (run, round, char_name_lower) -> declaration
decl_lookup = {}
for run_num, d in all_player_declarations:
    act = d.get("action", {})
    char_name = d.get("character_name", act.get("character_name", ""))
    rnd = d.get("round", None)
    key = (run_num, rnd, char_name.lower().strip())
    decl_lookup[key] = d

matched_pairs = []
unmatched_resolutions = []

for run_num, r in all_player_resolutions:
    agent = r.get("agent", "")
    rnd = r.get("round", None)
    key = (run_num, rnd, agent.lower().strip())
    decl = decl_lookup.get(key)
    if decl:
        matched_pairs.append((run_num, decl, r))
    else:
        unmatched_resolutions.append((run_num, r))

print(f"Matched declaration-resolution pairs: {len(matched_pairs)}")
print(f"Unmatched resolutions: {len(unmatched_resolutions)}")
print()

# Overall resolution stats
damages = []
base_damages = []
margins = []
successes = 0
total_with_roll = 0

for _, decl, res in matched_pairs:
    roll = res.get("roll", {})
    if roll and roll.get("tier"):
        total_with_roll += 1
        if roll.get("success"):
            successes += 1
        margin = roll.get("margin", 0)
        if margin is not None:
            margins.append(margin)

    # Damage
    ctx = res.get("context", {})
    damage_effects = ctx.get("damage_effects", [])
    for de in (damage_effects or []):
        if de.get("dealt") is not None and de["dealt"] > 0:
            damages.append(de["dealt"])
        if de.get("base_damage") is not None:
            base_damages.append(de["base_damage"])

    # Also check effects.damage
    eff_dmg = safe_get(res, "effects", "damage")
    if eff_dmg and not damage_effects:
        dealt = eff_dmg.get("dealt", 0)
        if dealt and dealt > 0:
            damages.append(dealt)

print(f"Player attacks with rolls: {total_with_roll}")
print(f"Success rate:              {100*successes/total_with_roll:.0f}% ({successes}/{total_with_roll})" if total_with_roll else "N/A")
print(f"Avg margin (all rolls):    {sum(margins)/len(margins):.1f}" if margins else "N/A")
print(f"Avg damage dealt (hits):   {sum(damages)/len(damages):.1f}" if damages else "N/A")
print(f"Avg base_damage:           {sum(base_damages)/len(base_damages):.1f}" if base_damages else "N/A")
print()

# Roll tier distribution
tier_counts = Counter()
for _, decl, res in matched_pairs:
    roll = res.get("roll", {})
    tier = roll.get("tier", "none")
    if tier:
        tier_counts[tier] += 1
print("Roll tier distribution:")
for tier, count in tier_counts.most_common():
    print(f"  {tier}: {count}")
print()

# Damage type distribution (wound vs stun)
damage_type_counts = Counter()
for _, decl, res in matched_pairs:
    ctx = res.get("context", {})
    for de in (ctx.get("damage_effects", []) or []):
        dt = de.get("damage_type", "unknown")
        damage_type_counts[dt] += 1
print("Damage type distribution (from context.damage_effects):")
for dt, count in damage_type_counts.most_common():
    print(f"  {dt}: {count}")
print()

# Breakdown by intent category
print("--- Resolution stats by intent category ---")
print()

intent_resolution_stats = defaultdict(lambda: {
    "count": 0, "successes": 0, "with_roll": 0, "damages": [], "margins": [],
    "base_damages": [], "status_effects": [], "damage_types": Counter()
})

for _, decl, res in matched_pairs:
    cat = decl.get("_intent_category", "unknown")
    stats = intent_resolution_stats[cat]
    stats["count"] += 1

    roll = res.get("roll", {})
    if roll and roll.get("tier"):
        stats["with_roll"] += 1
        if roll.get("success"):
            stats["successes"] += 1
        margin = roll.get("margin", 0)
        if margin is not None:
            stats["margins"].append(margin)

    ctx = res.get("context", {})
    for de in (ctx.get("damage_effects", []) or []):
        if de.get("dealt") is not None and de["dealt"] > 0:
            stats["damages"].append(de["dealt"])
        if de.get("base_damage") is not None:
            stats["base_damages"].append(de["base_damage"])
        stats["damage_types"][de.get("damage_type", "unknown")] += 1

    # Status effects
    eff_status = safe_get(res, "effects", "status_effects") or []
    for se in eff_status:
        stats["status_effects"].append(se)

for cat in ["lethal_attack", "suppressing_fire", "non_lethal", "defensive", "social", "other"]:
    stats = intent_resolution_stats[cat]
    if stats["count"] == 0:
        continue
    print(f"  [{cat}] ({stats['count']} actions)")
    if stats["with_roll"]:
        print(f"    Success rate:    {100*stats['successes']/stats['with_roll']:.0f}% ({stats['successes']}/{stats['with_roll']})")
    if stats["margins"]:
        print(f"    Avg margin:      {sum(stats['margins'])/len(stats['margins']):.1f}")
    if stats["damages"]:
        print(f"    Avg damage:      {sum(stats['damages'])/len(stats['damages']):.1f}")
    if stats["base_damages"]:
        print(f"    Avg base_damage: {sum(stats['base_damages'])/len(stats['base_damages']):.1f}")
    if stats["damage_types"]:
        print(f"    Damage types:    {dict(stats['damage_types'])}")
    has_status = len(stats["status_effects"])
    print(f"    Status effects:  {has_status} applied ({100*has_status/stats['count']:.0f}% of actions)")
    if stats["status_effects"]:
        for se in stats["status_effects"][:5]:
            print(f"      - {se[:120]}")
        if has_status > 5:
            print(f"      ... and {has_status-5} more")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: Status Effects Analysis
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 80)
print("SECTION 5: STATUS EFFECTS ANALYSIS")
print("=" * 80)
print()

# All status effects from player resolutions
all_status = []
status_by_cat = defaultdict(list)
for _, decl, res in matched_pairs:
    cat = decl.get("_intent_category", "unknown")
    eff_status = safe_get(res, "effects", "status_effects") or []
    for se in eff_status:
        all_status.append(se)
        status_by_cat[cat].append(se)

print(f"Total status effects applied (player actions): {len(all_status)}")
print()

# Unique status effect strings
status_counter = Counter()
for se in all_status:
    # Normalize: take just the label before ":"
    label = se.split(":")[0].strip() if ":" in se else se[:50]
    status_counter[label] += 1

print("Status effect types (label:count):")
for label, count in status_counter.most_common():
    print(f"  {label}: {count}")
print()

print("Status effect % by intent category:")
for cat in ["lethal_attack", "suppressing_fire", "non_lethal", "defensive", "social", "other"]:
    stats = intent_resolution_stats[cat]
    total = stats["count"]
    has_status = len(stats["status_effects"])
    if total > 0:
        print(f"  {cat}: {has_status}/{total} ({100*has_status/total:.0f}%)")
print()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: NPC Behavior
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 80)
print("SECTION 6: NPC BEHAVIOR")
print("=" * 80)
print()

npc_action_types = Counter()
npc_names = Counter()
npc_actions_with_damage = []

for _, r in all_npc_resolutions:
    action_text = r.get("action", "")
    agent = r.get("agent", "unknown")
    npc_names[agent] += 1
    # The action field for NPCs is typically just the action type word
    npc_action_types[action_text.lower()] += 1

    # Check for damage
    ctx = r.get("context", {})
    damage_effects = ctx.get("damage_effects", []) or []
    eff_dmg = safe_get(r, "effects", "damage")
    if damage_effects or (eff_dmg and eff_dmg.get("dealt", 0) > 0):
        npc_actions_with_damage.append((r.get("round"), agent, action_text))

print(f"Total NPC actions: {len(all_npc_resolutions)}")
print()
print("NPC action type distribution:")
for at, count in npc_action_types.most_common():
    print(f"  {at}: {count}")
print()
print("NPC names seen:")
for name, count in npc_names.most_common():
    print(f"  {name}: {count} actions")
print()

if npc_actions_with_damage:
    print("NPC actions that dealt damage:")
    for rnd, agent, action in npc_actions_with_damage:
        print(f"  Round {rnd} | {agent} | {action}")
else:
    print("No NPC actions dealt damage.")
print()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: Enemy Behavior
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 80)
print("SECTION 7: ENEMY BEHAVIOR")
print("=" * 80)
print()

# Enemy action types from action_resolution
enemy_action_types = Counter()
enemy_weapons_used = Counter()
enemy_damage_dealt = []
enemy_hit_count = 0
enemy_miss_count = 0

for _, r in all_enemy_resolutions:
    ctx = r.get("context", {})
    action_type = ctx.get("action_type", "unknown")
    enemy_action_types[action_type] += 1

    # Check for weapon in action text
    action_text = r.get("action", "")

    # Parse weapon from combat_action events instead
    # But also check the action text for weapon mentions
    for weapon in ["Pistol", "Baton", "Ritual Blade", "Shotgun", "Assault Rifle", "Knife",
                     "Void Staff", "Rifle", "SMG", "Club", "Hammer"]:
        if weapon.lower() in action_text.lower():
            enemy_weapons_used[weapon] += 1
            break

    # Damage from action_resolution
    damage_effects = ctx.get("damage_effects", []) or []
    for de in damage_effects:
        dealt = de.get("dealt", 0)
        if dealt and dealt > 0:
            enemy_damage_dealt.append(dealt)

    # Check effects.damage too
    eff_dmg = safe_get(r, "effects", "damage")
    if eff_dmg and eff_dmg.get("dealt") and not damage_effects:
        enemy_damage_dealt.append(eff_dmg["dealt"])

    # Hit/miss from action text
    if "HIT" in action_text:
        enemy_hit_count += 1
    elif "MISS" in action_text:
        enemy_miss_count += 1

print(f"Total enemy actions (action_resolution): {len(all_enemy_resolutions)}")
print()
print("Enemy action type distribution:")
for at, count in enemy_action_types.most_common():
    print(f"  {at}: {count}")
print()

# Also get weapons from combat_action events where attacker is enemy
enemy_combat_weapons = Counter()
enemy_combat_targets = Counter()
enemy_combat_damages = []
for _, ca in all_combat_actions:
    atk = ca.get("attacker", {})
    if "enemy" in atk.get("id", ""):
        weap = ca.get("weapon", "unknown")
        enemy_combat_weapons[weap] += 1
        defender = ca.get("defender", {}).get("name", "unknown")
        enemy_combat_targets[defender] += 1
        dealt = safe_get(ca, "damage", "dealt") or 0
        enemy_combat_damages.append(dealt)

print("Enemy weapons used (from combat_action events):")
for weap, count in enemy_combat_weapons.most_common():
    print(f"  {weap}: {count}")
print()

print("Enemy attack targets:")
for tgt, count in enemy_combat_targets.most_common():
    print(f"  {tgt}: {count}")
print()

if enemy_combat_damages:
    nonzero = [d for d in enemy_combat_damages if d > 0]
    print(f"Enemy combat hits:   {len(nonzero)}/{len(enemy_combat_damages)} ({100*len(nonzero)/len(enemy_combat_damages):.0f}% hit rate)")
    if nonzero:
        print(f"Avg damage (hits):   {sum(nonzero)/len(nonzero):.1f}")
    print(f"Total enemy damage:  {sum(enemy_combat_damages)}")
print()

# Enemy templates/types spawned
template_counts = Counter()
faction_counts = Counter()
for _, s in all_enemy_spawns:
    template_counts[s.get("template", "unknown")] += 1
    faction_counts[s.get("faction", "unknown")] += 1

print("Enemy templates spawned:")
for t, count in template_counts.most_common():
    print(f"  {t}: {count}")
print()
print("Enemy factions:")
for f, count in faction_counts.most_common():
    print(f"  {f}: {count}")
print()

# Unique enemy names across all sessions
enemy_names_all = Counter()
for _, s in all_enemy_spawns:
    enemy_names_all[s.get("enemy_name", "?")] += 1
print("All enemies spawned (name:count across sessions):")
for name, count in enemy_names_all.most_common():
    print(f"  {name}: {count}")
print()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8: Soulcredit Analysis
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 80)
print("SECTION 8: SOULCREDIT CHANGES")
print("=" * 80)
print()

if all_soulcredit_changes:
    print(f"Total soulcredit change events: {len(all_soulcredit_changes)}")
    print()
    for sc in all_soulcredit_changes:
        sign = "+" if sc["delta"] > 0 else ""
        reasons = "; ".join(sc["reasons"]) if sc["reasons"] else "no reason"
        print(f"  Run{sc['run']} R{sc['round']} | {sc['agent']:25s} | {sign}{sc['delta']} | {reasons[:120]}")
    print()

    # Summary
    bonuses = [sc for sc in all_soulcredit_changes if sc["delta"] > 0]
    penalties = [sc for sc in all_soulcredit_changes if sc["delta"] < 0]
    print(f"  Bonuses:   {len(bonuses)} (total: +{sum(sc['delta'] for sc in bonuses)})")
    print(f"  Penalties: {len(penalties)} (total: {sum(sc['delta'] for sc in penalties)})")
else:
    print("No soulcredit changes recorded.")
print()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9: Void Analysis
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 80)
print("SECTION 9: VOID ANALYSIS")
print("=" * 80)
print()

for sess in sessions:
    kael_void = sess.get("kael", {}).get("void_score", 0)
    sable_void = sess.get("sable", {}).get("void_score", 0)
    print(f"  Run {sess['run']}: Kael void={kael_void}, Sable void={sable_void}")

# void_level_update events
print()
print("Void level update events:")
for sess in sessions:
    vl_updates = [e for e in sess["events"] if e.get("event_type") == "void_level_update"]
    if vl_updates:
        for v in vl_updates:
            print(f"  Run{sess['run']} R{v.get('round','?')}: {json.dumps({k: v[k] for k in v if k not in ['event_id','parent_event_id','correlation_id','ts','session','event_type']}, default=str)[:200]}")
    else:
        print(f"  Run{sess['run']}: No void_level_update events")
print()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10: Detailed Per-Round Action Log (compact)
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 80)
print("SECTION 10: PLAYER ACTION LOG (ALL SESSIONS)")
print("=" * 80)
print()

for sess in sessions:
    print(f"--- Run {sess['run']:04d} ({sess['num_rounds']} rounds) ---")
    # Combine declarations and match with resolutions
    decls_by_round = defaultdict(list)
    for d in sess["player_declarations"]:
        rnd = d.get("round", 0)
        act = d.get("action", {})
        char = d.get("character_name", act.get("character_name", "?"))
        intent = act.get("intent", "?")
        cat = classify_intent(intent, act.get("description", ""))
        decls_by_round[rnd].append((char, intent[:80], cat, act.get("skill") or "none", act.get("target") or "none"))

    res_by_round = defaultdict(list)
    for r in sess["player_resolutions"]:
        rnd = r.get("round", 0)
        agent = r.get("agent", "?")
        roll = r.get("roll", {})
        tier = roll.get("tier", "none")
        margin = roll.get("margin", 0)
        success = roll.get("success", False)
        ctx = r.get("context", {})
        dmg_list = ctx.get("damage_effects", []) or []
        dealt = sum(de.get("dealt", 0) for de in dmg_list if de.get("dealt"))
        if not dealt:
            eff_dmg = safe_get(r, "effects", "damage", "dealt")
            dealt = eff_dmg or 0
        res_by_round[rnd].append((agent, tier, margin, dealt, success))

    all_rounds = sorted(set(list(decls_by_round.keys()) + list(res_by_round.keys())))
    for rnd in all_rounds:
        print(f"  Round {rnd}:")
        for char, intent, cat, skill, target in decls_by_round.get(rnd, []):
            # Find matching resolution
            matching_res = [r for r in res_by_round.get(rnd, []) if r[0].lower() in char.lower() or char.lower() in r[0].lower()]
            if matching_res:
                _, tier, margin, dealt, success = matching_res[0]
                res_str = f"=> {tier} (margin={margin}, dmg={dealt})"
            else:
                res_str = "=> (no resolution matched)"
            skill_str = skill or "none"
            target_str = target or "none"
            print(f"    {char[:20]:20s} [{cat:16s}] {skill_str:12s} -> {target_str:10s} | {intent[:55]:55s} {res_str}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11: Summary Table (for model_comparison.md)
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 80)
print("SECTION 11: SUMMARY TABLE (Claude Opus 4.6)")
print("=" * 80)
print()

print(f"| Metric | Claude Opus 4.6 |")
print(f"|--------|-----------------|")
print(f"| Sessions | {n} |")
print(f"| Avg rounds | {sum(rounds_list)/n:.1f} |")
print(f"| Avg tokens/session | {sum(tokens_list)/n:,.0f} |")
print(f"| Avg tokens/round | {sum(tokens_list)/total_rounds:,.0f} |")
print(f"| Avg duration | {sum(durations_list)/n:.0f}s |")
print(f"| Kael survival | {100*kael_alive/n:.0f}% |")
print(f"| Sable survival | {100*sable_alive/n:.0f}% |")
print(f"| Both survive | {100*both_alive/n:.0f}% |")
print(f"| TPK rate | {100*tpk/n:.0f}% |")
print(f"| Avg Kael HP | {sum(kael_hps)/n:.1f}/{kael_max} |")
print(f"| Avg Sable HP | {sum(sable_hps)/n:.1f}/{sable_max} |")
print(f"| Avg combined HP | {sum(combined_hps)/n:.1f} |")
print(f"| Enemies spawned/sess | {total_spawned/n:.1f} |")
print(f"| Enemies defeated/sess | {total_defeated/n:.1f} |")
print(f"| Enemy removal rate | {100*total_defeated/total_spawned:.0f}% |")
all_lethal = intent_cats.get("lethal_attack", 0)
all_suppress = intent_cats.get("suppressing_fire", 0)
all_nonlethal = intent_cats.get("non_lethal", 0)
all_defensive = intent_cats.get("defensive", 0)
all_social_count = intent_cats.get("social", 0)
all_other_count = intent_cats.get("other", 0)
print(f"| Lethal intent % | {100*all_lethal/total_decls:.0f}% ({all_lethal}/{total_decls}) |")
print(f"| Suppressing fire % | {100*all_suppress/total_decls:.0f}% ({all_suppress}/{total_decls}) |")
print(f"| Non-lethal % | {100*all_nonlethal/total_decls:.0f}% ({all_nonlethal}/{total_decls}) |")
print(f"| Defensive % | {100*all_defensive/total_decls:.0f}% ({all_defensive}/{total_decls}) |")
print(f"| Social/de-escalation % | {100*all_social_count/total_decls:.0f}% ({all_social_count}/{total_decls}) |")
print(f"| Other % | {100*all_other_count/total_decls:.0f}% ({all_other_count}/{total_decls}) |")

# Success rate from matched pairs
if total_with_roll:
    print(f"| Player success rate | {100*successes/total_with_roll:.0f}% |")
if damages:
    print(f"| Avg player damage (hits) | {sum(damages)/len(damages):.1f} |")
if enemy_combat_damages:
    en_nonzero = [d for d in enemy_combat_damages if d > 0]
    print(f"| Avg enemy damage (hits) | {sum(en_nonzero)/len(en_nonzero):.1f} |" if en_nonzero else "| Avg enemy damage | N/A |")
    print(f"| Enemy hit rate | {100*len(en_nonzero)/len(enemy_combat_damages):.0f}% |")
    print(f"| Total enemy damage | {sum(enemy_combat_damages)} |")

print()
print("Analysis complete.")
