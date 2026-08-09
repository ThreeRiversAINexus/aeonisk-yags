"""No handler may swallow Ctrl-C, and none may discard an error without trace.

Part of #109. The failure mode this whole testing effort exists to address is a
defect that produces no error — only a slightly-wrong value. 155 broad handlers
in the package are the machinery that converts one into the other.

#81 was exactly this: a TypeError (`'>' not supported between instances of
'NoneType' and 'int'`) caught by a broad handler in the NPC declaration loop and
downgraded to a warning. The agent forfeited its turn, the round looked normal,
and the engine's own ghost-agent detector fired with no cause attached.

These tests police the two mechanical cases — bare handlers, and handlers that
discard the exception entirely — leaving the judgement calls for #109 proper.
"""

import ast
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[2] / "scripts" / "aeonisk" / "multiagent"


def python_files():
    return sorted(_PKG.glob("*.py"))


def handlers(path):
    """Yield (node, source_lines) for every except clause in a file."""
    source = path.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            yield node


class TestNoBareExcept:
    """`except:` also catches KeyboardInterrupt and SystemExit.

    Ctrl-C during one of those paths does not do what the operator expects —
    which matters when a session runs for nineteen minutes.
    """

    def test_no_bare_except_in_the_package(self):
        offenders = [
            f"{path.name}:{node.lineno}"
            for path in python_files()
            for node in handlers(path)
            if node.type is None
        ]

        assert not offenders, (
            "bare `except:` catches KeyboardInterrupt and SystemExit — narrow it "
            "to `except Exception` at minimum:\n  " + "\n  ".join(offenders))


class TestNoSilentDiscard:
    """A handler whose whole body is `pass` leaves no evidence at all.

    Not banned outright — a few are legitimate (optional cleanup, best-effort
    telemetry) — but each must say why, so the next reader can tell a considered
    decision from an oversight.
    """

    def test_silent_handlers_carry_a_reason(self):
        undocumented = []
        for path in python_files():
            lines = path.read_text().splitlines()
            for node in handlers(path):
                body = node.body
                if not (len(body) == 1 and isinstance(body[0], ast.Pass)):
                    continue
                # A comment on the `except` line or the `pass` line counts.
                window = " ".join(
                    lines[i] for i in range(node.lineno - 1, min(node.lineno + 1, len(lines)))
                )
                if "#" not in window:
                    undocumented.append(f"{path.name}:{node.lineno}")

        assert not undocumented, (
            "these handlers discard the exception with no explanation; add a "
            "comment saying why swallowing is correct here:\n  "
            + "\n  ".join(undocumented))


class TestRangeCalculationIsNotSilentlyZeroed:
    """Range failures must not quietly become "no penalty".

    `enemy.position.calculate_range(...)` failing used to fall through a bare
    handler to `("Unknown", 0)`. A positioning bug therefore *improved* every
    attack, and was invisible in the log because "Unknown" reads like an
    ordinary range band. The audit saw a Heavy Machine Gun firing at Extreme
    range with a -6 penalty; had that call failed, the penalty would have been 0
    and nothing would have said so.
    """

    @pytest.mark.parametrize("filename", ["enemy_combat.py", "enemy_prompts.py"])
    def test_range_fallbacks_log_rather_than_pass_silently(self, filename):
        source = (_PKG / filename).read_text()
        tree = ast.parse(source)
        lines = source.splitlines()

        silent = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body_src = "\n".join(
                lines[node.lineno - 1: node.end_lineno or node.lineno])
            if "range_penalty" not in body_src:
                continue
            if "logger" not in body_src:
                silent.append(f"{filename}:{node.lineno}")

        assert not silent, (
            "a range-calculation failure silently becomes zero penalty, which "
            "changes combat outcomes with no trace:\n  " + "\n  ".join(silent))
