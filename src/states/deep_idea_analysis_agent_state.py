from pydantic import BaseModel
from typing import Optional, List, Literal

class DeepIdeaAnalysisState(BaseModel):
    idea_long_description: Optional[str] = None
    core_features_must_have: Optional[List[str]] = None
    optional_features_good_to_have: Optional[List[str]] = None
    is_product_needed: Optional[str] = None
    product_similar_to: Optional[str] = None

    follow_up_question: Optional[str] = None
    state: Literal["ongoing", "completed"] = "ongoing"
