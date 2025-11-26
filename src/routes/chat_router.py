# src/routes/chat_router.py
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
from src import db
import json, re, logging
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat")


class MessageRequest(BaseModel):
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    role: str  # 'user' | 'agent' | 'system'
    content: str
    metadata: Optional[Any] = None


def extract_text_from_model_messages(obj) -> Optional[str]:
    """
    Extract plain text from shapes like:
    - {'model': {'messages': [HumanMessage(...), ...]}}
    - {'model': {'messages': ["content='...'", ...]}}
    - {'model': {'messages': [{'content': '...'}, ...]}}
    Returns the first non-empty content string or None.
    """
    try:
        model = obj.get("model") if isinstance(obj, dict) else None
        if not model:
            return None
        msgs = model.get("messages")
        if not msgs:
            return None

        # take first message item and try several heuristics
        first = msgs[0]

        # if it's an object with .content
        if hasattr(first, "content"):
            return getattr(first, "content")

        # if it's dict with 'content'
        if isinstance(first, dict) and isinstance(first.get("content"), (str, bytes)):
            return first.get("content")

        # if it's a string like "content='Here... ' additional_kwargs=..."
        if isinstance(first, str):
            # look for content='...'
            m = re.search(r"content=(?:'|\")(?P<c>.*?)(?:'|\")", first, flags=re.DOTALL)
            if m:
                return m.group("c")
            # otherwise return the whole string as fallback
            return first

    except Exception as e:
        logger.debug("extract_text_from_model_messages error: %s", e)
    return None


def normalize_agent_result(result) -> str:
    """
    Normalize possible result types into a plain string.
    """
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, bytes):
        return result.decode("utf-8", errors="replace")
    if isinstance(result, (list, tuple)):
        parts = [normalize_agent_result(r) for r in result]
        return " ".join([p for p in parts if p])
    if isinstance(result, dict):
        # try model.messages shape first (special LangChain run)
        text = extract_text_from_model_messages(result)
        if text:
            return text
        # fallback: try text/content keys
        if "text" in result and isinstance(result["text"], (str, bytes)):
            return normalize_agent_result(result["text"])
        if "content" in result and isinstance(result["content"], (str, bytes)):
            return normalize_agent_result(result["content"])
        # fallback to safe JSON string
        try:
            return json.dumps(result, default=str, ensure_ascii=False)
        except Exception:
            return str(result)
    # objects with 'content' or 'text' attributes (e.g., HumanMessage)
    if hasattr(result, "content"):
        try:
            return normalize_agent_result(getattr(result, "content"))
        except Exception:
            pass
    if hasattr(result, "text"):
        try:
            return normalize_agent_result(getattr(result, "text"))
        except Exception:
            pass
    # last resort
    try:
        return str(result)
    except Exception:
        return "<unserializable agent result>"


@router.post("/session/create")
async def create_session(user_id: Optional[str] = None):
    row = await db.fetchrow(
        "INSERT INTO sessions (user_id) VALUES ($1) RETURNING id",
        user_id
    )
    return {"session_id": str(row["id"])}


@router.post("/message")
async def post_message(request: Request, payload: MessageRequest):
    # ensure session exists
    session_id = payload.session_id
    if not session_id:
        row = await db.fetchrow("INSERT INTO sessions (user_id) VALUES ($1) RETURNING id", payload.user_id)
        session_id = str(row["id"])

    # save incoming message
    meta = None
    try:
        meta = json.dumps(payload.metadata, default=str) if payload.metadata is not None else None
    except Exception:
        meta = json.dumps(str(payload.metadata))

    await db.execute(
        "INSERT INTO messages (session_id, user_id, role, content, metadata) VALUES ($1,$2,$3,$4,$5)",
        session_id, payload.user_id, payload.role, payload.content, meta
    )

    # if user message -> call agent
    if payload.role == "user":
        agent = getattr(request.app.state, "agent", None)
        if agent is None:
            raise HTTPException(status_code=503, detail="Agent not available")

        agent_text = None

        # Try streaming astream if available
        try:
            astream = getattr(agent, "astream", None)
            if astream and callable(astream):
                collected = []
                async for chunk in agent.astream([payload.content]):
                    collected.append(normalize_agent_result(chunk))
                agent_text = "".join([c for c in collected if c])
        except Exception as e:
            logger.debug("astream error or not available: %s", e)
            agent_text = None

        # fallback to sync invoke in threadpool
        if not agent_text:
            invoke_fn = getattr(agent, "invoke", None)
            if not invoke_fn or not callable(invoke_fn):
                raise HTTPException(status_code=500, detail="Agent interface missing invoke/astream")
            result = await run_in_threadpool(invoke_fn, [payload.content])

            # first try special extractor for model.messages shapes
            if isinstance(result, dict):
                extracted = extract_text_from_model_messages(result)
                if extracted:
                    agent_text = extracted

            # otherwise normalize generically
            if not agent_text:
                agent_text = normalize_agent_result(result)

        # truncate if very long (optional)
        if len(agent_text) > 20000:
            agent_text = agent_text[:20000]

        # persist agent response
        await db.execute(
            "INSERT INTO messages (session_id, role, content) VALUES ($1, $2, $3)",
            session_id, "agent", agent_text
        )

        return {"ok": True, "agent_response": agent_text, "session_id": session_id}

    return {"ok": True, "session_id": session_id}


@router.get("/session/{session_id}/messages")
async def get_messages(session_id: str):
    rows = await db.fetch(
        "SELECT id, role, content, metadata, created_at FROM messages WHERE session_id = $1 ORDER BY created_at ASC",
        session_id
    )
    out = []
    for r in rows:
        c = r["content"]
        # if looks like a serialized run blob, try extracting
        cleaned = None
        if isinstance(c, str) and c.strip().startswith("{"):
            # try JSON decode then extract
            try:
                parsed = None
                try:
                    parsed = json.loads(c)
                except Exception:
                    parsed = None
                if isinstance(parsed, dict):
                    extracted = extract_text_from_model_messages(parsed)
                    if extracted:
                        cleaned = extracted
                # fallback: try the existing normalizer
                if not cleaned:
                    cleaned = normalize_agent_result(c)
            except Exception:
                cleaned = c
        else:
            cleaned = c
        rec = dict(r)
        rec["content"] = cleaned
        out.append(rec)
    return {"messages": out}
