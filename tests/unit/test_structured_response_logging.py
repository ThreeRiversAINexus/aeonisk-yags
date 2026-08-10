"""A structured LLM response must be logged as JSON, not as `repr()`.

Found by running a replay end to end (#100). The ClaudeProvider logged
`str(result.output)`, which for a Pydantic model is the `field=value` repr:

    success_tier=<SuccessTier.FAILURE: 'failure'> margin=-13 effects=Mecha...

The OpenAI path (`openai_structured.py:363`) logged the raw JSON for the same
schemas. Two writers of one field, disagreeing — 104 events in the corpus, all
`claude-sonnet-4-5`, across six schemas that the OpenAI path recorded as JSON.

It matters twice over: the DM's structured output is the authoritative
mechanical record in the training corpus, and replay cannot reconstruct a model
from a repr without `eval`.
"""

import json

import pytest
from pydantic import BaseModel

from scripts.aeonisk.multiagent.schemas.action_resolution import SuccessTier


class Nested(BaseModel):
    tier: SuccessTier
    note: str


class Sample(BaseModel):
    margin: int
    nested: Nested
    tags: list[str]


@pytest.fixture
def model():
    return Sample(margin=-13,
                  nested=Nested(tier=SuccessTier.FAILURE, note="he'd stalled"),
                  tags=["a", "b"])


class TestReprIsNotRoundTrippable:
    """Why the old format had to go, asserted rather than assumed."""

    def test_repr_does_not_parse_as_json(self, model):
        with pytest.raises(json.JSONDecodeError):
            json.loads(str(model))

    def test_repr_loses_the_enum_to_a_debug_form(self, model):
        """`<SuccessTier.FAILURE: 'failure'>` is not a value any parser reads."""
        assert "<SuccessTier.FAILURE:" in str(model)

    def test_json_round_trips_exactly(self, model):
        assert Sample.model_validate_json(model.model_dump_json()) == model


class TestTheClaudeProviderLogsJSON:
    """The provider is the thing under test — the schema was never the variable.

    `ActionAdjudication` appears in the corpus 117 times as JSON (OpenAI) and 26
    times as repr (Claude).
    """

    def test_logs_a_json_payload(self, model):
        from scripts.aeonisk.multiagent.llm_provider import serialize_structured_response

        assert json.loads(serialize_structured_response(model))["margin"] == -13

    def test_enum_serializes_to_its_value(self, model):
        from scripts.aeonisk.multiagent.llm_provider import serialize_structured_response

        payload = json.loads(serialize_structured_response(model))

        assert payload["nested"]["tier"] == "failure"

    def test_matches_what_the_openai_path_records(self, model):
        """openai_structured.py logs the API's raw JSON content; this must be
        the same shape, or the corpus stays inconsistent by provider."""
        from scripts.aeonisk.multiagent.llm_provider import serialize_structured_response

        assert json.loads(serialize_structured_response(model)) == \
            json.loads(model.model_dump_json())

    def test_non_model_output_still_produces_a_string(self):
        """Not every result_type is a BaseModel — don't crash the logger."""
        from scripts.aeonisk.multiagent.llm_provider import serialize_structured_response

        assert serialize_structured_response("plain text") == "plain text"

    def test_a_serialization_failure_never_breaks_the_call(self):
        """Logging is telemetry. It must not take down a resolved LLM call."""
        from scripts.aeonisk.multiagent.llm_provider import serialize_structured_response

        class Exploding(BaseModel):
            def model_dump_json(self, **kwargs):
                raise RuntimeError("boom")

        assert isinstance(serialize_structured_response(Exploding()), str)
