from pydantic import BaseModel
from typing import Optional, List, Literal

class MarketCompetitionState(BaseModel):
    market_size_assumption: Optional[str] = None
    primary_competitors: Optional[List[str]] = None
    competitive_advantage: Optional[str] = None
    user_pain_points_from_research: Optional[List[str]] = None
    validation_status: Optional[str] = None

    follow_up_question: Optional[str] = None
    state: Literal["ongoing", "completed"] = "ongoing"
