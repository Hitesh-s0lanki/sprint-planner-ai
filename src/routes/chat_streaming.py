import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.handlers.streaming import stream_generator
from src.models.chat_transfer_model import ChatResponse, ChatRequest

logger = logging.getLogger("sprint-planner-ai")

router = APIRouter(prefix="/api")

@router.post("/streaming")
async def stream_chat(chat_request: ChatRequest, http_request: Request):
    # get the agent and database from the app state
    agent = getattr(http_request.app.state, "agent", None)
    db = getattr(http_request.app.state, "db", None)
    
    if agent is None:
        logger.error("Agent not initialized. Cannot serve/stream.")
        return ChatResponse(
            connection_status="error",
            error_message="Agent not initialized. Cannot serve/stream.",
            idea_state_stage=chat_request.idea_state_stage
        )

    try:
        # stream_generator yields NDJSON lines (string) — use StreamingResponse
        # Pass the full ChatRequest and database to stream_generator
        return StreamingResponse(
            stream_generator(chat_request, agent, db),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except Exception as e:
        logger.exception("Error handling /stream: %s", e)
        error_msg = str(e)
        idea_stage = chat_request.idea_state_stage
        async def error_generator():
            error_response = ChatResponse(
                connection_status="error",
                error_message=f"Error: {error_msg}",
                idea_state_stage=idea_stage
            )
            yield f"{error_response.model_dump_json()}\n"
        return StreamingResponse(
            error_generator(),
            media_type="application/x-ndjson"
        )

