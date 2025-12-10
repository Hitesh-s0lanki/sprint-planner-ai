from pydantic import BaseModel
from typing import Optional, List, Literal

class TeamMember(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    profession: Optional[str] = None
    role: Optional[str] = None
    description: Optional[str] = None
    domain_expertise: Optional[str] = None

class TeamProfileState(BaseModel):
    team: Optional[List[TeamMember]] = None
    execution_capacity: Optional[str] = None
    
    follow_up_question: Optional[str] = None
    state: Literal["ongoing", "completed"] = "ongoing"
