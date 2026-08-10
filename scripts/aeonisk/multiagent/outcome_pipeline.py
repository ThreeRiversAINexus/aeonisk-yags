"""Mechanics-first action outcomes and validated round narration."""

from __future__ import annotations

import itertools
import logging
import re
import uuid
from enum import Enum
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence

from pydantic import BaseModel, Field, field_validator, model_validator

from .schemas.action_resolution import MechanicalEffects
from .schemas.shared_types import SuccessTier
from .schemas.story_events import RoundSynthesis


OUTCOME_PIPELINE_CONFIG_KEY = "outcome_first_narration"
SCHEMA_VERSION = "3.0.0"

logger = logging.getLogger(__name__)


class ActionAdjudication(BaseModel):
    """LLM-proposed mechanics. It deliberately has no literary narration."""

    success_tier: SuccessTier
    margin: int
    effects: MechanicalEffects = Field(default_factory=MechanicalEffects)
    reasoning_short: str = Field(
        min_length=5,
        max_length=500,
        description="Concise mechanical rationale; never literary outcome prose.",
    )
    skill_override: Optional[Dict[str, str]] = None
    action_skipped: bool = False
    skip_reason: Optional[str] = Field(default=None, min_length=5, max_length=300)
    # Secrecy exception, not a presence roster: default [] (public). Populate
    # only for deliberately concealed, successful actions. Full-party and
    # physically-observable restrictions are dropped downstream.
    aware_agents: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_skip(self) -> "ActionAdjudication":
        if self.action_skipped and not self.skip_reason:
            raise ValueError("skip_reason is required when action_skipped is true")
        return self


class EntityStateSnapshot(BaseModel):
    entity_id: str
    entity_type: Literal["player", "enemy", "npc", "environment"]
    name: str
    narrative_name: str
    health: Optional[int] = None
    max_health: Optional[int] = None
    wounds: int = 0
    stuns: int = 0
    barrier: Optional[int] = None
    is_active: bool = True
    consciousness: Literal["conscious", "unconscious"] = "conscious"
    life_state: Literal["alive", "dead"] = "alive"
    combat_state: Literal["active", "defeated", "departed", "destroyed"] = "active"
    position: Optional[str] = None
    conditions: List[str] = Field(default_factory=list)


class ObservableFact(BaseModel):
    fact_kind: Literal[
        "attempt", "success", "failure", "damage", "healing", "condition",
        "movement", "defeat", "unconscious", "death", "dialogue", "other"
    ]
    subject_id: str
    causing_actor_id: str
    symbolic_value: Optional[str] = None
    severity: Optional[Literal["minor", "moderate", "severe", "critical"]] = None
    prose_safe_summary: str = Field(min_length=3, max_length=300)

    @field_validator("prose_safe_summary", mode="before")
    @classmethod
    def _clamp_prose_safe_summary(cls, value: Any) -> Any:
        # Built engine-side from unbounded input (e.g. a long dialogue line);
        # a verbose summary must not crash outcome construction mid-session.
        if isinstance(value, str) and len(value) > 300:
            return value[:297] + "..."
        return value


_outcome_counter = itertools.count(1)
_adjudication_counter = itertools.count(1)


def reset_outcome_ids() -> None:
    """Restart outcome/adjudication numbering. Called once per session.

    These were `uuid.uuid4().hex[:12]`, so a replayed session minted different
    ids than the recording. The DM's recorded synthesis references outcomes by
    id (`coverage references unknown outcome out_1119991e3ee8`), so every
    reference dangled, validation rejected the synthesis, and the retry pushed
    the whole call stream out of alignment.

    A counter rather than a seeded RNG on purpose: dice already draw from the
    session's `random` stream, and minting ids from the same stream would make
    every id depend on how many rolls happened first.
    """
    global _outcome_counter, _adjudication_counter
    _outcome_counter = itertools.count(1)
    _adjudication_counter = itertools.count(1)


class AppliedOutcome(BaseModel):
    schema_version: str = SCHEMA_VERSION
    outcome_id: str = Field(
        default_factory=lambda: f"out_{next(_outcome_counter):06d}")
    adjudication_id: str = Field(
        default_factory=lambda: f"adj_{next(_adjudication_counter):06d}")
    declaration_event_id: Optional[str] = None
    round: int
    sequence: int
    actor_id: str
    actor_name: str
    actor_narrative_name: str
    intent: str
    method: Optional[str] = None
    target_ids: List[str] = Field(default_factory=list)
    target_names: List[str] = Field(default_factory=list)
    declared_dialogue: Optional[str] = None
    roll_result: Dict[str, Any] = Field(default_factory=dict)
    applied_effects: Dict[str, Any] = Field(default_factory=dict)
    entity_states_before: Dict[str, EntityStateSnapshot] = Field(default_factory=dict)
    entity_states_after: Dict[str, EntityStateSnapshot] = Field(default_factory=dict)
    lifecycle_changes: List[Dict[str, Any]] = Field(default_factory=list)
    observable_facts: List[ObservableFact] = Field(default_factory=list)
    prohibited_claims: List[str] = Field(default_factory=list)
    visibility: List[str] = Field(default_factory=list)
    consequential: bool = True


class NarrativeSegment(BaseModel):
    segment_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4000)
    source_outcome_ids: List[str] = Field(min_length=1)
    visibility: List[str] = Field(default_factory=list)


class CoverageEntry(BaseModel):
    outcome_id: str
    disposition: Literal["rendered", "merged", "omitted_nonconsequential"]
    segment_id: Optional[str] = None


class StateClaim(BaseModel):
    claim_kind: Literal[
        "life_state", "consciousness", "combat_state", "damage", "healing",
        "condition", "movement", "dialogue", "other"
    ]
    subject_id: str
    causing_actor_id: str
    source_outcome_id: str
    symbolic_value: str = Field(min_length=1, max_length=100)

    @field_validator("symbolic_value", mode="before")
    @classmethod
    def _clamp_symbolic_value(cls, value: Any) -> Any:
        # Structured-output providers don't enforce maxLength, and a verbose
        # tag must not hard-reject the whole synthesis before semantic
        # validation runs. Clamp; hard claim kinds still get value-checked.
        if isinstance(value, str) and len(value) > 100:
            return value[:100]
        return value


class OutcomeRoundSynthesis(RoundSynthesis):
    schema_version: str = SCHEMA_VERSION
    segments: List[NarrativeSegment] = Field(min_length=1)
    coverage: List[CoverageEntry] = Field(min_length=1)
    state_claims: List[StateClaim] = Field(default_factory=list)


class SynthesisValidationError(ValueError):
    def __init__(self, errors: Sequence[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


class RoundSynthesisFailClosed(RuntimeError):
    """Synthesis exhausted its bounded validation retries; the round cannot narrate."""


_MECHANICS_LEAK_PATTERNS = (
    (re.compile(r"\b\d+\s*/\s*\d+\s*(?:hp|health)?\b", re.I), "raw HP fraction"),
    (re.compile(r"\b\d+\s+(?:hp|health points?)\b", re.I), "raw HP value"),
    (re.compile(r"\b\d+\s+(?:wounds?|stuns?|clock ticks?)\b", re.I), "raw counter"),
    (re.compile(r"\b(?:dc|margin|roll total)\s*[:=]?\s*[+-]?\d+\b", re.I), "roll mechanics"),
    (re.compile(r"\btgt_[a-z0-9]+\b", re.I), "target ID"),
    (re.compile(r"\[(?:round|turn)\s+\d+\]", re.I), "round/turn label"),
)
_DEATH_LANGUAGE = re.compile(
    r"\b(?:dead|dies?|died|killed|corpse|lifeless|last breath|goes? slack|body goes slack)\b",
    re.I,
)


def outcome_pipeline_enabled(config: Optional[Dict[str, Any]]) -> bool:
    return bool((config or {}).get(OUTCOME_PIPELINE_CONFIG_KEY, False))


def _position(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _conditions(entity: Any, mechanics: Any = None) -> List[str]:
    values: List[str] = []
    for condition in getattr(entity, "status_effects", []) or []:
        values.append(str(getattr(condition, "name", condition)))
    entity_id = getattr(entity, "agent_id", None)
    if mechanics is not None and entity_id:
        for condition in getattr(mechanics, "conditions", {}).get(entity_id, []) or []:
            values.append(str(getattr(condition, "name", condition)))
    return sorted(set(values))


def _snapshot_entity(entity: Any, entity_type: str, mechanics: Any = None) -> EntityStateSnapshot:
    state = getattr(entity, "character_state", None) or entity
    entity_id = str(
        getattr(entity, "agent_id", None)
        or getattr(entity, "object_id", None)
        or getattr(state, "character_id", None)
        or getattr(state, "name", "unknown")
    )
    name = str(getattr(state, "name", None) or getattr(entity, "name", entity_id))
    health = getattr(state, "health", getattr(entity, "health", None))
    max_health = getattr(state, "max_health", getattr(entity, "max_health", None))
    wounds = int(getattr(state, "wounds", getattr(entity, "wounds", 0)) or 0)
    stuns = int(getattr(state, "stuns", getattr(entity, "stuns", 0)) or 0)
    permanently_dead = bool(
        getattr(entity, "_permanently_dead", False)
        or getattr(state, "_permanently_dead", False)
        or wounds >= 6
        or (
            entity_type == "enemy"
            and health is not None
            and health <= 0
            and stuns < 6
        )
    )
    explicit_conscious = getattr(entity, "is_conscious", None)
    if callable(explicit_conscious):
        explicit_conscious = explicit_conscious()
    unconscious = not permanently_dead and (
        explicit_conscious is False
        or (health is not None and health <= 0)
        or stuns >= 6
        or bool(getattr(entity, "is_stabilized", False))
    )
    is_active = bool(getattr(entity, "is_active", True))
    if entity_type == "player":
        is_active = bool(getattr(entity, "is_in_combat", getattr(entity, "is_alive", True)))
    destroyed = bool(getattr(entity, "is_destroyed", False))
    departed = bool(
        getattr(entity, "despawned_round", None) is not None
        or getattr(entity, "is_extracted", False)
    )
    if destroyed:
        combat_state = "destroyed"
    elif departed:
        combat_state = "departed"
    elif not is_active:
        combat_state = "defeated"
    else:
        combat_state = "active"
    return EntityStateSnapshot(
        entity_id=entity_id,
        entity_type=entity_type,
        name=name,
        narrative_name=str(getattr(entity, "narrative_name", None) or name),
        health=health,
        max_health=max_health,
        wounds=wounds,
        stuns=stuns,
        barrier=getattr(state, "barrier", getattr(entity, "barrier", None)),
        is_active=is_active,
        consciousness="unconscious" if unconscious else "conscious",
        life_state="dead" if permanently_dead else "alive",
        combat_state=combat_state,
        position=_position(getattr(entity, "position", getattr(state, "position", None))),
        conditions=_conditions(entity, mechanics),
    )


def snapshot_shared_state(shared_state: Any) -> Dict[str, EntityStateSnapshot]:
    """Capture the state used to derive an outcome; character_state remains oracle."""
    if shared_state is None:
        return {}
    mechanics = getattr(shared_state, "mechanics_engine", None)
    result: Dict[str, EntityStateSnapshot] = {}
    groups: List[tuple[str, Iterable[Any]]] = [
        ("player", getattr(shared_state, "player_agents", []) or []),
        ("npc", getattr(shared_state, "npc_agents", []) or []),
    ]
    enemy_combat = getattr(shared_state, "enemy_combat", None)
    groups.append(("enemy", getattr(enemy_combat, "enemy_agents", []) or []))
    groups.append(("environment", getattr(shared_state, "current_env_objects", []) or []))
    for entity_type, entities in groups:
        for entity in entities:
            snap = _snapshot_entity(entity, entity_type, mechanics)
            result[snap.entity_id] = snap
    return result


def _severity(after: EntityStateSnapshot) -> str:
    if after.life_state == "dead" or after.consciousness == "unconscious":
        return "critical"
    if after.health is None or not after.max_health:
        return "moderate"
    ratio = after.health / after.max_health
    if ratio <= 0.25:
        return "critical"
    if ratio <= 0.5:
        return "severe"
    if ratio <= 0.75:
        return "moderate"
    return "minor"


def _changed_states(
    before: Dict[str, EntityStateSnapshot],
    after: Dict[str, EntityStateSnapshot],
) -> tuple[Dict[str, EntityStateSnapshot], Dict[str, EntityStateSnapshot]]:
    changed_before: Dict[str, EntityStateSnapshot] = {}
    changed_after: Dict[str, EntityStateSnapshot] = {}
    for entity_id in sorted(set(before) | set(after)):
        old = before.get(entity_id)
        new = after.get(entity_id)
        if old != new:
            if old:
                changed_before[entity_id] = old
            if new:
                changed_after[entity_id] = new
    return changed_before, changed_after


def _observable_facts(
    actor_id: str,
    intent: str,
    success: bool,
    before: Dict[str, EntityStateSnapshot],
    after: Dict[str, EntityStateSnapshot],
) -> List[ObservableFact]:
    facts = [ObservableFact(
        fact_kind="success" if success else "failure",
        subject_id=actor_id,
        causing_actor_id=actor_id,
        symbolic_value="succeeded" if success else "failed",
        prose_safe_summary=f"The attempt {'succeeds' if success else 'fails'}.",
    )]
    for entity_id, new in after.items():
        old = before.get(entity_id)
        if old is None:
            continue
        recorded_incapacitation = False
        if old.health is not None and new.health is not None and new.health < old.health:
            severity = _severity(new)
            summary = {
                "minor": "is hurt but remains capable",
                "moderate": "is wounded but remains conscious",
                "severe": "is badly wounded but remains conscious",
                "critical": "is critically wounded",
            }[severity]
            if new.life_state == "dead":
                summary = "is killed"
            elif new.consciousness == "unconscious":
                summary = "is rendered unconscious"
            facts.append(ObservableFact(
                fact_kind="death" if new.life_state == "dead" else (
                    "unconscious" if new.consciousness == "unconscious" else "damage"
                ),
                subject_id=entity_id,
                causing_actor_id=actor_id,
                symbolic_value=new.life_state if new.life_state == "dead" else new.consciousness,
                severity=severity,
                prose_safe_summary=f"{new.narrative_name} {summary}.",
            ))
            recorded_incapacitation = new.life_state == "dead" or new.consciousness == "unconscious"
        if old.life_state != "dead" and new.life_state == "dead" and not recorded_incapacitation:
            facts.append(ObservableFact(
                fact_kind="death",
                subject_id=entity_id,
                causing_actor_id=actor_id,
                symbolic_value="dead",
                severity="critical",
                prose_safe_summary=f"{new.narrative_name} is killed.",
            ))
            recorded_incapacitation = True
        if (
            old.consciousness == "conscious"
            and new.consciousness == "unconscious"
            and not recorded_incapacitation
        ):
            facts.append(ObservableFact(
                fact_kind="unconscious",
                subject_id=entity_id,
                causing_actor_id=actor_id,
                symbolic_value="unconscious",
                severity="critical",
                prose_safe_summary=f"{new.narrative_name} is rendered unconscious but remains alive.",
            ))
        if old.health is not None and new.health is not None and new.health > old.health:
            facts.append(ObservableFact(
                fact_kind="healing",
                subject_id=entity_id,
                causing_actor_id=actor_id,
                symbolic_value="improved",
                prose_safe_summary=f"{new.narrative_name}'s condition improves.",
            ))
        if old.position != new.position:
            facts.append(ObservableFact(
                fact_kind="movement",
                subject_id=entity_id,
                causing_actor_id=actor_id,
                symbolic_value="moved",
                prose_safe_summary=f"{new.narrative_name} changes position.",
            ))
        for condition in sorted(set(new.conditions) - set(old.conditions)):
            facts.append(ObservableFact(
                fact_kind="condition",
                subject_id=entity_id,
                causing_actor_id=actor_id,
                symbolic_value=condition,
                prose_safe_summary=f"{new.narrative_name} is affected by {condition}.",
            ))
    return facts


def build_applied_outcome(
    *,
    round_num: int,
    sequence: int,
    actor_id: str,
    actor_name: str,
    action: Dict[str, Any],
    resolution_data: Dict[str, Any],
    before: Dict[str, EntityStateSnapshot],
    after: Dict[str, EntityStateSnapshot],
) -> AppliedOutcome:
    changed_before, changed_after = _changed_states(before, after)
    outcome_data = resolution_data.get("resolution", {}) or {}
    if isinstance(outcome_data, dict) and isinstance(outcome_data.get("resolution"), dict):
        roll_result = dict(outcome_data["resolution"])
    else:
        roll_result = dict(outcome_data) if isinstance(outcome_data, dict) else {}
    success = bool(roll_result.get("success", resolution_data.get("success", True)))
    target = action.get("target_entity_id") or action.get("target")
    target_ids: List[str] = []
    target_names: List[str] = []
    if target:
        snap = after.get(target) or before.get(target)
        if snap is None:
            snap = next(
                (
                    candidate
                    for candidate in list(after.values()) + list(before.values())
                    if target in {candidate.name, candidate.narrative_name}
                ),
                None,
            )
        if snap:
            target_ids.append(snap.entity_id)
            target_names.append(snap.narrative_name)
        else:
            target_ids.append(str(target))
    facts = _observable_facts(actor_id, action.get("intent", "acts"), success,
                              changed_before, changed_after)
    dialogue = action.get("dialogue_content")
    ambient = action.get("ambient_speech")
    if not dialogue and isinstance(ambient, dict):
        dialogue = ambient.get("line")
    if dialogue:
        facts.append(ObservableFact(
            fact_kind="dialogue",
            subject_id=actor_id,
            causing_actor_id=actor_id,
            symbolic_value="spoken",
            prose_safe_summary=f'{actor_name} says: "{dialogue}"',
        ))
    prohibited: List[str] = []
    for snap in changed_after.values():
        if snap.life_state == "alive":
            prohibited.append(f"Do not describe {snap.narrative_name} as dead or a corpse.")
        if snap.consciousness == "conscious":
            prohibited.append(f"Do not describe {snap.narrative_name} as unconscious.")
    effects = resolution_data.get("effects") or {}
    action_type = str(action.get("action_type", "")).lower()
    consequential = (
        not resolution_data.get("action_skipped", False)
        and action_type not in {"pass", "wait"}
    )
    return AppliedOutcome(
        round=round_num,
        sequence=sequence,
        actor_id=actor_id,
        actor_name=actor_name,
        actor_narrative_name=actor_name,
        intent=action.get("intent") or action.get("description") or "acts",
        method=action.get("description"),
        target_ids=target_ids,
        target_names=target_names,
        declared_dialogue=dialogue,
        roll_result=roll_result,
        applied_effects=effects if isinstance(effects, dict) else {},
        entity_states_before=changed_before,
        entity_states_after=changed_after,
        observable_facts=facts,
        prohibited_claims=prohibited,
        visibility=_effective_visibility(
            resolution_data.get("aware_agents", []) or [],
            before,
            facts,
        ),
        consequential=consequential,
    )


def prose_safe_outcome_payload(outcomes: Sequence[AppliedOutcome]) -> List[Dict[str, Any]]:
    """Return prompt data without numeric mechanics or registry-only names."""
    return [
        {
            "outcome_id": outcome.outcome_id,
            "sequence": outcome.sequence,
            "actor_id": outcome.actor_id,
            "actor_name": outcome.actor_narrative_name,
            "intent": outcome.intent,
            "method": outcome.method,
            "target_names": outcome.target_names,
            "declared_dialogue": outcome.declared_dialogue,
            "facts": [fact.model_dump() for fact in outcome.observable_facts],
            "prohibited_claims": outcome.prohibited_claims,
            "visibility": outcome.visibility,
            "consequential": outcome.consequential,
        }
        for outcome in sorted(outcomes, key=lambda item: item.sequence)
    ]


_VIEWER_ID_PREFIXES = ("player_", "npc_", "enemy_", "env_")


def _normalize_viewer_token(token: str) -> str:
    token = token.strip().lower()
    for prefix in _VIEWER_ID_PREFIXES:
        if token.startswith(prefix):
            token = token[len(prefix):]
            break
    return token.replace("_", " ").strip()


def canonicalize_viewer_ids(
    raw_ids: Sequence[str],
    roster: Dict[str, str],
) -> List[str]:
    """Map proposed viewer ids onto real entity ids; drop what cannot be matched.

    Viewer lists are proposed by the LLM and routinely carry invented agent ids
    (e.g. `player_oathkeeper_sela` for the real `player_01`). Visibility set
    logic is only meaningful over canonical ids, so unmatched or ambiguous
    entries are dropped rather than trusted.
    """
    names = {
        entity_id: (name or "").strip().lower()
        for entity_id, name in roster.items()
    }
    result: List[str] = []
    for raw in raw_ids or []:
        token = (raw or "").strip()
        low = token.lower()
        canonical: Optional[str] = None
        if low in ("dm", "gm") or low.startswith("dm_"):
            canonical = "dm"
        elif token in roster:
            canonical = token
        else:
            wanted = _normalize_viewer_token(token)
            if wanted:
                matches = [
                    entity_id
                    for entity_id, name in names.items()
                    if name and (name == wanted or name.endswith(" " + wanted))
                ]
                if len(matches) == 1:
                    canonical = matches[0]
        if canonical is None:
            logger.warning("Dropping unmappable viewer id %r", raw)
        elif canonical not in result:
            result.append(canonical)
    return result


# Consequences that co-present agents physically witness — a restriction on an
# outcome carrying any of these is adjudicator noise, not real concealment. A
# body dropping, a wound, a kill cannot be hidden from people in the room.
_UNHIDEABLE_FACT_KINDS = frozenset({"damage", "defeat", "unconscious", "death"})


def _effective_visibility(
    raw_ids: Sequence[str],
    before: Dict[str, EntityStateSnapshot],
    facts: Sequence["ObservableFact"] = (),
) -> List[str]:
    """Canonicalize proposed viewers; drop restrictions that cannot be real.

    Two deterministic corrections to noisy adjudicator `aware_agents`:
    - A set covering every player collapses to [] (public); visibility only
      carries meaning when someone is excluded, and copying the full roster
      forces synthesis segments to echo it verbatim.
    - A restriction on an outcome with a physically-observable consequence
      (damage, defeat, KO, death) collapses to []: you cannot conceal a loud
      physical event from co-present agents. Soft/stealthy actions with no
      such fact keep their restriction.
    """
    if any(fact.fact_kind in _UNHIDEABLE_FACT_KINDS for fact in facts):
        return []
    viewers = canonicalize_viewer_ids(
        raw_ids,
        {entity_id: snap.name for entity_id, snap in before.items()},
    )
    player_ids = {
        entity_id for entity_id, snap in before.items()
        if snap.entity_type == "player"
    }
    if player_ids and player_ids.issubset(set(viewers)):
        return []
    return viewers


def finalize_synthesis_narration(synthesis: OutcomeRoundSynthesis) -> None:
    """Derive narration from segments; presentation is code's job, not the LLM's."""
    synthesis.narration = "\n\n".join(
        segment.text.strip() for segment in synthesis.segments
    ).strip()


def canonicalize_synthesis_visibility(
    synthesis: OutcomeRoundSynthesis,
    roster: Dict[str, str],
) -> None:
    """Rewrite each segment's proposed viewer list onto canonical entity ids."""
    for segment in synthesis.segments:
        if segment.visibility:
            segment.visibility = canonicalize_viewer_ids(segment.visibility, roster)


def validate_outcome_synthesis(
    synthesis: OutcomeRoundSynthesis,
    outcomes: Sequence[AppliedOutcome],
) -> List[str]:
    """Raise SynthesisValidationError on falsifying defects; return style warnings.

    Errors block: anything that would let prose assert false authoritative
    state (false deaths, contradicted claims, leaks, broadened visibility,
    broken coverage/provenance). Warnings log: presentation-order deviations,
    which a DM legitimately reorders for drama and which cannot falsify state.
    """
    errors: List[str] = []
    warnings: List[str] = []
    by_id = {outcome.outcome_id: outcome for outcome in outcomes}
    sequence = {outcome.outcome_id: outcome.sequence for outcome in outcomes}
    # Listing order inside a segment is formatting, not semantics — sort it.
    for segment in synthesis.segments:
        segment.source_outcome_ids = sorted(
            segment.source_outcome_ids,
            key=lambda outcome_id: sequence.get(outcome_id, float("inf")),
        )
    # Coverage is bookkeeping over segments, and segments are ground truth for
    # what was rendered. Reconcile deterministic mismatches instead of burning
    # model retries on them (observed live: bulk runs 0001/0009).
    rendering_segments: Dict[str, List[str]] = {}
    for segment in synthesis.segments:
        for outcome_id in segment.source_outcome_ids:
            rendering_segments.setdefault(outcome_id, []).append(segment.segment_id)
    for entry in synthesis.coverage:
        sources = rendering_segments.get(entry.outcome_id, [])
        if entry.disposition == "omitted_nonconsequential" and sources:
            entry.disposition = "merged"
            entry.segment_id = sources[0]
            warnings.append(
                f"auto-repair: outcome {entry.outcome_id} was marked omitted but "
                f"is rendered by {sources[0]}; coverage set to merged"
            )
        elif (entry.disposition != "omitted_nonconsequential"
                and entry.segment_id not in sources and len(sources) == 1):
            warnings.append(
                f"auto-repair: coverage for {entry.outcome_id} pointed at "
                f"{entry.segment_id}; corrected to {sources[0]}"
            )
            entry.segment_id = sources[0]
    coverage_by_id: Dict[str, List[CoverageEntry]] = {}
    segments = {segment.segment_id: segment for segment in synthesis.segments}
    source_segments: Dict[str, List[str]] = {}
    # narration is derived from segments by finalize_synthesis_narration, not validated.
    for entry in synthesis.coverage:
        coverage_by_id.setdefault(entry.outcome_id, []).append(entry)
        if entry.outcome_id not in by_id:
            errors.append(f"coverage references unknown outcome {entry.outcome_id}")
        if entry.disposition != "omitted_nonconsequential" and entry.segment_id not in segments:
            errors.append(f"coverage for {entry.outcome_id} references missing segment {entry.segment_id}")
    for outcome in outcomes:
        entries = coverage_by_id.get(outcome.outcome_id, [])
        if len(entries) != 1:
            errors.append(f"outcome {outcome.outcome_id} must have exactly one coverage entry")
        if outcome.consequential and entries and entries[0].disposition == "omitted_nonconsequential":
            errors.append(f"consequential outcome {outcome.outcome_id} cannot be omitted")
    last_sequence = -1
    for segment in synthesis.segments:
        for outcome_id in segment.source_outcome_ids:
            source_segments.setdefault(outcome_id, []).append(segment.segment_id)
        unknown = [item for item in segment.source_outcome_ids if item not in by_id]
        if unknown:
            errors.append(f"segment {segment.segment_id} references unknown outcomes {unknown}")
            continue
        segment_sequences = [sequence[item] for item in segment.source_outcome_ids]
        # Segments ordered by earliest outcome is a style preference: the model
        # narrates the dramatic anchor first for independent outcomes, and a
        # reordering cannot falsify state. Warn, don't fail the round.
        if segment_sequences and min(segment_sequences) < last_sequence:
            warnings.append(
                f"segment {segment.segment_id} appears out of chronological order"
            )
        if segment_sequences:
            last_sequence = min(segment_sequences)
        for pattern, label in _MECHANICS_LEAK_PATTERNS:
            if pattern.search(segment.text):
                errors.append(f"segment {segment.segment_id} leaks {label}")
        source_outcomes = [by_id[item] for item in segment.source_outcome_ids]
        restricted_sets = [set(outcome.visibility) for outcome in source_outcomes if outcome.visibility]
        if restricted_sets:
            allowed_visibility = set.intersection(*restricted_sets)
            if not segment.visibility:
                errors.append(
                    f"segment {segment.segment_id} broadens restricted outcomes to "
                    f"public visibility; set its visibility to {sorted(allowed_visibility)}"
                )
            elif not set(segment.visibility).issubset(allowed_visibility):
                errors.append(
                    f"segment {segment.segment_id} includes unauthorized viewers; "
                    f"allowed viewers are {sorted(allowed_visibility)}"
                )
        living_changed = any(
            snap.life_state == "alive"
            for outcome in source_outcomes
            for snap in outcome.entity_states_after.values()
        )
        actual_death = any(
            snap.life_state == "dead"
            for outcome in source_outcomes
            for snap in outcome.entity_states_after.values()
        )
        if living_changed and not actual_death and _DEATH_LANGUAGE.search(segment.text):
            errors.append(f"segment {segment.segment_id} uses death language for living outcomes")
        allowed_names = {
            snap.narrative_name
            for outcome in source_outcomes
            for snap in list(outcome.entity_states_before.values()) + list(outcome.entity_states_after.values())
        }
        raw_names = {
            snap.name
            for outcome in source_outcomes
            for snap in list(outcome.entity_states_before.values()) + list(outcome.entity_states_after.values())
            if snap.name != snap.narrative_name
        }
        for raw_name in raw_names - allowed_names:
            if raw_name and raw_name in segment.text:
                errors.append(f"segment {segment.segment_id} leaks raw entity name {raw_name!r}")
    for outcome in outcomes:
        entries = coverage_by_id.get(outcome.outcome_id, [])
        sources = source_segments.get(outcome.outcome_id, [])
        if len(sources) > 1:
            # Re-describing an already-rendered outcome (e.g. a closing summary
            # beat) is repetition, not falsity; coverage still names one
            # primary segment. Warn, don't fail the round.
            warnings.append(
                f"outcome {outcome.outcome_id} is rendered by multiple segments"
            )
        if not entries:
            continue
        entry = entries[0]
        if entry.disposition == "omitted_nonconsequential":
            if entry.segment_id is not None or sources:
                errors.append(f"omitted outcome {outcome.outcome_id} cannot have a narrative segment")
        elif entry.segment_id not in sources:
            errors.append(
                f"coverage for {outcome.outcome_id} does not match segment provenance"
            )
    for claim in synthesis.state_claims:
        outcome = by_id.get(claim.source_outcome_id)
        if outcome is None:
            errors.append(f"state claim references unknown outcome {claim.source_outcome_id}")
            continue
        if claim.causing_actor_id != outcome.actor_id:
            errors.append(f"state claim misattributes {claim.source_outcome_id} to {claim.causing_actor_id}")
        state = outcome.entity_states_after.get(claim.subject_id)
        if claim.claim_kind in {"life_state", "consciousness", "combat_state"}:
            if state is None:
                errors.append(
                    f"state claim subject {claim.subject_id} is not changed by "
                    f"{claim.source_outcome_id}; for attitude or social observations "
                    "use claim_kind 'other' or omit the claim"
                )
            else:
                expected = getattr(state, claim.claim_kind)
                if claim.symbolic_value != expected:
                    errors.append(
                        f"state claim {claim.claim_kind}={claim.symbolic_value} contradicts "
                        f"{expected}; for attitude or social observations use "
                        "claim_kind 'other' or omit the claim"
                    )
        elif claim.claim_kind != "other":
            matching_fact = any(
                fact.subject_id == claim.subject_id
                and fact.causing_actor_id == claim.causing_actor_id
                and (
                    fact.fact_kind == claim.claim_kind
                    or (fact.fact_kind == "unconscious" and claim.claim_kind == "damage")
                )
                for fact in outcome.observable_facts
            )
            if not matching_fact:
                available = [
                    f"{fact.fact_kind}/{fact.subject_id}/{fact.causing_actor_id}"
                    for fact in outcome.observable_facts
                ]
                errors.append(
                    f"state claim {claim.claim_kind} lacks an applied fact in "
                    f"{claim.source_outcome_id}; available facts "
                    f"(kind/subject/actor) are {available or 'none'} — match one, "
                    "use claim_kind 'other', or drop the claim"
                )
    claimed_facts = {
        (claim.source_outcome_id, claim.claim_kind, claim.subject_id, claim.causing_actor_id)
        for claim in synthesis.state_claims
    }
    for outcome in outcomes:
        for fact in outcome.observable_facts:
            claim_kind = "damage" if fact.fact_kind == "unconscious" else fact.fact_kind
            if claim_kind not in {"damage", "healing", "condition", "movement", "dialogue", "death"}:
                continue
            candidate_kinds = {claim_kind}
            if fact.fact_kind == "death":
                candidate_kinds.add("life_state")
            if not any(
                (outcome.outcome_id, kind, fact.subject_id, fact.causing_actor_id) in claimed_facts
                for kind in candidate_kinds
            ):
                errors.append(
                    f"applied fact {fact.fact_kind} for {fact.subject_id} lacks a state claim; "
                    f"add one with claim_kind '{sorted(candidate_kinds)[0]}', subject_id "
                    f"'{fact.subject_id}', causing_actor_id '{fact.causing_actor_id}', "
                    f"source_outcome_id '{outcome.outcome_id}'"
                )
    if errors:
        raise SynthesisValidationError(errors)
    return warnings
