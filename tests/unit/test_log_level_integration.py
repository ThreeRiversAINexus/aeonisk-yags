"""
Integration tests for custom log levels in actual usage.

Verifies that the custom log levels work when imported in the real codebase.
"""

import logging
import pytest
from io import StringIO


def test_llm_provider_has_custom_levels():
    """Test that llm_provider module can use custom log levels."""
    # Import the module (which imports custom_log_levels)
    from scripts.aeonisk.multiagent import llm_provider

    # Verify custom levels are available
    assert hasattr(logging, 'TRACE')
    assert hasattr(logging, 'LLM')
    assert logging.TRACE == 5
    assert logging.LLM == 15


def test_llm_logger_has_custom_levels():
    """Test that llm_logger module can use custom log levels."""
    # Import the module (which imports custom_log_levels)
    from scripts.aeonisk.multiagent import llm_logger

    # Verify custom levels are available
    assert hasattr(logging, 'TRACE')
    assert hasattr(logging, 'LLM')


def test_main_module_has_custom_levels():
    """Test that main module has custom log levels initialized."""
    from scripts.aeonisk.multiagent import main

    # Verify custom levels are available
    assert hasattr(logging, 'TRACE')
    assert hasattr(logging, 'LLM')


def test_logger_methods_available():
    """Test that loggers have .trace() and .llm() methods."""
    from scripts.aeonisk.multiagent import llm_provider

    # Get a logger from the module
    logger = logging.getLogger('scripts.aeonisk.multiagent.test')

    # Verify methods exist
    assert hasattr(logger, 'trace')
    assert hasattr(logger, 'llm')
    assert callable(logger.trace)
    assert callable(logger.llm)


def test_llm_level_filtering():
    """Test that LLM level messages are filtered correctly."""
    from scripts.aeonisk.multiagent import custom_log_levels  # noqa: F401

    # Create test logger at INFO level (should filter LLM=15)
    logger = logging.getLogger('test_llm_filter')
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Capture log output
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Log at LLM level (15) - should be filtered by INFO (20)
    logger.llm("This LLM message should be filtered")

    output = stream.getvalue()
    assert "This LLM message should be filtered" not in output

    # Log at INFO level - should appear
    logger.info("This INFO message should appear")

    output = stream.getvalue()
    assert "This INFO message should appear" in output

    # Cleanup
    logger.removeHandler(handler)


def test_trace_level_filtering():
    """Test that TRACE level messages are filtered correctly."""
    from scripts.aeonisk.multiagent import custom_log_levels  # noqa: F401

    # Create test logger at DEBUG level (should filter TRACE=5)
    logger = logging.getLogger('test_trace_filter')
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Capture log output
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Log at TRACE level (5) - should be filtered by DEBUG (10)
    logger.trace("This TRACE message should be filtered")

    output = stream.getvalue()
    assert "This TRACE message should be filtered" not in output

    # Log at DEBUG level - should appear
    logger.debug("This DEBUG message should appear")

    output = stream.getvalue()
    assert "This DEBUG message should appear" in output

    # Cleanup
    logger.removeHandler(handler)
