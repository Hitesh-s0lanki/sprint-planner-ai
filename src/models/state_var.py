from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime

class StateVar(BaseModel):
    id: Optional[int]
    session_id: Optional[str]
    user_id: Optional[str]
    key: str
    value: Any
    updated_at: Optional[datetime]
