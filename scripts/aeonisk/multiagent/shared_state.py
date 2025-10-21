"""Shared state tooling for coordinating multi-agent Aeonisk sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .mechanics import MechanicsEngine, SceneClock
    from .action_schema import ActionValidator
    from .knowledge_retrieval import KnowledgeRetrieval


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

    # Party-wide shared knowledge to reduce repetitive actions
    party_discoveries: List[str] = field(default_factory=list)

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

    def add_discovery(self, discovery: str) -> None:
        """Add to party's shared knowledge pool."""
        if discovery and discovery not in self.party_discoveries:
            self.party_discoveries.append(discovery)
            # Keep only the most recent 10 discoveries
            if len(self.party_discoveries) > 10:
                self.party_discoveries = self.party_discoveries[-10:]

    def get_recent_discoveries(self, limit: int = 5) -> List[str]:
        """Get the most recent party discoveries."""
        return self.party_discoveries[-limit:] if self.party_discoveries else []

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
