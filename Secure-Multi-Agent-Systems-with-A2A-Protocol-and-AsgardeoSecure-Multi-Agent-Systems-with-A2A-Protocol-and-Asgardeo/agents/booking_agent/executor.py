"""
Booking Agent Executor - Standard A2A pattern.
"""

import logging
from typing import Any

from a2a.server.agent_execution import AgentExecutor
from a2a.server.events import Event, EventQueue
from a2a.types import UnsupportedOperationError, Message, TextPart

from .agent import BookingAgent

logger = logging.getLogger(__name__)


class BookingExecutor(AgentExecutor):
    """
    Standard A2A executor for Booking Agent.
    Extracts token from request and validates.
    """
    
    def __init__(self, config: dict):
        self.agent = BookingAgent(config)
        self._current_token: str = None
    
    def set_auth_token(self, token: str):
        """Set auth token from middleware."""
        self._current_token = token
    
    async def execute(
        self,
        context: Any,
        event_queue: EventQueue
    ) -> None:
        """Execute booking request."""
        query = ""
        
        # Debug: log full context structure
        logger.info(f"Context type: {type(context)}")
        
        # Try to get all non-private attributes
        attrs = [a for a in dir(context) if not a.startswith('_')]
        logger.info(f"Context public attrs: {attrs}")
        
        # Try multiple approaches to extract query
        # Check for common attribute names
        for attr_name in ['request', 'params', 'message', 'data', 'body']:
            if hasattr(context, attr_name):
                attr_val = getattr(context, attr_name)
                logger.info(f"Found context.{attr_name} = {type(attr_val)}: {str(attr_val)[:100]}...")
        
        # Try context.request.params.message
        if hasattr(context, 'request'):
            request = context.request
            logger.info(f"request type: {type(request)}")
            if hasattr(request, 'params'):
                params = request.params
                logger.info(f"params type: {type(params)}, attrs: {[a for a in dir(params) if not a.startswith('_')][:10]}")
                if hasattr(params, 'message'):
                    message = params.message
                    logger.info(f"Found message via context.request.params.message: {type(message)}")
                    if hasattr(message, 'parts'):
                        for part in message.parts:
                            if hasattr(part, 'text'):
                                query = part.text
                                logger.info(f"Found query: {query[:50]}...")
                                break
        
        # Approach 2: Direct message attribute on context
        if not query and hasattr(context, 'message'):
            message = context.message
            # Debug: explore Message structure
            msg_attrs = [a for a in dir(message) if not a.startswith('_')]
            logger.info(f"Message attrs: {msg_attrs}")
            
            # Try common attribute names for parts
            parts = None
            if hasattr(message, 'parts'):
                parts = message.parts
            elif hasattr(message, 'content'):
                parts = [message.content] if not isinstance(message.content, list) else message.content
            
            if parts:
                logger.info(f"Found parts: {len(parts)} items, type: {type(parts[0]) if parts else 'empty'}")
                for part in parts:
                    # For Pydantic models, use model_dump() to get the data
                    part_data = None
                    if hasattr(part, 'model_dump'):
                        part_data = part.model_dump()
                    elif hasattr(part, 'dict'):
                        part_data = part.dict()
                    else:
                        part_data = {}
                    
                    logger.info(f"Part data: {part_data}")
                    
                    # Try to get text from the dumped data
                    text = part_data.get('text') or part_data.get('content') or part_data.get('value')
                    
                    # Also try direct attribute access
                    if not text and hasattr(part, 'text'):
                        text = part.text
                    if not text and hasattr(part, 'root'):
                        # Union types in Pydantic might have root
                        if hasattr(part.root, 'text'):
                            text = part.root.text
                    
                    if text:
                        query = text
                        logger.info(f"Found query: {query[:50]}...")
                        break
        
        if not query:
            query = "Show travel options"
            logger.info("Using default query")
        
        logger.info(f"Executing: {query[:50]}...")
        
        # Stream response and put events into queue
        async for chunk in self.agent.stream(query, self._current_token):
            content = chunk.get('content', '')
            if content:
                # Create and enqueue a message event
                message = Message(
                    messageId=str(id(chunk)),
                    role="agent",
                    parts=[TextPart(text=content)]
                )
                await event_queue.enqueue_event(message)
    
    async def cancel(self, context: Any, event: Event) -> None:
        """Cancel is not supported."""
        raise UnsupportedOperationError("Cancel not supported")

