from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class CharResponse(BaseModel):
    content: str

