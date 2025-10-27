"""Shared state tooling for coordinating multi-agent Aeonisk sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .mechanics import MechanicsEngine, SceneClock
    from .action_schema import ActionValidator
    from .knowledge_retrieval import KnowledgeRetrieval
    from .enemy_combat import EnemyCombatManager
    from .combat_ids import CombatIDMapper


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
    combat_id_mapper: Optional['CombatIDMapper'] = None

    # Session configuration (for accessing config flags like free_targeting_mode)
    session_config: Dict[str, Any] = field(default_factory=dict)

    # Player agents (for ally buff targeting)
    player_agents: List[Any] = field(default_factory=list)

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
            self.mechanics_engine = MechanicsEngine()

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

    def get_combat_id_mapper(self) -> 'CombatIDMapper':
        """Get or create combat ID mapper."""
        if self.combat_id_mapper is None:
            from .combat_ids import CombatIDMapper
            self.combat_id_mapper = CombatIDMapper()
        return self.combat_id_mapper

    def get_all_players(self) -> List[Any]:
        """Get all registered player agents."""
        return self.player_agents
