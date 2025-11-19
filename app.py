import os
import logging
from dotenv import load_dotenv

load_dotenv()

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# local imports
from src.routes.chat_router import router as chat_router
from src.handlers.streaming import stream_generator
from src.schemas import ChatRequest, CharResponse
from src import db

# Lang model imports (kept here but model is created at startup)
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from src.agents.simple_agent import SimpleAgent

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sprint-planner-ai")

# Validate required env vars early (but don't instantiate the model until startup)
if "OPENAI_API_KEY" not in os.environ:
    logger.warning("OPENAI_API_KEY not set — the model will fail to initialize until it's provided.")

# Create FastAPI app
app = FastAPI(
    title="Sprint Planner AI - Simple Agent Streaming Server",
    description="A FastAPI server to stream responses from a LangChain agent.",
    docs_url="/",
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers (chat_router contains session/message endpoints)
app.include_router(chat_router)


@app.on_event("startup")
async def startup_event():
    """
    Initialize DB pool and the LLM agent on startup.
    Storing them on app.state so endpoints can access them.
    """
    logger.info("Starting up: creating DB pool...")
    await db.get_pool()
    logger.info("DB pool ready.")

    # Initialize the model and agent here to avoid import-time failures.
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        logger.error("OPENAI_API_KEY not found in environment. The agent will not be available.")
        app.state.agent = None
        return

    try:
        logger.info("Initializing ChatOpenAI model...")
        model = ChatOpenAI(model="gpt-4o-mini", temperature=0, streaming=True)
        agent = SimpleAgent(model=model, tools=[])
        app.state.agent = agent
        logger.info("Agent initialized successfully.")
    except Exception as exc:
        logger.exception("Failed to initialize model/agent: %s", exc)
        # Keep app running but mark agent unavailable
        app.state.agent = None


@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanly close DB pool if present.
    """
    logger.info("Shutting down: closing DB pool...")
    pool = getattr(db, "_pool", None)
    if pool:
        await pool.close()
    logger.info("Shutdown complete.")


@app.post("/stream")
async def stream_chat(request: ChatRequest):
    """
    Stream chat responses from the agent in NDJSON CharResponse format.
    Uses the streaming handler in src/handlers/streaming.py which expects
    messages and an agent with an `astream` method.
    """
    agent = getattr(app.state, "agent", None)
    if agent is None:
        # More informative than a raw 500 stack trace
        logger.error("Agent not initialized. Cannot serve /stream.")
        raise HTTPException(status_code=503, detail="Agent unavailable. Check server logs and OPENAI_API_KEY.")

    try:
        logger.info("Received stream request.")
        messages = [HumanMessage(content=request.message)]
        # stream_generator yields NDJSON lines (string) — use StreamingResponse
        return StreamingResponse(
            stream_generator(messages, agent),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except Exception as e:
        logger.exception("Error handling /stream: %s", e)
        async def error_generator():
            error_response = CharResponse(content=f"Error: {str(e)}")
            yield f"{error_response.model_dump_json()}\n"
        return StreamingResponse(
            error_generator(),
            media_type="application/x-ndjson",
            status_code=500
        )


if __name__ == "__main__":
    # Use python -m uvicorn app:app --reload --port 8000 in production dev.
    print("Starting FastAPI server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
