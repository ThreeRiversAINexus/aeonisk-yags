"""Tests for the onboarding quickstart utilities."""

from aeonisk.onboarding.quickstart import QuickstartGuide


def test_quickstart_flowchart_structure():
    """Quickstart flowcharts should expose ordered phases with summaries."""
    guide = QuickstartGuide()

    flow = guide.to_flowchart()

    assert flow["title"] == "Aeonisk Character & Ritual Quickstart"
    assert len(flow["phases"]) >= 4
    assert flow["phases"][0]["id"] == "origin_seed"
    assert {phase["id"] for phase in flow["phases"]} >= {"origin_seed", "bonds", "ritual_loop", "void_breakpoints"}

    # Each phase must provide a callout to reinforce onboarding anchors
    for phase in flow["phases"]:
        assert phase["summary"]
        assert phase["callouts"], "Each quickstart phase requires at least one callout for onboarding anchors."


def test_quickstart_page_layout():
    """The printable quickstart should be laid out as two digestible pages."""
    guide = QuickstartGuide()

    pages = guide.to_two_page_brief()
    assert len(pages) == 2
    assert pages[0]["headline"] == "Page 1: Character Spark"
    assert pages[1]["headline"].startswith("Page 2")

    # Each page should reference Soulcredit or Void reminders for onboarding emphasis
    assert any("Soulcredit" in bullet for bullet in pages[0]["bullets"])
    assert any("Void" in bullet for bullet in pages[1]["bullets"])
