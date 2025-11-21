from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class User(BaseModel):
    id: Optional[str]
    email: Optional[str]
    name: Optional[str]
    role: Optional[str]  # "individual" | "investor"
    plan_type: Optional[str]  # "free" | "paid"
    created_at: Optional[datetime]
