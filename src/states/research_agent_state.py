from pydantic import BaseModel
from typing import Optional

class ResearchAgentState(BaseModel):
    title: Optional[str] = None
    brief_summary: Optional[str] = None