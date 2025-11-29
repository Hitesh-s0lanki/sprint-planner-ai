from pydantic import BaseModel, Field
from typing import Optional, List, Literal

class IdeaEvaluationState(BaseModel):
    idea_title: Optional[str] = None
    problem_statement: Optional[str] = None
    target_user: Optional[str] = None
    idea_summary_short: Optional[str] = None
    follow_up_question: Optional[str] = None
    state: Literal["ongoing", "completed"] = "ongoing"