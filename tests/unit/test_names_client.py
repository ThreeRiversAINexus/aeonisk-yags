"""Tests for NamesClient — the yags-side wrapper around aeonisk-names-mcp.

Covers the FACTION_MAP / PRONOUN_GENDER_MAP tables, the non-canon faction
skip path, the happy-path generate+reserve, exception fail-open, and the
reservation-conflict retry budget.
"""

from __future__ import annotations

import pytest

from scripts.aeonisk.multiagent.names_client import (
    FACTION_MAP,
    PRONOUN_GENDER_MAP,
    NamesClient,
    pronouns_to_gender,
)


# --- Static mapping tables -------------------------------------------------


def test_faction_map_covers_canonical_yags_factions() -> None:
    # The MCP knows 8 canonical factions; yags accepts 7 of them by display name
    # plus three edge values (Void / Independent / Unknown) that intentionally
    # have NO MCP mapping — the caller treats absence as "skip MCP".
    for display in (
        "Sovereign Nexus",
        "Pantheon Security",
        "ACG",
        "ArcGen",
        "House of Vox",
        "Tempest Industries",
        "Freeborn",
    ):
        assert display in FACTION_MAP, f"{display!r} missing from FACTION_MAP"
        assert FACTION_MAP[display].islower() and "-" in FACTION_MAP[display] or \
            FACTION_MAP[display] == "freeborn"

    for edge in ("Void", "Independent", "Unknown"):
        assert edge not in FACTION_MAP, f"{edge!r} should NOT be mapped"


def test_pronoun_gender_mapping() -> None:
    assert pronouns_to_gender("she/her") == "feminine"
    assert pronouns_to_gender("he/him") == "masculine"
    assert pronouns_to_gender("they/them") == "ambiguous"
    assert pronouns_to_gender("it/its") == "ambiguous"
    assert pronouns_to_gender("xe/xem") == "ambiguous"
    assert pronouns_to_gender("") == "ambiguous"
    assert pronouns_to_gender(None) == "ambiguous"  # type: ignore[arg-type]
    # The lookup table itself only carries the two canonical pronoun strings.
    assert set(PRONOUN_GENDER_MAP.keys()) == {"she/her", "he/him"}


# --- generate_npc_name ------------------------------------------------------


def test_generate_returns_none_for_noncanon_faction(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AEONISK_NAMES_DB", str(tmp_path / "rsrv.db"))

    calls: list[str] = []

    def fake_generate(*args, **kwargs):  # would-be MCP call
        calls.append("generate")
        raise AssertionError("MCP should not be invoked for non-canon faction")

    monkeypatch.setattr(
        "scripts.aeonisk.multiagent.names_client.generate_baseline_names",
        fake_generate,
    )

    client = NamesClient(owner="yags:test")
    assert client.generate_npc_name(faction="Independent", pronouns="they/them") is None
    assert client.generate_npc_name(faction="Void", pronouns="she/her") is None
    assert client.generate_npc_name(faction="Unknown", pronouns="he/him") is None
    assert calls == []


def test_generate_returns_canonical_name_for_canon_faction(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AEONISK_NAMES_DB", str(tmp_path / "rsrv.db"))

    from aeonisk_names_mcp.generator import GenerateResult

    captured: dict = {}

    def fake_generate(*, faction, count, gender, from_pool, exclude=None, **kwargs):
        captured["faction"] = faction
        captured["gender"] = gender
        captured["from_pool"] = from_pool
        captured["exclude"] = list(exclude or [])
        return GenerateResult(
            names=[{"name": "Vehalin Halessan", "full_name": "Vehalin Halessan"}],
            partial=False,
            reason=None,
            pool_used=1,
            live_used=0,
        )

    reserve_calls: list[dict] = []

    def fake_reserve(*, name, owner, context=None, **_):
        reserve_calls.append({"name": name, "owner": owner, "context": context})
        return {"reserved": True, "name": name, "owner": owner, "reserved_at": "now"}

    monkeypatch.setattr(
        "scripts.aeonisk.multiagent.names_client.generate_baseline_names",
        fake_generate,
    )
    monkeypatch.setattr(
        "scripts.aeonisk.multiagent.names_client.tool_reserve",
        fake_reserve,
    )

    client = NamesClient(owner="yags:abc123")
    name = client.generate_npc_name(
        faction="Sovereign Nexus",
        pronouns="she/her",
        context="round_3_npc_spawn",
    )

    assert name == "Vehalin Halessan"
    assert captured == {
        "faction": "sovereign-nexus",
        "gender": "feminine",
        "from_pool": True,
        "exclude": [],
    }
    assert reserve_calls == [
        {
            "name": "Vehalin Halessan",
            "owner": "yags:abc123",
            "context": "round_3_npc_spawn",
        }
    ]


def test_generate_falls_back_on_mcp_exception(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setenv("AEONISK_NAMES_DB", str(tmp_path / "rsrv.db"))

    def fake_generate(**_):
        raise RuntimeError("MCP corpus exploded")

    monkeypatch.setattr(
        "scripts.aeonisk.multiagent.names_client.generate_baseline_names",
        fake_generate,
    )

    client = NamesClient(owner="yags:test")
    with caplog.at_level("WARNING"):
        result = client.generate_npc_name(faction="Freeborn", pronouns="they/them")
    assert result is None
    assert any("MCP" in r.message or "names" in r.message.lower() for r in caplog.records)


def test_generate_excludes_conflicting_name_on_retry(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AEONISK_NAMES_DB", str(tmp_path / "rsrv.db"))

    from aeonisk_names_mcp.generator import GenerateResult

    # First call returns a name that's already reserved by someone else;
    # second call returns a fresh one.
    gen_calls: list[dict] = []

    def fake_generate(*, faction, count, gender, from_pool, exclude=None, **_):
        gen_calls.append({"exclude": list(exclude or [])})
        names = [
            {"name": "Iresa Halessan", "full_name": "Iresa Halessan"},
            {"name": "Maen Halessan", "full_name": "Maen Halessan"},
        ]
        return GenerateResult(
            names=[names[len(gen_calls) - 1]],
            partial=False,
            reason=None,
            pool_used=1,
            live_used=0,
        )

    def fake_reserve(*, name, **_):
        if name == "Iresa Halessan":
            return {"reserved": False, "conflict": "already reserved"}
        return {"reserved": True, "name": name, "owner": "yags:test", "reserved_at": "now"}

    monkeypatch.setattr(
        "scripts.aeonisk.multiagent.names_client.generate_baseline_names",
        fake_generate,
    )
    monkeypatch.setattr(
        "scripts.aeonisk.multiagent.names_client.tool_reserve",
        fake_reserve,
    )

    client = NamesClient(owner="yags:test")
    result = client.generate_npc_name(faction="Sovereign Nexus", pronouns="she/her")
    assert result == "Maen Halessan"
    assert len(gen_calls) == 2
    assert gen_calls[1]["exclude"] == ["Iresa Halessan"]


def test_generate_returns_none_after_two_reservation_conflicts(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("AEONISK_NAMES_DB", str(tmp_path / "rsrv.db"))

    from aeonisk_names_mcp.generator import GenerateResult

    def fake_generate(**_):
        return GenerateResult(
            names=[{"name": "Conflicted Halessan", "full_name": "Conflicted Halessan"}],
            partial=False,
            reason=None,
            pool_used=1,
            live_used=0,
        )

    def always_conflict(**_):
        return {"reserved": False, "conflict": "already reserved"}

    monkeypatch.setattr(
        "scripts.aeonisk.multiagent.names_client.generate_baseline_names",
        fake_generate,
    )
    monkeypatch.setattr(
        "scripts.aeonisk.multiagent.names_client.tool_reserve",
        always_conflict,
    )

    client = NamesClient(owner="yags:test")
    assert client.generate_npc_name(faction="Freeborn", pronouns="they/them") is None
