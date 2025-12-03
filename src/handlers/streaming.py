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
    save_agent_message,
    fetch_session_messages,
    get_conversation_history
)

logger = logging.getLogger(__name__)


async def stream_generator(chat_request: ChatRequest, agent, db=None) -> AsyncGenerator[str, None]:
    """
    Generate streaming responses from the agent and handle message persistence.
    
    Args:
        chat_request: The chat request containing user message and session info
        agent: The LangChain agent instance
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
            
            logger.info(f"Prepared {len(messages)} messages for agent (including conversation history)")
            
            last_content = ""
            chunk_count = 0
            agent_response_content = ""  # Accumulate full agent response
            
            async for chunk in agent.astream(messages, chat_request.session_id):
                chunk_count += 1
                logger.debug(f"Received chunk #{chunk_count}: {type(chunk)}, keys: {chunk.keys() if isinstance(chunk, dict) else 'N/A'}")
                
                # Handle different chunk structures
                messages_list = None
                
                if isinstance(chunk, dict):
                    if "messages" in chunk:
                        messages_list = chunk["messages"]
                    elif "model" in chunk and isinstance(chunk["model"], dict) and "messages" in chunk["model"]:
                        # Handle LangChain agent model chunks: {'model': {'messages': [...]}}
                        messages_list = chunk["model"]["messages"]
                    elif "agent" in chunk and isinstance(chunk["agent"], dict) and "messages" in chunk["agent"]:
                        messages_list = chunk["agent"]["messages"]
                    elif "steps" in chunk:
                        # Handle agent steps
                        for step in chunk.get("steps", []):
                            if "messages" in step:
                                messages_list = step["messages"]
                                break
                
                if messages_list:
                    for message in messages_list:
                        # Check if it's an AI message
                        if isinstance(message, AIMessage) or (hasattr(message, "type") and message.type == "ai"):
                            # Handle different content types
                            raw_content = message.content if hasattr(message, "content") else str(message)
                            
                            # Convert content to string if it's a list or other type
                            if isinstance(raw_content, list):
                                # Handle list of content blocks (e.g., from OpenAI)
                                content = "".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in raw_content)
                            elif isinstance(raw_content, dict):
                                # Handle dict content
                                content = raw_content.get("text", str(raw_content))
                            else:
                                content = str(raw_content)
                            
                            if content and isinstance(content, str):
                                # Update accumulated agent response
                                agent_response_content = content
                                
                                # Extract only the new part
                                if content.startswith(last_content):
                                    new_part = content[len(last_content):]
                                    if new_part:
                                        last_content = content
                                        response = ChatResponse(connection_status="active", response_content=new_part, messages=messages_list)
                                        logger.debug(f"Yielding new content: {new_part[:50]}...")
                                        yield f"{response.model_dump_json()}\n"
                                elif last_content and not content.startswith(last_content):
                                    # Content changed completely, send the full new content
                                    last_content = content
                                    response = ChatResponse(connection_status="active", response_content=content, messages=messages_list)
                                    logger.debug(f"Yielding full new content: {content[:50]}...")
                                    yield f"{response.model_dump_json()}\n"
                                elif not last_content:
                                    # First chunk
                                    last_content = content
                                    response = ChatResponse(connection_status="active", response_content=content, messages=messages_list)
                                    logger.debug(f"Yielding first content: {content[:50]}...")
                                    yield f"{response.model_dump_json()}\n"
                
                # If no messages found, log for debugging
                if not messages_list:
                    logger.warning(f"No messages found in chunk #{chunk_count}: {chunk}")
            
            # Save agent response to database after streaming completes
            if agent_response_content:
                await save_agent_message(
                    chat_request.session_id,
                    chat_request.user_id,
                    agent_response_content,
                    db,
                    stage
                )
        
        elif chat_request.connection_status == "active" and not chat_request.user_message:
            logger.warning(f"User message is required.")
            error_response = ChatResponse(connection_status="error", error_message="User message is required.")
            yield f"{error_response.model_dump_json()}\n"
        
    except Exception as e:
        logger.error(f"Error in stream_generator: {e}", exc_info=True)
        error_response = ChatResponse(connection_status="error", error_message=f"Error: {str(e)}")
        yield f"{error_response.model_dump_json()}\n"

