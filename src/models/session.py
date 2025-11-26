from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Session(BaseModel):
    id: Optional[str]
    user_id: Optional[str]
    created_at: Optional[datetime]
    last_activity: Optional[datetime]
