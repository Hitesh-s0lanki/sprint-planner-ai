import os
import logging
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

## handlers
from src.handlers.lifespan_handler import lifespan

## routes
from src.routes.chat_streaming import router as chat_streaming_router

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sprint-planner-ai")

# Validate required env vars early (but don't instantiate the model until startup)
if "OPENAI_API_KEY" not in os.environ:
    logger.warning("OPENAI_API_KEY not set — the model will fail to initialize until it's provided.")
    
if not os.environ.get("TAVILY_API_KEY"):
    logger.warning("TAVILY_API_KEY not set — the model will fail to initialize until it's provided.")


# Create FastAPI app with lifespan handler
app = FastAPI(
    title="Sprint Planner AI - Agent Streaming Server",
    description="A FastAPI server to stream responses from a LangChain agent.",
    docs_url="/",
    lifespan=lifespan,
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    for err in exc.errors():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "connection_status": "error",
                "error_message": f"{err["loc"][1]} is required",
                "idea_state_stage": 0
            },
        )
        
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content= {
            "connection_status": "error",
            "error_message": "Validation failed for request body.",
            "idea_state_stage": 0
        }
    )

# Include routers
app.include_router(chat_streaming_router)


# if __name__ == "__main__":
#     # Use python -m uvicorn app:app --reload --port 8000 in production dev.
#     print("Starting FastAPI server on http://localhost:8000")
#     uvicorn.run(app, host="0.0.0.0", port=8000)
