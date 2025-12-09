from pydantic import BaseModel, Field, conint
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

class ChatMessageModel(BaseModel):
    chat_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    session_id: str
    user_id: Optional[str] = None
    role: str
    formatted_output: Optional[str] = None
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # New field: stage (1–9)
    stage: conint(ge=1, le=9)
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
