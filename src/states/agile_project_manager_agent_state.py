from pydantic import BaseModel
from typing import List, Optional, Literal


class SprintTask(BaseModel):
    title: str
    description: str  # must include Definition of Done / acceptance criteria textually
    priority: Literal["High", "Medium", "Low"]
    timeline_days: float
    assigneeId: str
    sub_tasks: Optional[List[str]] = None


class SprintWeek(BaseModel):
    week: int
    tasks: List[SprintTask]


class SprintPlanningState(BaseModel):
    """
    Output state for the sprint planning agent.
    """
    sprint: List[SprintWeek] = []
    follow_up_question: Optional[str] = None
    state: Literal["ongoing", "completed"] = "ongoing"
