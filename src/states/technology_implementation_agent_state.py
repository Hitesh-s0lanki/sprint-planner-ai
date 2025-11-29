from pydantic import BaseModel
from typing import Optional, List, Literal

class TechnologyImplementationState(BaseModel):
    tech_required: Optional[List[str]] = None
    preferred_frontend: Optional[str] = None
    preferred_backend: Optional[str] = None
    preferred_database: Optional[str] = None
    ai_models: Optional[str] = None
    cloud: Optional[str] = None
    integrations_needed: Optional[List[str]] = None
    data_needed_for_MVP: Optional[List[str]] = None
    constraints: Optional[List[str]] = None

    follow_up_question: Optional[str] = None
    state: Literal["ongoing", "completed"] = "ongoing"
