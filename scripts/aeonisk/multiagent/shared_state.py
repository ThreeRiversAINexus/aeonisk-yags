"""Shared state tooling for coordinating multi-agent Aeonisk sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VoidSpikeRecord:
    """Representation of a communal Void spike event."""

    reason: str
    severity: int = 1


@dataclass
class SharedState:
    """Track communal resources accessible by all agents."""

    soulcredit_pool: int = 0
    void_spikes: List[VoidSpikeRecord] = field(default_factory=list)
    rituals: Dict[str, int] = field(default_factory=dict)
    soulcredit_history: List[Dict[str, Any]] = field(default_factory=list)
    soulcredit_floor: int = -4
    void_threshold: int = 4

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

    def snapshot(self) -> Dict[str, Any]:
        """Return a serialisable snapshot for prompts or logging."""
        return {
            "soulcredit_pool": self.soulcredit_pool,
            "soulcredit_history": list(self.soulcredit_history),
            "void_spikes": [record.__dict__ for record in self.void_spikes],
            "rituals": dict(self.rituals),
        }
