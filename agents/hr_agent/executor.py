"""
HR Agent Executor - A2A standard pattern with EventQueue.
"""

import logging
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import UnsupportedOperationError, TextPart, Message, Part

from .agent import HRAgent

logger = logging.getLogger(__name__)


class HRExecutor(AgentExecutor):
    """Standard A2A executor for HR Agent using EventQueue."""

    def __init__(self, config: dict = None):
        self.agent = HRAgent(config)
        self._current_token: str = None

    def set_auth_token(self, token: str):
        """Set auth token from middleware."""
        self._current_token = token

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue
    ) -> None:
        """Execute agent task using EventQueue."""
        # Extract query from context
        query = ""
        if context.message and context.message.parts:
            for part in context.message.parts:
                if hasattr(part, 'root') and hasattr(part.root, 'text'):
                    query = part.root.text
                    break
                elif hasattr(part, 'text'):
                    query = part.text
                    break

        if not query:
            query = "Hello"

        logger.info(f"HR Agent processing: {query[:50]}...")

        # Process and enqueue response
        response = await self.agent.process_request(query, self._current_token)
        
        # Create response message with TextPart
        msg_id = context.message.message_id if context.message else 'default'
        message = Message(
            role="agent",
            parts=[Part(root=TextPart(text=response))],
            message_id=f"response-{msg_id}"
        )
        
        # Await the async enqueue_event
        await event_queue.enqueue_event(message)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel is not supported."""
        raise UnsupportedOperationError("Cancel not supported")
