"""Tests for the Aeonisk currency conversion helpers."""

from aeonisk.onboarding.currency import spark_core_to_drip_example


def test_spark_core_conversion_example():
    """The worked example should detail each conversion step."""
    example = spark_core_to_drip_example()

    assert example.name == "Spark Core upkeep conversion"
    assert example.input_resource == "Spark Core"
    assert example.output_resource == "Drip"
    assert example.total_output == 9
    assert len(example.steps) == 3

    # Ensure the example enforces bond or faction acknowledgement for the handoff
    assert any("bond" in step.note.lower() for step in example.steps)
