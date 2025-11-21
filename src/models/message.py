from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Message(BaseModel):
    id: Optional[int]
    session_id: str
    user_id: Optional[str]
    role: str
    content: str
    created_at: Optional[datetime]
