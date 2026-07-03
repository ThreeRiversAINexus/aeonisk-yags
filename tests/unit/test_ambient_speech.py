import json
from pathlib import Path
from types import SimpleNamespace

from scripts.aeonisk.multiagent.action_schema import ActionDeclaration
from scripts.aeonisk.multiagent.dm import AIDMAgent
from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
from scripts.aeonisk.multiagent.reconstruct_narrative import extract_narrative_elements
from scripts.aeonisk.multiagent.schemas.player_action import (
    AmbientSpeech,
    ExploreAction,
    PlayerAction,
)
from scripts.aeonisk.multiagent.schemas.shared_types import ActionType
from scripts.aeonisk.multiagent.session import SelfPlayingSession
from scripts.aeonisk.multiagent.shared_state import SharedState


def _session_with_agents(*agents):
    session = SelfPlayingSession.__new__(SelfPlayingSession)
    session.shared_state = SharedState()
    session.shared_state.player_agents = [a for a in agents if a.agent_id.startswith("player_")]
    session.shared_state.npc_agents = [a for a in agents if a.agent_id.startswith("npc_")]
    return session


def _agent(agent_id, name):
    return SimpleNamespace(
        agent_id=agent_id,
        character_state=SimpleNamespace(name=name),
        recent_narrations=[],
        is_alive=True,
        _permanently_dead=False,
    )


def test_action_specific_schema_accepts_ambient_speech():
    action = ExploreAction(
        intent="Search northwest corridor for exit",
        description="Moving carefully through the darkened hallway, checking the bulkhead seams and floor for void residue.",
        attribute="Perception",
        skill="Awareness",
        difficulty_estimate=15,
        difficulty_justification="Poor lighting, but the corridor is stable enough to inspect.",
        action_type=ActionType.EXPLORE,
        ambient_speech=AmbientSpeech(
            line="Keep your comms open; I am checking the north corridor.",
            target_type="party",
            target="Sanctuary Vael",
            delivery="comms",
        ),
    )

    assert action.ambient_speech.line.startswith("Keep your comms")
    assert not hasattr(action.ambient_speech, "attribute")
    assert not hasattr(action.ambient_speech, "skill")
    assert not hasattr(action.ambient_speech, "coordination_bonus")


def test_ambient_speech_accepts_enemy_and_crowd_targets():
    enemy_line = AmbientSpeech(
        line="Back off and nobody has to make this ugly.",
        target_type="enemy",
        target="tgt_guard",
        delivery="spoken",
    )
    crowd_line = AmbientSpeech(
        line="Anyone who saw that scanner flicker, now is the time to speak up.",
        target_type="crowd",
        target=None,
        delivery="spoken",
    )

    assert enemy_line.target_type == "enemy"
    assert crowd_line.target_type == "crowd"


def test_legacy_player_action_serializes_ambient_speech():
    action = PlayerAction(
        intent="Search northwest corridor for exit",
        description="Moving carefully through the darkened hallway, checking the bulkhead seams and floor for void residue.",
        attribute="Perception",
        skill="Awareness",
        difficulty_estimate=15,
        difficulty_justification="Poor lighting, but the corridor is stable enough to inspect.",
        action_type=ActionType.EXPLORE,
        ambient_speech={
            "line": "Keep your comms open; I am checking the north corridor.",
            "target_type": "party",
            "target": "Sanctuary Vael",
            "delivery": "comms",
        },
    )

    legacy = action.to_legacy_dict()

    assert legacy["ambient_speech"] == {
        "line": "Keep your comms open; I am checking the north corridor.",
        "target_type": "party",
        "target": "Sanctuary Vael",
        "delivery": "comms",
    }


def test_action_declaration_preserves_ambient_speech():
    declaration = ActionDeclaration(
        intent="Search northwest corridor for exit",
        description="Moving carefully through the darkened hallway, checking the bulkhead seams and floor for void residue.",
        attribute="Perception",
        skill="Awareness",
        difficulty_estimate=15,
        difficulty_justification="Poor lighting, but the corridor is stable enough to inspect.",
        character_name="Iris Kain",
        agent_id="player_03",
        action_type="explore",
        ambient_speech={
            "line": "Keep your comms open; I am checking the north corridor.",
            "target_type": "party",
            "target": "Sanctuary Vael",
            "delivery": "comms",
        },
    )

    assert declaration.to_dict()["ambient_speech"]["delivery"] == "comms"


def test_reconstruct_narrative_renders_ambient_speech(tmp_path):
    session = tmp_path / "session_test.jsonl"
    event = {
        "event_type": "action_declaration",
        "ts": "2026-01-01T00:00:00",
        "session": "s",
        "round": 1,
        "player_id": "player_03",
        "character_name": "Iris Kain",
        "initiative": 12,
        "action": {
            "intent": "Search northwest corridor for exit",
            "description": "Iris checks the corridor for signs of void residue.",
            "attribute": "Perception",
            "skill": "Awareness",
            "difficulty_estimate": 15,
            "action_type": "explore",
            "ambient_speech": {
                "line": "Keep your comms open; I am checking the north corridor.",
                "target_type": "party",
                "target": "Sanctuary Vael",
                "delivery": "comms",
            },
        },
    }
    session.write_text(json.dumps(event) + "\n")

    narratives = extract_narrative_elements(session)

    assert "Ambient speech (comms to Sanctuary Vael)" in narratives[0]["content"]
    assert "Keep your comms open" in narratives[0]["content"]


def test_dm_prompt_renders_ambient_speech_without_mechanical_instruction():
    prompt = AIDMAgent._build_dm_narration_prompt(
        SimpleNamespace(shared_state=None),
        is_dialogue=False,
        scenario_context="Checkpoint queue.",
        character_context="Drifter Cas is present.",
        resolution_context="Success: moderate.",
        tactical_combat_context="",
        clock_context="",
        description="Drifter Cas blends into the queue and charms the vendor.",
        action_type="social",
        action={
            "ambient_speech": {
                "line": "Nice stand; seen anything interesting lately?",
                "target_type": "npc",
                "target": "tgt_vendor",
                "delivery": "spoken",
            }
        },
    )

    assert "Ambient Speech (flavor only, do not roll or apply mechanics)" in prompt
    assert "Nice stand; seen anything interesting lately?" in prompt


def test_party_comms_ambient_speech_enters_visible_context_for_players():
    iris = _agent("player_01", "Iris Kain")
    sol = _agent("player_02", "Sol Vance")
    session = _session_with_agents(iris, sol)

    session._publish_ambient_speech_context(
        "player_01",
        {
            "character_name": "Iris Kain",
            "ambient_speech": {
                "line": "Keep comms open; I am checking the north corridor.",
                "target_type": "party",
                "target": None,
                "delivery": "comms",
            },
        },
    )

    visible_to_sol = filter_narrations_for_agent("player_02", sol.recent_narrations)

    assert "Iris Kain, comms to party" in str(visible_to_sol[0])
    assert "checking the north corridor" in str(visible_to_sol[0])


def test_whisper_ambient_speech_is_hidden_from_non_target_players():
    iris = _agent("player_01", "Iris Kain")
    sol = _agent("player_02", "Sol Vance")
    nova = _agent("player_03", "Nova Reed")
    session = _session_with_agents(iris, sol, nova)

    session._publish_ambient_speech_context(
        "player_01",
        {
            "character_name": "Iris Kain",
            "ambient_speech": {
                "line": "The guard is watching the scanner, not us.",
                "target_type": "party",
                "target": "player_02",
                "delivery": "whisper",
            },
        },
    )

    assert filter_narrations_for_agent("player_02", sol.recent_narrations)
    assert not filter_narrations_for_agent("player_03", nova.recent_narrations)


def test_spoken_ambient_speech_defaults_to_public_context():
    iris = _agent("player_01", "Iris Kain")
    sol = _agent("player_02", "Sol Vance")
    session = _session_with_agents(iris, sol)

    session._publish_ambient_speech_context(
        "player_01",
        {
            "character_name": "Iris Kain",
            "ambient_speech": {
                "line": "Nice stand; seen anything interesting lately?",
                "target_type": "npc",
                "target": "npc_vendor",
                "delivery": "spoken",
            },
        },
    )

    entry = sol.recent_narrations[0]

    assert entry.aware_agents == []
    assert filter_narrations_for_agent("player_02", sol.recent_narrations)


def test_player_prompt_no_longer_promises_free_dialogue_bonus():
    prompt = Path("scripts/aeonisk/multiagent/prompts/claude/en/player.yaml").read_text()

    assert "ambient_speech" in prompt
    assert "This will trigger a FREE second action" not in prompt
    assert "COORDINATION BONUS" not in prompt
    assert "Party dialogue is a FREE ACTION" not in prompt


def test_player_runtime_no_longer_auto_grants_dialogue_free_action():
    source = Path("scripts/aeonisk/multiagent/player.py").read_text()

    assert "Inter-party dialogue detected - FREE ACTION" not in source
    assert "Free action used - requesting main action" not in source
    assert "grant_coordination_bonus(" not in source
