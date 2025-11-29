from pydantic import BaseModel
from typing import Optional, List, Literal

class BusinessGoalsState(BaseModel):
    primary_goal_for_4_weeks: Optional[str] = None
    monetization_model: Optional[str] = None
    launch_channel: Optional[List[str]] = None
    KPI_for_success: Optional[List[str]] = None

    follow_up_question: Optional[str] = None
    state: Literal["ongoing", "completed"] = "ongoing"
