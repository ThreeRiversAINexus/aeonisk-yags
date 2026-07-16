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
