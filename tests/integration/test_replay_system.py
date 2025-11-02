"""
Integration tests for replay system.

Tests verify that replay_fixture.py correctly replays sessions using cached
LLM responses, enabling deterministic replay for debugging and testing.

NOTE: These integration tests are currently SKIPPED because they make live
API calls and take 5-10 minutes to run. They've been replaced with fast
unit tests in tests/unit/test_replay_mocked.py that use mocked LLM clients.

WHY KEEP THESE TESTS?
- Future comprehensive end-to-end validation
- Regression testing when replay system changes significantly
- Verify real API behavior (not just mocked behavior)

TO RE-ENABLE: Remove @pytest.mark.skip decorators and run with:
  pytest tests/integration/test_replay_system.py -v --timeout=600

Last verified working: 2025-11-01 (commit af21c82)
"""

import pytest
import subprocess
from pathlib import Path
import json


class TestReplaySystem:
    """Integration tests for replay functionality (CURRENTLY SKIPPED - see module docstring)."""

    @pytest.mark.skip(reason="Replaced with fast unit tests - see test_replay_mocked.py. Re-enable for comprehensive E2E validation.")
    @pytest.mark.integration
    def test_full_deterministic_replay(self):
        """
        Full cached replay should produce identical mechanical outcomes.

        Uses the replay_test_fresh.jsonl fixture which has 2 rounds,
        2 players, 1 enemy, and all LLM calls logged (including player calls).

        Expected: --all-cached with --max-rounds 1 should complete successfully.
        Note: Replay is intentionally slow (300-600s) due to API rate limiting.
        """
        fixture_path = "tests/fixtures/sessions/replay_test_fresh.jsonl"
        output_path = "/tmp/test_replay_deterministic.jsonl"

        # Verify fixture exists
        assert Path(fixture_path).exists(), f"Fixture not found: {fixture_path}"

        # Run replay with all caching (long timeout due to intentional rate limiting)
        result = subprocess.run([
            "python", "scripts/replay_fixture.py",
            fixture_path,
            "--all-cached",
            "--max-rounds", "1",
            "--output", output_path
        ], capture_output=True, text=True, timeout=600, cwd="/home/p/Coding/aeonisk-yags")

        # Should complete successfully
        assert result.returncode == 0, f"Replay failed with exit code {result.returncode}\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"

        # Output file should exist
        assert Path(output_path).exists(), f"Output file not created: {output_path}"

        # Output should have content
        output_size = Path(output_path).stat().st_size
        assert output_size > 0, "Output file is empty"

        # TODO: Add comparison with diff_fixtures.py once basic replay works

    @pytest.mark.skip(reason="Replaced with fast unit tests - see test_replay_mocked.py. Re-enable for comprehensive E2E validation.")
    @pytest.mark.integration
    def test_hybrid_mode_cache_until_round(self):
        """
        Hybrid mode should cache early rounds, then generate later rounds live.

        Tests --cache-until-round functionality to ensure replay can switch
        from cached to live LLM generation mid-session.

        Expected: Should complete with rounds 0-1 cached, round 2 live.
        """
        fixture_path = "tests/fixtures/sessions/replay_test_fresh.jsonl"
        output_path = "/tmp/test_replay_hybrid.jsonl"

        # Verify fixture exists
        assert Path(fixture_path).exists(), f"Fixture not found: {fixture_path}"

        # Run replay with hybrid mode (long timeout due to intentional rate limiting)
        result = subprocess.run([
            "python", "scripts/replay_fixture.py",
            fixture_path,
            "--all-cached",
            "--cache-until-round", "1",
            "--max-rounds", "2",
            "--output", output_path
        ], capture_output=True, text=True, timeout=600, cwd="/home/p/Coding/aeonisk-yags")

        # Should complete successfully
        assert result.returncode == 0, f"Hybrid replay failed with exit code {result.returncode}\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"

        # Output file should exist
        assert Path(output_path).exists(), f"Output file not created: {output_path}"

        # Output should have content
        output_size = Path(output_path).stat().st_size
        assert output_size > 0, "Output file is empty"

    @pytest.mark.skip(reason="Replaced with fast unit tests - see test_replay_mocked.py. Re-enable for comprehensive E2E validation.")
    @pytest.mark.integration
    def test_replay_completes_without_hanging(self):
        """
        Replay should complete successfully without hanging indefinitely.

        Note: Replay is intentionally slow (300-600s) due to API rate limiting,
        NOT a performance bug. This test ensures it completes, not speed.
        """
        fixture_path = "tests/fixtures/sessions/replay_test_fresh.jsonl"
        output_path = "/tmp/test_replay_performance.jsonl"

        # Verify fixture exists
        assert Path(fixture_path).exists(), f"Fixture not found: {fixture_path}"

        # Run with realistic timeout (not testing speed, just that it completes)
        result = subprocess.run([
            "python", "scripts/replay_fixture.py",
            fixture_path,
            "--all-cached",
            "--max-rounds", "1",
            "--output", output_path
        ], capture_output=True, text=True, timeout=600, cwd="/home/p/Coding/aeonisk-yags")

        # Should complete successfully
        assert result.returncode == 0, f"Replay failed: {result.stderr}"
