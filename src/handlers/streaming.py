import logging
from typing import AsyncGenerator, List
from langchain_core.messages import HumanMessage, AIMessage
from src.schemas.models import CharResponse

logger = logging.getLogger(__name__)


async def stream_generator(messages: List[HumanMessage], agent) -> AsyncGenerator[str, None]:
    """Stream chunks from the agent in CharResponse format."""
    try:
        logger.info(f"Starting stream for messages: {messages}")
        last_content = ""
        chunk_count = 0
        
        async for chunk in agent.astream(messages):
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
                            # Extract only the new part
                            if content.startswith(last_content):
                                new_part = content[len(last_content):]
                                if new_part:
                                    last_content = content
                                    response = CharResponse(content=new_part)
                                    logger.debug(f"Yielding new content: {new_part[:50]}...")
                                    yield f"{response.model_dump_json()}\n"
                            elif last_content and not content.startswith(last_content):
                                # Content changed completely, send the full new content
                                last_content = content
                                response = CharResponse(content=content)
                                logger.debug(f"Yielding full new content: {content[:50]}...")
                                yield f"{response.model_dump_json()}\n"
                            elif not last_content:
                                # First chunk
                                last_content = content
                                response = CharResponse(content=content)
                                logger.debug(f"Yielding first content: {content[:50]}...")
                                yield f"{response.model_dump_json()}\n"
            
            # If no messages found, log for debugging
            if not messages_list:
                logger.warning(f"No messages found in chunk #{chunk_count}: {chunk}")
        
        logger.info(f"Stream completed. Total chunks processed: {chunk_count}")
        
    except Exception as e:
        logger.error(f"Error in stream_generator: {e}", exc_info=True)
        error_response = CharResponse(content=f"Error: {str(e)}")
        yield f"{error_response.model_dump_json()}\n"

