"""
Custom log levels for the Aeonisk multi-agent system.

This module must be imported before any logging configuration occurs.
Import this module at the top of any file that uses custom log levels.
"""

import logging


# Define custom log levels
# TRACE (5) - Ultra-verbose debugging: stacktraces, line-by-line parsing, state transitions
# LLM (15) - API calls: prompts, responses, tokens, rate limiting, cache operations
TRACE_LEVEL = 5
LLM_LEVEL = 15

# Register custom levels with Python's logging system
logging.addLevelName(TRACE_LEVEL, "TRACE")
logging.addLevelName(LLM_LEVEL, "LLM")

# Add level constants to logging module for easy access (logging.TRACE, logging.LLM)
logging.TRACE = TRACE_LEVEL
logging.LLM = LLM_LEVEL


# Add convenience methods to Logger class
def trace(self, message, *args, **kwargs):
    """Log a message at TRACE level (5)."""
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kwargs)


def llm(self, message, *args, **kwargs):
    """Log a message at LLM level (15)."""
    if self.isEnabledFor(LLM_LEVEL):
        self._log(LLM_LEVEL, message, args, **kwargs)


# Attach methods to Logger class
logging.Logger.trace = trace
logging.Logger.llm = llm


# Module-level convenience functions (optional, for use without logger instance)
def get_trace_level():
    """Get the TRACE level value (5)."""
    return TRACE_LEVEL


def get_llm_level():
    """Get the LLM level value (15)."""
    return LLM_LEVEL
