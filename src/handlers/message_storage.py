"""
Message storage operations for saving and fetching chat messages from the database.
"""
import logging
import asyncio
import uuid
import json
from typing import Optional, List, Dict
from langchain_core.messages import HumanMessage, AIMessage
from src.models.chat_transfer_model import ChatResponse, ChatRequest
from src.models.chat_message_model import ChatMessageModel
from src.states.global_idea_state import GlobalIdeaState
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
    stage: int,
    formatted_output: Optional[str] = None
) -> bool:
    """
    Save agent response to database with retry logic.
    
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
    retry_delay = 0.5
    
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


def update_global_state_from_messages(messages: List[Dict], global_state: GlobalIdeaState) -> GlobalIdeaState:
    """
    Update global idea state from completed messages.
    Only updates from messages where state == "completed".
    
    Args:
        messages: List of message dictionaries with formatted_output
        global_state: GlobalIdeaState instance to update
        
    Returns:
        Updated GlobalIdeaState instance
    """
    if not messages or not global_state:
        return global_state
    
    try:
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
                # Use model_validate to update only matching fields
                global_state.model_validate(parsed_output, strict=False)
                logger.debug(f"Updated global state from stage {msg.get('stage')} completed message")
            except Exception as e:
                logger.warning(f"Error updating global state from message: {e}")
                continue
        
        return global_state
    except Exception as e:
        logger.error(f"Error updating global state from messages: {e}", exc_info=True)
        return global_state


def determine_current_stage(messages: List[Dict]) -> int:
    """
    Determine the current stage based on completed states in messages.
    
    Stages are considered completed if there's a message with:
    - role == "assistant"
    - formatted_output with state == "completed"
    - stage matching the stage number
    
    Args:
        messages: List of message dictionaries
        
    Returns:
        Current stage number (1-8). Returns 1 if no completed stages found.
    """
    if not messages:
        return 1
    
    # Track which stages are completed
    completed_stages = set()
    
    try:
        for msg in messages:
            # Only check assistant messages with formatted_output
            if msg.get("role") != "assistant":
                continue
            
            formatted_output = msg.get("formatted_output")
            if not formatted_output:
                continue
            
            # Check if state is completed
            state = extract_state_from_formatted_output(formatted_output)
            if state == "completed":
                stage = msg.get("stage")
                if stage and isinstance(stage, int) and 1 <= stage <= 8:
                    completed_stages.add(stage)
        
        # Current stage is the next incomplete stage
        # If stages 1-3 are completed, current stage is 4
        # If no stages are completed, current stage is 1
        if not completed_stages:
            return 1
        
        # Find the highest completed stage
        max_completed = max(completed_stages)
        
        # If all stages 1-8 are completed, return 8
        # Otherwise, return the next stage after the highest completed
        if max_completed >= 8:
            return 8
        
        return max_completed + 1
        
    except Exception as e:
        logger.error(f"Error determining current stage: {e}", exc_info=True)
        return 1


async def fetch_session_messages(
    session_id: str,
    db,
    idea_state_stage: int,
    global_state: Optional[GlobalIdeaState] = None
) -> Optional[ChatResponse]:
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
            
            # Update global state from completed messages if provided
            if global_state and messages_list:
                try:
                    update_global_state_from_messages(messages_list, global_state)
                    logger.debug(f"Updated global state from messages for session {session_id}")
                except Exception as e:
                    logger.warning(f"Failed to update global state from messages: {e}")
            
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
            
            return ChatResponse(
                connection_status="started",
                messages=messages_list,
                idea_state_stage=current_stage
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

