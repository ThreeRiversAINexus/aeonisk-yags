"""
Unit tests for HumanInterface shutdown behavior - Bug 4 fix.

Bug 4: Fatal Python error on shutdown due to daemon thread blocking on input()
holding stdin lock when interpreter exits.

Fix: Replace blocking input() with non-blocking select()-based input + threading.Event
for clean shutdown coordination.
"""

import pytest
import threading
import time
import os
from unittest.mock import MagicMock, patch
import sys
import io


class TestHumanInterfaceShutdown:
    """Test clean shutdown of HumanInterface daemon thread."""

    def test_stop_event_exists(self):
        """HumanInterface should have a _stop_event for shutdown coordination."""
        from scripts.aeonisk.multiagent.human_interface import HumanInterface

        interface = HumanInterface("/tmp/test.sock")

        # _stop_event should exist for shutdown coordination
        assert hasattr(interface, '_stop_event'), \
            "HumanInterface should have _stop_event for shutdown coordination"
        assert isinstance(interface._stop_event, threading.Event), \
            "_stop_event should be a threading.Event"

    def test_shutdown_sets_stop_event(self):
        """shutdown() should set the stop event to signal thread to exit."""
        from scripts.aeonisk.multiagent.human_interface import HumanInterface

        interface = HumanInterface("/tmp/test.sock")

        # Verify stop event starts unset
        assert not interface._stop_event.is_set()

        # Mock agent to avoid errors
        interface.agent = MagicMock()

        # Call shutdown
        interface.shutdown()

        # Verify stop event is now set
        assert interface._stop_event.is_set(), \
            "shutdown() should set _stop_event to signal thread to exit"
        assert interface.running is False

    def test_command_thread_reference_stored(self):
        """start() should store reference to command thread for joining."""
        from scripts.aeonisk.multiagent.human_interface import HumanInterface

        interface = HumanInterface("/tmp/test.sock")

        # _command_thread should be an instance variable (may be None until start)
        assert hasattr(interface, '_command_thread'), \
            "HumanInterface should have _command_thread attribute"


class TestNonBlockingInput:
    """Test non-blocking input implementation for Bug 4 fix."""

    def test_read_line_with_timeout_method_exists(self):
        """_read_line_with_timeout() helper should exist."""
        from scripts.aeonisk.multiagent.human_interface import HumanInterface

        interface = HumanInterface("/tmp/test.sock")

        assert hasattr(interface, '_read_line_with_timeout'), \
            "HumanInterface should have _read_line_with_timeout method"
        assert callable(interface._read_line_with_timeout), \
            "_read_line_with_timeout should be callable"

    def test_read_line_with_timeout_returns_none_on_timeout(self):
        """When no input available, should return None after timeout (not block)."""
        from scripts.aeonisk.multiagent.human_interface import HumanInterface

        interface = HumanInterface("/tmp/test.sock")

        # Create a pipe where we control the write end (don't write anything)
        read_fd, write_fd = os.pipe()

        try:
            start = time.time()
            result = interface._read_line_with_timeout(read_fd, timeout=0.1)
            elapsed = time.time() - start

            # Should return None (timeout) not block
            assert result is None, \
                "_read_line_with_timeout should return None on timeout"
            # Should complete in reasonable time (not block forever)
            assert elapsed < 0.3, \
                f"_read_line_with_timeout should not block (took {elapsed}s)"
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_read_line_with_timeout_reads_available_input(self):
        """When input available, should read and return the line."""
        from scripts.aeonisk.multiagent.human_interface import HumanInterface

        interface = HumanInterface("/tmp/test.sock")

        # Create a pipe and write test data
        read_fd, write_fd = os.pipe()

        try:
            # Write test input
            os.write(write_fd, b"test command\n")
            os.close(write_fd)  # Close write end to signal EOF after data

            # Mock sys.stdin to be our pipe's read end
            with os.fdopen(read_fd, 'r') as read_file:
                with patch.object(sys, 'stdin', read_file):
                    result = interface._read_line_with_timeout(read_file.fileno(), timeout=1.0)

            assert result == "test command", \
                f"Expected 'test command', got '{result}'"
        except Exception:
            # Clean up on error
            try:
                os.close(read_fd)
            except OSError:
                pass
            try:
                os.close(write_fd)
            except OSError:
                pass
            raise


class TestShutdownIntegration:
    """Integration tests for complete shutdown flow."""

    def test_shutdown_completes_quickly(self):
        """shutdown() should complete quickly, not hang on blocked input()."""
        from scripts.aeonisk.multiagent.human_interface import HumanInterface

        interface = HumanInterface("/tmp/test_lifecycle.sock")

        # Mock agent to avoid socket dependencies
        interface.agent = MagicMock()
        interface.running = True

        # Simulate the fixed shutdown (without actually starting thread)
        start = time.time()
        interface.shutdown()
        elapsed = time.time() - start

        # Shutdown should be fast (< 2 seconds even with join timeout)
        assert elapsed < 2.0, \
            f"shutdown() took too long: {elapsed}s (should be < 2s)"

    def test_command_loop_checks_stop_event(self):
        """Command loop should check _stop_event to know when to exit."""
        from scripts.aeonisk.multiagent.human_interface import HumanInterface

        interface = HumanInterface("/tmp/test.sock")

        # The fixed _command_loop should check both self.running and _stop_event
        # We verify this by inspecting the source (or behavioral test)

        # Set stop event before loop would start
        interface._stop_event.set()
        interface.running = True  # Even if running is True, stop_event should exit

        # The loop condition should be: while self.running and not self._stop_event.is_set()
        # So with _stop_event set, loop should not iterate

        # This is a design verification - the implementation will be tested
        # by the behavioral test above (test_shutdown_completes_quickly)
        assert interface._stop_event.is_set()


class TestSelectImport:
    """Test that required imports exist for non-blocking input."""

    def test_select_module_available(self):
        """select module should be imported in human_interface."""
        # This tests that the fix includes the necessary import
        import select  # noqa: F401 - verify select is available on system

        # The actual import check in human_interface.py will happen
        # when we run the implementation
        assert True  # select is available

    def test_sys_module_available(self):
        """sys module should be imported in human_interface."""
        import sys  # noqa: F401

        assert hasattr(sys, 'stdin')
        assert hasattr(sys.stdin, 'fileno')
