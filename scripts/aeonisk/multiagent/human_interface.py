"""
Human interface for taking control of agents in the multi-agent system.
"""

import asyncio
import select
import sys
import threading
from typing import Dict, Any, Optional
from .base import MessageBus, MessageType, Message
from datetime import datetime
import uuid


class HumanInterface:
    """
    Text-based interface for humans to take control of any agent
    in the multi-agent system.
    """
    
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.message_bus = None
        self.running = False
        self._stop_event = threading.Event()
        self._command_thread: Optional[threading.Thread] = None
        self.available_agents: Dict[str, str] = {}  # agent_id -> agent_type
        self.controlled_agent: Optional[str] = None
        self.agent = None
        
    async def start(self):
        """Start the human interface."""
        # Connect to message bus as special human interface agent
        from .base import Agent
        
        class HumanInterfaceAgent(Agent):
            def __init__(self, interface):
                super().__init__("human_interface", interface.socket_path)
                self.interface = interface
                
            async def on_start(self):
                pass
                
            async def on_shutdown(self):
                pass
                
        self.agent = HumanInterfaceAgent(self)
        await self.agent.start()
        
        # Set up message handlers to track available agents
        self.agent.message_handlers[MessageType.AGENT_REGISTER] = self._handle_agent_register
        self.agent.message_handlers[MessageType.AGENT_READY] = self._handle_agent_ready
        
        self.running = True
        self._stop_event.clear()

        # Start command line interface in separate thread
        self._command_thread = threading.Thread(target=self._command_loop, daemon=True)
        self._command_thread.start()
        
        print("\n=== Aeonisk Multi-Agent Human Interface ===")
        print("Type 'help' for available commands")
        print("Type 'agents' to see available agents")
        print("Type 'control <agent_name>' to take control of an agent")
        
    async def _handle_agent_register(self, message):
        """Track agent registrations."""
        agent_id = message.sender
        agent_type = message.payload.get('agent_type', 'unknown')
        self.available_agents[agent_id] = agent_type

    async def _handle_agent_ready(self, message):
        """Track when agents are ready."""
        agent_id = message.sender
        agent_type = message.payload.get('agent_type', 'unknown')
        self.available_agents[agent_id] = agent_type

        if message.payload.get('character'):
            char_name = message.payload['character']['name']
            print(f"\n[System] {char_name} ({agent_type}) is ready")
            
    def _read_line_with_timeout(self, fd: int, timeout: float) -> Optional[str]:
        """
        Read a line from file descriptor with timeout.

        Uses select() to poll stdin, allowing periodic checks of shutdown event.

        Args:
            fd: File descriptor to read from (usually sys.stdin.fileno())
            timeout: Timeout in seconds

        Returns:
            str: The line read (without trailing newline)
            None: If timeout occurred (no input available)

        Raises:
            EOFError: If stdin is closed/EOF
        """
        # Use select to wait for input with timeout
        readable, _, _ = select.select([fd], [], [], timeout)

        if readable:
            # Input is available, read a line
            line = sys.stdin.readline()
            if not line:
                # Empty string from readline means EOF
                raise EOFError("stdin closed")
            return line.rstrip('\n')

        # Timeout - no input available
        return None

    def _command_loop(self):
        """Main command loop for human interface with non-blocking input."""
        stdin_fd = sys.stdin.fileno()

        while self.running and not self._stop_event.is_set():
            try:
                if self.controlled_agent:
                    prompt = f"[Controlling {self.controlled_agent}]> "
                else:
                    prompt = "[Observer]> "

                # Print prompt without newline, flush immediately
                print(prompt, end='', flush=True)

                # Non-blocking read with timeout using select()
                command = self._read_line_with_timeout(stdin_fd, timeout=0.5)

                if command is None:
                    # Timeout - check stop event and continue
                    if self.running and not self._stop_event.is_set():
                        # Clear the prompt line before re-printing
                        print('\r' + ' ' * len(prompt) + '\r', end='', flush=True)
                    continue

                command = command.strip()

                if not command:
                    continue

                self._handle_command(command)

            except KeyboardInterrupt:
                print("\nShutting down...")
                self.running = False
                self._stop_event.set()
                break
            except EOFError:
                # Piped input exhausted or stdin closed
                break
            except Exception as e:
                print(f"Error: {e}")
                
    def _handle_command(self, command: str):
        """Handle user commands."""
        parts = command.split(' ', 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        if cmd == 'help':
            self._show_help()
        elif cmd == 'agents':
            self._show_agents()
        elif cmd == 'control':
            self._control_agent(args)
        elif cmd == 'release':
            self._release_control()
        elif cmd == 'status':
            self._show_status()
        elif cmd == 'say' and self.controlled_agent:
            self._say_as_agent(args)
        elif cmd == 'quit' or cmd == 'exit':
            self.running = False
        elif self.controlled_agent:
            # Pass command directly to controlled agent
            self._send_agent_command(command)
        else:
            print("Unknown command. Type 'help' for available commands.")
            
    def _show_help(self):
        """Show help information."""
        print("""
Available Commands:
  help              - Show this help
  agents            - List available agents
  control <agent>   - Take control of an agent
  release           - Release control of current agent
  status            - Show current status
  say <message>     - Speak as controlled agent
  quit/exit         - Exit interface

When controlling an agent:
  - Type actions directly (e.g., "explore the room")
  - Use 'status' to see character info
  - Use 'release' to return to AI control
        """)
        
    def _show_agents(self):
        """Show available agents."""
        if not self.available_agents:
            print("No agents available.")
            return
            
        print("\nAvailable Agents:")
        for agent_id, agent_type in self.available_agents.items():
            status = " [CONTROLLED]" if agent_id == self.controlled_agent else ""
            print(f"  {agent_id} ({agent_type}){status}")
            
    def _control_agent(self, agent_name: str):
        """Take control of an agent."""
        if not agent_name:
            print("Please specify agent name. Use 'agents' to see available agents.")
            return
            
        # Find agent by partial name match
        matches = [aid for aid in self.available_agents.keys() if agent_name.lower() in aid.lower()]
        
        if not matches:
            print(f"Agent '{agent_name}' not found.")
            return
        elif len(matches) > 1:
            print(f"Multiple matches: {', '.join(matches)}")
            return
            
        agent_id = matches[0]
        
        # Send control message to agent
        message = Message(
            id=str(uuid.uuid4()),
            type=MessageType.PING,  # Using ping for simplicity
            sender="human_interface",
            recipient=agent_id,
            payload={'command': 'take_control'},
            timestamp=datetime.now()
        )
        
        asyncio.create_task(self.agent._send_message(message))
        
        self.controlled_agent = agent_id
        print(f"You now control {agent_id}")
        print("Type commands as this agent, or 'release' to return to AI control")
        
    def _release_control(self):
        """Release control of current agent."""
        if not self.controlled_agent:
            print("You are not controlling any agent.")
            return
            
        # Send release message to agent
        message = Message(
            id=str(uuid.uuid4()),
            type=MessageType.PING,
            sender="human_interface", 
            recipient=self.controlled_agent,
            payload={'command': 'release_control'},
            timestamp=datetime.now()
        )
        
        asyncio.create_task(self.agent._send_message(message))
        
        print(f"Released control of {self.controlled_agent}")
        self.controlled_agent = None
        
    def _show_status(self):
        """Show current status."""
        if self.controlled_agent:
            print(f"Currently controlling: {self.controlled_agent}")
        else:
            print("Not controlling any agent (Observer mode)")
        print(f"Available agents: {len(self.available_agents)}")
        
    def _say_as_agent(self, message: str):
        """Speak as the controlled agent."""
        if not self.controlled_agent or not message:
            return
            
        # Send chat message
        chat_message = Message(
            id=str(uuid.uuid4()),
            type=MessageType.PLAYER_RESPONSE,
            sender=self.controlled_agent,
            recipient=None,  # broadcast
            payload={'message': message, 'type': 'chat'},
            timestamp=datetime.now()
        )
        
        asyncio.create_task(self.agent._send_message(chat_message))
        print(f"[{self.controlled_agent}] {message}")
        
    def _send_agent_command(self, command: str):
        """Send command to controlled agent."""
        if not self.controlled_agent:
            return
            
        # Send as turn request for now
        message = Message(
            id=str(uuid.uuid4()),
            type=MessageType.TURN_REQUEST,
            sender="human_interface",
            recipient=self.controlled_agent,
            payload={'human_command': command},
            timestamp=datetime.now()
        )
        
        asyncio.create_task(self.agent._send_message(message))
        
    def shutdown(self):
        """Shutdown the interface."""
        self.running = False
        self._stop_event.set()

        # Wait for command thread to notice shutdown (with timeout)
        if self._command_thread and self._command_thread.is_alive():
            self._command_thread.join(timeout=1.0)
            # If thread didn't exit cleanly, daemon=True ensures it won't block Python exit

        if self.agent:
            self.agent.shutdown()