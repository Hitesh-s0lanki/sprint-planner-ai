from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, Union
from datetime import datetime
import uuid


class User(BaseModel):
    """
    User model representing a user in the system.
    Maps to the users table in the database.
    """
    
    id: str = Field(..., description="Unique user identifier")
    
    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_string(cls, v: Union[str, uuid.UUID]) -> str:
        """Convert UUID to string if needed."""
        if isinstance(v, uuid.UUID):
            return str(v)
        return v
    clerk_id: Optional[str] = Field(None, description="Clerk authentication ID")
    email: Optional[str] = Field(None, description="User email address")
    name: Optional[str] = Field(None, description="User full name")
    role: Optional[Literal["individual", "investor", "admin"]] = Field(
        None,
        description="User role: individual, investor, or admin"
    )
    description: Optional[str] = Field(None, description="User description/bio")
    profession: Optional[str] = Field(None, description="User profession")
    
    # Timestamps (typically added by database, but included for consistency)
    created_at: Optional[datetime] = Field(None, description="User creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="User last update timestamp")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "user-123",
                "clerk_id": "user_abc123",
                "email": "user@example.com",
                "name": "John Doe",
                "role": "individual",
                "description": "Software engineer and entrepreneur",
                "profession": "Software Engineer",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z"
            }
        }















