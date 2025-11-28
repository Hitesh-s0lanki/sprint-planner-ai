# src/routes/ai_router.py
from fastapi import APIRouter, HTTPException
from src import db
import logging

from src.schemas.chat_response_models import ChatResponse, ChatRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai")

@router.post("/streaming")
async def create_streaming_session(request: ChatRequest):

    # Get session_id from request
    session_id = request.session_id
    
    ## get the messages on first request from the database
    request_type = request.request_type
    
    messages = []
    
    # ## get the messages on first request from the database
    # if request_type == "session_started":
    #     messages = await db.fetch(
    #         "SELECT id, role, content, metadata, created_at FROM messages WHERE session_id = $1 ORDER BY created_at ASC",
    #         session_id
    #     )

    # If session_id provided, validate it exists
    if session_id:
        row = await db.fetchrow(
            "SELECT id FROM sessions WHERE id = $1",
            session_id
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        logger.info(f"Connected to existing streaming session: {session_id}")
    else:
        # Create new session
        row = await db.fetchrow(
            "INSERT INTO sessions (user_id) VALUES ($1) RETURNING id",
            None
        )
        session_id = str(row["id"])
        logger.info(f"Created new streaming session: {session_id}")
    
    # Return streaming status
    return ChatResponse(
        connection_status='active',
        messages=messages,
        response='',
        frontend_action=None
    )

