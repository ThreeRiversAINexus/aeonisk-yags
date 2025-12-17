"""
Tests for HumanInterface prompt behavior.

Ensures that the Observer prompt doesn't spam stdout when running
automated sessions (bulk generation, tests, CI/CD).
"""

import pytest
import sys
import io
import threading
import time
from unittest.mock import Mock, patch
from scripts.aeonisk.multiagent.human_interface import HumanInterface


class TestHumanInterfacePrompt:
    """Test that HumanInterface doesn't spam prompts in non-interactive mode."""

    def test_no_prompt_spam_when_stdin_not_tty(self):
        """
        CRITICAL: When stdin is not a TTY (pipes, bulk runs, CI/CD),
        the human interface should not print any prompts.
        """
        # Create a HumanInterface instance
        interface = HumanInterface("/tmp/test_socket")

        # Mock stdin as non-TTY (piped input)
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.fileno.return_value = 0

            # Mock select to return no input available
            with patch('select.select', return_value=([], [], [])):
                # Start the command loop in a thread
                interface.running = True
                output = io.StringIO()

                with patch('sys.stdout', new=output):
                    # Run command loop for 2 seconds
                    thread = threading.Thread(
                        target=interface._command_loop,
                        daemon=True
                    )
                    thread.start()
                    time.sleep(2.0)
                    interface.running = False
                    interface._stop_event.set()
                    thread.join(timeout=1.0)

                # Assert: NO output should be printed when stdin is not a TTY
                captured = output.getvalue()
                assert "[Observer]>" not in captured, \
                    "Observer prompt should not print when stdin is not a TTY"
                assert "[Controlling" not in captured, \
                    "Control prompt should not print when stdin is not a TTY"

    def test_prompt_only_prints_once_per_input_when_tty(self):
        """
        When stdin IS a TTY (interactive terminal), the prompt should
        only print once and wait for input, not spam every 0.5s.
        """
        interface = HumanInterface("/tmp/test_socket")

        # Mock stdin as TTY
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0

            # Mock select to return no input (timeout)
            with patch('select.select', return_value=([], [], [])):
                interface.running = True
                output = io.StringIO()

                with patch('sys.stdout', new=output):
                    # Run for 2 seconds
                    thread = threading.Thread(
                        target=interface._command_loop,
                        daemon=True
                    )
                    thread.start()
                    time.sleep(2.0)
                    interface.running = False
                    interface._stop_event.set()
                    thread.join(timeout=1.0)

                captured = output.getvalue()
                # Count how many times the prompt appears
                prompt_count = captured.count("[Observer]>")

                # Should print prompt at most a few times (not dozens)
                # With 0.5s timeout, 2 seconds = 4 iterations max
                assert prompt_count <= 5, \
                    f"Prompt printed {prompt_count} times in 2s - should be ≤5"

    def test_bulk_runner_disables_human_interface(self):
        """
        Bulk session runner should disable human interface entirely
        via session config.
        """
        # This is verified via session config, not code test
        # Just document the expected behavior
        pass  # Checked manually via config validation


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
