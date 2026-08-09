"""Mocks belong on sinks, not on values.

#103. A bare `MagicMock` in a *value* position lies in specific, silent ways:

    list(mock.npc_agents)         -> []          iterates EMPTY
    bool(mock.is_active)          -> True        filters never exclude
    mock.health > 0               -> TypeError   (this is #81's crash)
    str(mock.name)                -> "<MagicMock name='mock.name' ...>"
    a, b = mock.calculate_range() -> ValueError  (today's de-escalation failure)

The first is the worst, and it is not hypothetical: a test asking "was every NPC
processed?" against a mocked `shared_state` sees an empty list and passes. That
is exactly how #89 survived — NPCs missing from `character_state` for months
with the suite green throughout.

Mocking a *sink* is fine and often right: loggers, LLM providers, message buses,
anything you assert was called. This file polices the attributes the engine
reads values from, and `tests/factories.py` provides realistic builders for them.
"""

import ast
from collections import defaultdict
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parents[1]

# Attributes whose value the engine reads, iterates, compares or formats.
# A mock here does not fail — it produces a plausible-looking wrong answer.
VALUE_BEARING = {
    "position": "calculate_range() returns a mock, which unpacks as empty (ValueError)",
    "character_state": "name/attributes/soulcredit come back as mocks, not values",
    "npc_agents": "iterates EMPTY — the test sees no entities at all",
    "player_agents": "iterates EMPTY — the test sees no entities at all",
    "enemy_agents": "iterates EMPTY — the test sees no entities at all",
}

# Sites predating this guard. Shrinks as tests move to tests/factories.py;
# the companion test below fails if an entry becomes stale, so the list cannot
# quietly outlive the problem.
KNOWN_MOCKED_VALUES = {
    "integration/test_npc_healing_integration.py:30",
    "integration/test_unarmed_combat_integration.py:45",
    "unit/test_adjudication_context.py:85",
    "unit/test_death_save.py:188",
    "unit/test_death_save.py:50",
    "unit/test_deescalation_pipeline.py:79",
    "unit/test_enemy_combat_logging.py:148",
    "unit/test_enemy_combat_logging.py:41",
    "unit/test_enemy_on_enemy_combat.py:68",
    "unit/test_env_objects.py:666",
    "unit/test_env_objects.py:716",
    "unit/test_env_objects.py:773",
    "unit/test_faction_awareness.py:26",
    "unit/test_healing_defeat_guard.py:33",
    "unit/test_npc_attack.py:83",
    "unit/test_npc_combat_logging.py:109",
    "unit/test_npc_context.py:640",
    "unit/test_npc_healing.py:91",
    "unit/test_range_awareness.py:34",
    "unit/test_targeting_validation.py:27",
    "unit/test_targeting_validation.py:437",
}


def bare_mock_value_assignments():
    """Every `x.attr = MagicMock()` where attr is value-bearing and the mock is
    unconfigured (no spec=, no return_value=)."""
    found = defaultdict(list)
    for path in sorted(_TESTS.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            value = node.value
            if not isinstance(value, ast.Call):
                continue
            if getattr(value.func, "id", "") not in ("MagicMock", "Mock"):
                continue
            if value.args or value.keywords:
                continue  # spec'd or configured — the author was explicit
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in VALUE_BEARING:
                    rel = path.relative_to(_TESTS).as_posix()
                    found[target.attr].append(f"{rel}:{node.lineno}")
    return found


class TestNoNewMockedValues:

    def test_value_bearing_attributes_are_not_bare_mocks(self):
        offenders = []
        for attr, sites in bare_mock_value_assignments().items():
            for site in sites:
                if site in KNOWN_MOCKED_VALUES:
                    continue
                offenders.append(f"{site}  .{attr} — {VALUE_BEARING[attr]}")

        assert not offenders, (
            "a bare MagicMock here produces a plausible-looking wrong answer "
            "rather than an error. Use tests/factories.py "
            "(FakeAgent, FakeSharedState, make_position):\n  "
            + "\n  ".join(sorted(offenders)))

    def test_allowlist_has_no_stale_entries(self):
        """Fix a test and its exemption must go with it, or the list grants
        amnesty to code that no longer needs it."""
        live = {site for sites in bare_mock_value_assignments().values()
                for site in sites}
        stale = sorted(KNOWN_MOCKED_VALUES - live)

        assert not stale, (
            "these no longer mock a value-bearing attribute — remove them from "
            "KNOWN_MOCKED_VALUES:\n  " + "\n  ".join(stale))


class TestTheDebtIsShrinking:
    """A ratchet, so the count can only go down."""

    def test_known_mocked_values_does_not_grow(self):
        assert len(KNOWN_MOCKED_VALUES) <= 21, (
            "the allowlist grew; new tests should use tests/factories.py")
