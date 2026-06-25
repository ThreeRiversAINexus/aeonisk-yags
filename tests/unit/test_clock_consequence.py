"""
Clock completions must always hand the DM a non-empty, in-world consequence.

Root cause this guards against: ~116/118 authored configs leave
`filled_consequence` empty, and even when it is authored, the engine only
passed `{clock_name, reason}` to the DM's synthesis input -- never the
consequence. So dramatic clocks completed meaningless, and the DM improvised
near-misses ("steadies instead of tearing apart") instead of rendering the
resolution as fact.

Contract:
1. SceneClock.effective_consequence is the authored filled_consequence when set,
   otherwise a non-empty fallback synthesized from advance_meaning (then
   description). It is NEVER empty.
2. When a clock fills, get_and_clear_filled_clocks() entries carry that
   effective consequence so the DM synthesis actually receives it.
"""

from aeonisk.multiagent.mechanics import MechanicsEngine, SceneClock


class TestEffectiveConsequence:
    def test_authored_consequence_used_verbatim(self):
        clock = SceneClock(
            name="Bond Resonance Collapse",
            maximum=4,
            advance_meaning="the thread frays",
            filled_consequence="The bond snaps in open court.",
        )
        assert clock.effective_consequence == "The bond snaps in open court."

    def test_empty_consequence_synthesized_from_advance_meaning(self):
        clock = SceneClock(
            name="Bond Stability",
            maximum=6,
            advance_meaning="visible distortions, pain for the Matrons, void leakage",
            filled_consequence="",  # authored config left this blank
        )
        eff = clock.effective_consequence
        assert eff.strip(), "effective_consequence must never be empty"
        # the synthesized text is grounded in the clock's own advance_meaning
        assert "distortions" in eff.lower()

    def test_blank_advance_meaning_falls_back_to_description(self):
        clock = SceneClock(
            name="Secret Exposure",
            maximum=5,
            advance_meaning="",
            description="how close the real truth is to coming out",
            filled_consequence="",
        )
        eff = clock.effective_consequence
        assert eff.strip(), "effective_consequence must never be empty"
        assert "truth" in eff.lower()

    def test_never_empty_even_with_nothing_authored(self):
        clock = SceneClock(name="Bare Clock", maximum=3)
        assert clock.effective_consequence.strip(), "must always yield some in-world text"


class TestFilledClocksCarryConsequence:
    def test_filled_clock_entry_includes_authored_consequence(self):
        engine = MechanicsEngine(jsonl_logger=None)
        engine.create_scene_clock(
            name="Bond Resonance Collapse",
            maximum=4,
            advance_meaning="the thread frays",
            filled_consequence="The bond snaps in open court.",
        )
        engine.advance_clock("Bond Resonance Collapse", ticks=4, reason="press the matrons")
        filled = engine.get_and_clear_filled_clocks()
        assert len(filled) == 1
        entry = filled[0]
        assert entry["clock_name"] == "Bond Resonance Collapse"
        assert entry.get("consequence") == "The bond snaps in open court."

    def test_filled_clock_entry_synthesizes_when_unauthored(self):
        engine = MechanicsEngine(jsonl_logger=None)
        engine.create_scene_clock(
            name="Bond Stability",
            maximum=6,
            advance_meaning="visible distortions, pain for the Matrons, void leakage",
            # filled_consequence omitted -> empty, as in the tribunal config
        )
        engine.advance_clock("Bond Stability", ticks=6, reason="ritual fails")
        filled = engine.get_and_clear_filled_clocks()
        assert len(filled) == 1
        consequence = filled[0].get("consequence", "")
        assert consequence.strip(), "DM must receive a non-empty consequence even when config omitted it"
        assert "distortions" in consequence.lower()


class TestFilledClocksGuidance:
    """The synthesis guidance must surface consequences and forbid near-misses."""

    def test_empty_when_no_filled_clocks(self):
        from aeonisk.multiagent.dm import format_filled_clocks_guidance
        assert format_filled_clocks_guidance([]) == ""

    def test_surfaces_each_consequence_as_fact(self):
        from aeonisk.multiagent.dm import format_filled_clocks_guidance
        text = format_filled_clocks_guidance([
            {"clock_name": "Bond Resonance Collapse",
             "consequence": "The bond snaps in open court."},
        ])
        # the actual consequence text must reach the DM, not just the clock name
        assert "The bond snaps in open court." in text
        assert "Bond Resonance Collapse" in text

    def test_forbids_near_miss_narration(self):
        from aeonisk.multiagent.dm import format_filled_clocks_guidance
        text = format_filled_clocks_guidance([
            {"clock_name": "Verdict", "consequence": "The verdict is delivered."},
        ]).lower()
        # the directive that stops the DM walking completions back into "almost"
        assert "happened" in text
        assert "near-miss" in text or "almost" in text

    def test_extreme_urgency_on_overflow(self):
        from aeonisk.multiagent.dm import format_filled_clocks_guidance
        text = format_filled_clocks_guidance(
            [{"clock_name": "Doom", "consequence": "It detonates."}],
            critical_overflow=True,
        )
        assert "EXTREME URGENCY" in text
