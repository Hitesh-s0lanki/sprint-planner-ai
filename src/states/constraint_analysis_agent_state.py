from pydantic import BaseModel
from typing import Optional, List, Literal

class ConstraintAnalysisState(BaseModel):
    budget_range: Optional[str] = None
    tools_they_already_use: Optional[List[str]] = None
    time_constraints: Optional[str] = None
    assets_available: Optional[List[str]] = None

    follow_up_question: Optional[str] = None
    state: Literal["ongoing", "completed"] = "ongoing"
