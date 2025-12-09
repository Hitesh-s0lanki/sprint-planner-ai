from __future__ import annotations

import os
from typing import Any, Iterable, Optional, List, Dict

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from psycopg.types.json import Json

from src.models.chat_message_model import ChatMessageModel
from src.models.idea_state_model import IdeaState

class NeonDB:
    """
    Simple Neon Postgres client using psycopg3 connection pool.

    - Uses DATABASE_URL from env (Neon connection string).
    - Closes idle connections after ~4 minutes (max_idle=240),
      so Neon can auto-hibernate after 5 min of inactivity.
    - Provides helpers for chat_messages table.
    """

    def __init__(
        self,
        db_url: Optional[str] = None,
        min_size: int = 1,
        max_size: int = 5,
        acquire_timeout: float = 10.0,
        max_idle_seconds: float = 240.0,  # < 5 min to help Neon hibernate
    ) -> None:
        self._db_url = db_url or os.getenv("DATABASE_URL")
        if not self._db_url:
            raise ValueError(
                "DATABASE_URL is not set. "
                "Copy the connection string from Neon and put it in the env."
            )

        self._pool = ConnectionPool(
            conninfo=self._db_url,
            min_size=min_size,
            max_size=max_size,
            timeout=acquire_timeout,
            max_idle=max_idle_seconds,
            max_lifetime=3600.0,  # recycle connections every hour
            open=True,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )

    @property
    def pool(self) -> ConnectionPool:
        return self._pool

    # ─────────────────────────────────────────
    # Generic helpers
    # ─────────────────────────────────────────

    def execute(
        self,
        sql: str,
        params: Optional[Iterable[Any]] = None,
    ) -> None:
        """
        Execute a statement that doesn't return rows (INSERT/UPDATE/DELETE, DDL).
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())

    def fetch_one(
        self,
        sql: str,
        params: Optional[Iterable[Any]] = None,
    ) -> Optional[dict]:
        """
        Execute a SELECT and return a single row as a dict, or None.
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                row = cur.fetchone()
                return row if row is not None else None

    def fetch_all(
        self,
        sql: str,
        params: Optional[Iterable[Any]] = None,
    ) -> List[dict]:
        """
        Execute a SELECT and return all rows as a list of dicts.
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                rows = cur.fetchall()
                return list(rows)

    def close(self) -> None:
        """
        Close the pool and all connections (e.g. on app shutdown).
        """
        if self._pool is not None:
            self._pool.close()

    def init_chat_schema(self) -> None:
        """
        Create the chat_messages table if it doesn't exist.

        Fields:
        - chat_id: UUID PK
        - session_id: text (required)
        - user_id: text (optional)
        - role: text
        - formatted_output: text
        - content: text
        - metadata: jsonb
        - stage: int (1-9)
        - created_at: timestamp
        - updated_at: timestamp
        """
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS chat_messages (
            chat_id UUID PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_id TEXT NULL,
            role TEXT NOT NULL,
            formatted_output TEXT NULL,
            content TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            stage INT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT check_stage_range CHECK (stage >= 1 AND stage <= 9)
        );
        """
        self.execute(create_table_sql)
        
        # Add created_at and updated_at columns if they don't exist (for existing tables)
        try:
            alter_table_sql = """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'chat_messages' AND column_name = 'created_at'
                ) THEN
                    ALTER TABLE chat_messages 
                    ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
                END IF;
                
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'chat_messages' AND column_name = 'updated_at'
                ) THEN
                    ALTER TABLE chat_messages 
                    ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
                END IF;
            END $$;
            """
            self.execute(alter_table_sql)
        except Exception as e:
            # Ignore errors if columns already exist or table doesn't exist yet
            pass

    def _row_to_chat_message(self, row: dict) -> ChatMessageModel:
        """
        Internal helper: convert a DB row dict → ChatMessage Pydantic object.
        """
        return ChatMessageModel(
            chat_id=row["chat_id"],
            session_id=row["session_id"],
            user_id=row.get("user_id"),
            role=row["role"],
            formatted_output=row.get("formatted_output"),
            content=row["content"],
            metadata=row.get("metadata") or {},
            stage=row["stage"],
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def create_chat_message(self, msg: ChatMessageModel) -> ChatMessageModel:
        sql = """
        INSERT INTO chat_messages (
            chat_id,
            session_id,
            user_id,
            role,
            formatted_output,
            content,
            metadata,
            stage,
            created_at,
            updated_at
        )
        VALUES (
            %(chat_id)s,
            %(session_id)s,
            %(user_id)s,
            %(role)s,
            %(formatted_output)s,
            %(content)s,
            %(metadata)s,
            %(stage)s,
            NOW(),
            NOW()
        )
        RETURNING *;
        """

        params = {
            "chat_id": msg.chat_id,
            "session_id": msg.session_id,
            "user_id": msg.user_id,
            "role": msg.role,
            "formatted_output": msg.formatted_output,
            "content": msg.content,
            # 👇 THIS is the important change
            "metadata": Json(msg.metadata or {}),
            "stage": msg.stage,
        }

        row = self.fetch_one(sql, params)
        if row is None:
            raise RuntimeError("Failed to insert chat message")

        # If you're using ChatMessageModel as the Pydantic class:
        return ChatMessageModel(**row)

    def get_chat_messages_by_session(
        self,
        session_id: str,
        stage: Optional[int] = None,
        limit: int = 100,
    ) -> List[ChatMessageModel]:
        """
        Fetch chat messages for a given session_id (optionally filtered by stage).
        Ordered by created_at timestamp to ensure chronological order.
        """
        if stage is not None:
            sql = """
            SELECT *
            FROM chat_messages
            WHERE session_id = %(session_id)s
              AND stage = %(stage)s
            ORDER BY created_at ASC
            LIMIT %(limit)s;
            """
            params = {
                "session_id": session_id,
                "stage": stage,
                "limit": limit,
            }
        else:
            sql = """
            SELECT *
            FROM chat_messages
            WHERE session_id = %(session_id)s
            ORDER BY created_at ASC
            LIMIT %(limit)s;
            """
            params = {
                "session_id": session_id,
                "limit": limit,
            }

        rows = self.fetch_all(sql, params)
        return [self._row_to_chat_message(r) for r in rows]


    def init_idea_state_schema(self) -> None:
        """
        Create the idea_state table if it doesn't exist.

        - session_id: primary key (one idea state per chat session)
        - data: JSONB with all idea fields (flattened, no "stage" keys)
        - created_at / updated_at: timestamps
        """
        sql = """
        CREATE TABLE IF NOT EXISTS idea_state (
            session_id TEXT PRIMARY KEY,
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
        self.execute(sql)
        
    def upsert_idea_state(self, state: IdeaState) -> IdeaState:
        """
        Insert or update the full idea state for a session_id.
        Overwrites the 'data' JSON with the given state.
        """
        payload = state.model_dump(exclude={"session_id"}, exclude_none=True)

        sql = """
        INSERT INTO idea_state (session_id, data)
        VALUES (%(session_id)s, %(data)s)
        ON CONFLICT (session_id) DO UPDATE
        SET data = EXCLUDED.data,
            updated_at = NOW()
        RETURNING session_id, data;
        """

        params = {
            "session_id": state.session_id,
            "data": Json(payload),
        }

        row = self.fetch_one(sql, params)
        if row is None:
            raise RuntimeError("Failed to upsert idea_state")

        data = row["data"] or {}
        return IdeaState(session_id=row["session_id"], **data)
    
    def get_idea_state(self, session_id: str) -> Optional[IdeaState]:
        """
        Fetch the idea state for a session_id.
        Returns None if not found.
        """
        sql = """
        SELECT session_id, data
        FROM idea_state
        WHERE session_id = %(session_id)s;
        """

        row = self.fetch_one(sql, {"session_id": session_id})
        if row is None:
            return None

        data = row["data"] or {}
        return IdeaState(session_id=row["session_id"], **data)

    def update_idea_state_fields(
        self,
        session_id: str,
        fields: Dict[str, Any],
    ) -> IdeaState:
        """
        Partially update idea_state for a session_id.

        Example 'fields':
        {
            "idea_title": "New title",
            "primary_competitors": ["X", "Y"],
            "preferred_tech_stack": {
                "frontend": "Next.js",
                "backend": "FastAPI"
            }
        }
        """
        # Get existing or create empty state
        current = self.get_idea_state(session_id)
        if current is None:
            current = IdeaState(session_id=session_id)

        # Merge in new fields
        updated = current.model_copy(update=fields, deep=True)

        # Save back
        return self.upsert_idea_state(updated)

