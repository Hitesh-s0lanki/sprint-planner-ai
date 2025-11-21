from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class InvestorQuestion(BaseModel):
    id: Optional[str]
    idea_id: str
    investor_id: str
    question_text: str
    answer_individual: Optional[str]
    answer_ai: Optional[str]
    created_at: Optional[datetime]
