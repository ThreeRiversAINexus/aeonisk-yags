"""Voice diversification utilities for the multi-agent orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Iterable, Optional


@dataclass(frozen=True)
class VoiceProfile:
    """Represents a narrative perspective with unique lexicon and motives."""

    key: str
    name: str
    faction_anchor: str
    lexicon_signature: str
    speech_markers: List[str]
    default_agenda: str

    def as_dict(self) -> Dict[str, str]:
        """Dictionary form for serialization or UI layers."""
        return {
            "key": self.key,
            "name": self.name,
            "faction_anchor": self.faction_anchor,
            "lexicon_signature": self.lexicon_signature,
            "speech_markers": ", ".join(self.speech_markers),
            "default_agenda": self.default_agenda,
        }


class VoiceLibrary:
    """Collection of curated voice profiles to avoid clone-like agents."""

    def __init__(self) -> None:
        self._profiles: Dict[str, VoiceProfile] = {
            "ritual_scholar": VoiceProfile(
                key="ritual_scholar",
                name="Professor Iriso Tal",
                faction_anchor="Luminant Seminary",
                lexicon_signature="axiom/annotation/petition",
                speech_markers=["quotes doctrine passages", "references ethnographic case studies"],
                default_agenda="Catalog and preserve ritual integrity while critiquing Void shortcuts.",
            ),
            "void_cultist": VoiceProfile(
                key="void_cultist",
                name="Whisper-Through-Basalt",
                faction_anchor="Sable Conclave",
                lexicon_signature="whisper/erosion/embrace",
                speech_markers=["describes sensations in present tense", "invites others to share corruption"],
                default_agenda="Seduce others toward controlled collapse and track Void spike resonance.",
            ),
            "freeborn_rebel": VoiceProfile(
                key="freeborn_rebel",
                name="Cato Emberline",
                faction_anchor="Freeborn Mutual Aid Cells",
                lexicon_signature="spark/mutual/defy",
                speech_markers=["invokes communal debts", "frames choices as uprisings"],
                default_agenda="Protect unbonded civilians and redistribute Soulcredit hoards.",
            ),
            "guild_arbiter": VoiceProfile(
                key="guild_arbiter",
                name="Marshal Ves Oru",
                faction_anchor="Guild Accords Tribunal",
                lexicon_signature="ledger/audit/sanction",
                speech_markers=["demands itemised restitution", "issues binding contracts mid-scene"],
                default_agenda="Balance Soulcredit ledgers while preventing uncontrolled Void liability.",
            ),
        }

    def all_profiles(self) -> List[VoiceProfile]:
        """Return all voice profiles in deterministic order."""
        return list(self._profiles.values())

    def get_profile(self, key: str) -> VoiceProfile:
        """Retrieve a specific profile by key."""
        if key not in self._profiles:
            raise KeyError(f"Unknown voice profile: {key}")
        return self._profiles[key]

    def enrich_prompt(
        self,
        base_prompt: str,
        profile: VoiceProfile,
        *,
        previous_turns: Optional[Iterable[str]] = None,
        shared_state: Optional[Dict[str, int]] = None,
    ) -> str:
        """Annotate a prompt with persona directives and shared-state reminders."""
        previous_text = "\n".join(f"- {turn}" for turn in previous_turns or [])
        shared_state_text = "\n".join(
            f"{key}: {value}" for key, value in (shared_state or {}).items()
        )

        return (
            f"Persona: {profile.key} ({profile.faction_anchor})\n"
            f"Lexicon cues: {profile.lexicon_signature}\n"
            f"Agenda: {profile.default_agenda}\n"
            f"Speech markers: {', '.join(profile.speech_markers)}\n"
            f"Shared state:\n{shared_state_text or 'none recorded'}\n"
            f"Previous turns:\n{previous_text or '- none'}\n"
            f"Prompt: {base_prompt}"
        )

    def assign_to_agents(self, agent_keys: Iterable[str]) -> Dict[str, VoiceProfile]:
        """Assign profiles round-robin to a list of agent identifiers."""
        profiles = self.all_profiles()
        if not profiles:
            raise ValueError("No voice profiles configured")
        assignments: Dict[str, VoiceProfile] = {}
        for index, agent_key in enumerate(agent_keys):
            assignments[agent_key] = profiles[index % len(profiles)]
        return assignments
