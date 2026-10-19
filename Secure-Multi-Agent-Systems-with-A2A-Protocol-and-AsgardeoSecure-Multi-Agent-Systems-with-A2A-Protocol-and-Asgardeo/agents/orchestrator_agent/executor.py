"""
Orchestrator Agent Executor - Standard A2A pattern.
"""

import logging
from typing import AsyncIterable

from a2a.server.agent_execution import AgentExecutor
from a2a.server.events import Event
from a2a.types import Message, TextPart, UnsupportedOperationError
from a2a.utils import new_agent_text_message

from .agent import OrchestratorAgent

logger = logging.getLogger(__name__)

class OrchestratorExecutor(AgentExecutor):
    """
    Standard A2A executor for Orchestrator Agent.
    Routes requests to the agent's stream method.
    """
    
    def __init__(self, config: dict):
        self.agent = OrchestratorAgent(config)
        self._current_context_id: str = "default"
    
    async def execute(
        self,
        context: any,
        event: Event
    ) -> AsyncIterable[Event]:
        """Execute agent task."""
        # Extract query from message
        query = ""
        if hasattr(event, 'message') and event.message:
            for part in event.message.parts:
                if hasattr(part, 'text'):
                    query = part.text
                    break
        
        if not query:
            query = "Hello"
        
        # Use task_id as context_id for session management
        context_id = getattr(context, 'task_id', None) or self._current_context_id
        
        logger.info(f"Executing query: {query[:50]}...")
        
        # Stream response from agent
        async for chunk in self.agent.stream(query, context_id):
            content = chunk.get('content', '')
            if content:
                yield new_agent_text_message(content)
    
    async def cancel(self, context: any, event: Event) -> None:
        """Cancel is not supported."""
        raise UnsupportedOperationError("Cancel not supported")
