"""Tactical Position.__str__ must emit only the 7 canonical position strings.

The bug chain this pins: the Engaged ring printed as 'Engaged-PC'/'Engaged-Enemy'
(side is meaningless at center — calculate_range Rule 1 ignores it). That
non-canonical string leaked into prompts and logs, the DM echoed it back in
position_changes, and the validation filter (canonical-7 allowlist) silently
DROPPED those legitimate movement rulings ("position_change will be skipped").

Canonical set = the schemas Position enum values:
  Engaged, Near-PC, Near-Enemy, Far-PC, Far-Enemy, Extreme-PC, Extreme-Enemy
"""
from aeonisk.multiagent.enemy_agent import Position

CANONICAL = {"Engaged", "Near-PC", "Near-Enemy", "Far-PC", "Far-Enemy",
             "Extreme-PC", "Extreme-Enemy"}


def test_engaged_prints_without_side():
    assert str(Position(ring="Engaged", side="PC")) == "Engaged"
    assert str(Position(ring="Engaged", side="Enemy")) == "Engaged"


def test_all_canonical_strings_round_trip():
    for s in CANONICAL:
        assert str(Position.from_string(s)) == s


def test_legacy_engaged_pc_input_still_parses_to_canonical():
    # historical corpus carries 'Engaged-PC'; parsing stays compatible but the
    # printed form is canonical
    p = Position.from_string("Engaged-PC")
    assert p.ring == "Engaged"
    assert str(p) == "Engaged"


def test_every_ring_side_combination_prints_canonical():
    for ring in ("Engaged", "Near", "Far", "Extreme"):
        for side in ("PC", "Enemy"):
            assert str(Position(ring=ring, side=side)) in CANONICAL
