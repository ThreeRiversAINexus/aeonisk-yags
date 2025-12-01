"""
Unit tests for bulk_session_runner.py

Tests bulk orchestration logic without running actual sessions.
Uses mocking for subprocess and file I/O operations.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from scripts.bulk_session_runner import (
    check_proxy_health,
    load_session_config,
    modify_config_for_bulk_run,
    inject_proxy_config,
    extract_session_stats,
    get_completed_runs,
    calculate_bulk_stats,
    run_single_session,
    check_session_completed,
    load_bulk_run_metadata,
    write_bulk_run_metadata,
    discover_run_metadata_from_dirs,
    get_last_successful_round,
    count_llm_calls_in_jsonl,
    try_replay_session,
    RunResult,
    BulkRunStats
)
import subprocess


class TestProxyHealthCheck:
    """Test proxy health check functionality."""

    @patch('scripts.bulk_session_runner.requests.get')
    def test_healthy_proxy(self, mock_get):
        """Test successful proxy health check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        is_healthy, message = check_proxy_health("http://localhost:8000")

        assert is_healthy is True
        assert "healthy" in message.lower()
        mock_get.assert_called_once_with("http://localhost:8000/health", timeout=5)

    @patch('scripts.bulk_session_runner.requests.get')
    def test_unhealthy_proxy(self, mock_get):
        """Test proxy returning non-200 status."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        is_healthy, message = check_proxy_health("http://localhost:8000")

        assert is_healthy is False
        assert "500" in message

    @patch('scripts.bulk_session_runner.requests.get')
    def test_proxy_connection_error(self, mock_get):
        """Test proxy unreachable (connection error)."""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()

        is_healthy, message = check_proxy_health("http://localhost:8000")

        assert is_healthy is False
        assert "cannot connect" in message.lower()

    @patch('scripts.bulk_session_runner.requests.get')
    def test_proxy_timeout(self, mock_get):
        """Test proxy health check timeout."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()

        is_healthy, message = check_proxy_health("http://localhost:8000", timeout=2)

        assert is_healthy is False
        assert "timeout" in message.lower()


class TestConfigManipulation:
    """Test session config loading and modification."""

    def test_load_session_config(self):
        """Test loading JSON session config."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {
                "session_name": "test_session",
                "max_turns": 5,
                "agents": {}
            }
            json.dump(test_config, f)
            temp_path = f.name

        try:
            config = load_session_config(temp_path)
            assert config['session_name'] == 'test_session'
            assert config['max_turns'] == 5
        finally:
            Path(temp_path).unlink()

    def test_modify_config_for_bulk_run(self):
        """Test config modification for bulk run."""
        original_config = {
            "session_name": "base_session",
            "max_turns": 5,
            "agents": {}
        }

        modified = modify_config_for_bulk_run(
            original_config,
            run_id=42,
            output_path="/tmp/output.jsonl"
        )

        # Verify modifications
        assert modified['session_name'] == 'base_session_run_0042'
        assert modified['random_seed'] == 42000  # run_id * 1000
        assert modified['max_turns'] == 5  # Unchanged

    def test_modify_config_preserves_existing_seed(self):
        """Test that existing random_seed is preserved."""
        original_config = {
            "session_name": "session",
            "random_seed": 12345
        }

        modified = modify_config_for_bulk_run(
            original_config,
            run_id=1,
            output_path="/tmp/out.jsonl"
        )

        assert modified['random_seed'] == 12345  # Not overwritten

    def test_inject_proxy_config_dm(self):
        """Test proxy config injection into DM agent."""
        config = {
            "agents": {
                "dm": {
                    "llm": {
                        "provider": "openai",
                        "model": "gpt-5-mini"
                    }
                }
            }
        }

        modified = inject_proxy_config(config, "http://proxy:8000")

        dm_llm = modified['agents']['dm']['llm']
        assert dm_llm['use_proxy'] is True
        assert dm_llm['proxy_url'] == "http://proxy:8000"
        assert dm_llm['provider'] == "openai"  # Preserved

    def test_inject_proxy_config_players(self):
        """Test proxy config injection into player agents."""
        config = {
            "agents": {
                "players": [
                    {"name": "Player1", "llm": {"provider": "anthropic"}},
                    {"name": "Player2", "llm": {"provider": "openai"}}
                ]
            }
        }

        modified = inject_proxy_config(config, "http://proxy:8000")

        for player in modified['agents']['players']:
            assert player['llm']['use_proxy'] is True
            assert player['llm']['proxy_url'] == "http://proxy:8000"

    def test_inject_proxy_config_no_agents(self):
        """Test proxy injection handles missing agents gracefully."""
        config = {"session_name": "test"}

        # Should not raise error
        modified = inject_proxy_config(config, "http://proxy:8000")

        assert modified['session_name'] == "test"


class TestSessionStatsExtraction:
    """Test extraction of statistics from session JSONL files."""

    def test_extract_session_stats_success(self):
        """Test extracting tokens and rounds from valid JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            # Write test events
            f.write(json.dumps({"event_type": "session_start", "round": 0}) + "\n")
            f.write(json.dumps({
                "event_type": "llm_call",
                "round": 1,
                "tokens": {"input": 100, "output": 50, "total": 150}
            }) + "\n")
            f.write(json.dumps({
                "event_type": "llm_call",
                "round": 2,
                "tokens": {"input": 200, "output": 100, "total": 300}
            }) + "\n")
            f.write(json.dumps({"event_type": "round_summary", "round": 3}) + "\n")
            temp_path = Path(f.name)

        try:
            total_tokens, max_round = extract_session_stats(temp_path)

            assert total_tokens == 450  # 150 + 300
            assert max_round == 3
        finally:
            temp_path.unlink()

    def test_extract_session_stats_no_file(self):
        """Test handling of missing JSONL file."""
        total_tokens, max_round = extract_session_stats(Path("/nonexistent/file.jsonl"))

        assert total_tokens is None
        assert max_round is None

    def test_extract_session_stats_empty_file(self):
        """Test handling of empty JSONL file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            temp_path = Path(f.name)

        try:
            total_tokens, max_round = extract_session_stats(temp_path)

            assert total_tokens == 0
            assert max_round == 0
        finally:
            temp_path.unlink()


class TestResumeCapability:
    """Test resume functionality for bulk runs."""

    def test_get_completed_runs(self):
        """Test identification of completed runs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create run subdirectories with session files containing session_end
            for run_id in [1, 5, 10]:
                run_dir = output_dir / f"run_{run_id:04d}"
                run_dir.mkdir()
                with open(run_dir / "session_test.jsonl", "w") as f:
                    f.write(json.dumps({"event_type": "session_start"}) + "\n")
                    f.write(json.dumps({"event_type": "session_end"}) + "\n")

            # Create incomplete run (no session_end event)
            incomplete_dir = output_dir / "run_0007"
            incomplete_dir.mkdir()
            with open(incomplete_dir / "session_test.jsonl", "w") as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")

            (output_dir / "other_file.txt").touch()  # Should be ignored

            completed = get_completed_runs(output_dir)

            assert completed == {1, 5, 10}

    def test_get_completed_runs_empty_dir(self):
        """Test get_completed_runs with empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = get_completed_runs(Path(tmpdir))

            assert completed == set()

    def test_get_completed_runs_nonexistent_dir(self):
        """Test get_completed_runs with nonexistent directory."""
        completed = get_completed_runs(Path("/nonexistent/dir"))

        assert completed == set()


class TestStatisticsCalculation:
    """Test bulk run statistics calculation."""

    def test_calculate_bulk_stats_all_successful(self):
        """Test statistics calculation with all successful runs."""
        results = [
            RunResult(
                run_id=1,
                config_path="config.json",
                output_path="out1.jsonl",
                success=True,
                duration_seconds=10.0,
                total_tokens=1000,
                total_rounds=5
            ),
            RunResult(
                run_id=2,
                config_path="config.json",
                output_path="out2.jsonl",
                success=True,
                duration_seconds=12.0,
                total_tokens=1200,
                total_rounds=6
            ),
            RunResult(
                run_id=3,
                config_path="config.json",
                output_path="out3.jsonl",
                success=True,
                duration_seconds=8.0,
                total_tokens=800,
                total_rounds=4
            )
        ]

        stats = calculate_bulk_stats(results)

        assert stats.total_runs == 3
        assert stats.successful_runs == 3
        assert stats.failed_runs == 0
        assert stats.total_duration_seconds == 30.0
        assert stats.avg_duration_seconds == 10.0
        assert stats.total_tokens == 3000
        assert stats.avg_tokens_per_run == 1000.0
        assert stats.runs_per_hour == pytest.approx(360.0, rel=0.01)  # 3 runs in 30s = 360/hr

    def test_calculate_bulk_stats_with_failures(self):
        """Test statistics calculation with some failures."""
        results = [
            RunResult(
                run_id=1,
                config_path="config.json",
                output_path="out1.jsonl",
                success=True,
                duration_seconds=10.0,
                total_tokens=1000,
                total_rounds=5
            ),
            RunResult(
                run_id=2,
                config_path="config.json",
                output_path="out2.jsonl",
                success=False,
                duration_seconds=5.0,
                error="Timeout"
            )
        ]

        stats = calculate_bulk_stats(results)

        assert stats.total_runs == 2
        assert stats.successful_runs == 1
        assert stats.failed_runs == 1
        assert stats.total_tokens == 1000  # Only successful run counted
        assert stats.avg_tokens_per_run == 1000.0

    def test_calculate_bulk_stats_empty_results(self):
        """Test statistics calculation with no results."""
        stats = calculate_bulk_stats([])

        assert stats.total_runs == 0
        assert stats.successful_runs == 0
        assert stats.failed_runs == 0
        assert stats.avg_duration_seconds == 0
        assert stats.avg_tokens_per_run == 0
        assert stats.runs_per_hour == 0

    def test_calculate_bulk_stats_missing_tokens(self):
        """Test statistics calculation when some runs have no token data."""
        results = [
            RunResult(
                run_id=1,
                config_path="config.json",
                output_path="out1.jsonl",
                success=True,
                duration_seconds=10.0,
                total_tokens=None,  # Missing token data
                total_rounds=5
            ),
            RunResult(
                run_id=2,
                config_path="config.json",
                output_path="out2.jsonl",
                success=True,
                duration_seconds=10.0,
                total_tokens=1000,
                total_rounds=5
            )
        ]

        stats = calculate_bulk_stats(results)

        # Should handle None gracefully
        assert stats.total_tokens == 1000
        assert stats.avg_tokens_per_run == 500.0  # Averaged across all successful runs (1000/2)


class TestRunResultDataclass:
    """Test RunResult dataclass."""

    def test_run_result_creation(self):
        """Test creating RunResult instance."""
        result = RunResult(
            run_id=1,
            config_path="test.json",
            output_path="out.jsonl",
            success=True,
            duration_seconds=15.5,
            total_tokens=2000,
            total_rounds=8
        )

        assert result.run_id == 1
        assert result.success is True
        assert result.error is None  # Default

    def test_run_result_with_error(self):
        """Test RunResult with error."""
        result = RunResult(
            run_id=2,
            config_path="test.json",
            output_path="out.jsonl",
            success=False,
            duration_seconds=5.0,
            error="Timeout after 1 hour"
        )

        assert result.success is False
        assert result.error == "Timeout after 1 hour"
        assert result.total_tokens is None  # Default


class TestBulkRunStatsDataclass:
    """Test BulkRunStats dataclass."""

    def test_bulk_run_stats_creation(self):
        """Test creating BulkRunStats instance."""
        stats = BulkRunStats(
            total_runs=100,
            successful_runs=95,
            failed_runs=5,
            skipped_runs=10,
            total_duration_seconds=3600.0,
            avg_duration_seconds=36.0,
            total_tokens=500000,
            avg_tokens_per_run=5000.0,
            runs_per_hour=100.0
        )

        assert stats.total_runs == 100
        assert stats.successful_runs == 95
        assert stats.failed_runs == 5
        assert stats.skipped_runs == 10


class TestSubprocessExecution:
    """Test run_single_session subprocess execution logic.

    These tests verify the "JSONL is authoritative" logic:
    - Session completion is determined by session_end event in JSONL
    - Exit codes can be unreliable (spurious errors)
    - Timeouts should still check for completed JSONL
    """

    @patch('scripts.bulk_session_runner.subprocess.run')
    def test_run_single_session_success(self, mock_subprocess):
        """Test successful session execution with exit code 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create config file
            config_path = output_dir / "test_config.json"
            with open(config_path, 'w') as f:
                json.dump({"session_name": "test", "max_turns": 1}, f)

            # Mock subprocess to return success
            mock_result = Mock()
            mock_result.returncode = 0
            mock_subprocess.return_value = mock_result

            # Create the run directory and JSONL file that the subprocess "would create"
            run_dir = output_dir / "run_0001"
            run_dir.mkdir()
            jsonl_path = run_dir / "session_test.jsonl"
            with open(jsonl_path, 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                f.write(json.dumps({"event_type": "llm_call", "tokens": {"total": 100}}) + "\n")
                f.write(json.dumps({"event_type": "session_end"}) + "\n")

            # Also create stderr/stdout logs that subprocess writes to
            (run_dir / "stderr.log").touch()
            (run_dir / "stdout.log").touch()

            result = run_single_session(
                config_path=str(config_path),
                run_id=1,
                output_dir=output_dir,
                proxy_url=None,
                log_level="INFO"
            )

            assert result.success is True
            assert result.run_id == 1
            assert result.error is None
            mock_subprocess.assert_called_once()

    @patch('scripts.bulk_session_runner.subprocess.run')
    def test_run_single_session_timeout(self, mock_subprocess):
        """Test session timeout handling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create config file
            config_path = output_dir / "test_config.json"
            with open(config_path, 'w') as f:
                json.dump({"session_name": "test", "max_turns": 1}, f)

            # Mock subprocess to raise timeout
            mock_subprocess.side_effect = subprocess.TimeoutExpired(
                cmd=["python", "test.py"],
                timeout=90000
            )

            # Create partial JSONL (no session_end - truly incomplete)
            run_dir = output_dir / "run_0001"
            run_dir.mkdir()
            jsonl_path = run_dir / "session_test.jsonl"
            with open(jsonl_path, 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")

            result = run_single_session(
                config_path=str(config_path),
                run_id=1,
                output_dir=output_dir,
                proxy_url=None,
                log_level="INFO"
            )

            assert result.success is False
            assert "timeout" in result.error.lower()

    @patch('scripts.bulk_session_runner.subprocess.run')
    def test_run_single_session_nonzero_exit_with_completed_jsonl(self, mock_subprocess):
        """Test that non-zero exit code is overridden if JSONL has session_end.

        This tests the "JSONL is authoritative" logic - spurious shutdown errors
        can cause non-zero exit codes even when the session completed successfully.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create config file
            config_path = output_dir / "test_config.json"
            with open(config_path, 'w') as f:
                json.dump({"session_name": "test", "max_turns": 1}, f)

            # Mock subprocess to return non-zero exit code (spurious error)
            mock_result = Mock()
            mock_result.returncode = 1  # Non-zero!
            mock_subprocess.return_value = mock_result

            # But JSONL has session_end (session actually completed)
            run_dir = output_dir / "run_0001"
            run_dir.mkdir()
            jsonl_path = run_dir / "session_test.jsonl"
            with open(jsonl_path, 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                f.write(json.dumps({"event_type": "session_end"}) + "\n")

            (run_dir / "stderr.log").write_text("Some spurious error")
            (run_dir / "stdout.log").touch()

            result = run_single_session(
                config_path=str(config_path),
                run_id=1,
                output_dir=output_dir,
                proxy_url=None,
                log_level="INFO"
            )

            # Should be SUCCESS because JSONL has session_end
            assert result.success is True
            assert result.error is None

    @patch('scripts.bulk_session_runner.subprocess.run')
    def test_run_single_session_exit_zero_incomplete_jsonl(self, mock_subprocess):
        """Test that exit code 0 but no session_end marks as incomplete.

        Edge case: process exits cleanly but session didn't complete.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create config file
            config_path = output_dir / "test_config.json"
            with open(config_path, 'w') as f:
                json.dump({"session_name": "test", "max_turns": 1}, f)

            # Mock subprocess to return exit 0
            mock_result = Mock()
            mock_result.returncode = 0
            mock_subprocess.return_value = mock_result

            # But JSONL is incomplete (no session_end)
            run_dir = output_dir / "run_0001"
            run_dir.mkdir()
            jsonl_path = run_dir / "session_test.jsonl"
            with open(jsonl_path, 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                # No session_end!

            (run_dir / "stderr.log").touch()
            (run_dir / "stdout.log").touch()

            result = run_single_session(
                config_path=str(config_path),
                run_id=1,
                output_dir=output_dir,
                proxy_url=None,
                log_level="INFO"
            )

            # Should be FAILURE because no session_end
            assert result.success is False
            assert "incomplete" in result.error.lower()


class TestResumeLogic:
    """Test resume capability - metadata loading and fallback discovery."""

    def test_resume_with_metadata_json(self):
        """Test that resume loads config paths from metadata.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Write metadata.json
            metadata = {
                'config_paths': ['/path/to/config1.json', '/path/to/config2.json'],
                'runs_per_config': 5,
                'total_runs': 10,
                'workers': 4,
                'proxy_url': None,
                'log_level': 'INFO',
                'created_at': '2025-01-01 12:00:00'
            }
            with open(output_dir / 'metadata.json', 'w') as f:
                json.dump(metadata, f)

            loaded = load_bulk_run_metadata(output_dir)

            assert loaded is not None
            assert loaded['config_paths'] == ['/path/to/config1.json', '/path/to/config2.json']
            assert loaded['runs_per_config'] == 5
            assert loaded['total_runs'] == 10

    def test_resume_without_metadata_fallback(self):
        """Test fallback discovery from run_* directories when metadata missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create run directories with configs
            for run_id in [1, 2, 3]:
                run_dir = output_dir / f"run_{run_id:04d}"
                run_dir.mkdir()

                # Write stored config
                config = {"session_name": f"test_run_{run_id}"}
                with open(run_dir / "config.json", 'w') as f:
                    json.dump(config, f)

                # Run 1 and 2 completed, run 3 incomplete
                with open(run_dir / "session_test.jsonl", 'w') as f:
                    f.write(json.dumps({"event_type": "session_start"}) + "\n")
                    if run_id != 3:  # Only 1 and 2 have session_end
                        f.write(json.dumps({"event_type": "session_end"}) + "\n")

            total_runs, incomplete_runs = discover_run_metadata_from_dirs(output_dir)

            assert total_runs == 3
            assert len(incomplete_runs) == 1  # Only run 3 is incomplete
            assert incomplete_runs[0][1] == 3  # run_id of incomplete run

    def test_resume_skips_completed_runs(self):
        """Test that get_completed_runs correctly identifies completed sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create completed run (has session_end)
            completed_dir = output_dir / "run_0001"
            completed_dir.mkdir()
            with open(completed_dir / "session_test.jsonl", 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                f.write(json.dumps({"event_type": "session_end"}) + "\n")

            # Create incomplete run (no session_end)
            incomplete_dir = output_dir / "run_0002"
            incomplete_dir.mkdir()
            with open(incomplete_dir / "session_test.jsonl", 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")

            # Create run with no JSONL (just started)
            empty_dir = output_dir / "run_0003"
            empty_dir.mkdir()

            completed = get_completed_runs(output_dir)

            assert completed == {1}  # Only run 1 is complete


class TestReplayResumeFunctions:
    """Test replay-based resume helper functions."""

    def test_get_last_successful_round_with_completed_rounds(self):
        """Test finding last successful round from JSONL with round_end events."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            # Session with rounds 0, 1, 2 completed, round 3 started but not finished
            f.write(json.dumps({"event_type": "session_start"}) + "\n")
            f.write(json.dumps({"event_type": "round_start", "round": 0}) + "\n")
            f.write(json.dumps({"event_type": "round_end", "round": 0}) + "\n")
            f.write(json.dumps({"event_type": "round_start", "round": 1}) + "\n")
            f.write(json.dumps({"event_type": "round_end", "round": 1}) + "\n")
            f.write(json.dumps({"event_type": "round_start", "round": 2}) + "\n")
            f.write(json.dumps({"event_type": "round_end", "round": 2}) + "\n")
            f.write(json.dumps({"event_type": "round_start", "round": 3}) + "\n")
            # No round_end for round 3 - session failed here
            temp_path = Path(f.name)

        try:
            last_round = get_last_successful_round(temp_path)
            assert last_round == 2
        finally:
            temp_path.unlink()

    def test_get_last_successful_round_no_completed_rounds(self):
        """Test when no rounds completed (failed in round 0)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write(json.dumps({"event_type": "session_start"}) + "\n")
            f.write(json.dumps({"event_type": "round_start", "round": 0}) + "\n")
            # No round_end at all
            temp_path = Path(f.name)

        try:
            last_round = get_last_successful_round(temp_path)
            assert last_round is None
        finally:
            temp_path.unlink()

    def test_get_last_successful_round_nonexistent_file(self):
        """Test handling of nonexistent file."""
        last_round = get_last_successful_round(Path("/nonexistent/file.jsonl"))
        assert last_round is None

    def test_get_last_successful_round_empty_file(self):
        """Test handling of empty file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            temp_path = Path(f.name)

        try:
            last_round = get_last_successful_round(temp_path)
            assert last_round is None
        finally:
            temp_path.unlink()

    def test_count_llm_calls_in_jsonl(self):
        """Test counting LLM calls in JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write(json.dumps({"event_type": "session_start"}) + "\n")
            f.write(json.dumps({"event_type": "llm_call", "agent_id": "dm_01"}) + "\n")
            f.write(json.dumps({"event_type": "llm_call", "agent_id": "player_1"}) + "\n")
            f.write(json.dumps({"event_type": "round_start", "round": 1}) + "\n")
            f.write(json.dumps({"event_type": "llm_call", "agent_id": "dm_01"}) + "\n")
            f.write(json.dumps({"event_type": "action_declaration"}) + "\n")
            temp_path = Path(f.name)

        try:
            count = count_llm_calls_in_jsonl(temp_path)
            assert count == 3
        finally:
            temp_path.unlink()

    def test_count_llm_calls_no_calls(self):
        """Test counting when no LLM calls present."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write(json.dumps({"event_type": "session_start"}) + "\n")
            f.write(json.dumps({"event_type": "round_start"}) + "\n")
            temp_path = Path(f.name)

        try:
            count = count_llm_calls_in_jsonl(temp_path)
            assert count == 0
        finally:
            temp_path.unlink()

    def test_count_llm_calls_nonexistent_file(self):
        """Test counting with nonexistent file."""
        count = count_llm_calls_in_jsonl(Path("/nonexistent/file.jsonl"))
        assert count == 0


class TestTryReplaySession:
    """Test try_replay_session subprocess call logic."""

    @patch('scripts.bulk_session_runner.subprocess.run')
    @patch('scripts.bulk_session_runner.check_session_completed')
    def test_try_replay_success(self, mock_check_completed, mock_subprocess):
        """Test successful replay execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create partial JSONL with enough LLM calls
            partial_jsonl = tmpdir / "session_partial.jsonl"
            with open(partial_jsonl, 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                f.write(json.dumps({"event_type": "llm_call", "agent_id": "dm"}) + "\n")
                f.write(json.dumps({"event_type": "llm_call", "agent_id": "player_1"}) + "\n")
                f.write(json.dumps({"event_type": "llm_call", "agent_id": "player_2"}) + "\n")
                f.write(json.dumps({"event_type": "llm_call", "agent_id": "dm"}) + "\n")

            output_path = tmpdir / "session_replay.jsonl"

            # Mock subprocess success
            mock_result = Mock()
            mock_result.returncode = 0
            mock_subprocess.return_value = mock_result

            # Mock output file created and completed
            mock_check_completed.return_value = True
            output_path.touch()  # Create empty file for exists() check

            success, error = try_replay_session(
                partial_jsonl=partial_jsonl,
                output_path=output_path,
                continue_from_round=2,
                timeout=100
            )

            assert success is True
            assert error is None

            # Verify subprocess was called with correct args
            mock_subprocess.assert_called_once()
            call_args = mock_subprocess.call_args[0][0]
            assert "replay_fixture.py" in call_args[1]
            assert "--all-cached" in call_args
            assert "--cache-until-round" in call_args
            assert "2" in call_args

    @patch('scripts.bulk_session_runner.subprocess.run')
    def test_try_replay_insufficient_llm_calls(self, mock_subprocess):
        """Test replay fails early if not enough LLM calls cached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create partial JSONL with too few LLM calls
            partial_jsonl = tmpdir / "session_partial.jsonl"
            with open(partial_jsonl, 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                f.write(json.dumps({"event_type": "llm_call", "agent_id": "dm"}) + "\n")
                # Only 1 LLM call - below threshold of 3

            output_path = tmpdir / "session_replay.jsonl"

            success, error = try_replay_session(
                partial_jsonl=partial_jsonl,
                output_path=output_path,
                continue_from_round=0,
                timeout=100
            )

            assert success is False
            assert "Insufficient LLM calls" in error
            # Subprocess should NOT have been called
            mock_subprocess.assert_not_called()

    @patch('scripts.bulk_session_runner.subprocess.run')
    def test_try_replay_subprocess_failure(self, mock_subprocess):
        """Test handling of subprocess failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create partial JSONL with enough LLM calls
            partial_jsonl = tmpdir / "session_partial.jsonl"
            with open(partial_jsonl, 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                for i in range(5):
                    f.write(json.dumps({"event_type": "llm_call", "agent_id": f"agent_{i}"}) + "\n")

            output_path = tmpdir / "session_replay.jsonl"

            # Mock subprocess failure
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stderr = "Some error occurred"
            mock_subprocess.return_value = mock_result

            success, error = try_replay_session(
                partial_jsonl=partial_jsonl,
                output_path=output_path,
                continue_from_round=2,
                timeout=100
            )

            assert success is False
            assert "Replay failed" in error

    @patch('scripts.bulk_session_runner.subprocess.run')
    def test_try_replay_timeout(self, mock_subprocess):
        """Test handling of subprocess timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create partial JSONL with enough LLM calls
            partial_jsonl = tmpdir / "session_partial.jsonl"
            with open(partial_jsonl, 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                for i in range(5):
                    f.write(json.dumps({"event_type": "llm_call", "agent_id": f"agent_{i}"}) + "\n")

            output_path = tmpdir / "session_replay.jsonl"

            # Mock subprocess timeout
            mock_subprocess.side_effect = subprocess.TimeoutExpired(
                cmd=["python", "replay.py"],
                timeout=100
            )

            success, error = try_replay_session(
                partial_jsonl=partial_jsonl,
                output_path=output_path,
                continue_from_round=2,
                timeout=100
            )

            assert success is False
            assert "timeout" in error.lower()


class TestRunSingleSessionWithReplay:
    """Test run_single_session with attempt_replay=True."""

    @patch('scripts.bulk_session_runner.try_replay_session')
    @patch('scripts.bulk_session_runner.subprocess.run')
    def test_replay_success_skips_restart(self, mock_subprocess, mock_try_replay):
        """Test that successful replay returns immediately without restart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create config file
            config_path = output_dir / "test_config.json"
            with open(config_path, 'w') as f:
                json.dump({"session_name": "test", "max_turns": 5}, f)

            # Create partial session that failed at round 3
            run_dir = output_dir / "run_0001"
            run_dir.mkdir()
            partial_jsonl = run_dir / "session_test.jsonl"
            with open(partial_jsonl, 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                f.write(json.dumps({"event_type": "round_end", "round": 0}) + "\n")
                f.write(json.dumps({"event_type": "round_end", "round": 1}) + "\n")
                f.write(json.dumps({"event_type": "round_end", "round": 2}) + "\n")
                # Round 3 started but didn't complete
                for i in range(5):
                    f.write(json.dumps({"event_type": "llm_call", "agent_id": f"agent_{i}"}) + "\n")

            # Mock successful replay
            replay_output = run_dir / "session_replay_0001.jsonl"
            with open(replay_output, 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                f.write(json.dumps({"event_type": "session_end"}) + "\n")
            mock_try_replay.return_value = (True, None)

            result = run_single_session(
                config_path=str(config_path),
                run_id=1,
                output_dir=output_dir,
                attempt_replay=True
            )

            assert result.success is True
            # subprocess.run should NOT be called - replay succeeded
            mock_subprocess.assert_not_called()
            # try_replay_session should have been called
            mock_try_replay.assert_called_once()

    @patch('scripts.bulk_session_runner.try_replay_session')
    @patch('scripts.bulk_session_runner.get_last_successful_round')
    @patch('scripts.bulk_session_runner.subprocess.run')
    def test_replay_failure_falls_back_to_restart(self, mock_subprocess, mock_get_last_round, mock_try_replay):
        """Test that failed replay falls back to fresh restart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create config file
            config_path = output_dir / "test_config.json"
            with open(config_path, 'w') as f:
                json.dump({"session_name": "test", "max_turns": 5}, f)

            # Create partial session that failed at round 3
            run_dir = output_dir / "run_0001"
            run_dir.mkdir()
            partial_jsonl = run_dir / "session_test.jsonl"
            with open(partial_jsonl, 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                f.write(json.dumps({"event_type": "round_end", "round": 0}) + "\n")
                f.write(json.dumps({"event_type": "round_end", "round": 1}) + "\n")
                f.write(json.dumps({"event_type": "round_end", "round": 2}) + "\n")
                # Round 3 started but didn't complete
                for i in range(5):
                    f.write(json.dumps({"event_type": "llm_call", "agent_id": f"agent_{i}"}) + "\n")

            # Mock get_last_successful_round to return 2 (rounds 0-2 completed)
            mock_get_last_round.return_value = 2

            # Mock failed replay
            mock_try_replay.return_value = (False, "Cache mismatch")

            # Mock successful restart
            mock_result = Mock()
            mock_result.returncode = 0
            mock_subprocess.return_value = mock_result

            # Create files that subprocess "would create"
            with open(run_dir / "session_fresh.jsonl", 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                f.write(json.dumps({"event_type": "session_end"}) + "\n")
            (run_dir / "stderr.log").touch()
            (run_dir / "stdout.log").touch()

            result = run_single_session(
                config_path=str(config_path),
                run_id=1,
                output_dir=output_dir,
                attempt_replay=True
            )

            # Both replay and subprocess should have been called
            mock_try_replay.assert_called_once()
            mock_subprocess.assert_called_once()
            # Final result should be success (from restart)
            assert result.success is True

    @patch('scripts.bulk_session_runner.subprocess.run')
    def test_no_replay_when_no_completed_rounds(self, mock_subprocess):
        """Test that replay is skipped when session has no completed rounds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create config file
            config_path = output_dir / "test_config.json"
            with open(config_path, 'w') as f:
                json.dump({"session_name": "test", "max_turns": 5}, f)

            # Create partial session with NO completed rounds
            run_dir = output_dir / "run_0001"
            run_dir.mkdir()
            partial_jsonl = run_dir / "session_test.jsonl"
            with open(partial_jsonl, 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                f.write(json.dumps({"event_type": "round_start", "round": 0}) + "\n")
                # No round_end - failed in round 0

            # Mock subprocess for restart
            mock_result = Mock()
            mock_result.returncode = 0
            mock_subprocess.return_value = mock_result

            with open(run_dir / "session_fresh.jsonl", 'w') as f:
                f.write(json.dumps({"event_type": "session_start"}) + "\n")
                f.write(json.dumps({"event_type": "session_end"}) + "\n")
            (run_dir / "stderr.log").touch()
            (run_dir / "stdout.log").touch()

            result = run_single_session(
                config_path=str(config_path),
                run_id=1,
                output_dir=output_dir,
                attempt_replay=True
            )

            # Should go straight to restart (no replay attempted)
            mock_subprocess.assert_called_once()
            assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
