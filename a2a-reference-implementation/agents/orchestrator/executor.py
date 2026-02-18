"""
Orchestrator Agent Executor - A2A standard pattern with EventQueue.
"""

import logging
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import UnsupportedOperationError, TextPart, Message, Part

from .agent import OrchestratorAgent

logger = logging.getLogger(__name__)


class OrchestratorExecutor(AgentExecutor):
    """Standard A2A executor for Orchestrator Agent using EventQueue."""

    def __init__(self, config: dict = None):
        self.agent = OrchestratorAgent(config)
        self._current_context_id: str = "default"
        self._current_token: str = None

    def set_auth_token(self, token: str):
        """Set auth token from middleware."""
        self._current_token = token

    def set_context_id(self, context_id: str):
        """Set context ID for session management."""
        self._current_context_id = context_id

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
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

        # Use task_id as context_id for session management
        ctx_id = getattr(context, 'task_id', None) or self._current_context_id

        logger.info(f"Orchestrator executing: {query[:50]}...")

        # Stream response from agent and collect
        full_response = ""
        async for chunk in self.agent.stream(query, ctx_id, self._current_token):
            content = chunk.get('content', '')
            if content:
                full_response += content

        # Create response message
        msg_id = context.message.message_id if context.message else 'default'
        message = Message(
            role="agent",
            parts=[Part(root=TextPart(text=full_response or "Processing request..."))],
            message_id=f"response-{msg_id}"
        )
        await event_queue.enqueue_event(message)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel is not supported."""
        raise UnsupportedOperationError("Cancel not supported")
