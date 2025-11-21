from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class Idea(BaseModel):
    id: Optional[str]
    user_id: str
    idea_name: str
    idea_description: Optional[str]
    problem_statement: Optional[str]
    target_audience: Optional[str]
    category: Optional[str]
    business_model: Optional[str]
    competitor_info: Optional[str]
    features_list: Optional[List[str]]
    summary_60_words: Optional[str]
    created_at: Optional[datetime]
