"""
Aeonisk Multi-Agent Self-Playing System

A distributed system for generating realistic gameplay data through
autonomous AI agents playing Aeonisk YAGS sessions together.
"""

from .base import Agent, MessageBus, GameCoordinator
from .dm import AIDMAgent 
from .player import AIPlayerAgent
from .npc import AINPCAgent
from .session import SelfPlayingSession

__all__ = [
    'Agent',
    'MessageBus', 
    'GameCoordinator',
    'AIDMAgent',
    'AIPlayerAgent',
    'AINPCAgent',
    'SelfPlayingSession'
]