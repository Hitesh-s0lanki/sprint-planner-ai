from pydantic import BaseModel
from typing import Optional, List, Literal

class ExecutionPreferencesState(BaseModel):
    working_style: Optional[str] = None
    preferred_sprint_format: Optional[str] = None
    need_AI_assistance_for: Optional[List[str]] = None
    risk_tolerance: Optional[str] = None

    follow_up_question: Optional[str] = None
    state: Literal["ongoing", "completed"] = "ongoing"
