from pydantic import BaseModel
from typing import Literal

NarrativeCategory = Literal[
    "narrative",
    "product",
    "engineering",
    "administrative",
    "people_hr",
    "gtm",
    "funding",
    "tools",
]

NarrativeSectionType = Literal["text", "files"]

class NarrativeSection(BaseModel):
    category: NarrativeCategory
    name: str
    type: NarrativeSectionType = "text"
    content: str  # Markdown output
    position: int = 0  # caller can set

class NarrativeSectionResponse(BaseModel):
    section: NarrativeSection