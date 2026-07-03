import json
import sys
from pathlib import Path


scripts_dir = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from build_dm_finetune_dataset import (  # noqa: E402
    Rejection,
    TrainingExample,
    build_dataset,
    parse_args,
    split_examples,
)


def write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n")


def base_session_events(session_id: str = "session_a") -> list[dict]:
    prompt = [
        {
            "role": "system",
            "content": "You are the DM. Return an ActionResolution.",
        },
        {
            "role": "user",
            "content": "Resolve this player action with ActionResolution mechanics.",
        },
    ]
    return [
        {
            "event_type": "session_start",
            "ts": "2026-01-01T00:00:00",
            "session": session_id,
            "config": {
                "session_name": "unit_test_session",
                "agents": {
                    "dm": {"llm": {"provider": "openai", "model": "gpt-test"}},
                    "players": [{"llm": {"provider": "openai", "model": "gpt-test"}}],
                },
            },
            "random_seed": 123,
            "git_commit": "abc1234",
            "version": "test",
        },
        {
            "event_type": "scenario",
            "ts": "2026-01-01T00:00:01",
            "session": session_id,
            "scenario": {"theme": "Unit Test", "location": "Lab", "situation": "Test"},
        },
        {"event_type": "round_start", "ts": "2026-01-01T00:00:02", "session": session_id, "round": 1},
        {
            "event_type": "llm_call",
            "ts": "2026-01-01T00:00:03",
            "session": session_id,
            "round": 1,
            "agent_id": "dm_01",
            "agent_type": "dm",
            "call_sequence": 1,
            "prompt": prompt,
            "response": "The test action resolves with clear mechanical consequence and clean narration.",
            "model": "gpt-test",
            "temperature": 0.7,
            "tokens": {"input": 100, "output": 20, "total": 120},
        },
        {
            "event_type": "structured_output_metrics",
            "ts": "2026-01-01T00:00:04",
            "session": session_id,
            "round": 1,
            "agent_type": "dm",
            "agent_id": "dm_01",
            "structured_output_success": True,
            "fallback_triggered": False,
            "validation_warnings": [],
            "validation_issues_count": 0,
            "completeness_score": 1.0,
            "is_complete": True,
        },
        {
            "event_type": "action_resolution",
            "ts": "2026-01-01T00:00:05",
            "session": session_id,
            "round": 1,
            "phase": "adjudicate",
            "agent": "Tester",
            "action": "Test action",
            "context": {
                "action_type": "social",
                "is_ritual": False,
                "prompt_metadata": {
                    "version": "2.0.0",
                    "agent_type": "dm",
                    "provider": "openai",
                    "language": "en",
                    "template": "dm/narration_task",
                },
            },
            "roll": {
                "attr": "Empathy",
                "attr_val": 4,
                "skill": "Charm",
                "skill_val": 5,
                "ability": 20,
                "d20": 10,
                "total": 30,
                "dc": 18,
                "margin": 12,
                "tier": "excellent",
                "success": True,
            },
            "economy": {},
            "clocks": {},
            "effects": [],
            "outcome_tiers_full": {
                "critical_failure": {"narrative": "Bad", "mechanical_effect": "Clock +2"},
                "failure": {"narrative": "Fail", "mechanical_effect": "No progress"},
                "moderate_success": {"narrative": "Some", "mechanical_effect": "Clock +1"},
                "good_success": {"narrative": "Good", "mechanical_effect": "Clock +2"},
                "excellent_success": {"narrative": "Great", "mechanical_effect": "Clock +3"},
                "exceptional_success": {"narrative": "Best", "mechanical_effect": "Clock +4"},
            },
        },
        {"event_type": "session_end", "ts": "2026-01-01T00:00:06", "session": session_id, "final_state": {}},
    ]


def test_build_dataset_writes_strict_chat_jsonl(tmp_path):
    source = tmp_path / "session_a.jsonl"
    output = tmp_path / "out"
    write_jsonl(source, base_session_events())

    args = parse_args([str(source), "--output-dir", str(output), "--validation-ratio", "0"])

    assert build_dataset(args) == 0

    train_rows = [json.loads(line) for line in (output / "train.jsonl").read_text().splitlines()]
    manifest = json.loads((output / "manifest.json").read_text())
    quarantine = (output / "quarantine.jsonl").read_text()

    assert len(train_rows) == 1
    assert train_rows[0]["messages"][-1]["role"] == "assistant"
    assert "clear mechanical consequence" in train_rows[0]["messages"][-1]["content"]
    assert manifest["counts"]["included_sessions"] == 1
    assert manifest["counts"]["examples"] == 1
    assert quarantine == ""


def test_build_dataset_rejects_warning_sessions_in_strict_mode(tmp_path):
    events = base_session_events()
    events[4]["validation_warnings"] = ["Condition has penalty=0"]
    source = tmp_path / "session_warning.jsonl"
    output = tmp_path / "out"
    write_jsonl(source, events)

    args = parse_args([str(source), "--output-dir", str(output)])

    assert build_dataset(args) == 2
    assert not (output / "train.jsonl").exists()


def test_split_examples_is_session_disjoint():
    examples = []
    for session_id in ("a", "b", "c", "d"):
        examples.append(TrainingExample(
            example_id=f"ex_{session_id}",
            source_path=f"{session_id}.jsonl",
            session_id=session_id,
            session_name=None,
            round_num=1,
            llm_line=1,
            resolution_line=2,
            action_type="social",
            success_tier="good",
            margin=5,
            slice_key="slice",
            messages=[{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}],
            mechanics={},
        ))

    train, validation = split_examples(examples, validation_ratio=0.5)
    train_sessions = {example.session_id for example in train}
    validation_sessions = {example.session_id for example in validation}

    assert train_sessions
    assert validation_sessions
    assert train_sessions.isdisjoint(validation_sessions)


def test_rejection_serializable():
    rejection = Rejection("session.jsonl", "s", 10, "missing_roll", {"x": 1})

    assert rejection.reason == "missing_roll"
