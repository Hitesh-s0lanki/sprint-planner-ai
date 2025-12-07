"""
Streaming handler for chat responses.
Handles the streaming of agent responses and delegates message storage to message_storage module.
"""
import logging
from typing import AsyncGenerator
from langchain_core.messages import HumanMessage, AIMessage
from src.models.chat_transfer_model import ChatResponse, ChatRequest
from src.handlers.message_storage import (
    save_user_message,
    fetch_session_messages,
    get_conversation_history
)

logger = logging.getLogger(__name__)


async def stream_generator(chat_request: ChatRequest, workflow, db=None) -> AsyncGenerator[str, None]:
    """
    Generate streaming responses from the agent and handle message persistence.
    
    Args:
        chat_request: The chat request containing user message and session info
        workflow: The Workflow instance
        db: Optional database instance for message persistence
    
    Yields:
        NDJSON formatted ChatResponse strings
    """
    # Ensure stage is between 1-9 (required by ChatMessageModel)
    stage = chat_request.idea_state_stage if 1 <= chat_request.idea_state_stage <= 9 else 1
        
    try:
        # Handle 'started' connection_status: fetch messages from DB
        if chat_request.connection_status == "started":
            initial_response = await fetch_session_messages(
                chat_request.session_id,
                db,
                chat_request.idea_state_stage
            )
            if initial_response:
                yield f"{initial_response.model_dump_json()}\n"
                logger.info(f"Sent messages for session {chat_request.session_id}")
        
        # Save user message to database (always save if there's a user message)
        if chat_request.user_message and chat_request.connection_status == "active":
            await save_user_message(chat_request, db, stage)
            
            # Fetch all conversation history from database (includes the message we just saved)
            # This ensures we have the complete conversation context
            messages = await get_conversation_history(chat_request.session_id, db)
    
            # Execute the workflow and get the response
            response = await workflow.execute(messages, stage, chat_request.session_id, chat_request.user_id, db)
            yield f"{response.model_dump_json()}\n"
        
        elif chat_request.connection_status == "active" and not chat_request.user_message:
            logger.warning(f"User message is required.")
            error_response = ChatResponse(connection_status="error", error_message="User message is required.")
            yield f"{error_response.model_dump_json()}\n"
        
    except Exception as e:
        logger.error(f"Error in stream_generator: {e}", exc_info=True)
        error_response = ChatResponse(connection_status="error", error_message=f"Error: {str(e)}")
        yield f"{error_response.model_dump_json()}\n"

