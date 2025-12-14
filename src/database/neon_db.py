from __future__ import annotations

import os
from typing import Any, Iterable, Optional, List, Dict

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from psycopg.types.json import Json

from src.models.chat_message_model import ChatMessageModel
from src.models.idea_state_model import IdeaState
from datetime import datetime

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
        stage: Optional[int] = None
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
            }
        else:
            sql = """
            SELECT *
            FROM chat_messages
            WHERE session_id = %(session_id)s
            ORDER BY created_at ASC
            """
            params = {
                "session_id": session_id,
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
    
    # ─────────────────────────────────────────
    # Documents
    # ─────────────────────────────────────────

    def create_document(
        self,
        *,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        title: str = "Untitled",
        icon: Optional[str] = None,
        content: Any = None,
        added_by: str = "user",  # 'user' | 'ai'
    ) -> Dict[str, Any]:
        """
        Insert a new document row.

        'content' is stored as JSONB (BlockNote doc). If None, defaults to [].
        """
        if content is None:
            content = []

        sql = """
        INSERT INTO documents (
            project_id,
            session_id,
            title,
            icon,
            content,
            added_by
        )
        VALUES (
            %(project_id)s,
            %(session_id)s,
            %(title)s,
            %(icon)s,
            %(content)s,
            %(added_by)s
        )
        RETURNING *;
        """

        params = {
            "project_id": project_id,
            "session_id": session_id,
            "title": title,
            "icon": icon,
            "content": Json(content),
            "added_by": added_by,
        }

        row = self.fetch_one(sql, params)
        if row is None:
            raise RuntimeError("Failed to create document")

        return row

    def update_document(
        self,
        document_id: str,
        *,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
        icon: Optional[str] = None,
        content: Any = None,
        added_by: Optional[str] = None,
        is_trashed: Optional[bool] = None,
        trashed_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Partially update a document by id.
        Only non-None fields are updated.
        Also bumps updated_at = NOW().
        """
        fields: Dict[str, Any] = {}
        if project_id is not None:
            fields["project_id"] = project_id
        if session_id is not None:
            fields["session_id"] = session_id
        if title is not None:
            fields["title"] = title
        if icon is not None:
            fields["icon"] = icon
        if content is not None:
            fields["content"] = Json(content)
        if added_by is not None:
            fields["added_by"] = added_by
        if is_trashed is not None:
            fields["is_trashed"] = is_trashed
        if trashed_at is not None:
            fields["trashed_at"] = trashed_at

        if not fields:
            raise ValueError("No fields provided to update_document")

        set_clauses = []
        params: Dict[str, Any] = {"id": document_id}
        for idx, (col, value) in enumerate(fields.items(), start=1):
            key = f"v{idx}"
            set_clauses.append(f"{col} = %({key})s")
            params[key] = value

        # always bump updated_at
        set_clauses.append("updated_at = NOW()")

        sql = f"""
        UPDATE documents
        SET {", ".join(set_clauses)}
        WHERE id = %(id)s
        RETURNING *;
        """

        row = self.fetch_one(sql, params)
        if row is None:
            raise RuntimeError("Document not found or not updated")

        return row
    
    def get_documents_by_session_id(
        self,
        session_id: str,
        *,
        include_trashed: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all documents for a given session_id.

        - Ordered by created_at ASC (oldest → newest)
        - By default excludes trashed documents
        - Matches Drizzle schema: session_id is VARCHAR(128), is_trashed is BOOLEAN
        """
        if include_trashed:
            sql = """
            SELECT *
            FROM documents
            WHERE session_id = %(session_id)s
            ORDER BY created_at ASC
            LIMIT %(limit)s;
            """
            params = {
                "session_id": session_id,
                "limit": limit,
            }
        else:
            sql = """
            SELECT *
            FROM documents
            WHERE session_id = %(session_id)s
              AND is_trashed = FALSE
            ORDER BY created_at ASC
            LIMIT %(limit)s;
            """
            params = {
                "session_id": session_id,
                "limit": limit,
            }

        return self.fetch_all(sql, params)
    
    # ─────────────────────────────────────────
    # Projects
    # ─────────────────────────────────────────

    def create_project(
        self,
        *,
        key: str,
        name: str,
        lead_user_id: str,
        description: Optional[str] = None,
        status: str = "active",  # 'active' | 'inactive' | 'archived'
        team_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Insert a new project (aligned with Drizzle `projects` table).
        """

        # Safety check for enum (recommended)
        if status not in {"active", "inactive", "archived"}:
            raise ValueError(f"Invalid project status: {status}")

        sql = """
        INSERT INTO projects (
            key,
            name,
            description,
            project_status,
            lead_user_id,
            team_ids
        )
        VALUES (
            %(key)s,
            %(name)s,
            %(description)s,
            %(status)s,
            %(lead_user_id)s,
            %(team_ids)s
        )
        RETURNING *;
        """

        params = {
            "key": key,
            "name": name,
            "description": description,
            "status": status,
            "lead_user_id": lead_user_id,
            # postgres uuid[] expects list; default to empty list
            "team_ids": team_ids or [],
        }

        row = self.fetch_one(sql, params)
        if row is None:
            raise RuntimeError("Failed to create project")

        return row


    def update_project(
        self,
        project_id: str,
        *,
        key: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        lead_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Partially update a project by id.
        Only non-None fields are updated.
        Also bumps updated_at = NOW().
        """
        fields: Dict[str, Any] = {}
        if key is not None:
            fields["key"] = key
        if name is not None:
            fields["name"] = name
        if description is not None:
            fields["description"] = description
        if status is not None:
            fields["project_status"] = status
        if lead_user_id is not None:
            fields["lead_user_id"] = lead_user_id

        if not fields:
            raise ValueError("No fields provided to update_project")

        set_clauses = []
        params: Dict[str, Any] = {"id": project_id}
        for idx, (col, value) in enumerate(fields.items(), start=1):
            key_param = f"v{idx}"
            set_clauses.append(f"{col} = %({key_param})s")
            params[key_param] = value

        set_clauses.append("updated_at = NOW()")

        sql = f"""
        UPDATE projects
        SET {", ".join(set_clauses)}
        WHERE id = %(id)s
        RETURNING *;
        """

        row = self.fetch_one(sql, params)
        if row is None:
            raise RuntimeError("Project not found or not updated")

        return row
    
    # ─────────────────────────────────────────
    # Tasks
    # ─────────────────────────────────────────
    
    def create_task(
        self,
        *,
        project_id: str,
        key: str,                         # e.g. "SP-12"
        title: str,
        sprint_week: int = 0,
        tags: Optional[List[str]] = None,
        description: Optional[str] = None,
        ai_description: Optional[str] = None,
        generated_by: str = "ai",         # "user" | "ai"
        status: str = "todo",          # backlog|todo|in_progress|done|cancelled
        priority: str = "Medium",
        assignee_id: Optional[str] = None,
        reporter_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        timeline_days: Optional[float] = None,
        start_date: Optional[datetime] = None,
        due_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Insert a new task matching the tasks table:

        - project_id
        - key
        - title
        - sprint_week
        - tags
        - description
        - ai_description
        - task_generated_by
        - task_status
        - priority
        - assignee_id
        - reporter_id
        - parent_task_id
        - timeline_days
        - start_date
        - due_date
        """
        if tags is None:
            tags = []

        sql = """
        INSERT INTO tasks (
            project_id,
            key,
            title,
            sprint_week,
            tags,
            description,
            ai_description,
            task_generated_by,
            task_status,
            priority,
            assignee_id,
            reporter_id,
            parent_task_id,
            timeline_days,
            start_date,
            due_date
        )
        VALUES (
            %(project_id)s,
            %(key)s,
            %(title)s,
            %(sprint_week)s,
            %(tags)s,
            %(description)s,
            %(ai_description)s,
            %(generated_by)s,
            %(status)s,
            %(priority)s,
            %(assignee_id)s,
            %(reporter_id)s,
            %(parent_task_id)s,
            %(timeline_days)s,
            %(start_date)s,
            %(due_date)s
        )
        RETURNING *;
        """

        params = {
            "project_id": project_id,
            "key": key,
            "title": title,
            "sprint_week": sprint_week,
            "tags": tags,
            "description": description,
            "ai_description": ai_description,
            "generated_by": generated_by,
            "status": status,
            "priority": priority,
            "assignee_id": assignee_id,
            "reporter_id": reporter_id,
            "parent_task_id": parent_task_id,
            "timeline_days": timeline_days,
            "start_date": start_date,
            "due_date": due_date,
        }

        row = self.fetch_one(sql, params)
        if row is None:
            raise RuntimeError("Failed to create task")

        return row

    def update_task(
        self,
        task_id: str,
        *,
        project_id: Optional[str] = None,
        key: Optional[str] = None,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        description: Optional[str] = None,
        ai_description: Optional[str] = None,
        generated_by: Optional[str] = None,   # user|ai
        status: Optional[str] = None,         # backlog|todo|in_progress|done|cancelled
        priority: Optional[str] = None,
        assignee_id: Optional[str] = None,
        reporter_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        timeline_days: Optional[float] = None,
        due_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Partially update a task by id.
        Only non-None fields are updated.
        Also bumps updated_at = NOW().

        Matches tasks columns:
        - project_id, key, title, tags, description, ai_description,
          task_generated_by, task_status, priority, assignee_id,
          reporter_id, parent_task_id, timeline_days, due_date
        """
        fields: Dict[str, Any] = {}
        if project_id is not None:
            fields["project_id"] = project_id
        if key is not None:
            fields["key"] = key
        if title is not None:
            fields["title"] = title
        if tags is not None:
            fields["tags"] = tags
        if description is not None:
            fields["description"] = description
        if ai_description is not None:
            fields["ai_description"] = ai_description
        if generated_by is not None:
            fields["task_generated_by"] = generated_by
        if status is not None:
            fields["task_status"] = status
        if priority is not None:
            fields["priority"] = priority
        if assignee_id is not None:
            fields["assignee_id"] = assignee_id
        if reporter_id is not None:
            fields["reporter_id"] = reporter_id
        if parent_task_id is not None:
            fields["parent_task_id"] = parent_task_id
        if timeline_days is not None:
            fields["timeline_days"] = timeline_days
        if due_date is not None:
            fields["due_date"] = due_date

        if not fields:
            raise ValueError("No fields provided to update_task")

        set_clauses = []
        params: Dict[str, Any] = {"id": task_id}
        for idx, (col, value) in enumerate(fields.items(), start=1):
            key_param = f"v{idx}"
            set_clauses.append(f"{col} = %({key_param})s")
            params[key_param] = value

        # Always bump updated_at
        set_clauses.append("updated_at = NOW()")

        sql = f"""
        UPDATE tasks
        SET {", ".join(set_clauses)}
        WHERE id = %(id)s
        RETURNING *;
        """

        row = self.fetch_one(sql, params)
        if row is None:
            raise RuntimeError("Task not found or not updated")

        return row

    
    def create_task_dependency(
        self,
        *,
        task_id: str,
        depends_on_task_id: str,
    ) -> Dict[str, Any]:
        """
        Insert a new task dependency (task_id depends on depends_on_task_id).

        PK is (task_id, depends_on_task_id). If you want to silently ignore
        duplicates, you can add ON CONFLICT DO NOTHING.
        """
        sql = """
        INSERT INTO task_dependencies (
            task_id,
            depends_on_task_id
        )
        VALUES (
            %(task_id)s,
            %(depends_on_task_id)s
        )
        RETURNING *;
        """

        params = {
            "task_id": task_id,
            "depends_on_task_id": depends_on_task_id,
        }

        row = self.fetch_one(sql, params)
        if row is None:
            raise RuntimeError("Failed to create task_dependency")

        return row

    def update_task_dependency(
        self,
        *,
        task_id: str,
        depends_on_task_id: str,
        new_task_id: Optional[str] = None,
        new_depends_on_task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update a task dependency's keys.
        Useful if you rewire dependency graph.

        WHERE (task_id, depends_on_task_id) = (old values).
        """
        fields: Dict[str, Any] = {}
        if new_task_id is not None:
            fields["task_id"] = new_task_id
        if new_depends_on_task_id is not None:
            fields["depends_on_task_id"] = new_depends_on_task_id

        if not fields:
            raise ValueError("No fields provided to update_task_dependency")

        set_clauses = []
        params: Dict[str, Any] = {
            "old_task_id": task_id,
            "old_depends_on_task_id": depends_on_task_id,
        }

        for idx, (col, value) in enumerate(fields.items(), start=1):
            key_param = f"v{idx}"
            set_clauses.append(f"{col} = %({key_param})s")
            params[key_param] = value

        sql = f"""
        UPDATE task_dependencies
        SET {", ".join(set_clauses)}
        WHERE task_id = %(old_task_id)s
          AND depends_on_task_id = %(old_depends_on_task_id)s
        RETURNING *;
        """

        row = self.fetch_one(sql, params)
        if row is None:
            raise RuntimeError("Task dependency not found or not updated")

        return row
    
    # ─────────────────────────────────────────
    # User management
    # ─────────────────────────────────────────
    
    def get_user(self, clerk_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a user by ID.
        
        Args:
            clerk_id: The clerk ID to fetch
            
        Returns:
            User dictionary if found, None otherwise
        """
        sql = """
        SELECT *
        FROM users
        WHERE clerk_id = %(clerk_id)s;
        """
        
        params = {"clerk_id": clerk_id}
        return self.fetch_one(sql, params)
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get a user by email address.
        
        Args:
            email: The email address to search for
            
        Returns:
            User dictionary if found, None otherwise
        """
        sql = """
        SELECT *
        FROM users
        WHERE email = %(email)s;
        """
        
        params = {"email": email}
        return self.fetch_one(sql, params)
    
    def update_user(
        self,
        user_id: str,
        *,
        clerk_id: Optional[str] = None,
        email: Optional[str] = None,
        name: Optional[str] = None,
        role: Optional[str] = None,          # 'individual' | 'investor' | 'admin'
        description: Optional[str] = None,
        profession: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Partially update a user by id.
        Only non-None fields are updated.
        """
        fields: Dict[str, Any] = {}
        if clerk_id is not None:
            fields["clerk_id"] = clerk_id
        if email is not None:
            fields["email"] = email
        if name is not None:
            fields["name"] = name
        if role is not None:
            fields["role"] = role
        if description is not None:
            fields["description"] = description
        if profession is not None:
            fields["profession"] = profession

        if not fields:
            raise ValueError("No fields provided to update_user")

        set_clauses = []
        params: Dict[str, Any] = {"id": user_id}
        for idx, (col, value) in enumerate(fields.items(), start=1):
            key_param = f"v{idx}"
            set_clauses.append(f"{col} = %({key_param})s")
            params[key_param] = value

        sql = f"""
        UPDATE users
        SET {", ".join(set_clauses)}
        WHERE id = %(id)s
        RETURNING *;
        """

        row = self.fetch_one(sql, params)
        if row is None:
            raise RuntimeError("User not found or not updated")

        return row
    
    def get_or_create_user_by_email(
        self,
        email: str,
        name: Optional[str] = None,
        profession: str = "",
        description: str = "",
        role: str = "individual",
        clerk_id: str = "user_invited",
    ) -> Dict[str, Any]:
        """
        Fetch a user by email, or create one if it doesn't exist.
        
        Args:
            email: Email of the user
            name: Optional name to assign on creation
            profession: User profession (default empty as per schema)
            description: User description (default empty as per schema)
            role: Role to assign ('individual' by default)
            clerk_id: Clerk identifier; defaults to 'user_invited'
        
        Returns:
            A full user row (existing or newly created)
        """

        # 1. Try fetching an existing user
        existing_user = self.get_user_by_email(email)
        if existing_user:
            return existing_user

        # 2. Create a new user since none exists
        sql = """
        INSERT INTO users (
            clerk_id,
            email,
            name,
            role,
            description,
            profession
        )
        VALUES (
            %(clerk_id)s,
            %(email)s,
            %(name)s,
            %(role)s,
            %(description)s,
            %(profession)s
        )
        RETURNING *;
        """

        params = {
            "clerk_id": clerk_id,
            "email": email,
            "name": name,
            "role": role,  # 'individual' default
            "description": description,
            "profession": profession,
        }

        new_user = self.fetch_one(sql, params)
        if not new_user:
            raise RuntimeError("Failed to create user")

        return new_user
    

    # ─────────────────────────────────────────
    # Narrative Sections
    # ─────────────────────────────────────────

    def create_narrative_section(
        self,
        *,
        project_id: str,
        category: str,     # narrative | product | engineering | ...
        name: str,
        section_type: str = "text",  # text | files
        content: str = "",
        position: int = 0,
    ) -> Dict[str, Any]:
        """
        Insert a narrative section.
        """
        sql = """
        INSERT INTO narrative_sections (
            project_id,
            category,
            name,
            type,
            content,
            position,
            created_at,
            updated_at
        )
        VALUES (
            %(project_id)s,
            %(category)s,
            %(name)s,
            %(type)s,
            %(content)s,
            %(position)s,
            NOW(),
            NOW()
        )
        RETURNING *;
        """

        params = {
            "project_id": project_id,
            "category": category,
            "name": name,
            "type": section_type,
            "content": content,
            "position": position,
        }

        row = self.fetch_one(sql, params)
        if row is None:
            raise RuntimeError("Failed to create narrative section")

        return row
    
