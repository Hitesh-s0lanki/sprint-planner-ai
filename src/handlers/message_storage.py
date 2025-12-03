"""
Message storage operations for saving and fetching chat messages from the database.
"""
import logging
import asyncio
import uuid
from typing import Optional, List
from langchain_core.messages import HumanMessage, AIMessage
from src.models.chat_transfer_model import ChatResponse, ChatRequest
from src.models.chat_message_model import ChatMessageModel
import psycopg

logger = logging.getLogger(__name__)


async def save_user_message(chat_request: ChatRequest, db, stage: int) -> bool:
    """
    Save user message to database with retry logic.
    
    Args:
        chat_request: The chat request containing user message
        db: Database instance
        stage: The idea state stage (1-9)
    
    Returns:
        bool: True if saved successfully, False otherwise
    """
    if not db or not chat_request.user_message:
        return False
    
    max_retries = 3
    retry_delay = 0.5
    
    for attempt in range(max_retries):
        try:
            user_message = ChatMessageModel(
                chat_id=uuid.uuid4(),
                session_id=chat_request.session_id,
                user_id=chat_request.user_id,
                role="user",
                content=chat_request.user_message,
                metadata={},
                stage=stage
            )
            db.create_chat_message(user_message)
            logger.info(f"Saved user message to DB for session {chat_request.session_id}")
            return True
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                logger.warning(
                    f"Error saving user message (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Failed to save user message after {max_retries} attempts: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error saving user message to DB: {e}", exc_info=True)
            break  # Don't retry for non-connection errors
    
    return False


async def save_agent_message(
    session_id: str,
    user_id: Optional[str],
    content: str,
    db,
    stage: int
) -> bool:
    """
    Save agent response to database with retry logic.
    
    Args:
        session_id: The session ID
        user_id: Optional user ID
        content: The agent response content
        db: Database instance
        stage: The idea state stage (1-9)
    
    Returns:
        bool: True if saved successfully, False otherwise
    """
    if not db or not content:
        return False
    
    max_retries = 3
    retry_delay = 0.5
    
    for attempt in range(max_retries):
        try:
            agent_message = ChatMessageModel(
                chat_id=uuid.uuid4(),
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=content,
                metadata={},
                stage=stage
            )
            db.create_chat_message(agent_message)
            logger.info(f"Saved agent response to DB for session {session_id}")
            return True
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                logger.warning(
                    f"Error saving agent response (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Failed to save agent response after {max_retries} attempts: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error saving agent response to DB: {e}", exc_info=True)
            break  # Don't retry for non-connection errors
    
    return False


async def fetch_session_messages(
    session_id: str,
    db,
    idea_state_stage: int
) -> Optional[ChatResponse]:
    """
    Fetch all messages for a session from the database with retry logic.
    
    Args:
        session_id: The session ID to fetch messages for
        db: Database instance
        idea_state_stage: The idea state stage for the response
    
    Returns:
        ChatResponse with messages list, or None if fetch failed
    """
    if not db:
        return None
    
    max_retries = 3
    retry_delay = 0.5
    
    for attempt in range(max_retries):
        try:
            chat_messages = db.get_chat_messages_by_session(session_id)
            # Convert ChatMessageModel to dict format for ChatResponse
            messages_list = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "metadata": msg.metadata,
                    "chat_id": str(msg.chat_id),
                    "stage": msg.stage,
                    "formatted_output": msg.formatted_output,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    "updated_at": msg.updated_at.isoformat() if msg.updated_at else None
                }
                for msg in chat_messages
            ]
            
            logger.info(f"Fetched {len(messages_list)} messages for session {session_id}")
            
            if len(messages_list) == 0:
                await save_agent_message(
                    session_id,
                    None,
                    "Hey! 👋 Welcome to SprintPlanner. Tell me about the idea you're excited to build — even a rough thought is enough. Let's shape it together.",
                    db,
                    idea_state_stage
                )
                messages_list = [
                    {
                        "role": "assistant",
                        "content": "Hey! 👋 Welcome to SprintPlanner. Tell me about the idea you're excited to build — even a rough thought is enough. Let's shape it together.",
                        "metadata": {},
                        "chat_id": str(uuid.uuid4()),
                        "stage": idea_state_stage
                    }
                ]
            
            return ChatResponse(
                connection_status="started",
                messages=messages_list,
                idea_state_stage=idea_state_stage
            )
            
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                logger.warning(
                    f"Database connection error (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(
                    f"Failed to fetch messages from DB after {max_retries} attempts: {e}",
                    exc_info=True
                )
                # Return empty messages list to continue
                return ChatResponse(
                    connection_status="started",
                    messages=[],
                    idea_state_stage=idea_state_stage
                )
        except Exception as e:
            logger.error(f"Error fetching messages from DB: {e}", exc_info=True)
            # Return empty messages list to continue
            return ChatResponse(
                connection_status="started",
                messages=[],
                idea_state_stage=idea_state_stage
            )
    
    return ChatResponse(
        connection_status="started",
        messages=[],
        idea_state_stage=idea_state_stage
    )


async def get_conversation_history(session_id: str, db) -> List:
    """
    Fetch all previous messages for a session and convert them to LangChain message format.
    
    Args:
        session_id: The session ID to fetch messages for
        db: Database instance
    
    Returns:
        List of LangChain messages (HumanMessage/AIMessage) in chronological order
    """
    if not db:
        return []
    
    try:
        chat_messages = db.get_chat_messages_by_session(session_id)
        langchain_messages = []
        
        for msg in chat_messages:
            if msg.role == "user":
                langchain_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                langchain_messages.append(AIMessage(content=msg.content))
        
        logger.debug(f"Converted {len(langchain_messages)} messages to LangChain format for session {session_id}")
        return langchain_messages
    except Exception as e:
        logger.error(f"Error fetching conversation history: {e}", exc_info=True)
        return []

