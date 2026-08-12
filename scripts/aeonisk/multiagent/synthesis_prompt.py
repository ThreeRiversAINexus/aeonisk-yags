"""The outcome-first synthesis prompt, loaded from YAML rather than baked in (#159).

Both halves of this call used to be string literals in `dm.py` — the system
prompt inline at the call site, the user prompt a 2,291-character f-string. That
put the worst prompt in the system beyond the reach of every tool built to
improve it: `prompt_eval_harness.py` swaps YAML modules through `ModuleSwapper`,
so a prompt in Python cannot be swapped, varied, A/B tested or iterated on.

Rendering is `str.format`, which means the template body must contain no braces
of its own. That is asserted in `tests/unit/test_synthesis_prompt_module.py`
alongside the byte-identity check, because a stray brace would not fail loudly —
it would raise mid-session on the one call that turns mechanics into story.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import yaml

MODULE_PATH = (Path(__file__).parent / "prompts" / "claude" / "en" / "dm"
               / "dm_outcome_synthesis.yaml")

#: What the user prompt renders when there is no prior round. Kept here rather
#: than inline so the "opening round" case is visible to anyone reading the
#: module, and so #158's variants can change it in one place.
NO_PRIOR_ROUND = "(opening round)"


@lru_cache(maxsize=8)
def load_module(path: Optional[str] = None) -> Dict[str, Any]:
    """A synthesis prompt module, cached per path.

    Keyed by path rather than cached as a singleton so an eval harness can
    render a variant in the same process without evicting or poisoning the
    module the live session uses — the two must not be able to see each other's
    prompt.
    """
    with open(path or MODULE_PATH, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


#: Where the previous round's narration gets cut before it goes in the prompt.
#: `full` is what production sends: the *entire* prior round, sitting directly
#: above the rule forbidding its reuse. The others exist so #158 can measure
#: whether that field is the contamination source rather than argue about it.
PREVIOUS_ENDING_MODES = ("full", "final_paragraph", "final_sentence", "none")


def trim_previous_ending(text: str, mode: str = "full") -> str:
    """Cut the prior narration down to what a variant wants to show.

    Continuity needs a handhold, not a transcript. `final_sentence` is the
    smallest thing that still tells the narrator where the last round left off,
    and `none` is the control that says whether any of it is needed.
    """
    if mode not in PREVIOUS_ENDING_MODES:
        raise ValueError(f"unknown previous_ending mode {mode!r}; "
                         f"expected one of {list(PREVIOUS_ENDING_MODES)}")
    text = (text or "").strip()
    if not text or mode == "full":
        return text
    if mode == "none":
        return ""
    if mode == "final_paragraph":
        return text.rsplit("\n\n", 1)[-1].strip()
    sentences = re.findall(r"[^.!?]*[.!?]+[\"'”’]?", text)
    return (sentences[-1].strip() if sentences else text)


def response_schema_block(result_type: Any = None) -> str:
    """The JSON-schema instruction the structured-output layer appends live.

    Reproduced here because a replay outside a session talks to a plain chat
    endpoint: without it the model is never told the shape and every response
    fails validation for a reason that has nothing to do with the prompt under
    test. It is also ~21.7k of the call's 33.8k characters, which is why
    dropping it is a variant worth measuring rather than an obvious win.
    """
    if result_type is None:
        from .outcome_pipeline import OutcomeRoundSynthesis as result_type
    return ("\n\nYou must respond with valid JSON matching this schema:\n"
            + json.dumps(result_type.model_json_schema(), indent=2)
            + "\n\nRespond ONLY with the JSON object, no additional text.")


def system_prompt(module: Optional[Dict[str, Any]] = None,
                  include_schema: Optional[bool] = None) -> str:
    """The narrator's role instruction, and optionally the schema behind it.

    Live, the role line is one sentence and the structured-output layer appends
    ~21,700 characters of Pydantic schema — a schema the decoder already
    enforces. A module may set `include_schema: false` to test whether that dump
    earns its place; the default follows the module, and the module defaults to
    reproducing production.
    """
    module = module or load_module()
    if include_schema is None:
        include_schema = module.get("include_schema", True)
    return module["system_prompt"] + (response_schema_block() if include_schema else "")


def user_prompt(
    round_num: int,
    safe_payload: Sequence[Dict[str, Any]],
    previous_ending: Optional[str],
    safe_lifecycle: Dict[str, Any],
    module: Optional[Dict[str, Any]] = None,
) -> str:
    """Render the round's synthesis request.

    `previous_ending` is, despite its name, the entire previous round's
    narration. It is preserved exactly as it was so this extraction stays a
    pure move; #158 is where it gets trimmed.

    Pass `module` to render a variant. The default is the module the live
    session uses, so a harness cannot change what a session sends by forgetting
    an argument — the override has to be deliberate.

    A module may set `previous_ending: final_sentence` (or `final_paragraph`,
    or `none`) to send less of the prior round. That knob lives in the YAML
    rather than in a caller so the variant is fully declared in the file being
    tested — the whole point of getting these prompts out of Python (#159).
    """
    module = module or load_module()
    prior = trim_previous_ending(previous_ending or "",
                                 module.get("previous_ending", "full"))
    return module["user_prompt"].format(
        round_num=round_num,
        outcomes_json=json.dumps(list(safe_payload), indent=2),
        previous_ending=prior or NO_PRIOR_ROUND,
        lifecycle_json=json.dumps(safe_lifecycle, indent=2, default=str),
    )
