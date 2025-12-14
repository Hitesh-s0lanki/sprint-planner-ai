from typing import Optional, List, Literal
from pydantic import BaseModel, Field
class UserPreferences(BaseModel):
    """User preferences associated with the request."""
    user_id: Optional[str] = Field(
        default=None,
        description="Optional user ID associated with the request."
    )
    user_name: Optional[str] = Field(
        default=None,
        description="Optional user message associated with the request."
    )
    user_email: Optional[str] = Field(
        default=None,
        description="Optional user email associated with the request."
    )
    

class Event(BaseModel):
    """Event associated with the request."""
    event_type: Literal[
        "project_created",
        "team_members_synced",
        "sources_updated",
        "sprint_plan_generated",
        "narrative_sections_started",
        "completed"
        ] = Field(
        description="Type of event."
    )
    event_status: Literal["started", "completed"] = Field(
        "started",
        description="Status of the event."
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Project ID associated with the request."
    )
class ChatRequest(BaseModel):
    """Incoming request from client → server."""

    connection_status: Literal["started", "active", "events_streaming", "events_completed", "error", "disactive"] = Field(
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
    user_preferences: Optional[UserPreferences] = Field(
        default=None,
        description="Optional user preferences associated with the request."
    )
    event: Optional[Event] = Field(
        default=None,
        description="Event associated with the request."
    )

class ChatResponse(BaseModel):
    """Server → client response."""
    
    connection_status: Literal["started", "active", "events_streaming", "events_completed", "error", "disactive"] = Field(
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
    formatted_output: Optional[dict] = Field(
        default=None,
        description="Formatted output of the agent. This is the output of the agent in a dictionary format."
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if the connection is in error status."
    )
    idea_state_stage: int = Field(
        default=0, # means not started
        description="Current stage of the idea state."
    )
    event: Optional[Event] = Field(
        default=None,
        description="Event associated with the response."
    )
    
