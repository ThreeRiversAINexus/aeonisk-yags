"""A prompt that could not be varied must never be scored as though it was (#158).

Three call sites in the self-judge loop swallowed the swap failure and fell back
to `case.system_prompt` — replaying the *original* prompt and scoring it as the
rewrite. That is worse than a crash. A crash stops you; this hands the optimiser
numbers that describe a prompt it never sent, and then the judge iterates on
them. Ten iterations later you have a carefully tuned rewrite whose entire
evidence base is the prompt it was supposed to replace.

It was reachable, not theoretical: `ModuleSwapper` looks for a module's body
inside the recorded *system* prompt, and `dm_outcome_synthesis` keeps its
template in the *user* message. Every one of its 118 cases fails the swap, so a
self-judge run over them would have scored 118 unmodified prompts and reported
a number.

All four call sites now go through `build_modified_prompts`, which drops what it
cannot vary, counts it, and raises when that leaves nothing.
"""

from pathlib import Path

import pytest
import yaml

from scripts.prompt_eval_harness import (
    MODULE_BODY_KEYS, UnswappableCases, _write_module_yaml,
    build_modified_prompts, module_body, module_body_key, replacement_shape,
)


class FakeCase:
    def __init__(self, case_id, system_prompt):
        self.case_id = case_id
        self.system_prompt = system_prompt
        self.user_prompt = f"user message for {case_id}"
        self.kind_name = "resolution"


class FakeSwapper:
    """Swaps when the old body is present, raises when it is not — the real
    `ModuleSwapper` contract (`swap_module` raises ValueError on a miss)."""

    def __init__(self, old_body):
        self.old_body = old_body

    def swap_module(self, system_prompt, module_name, new_content):
        if self.old_body not in system_prompt:
            raise ValueError(f"Module {module_name!r} content not found")
        return system_prompt.replace(self.old_body, new_content)


SWAPPER = FakeSwapper("OLD BODY")


class TestBuildModifiedPrompts:

    def test_a_swappable_case_gets_the_new_content(self):
        """Resolution keeps the recorded user message verbatim — only the
        system prompt varies. Synthesis is the kind that re-renders."""
        cases = [FakeCase("c1", "prefix OLD BODY suffix")]

        prompts, kept, dropped = build_modified_prompts(cases, SWAPPER, "m", "NEW")

        assert prompts == {"c1": ("prefix NEW suffix", "user message for c1")}
        assert [c.case_id for c in kept] == ["c1"]
        assert dropped == []

    def test_an_unswappable_case_is_dropped_not_passed_through(self):
        """The whole point. Before, `c2` was replayed with its original prompt
        and its score counted toward the rewrite."""
        cases = [FakeCase("c1", "has OLD BODY"), FakeCase("c2", "has nothing")]

        prompts, kept, dropped = build_modified_prompts(cases, SWAPPER, "m", "NEW")

        assert "c2" not in prompts
        assert [c.case_id for c in kept] == ["c1"]
        assert dropped == ["c2"]

    def test_no_dropped_case_keeps_its_original_prompt_anywhere(self):
        cases = [FakeCase("c1", "has OLD BODY"), FakeCase("c2", "has nothing")]

        prompts, _, _ = build_modified_prompts(cases, SWAPPER, "m", "NEW")

        assert "has nothing" not in [system for system, _user in prompts.values()]

    def test_dropping_everything_raises_rather_than_scoring_nothing(self):
        """A run that varied no prompt must not report a score — that is the
        expensive form of a check that cannot fail."""
        cases = [FakeCase("c1", "no match"), FakeCase("c2", "also none")]

        with pytest.raises(UnswappableCases, match="none of 2 cases"):
            build_modified_prompts(cases, SWAPPER, "dm_outcome_synthesis", "NEW")

    def test_the_error_names_the_module_so_the_cause_is_findable(self):
        with pytest.raises(UnswappableCases, match="dm_outcome_synthesis"):
            build_modified_prompts([FakeCase("c", "x")], SWAPPER,
                                   "dm_outcome_synthesis", "NEW")

    def test_an_empty_case_list_is_not_an_error(self):
        """Nothing to vary is a filter result, not a swap failure."""
        assert build_modified_prompts([], SWAPPER, "m", "NEW") == ({}, [], [])


class TestEverySiteUsesIt:
    """A helper only helps if the callers actually go through it."""

    SOURCE = Path(__file__).parent.parent.parent / "scripts/prompt_eval_harness.py"

    def test_no_call_site_still_falls_back_to_the_original_prompt(self):
        text = self.SOURCE.read_text(encoding="utf-8")

        assert "modified_prompts[case.case_id] = case.system_prompt" not in text
        assert "reg_prompts[case.case_id] = case.system_prompt" not in text
        assert "validation_prompts[case.case_id] = case.system_prompt" not in text

    def test_all_four_sites_call_the_helper(self):
        text = self.SOURCE.read_text(encoding="utf-8")

        assert text.count("build_modified_prompts(") == 5  # 1 def + 4 callers


class TestModuleShapeRoundTrips:
    """A self-judged rewrite has to load again, or the loop optimises a file
    nothing can read."""

    def test_the_body_key_is_recovered_from_the_source(self, tmp_path):
        path = tmp_path / "m.yaml"
        path.write_text(yaml.dump({"module": "dm_outcome_synthesis",
                                   "system_prompt": "role line",
                                   "user_prompt": "the template"}))

        key, siblings = replacement_shape(path)

        assert key == "user_prompt"
        assert siblings == {"system_prompt": "role line"}

    def test_a_variants_config_survives_a_rewrite(self):
        """The one that bites a self-judge run.

        A rewrite changes the prose and nothing else. Carrying forward only
        `*_prompt` keys dropped `previous_ending: final_sentence` from V1, so
        the module the loop saved sent the whole previous round again while the
        score it reported came from a run that had not — an artifact that
        disagrees with its own number, and nothing to say so.
        """
        prompts = Path(__file__).parent.parent.parent / (
            "scripts/aeonisk/multiagent/prompts/claude/en/dm")
        for name, knob, value in (("v1", "previous_ending", "final_sentence"),
                                  ("v3", "include_schema", False)):
            source = prompts / f"dm_outcome_synthesis_{name}.yaml"

            body_key, siblings = replacement_shape(source)

            assert siblings.get(knob) == value, f"{name} would lose {knob}"
            assert body_key == "user_prompt"

    def test_a_rewrite_loses_no_key_the_source_had(self, tmp_path):
        source = tmp_path / "src.yaml"
        source.write_text(yaml.dump({
            "version": "1.0.0", "module": "m", "description": "d",
            "system_prompt": "role", "user_prompt": "body",
            "previous_ending": "final_sentence", "include_schema": False,
            "notes": "why this variant exists\nover two lines"}))
        key, siblings = replacement_shape(source)
        out = tmp_path / "final_module.yaml"

        _write_module_yaml(out, "m", "REWRITTEN", description="best",
                           body_key=key, extra=siblings)

        after = yaml.safe_load(out.read_text())
        assert set(yaml.safe_load(source.read_text())) <= set(after)
        assert after["include_schema"] is False          # not the string "False"
        assert after["notes"].endswith("over two lines")  # block scalar, not escaped
        assert after["user_prompt"] == "REWRITTEN"

    def test_a_content_module_is_unchanged(self, tmp_path):
        path = tmp_path / "m.yaml"
        path.write_text(yaml.dump({"module": "dm_combat", "content": "body"}))

        assert replacement_shape(path) == ("content", {})

    def test_an_unreadable_file_falls_back_rather_than_crashing(self, tmp_path):
        assert replacement_shape(tmp_path / "missing.yaml") == (MODULE_BODY_KEYS[0], {})

    def test_a_rewrite_written_under_the_source_key_loads_again(self, tmp_path):
        """The regression: written under `content:`, this file would come back
        from `module_body` as the empty string and be silently unswappable."""
        out = tmp_path / "final_module.yaml"

        _write_module_yaml(out, "dm_outcome_synthesis", "REWRITTEN TEMPLATE",
                           description="best", body_key="user_prompt",
                           extra={"system_prompt": "role line"})

        data = yaml.safe_load(out.read_text())
        assert module_body_key(data) == "user_prompt"
        assert module_body(data) == "REWRITTEN TEMPLATE"
        assert data["system_prompt"] == "role line"

    def test_the_default_shape_is_still_content(self, tmp_path):
        out = tmp_path / "m.yaml"

        _write_module_yaml(out, "dm_combat", "body text")

        assert yaml.safe_load(out.read_text())["content"] == "body text"

    def test_a_multiline_body_survives_the_block_scalar(self, tmp_path):
        out = tmp_path / "m.yaml"
        body = "first line\n\nthird line after a blank"

        _write_module_yaml(out, "dm_combat", body, body_key="user_prompt")

        assert yaml.safe_load(out.read_text())["user_prompt"] == body
