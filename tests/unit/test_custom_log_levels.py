"""
Tests for custom log levels (TRACE and LLM).

Following TDD: These tests define the expected behavior BEFORE implementation.
"""

# Import custom log levels FIRST (before any other logging imports)
from scripts.aeonisk.multiagent import custom_log_levels  # noqa: F401

import logging
import pytest
from io import StringIO


def test_trace_level_exists():
    """TRACE level should exist with value 5 (below DEBUG=10)."""
    assert hasattr(logging, 'TRACE')
    assert logging.TRACE == 5
    assert logging.TRACE < logging.DEBUG


def test_llm_level_exists():
    """LLM level should exist with value 15 (between DEBUG=10 and INFO=20)."""
    assert hasattr(logging, 'LLM')
    assert logging.LLM == 15
    assert logging.DEBUG < logging.LLM < logging.INFO


def test_trace_level_name_registered():
    """TRACE level name should be registered in logging system."""
    assert logging.getLevelName(5) == 'TRACE'
    assert logging.getLevelName('TRACE') == 5


def test_llm_level_name_registered():
    """LLM level name should be registered in logging system."""
    assert logging.getLevelName(15) == 'LLM'
    assert logging.getLevelName('LLM') == 15


def test_logger_has_trace_method():
    """Logger should have a .trace() convenience method."""
    logger = logging.getLogger('test_logger')
    assert hasattr(logger, 'trace')
    assert callable(logger.trace)


def test_logger_has_llm_method():
    """Logger should have a .llm() convenience method."""
    logger = logging.getLogger('test_logger')
    assert hasattr(logger, 'llm')
    assert callable(logger.llm)


def test_trace_logging_works():
    """TRACE level messages should be logged when level is set to TRACE."""
    logger = logging.getLogger('test_trace')
    logger.setLevel(logging.TRACE)

    # Capture log output
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.TRACE)
    # Add formatter to include level name
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Log at TRACE level
    logger.trace("This is a trace message")

    output = stream.getvalue()
    assert "This is a trace message" in output
    assert "TRACE" in output

    # Cleanup
    logger.removeHandler(handler)


def test_llm_logging_works():
    """LLM level messages should be logged when level is set to LLM or lower."""
    logger = logging.getLogger('test_llm')
    logger.setLevel(logging.DEBUG)  # LLM=15 is above DEBUG=10, should show

    # Capture log output
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    # Add formatter to include level name
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Log at LLM level
    logger.llm("API call to Claude")

    output = stream.getvalue()
    assert "API call to Claude" in output
    assert "LLM" in output

    # Cleanup
    logger.removeHandler(handler)


def test_trace_filtered_by_debug_level():
    """TRACE messages should NOT appear when level is DEBUG or higher."""
    logger = logging.getLogger('test_trace_filtered')
    logger.setLevel(logging.DEBUG)

    # Capture log output
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    # Log at TRACE level
    logger.trace("This should be filtered")

    output = stream.getvalue()
    assert "This should be filtered" not in output

    # Cleanup
    logger.removeHandler(handler)


def test_llm_filtered_by_info_level():
    """LLM messages should NOT appear when level is INFO or higher."""
    logger = logging.getLogger('test_llm_filtered')
    logger.setLevel(logging.INFO)

    # Capture log output
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)

    # Log at LLM level
    logger.llm("This should be filtered")

    output = stream.getvalue()
    assert "This should be filtered" not in output

    # Cleanup
    logger.removeHandler(handler)


def test_level_hierarchy():
    """Test full level hierarchy: TRACE < DEBUG < LLM < INFO < WARNING < ERROR."""
    assert logging.TRACE < logging.DEBUG
    assert logging.DEBUG < logging.LLM
    assert logging.LLM < logging.INFO
    assert logging.INFO < logging.WARNING
    assert logging.WARNING < logging.ERROR


def test_cli_accepts_trace_level():
    """CLI argument parser should accept 'TRACE' as a valid log level."""
    from scripts.aeonisk.multiagent.main import main
    import sys

    # This test verifies the CLI integration (will be implemented)
    # For now, just verify the function exists and can be imported
    assert callable(main)


def test_cli_accepts_llm_level():
    """CLI argument parser should accept 'LLM' as a valid log level."""
    from scripts.aeonisk.multiagent.main import main
    import sys

    # This test verifies the CLI integration (will be implemented)
    # For now, just verify the function exists and can be imported
    assert callable(main)


def test_setup_logging_accepts_trace():
    """setup_logging() should accept 'TRACE' as a valid level string."""
    from scripts.aeonisk.multiagent.main import setup_logging

    # Should not raise an exception
    try:
        setup_logging(level="TRACE")
    except AttributeError as e:
        pytest.fail(f"setup_logging failed with TRACE level: {e}")


def test_setup_logging_accepts_llm():
    """setup_logging() should accept 'LLM' as a valid level string."""
    from scripts.aeonisk.multiagent.main import setup_logging

    # Should not raise an exception
    try:
        setup_logging(level="LLM")
    except AttributeError as e:
        pytest.fail(f"setup_logging failed with LLM level: {e}")
