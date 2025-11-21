from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Task(BaseModel):
    id: Optional[str]
    idea_id: str
    title: str
    description: Optional[str]
    priority: Optional[int]
    created_at: Optional[datetime]
