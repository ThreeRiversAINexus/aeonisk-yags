"""
Base classes and infrastructure for multi-agent system.
"""

import asyncio
import json
import logging
import socket
import tempfile
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import os

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages in the system."""
    # System messages
    AGENT_REGISTER = "agent_register"
    AGENT_READY = "agent_ready"
    SESSION_START = "session_start"
    SESSION_END = "session_end"

    # Game flow messages
    SCENARIO_SETUP = "scenario_setup"
    SCENARIO_UPDATE = "scenario_update"  # For mid-game scenario pivots
    TURN_REQUEST = "turn_request"
    ACTION_DECLARED = "action_declared"
    ACTION_RESOLVED = "action_resolved"
    
    # State sync messages
    GAME_STATE_UPDATE = "game_state_update"
    CHARACTER_UPDATE = "character_update"
    
    # AI interactions
    DM_NARRATION = "dm_narration"
    NPC_DIALOGUE = "npc_dialogue"
    PLAYER_RESPONSE = "player_response"
    
    # System control
    PING = "ping"
    PONG = "pong"
    SHUTDOWN = "shutdown"


@dataclass
class Message:
    """Base message structure for IPC communication."""
    id: str
    type: MessageType
    sender: str
    recipient: Optional[str]  # None for broadcast
    payload: Dict[str, Any]
    timestamp: datetime
    
    def to_json(self) -> str:
        """Serialize message to JSON with newline delimiter."""
        data = asdict(self)
        data['type'] = self.type.value
        data['timestamp'] = self.timestamp.isoformat()
        return json.dumps(data) + '\n'
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        """Deserialize message from JSON."""
        data = json.loads(json_str)
        data['type'] = MessageType(data['type'])
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class MessageBus:
    """
    IPC message bus using Unix Domain Sockets for inter-process communication.
    """
    
    def __init__(self, socket_path: Optional[str] = None):
        if socket_path is None:
            # Create temp socket file
            temp_dir = Path(tempfile.gettempdir())
            self.socket_path = temp_dir / f"aeonisk_multiagent_{uuid.uuid4().hex[:8]}.sock"
        else:
            self.socket_path = Path(socket_path)
        
        self.server_socket: Optional[socket.socket] = None
        self.clients: Dict[str, socket.socket] = {}
        self.message_handlers: Dict[str, Callable[[Message], None]] = {}
        self.running = False
        
    async def start_server(self):
        """Start the message bus server."""
        # Clean up any existing socket
        if self.socket_path.exists():
            self.socket_path.unlink()
            
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(str(self.socket_path))
        self.server_socket.listen(10)
        self.server_socket.setblocking(False)
        
        self.running = True
        logger.info(f"Message bus started on {self.socket_path}")
        
        # Start accepting connections
        asyncio.create_task(self._accept_connections())
        
    async def _accept_connections(self):
        """Accept new client connections."""
        while self.running:
            try:
                client_socket, _ = await asyncio.get_event_loop().sock_accept(self.server_socket)
                client_socket.setblocking(False)
                
                # Start handling this client
                asyncio.create_task(self._handle_client(client_socket))
                
            except Exception as e:
                logger.error(f"Error accepting connection: {e}")
                await asyncio.sleep(0.1)
                
    async def _handle_client(self, client_socket: socket.socket):
        """Handle messages from a client connection."""
        client_id = None
        buffer = ""

        try:
            while self.running:
                data = await asyncio.get_event_loop().sock_recv(client_socket, 4096)
                if not data:
                    break

                buffer += data.decode()

                # Process all complete messages (delimited by newlines)
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)

                    if not line.strip():
                        continue

                    try:
                        message = Message.from_json(line)

                        # Register client on first message
                        if client_id is None:
                            client_id = message.sender
                            self.clients[client_id] = client_socket
                            logger.info(f"Client {client_id} connected")

                        # Route message
                        await self._route_message(message)

                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON received: {line[:100]!r} - {e}")
                    except Exception as e:
                        logger.error(f"Error processing message: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"Client connection error: {e}")
        finally:
            if client_id and client_id in self.clients:
                del self.clients[client_id]
                logger.info(f"Client {client_id} disconnected")
            client_socket.close()
            
    async def _route_message(self, message: Message):
        """Route message to appropriate recipients."""
        if message.recipient:
            # Direct message to specific agent
            if message.recipient in self.clients:
                await self._send_to_client(self.clients[message.recipient], message)
            else:
                logger.warning(f"Recipient {message.recipient} not found in clients: {list(self.clients.keys())}")
        else:
            # Broadcast to all clients (don't exclude sender if sender is not a client)
            for client_id, client_socket in self.clients.items():
                # Only exclude sender if sender is actually a client
                if message.sender not in self.clients or client_id != message.sender:
                    await self._send_to_client(client_socket, message)

        # Invoke local handlers
        for handler in self.message_handlers.values():
            try:
                handler(message)
            except Exception as e:
                logger.error(f"Message handler error: {e}")
                
    async def _send_to_client(self, client_socket: socket.socket, message: Message):
        """Send message to a specific client."""
        try:
            await asyncio.get_event_loop().sock_sendall(
                client_socket, 
                message.to_json().encode()
            )
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            
    def add_handler(self, handler_id: str, handler: Callable[[Message], None]):
        """Add a message handler."""
        self.message_handlers[handler_id] = handler
        
    def remove_handler(self, handler_id: str):
        """Remove a message handler."""
        if handler_id in self.message_handlers:
            del self.message_handlers[handler_id]
            
    def shutdown(self):
        """Shutdown the message bus."""
        self.running = False
        
        for client_socket in self.clients.values():
            client_socket.close()
        self.clients.clear()
        
        if self.server_socket:
            self.server_socket.close()
            
        if self.socket_path.exists():
            self.socket_path.unlink()
            
        logger.info("Message bus shutdown")


class Agent(ABC):
    """
    Base class for all agents in the multi-agent system.
    """
    
    def __init__(self, agent_id: str, socket_path: str):
        self.agent_id = agent_id
        self.socket_path = socket_path
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.message_handlers: Dict[MessageType, Callable[[Message], None]] = {}
        
        # Set up default handlers
        self._setup_default_handlers()
        
    def _setup_default_handlers(self):
        """Set up default message handlers."""
        self.message_handlers[MessageType.PING] = self._handle_ping
        self.message_handlers[MessageType.SHUTDOWN] = self._handle_shutdown
        
    async def start(self):
        """Start the agent."""
        await self._connect_to_message_bus()
        await self._register()
        self.running = True
        
        # Start message handling loop
        asyncio.create_task(self._message_loop())
        
        # Agent-specific startup
        await self.on_start()
        
    async def _connect_to_message_bus(self):
        """Connect to the message bus."""
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        await asyncio.get_event_loop().sock_connect(self.socket, self.socket_path)
        self.socket.setblocking(False)
        logger.info(f"Agent {self.agent_id} connected to message bus")
        
    async def _register(self):
        """Register with the message bus."""
        message = Message(
            id=str(uuid.uuid4()),
            type=MessageType.AGENT_REGISTER,
            sender=self.agent_id,
            recipient=None,
            payload={'agent_type': self.__class__.__name__},
            timestamp=datetime.now()
        )
        await self._send_message(message)
        
    async def _message_loop(self):
        """Main message handling loop."""
        buffer = ""
        while self.running:
            try:
                data = await asyncio.get_event_loop().sock_recv(self.socket, 4096)
                if not data:
                    break

                buffer += data.decode()

                # Process all complete messages (delimited by newlines)
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)

                    if not line.strip():
                        continue

                    message = Message.from_json(line)
                    await self._handle_message(message)

            except Exception as e:
                logger.error(f"Agent {self.agent_id} message loop error: {e}")
                await asyncio.sleep(0.1)
                
    async def _handle_message(self, message: Message):
        """Handle incoming message."""
        handler = self.message_handlers.get(message.type)
        if handler:
            try:
                await handler(message)
            except Exception as e:
                logger.error(f"Agent {self.agent_id} handler error: {e}")
        # Silently ignore messages without handlers - they may be handled by coordinator
            
    async def _send_message(self, message: Message):
        """Send message via message bus."""
        if self.socket:
            await asyncio.get_event_loop().sock_sendall(
                self.socket,
                message.to_json().encode()
            )
            
    def send_message_sync(self, message_type: MessageType, recipient: Optional[str], payload: Dict[str, Any]):
        """Send message synchronously (for convenience)."""
        message = Message(
            id=str(uuid.uuid4()),
            type=message_type,
            sender=self.agent_id,
            recipient=recipient,
            payload=payload,
            timestamp=datetime.now()
        )
        asyncio.create_task(self._send_message(message))
        
    async def _handle_ping(self, message: Message):
        """Handle ping message."""
        pong = Message(
            id=str(uuid.uuid4()),
            type=MessageType.PONG,
            sender=self.agent_id,
            recipient=message.sender,
            payload={'timestamp': datetime.now().isoformat()},
            timestamp=datetime.now()
        )
        await self._send_message(pong)
        
    async def _handle_shutdown(self, message: Message):
        """Handle shutdown message."""
        logger.info(f"Agent {self.agent_id} shutting down")
        await self.on_shutdown()
        self.running = False
        
    def shutdown(self):
        """Shutdown the agent."""
        if self.socket:
            self.socket.close()
        self.running = False
        
    @abstractmethod
    async def on_start(self):
        """Called when agent starts up."""
        pass
        
    @abstractmethod
    async def on_shutdown(self):
        """Called when agent shuts down."""
        pass


@dataclass 
class GameState:
    """Shared game state structure."""
    session_id: str
    scenario: Dict[str, Any]
    characters: List[Dict[str, Any]]
    npcs: List[Dict[str, Any]]
    current_turn: int
    phase: str
    actions: List[Dict[str, Any]]
    void_events: List[Dict[str, Any]]
    timestamp: datetime


class GameCoordinator:
    """
    Coordinates the overall game session and manages data collection.
    """
    
    def __init__(self, socket_path: Optional[str] = None):
        self.message_bus = MessageBus(socket_path)
        self.agents: Dict[str, str] = {}  # agent_id -> agent_type
        self.game_state: Optional[GameState] = None
        self.session_data: List[Dict[str, Any]] = []
        self.running = False
        
        # Set up message handlers
        self.message_bus.add_handler('coordinator', self._handle_coordinator_message)
        
    async def start(self):
        """Start the game coordinator."""
        await self.message_bus.start_server()
        self.running = True
        logger.info("Game coordinator started")
        
    def _handle_coordinator_message(self, message: Message):
        """Handle messages relevant to coordination."""
        if message.type == MessageType.AGENT_REGISTER:
            self.agents[message.sender] = message.payload.get('agent_type', 'Unknown')
            logger.info(f"Registered agent {message.sender} ({self.agents[message.sender]})")

        elif message.type == MessageType.ACTION_DECLARED:
            # Record action for data collection
            self.session_data.append({
                'type': 'action',
                'agent': message.sender,
                'action': message.payload,
                'timestamp': message.timestamp.isoformat()
            })

        elif message.type == MessageType.GAME_STATE_UPDATE:
            # Update shared game state
            self.game_state = GameState(**message.payload)

        elif message.type == MessageType.SESSION_START:
            # Track session start
            logger.info(f"Session started: {message.payload.get('session_id')}")
            self.session_data.append({
                'type': 'session_start',
                'config': message.payload.get('config', {}),
                'timestamp': message.timestamp.isoformat()
            })

        elif message.type == MessageType.SCENARIO_SETUP:
            # Track scenario setup
            logger.info(f"Scenario: {message.payload.get('scenario', {}).get('theme', 'Unknown')}")
            self.session_data.append({
                'type': 'scenario',
                'scenario': message.payload.get('scenario', {}),
                'timestamp': message.timestamp.isoformat()
            })

        elif message.type == MessageType.DM_NARRATION:
            # Track DM narration
            self.session_data.append({
                'type': 'narration',
                'narration': message.payload.get('narration', ''),
                'timestamp': message.timestamp.isoformat()
            })
            
    async def create_session(self, config: Dict[str, Any]) -> str:
        """Create and start a new game session."""
        session_id = str(uuid.uuid4())
        
        # Initialize game state
        self.game_state = GameState(
            session_id=session_id,
            scenario={},
            characters=[],
            npcs=[],
            current_turn=0,
            phase='setup',
            actions=[],
            void_events=[],
            timestamp=datetime.now()
        )
        
        # Broadcast session start
        start_message = Message(
            id=str(uuid.uuid4()),
            type=MessageType.SESSION_START,
            sender='coordinator',
            recipient=None,  # broadcast
            payload={
                'session_id': session_id,
                'config': config
            },
            timestamp=datetime.now()
        )
        
        await self.message_bus._route_message(start_message)
        return session_id
        
    def get_session_data(self) -> List[Dict[str, Any]]:
        """Get collected session data."""
        return self.session_data
        
    def shutdown(self):
        """Shutdown the coordinator."""
        self.running = False
        self.message_bus.shutdown()