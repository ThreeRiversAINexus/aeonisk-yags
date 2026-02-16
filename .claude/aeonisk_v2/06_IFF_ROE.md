# 06: IFF/ROE -- Discovery-Based Faction Identification and Selective Intel

**Priority:** P1
**Status:** Spec Draft
**Dependencies:** 05_STEALTH (stealth interacts with visibility/discovery)
**Estimated Scope:** Large (per-agent knowledge tracking, prompt refactoring, combatant list per-agent views)

---

## Problem Statement

The current free targeting system assigns randomized `tgt_xxxx` IDs to hide agent
allegiance from LLMs, enabling IFF (Identification Friend or Foe) testing. However,
faction information is displayed directly in the combatant list, defeating the purpose:

- **Players see** `(player)` next to PCs, `(enemy)` next to enemies, and
  `(npc, friendly)` next to NPCs.
- **Enemies see** PC names, health, weapons, and position -- full intel from the start.
- **NPCs see** everyone's faction via the system prompt.

There is no discovery mechanic. Agents know who is friend and foe from the first
round. SharedIntel broadcasts to all enemies globally -- there is no selective
sharing. This means:

1. **No IFF challenge.** LLMs never need to identify friend from foe because the
   system tells them outright. The randomized `tgt_xxxx` IDs are cosmetic only.

2. **No fog of war.** All agents have perfect battlefield awareness of faction
   allegiance. An enemy sniper at Extreme range knows exactly which targets are PCs.

3. **No intel asymmetry.** Enemy squads who have never encountered the party know
   all PC names, factions, health, and weapons. Reinforcements arriving mid-combat
   have perfect knowledge.

4. **SharedIntel is global.** When one enemy shares intel, ALL enemies receive it
   immediately. There is no communication cost, range limitation, or selective
   targeting of intel recipients.

5. **ML training data lacks IFF signals.** Training data shows agents always knowing
   faction, so models learn no IFF reasoning. This is the primary motivation for the
   feature -- producing training data where models must reason about identification.

**Design Decisions (confirmed):**
- Remove automatic ally/enemy labels from combatant lists.
- PCs know each other's faction by default (they know who their party members are).
- Enemies and NPCs default to "Unknown" for all targets they have not identified.
- Identification requires Perception x Awareness check.
- Intel sharing is selective, not global -- agents specify which allies receive intel.

---

## Current Implementation

### Combatant List Builder -- Full Faction Display

**File:** `scripts/aeonisk/multiagent/dm.py` lines 7536-7578

The DM combatant list builder shows faction/type for all agents:

```python
# Player entries (line 7553)
combatant_lines.append(
    f"  - [{tid}] {info['name']} ({pronouns}, {health_text}{wounds_text})"
)

# NPC entries (line 7564)
combatant_lines.append(
    f"  - [{tid}] {info['name']} ({pronouns}, npc, {disposition})"
)

# Enemy entries (line 7567)
combatant_lines.append(
    f"  - [{tid}] {info['name']} ({pronouns}, {info['type']})"
)
```

Every agent sees every other agent's type (player/enemy/npc) and disposition. This
makes IFF trivial -- the system does the identification for them.

### Enemy Prompts -- Full PC Information

**File:** `scripts/aeonisk/multiagent/enemy_prompts.py` lines 440-483

The `_format_pc_target_info()` function gives enemies complete PC information:

```python
return f"""- {pc_name} [{pc_id}]
  Position: {pc_position} ({range_name.upper()} RANGE, {range_penalty} penalty)
  Health: {health_str}
  Defence Token: {watching_str}
  Weapons: {weapons_str}
  Threat Level: {threat_level}"""
```

Enemies know PC names, exact health percentages, weapons, and positions from the
first round. No discovery needed.

### Enemy Prompts -- Target Priority with Full Knowledge

**File:** `scripts/aeonisk/multiagent/enemy_prompts.py` lines 740-767

The `_format_target_priorities()` function sorts PCs by threat level:

```python
for i, (threat, pc_name, range_name, is_watching) in enumerate(threat_order[:3]):
    priority_label = ["PRIMARY", "SECONDARY", "TERTIARY"][i]
    section += f"\n{i+1}. {priority_label} THREAT: {pc_name} - {threat}"
```

Enemies receive a pre-sorted priority target list. They never need to assess targets
themselves.

### SharedIntel -- Global Broadcast

**File:** `scripts/aeonisk/multiagent/enemy_agent.py` lines 678-728 (SharedIntel class)

```python
class SharedIntel:
    def __init__(self):
        self.intel_pool: List[IntelItem] = []

    def add_intel(self, source_agent: str, intel: str, round_num: int):
        item = IntelItem(source_agent=source_agent, intel=intel, round=round_num)
        self.intel_pool.append(item)

    def get_recent_intel(self, current_round: int, lookback: int = 2):
        return [f"[ALLY {item.source_agent}] {item.intel}"
                for item in self.intel_pool
                if current_round - item.round <= lookback]
```

All enemies share a single `SharedIntel` pool. When enemy A adds intel, enemy B sees
it in the next round regardless of distance, line of sight, or communication ability.

**File:** `scripts/aeonisk/multiagent/enemy_combat.py` line 165

```python
self.shared_intel = SharedIntel()  # Single global pool
```

One pool for all enemies.

### TargetIDMapper -- Type Information Exposed

**File:** `scripts/aeonisk/multiagent/target_ids.py` lines 281-345

`get_combatant_info()` returns full type information:

```python
info = {
    'target_id': target_id,
    'agent_id': entity_id,
    'type': entity_type  # "player", "enemy", "npc", "vendor"
}
```

Any agent querying combatant info gets the full type classification.

### NPC System Prompt -- Faction Displayed

**File:** `scripts/aeonisk/multiagent/npc_agent.py` lines 571-643

NPC system prompt includes full faction information and stance:

```python
return f"""You are {self.npc.name}, a {self.npc.entity_type} NPC...
- Entity Type: {self.npc.entity_type} (neutral/ally/prisoner)
- Disposition: {self.npc.disposition} (friendly/neutral/wary/prisoner)
- Faction: {self.npc.faction}
{self._get_faction_context()}
"""
```

NPCs know their own faction and have a stance toward all other factions. They do NOT
need to discover other agents' factions -- but they receive it from the system.

---

## Design Decisions

1. **Per-agent knowledge tracking.** Each agent maintains a `known_identities` dict
   mapping target_id to known information (faction, name, threat level, etc.). Only
   information that has been discovered or shared is available.

2. **PCs default to knowing each other.** Party members know each other's faction,
   name, and general capabilities. This is realistic (they traveled together) and
   prevents PCs from wasting actions identifying allies.

3. **Enemies/NPCs default to "Unknown."** When enemies spawn, they do not know which
   targets are PCs, NPCs, or enemies (from other factions). They see target IDs and
   physical descriptions (size, weapons visible, position) but NOT faction labels.

4. **Identification via Perception x Awareness.** An agent can attempt to identify
   an unknown target as a minor action or part of a Scan. The check uses YAGS
   formula: Perception x Awareness + d20 vs DC based on distance and conditions.

5. **Selective intel sharing.** When an enemy shares intel via `shared_intel`, they
   specify which allies receive it. Intel propagates only to specified recipients, not
   the entire pool. This models communication limitations (radio range, line of sight,
   coordination).

6. **DM always has full knowledge.** The DM sees all agents' true factions, names,
   and types. The DM builds agent-specific combatant lists that reflect each agent's
   knowledge state.

7. **Progressive discovery model.** As combat progresses, agents build up knowledge:
   - Round 1: "Unknown humanoid at Near-Enemy with rifle"
   - Round 2 (after Scan): "Armed, appears to be ACG faction based on uniform"
   - Round 3 (after engagement): "Confirmed ACG Enforcer, Perception 4, Guns 3"

8. **Faction identification difficulty.** Base DC for identification depends on
   distance and visibility:
   - Engaged/Melee: DC 10 (can see insignia, hear speech)
   - Near: DC 15 (can see general appearance, weapons)
   - Far: DC 20 (silhouette only, need optics)
   - Extreme: DC 25 (barely visible, need high-powered optics)

---

## Proposed Solution

### Phase 1: Per-Agent Knowledge Model

#### 1.1 KnownIdentity Data Structure

**File:** `scripts/aeonisk/multiagent/identity_tracking.py` (new file)

```python
"""
Identity Tracking System for IFF/ROE Mechanics.

Manages per-agent knowledge of other agents' identities, factions, and
capabilities. Supports progressive discovery and selective intel sharing.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class IdentificationLevel(Enum):
    """How much an observer knows about a target."""
    UNKNOWN = "unknown"        # Only target_id and position visible
    SILHOUETTE = "silhouette"  # Size, weapon type (ranged/melee), stance
    PARTIAL = "partial"        # Faction insignia visible, general appearance
    IDENTIFIED = "identified"  # Full name, faction, threat assessment
    DETAILED = "detailed"      # Name, faction, health estimate, capabilities


@dataclass
class KnownIdentity:
    """What one agent knows about another agent."""
    target_id: str                              # tgt_xxxx
    identification_level: IdentificationLevel = IdentificationLevel.UNKNOWN
    known_faction: Optional[str] = None         # "ACG", "Tempest", "Unknown"
    known_name: Optional[str] = None            # "ACG Enforcer Alpha"
    known_type: Optional[str] = None            # "humanoid", "drone", "vehicle"
    estimated_threat: Optional[str] = None      # "armed", "unarmed", "heavy"
    visible_weapons: List[str] = field(default_factory=list)  # ["rifle", "sidearm"]
    last_known_position: Optional[str] = None   # "Near-Enemy"
    identified_round: Optional[int] = None      # When identification occurred
    source: Optional[str] = None                # "visual", "intel", "engagement"

    def get_display_string(self) -> str:
        """Get display string based on identification level."""
        if self.identification_level == IdentificationLevel.UNKNOWN:
            return f"[{self.target_id}] Unknown contact"
        elif self.identification_level == IdentificationLevel.SILHOUETTE:
            weapons = ", ".join(self.visible_weapons) if self.visible_weapons else "unknown armament"
            return f"[{self.target_id}] Humanoid ({weapons})"
        elif self.identification_level == IdentificationLevel.PARTIAL:
            faction_str = self.known_faction or "Unknown faction"
            return f"[{self.target_id}] {faction_str} operative"
        elif self.identification_level == IdentificationLevel.IDENTIFIED:
            name = self.known_name or "Unknown"
            faction = self.known_faction or "Unknown"
            return f"[{self.target_id}] {name} ({faction})"
        else:  # DETAILED
            name = self.known_name or "Unknown"
            faction = self.known_faction or "Unknown"
            threat = self.estimated_threat or "unknown threat"
            return f"[{self.target_id}] {name} ({faction}, {threat})"


@dataclass
class AgentKnowledge:
    """
    Complete knowledge state for one agent.

    Tracks what this agent knows about all other agents on the battlefield.
    """
    agent_id: str
    agent_type: str  # "player", "enemy", "npc"
    agent_faction: str  # This agent's own faction

    # Known identities: target_id -> KnownIdentity
    known_identities: Dict[str, KnownIdentity] = field(default_factory=dict)

    # Allied agents (always fully identified)
    allied_agent_ids: Set[str] = field(default_factory=set)

    def get_identity(self, target_id: str) -> KnownIdentity:
        """Get known identity for a target. Returns UNKNOWN if not known."""
        if target_id in self.known_identities:
            return self.known_identities[target_id]
        return KnownIdentity(target_id=target_id)

    def update_identity(
        self,
        target_id: str,
        level: IdentificationLevel,
        faction: Optional[str] = None,
        name: Optional[str] = None,
        weapons: Optional[List[str]] = None,
        threat: Optional[str] = None,
        source: str = "visual",
        round_num: Optional[int] = None
    ):
        """Update knowledge about a target (only upgrades, never downgrades)."""
        current = self.get_identity(target_id)

        # Only upgrade identification level, never downgrade
        level_order = [
            IdentificationLevel.UNKNOWN,
            IdentificationLevel.SILHOUETTE,
            IdentificationLevel.PARTIAL,
            IdentificationLevel.IDENTIFIED,
            IdentificationLevel.DETAILED,
        ]
        current_idx = level_order.index(current.identification_level)
        new_idx = level_order.index(level)

        if new_idx <= current_idx:
            return  # No upgrade

        updated = KnownIdentity(
            target_id=target_id,
            identification_level=level,
            known_faction=faction or current.known_faction,
            known_name=name or current.known_name,
            known_type=current.known_type,
            estimated_threat=threat or current.estimated_threat,
            visible_weapons=weapons if weapons else current.visible_weapons,
            last_known_position=current.last_known_position,
            identified_round=round_num,
            source=source,
        )
        self.known_identities[target_id] = updated

        logger.info(
            f"Agent {self.agent_id} identified {target_id} at level "
            f"{level.value}: {updated.get_display_string()}"
        )

    def identify_ally(self, target_id: str, name: str, faction: str,
                      round_num: int = 0):
        """Mark a target as a known ally (full identification)."""
        self.allied_agent_ids.add(target_id)
        self.update_identity(
            target_id=target_id,
            level=IdentificationLevel.DETAILED,
            faction=faction,
            name=name,
            source="allied",
            round_num=round_num
        )

    def receive_intel(
        self,
        target_id: str,
        level: IdentificationLevel,
        faction: Optional[str] = None,
        name: Optional[str] = None,
        source_agent: str = "unknown",
        round_num: Optional[int] = None
    ):
        """Receive intel about a target from another agent."""
        self.update_identity(
            target_id=target_id,
            level=level,
            faction=faction,
            name=name,
            source=f"intel from {source_agent}",
            round_num=round_num
        )


class IdentityTracker:
    """
    Central identity tracking system.

    Manages AgentKnowledge for all agents on the battlefield.
    Handles initialization, identification checks, and intel propagation.
    """

    def __init__(self):
        self.agent_knowledge: Dict[str, AgentKnowledge] = {}
        self.enabled: bool = False

    def enable(self):
        """Enable IFF tracking."""
        self.enabled = True
        logger.info("IFF/ROE identity tracking ENABLED")

    def disable(self):
        """Disable IFF tracking (everyone sees everything)."""
        self.enabled = False
        logger.info("IFF/ROE identity tracking DISABLED")

    def initialize_agent(
        self,
        agent_id: str,
        agent_type: str,
        agent_faction: str,
        allied_agent_ids: Optional[Set[str]] = None
    ) -> AgentKnowledge:
        """
        Initialize knowledge tracking for an agent.

        Args:
            agent_id: The agent's ID
            agent_type: "player", "enemy", "npc"
            agent_faction: The agent's faction
            allied_agent_ids: Set of agent IDs this agent knows as allies

        Returns:
            AgentKnowledge instance
        """
        knowledge = AgentKnowledge(
            agent_id=agent_id,
            agent_type=agent_type,
            agent_faction=agent_faction,
            allied_agent_ids=allied_agent_ids or set()
        )
        self.agent_knowledge[agent_id] = knowledge
        return knowledge

    def get_knowledge(self, agent_id: str) -> Optional[AgentKnowledge]:
        """Get an agent's knowledge state."""
        return self.agent_knowledge.get(agent_id)

    def initialize_combat(
        self,
        player_agents: list,
        enemy_agents: list,
        npc_agents: list,
        target_id_mapper
    ):
        """
        Initialize identity knowledge for all agents at combat start.

        PCs know each other (full identification).
        Enemies know their faction allies (full identification).
        All other targets start as UNKNOWN or SILHOUETTE (based on range).

        Args:
            player_agents: List of PC agents
            enemy_agents: List of enemy agents
            npc_agents: List of NPC agents
            target_id_mapper: TargetIDMapper for tgt_xxxx resolution
        """
        if not self.enabled:
            return

        # Initialize PC knowledge
        pc_agent_ids = set()
        for pc in player_agents:
            aid = getattr(pc, 'agent_id', None)
            if aid:
                pc_agent_ids.add(aid)

        for pc in player_agents:
            aid = getattr(pc, 'agent_id', None)
            if not aid:
                continue

            faction = 'Unknown'
            if hasattr(pc, 'character_state'):
                faction = getattr(pc.character_state, 'faction', 'Unknown')

            knowledge = self.initialize_agent(
                agent_id=aid,
                agent_type="player",
                agent_faction=faction,
                allied_agent_ids=pc_agent_ids - {aid}
            )

            # PCs know each other
            for other_pc in player_agents:
                other_aid = getattr(other_pc, 'agent_id', None)
                if other_aid and other_aid != aid:
                    other_name = 'Unknown'
                    other_faction = 'Unknown'
                    if hasattr(other_pc, 'character_state'):
                        other_name = getattr(other_pc.character_state, 'name', 'Unknown')
                        other_faction = getattr(other_pc.character_state, 'faction', 'Unknown')

                    other_tid = target_id_mapper.get_target_id(other_aid) or other_aid
                    knowledge.identify_ally(other_tid, other_name, other_faction)

        # Initialize enemy knowledge
        for enemy in enemy_agents:
            aid = getattr(enemy, 'agent_id', None)
            if not aid:
                continue

            faction = getattr(enemy, 'faction', 'Unknown')
            same_faction_ids = set()
            for other_enemy in enemy_agents:
                other_aid = getattr(other_enemy, 'agent_id', None)
                other_faction = getattr(other_enemy, 'faction', 'Unknown')
                if other_aid and other_aid != aid and other_faction == faction:
                    same_faction_ids.add(other_aid)

            knowledge = self.initialize_agent(
                agent_id=aid,
                agent_type="enemy",
                agent_faction=faction,
                allied_agent_ids=same_faction_ids
            )

            # Enemies know their faction allies
            for other_enemy in enemy_agents:
                other_aid = getattr(other_enemy, 'agent_id', None)
                if other_aid and other_aid in same_faction_ids:
                    other_tid = target_id_mapper.get_target_id(other_aid) or other_aid
                    knowledge.identify_ally(
                        other_tid,
                        getattr(other_enemy, 'name', 'Unknown'),
                        getattr(other_enemy, 'faction', 'Unknown')
                    )

            # All other targets start as SILHOUETTE at best
            for pc in player_agents:
                pc_aid = getattr(pc, 'agent_id', None)
                if pc_aid:
                    pc_tid = target_id_mapper.get_target_id(pc_aid) or pc_aid
                    knowledge.update_identity(
                        target_id=pc_tid,
                        level=IdentificationLevel.SILHOUETTE,
                        source="visual_initial"
                    )

        # Initialize NPC knowledge
        for npc in npc_agents:
            aid = getattr(npc, 'agent_id', None)
            if not aid:
                continue

            knowledge = self.initialize_agent(
                agent_id=aid,
                agent_type="npc",
                agent_faction=getattr(npc, 'faction', 'Unknown')
            )
            # NPCs start with no identification of anyone
            # They may know locals (other NPCs) but not PCs or enemies

    def attempt_identification(
        self,
        observer_agent_id: str,
        target_id: str,
        target_agent,
        distance: str = "Near",
        modifiers: int = 0,
        target_id_mapper=None
    ) -> Dict[str, Any]:
        """
        Attempt to identify an unknown target.

        Uses YAGS formula: Perception x Awareness + d20 + modifiers vs DC.

        DC based on distance:
        - Engaged/Melee: DC 10
        - Near: DC 15
        - Far: DC 20
        - Extreme: DC 25

        On success, identification level increases based on margin:
        - Margin 0-4: PARTIAL (faction visible)
        - Margin 5-9: IDENTIFIED (name + faction)
        - Margin 10+: DETAILED (name, faction, capabilities)

        Args:
            observer_agent_id: Who is trying to identify
            target_id: tgt_xxxx of the target
            target_agent: The actual target agent object
            distance: Range band ("Engaged", "Near", "Far", "Extreme")
            modifiers: Situational modifiers
            target_id_mapper: For resolving IDs

        Returns:
            Dict with success, level achieved, roll details
        """
        import random
        from .mechanics import _get_attribute, _get_skill

        knowledge = self.get_knowledge(observer_agent_id)
        if not knowledge:
            return {'success': False, 'reason': 'Observer not tracked'}

        # Get observer stats
        observer = None
        if target_id_mapper:
            # Try to find observer agent
            observer_tid = target_id_mapper.get_target_id(observer_agent_id)
            if observer_tid:
                observer = target_id_mapper.resolve_target(observer_tid)

        # Fallback: use default stats
        perception = 3
        awareness = 0
        if observer:
            perception = _get_attribute(observer, 'Perception', 3)
            awareness = _get_skill(observer, 'Awareness', 0)

        # DC based on distance
        dc_map = {
            "Engaged": 10, "Melee": 10,
            "Near": 15,
            "Far": 20,
            "Extreme": 25,
        }
        dc = dc_map.get(distance, 15)

        # Roll
        unskilled_penalty = -5 if awareness == 0 else 0
        d20 = random.randint(1, 20)
        roll_total = (perception * awareness) + d20 + modifiers + unskilled_penalty
        roll_total = max(1, roll_total)

        success = roll_total >= dc
        margin = roll_total - dc

        result = {
            'success': success,
            'roll': roll_total,
            'd20': d20,
            'dc': dc,
            'margin': margin,
            'formula': f"Per {perception} x Awareness {awareness} + d20({d20}) = {roll_total} vs DC {dc}",
        }

        if success:
            # Determine identification level based on margin
            if margin >= 10:
                level = IdentificationLevel.DETAILED
            elif margin >= 5:
                level = IdentificationLevel.IDENTIFIED
            else:
                level = IdentificationLevel.PARTIAL

            # Extract target info
            target_name = getattr(target_agent, 'name', None)
            if not target_name and hasattr(target_agent, 'character_state'):
                target_name = getattr(target_agent.character_state, 'name', None)

            target_faction = getattr(target_agent, 'faction', None)
            if not target_faction and hasattr(target_agent, 'character_state'):
                target_faction = getattr(target_agent.character_state, 'faction', None)

            # Update knowledge
            knowledge.update_identity(
                target_id=target_id,
                level=level,
                faction=target_faction,
                name=target_name if level >= IdentificationLevel.IDENTIFIED else None,
                source="perception_check"
            )

            result['level'] = level.value
            result['identified_faction'] = target_faction
            result['identified_name'] = target_name if level >= IdentificationLevel.IDENTIFIED else None
        else:
            result['level'] = 'failed'

        return result
```

### Phase 2: Agent-Specific Combatant Lists

#### 2.1 Per-Agent Combatant List Builder

**File:** `scripts/aeonisk/multiagent/dm.py`

Replace the single combatant list with agent-specific views. The DM still sees
everything, but when building prompts for agents, filter based on their knowledge:

```python
def _build_agent_combatant_list(
    self,
    observer_agent_id: str,
    target_id_mapper,
    identity_tracker: Optional[IdentityTracker] = None
) -> str:
    """
    Build combatant list filtered by observer's knowledge.

    DM sees full information. Other agents see only what they have identified.

    Args:
        observer_agent_id: Who is viewing the list ("dm" for full view)
        target_id_mapper: TargetIDMapper instance
        identity_tracker: IdentityTracker instance (None = show everything)

    Returns:
        Formatted combatant list string
    """
    if not target_id_mapper or not target_id_mapper.enabled:
        return ""

    all_target_ids = target_id_mapper.get_all_target_ids()
    if not all_target_ids:
        return ""

    combatant_lines = []

    for tid in sorted(all_target_ids):
        info = target_id_mapper.get_combatant_info(tid)
        if not info:
            continue

        if observer_agent_id == "dm" or not identity_tracker or \
           not identity_tracker.enabled:
            # DM or IFF disabled: show full info (current behavior)
            combatant_lines.append(self._format_full_combatant(tid, info))
        else:
            # Agent-specific view based on knowledge
            knowledge = identity_tracker.get_knowledge(observer_agent_id)
            if knowledge:
                known = knowledge.get_identity(tid)
                combatant_lines.append(
                    f"  - {known.get_display_string()}"
                )
            else:
                # No knowledge tracking for this agent, show minimal
                combatant_lines.append(f"  - [{tid}] Unknown contact")

    if not combatant_lines:
        return ""

    header = "\n\n**DETECTED CONTACTS:**\n"
    return header + "\n".join(combatant_lines)
```

#### 2.2 Enemy Prompt -- Knowledge-Filtered Target Info

**File:** `scripts/aeonisk/multiagent/enemy_prompts.py`

Modify `_format_pc_target_info()` to use the enemy's knowledge state:

```python
def _format_pc_target_info_iff(
    enemy: EnemyAgent,
    pc,
    identity_tracker: Optional[IdentityTracker],
    target_id_mapper
) -> str:
    """Format PC target info filtered by enemy's knowledge."""
    pc_agent_id = getattr(pc, 'agent_id', None)
    pc_tid = target_id_mapper.get_target_id(pc_agent_id) if pc_agent_id else None

    if not pc_tid:
        return ""

    # Check enemy's knowledge of this target
    if identity_tracker and identity_tracker.enabled:
        knowledge = identity_tracker.get_knowledge(enemy.agent_id)
        if knowledge:
            known = knowledge.get_identity(pc_tid)

            if known.identification_level == IdentificationLevel.UNKNOWN:
                return f"""- [{pc_tid}] Unknown contact
  Position: {_get_position(pc, enemy)}
  Status: Unidentified (use Scan to identify)"""

            elif known.identification_level == IdentificationLevel.SILHOUETTE:
                weapons_visible = known.visible_weapons
                weapon_str = ", ".join(weapons_visible) if weapons_visible else "unknown"
                return f"""- [{pc_tid}] Humanoid ({weapon_str})
  Position: {_get_position(pc, enemy)}
  Faction: Unknown
  Status: Silhouette only (use Scan to identify)"""

            elif known.identification_level == IdentificationLevel.PARTIAL:
                return f"""- [{pc_tid}] {known.known_faction or 'Unknown'} operative
  Position: {_get_position(pc, enemy)}
  Faction: {known.known_faction or 'Unknown'}
  Status: Partially identified"""

            # IDENTIFIED or DETAILED: show full info (current behavior)

    # Fallback: show full info (IFF disabled or fully identified)
    return _format_pc_target_info(enemy, pc)
```

### Phase 3: Selective Intel Sharing

#### 3.1 Extend SharedIntel for Selective Distribution

**File:** `scripts/aeonisk/multiagent/enemy_agent.py`

```python
@dataclass
class IntelItem:
    """Single piece of shared tactical intelligence."""
    source_agent: str
    intel: str
    round: int
    recipients: Optional[Set[str]] = None  # NEW: None = broadcast to all allies
                                            # Set = only these agent_ids receive

class SharedIntel:
    def add_intel(
        self,
        source_agent: str,
        intel: str,
        round_num: int,
        recipients: Optional[Set[str]] = None
    ):
        """Add intelligence with optional recipient filtering."""
        if intel and intel.strip():
            item = IntelItem(
                source_agent=source_agent,
                intel=intel.strip(),
                round=round_num,
                recipients=recipients
            )
            self.intel_pool.append(item)

    def get_recent_intel_for_agent(
        self,
        agent_id: str,
        current_round: int,
        lookback: int = 2
    ) -> List[str]:
        """Get intel visible to a specific agent."""
        recent = []
        for item in self.intel_pool:
            if current_round - item.round > lookback:
                continue
            # Check if this agent is a recipient
            if item.recipients is None or agent_id in item.recipients:
                recent.append(f"[ALLY {item.source_agent}] {item.intel}")
        return recent
```

#### 3.2 Extend EnemyDecision for Selective Sharing

**File:** `scripts/aeonisk/multiagent/schemas/enemy_decision.py`

```python
class EnemyDecision(BaseModel):
    # ... existing fields ...

    shared_intel: Optional[str] = Field(
        default=None,
        max_length=300,
        description="Intel to share with allies"
    )

    intel_recipients: Optional[List[str]] = Field(
        default=None,
        description=(
            "Specific ally agent_ids to receive intel. "
            "None = broadcast to all allies. "
            "Example: ['enemy_sniper_b2e1'] to share only with the sniper."
        )
    )
```

#### 3.3 Identification Sharing Action

**File:** `scripts/aeonisk/multiagent/schemas/player_action.py`

Add a new field to `SocialAction` or create a new action for sharing intel:

```python
class SocialAction(PlayerActionBase):
    # ... existing fields ...

    share_identification: Optional[Dict[str, str]] = Field(
        default=None,
        description=(
            "Share target identification with specific allies. "
            "Maps target_id to ally_agent_id. "
            "Example: {'tgt_7a3f': 'player_02'} shares identity of tgt_7a3f "
            "with player_02."
        )
    )
```

### Phase 4: Auto-Identification Triggers

#### 4.1 Engagement-Based Identification

When an agent attacks or is attacked by a target, automatic identification occurs:

```python
# In combat resolution processing
def auto_identify_on_engagement(
    attacker_id: str,
    target_id: str,
    target_agent,
    identity_tracker: IdentityTracker,
    round_num: int
):
    """
    Auto-identify targets on combat engagement.

    When you attack someone or are attacked, you get at least PARTIAL
    identification (you can see them up close in combat).
    """
    if not identity_tracker or not identity_tracker.enabled:
        return

    knowledge = identity_tracker.get_knowledge(attacker_id)
    if not knowledge:
        return

    target_name = getattr(target_agent, 'name', None)
    if not target_name and hasattr(target_agent, 'character_state'):
        target_name = getattr(target_agent.character_state, 'name', None)

    target_faction = getattr(target_agent, 'faction', None)
    if not target_faction and hasattr(target_agent, 'character_state'):
        target_faction = getattr(target_agent.character_state, 'faction', None)

    # Combat engagement = at least IDENTIFIED level
    knowledge.update_identity(
        target_id=target_id,
        level=IdentificationLevel.IDENTIFIED,
        faction=target_faction,
        name=target_name,
        source="combat_engagement",
        round_num=round_num
    )
```

#### 4.2 Passive Identification at Close Range

At Engaged/Melee range, agents automatically get SILHOUETTE or PARTIAL identification
without a check:

```python
def passive_identification_at_range(
    observer_id: str,
    target_id: str,
    target_agent,
    distance: str,
    identity_tracker: IdentityTracker,
    round_num: int
):
    """
    Passive identification based on proximity.

    Engaged/Melee: automatic PARTIAL (can see face, insignia)
    Near: automatic SILHOUETTE (can see weapons, general build)
    Far/Extreme: no automatic identification
    """
    if not identity_tracker or not identity_tracker.enabled:
        return

    if distance in ("Engaged", "Melee"):
        level = IdentificationLevel.PARTIAL
    elif distance == "Near":
        level = IdentificationLevel.SILHOUETTE
    else:
        return  # No passive identification at Far/Extreme

    knowledge = identity_tracker.get_knowledge(observer_id)
    if not knowledge:
        return

    faction = getattr(target_agent, 'faction', None)
    if not faction and hasattr(target_agent, 'character_state'):
        faction = getattr(target_agent.character_state, 'faction', None)

    knowledge.update_identity(
        target_id=target_id,
        level=level,
        faction=faction if level >= IdentificationLevel.PARTIAL else None,
        source="passive_proximity",
        round_num=round_num
    )
```

### Phase 5: Prompt Updates

#### 5.1 Enemy Prompt -- IFF Guidance

**File:** `scripts/aeonisk/multiagent/prompts/claude/en/enemy.yaml`

Add IFF section:

```yaml
iff_guidance: |-
  ## Identification Friend or Foe (IFF)

  You may NOT know who all contacts are. Your target list shows only what you
  have identified:

  - **Unknown contact:** No information. Could be hostile, neutral, or friendly.
    DO NOT attack unknown contacts unless rules of engagement permit.
  - **Silhouette:** You can see their general shape and weapons. No faction ID.
  - **Partial:** You can see faction insignia. You know their allegiance.
  - **Identified:** Full name and faction known. Standard targeting applies.

  **To identify unknown contacts:**
  - Use 'Scan' as your minor_action
  - Engage at close range (automatic identification)
  - Receive intel from allies (via shared_intel)

  **Rules of Engagement:**
  - DO NOT fire on unidentified contacts unless fired upon first
  - Allies must be identified before providing support
  - Share identification intel with allies when you discover it
```

#### 5.2 Player Prompt -- IFF Awareness

```yaml
iff_awareness: |-
  ## Battlefield Awareness

  You know your party members (full identification from start).
  Other contacts start as Unknown and must be identified.

  **Identification methods:**
  - PERCEPTION action with search focus
  - Combat engagement (auto-identifies on attack/defense)
  - Close proximity (Near range = silhouette, Melee = partial)
  - Intel sharing from allies

  **Share intel:** Use SOCIAL action with share_identification field to tell
  allies about identified targets.
```

---

## Files to Modify

| File | Change | Lines |
|------|--------|-------|
| `identity_tracking.py` | NEW FILE: IdentityTracker, AgentKnowledge, KnownIdentity | N/A |
| `dm.py` | Agent-specific combatant list builder | Lines 7536-7578 |
| `dm.py` | Initialize IdentityTracker at combat start | Combat init |
| `dm.py` | Auto-identify on combat engagement | Resolution processing |
| `dm.py` | Passive identification at range each round | Round start |
| `enemy_agent.py` | Extend IntelItem with recipients, SharedIntel with agent filtering | Lines 671-728 |
| `enemy_combat.py` | Use agent-specific intel retrieval | Lines 592, 764, 788 |
| `enemy_prompts.py` | Knowledge-filtered target info | Lines 440-483 |
| `enemy_prompts.py` | IFF guidance section | New section |
| `schemas/enemy_decision.py` | Add `intel_recipients` field | After line 122 |
| `schemas/player_action.py` | Add `share_identification` to SocialAction | After line 333 |
| `target_ids.py` | Store IdentityTracker reference | Constructor |
| `mechanics.py` | **USE** `_get_attribute`, `_get_skill` helpers (defined in Spec 05 — do NOT redefine) | Import only |
| `awareness.py` | Extend for identity-based awareness | New functions |
| `session.py` | Initialize IdentityTracker with session config | Session setup |
| `prompts/.../enemy.yaml` | IFF guidance section | New section |
| `prompts/.../player.yaml` | IFF awareness section | New section |

---

## Test Plan

### Unit Tests

**File:** `tests/unit/test_iff_roe.py`

```python
class TestKnownIdentity:
    """KnownIdentity display string formatting."""

    def test_unknown_display(self):
        ki = KnownIdentity(target_id="tgt_7a3f")
        assert "Unknown contact" in ki.get_display_string()

    def test_silhouette_display(self):
        ki = KnownIdentity(
            target_id="tgt_7a3f",
            identification_level=IdentificationLevel.SILHOUETTE,
            visible_weapons=["rifle"]
        )
        assert "Humanoid" in ki.get_display_string()
        assert "rifle" in ki.get_display_string()

    def test_partial_display(self):
        ki = KnownIdentity(
            target_id="tgt_7a3f",
            identification_level=IdentificationLevel.PARTIAL,
            known_faction="ACG"
        )
        assert "ACG" in ki.get_display_string()

    def test_identified_display(self):
        ki = KnownIdentity(
            target_id="tgt_7a3f",
            identification_level=IdentificationLevel.IDENTIFIED,
            known_name="ACG Enforcer Alpha",
            known_faction="ACG"
        )
        assert "ACG Enforcer Alpha" in ki.get_display_string()
        assert "ACG" in ki.get_display_string()


class TestAgentKnowledge:
    """Per-agent knowledge tracking."""

    def test_default_unknown(self):
        """Untracked targets should return UNKNOWN."""
        knowledge = AgentKnowledge(
            agent_id="enemy_01", agent_type="enemy", agent_faction="ACG"
        )
        identity = knowledge.get_identity("tgt_7a3f")
        assert identity.identification_level == IdentificationLevel.UNKNOWN

    def test_update_upgrades_only(self):
        """Identification level should only increase, never decrease."""
        knowledge = AgentKnowledge(
            agent_id="enemy_01", agent_type="enemy", agent_faction="ACG"
        )
        knowledge.update_identity("tgt_7a3f", IdentificationLevel.IDENTIFIED,
                                  name="Ash Vex", faction="Freeborn")
        knowledge.update_identity("tgt_7a3f", IdentificationLevel.SILHOUETTE)
        # Should still be IDENTIFIED (not downgraded)
        identity = knowledge.get_identity("tgt_7a3f")
        assert identity.identification_level == IdentificationLevel.IDENTIFIED

    def test_ally_identification(self):
        """Allies should be fully identified."""
        knowledge = AgentKnowledge(
            agent_id="enemy_01", agent_type="enemy", agent_faction="ACG"
        )
        knowledge.identify_ally("tgt_b2e1", "ACG Sniper", "ACG")
        identity = knowledge.get_identity("tgt_b2e1")
        assert identity.identification_level == IdentificationLevel.DETAILED
        assert identity.known_name == "ACG Sniper"

    def test_intel_reception(self):
        """Receiving intel should update knowledge."""
        knowledge = AgentKnowledge(
            agent_id="enemy_01", agent_type="enemy", agent_faction="ACG"
        )
        knowledge.receive_intel(
            "tgt_7a3f",
            IdentificationLevel.PARTIAL,
            faction="Freeborn",
            source_agent="enemy_02"
        )
        identity = knowledge.get_identity("tgt_7a3f")
        assert identity.identification_level == IdentificationLevel.PARTIAL
        assert identity.known_faction == "Freeborn"


class TestIdentityTracker:
    """Central identity tracking system."""

    def test_pc_knows_other_pcs(self):
        """PCs should know all other PCs at start."""
        tracker = IdentityTracker()
        tracker.enable()

        pc1 = MockPlayer(agent_id="p1", name="Ash", faction="Freeborn")
        pc2 = MockPlayer(agent_id="p2", name="Echo", faction="Freeborn")
        mapper = MockTargetIDMapper({"p1": "tgt_1", "p2": "tgt_2"})

        tracker.initialize_combat([pc1, pc2], [], [], mapper)

        k1 = tracker.get_knowledge("p1")
        identity = k1.get_identity("tgt_2")
        assert identity.identification_level == IdentificationLevel.DETAILED
        assert identity.known_name == "Echo"

    def test_enemy_does_not_know_pcs(self):
        """Enemies should start with SILHOUETTE for PCs."""
        tracker = IdentityTracker()
        tracker.enable()

        pc = MockPlayer(agent_id="p1", name="Ash", faction="Freeborn")
        enemy = MockEnemy(agent_id="e1", name="Grunt", faction="ACG")
        mapper = MockTargetIDMapper({"p1": "tgt_1", "e1": "tgt_2"})

        tracker.initialize_combat([pc], [enemy], [], mapper)

        k = tracker.get_knowledge("e1")
        identity = k.get_identity("tgt_1")
        assert identity.identification_level == IdentificationLevel.SILHOUETTE
        assert identity.known_name is None

    def test_enemy_knows_faction_allies(self):
        """Enemies from same faction should know each other."""
        tracker = IdentityTracker()
        tracker.enable()

        e1 = MockEnemy(agent_id="e1", name="Grunt A", faction="ACG")
        e2 = MockEnemy(agent_id="e2", name="Grunt B", faction="ACG")
        mapper = MockTargetIDMapper({"e1": "tgt_1", "e2": "tgt_2"})

        tracker.initialize_combat([], [e1, e2], [], mapper)

        k = tracker.get_knowledge("e1")
        identity = k.get_identity("tgt_2")
        assert identity.identification_level == IdentificationLevel.DETAILED

    def test_identification_attempt(self):
        """Identification check should upgrade knowledge on success."""
        tracker = IdentityTracker()
        tracker.enable()

        enemy = MockEnemy(agent_id="e1", name="Grunt", faction="ACG",
                          attributes={'Perception': 4}, skills={'Awareness': 3})
        pc = MockPlayer(agent_id="p1", name="Ash", faction="Freeborn")
        mapper = MockTargetIDMapper({"e1": "tgt_1", "p1": "tgt_2"})

        tracker.initialize_combat([pc], [enemy], [], mapper)

        # Attempt identification (result depends on d20)
        result = tracker.attempt_identification(
            observer_agent_id="e1",
            target_id="tgt_2",
            target_agent=pc,
            distance="Near",
            target_id_mapper=mapper
        )
        assert 'success' in result
        assert 'roll' in result


class TestSelectiveIntel:
    """Selective intel sharing tests."""

    def test_broadcast_intel_visible_to_all(self):
        """Intel without recipients should be visible to all allies."""
        intel = SharedIntel()
        intel.add_intel("e1", "Target spotted at Near-PC", round_num=1)
        result = intel.get_recent_intel_for_agent("e2", current_round=1)
        assert len(result) == 1

    def test_selective_intel_only_to_recipients(self):
        """Intel with recipients should only be visible to those agents."""
        intel = SharedIntel()
        intel.add_intel("e1", "Secret info", round_num=1,
                        recipients={"e2"})
        result_e2 = intel.get_recent_intel_for_agent("e2", current_round=1)
        result_e3 = intel.get_recent_intel_for_agent("e3", current_round=1)
        assert len(result_e2) == 1
        assert len(result_e3) == 0


class TestAutoIdentification:
    """Automatic identification triggers."""

    def test_combat_engagement_identifies(self):
        """Attacking a target should auto-identify them."""
        tracker = IdentityTracker()
        tracker.enable()

        enemy = MockEnemy(agent_id="e1", name="Grunt", faction="ACG")
        pc = MockPlayer(agent_id="p1", name="Ash", faction="Freeborn")
        mapper = MockTargetIDMapper({"e1": "tgt_1", "p1": "tgt_2"})

        tracker.initialize_combat([pc], [enemy], [], mapper)

        auto_identify_on_engagement(
            attacker_id="e1",
            target_id="tgt_2",
            target_agent=pc,
            identity_tracker=tracker,
            round_num=1
        )

        k = tracker.get_knowledge("e1")
        identity = k.get_identity("tgt_2")
        assert identity.identification_level >= IdentificationLevel.IDENTIFIED

    def test_close_range_passive_identification(self):
        """Being at Melee range should auto-grant PARTIAL identification."""
        tracker = IdentityTracker()
        tracker.enable()

        enemy = MockEnemy(agent_id="e1", name="Grunt", faction="ACG")
        pc = MockPlayer(agent_id="p1", name="Ash", faction="Freeborn")
        mapper = MockTargetIDMapper({"e1": "tgt_1", "p1": "tgt_2"})

        tracker.initialize_combat([pc], [enemy], [], mapper)

        passive_identification_at_range(
            observer_id="e1",
            target_id="tgt_2",
            target_agent=pc,
            distance="Melee",
            identity_tracker=tracker,
            round_num=1
        )

        k = tracker.get_knowledge("e1")
        identity = k.get_identity("tgt_2")
        assert identity.identification_level >= IdentificationLevel.PARTIAL
```

### Integration Tests

**File:** `tests/integration/test_iff_integration.py`

1. **Full IFF combat round:** Initialize combat with IFF enabled, verify enemies see
   "Unknown contact" for PCs in their first prompt.
2. **Scan identifies target:** Enemy uses Scan, verify identification level increases
   in next round's prompt.
3. **Combat engagement auto-identifies:** After enemy attacks PC, verify full
   identification in subsequent rounds.
4. **Selective intel:** Enemy A shares intel with Enemy B only. Verify Enemy C does
   not receive it.
5. **PC identification sharing:** PC identifies enemy, shares via social action,
   verify other PC's knowledge updates.

---

## Migration Notes

- `identity_tracking.py` is a new file -- no existing code to break.
- SharedIntel `add_intel()` gains optional `recipients` parameter with default=None
  (broadcast), maintaining full backward compatibility.
- EnemyDecision gains optional `intel_recipients` field with default=None.
- SocialAction gains optional `share_identification` field with default=None.
- IdentityTracker has an `enabled` flag (default False). When disabled, all existing
  behavior is preserved -- combatant lists show full information, SharedIntel
  broadcasts globally.
- Session config should add `"iff_enabled": true` to enable the system.

---

## Open Questions

1. **Session config opt-in.** Should IFF be enabled globally or per-session?
   **Recommendation:** Per-session via `"iff_enabled": true` in session config.
   Default to false for backward compatibility. Enable for IFF training data
   generation sessions.

2. **Reinforcement knowledge.** When enemies spawn mid-combat, what do they know?
   **Recommendation:** Reinforcements start with UNKNOWN for all targets. They must
   identify or receive intel from existing allies. This rewards players who eliminate
   communication channels.

3. **NPC identification.** Do NPCs identify other agents?
   **Recommendation:** NPCs know local NPCs (same area) but not PCs or enemies.
   Friendly NPCs may provide identification intel to PCs ("Those are ACG enforcers,
   be careful!") as a dialogue action.

4. **IFF and stealth interaction.** If a hidden agent is detected, does detection
   also provide identification?
   **Recommendation:** Detection (spec 05) reveals presence but not identity. A
   separate identification check is needed. However, detection at close range (Melee)
   auto-grants PARTIAL identification.

5. **Friendly fire prevention.** In full IFF mode, agents might attack unidentified
   allies. Should the system prevent this?
   **Recommendation:** No. Friendly fire from misidentification is a valid ML training
   signal. The ROE (Rules of Engagement) prompt should discourage it, but the system
   should not mechanically prevent it.

6. **Performance impact.** Per-agent combatant lists mean building N different lists
   per round instead of 1. With 4 PCs + 4 enemies + NPCs, this could be 10+ lists.
   **Recommendation:** Only build agent-specific lists when IFF is enabled. Cache the
   DM's full list and filter it per-agent rather than rebuilding from scratch.

7. **Enemy faction diversity.** If enemies from different factions are present, do
   they know each other?
   **Recommendation:** Enemies from DIFFERENT factions start as UNKNOWN to each other.
   Only same-faction enemies are auto-identified as allies. This enables three-way
   combat scenarios.

8. **Identification persistence.** Does identification carry across combat encounters
   in the same session?
   **Recommendation:** Yes. Once identified, a target remains identified for the
   entire session. This rewards early investment in identification.
