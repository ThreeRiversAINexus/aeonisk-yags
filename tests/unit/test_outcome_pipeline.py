"""Contracts for mechanics-first adjudication and outcome-grounded narration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aeonisk.multiagent.outcome_pipeline import (
    ActionAdjudication,
    AppliedOutcome,
    CoverageEntry,
    EntityStateSnapshot,
    NarrativeSegment,
    ObservableFact,
    OutcomeRoundSynthesis,
    StateClaim,
    SynthesisValidationError,
    prose_safe_outcome_payload,
    build_applied_outcome,
    snapshot_shared_state,
    validate_outcome_synthesis,
)
from aeonisk.multiagent.dm import AIDMAgent
from aeonisk.multiagent.schemas.action_resolution import MechanicalEffects
from aeonisk.multiagent.schemas.shared_types import SuccessTier


def _state(
    *,
    health: int,
    life_state: str = "alive",
    consciousness: str = "conscious",
    combat_state: str = "active",
) -> EntityStateSnapshot:
    return EntityStateSnapshot(
        entity_id="enemy_vane",
        entity_type="enemy",
        name="Vane",
        narrative_name="Vane",
        health=health,
        max_health=30,
        life_state=life_state,
        consciousness=consciousness,
        combat_state=combat_state,
    )


def _outcome(*, sequence: int = 1, after: EntityStateSnapshot | None = None) -> AppliedOutcome:
    return AppliedOutcome(
        outcome_id=f"out_{sequence}",
        adjudication_id=f"adj_{sequence}",
        round=10,
        sequence=sequence,
        actor_id="player_kael",
        actor_name="Kael",
        actor_narrative_name="Kael",
        intent="Force Vane to surrender",
        target_ids=["enemy_vane"],
        target_names=["Vane"],
        entity_states_before={"enemy_vane": _state(health=30)},
        entity_states_after={"enemy_vane": after or _state(health=18)},
        consequential=True,
    )


def _synthesis(text: str, outcome: AppliedOutcome) -> OutcomeRoundSynthesis:
    return OutcomeRoundSynthesis(
        narration=text,
        segments=[NarrativeSegment(
            segment_id="beat_1",
            text=text,
            source_outcome_ids=[outcome.outcome_id],
        )],
        coverage=[CoverageEntry(
            outcome_id=outcome.outcome_id,
            disposition="rendered",
            segment_id="beat_1",
        )],
    )


def test_action_adjudication_schema_cannot_carry_narration():
    schema = ActionAdjudication.model_json_schema()
    assert "narration" not in schema["properties"]
    adjudication = ActionAdjudication(
        success_tier=SuccessTier.MODERATE,
        margin=3,
        effects=MechanicalEffects(),
        reasoning_short="The check succeeds against the selected difficulty.",
    )
    assert "narration" not in adjudication.model_dump()


def test_zero_health_is_unconscious_not_dead_without_lethal_wounds():
    state = SimpleNamespace(
        name="Vane",
        health=0,
        max_health=30,
        wounds=2,
        stuns=0,
        barrier=0,
    )
    player = SimpleNamespace(
        agent_id="player_vane",
        name="Vane",
        character_state=state,
        is_in_combat=False,
        is_alive=False,
        is_conscious=False,
        _permanently_dead=False,
    )
    shared_state = SimpleNamespace(
        mechanics_engine=None,
        player_agents=[player],
        npc_agents=[],
        enemy_combat=SimpleNamespace(enemy_agents=[]),
        current_env_objects=[],
    )

    snapshot = snapshot_shared_state(shared_state)["player_vane"]

    assert snapshot.life_state == "alive"
    assert snapshot.consciousness == "unconscious"
    assert snapshot.combat_state == "defeated"


def test_enemy_zero_health_is_dead_but_stun_ko_is_not():
    killed = SimpleNamespace(
        agent_id="enemy_killed",
        name="Killed Enemy",
        health=0,
        max_health=20,
        wounds=3,
        stuns=0,
        is_active=False,
        despawned_round=None,
    )
    stunned = SimpleNamespace(
        agent_id="enemy_stunned",
        name="Stunned Enemy",
        health=20,
        max_health=20,
        wounds=0,
        stuns=6,
        is_active=False,
        despawned_round=None,
    )
    env_object = SimpleNamespace(
        object_id="env_door",
        name="Blast Door",
        health=12,
        max_health=20,
        wounds=0,
        stuns=0,
        is_active=True,
        is_destroyed=False,
    )
    shared_state = SimpleNamespace(
        mechanics_engine=None,
        player_agents=[],
        npc_agents=[],
        enemy_combat=SimpleNamespace(enemy_agents=[killed, stunned]),
        current_env_objects=[env_object],
    )

    snapshot = snapshot_shared_state(shared_state)

    assert snapshot["enemy_killed"].life_state == "dead"
    assert snapshot["enemy_stunned"].life_state == "alive"
    assert snapshot["enemy_stunned"].consciousness == "unconscious"
    assert snapshot["env_door"].entity_type == "environment"


def test_stun_ko_becomes_observable_without_hp_change():
    before = {"enemy_vane": _state(health=30)}
    after_state = _state(health=30, consciousness="unconscious", combat_state="defeated")
    after_state.stuns = 6
    outcome = build_applied_outcome(
        round_num=10,
        sequence=1,
        actor_id="player_kael",
        actor_name="Kael",
        action={"intent": "Subdue Vane", "target_entity_id": "enemy_vane"},
        resolution_data={"success": True, "effects": {}},
        before=before,
        after={"enemy_vane": after_state},
    )

    fact = next(fact for fact in outcome.observable_facts if fact.fact_kind == "unconscious")
    assert fact.subject_id == "enemy_vane"
    assert "remains alive" in fact.prose_safe_summary


def test_display_name_target_normalizes_to_canonical_entity_id():
    outcome = build_applied_outcome(
        round_num=10,
        sequence=1,
        actor_id="enemy_broker",
        actor_name="Broker",
        action={"intent": "attack", "target": "Vane"},
        resolution_data={"success": False, "effects": {}},
        before={"enemy_vane": _state(health=30)},
        after={"enemy_vane": _state(health=30)},
    )

    assert outcome.target_ids == ["enemy_vane"]
    assert outcome.target_names == ["Vane"]


def test_literary_synthesis_rejects_false_death_for_living_target():
    outcome = _outcome()
    text = (
        "Kael closes the distance while Vane reels beneath the pressure, and the contest "
        "ends with Vane's lifeless body going slack on the rain-dark stones. The alley "
        "falls quiet around them as the remaining witnesses retreat behind their shutters."
    )

    with pytest.raises(SynthesisValidationError, match="death language"):
        validate_outcome_synthesis(_synthesis(text, outcome), [outcome])


@pytest.mark.parametrize("leak", ["18 HP", "DC 15", "margin +4", "tgt_deadbeef"])
def test_literary_synthesis_rejects_raw_mechanics(leak: str):
    outcome = _outcome()
    text = (
        f"Kael presses the advantage while Vane staggers but remains standing; the record says {leak}. "
        "Rain rattles across the awnings, and the watching crowd draws back from the confrontation."
    )

    with pytest.raises(SynthesisValidationError, match="leaks"):
        validate_outcome_synthesis(_synthesis(text, outcome), [outcome])


def test_state_claim_must_match_applied_state_and_actor():
    outcome = _outcome()
    text = (
        "Kael corners Vane without delivering a killing blow. Vane remains conscious, wounded, "
        "and capable of answering as rain runs from the market awnings and witnesses hold their distance."
    )
    synthesis = _synthesis(text, outcome)
    synthesis.state_claims = [StateClaim(
        claim_kind="life_state",
        subject_id="enemy_vane",
        causing_actor_id="player_sael",
        source_outcome_id=outcome.outcome_id,
        symbolic_value="dead",
    )]

    with pytest.raises(SynthesisValidationError) as exc_info:
        validate_outcome_synthesis(synthesis, [outcome])

    assert "misattributes" in str(exc_info.value)
    assert "contradicts alive" in str(exc_info.value)


def test_valid_synthesis_covers_outcome_once_and_preserves_provenance():
    outcome = _outcome()
    text = (
        "Kael's pressure forces Vane back beneath the dripping awning, wounded but plainly alive. "
        "The broker keeps his feet and his voice, though the witnesses can see that the balance of "
        "the confrontation has shifted and that surrender has become the safer choice."
    )
    synthesis = _synthesis(text, outcome)
    synthesis.state_claims = [StateClaim(
        claim_kind="life_state",
        subject_id="enemy_vane",
        causing_actor_id="player_kael",
        source_outcome_id=outcome.outcome_id,
        symbolic_value="alive",
    )]

    validate_outcome_synthesis(synthesis, [outcome])


def test_prose_payload_excludes_numeric_state_and_effects():
    payload = prose_safe_outcome_payload([_outcome()])[0]

    assert "roll_result" not in payload
    assert "applied_effects" not in payload
    assert "entity_states_before" not in payload
    assert "entity_states_after" not in payload


def test_coverage_must_match_segment_provenance():
    outcome = _outcome()
    text = (
        "Kael forces Vane beneath the awning, where the broker remains alive and alert despite "
        "his injuries. The witnesses edge away while rain drums against the sealed market shutters."
    )
    synthesis = _synthesis(text, outcome)
    synthesis.coverage[0].segment_id = "invented_beat"

    with pytest.raises(SynthesisValidationError, match="missing segment"):
        validate_outcome_synthesis(synthesis, [outcome])


def test_restricted_outcome_cannot_be_rendered_publicly():
    outcome = _outcome()
    outcome.visibility = ["player_kael", "player_sael"]
    text = (
        "Kael exchanges a quiet signal with Vane beneath the rain-battered awning, keeping the "
        "meaning concealed from everyone beyond the two allies permitted to witness the moment."
    )

    with pytest.raises(SynthesisValidationError, match="public visibility"):
        validate_outcome_synthesis(_synthesis(text, outcome), [outcome])


def test_applied_damage_fact_requires_matching_state_claim():
    outcome = _outcome()
    outcome.observable_facts = [ObservableFact(
        fact_kind="damage",
        subject_id="enemy_vane",
        causing_actor_id="player_kael",
        symbolic_value="conscious",
        severity="moderate",
        prose_safe_summary="Vane is wounded but remains conscious.",
    )]
    text = (
        "Kael's strike drives Vane back beneath the awning. The broker remains conscious despite "
        "the wound, one hand pressed to his side while the watching market recoils from the impact."
    )

    with pytest.raises(SynthesisValidationError, match="lacks a state claim"):
        validate_outcome_synthesis(_synthesis(text, outcome), [outcome])


def test_mechanics_only_resolution_contains_no_literary_text():
    dm = object.__new__(AIDMAgent)
    result = dm._build_mechanics_only_resolution(
        executed=True,
        reasoning="The pre-validated transaction completed successfully.",
    )

    assert isinstance(result["resolution"], ActionAdjudication)
    assert result["narration"] == ""
    assert result["outcome"]["narration"] == ""
    assert dm._last_structured_resolution is result["resolution"]


@pytest.mark.asyncio
async def test_synthesis_retries_validation_without_reapplying_outcomes():
    dm = object.__new__(AIDMAgent)
    dm.session_config = {"outcome_synthesis_attempts": 2}
    dm._round_synthesis_history = []
    dm.shared_state = None

    outcome = _outcome()
    invalid_text = (
        "Kael watches Vane's lifeless body settle beneath the awning while the market goes silent. "
        "Rain carries the last traces of the confrontation into the gutters as every witness withdraws."
    )
    valid_text = (
        "Kael forces Vane beneath the awning, wounded but alive and capable of answering. The broker "
        "keeps his feet while the market witnesses retreat, leaving the balance of the confrontation "
        "plainly altered without inventing a death that never occurred."
    )
    dm._generate_round_synthesis_structured = AsyncMock(side_effect=[
        _synthesis(invalid_text, outcome),
        _synthesis(valid_text, outcome),
    ])

    result = await dm._synthesize_applied_outcomes(
        [{"applied_outcome": outcome.model_dump(mode="json")}],
        round_num=10,
        entity_lifecycle_result={
            "morale_events": [{
                "type": "surrender",
                "character_name": "Vane",
                "narration": "CONTAMINATED PRIOR PROSE",
            }],
        },
    )

    assert result.narration == valid_text
    assert dm._generate_round_synthesis_structured.await_count == 2
    first_prompt = dm._generate_round_synthesis_structured.await_args_list[0].args[0]
    second_prompt = dm._generate_round_synthesis_structured.await_args_list[1].args[0]
    assert "CONTAMINATED PRIOR PROSE" not in first_prompt
    assert "uses death language" in second_prompt


# --- Live-experiment regressions (2026-07-16, Kneeling run 9052cb25) ---
# Round-1 synthesis failed closed on all attempts and the session hung:
# (a) aware_agents/visibility carried LLM-invented agent ids (player_sela vs
#     player_oathkeeper_sela vs real id player_01), making the visibility
#     subset check unsatisfiable;
# (b) narration was rejected for joining segments with a space instead of
#     blank lines — presentation the code should derive, not validate;
# (c) the fail-closed RuntimeError was swallowed by the message bus and the
#     session waited on _synthesis_complete forever.

from aeonisk.multiagent.outcome_pipeline import (
    RoundSynthesisFailClosed,
    canonicalize_viewer_ids,
    canonicalize_synthesis_visibility,
    finalize_synthesis_narration,
)


def _roster():
    return {
        "player_01": "Oathkeeper Sela",
        "player_02": "Cold Tarn",
        "enemy_op_1": "Subdued Operative #1",
    }


def test_viewer_ids_canonicalize_to_roster_entity_ids():
    raw = [
        "player_01",              # exact id
        "player_oathkeeper_sela", # invented id, full name
        "player_sela",            # invented id, partial name (duplicate)
        "player_cold_tarn",       # invented id, full name
        "dm", "dm_01",            # dm aliases collapse
        "spectral_witness",       # unmappable — dropped
    ]
    assert canonicalize_viewer_ids(raw, _roster()) == ["player_01", "player_02", "dm"]


def test_viewer_id_ambiguous_partial_is_dropped():
    roster = {"player_01": "Sela Vane", "player_02": "Kara Vane"}
    assert canonicalize_viewer_ids(["player_vane"], roster) == []


def test_build_applied_outcome_canonicalizes_aware_agents():
    snap = _state(health=30)
    before = {
        "enemy_vane": snap,
        "player_01": EntityStateSnapshot(
            entity_id="player_01",
            entity_type="player",
            name="Oathkeeper Sela",
            narrative_name="Sela",
            health=20,
            max_health=20,
            life_state="alive",
            consciousness="conscious",
            combat_state="active",
        ),
    }
    outcome = build_applied_outcome(
        round_num=1,
        sequence=1,
        actor_id="player_01",
        actor_name="Oathkeeper Sela",
        action={"intent": "watch"},
        resolution_data={"aware_agents": ["player_sela", "dm"], "resolution": {}},
        before=before,
        after=before,
    )
    assert outcome.visibility == ["player_01", "dm"]


def test_narration_is_derived_from_segments_not_validated_for_exact_join():
    first = _outcome(sequence=1)
    second = _outcome(sequence=2)
    synthesis = OutcomeRoundSynthesis(
        narration=(
            "The model joined these segment texts with a single space instead of "
            "blank lines and the old validator rejected the entire synthesis for it."
        ),
        segments=[
            NarrativeSegment(
                segment_id="seg_1",
                text="Kael forces the broker back beneath the awning, alive and answering.",
                source_outcome_ids=[first.outcome_id],
            ),
            NarrativeSegment(
                segment_id="seg_2",
                text="The market crowd withdraws, leaving the balance plainly altered.",
                source_outcome_ids=[second.outcome_id],
            ),
        ],
        coverage=[
            CoverageEntry(outcome_id=first.outcome_id, disposition="rendered", segment_id="seg_1"),
            CoverageEntry(outcome_id=second.outcome_id, disposition="rendered", segment_id="seg_2"),
        ],
    )
    finalize_synthesis_narration(synthesis)
    assert synthesis.narration == (
        "Kael forces the broker back beneath the awning, alive and answering."
        "\n\n"
        "The market crowd withdraws, leaving the balance plainly altered."
    )
    validate_outcome_synthesis(synthesis, [first, second])


def test_segment_visibility_canonicalized_before_subset_check():
    outcome = _outcome()
    outcome.visibility = ["player_01", "player_02", "dm"]
    synthesis = _synthesis(
        "Kael forces the broker back beneath the awning, alive and answering for "
        "what he knows, while the market crowd holds its distance and watches.",
        outcome,
    )
    synthesis.segments[0].visibility = ["player_oathkeeper_sela", "player_cold_tarn", "dm"]
    canonicalize_synthesis_visibility(synthesis, _roster())
    assert synthesis.segments[0].visibility == ["player_01", "player_02", "dm"]
    validate_outcome_synthesis(synthesis, [outcome])


@pytest.mark.asyncio
async def test_synthesis_exhaustion_raises_fail_closed():
    dm = object.__new__(AIDMAgent)
    dm.session_config = {"outcome_synthesis_attempts": 2}
    dm._round_synthesis_history = []
    dm.shared_state = None

    outcome = _outcome()
    invalid = _synthesis(
        "Kael watches Vane's lifeless body settle beneath the awning while the "
        "market goes silent and every witness quietly withdraws from the square.",
        outcome,
    )
    dm._generate_round_synthesis_structured = AsyncMock(side_effect=[invalid, invalid])

    with pytest.raises(RoundSynthesisFailClosed):
        await dm._synthesize_applied_outcomes(
            [{"applied_outcome": outcome.model_dump(mode="json")}],
            round_num=10,
        )


@pytest.mark.asyncio
async def test_handle_synthesis_fail_closed_broadcasts_failure():
    dm = object.__new__(AIDMAgent)
    dm.agent_id = "dm_01"
    dm._synthesize_round_outcome = AsyncMock(
        side_effect=RoundSynthesisFailClosed("validation exhausted")
    )
    sent = []
    dm.send_message_sync = lambda mtype, recipient, payload: sent.append(
        (mtype, recipient, payload)
    )

    await dm._handle_synthesis({"resolutions": [{"stub": True}], "round": 3})

    assert len(sent) == 1
    _, recipient, payload = sent[0]
    assert recipient is None  # broadcast
    assert payload["is_round_synthesis"] is True
    assert payload["synthesis_failed"] is True
    assert payload["round"] == 3


@pytest.mark.asyncio
async def test_session_aborts_cleanly_on_failed_synthesis_message():
    import asyncio
    from aeonisk.multiagent.base import Message, MessageType
    from aeonisk.multiagent.session import SelfPlayingSession
    from datetime import datetime

    session = object.__new__(SelfPlayingSession)
    session._synthesis_complete = asyncio.Event()
    session._session_end_status = None
    session._end_reason = None
    session._last_dm_narration = None

    message = Message(
        id="synthesis_fail",
        type=MessageType.DM_NARRATION,
        sender="dm_01",
        recipient=None,
        payload={
            "narration": "Round synthesis failed validation after bounded retries.",
            "is_round_synthesis": True,
            "synthesis_failed": True,
            "round": 1,
        },
        timestamp=datetime.now(),
    )
    await session._handle_dm_narration(message)

    assert session._synthesis_complete.is_set()
    assert session._session_end_status == "aborted"
    assert session._end_reason == "round_synthesis_failed"
