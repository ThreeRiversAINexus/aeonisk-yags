"""
Agent Prompt Logger - Human-Readable LLM Prompt/Response Logging

Creates per-agent log files showing full LLM prompts (input) and responses (output)
for debugging agent context visibility issues.

Usage:
    logger = AgentPromptLogger(output_dir="agent_prompts")
    logger.log_llm_call(
        agent_id="player_01",
        round_num=1,
        call_sequence=0,
        prompt="<full prompt text>",
        response="<full response text>",
        model="claude-sonnet-4-5",
        temperature=0.8,
        tokens={"input": 1234, "output": 567}
    )
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any
from threading import Lock

logger = logging.getLogger(__name__)


class AgentPromptLogger:
    """
    Manages per-agent human-readable log files for LLM prompt/response debugging.

    Creates files like: agent_prompts/player_01.log, agent_prompts/dm.log
    Each file contains timestamped entries showing full prompts and responses.
    """

    def __init__(self, output_dir: str = "agent_prompts", session_id: Optional[str] = None):
        """
        Initialize agent prompt logger.

        Args:
            output_dir: Directory for agent log files (created if doesn't exist)
            session_id: Optional session ID to include in file names
        """
        self.output_dir = Path(output_dir)
        self.session_id = session_id
        self.file_handles: Dict[str, Any] = {}  # agent_id -> file handle
        self.call_counts: Dict[str, int] = {}  # agent_id -> call count
        self.lock = Lock()  # Thread safety for file operations

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"AgentPromptLogger initialized: {self.output_dir}")

    def _get_file_path(self, agent_id: str) -> Path:
        """Get log file path for an agent."""
        if self.session_id:
            filename = f"{agent_id}_{self.session_id}.log"
        else:
            filename = f"{agent_id}.log"
        return self.output_dir / filename

    def _get_file_handle(self, agent_id: str):
        """Get or create file handle for an agent (lazy open)."""
        if agent_id not in self.file_handles:
            file_path = self._get_file_path(agent_id)
            self.file_handles[agent_id] = open(file_path, 'w', encoding='utf-8')
            self.call_counts[agent_id] = 0

            # Write header
            self.file_handles[agent_id].write(f"{'='*80}\n")
            self.file_handles[agent_id].write(f"Agent Prompt Log: {agent_id}\n")
            if self.session_id:
                self.file_handles[agent_id].write(f"Session: {self.session_id}\n")
            self.file_handles[agent_id].write(f"Created: {datetime.now().isoformat()}\n")
            self.file_handles[agent_id].write(f"{'='*80}\n\n")
            self.file_handles[agent_id].flush()

            logger.debug(f"Opened log file for {agent_id}: {file_path}")

        return self.file_handles[agent_id]

    def log_llm_call(
        self,
        agent_id: str,
        round_num: Optional[int],
        call_sequence: int,
        prompt: str,
        response: str,
        model: str = "unknown",
        temperature: Optional[float] = None,
        tokens: Optional[Dict[str, int]] = None,
        duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log an LLM call for an agent.

        Args:
            agent_id: Unique agent identifier (player_01, dm, etc.)
            round_num: Current round number (None for pre-game)
            call_sequence: Sequential call number for this agent
            prompt: Full prompt text sent to LLM
            response: Full response text from LLM
            model: Model name
            temperature: Temperature setting
            tokens: Dict with 'input' and 'output' token counts
            duration_seconds: Request duration
            metadata: Additional metadata dict
        """
        with self.lock:
            try:
                fh = self._get_file_handle(agent_id)
                self.call_counts[agent_id] += 1

                # Build entry
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                round_str = f"Round {round_num}" if round_num is not None else "Pre-game"

                fh.write(f"{'='*80}\n")
                fh.write(f"[{timestamp}] {round_str} - LLM Call #{self.call_counts[agent_id]}\n")
                fh.write(f"{'='*80}\n\n")

                # Prompt section
                fh.write(f"--- PROMPT (sent to {model}) ---\n")
                fh.write(prompt)
                if not prompt.endswith('\n'):
                    fh.write('\n')
                fh.write('\n')

                # Response section
                fh.write(f"--- RESPONSE ---\n")
                fh.write(response)
                if not response.endswith('\n'):
                    fh.write('\n')
                fh.write('\n')

                # Metadata section
                fh.write(f"--- METADATA ---\n")
                if tokens:
                    fh.write(f"Tokens: {tokens.get('input', '?')} input / {tokens.get('output', '?')} output\n")
                if temperature is not None:
                    fh.write(f"Temperature: {temperature}\n")
                if duration_seconds is not None:
                    fh.write(f"Duration: {duration_seconds:.2f}s\n")
                if metadata:
                    for key, value in metadata.items():
                        fh.write(f"{key}: {value}\n")

                fh.write(f"\n{'='*80}\n\n")
                fh.flush()

            except Exception as e:
                logger.error(f"Failed to log LLM call for {agent_id}: {e}", exc_info=True)

    def close_all(self):
        """Close all open file handles."""
        with self.lock:
            for agent_id, fh in self.file_handles.items():
                try:
                    fh.write(f"\n{'='*80}\n")
                    fh.write(f"Log closed: {datetime.now().isoformat()}\n")
                    fh.write(f"Total calls: {self.call_counts.get(agent_id, 0)}\n")
                    fh.write(f"{'='*80}\n")
                    fh.close()
                    logger.debug(f"Closed log file for {agent_id}")
                except Exception as e:
                    logger.error(f"Error closing log file for {agent_id}: {e}")

            self.file_handles.clear()
            self.call_counts.clear()

    def __del__(self):
        """Cleanup: close all files on deletion."""
        self.close_all()
