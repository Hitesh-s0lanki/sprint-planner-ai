from pydantic import BaseModel
from typing import List, Optional, Literal


class SprintTask(BaseModel):
    title: str
    description: str  # must include Definition of Done / acceptance criteria textually
    priority: Literal["High", "Medium", "Low"]
    timeline_days: float
    assigneeEmail: str
    sub_tasks: Optional[List[str]] = None


class SprintWeek(BaseModel):
    week: int
    tasks: List[SprintTask]


class SprintPlanningState(BaseModel):
    sprints: List[SprintWeek] = []
