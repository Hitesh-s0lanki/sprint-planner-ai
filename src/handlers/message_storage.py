"""
Message storage operations for saving and fetching chat messages from the database.
"""
import logging
import asyncio
import uuid
import json
import random
from typing import Optional, List, Dict
from langchain_core.messages import HumanMessage, AIMessage
from src.models.chat_transfer_model import ChatResponse, ChatRequest
from src.models.chat_message_model import ChatMessageModel
from src.states.global_idea_state import GlobalIdeaState
import psycopg
import psycopg_pool

logger = logging.getLogger(__name__)


async def save_user_message(chat_request: ChatRequest, db, stage: int) -> bool:
    """
    Save user message to database with retry logic and connection error handling.
    
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
    base_retry_delay = 0.5
    
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
            return True
        except (psycopg.OperationalError, psycopg.InterfaceError, psycopg_pool.PoolTimeout) as e:
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                wait_time = base_retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
                logger.warning(
                    f"Database connection error saving user message (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait_time:.2f}s..."
                )
                await asyncio.sleep(wait_time)
                # Try to reconnect pool if it's closed
                if hasattr(db, 'pool') and hasattr(db.pool, 'check'):
                    try:
                        db.pool.check()
                    except Exception:
                        pass
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
    stage: int,
    formatted_output: Optional[str] = None
) -> bool:
    """
    Save agent response to database with retry logic and connection error handling.
    
    Args:
        session_id: The session ID
        user_id: Optional user ID
        content: The agent response content
        db: Database instance
        stage: The idea state stage (1-9)
        formatted_output: the formatted output of the agent
    
    Returns:
        bool: True if saved successfully, False otherwise
    """
    if not db or not content:
        return False
    
    max_retries = 3
    base_retry_delay = 0.5
    
    for attempt in range(max_retries):
        try:
            agent_message = ChatMessageModel(
                chat_id=uuid.uuid4(),
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=content,
                formatted_output=formatted_output,
                metadata={},
                stage=stage
            )
            db.create_chat_message(agent_message)
            return True
        except (psycopg.OperationalError, psycopg.InterfaceError, psycopg_pool.PoolTimeout) as e:
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                wait_time = base_retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
                logger.warning(
                    f"Database connection error saving agent response (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait_time:.2f}s..."
                )
                await asyncio.sleep(wait_time)
                # Try to reconnect pool if it's closed
                if hasattr(db, 'pool') and hasattr(db.pool, 'check'):
                    try:
                        db.pool.check()
                    except Exception:
                        pass
            else:
                logger.error(f"Failed to save agent response after {max_retries} attempts: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error saving agent response to DB: {e}", exc_info=True)
            break  # Don't retry for non-connection errors
    
    return False


def parse_formatted_output(formatted_output: str) -> Optional[Dict]:
    """
    Parse formatted_output JSON string to dictionary.
    
    Args:
        formatted_output: JSON string to parse
        
    Returns:
        Parsed dictionary or None if parsing fails
    """
    if not formatted_output:
        return None
    
    try:
        parsed = json.loads(formatted_output)
        if isinstance(parsed, dict):
            return parsed
        else:
            logger.warning(f"Formatted output is not a dictionary: {type(parsed)}")
            return None
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing formatted_output JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing formatted_output: {e}", exc_info=True)
        return None


def extract_state_from_formatted_output(formatted_output: Optional[str]) -> Optional[str]:
    """
    Extract state field from formatted_output JSON string.
    
    Args:
        formatted_output: JSON string containing structured response
        
    Returns:
        State value ("ongoing" or "completed") or None if not found/invalid
    """
    if not formatted_output:
        return None
    
    parsed = parse_formatted_output(formatted_output)
    if not parsed:
        return None
    
    state = parsed.get("state")
    if state in ["ongoing", "completed"]:
        return state
    
    return None


def update_global_state_from_messages(messages: List[Dict]) -> GlobalIdeaState:
    """
    Update global idea state from completed messages.
    Only updates from messages where state == "completed".
    
    Args:
        messages: List of message dictionaries with formatted_output
        global_state: GlobalIdeaState instance to update
        
    Returns:
        Updated GlobalIdeaState instance
    """
    if not messages:
        return GlobalIdeaState()
    
    try:
        
        global_state = GlobalIdeaState()
        
        
        for msg in messages:
            # Only process assistant messages with formatted_output
            if msg.get("role") != "assistant":
                continue
            
            formatted_output = msg.get("formatted_output")
            if not formatted_output:
                continue
            
            # Parse and check if state is completed
            parsed_output = parse_formatted_output(formatted_output)
            if not parsed_output:
                continue
            
            state = parsed_output.get("state")
            
            if state != "completed":
                continue
            
            # Update global state with the structured response
            try:
                # Get current state as dict
                current_state_dict = global_state.model_dump()
                
                # Filter out None values from parsed_output to avoid overwriting existing values
                # Only update fields that have actual values (not None)
                updates = {k: v for k, v in parsed_output.items() if v is not None}
                
                # Merge updates into current state
                merged_state = {**current_state_dict, **updates}
                
                # Create new state instance from merged dict
                global_state = GlobalIdeaState.model_validate(merged_state, strict=False)
                logger.debug(f"Updated global state from stage {msg.get('stage')} completed message")
            except Exception as e:
                logger.warning(f"Error updating global state from message: {e}")
            
        return global_state
        
    except Exception as e:
        logger.error(f"Error updating global state from messages: {e}", exc_info=True)
        return GlobalIdeaState()


def determine_current_stage(messages: List[Dict]) -> int:
    """
        Determine the current stage based on the last message.
        Handles both dictionary messages and Pydantic model objects.
    """
    try:
        # Check if messages list is empty
        if not messages:
            return 1
        
        last_message = messages[-1]
        
        last_message_stage = 0
        
        # instance of ChatMessageModel
        if isinstance(last_message, ChatMessageModel):
            last_message_stage = last_message.stage
            role = last_message.role
            formatted_output = last_message.formatted_output
        else:
            # dict
            last_message_stage = last_message.get("stage")
            role = last_message.get("role")
            formatted_output = last_message.get("formatted_output")
        
        if last_message_stage == 8 and role == "assistant":
            parsed_output = parse_formatted_output(formatted_output)
            if parsed_output and parsed_output.get("state") == "completed":
                return 9
            else:
                return 8
            
        if last_message_stage == 9:
            return 10

        return last_message_stage if last_message_stage is not None else 1
        
    except Exception as e:
        logger.error(f"Error determining current stage: {e}", exc_info=True)
        return 1

async def fetch_session_messages(
    session_id: str,
    db,
    idea_state_stage: int,
) -> tuple:
    """
    Fetch all messages for a session from the database with retry logic.
    Updates global_idea_state from completed messages and determines current stage.
    
    Args:
        session_id: The session ID to fetch messages for
        db: Database instance
        idea_state_stage: The idea state stage for the response (fallback if can't determine)
        global_state: Optional GlobalIdeaState instance to update from messages
    
    Returns:
        ChatResponse with messages list and updated idea_state_stage, or None if fetch failed
    """
    if not db:
        return (None, GlobalIdeaState())
    
    max_retries = 3
    base_retry_delay = 0.5
    
    for attempt in range(max_retries):
        try:
            chat_messages = db.get_chat_messages_by_session(session_id)
            # Convert ChatMessageModel to dict format for ChatResponse
            # Skip messages with content "Stage completed"
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
            
            # Update global state from completed messages if provided
            global_state = update_global_state_from_messages(messages_list)
            logger.debug(f"Updated global state from messages for session {session_id}")
            
            # Determine current stage based on completed states
            current_stage = determine_current_stage(messages_list)
            
            if len(messages_list) == 0:
                await save_agent_message(
                    session_id,
                    None,
                    "Hey! 👋 Welcome to SprintPlanner. Tell me about the idea you're excited to build — even a rough thought is enough. Let's shape it together.",
                    db,
                    current_stage
                )
                messages_list = [
                    {
                        "role": "assistant",
                        "content": "Hey! 👋 Welcome to SprintPlanner. Tell me about the idea you're excited to build — even a rough thought is enough. Let's shape it together.",
                        "metadata": {},
                        "chat_id": str(uuid.uuid4()),
                        "stage": current_stage
                    }
                ]
            
            return (ChatResponse(
                connection_status="started",
                messages=[msg for msg in messages_list if msg.get("content") != "Stage completed"],
                idea_state_stage=current_stage
            ), global_state)
            
        except (psycopg.OperationalError, psycopg.InterfaceError, psycopg_pool.PoolTimeout) as e:
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                wait_time = base_retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
                logger.warning(
                    f"Database connection error fetching messages (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait_time:.2f}s..."
                )
                await asyncio.sleep(wait_time)
                # Try to reconnect pool if it's closed
                if hasattr(db, 'pool') and hasattr(db.pool, 'check'):
                    try:
                        db.pool.check()
                    except Exception:
                        pass
            else:
                logger.error(
                    f"Failed to fetch messages from DB after {max_retries} attempts: {e}",
                    exc_info=True
                )
                # Return empty messages list to continue
                return (ChatResponse(
                    connection_status="started",
                    messages=[],
                    idea_state_stage=idea_state_stage if idea_state_stage is not None else 1
                ), GlobalIdeaState())
        except Exception as e:
            logger.error(f"Error fetching messages from DB: {e}", exc_info=True)
            # Return empty messages list to continue
            return (ChatResponse(
                connection_status="started",
                messages=[],
                idea_state_stage=idea_state_stage if idea_state_stage is not None else 1
            ), GlobalIdeaState())
    
    return (ChatResponse(
        connection_status="started",
        messages=[],
        idea_state_stage=idea_state_stage
    ), GlobalIdeaState())


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
                if msg.formatted_output:
                    langchain_messages.append(AIMessage(content=msg.formatted_output))
                else:
                    langchain_messages.append(AIMessage(content=msg.content))
        
        logger.debug(f"Converted {len(langchain_messages)} messages to LangChain format for session {session_id}")
        return langchain_messages
    except Exception as e:
        logger.error(f"Error fetching conversation history: {e}", exc_info=True)
        return []


async def get_conversation_history_by_stage(session_id: str, stage: int, db) -> List:
    """
    Fetch messages for a session matching a specific stage and convert them to LangChain message format.
    
    Args:
        session_id: The session ID to fetch messages for
        stage: The stage number to filter messages by (1-9)
        db: Database instance
    
    Returns:
        List of LangChain messages (HumanMessage/AIMessage) in chronological order, filtered by stage
    """
    if not db:
        return []
    
    try:
        chat_messages = db.get_chat_messages_by_session(session_id)
        langchain_messages = []
        
        # Filter messages by stage
        for msg in chat_messages:
            if msg.stage == stage:
                if msg.role == "user":
                    langchain_messages.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    if msg.formatted_output:
                        langchain_messages.append(AIMessage(content=msg.formatted_output))
                    else:
                        langchain_messages.append(AIMessage(content=msg.content))
        
        logger.debug(f"Converted {len(langchain_messages)} messages to LangChain format for session {session_id} at stage {stage}")
        return langchain_messages
    except Exception as e:
        logger.error(f"Error fetching conversation history by stage: {e}", exc_info=True)
        return []


async def get_last_stage_messages(session_id: str, db) -> tuple:
    """
    Fetch all messages for a session and return all messages from the last stage with its stage number.
    
    Args:
        session_id: The session ID to fetch messages for
        db: Database instance
    
    Returns:
        Tuple of (List of LangChain messages, stage number) for all messages with the highest stage.
        Returns ([], 1) if no messages found or on error.
    """
    if not db:
        return ([], 1)
    
    try:
        chat_messages = db.get_chat_messages_by_session(session_id)
        
        if not chat_messages:
            logger.debug(f"No messages found for session {session_id}")
            return ([], 1)
        
        max_stage = determine_current_stage(chat_messages)
        last_stage_messages = [msg for msg in chat_messages if msg.stage == max_stage]
        
        if not last_stage_messages:
            logger.debug(f"No messages found for session {session_id} at stage {max_stage}")
            return ([], max_stage)
        
        # Convert all messages from the last stage to LangChain message format
        langchain_messages = []
        for msg in last_stage_messages:
            if msg.role == "user":
                langchain_message = HumanMessage(content=msg.content)
                langchain_messages.append(langchain_message)
            elif msg.role == "assistant":
                if msg.formatted_output:
                    langchain_message = AIMessage(content=msg.formatted_output)
                else:
                    langchain_message = AIMessage(content=msg.content)
                langchain_messages.append(langchain_message)
            else:
                logger.warning(f"Unknown role {msg.role} for message in session {session_id}, skipping")
                continue
        
        logger.info(f"Retrieved {len(langchain_messages)} messages from last stage {max_stage} for session {session_id}")
        # Return all messages from the last stage
        return (langchain_messages, max_stage)
    except Exception as e:
        logger.error(f"Error fetching last stage messages: {e}", exc_info=True)
        return ([], 1)

