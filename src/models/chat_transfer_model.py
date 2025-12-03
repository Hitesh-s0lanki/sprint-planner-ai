from typing import Optional, List, Literal
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    """Incoming request from client → server."""

    connection_status: Literal["started", "active", "error", "disactive"] = Field(
        "active",
        description="Type of request."
    )
    session_id: str
    user_id: Optional[str] = Field(
        default=None,
        description="Optional user ID associated with the request."
    )
    user_message: Optional[str] = Field(
        default=None,
        description="Optional user message associated with the request."
    )
    idea_state_stage: int = Field(
        default=0, # means not started
        description="Current stage of the idea state."
    )
    

class ChatResponse(BaseModel):
    """Server → client response."""
    
    connection_status: Literal["started", "active", "error", "disactive"] = Field(
        "active",
        description="Status of the chat connection."
    )
    
    # will only be provide if the chat_messages are there for the session
    messages: Optional[List[dict]] = Field(
        default=None, 
        description="List of messages sent by the user. Each message is a dictionary with the following keys: 'role', 'content', 'metadata'."
    )
    response_content: Optional[str] = Field(
        default=None,
        description="Last message sent by the user."
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if the connection is in error status."
    )
    idea_state_stage: int = Field(
        default=0, # means not started
        description="Current stage of the idea state."
    )
    
