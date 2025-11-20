"""Shared state tooling for coordinating multi-agent Aeonisk sessions."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .mechanics import MechanicsEngine, SceneClock
    from .action_schema import ActionValidator
    from .knowledge_retrieval import KnowledgeRetrieval
    from .enemy_combat import EnemyCombatManager
    from .target_ids import TargetIDMapper


def generate_altar_id() -> str:
    """
    Generate unique altar ID: alt_xxxx

    Format: alt_ + 4 random alphanumeric characters
    Example: alt_r8k3
    """
    import string
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"alt_{suffix}"


class AltarType(Enum):
    """Types of ritual altars in Aeonisk."""
    RITUAL_ALTAR = "ritual_altar"  # Generic ritual space
    NEXUS_ALTAR = "nexus_altar"  # Sovereign Nexus sanctums (high quality, SC gated)
    FREEBORN_ALTAR = "freeborn_altar"  # Neutral Zone markets (moderate quality, open access)
    BLACK_MARKET_ALTAR = "black_market_altar"  # Hidden altars (low quality, risky, accepts Hollows)
    ABANDONED_ALTAR = "abandoned_altar"  # Discovered altars (random quality, contested)


@dataclass
class Altar:
    """
    Represents a ritual altar that provides bonuses to attunement rituals.

    Altars are infrastructure (not vendors) that assist player-performed rituals.
    """
    altar_type: AltarType
    quality: int  # 1-10, determines bonus
    location: str
    altar_id: Optional[str] = None

    def __post_init__(self):
        """Auto-generate altar_id if not provided."""
        if self.altar_id is None:
            self.altar_id = generate_altar_id()

    def get_ritual_bonus(self) -> int:
        """
        Get ritual bonus based on altar quality.

        Quality 1-3: +1 bonus
        Quality 4-7: +2 bonus
        Quality 8-10: +3 bonus
        """
        if 1 <= self.quality <= 3:
            return 1
        elif 4 <= self.quality <= 7:
            return 2
        elif 8 <= self.quality <= 10:
            return 3
        else:
            # Invalid quality, default to +1
            logger.warning(f"Altar {self.altar_id} has invalid quality {self.quality}, defaulting to +1 bonus")
            return 1


@dataclass
class VoidSpikeRecord:
    """Representation of a communal Void spike event."""

    reason: str
    severity: int = 1


@dataclass
class SharedState:
    """
    Track communal resources and game state accessible by all agents.
    Now integrated with mechanics engine and knowledge retrieval.
    """

    soulcredit_pool: int = 0
    void_spikes: List[VoidSpikeRecord] = field(default_factory=list)
    rituals: Dict[str, int] = field(default_factory=dict)
    soulcredit_history: List[Dict[str, Any]] = field(default_factory=list)
    soulcredit_floor: int = -4
    void_threshold: int = 4

    # New: mechanics integration
    mechanics_engine: Optional['MechanicsEngine'] = None
    action_validator: Optional['ActionValidator'] = None
    knowledge_retrieval: Optional['KnowledgeRetrieval'] = None
    enemy_combat: Optional['EnemyCombatManager'] = None
    target_id_mapper: Optional['TargetIDMapper'] = None

    # Session configuration (for accessing config flags like free_targeting_mode)
    session_config: Dict[str, Any] = field(default_factory=dict)

    # Player agents (for ally buff targeting)
    player_agents: List[Any] = field(default_factory=list)

    # NPC agents (non-combatant agents with simple LLM)
    npc_agents: List[Any] = field(default_factory=list)

    # Current vendors present in the scenario (persists across rounds until StoryAdvancement removes them)
    current_vendors: List[Any] = field(default_factory=list)

    # Current altars present in the scenario (ritual infrastructure for attunement)
    current_altars: List[Altar] = field(default_factory=list)

    # Party-wide shared knowledge to reduce repetitive actions
    # Each discovery is a dict with 'discovery' and 'character' keys
    party_discoveries: List[Dict[str, str]] = field(default_factory=list)

    # Track registered player characters for dialogue
    registered_players: List[Dict[str, str]] = field(default_factory=list)

    # Track recent scenarios for variety
    recent_scenarios: List[Dict[str, str]] = field(default_factory=list)

    # Track coordination bonuses (who gave bonus to whom)
    # Format: {recipient_agent_id: {'bonus': +2, 'from': giver_name, 'reason': 'shared intel'}}
    coordination_bonuses: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def adjust_soulcredit(self, delta: int, *, reason: Optional[str] = None) -> Optional[str]:
        """Adjust communal Soulcredit and return escalation cues if thresholds are crossed."""
        self.soulcredit_pool += delta
        self.soulcredit_history.append({
            "delta": delta,
            "reason": reason or "unspecified",
            "result": self.soulcredit_pool,
        })
        cue: Optional[str] = None
        if self.soulcredit_pool <= self.soulcredit_floor:
            cue = (
                "Escalate: communal Soulcredit deficit detected. Trigger debt collectors or bond audits."
            )
        return cue

    def record_void_spike(self, reason: str, severity: int = 1) -> Optional[str]:
        """Record a Void spike and emit guidance when the pool becomes volatile."""
        record = VoidSpikeRecord(reason=reason, severity=severity)
        self.void_spikes.append(record)

        total_severity = sum(spike.severity for spike in self.void_spikes)
        if total_severity >= self.void_threshold:
            return "Escalate Void fallout: introduce environmental warping or faction intervention."
        return None

    def advance_ritual(self, name: str, *, progress: int = 1) -> None:
        """Advance communal ritual progress."""
        self.rituals[name] = self.rituals.get(name, 0) + progress

    def add_discovery(self, discovery: str, character_name: str = None) -> None:
        """Add to party's shared knowledge pool with character attribution."""
        if not discovery:
            return

        # Check if this exact discovery already exists
        existing = [d for d in self.party_discoveries if d.get('discovery') == discovery]
        if not existing:
            self.party_discoveries.append({
                'discovery': discovery,
                'character': character_name or 'Unknown'
            })
            # Keep only the most recent 10 discoveries
            if len(self.party_discoveries) > 10:
                self.party_discoveries = self.party_discoveries[-10:]

    def get_recent_discoveries(self, limit: int = 5) -> List[Dict[str, str]]:
        """Get the most recent party discoveries with character attribution."""
        return self.party_discoveries[-limit:] if self.party_discoveries else []

    def register_player(self, agent_id: str, name: str, faction: str) -> None:
        """Register a player character for party awareness."""
        # Check if already registered
        for player in self.registered_players:
            if player['agent_id'] == agent_id:
                return
        self.registered_players.append({
            'agent_id': agent_id,
            'name': name,
            'faction': faction
        })

    def get_other_players(self, current_agent_id: str) -> List[str]:
        """Get names of other player characters (excluding current agent)."""
        return [p['name'] for p in self.registered_players if p['agent_id'] != current_agent_id]

    def grant_coordination_bonus(self, from_agent: str, from_name: str, to_name: str, reason: str = "coordination") -> bool:
        """
        Grant a +2 coordination bonus to another character.
        Returns True if successfully granted, False if target not found.
        """
        # Find the target agent_id from name
        target_agent = None
        for player in self.registered_players:
            if player['name'].lower() == to_name.lower():
                target_agent = player['agent_id']
                break

        if not target_agent:
            return False

        # Grant the bonus (replaces any existing bonus)
        self.coordination_bonuses[target_agent] = {
            'bonus': 2,
            'from': from_name,
            'reason': reason
        }
        print(f"✓ {from_name} granted +2 coordination bonus to {to_name} ({reason})")
        return True

    def consume_coordination_bonus(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Check if an agent has a coordination bonus and consume it.
        Returns the bonus dict if present, None otherwise.
        """
        if agent_id in self.coordination_bonuses:
            bonus = self.coordination_bonuses.pop(agent_id)
            return bonus
        return None

    def add_scenario(self, theme: str, location: str) -> None:
        """Record a scenario for variety tracking."""
        self.recent_scenarios.append({
            'theme': theme,
            'location': location
        })
        # Keep only last 5 scenarios
        if len(self.recent_scenarios) > 5:
            self.recent_scenarios = self.recent_scenarios[-5:]

    def load_dm_notes(self, notes_path: str = 'dm_notes.json') -> None:
        """Load DM notes from persistent storage."""
        from pathlib import Path
        import json

        if Path(notes_path).exists():
            try:
                with open(notes_path, 'r') as f:
                    notes = json.load(f)
                    self.recent_scenarios = notes.get('recent_scenarios', [])
            except Exception:
                pass  # Silent fail, start fresh

    def save_dm_notes(self, notes_path: str = 'dm_notes.json') -> None:
        """Save DM notes to persistent storage."""
        import json

        notes = {
            'recent_scenarios': self.recent_scenarios,
            'last_updated': str(__import__('datetime').datetime.now())
        }

        try:
            with open(notes_path, 'w') as f:
                json.dump(notes, f, indent=2)
        except Exception:
            pass  # Silent fail

    def get_recent_scenario_info(self) -> str:
        """Get formatted info about recent scenarios for variety prompting."""
        if not self.recent_scenarios:
            return ""

        themes = [s['theme'] for s in self.recent_scenarios]
        locations = [s['location'] for s in self.recent_scenarios]

        return f"""
**Recently Used (AVOID THESE):**
- Recent themes: {', '.join(themes)}
- Recent locations: {', '.join(locations)}

Generate something DIFFERENT from these recent scenarios.
"""

    def snapshot(self) -> Dict[str, Any]:
        """Return a serialisable snapshot for prompts or logging."""
        snapshot_data = {
            "soulcredit_pool": self.soulcredit_pool,
            "soulcredit_history": list(self.soulcredit_history),
            "void_spikes": [record.__dict__ for record in self.void_spikes],
            "rituals": dict(self.rituals),
        }

        # Add mechanics state if available
        if self.mechanics_engine:
            snapshot_data['mechanics'] = self.mechanics_engine.get_state_summary()

        return snapshot_data

    def initialize_mechanics(self):
        """Initialize mechanics systems if not already done."""
        if self.mechanics_engine is None:
            from .mechanics import MechanicsEngine
            self.mechanics_engine = MechanicsEngine(shared_state=self)  # FIX: Pass self for vendor lookup

        if self.action_validator is None:
            from .action_schema import ActionValidator
            self.action_validator = ActionValidator()

        if self.knowledge_retrieval is None:
            from .knowledge_retrieval import KnowledgeRetrieval
            self.knowledge_retrieval = KnowledgeRetrieval()

    def get_mechanics_engine(self) -> 'MechanicsEngine':
        """Get or create mechanics engine."""
        if self.mechanics_engine is None:
            self.initialize_mechanics()
        return self.mechanics_engine

    def get_action_validator(self) -> 'ActionValidator':
        """Get or create action validator."""
        if self.action_validator is None:
            self.initialize_mechanics()
        return self.action_validator

    def get_knowledge_retrieval(self) -> 'KnowledgeRetrieval':
        """Get or create knowledge retrieval."""
        if self.knowledge_retrieval is None:
            self.initialize_mechanics()
        return self.knowledge_retrieval

    def get_target_id_mapper(self) -> 'TargetIDMapper':
        """Get or create target ID mapper."""
        if self.target_id_mapper is None:
            from .target_ids import TargetIDMapper
            self.target_id_mapper = TargetIDMapper()
        return self.target_id_mapper

    def get_all_players(self) -> List[Any]:
        """Get all registered player agents."""
        return self.player_agents

    # NPC agent management methods

    def add_npc(self, npc: Any) -> None:
        """
        Add NPC to shared state.

        Args:
            npc: NPCAgent instance to track
        """
        self.npc_agents.append(npc)

    def get_npc(self, agent_id: str) -> Optional[Any]:
        """
        Get NPC by agent_id.

        Args:
            agent_id: NPC agent ID (can be enemy_xxx format due to stable IDs)

        Returns:
            NPCAgent if found, None otherwise
        """
        for npc in self.npc_agents:
            if npc.agent_id == agent_id:
                return npc
        return None

    def remove_npc(self, agent_id: str) -> bool:
        """
        Remove NPC by agent_id.

        Args:
            agent_id: NPC agent ID to remove

        Returns:
            True if removed, False if not found
        """
        for i, npc in enumerate(self.npc_agents):
            if npc.agent_id == agent_id:
                self.npc_agents.pop(i)
                return True
        return False

    def remove_npc_object(self, npc: Any) -> bool:
        """
        Remove NPC by object reference.

        Args:
            npc: NPCAgent instance to remove

        Returns:
            True if removed, False if not found
        """
        try:
            self.npc_agents.remove(npc)
            return True
        except ValueError:
            return False

    def get_active_npcs(self) -> List[Any]:
        """
        Get all active NPCs (is_active=True).

        Returns:
            List of active NPCAgents
        """
        return [npc for npc in self.npc_agents if getattr(npc, 'is_active', True)]

    def get_npc_count(self) -> int:
        """Get total number of NPCs in state."""
        return len(self.npc_agents)

    def get_all_agents(self) -> List[Any]:
        """
        Get all agents across all pools (players, enemies, NPCs).

        Returns:
            List of all agent objects

        Note: Requires enemy_combat manager for enemy agents.
        """
        agents = list(self.player_agents) + list(self.npc_agents)
        if self.enemy_combat:
            # Add enemy agents if enemy combat manager exists
            enemy_agents = getattr(self.enemy_combat, 'enemy_agents', [])
            agents.extend(enemy_agents)
        return agents

    def get_agent_by_id(self, agent_id: str) -> Optional[Any]:
        """
        Get agent by ID, searching across all pools (player/enemy/npc).

        Critical for stable agent_id support - NPCs can have enemy_xxx IDs.

        Args:
            agent_id: Agent ID to find

        Returns:
            Agent object if found, None otherwise
        """
        # Check players
        for player in self.player_agents:
            if getattr(player, 'agent_id', None) == agent_id:
                return player

        # Check NPCs
        for npc in self.npc_agents:
            if npc.agent_id == agent_id:
                return npc

        # Check enemies
        if self.enemy_combat:
            enemy_agents = getattr(self.enemy_combat, 'enemy_agents', [])
            for enemy in enemy_agents:
                if getattr(enemy, 'agent_id', None) == agent_id:
                    return enemy

        return None

    # Vendor management methods

    def add_vendor(self, vendor: Any) -> None:
        """
        Add vendor to current scenario (persists across rounds).

        Prevents duplicates by name - if vendor with same name exists, skip.
        This prevents session.py + dm.py from both loading persistent_vendors.

        Args:
            vendor: Vendor instance from energy_economy.py
        """
        # Check if vendor with same name already exists
        for existing_vendor in self.current_vendors:
            if existing_vendor.name == vendor.name:
                # Skip duplicate - already have this vendor
                return

        self.current_vendors.append(vendor)

    def remove_vendor(self, vendor_name: str) -> bool:
        """
        Remove vendor by name (via StoryAdvancement.vendor_departures).

        Args:
            vendor_name: Name of vendor to remove

        Returns:
            True if removed, False if not found
        """
        for i, vendor in enumerate(self.current_vendors):
            if vendor.name == vendor_name:
                self.current_vendors.pop(i)
                return True
        return False

    def get_vendor(self, vendor_name: str) -> Optional[Any]:
        """
        Get vendor by name.

        Args:
            vendor_name: Name of vendor to find

        Returns:
            Vendor object if found, None otherwise
        """
        for vendor in self.current_vendors:
            if vendor.name == vendor_name:
                return vendor
        return None

    def get_npc_by_id(self, npc_id: str) -> Optional[Any]:
        """
        Get NPC by agent ID.

        Args:
            npc_id: NPC agent ID to find (e.g., "npc_civilian_a3f2")

        Returns:
            NPCAgent object if found, None otherwise
        """
        for npc in self.npc_agents:
            if hasattr(npc, 'agent_id') and npc.agent_id == npc_id:
                return npc
        return None

    def get_vendor_by_id(self, vendor_id: str) -> Optional[Any]:
        """
        Get vendor by ID (legacy vendor system).

        Args:
            vendor_id: Vendor ID to find (e.g., "vnd_a1b2")

        Returns:
            Vendor object if found, None otherwise
        """
        for vendor in self.current_vendors:
            if hasattr(vendor, 'vendor_id') and vendor.vendor_id == vendor_id:
                return vendor
        return None

    def get_npc_by_vendor_id(self, vendor_id: str) -> Optional[Any]:
        """
        Get NPC vendor by agent ID (unified vendor-NPC system).

        This supports the vendor→NPC unification where NPCs can act as vendors.
        Purchase system uses agent_id as the unified identifier (no separate vendor_id).

        Args:
            vendor_id: NPC agent ID to find (e.g., "npc_xxxx")

        Returns:
            NPCAgent object if found and is_vendor=True, None otherwise
        """
        for npc in self.npc_agents:
            if not hasattr(npc, 'is_vendor') or not npc.is_vendor:
                continue

            if hasattr(npc, 'agent_id') and npc.agent_id == vendor_id:
                return npc

        return None

    def get_all_vendors(self) -> List[Any]:
        """Get all vendors currently present in scenario."""
        return self.current_vendors

    def clear_vendors(self) -> None:
        """Remove all vendors from scenario."""
        self.current_vendors.clear()

    # Altar management methods

    def add_altar(self, altar: Altar) -> None:
        """
        Add an altar to the scenario.

        Args:
            altar: Altar instance

        Note:
            Prevents duplicates by altar_id
        """
        # Check if altar with same ID already exists
        for existing_altar in self.current_altars:
            if existing_altar.altar_id == altar.altar_id:
                # Skip duplicate
                return

        self.current_altars.append(altar)

    def remove_altar(self, altar_id: str) -> bool:
        """
        Remove altar by ID.

        Args:
            altar_id: ID of altar to remove (e.g., "alt_r8k3")

        Returns:
            True if removed, False if not found
        """
        for i, altar in enumerate(self.current_altars):
            if altar.altar_id == altar_id:
                self.current_altars.pop(i)
                return True
        return False

    def get_altar_by_id(self, altar_id: str) -> Optional[Altar]:
        """
        Get altar by ID.

        Args:
            altar_id: ID of altar to find (e.g., "alt_r8k3")

        Returns:
            Altar object if found, None otherwise
        """
        for altar in self.current_altars:
            if altar.altar_id == altar_id:
                return altar
        return None

    def get_all_altars(self) -> List[Altar]:
        """Get all altars currently present in scenario."""
        return self.current_altars

    def clear_altars(self) -> None:
        """Remove all altars from scenario."""
        self.current_altars.clear()

    # Enemy agent management methods (delegate to enemy_combat module)

    def get_enemy(self, agent_id: str) -> Optional[Any]:
        """
        Get enemy by agent_id (delegates to enemy_combat module).

        Args:
            agent_id: Enemy agent ID to find

        Returns:
            Enemy agent if found, None otherwise
        """
        if not self.enemy_combat:
            return None

        # enemy_combat stores enemies in enemy_agents list
        enemy_agents = getattr(self.enemy_combat, 'enemy_agents', [])
        for enemy in enemy_agents:
            if getattr(enemy, 'agent_id', None) == agent_id:
                return enemy
        return None

    def remove_enemy(self, agent_id: str) -> bool:
        """
        Remove enemy by agent_id (delegates to enemy_combat module).

        Args:
            agent_id: Enemy agent ID to remove

        Returns:
            True if removed, False if not found
        """
        if not self.enemy_combat:
            return False

        # enemy_combat stores enemies in enemy_agents list
        enemy_agents = getattr(self.enemy_combat, 'enemy_agents', [])
        for i, enemy in enumerate(enemy_agents):
            if getattr(enemy, 'agent_id', None) == agent_id:
                enemy_agents.pop(i)
                return True
        return False
