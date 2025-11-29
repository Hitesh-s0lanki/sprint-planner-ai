from typing import Optional, List, Literal, Dict, Any
from pydantic import BaseModel, Field

class FrontendActionArgs(BaseModel):
    """Arguments passed to frontend actions."""
    email: Optional[str] = None


class FrontendAction(BaseModel):
    """Action to be executed on the frontend."""
    tool_name: Optional[str] = Field(
        default=None,
        description="Name of the frontend action/tool to trigger."
    )
    args: Optional[FrontendActionArgs] = Field(
        default=None,
        description="Arguments required by the tool."
    )

class ChatRequest(BaseModel):
    """Incoming request from client → server."""

    request_type: Literal["session_started", "session_ongoing"] = Field(
        "session_started",
        description="Type of request."
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session ID to track conversation."
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Optional user ID associated with the request."
    )
    messages: List[dict] = Field(
        ..., 
        description="List of messages sent by the user. Each message is a dictionary with the following keys: 'role', 'content', 'metadata'."
    )
    frontend_action: Optional[FrontendAction] = Field(
        default=None,
        description="Optional frontend action triggered by the user."
    )

class ChatResponse(BaseModel):
    """Server → client response."""

    connection_status: Literal["active", "error", "disactive"] = Field(
        "active",
        description="Status of the chat connection."
    )
    messages: List[dict] = Field(
        ..., 
        description="List of messages sent by the user. Each message is a dictionary with the following keys: 'role', 'content', 'metadata'."
    )
    response: str = Field(
        ...,
        description="Actual assistant response text."
    )
    frontend_action: Optional[FrontendAction] = Field(
        default=None,
        description="Frontend action to be executed."
    )
