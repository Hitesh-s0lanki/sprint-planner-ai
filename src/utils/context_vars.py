"""
Context variables for storing db and session_id globally.
These can be accessed from anywhere in the application without passing them as parameters.
"""
from contextvars import ContextVar
from typing import Optional, Any

# Context variables for db and session_id
db_context: ContextVar[Optional[Any]] = ContextVar('db_context', default=None)
session_id_context: ContextVar[Optional[str]] = ContextVar('session_id_context', default=None)


def get_db():
    """Get the current db instance from context."""
    return db_context.get()


def get_session_id():
    """Get the current session_id from context."""
    return session_id_context.get()


def set_db(db_instance: Any):
    """Set the db instance in context."""
    db_context.set(db_instance)


def set_session_id(session_id: str):
    """Set the session_id in context."""
    session_id_context.set(session_id)
