from contextlib import asynccontextmanager
from fastapi import FastAPI
import os
from dotenv import load_dotenv
from src.llms.openai_llm import OpenAILLM
from src.agents.simple_agent import SimpleAgent
from src.database.neon_db import NeonDB
import logging

load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sprint-planner-ai")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    Initialize DB pool and the LLM agent on startup.
    Cleanly close DB pool on shutdown.
    """

    # Initialize database
    try:
        db = NeonDB()
        # Initialize database schemas (create tables if they don't exist)
        db.init_chat_schema()
        db.init_idea_state_schema()
        app.state.db = db
        logger.info("Database initialized successfully.")
    except Exception as exc:
        logger.exception("Failed to initialize database: %s", exc)
        app.state.db = None

    # Initialize the model and agent here to avoid import-time failures.
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_key:
        logger.error("OPENAI_API_KEY not found in environment. The agent will not be available.")
        app.state.agent = None
    else:
        try:
            model = OpenAILLM().get_llm_model()
            agent = SimpleAgent(model=model)
            
            app.state.agent = agent
            logger.info("Agent initialized successfully.")
        except Exception as exc:
            logger.exception("Failed to initialize model/agent: %s", exc)
            
    yield  # App runs here
    
    # Cleanup: close database pool
    if hasattr(app.state, "db") and app.state.db:
        try:
            app.state.db.pool.close()
            logger.info("Database pool closed.")
        except Exception as exc:
            logger.exception("Error closing database pool: %s", exc)
    
