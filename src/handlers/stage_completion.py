import uuid
import logging
import threading
from typing import List, Dict, Any, Tuple, Optional, AsyncGenerator

from datetime import datetime, timedelta, time, timezone

from src.states.global_idea_state import GlobalIdeaState
from src.states.agile_project_manager_agent_state import SprintWeek
from src.database.neon_db import NeonDB
from src.models.user_model import User
from src.models.chat_transfer_model import Event
from src.utils.utils import safe_uuid_or_none

from src.agents.sprint_planner_agent import SprintPlannerAgent
from src.agents.narrative_agent import NarrativeSectionAgent

logger = logging.getLogger(__name__)

class StageCompletion:
    """
    Handles the completion stage of the sprint planning workflow.
    Orchestrates project creation, document updates, team sync, task generation, and narrative sections generation.
    """

    def __init__(
        self,
        db: NeonDB,
        sprint_planner_agent: SprintPlannerAgent,
        narrative_agent: NarrativeSectionAgent,
    ):
        self.db = db
        self.sprint_planner_agent = sprint_planner_agent
        self.narrative_agent = narrative_agent

        # populated by load_and_sync_team_members()
        self.members: List[User] = []

    # ─────────────────────────────────────────
    # Users
    # ─────────────────────────────────────────

    def get_user_from_db(self, user_id: str) -> Optional[User]:
        """
        Get a user from the database by clerk_id.
        """
        user_dict = self.db.get_user(clerk_id=user_id)
        if user_dict is None:
            return None

        if "id" in user_dict and user_dict["id"] is not None:
            user_dict["id"] = str(user_dict["id"])

        return User(**user_dict)

    # ─────────────────────────────────────────
    # Projects
    # ─────────────────────────────────────────

    def create_project(
        self,
        idea_title: str,
        idea_summary_short: Optional[str],
        lead_user_id: str,
        team_ids: Optional[List[str]] = None,
    ) -> str:
        """
        Create a new project row. lead_user_id must be users.id (uuid).
        """
        project_key = f"PROJ-{str(uuid.uuid4())[:8].upper()}"

        try:
            project = self.db.create_project(
                key=project_key,
                name=idea_title,
                description=idea_summary_short,
                status="active",
                lead_user_id=lead_user_id,
                team_ids=team_ids,
            )

            project_id = project["id"]
            # Ensure project_id is a string (convert UUID to string if needed)
            project_id_str = str(project_id) if project_id else None
            logger.info(f"Created project with ID: {project_id_str}, key: {project_key}")
            return project_id_str

        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            raise

    # ─────────────────────────────────────────
    # Documents
    # ─────────────────────────────────────────

    def get_all_documents_by_session_id(self, session_id: str) -> List[Dict[str, Any]]:
        try:
            documents = self.db.get_documents_by_session_id(
                session_id=session_id,
                include_trashed=False,
            )
            logger.info(f"Retrieved {len(documents)} documents for session_id: {session_id}")
            return documents
        except Exception as e:
            logger.error(f"Failed to get documents for session_id {session_id}: {e}")
            raise

    def update_documents_project_id(
        self,
        documents: List[Dict[str, Any]],
        project_id: str,
    ) -> List[Dict[str, Any]]:
        updated_documents = []

        for doc in documents:
            document_id = doc.get("id")
            if not document_id:
                logger.warning(f"Skipping document without ID: {doc}")
                continue

            try:
                updated_doc = self.db.update_document(
                    document_id=document_id,
                    project_id=project_id,
                )
                updated_documents.append(updated_doc)
            except Exception as e:
                logger.error(f"Failed to update document {document_id}: {e}")
                continue

        logger.info(f"Updated {len(updated_documents)} documents with project_id: {project_id}")
        return updated_documents

    # ─────────────────────────────────────────
    # Dates
    # ─────────────────────────────────────────

    def _compute_week_start_date(
        self,
        *,
        base_date: datetime,
        sprint_week: int,
        today_completed: bool = False,
    ) -> datetime:
        """
        Week start at 00:00 UTC.
        Week 1 starts today (or tomorrow if today_completed=True).
        """
        if base_date.tzinfo is None:
            base_date = base_date.replace(tzinfo=timezone.utc)

        anchor_date = base_date.date()
        if today_completed:
            anchor_date = anchor_date + timedelta(days=1)

        week_start_date = anchor_date + timedelta(days=(sprint_week - 1) * 7)
        return datetime.combine(week_start_date, time.min, tzinfo=timezone.utc)

    # ─────────────────────────────────────────
    # Tasks
    # ─────────────────────────────────────────

    def save_sprint_weeks_to_db(
        self,
        sprint_weeks: List["SprintWeek"],
        project_id: str,
        reporter_id: Optional[str] = None,
        *,
        base_date: Optional[datetime] = None,
        today_completed: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Save a full sprint (List[SprintWeek]) to DB.

        - timeline_days -> due_date = week_start + timeline_days
        - start_date = week_start
        - ai_description = SprintTask.description
        - description left None
        - creates sub_tasks as child tasks (parent_task_id = parent id)
        - guards invalid UUIDs for assignee_id / reporter_id
        """
        created_tasks: List[Dict[str, Any]] = []

        if base_date is None:
            base_date = datetime.now(timezone.utc)
        elif base_date.tzinfo is None:
            base_date = base_date.replace(tzinfo=timezone.utc)

        safe_reporter_id = safe_uuid_or_none(reporter_id)

        # Generate unique prefix from project_id (first 8 chars of UUID)
        project_prefix = project_id[:8].upper() if len(project_id) >= 8 else project_id.upper()
        task_counter = 0

        for sprint_week in sprint_weeks:
            week_number = sprint_week.week
            week_start_dt = self._compute_week_start_date(
                base_date=base_date,
                sprint_week=week_number,
                today_completed=today_completed,
            )

            for task in sprint_week.tasks:
                task_counter += 1
                # Include project prefix to ensure uniqueness across projects
                parent_key = f"{project_prefix}-SP-{task_counter}"

                safe_assignee_id = safe_uuid_or_none(getattr(task, "assigneeId", None))

                duration_days = getattr(task, "timeline_days", 0.0) or 0.0
                due_date = week_start_dt + timedelta(days=float(duration_days))

                try:
                    parent_row = self.db.create_task(
                        project_id=project_id,
                        key=parent_key,
                        title=task.title,
                        sprint_week=week_number,
                        tags=[],
                        description=None,
                        ai_description=task.description,
                        generated_by="ai",
                        status="todo",
                        priority=task.priority,
                        assignee_id=safe_assignee_id,
                        reporter_id=safe_reporter_id,
                        parent_task_id=None,
                        timeline_days=float(duration_days),
                        start_date=week_start_dt,
                        due_date=due_date,
                    )
                    created_tasks.append(parent_row)
                except Exception as e:
                    logger.error(
                        f"Failed to create task '{task.title}' for sprint week {week_number}: {e}"
                    )
                    continue

                parent_id = safe_uuid_or_none(str(parent_row.get("id")))

                sub_tasks = getattr(task, "sub_tasks", None) or []
                for sub_title in sub_tasks:
                    if not sub_title or not str(sub_title).strip():
                        continue

                    task_counter += 1
                    # Include project prefix to ensure uniqueness across projects
                    sub_key = f"{project_prefix}-SP-{task_counter}"

                    try:
                        child_row = self.db.create_task(
                            project_id=project_id,
                            key=sub_key,
                            title=str(sub_title).strip(),
                            sprint_week=week_number,
                            tags=["subtask"],
                            description=None,
                            ai_description=f"Subtask of '{task.title}': {str(sub_title).strip()}",
                            generated_by="ai",
                            status="todo",
                            priority=task.priority,
                            assignee_id=safe_assignee_id,
                            reporter_id=safe_reporter_id,
                            parent_task_id=parent_id,
                            timeline_days=float(duration_days),
                            start_date=week_start_dt,
                            due_date=due_date,
                        )
                        created_tasks.append(child_row)
                    except Exception as e:
                        logger.error(
                            f"Failed to create subtask '{sub_title}' for parent '{task.title}' "
                            f"(week {week_number}): {e}"
                        )
                        continue

        logger.info(
            f"Created {len(created_tasks)} tasks (including subtasks) "
            f"for project {project_id} starting from {base_date.date()}"
        )
        return created_tasks

    # ─────────────────────────────────────────
    # Team sync
    # ─────────────────────────────────────────

    def load_and_sync_team_members(
        self,
        global_idea_state: GlobalIdeaState,
    ) -> Tuple[List[User], List[Dict[str, Any]]]:
        """
        Load team members from global_idea_state.team, ensure they exist in DB (create if needed),
        return:
          - members: list of User objects from DB
          - updated_team: enriched team entries (preserve keys, add DB user id)
        """
        self.members = []

        team_list = getattr(global_idea_state, "team", None)
        if not team_list:
            logger.warning("No team found in global_idea_state.team")
            return [], []

        updated_team: List[Dict[str, Any]] = []

        for member in team_list:
            if hasattr(member, "dict"):
                member_data: Dict[str, Any] = member.dict()
            else:
                member_data = dict(member)

            email = member_data.get("email")
            name = member_data.get("name")
            profession = member_data.get("profession", "")
            description = member_data.get("description", "")

            if not email:
                logger.warning(f"Skipping team member without email: {member_data}")
                updated_team.append(member_data)
                continue

            try:
                user_dict = self.db.get_or_create_user_by_email(
                    email=email,
                    name=name,
                    profession=profession,
                    description=description,
                    role="individual",
                    clerk_id="user_invited",
                )

                if "id" in user_dict and user_dict["id"]:
                    user_dict["id"] = str(user_dict["id"])

                user_obj = User(**user_dict)
                self.members.append(user_obj)

                member_data["id"] = user_obj.id
                member_data.setdefault("email", user_obj.email)
                member_data.setdefault("name", user_obj.name)

                updated_team.append(member_data)

            except Exception as e:
                logger.error(f"Failed to sync team member {email}: {e}")
                updated_team.append(member_data)
                continue

        logger.info(f"Loaded and synced {len(self.members)} team members")
        return self.members, updated_team

    # ─────────────────────────────────────────
    # Narrative sections
    # ─────────────────────────────────────────

    @staticmethod
    def _default_narrative_plan() -> Dict[str, List[str]]:
        """
        Default plan (category -> ordered section names).
        Adjust as needed to match your UI.
        """
        return {
            "narrative": [
                "Executive Summary",
                "PR-Style Launch",
                "Customer FAQ",
                "Problem Statement",
                "Solution Overview",
                "Success Metrics",
            ],
            "product": [
                "Product Vision",
                "User Personas",
                "Customer Problems",
                "Feature Breakdown (MVP)",
                "Success Criteria",
            ],
            "engineering": [
                "Tech Stack",
                "System Architecture",
                "Testing Strategy",
            ],
            "administrative": [
                "Company Structure",
                "Operational Rituals",
            ],
            "people_hr": [
                "Hiring Plan",
                "Culture & Principles",
            ],
            "gtm": [
                "Go-to-Market Strategy",
                "Positioning & Messaging",
            ],
            "funding": [
                "Investment Narrative",
            ],
            "tools": [
                "Tool Stack Overview",
                "Build vs Buy Decisions",
            ],
        }

    def generate_full_narrative_sections(
        self,
        global_idea_state: GlobalIdeaState,
        *,
        instruction: Optional[str] = None,
        plan: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        Uses NarrativeSectionAgent.generate_full_narrative(...) to generate all sections.
        Returns dict: { "sections": [...], "messages": [...] }
        """
        if plan is None:
            plan = self._default_narrative_plan()

        return self.narrative_agent.generate_full_narrative(
            idea_context=str(global_idea_state),
            plan=plan,
            instruction=instruction,
        )

    def save_project_sections_to_db(
        self,
        project_id: str,
        sections: Dict[str, Any],
    ) -> bool:
        """
        Save narrative sections to the database.
        
        Args:
            project_id: The project ID to associate sections with
            sections: Dict with "sections" key containing list of section dicts.
                     Each section dict should have: category, name, type, content, position
        
        Returns:
            True if at least one section was saved successfully, False otherwise
        """
        logger.info(f"Saving project sections for project {project_id}")
        
        sections_list = sections.get("sections", [])
        if not sections_list:
            logger.warning(f"No sections found in sections dict for project {project_id}")
            return False
        
        saved_count = 0
        failed_count = 0
        
        for section in sections_list:
            category = section.get("category")
            name = section.get("name")
            section_type = section.get("type", "text")
            content = section.get("content", "")
            position = section.get("position", 0)
            
            if not category or not name:
                logger.warning(
                    f"Skipping section with missing category or name: {section}"
                )
                failed_count += 1
                continue
            
            try:
                self.db.create_narrative_section(
                    project_id=project_id,
                    category=category,
                    name=name,
                    section_type=section_type,
                    content=content,
                    position=position,
                )
                saved_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to save section '{name}' (category: {category}) "
                    f"for project {project_id}: {e}"
                )
                failed_count += 1
                continue
        
        if saved_count > 0:
            logger.info(
                f"Successfully saved {saved_count} sections for project {project_id}. "
                f"Failed: {failed_count}"
            )
            return True
        else:
            logger.error(
                f"Failed to save any sections for project {project_id}. "
                f"All {failed_count} sections failed."
            )
            return False

    # ─────────────────────────────────────────
    # Background Jobs
    # ─────────────────────────────────────────

    def _generate_and_save_narrative_sections_background(
        self,
        project_id: str,
        global_idea_state: GlobalIdeaState,
        instruction: str = "Make sections practical, MVP-focused, and execution-ready. Use research_tool only when needed for public facts.",
        timeout_minutes: int = 30,
    ) -> None:
        """
        Background job to generate and save narrative sections.
        Runs in a separate thread to avoid blocking the main flow.
        
        Processes categories sequentially:
        1. Generate all sections for category 1
        2. Save category 1 sections to DB immediately
        3. Generate all sections for category 2
        4. Save category 2 sections to DB immediately
        5. And so on...
        
        This approach ensures that if the process fails, at least some categories are saved.
        
        Args:
            project_id: Project ID to associate sections with
            global_idea_state: The global idea state (immutable, safe for threading)
            instruction: Optional instruction for narrative generation
            timeout_minutes: Maximum time to spend generating sections (default: 30 minutes)
        
        Note: global_idea_state is a Pydantic BaseModel (immutable) and is safe to read
        from multiple threads. The state is only read from (converted to string) and never mutated.
        """
        import time as time_module
        start_time = time_module.time()
        timeout_seconds = timeout_minutes * 60
        
        try:
            # Get the narrative plan (categories and their sections)
            plan = self._default_narrative_plan()
            idea_context = str(global_idea_state)
            
            total_categories = len(plan)
            total_sections = sum(len(sections) for sections in plan.values())
            
            logger.info(
                f"Background job started: Generating narrative sections for project {project_id} "
                f"({total_categories} categories, {total_sections} total sections, timeout: {timeout_minutes} minutes)"
            )
            
            # Track overall progress
            total_saved = 0
            total_failed = 0
            category_position = 0
            
            # Process each category sequentially
            for category_idx, (category, section_names) in enumerate(plan.items(), start=1):
                # Check timeout
                elapsed_time = time_module.time() - start_time
                if elapsed_time > timeout_seconds:
                    logger.warning(
                        f"Background job timeout reached ({timeout_minutes} minutes) "
                        f"for project {project_id}. Stopping at category {category} "
                        f"({category_idx}/{total_categories})."
                    )
                    break
                
                logger.info(
                    f"Processing category {category_idx}/{total_categories}: '{category}' "
                    f"({len(section_names)} sections) for project {project_id}"
                )
                
                try:
                    # Step 1: Generate all sections for this category
                    category_result = self.narrative_agent.generate_category_sections(
                        idea_context=idea_context,
                        category=category,
                        section_names=section_names,
                        instruction=instruction,
                        section_type="text",
                        start_position=category_position,
                    )
                    
                    category_sections = category_result.get("sections", [])
                    category_position += len(section_names)
                    
                    if not category_sections:
                        logger.warning(
                            f"No sections generated for category '{category}' "
                            f"in project {project_id}"
                        )
                        total_failed += len(section_names)
                        continue
                    
                    logger.info(
                        f"Generated {len(category_sections)}/{len(section_names)} sections "
                        f"for category '{category}' in project {project_id}"
                    )
                    
                    # Step 2: Save this category's sections to DB immediately
                    sections_dict = {"sections": category_sections}
                    saved_count, failed_count = self._save_category_sections_to_db(
                        project_id=project_id,
                        sections=sections_dict,
                        category=category,
                    )
                    
                    total_saved += saved_count
                    total_failed += failed_count
                    
                    if saved_count > 0:
                        logger.info(
                            f"Successfully saved {saved_count} sections for category '{category}' "
                            f"in project {project_id}"
                        )
                    
                    # Small delay between categories to prevent overwhelming the system
                    if category_idx < total_categories:
                        time_module.sleep(1.0)  # 1 second between categories
                        
                except Exception as e:
                    logger.error(
                        f"Error processing category '{category}' for project {project_id}: {e}",
                        exc_info=True
                    )
                    total_failed += len(section_names)
                    # Continue with next category instead of failing completely
                    continue
            
            total_time = time_module.time() - start_time
            logger.info(
                f"Background job completed for project {project_id}: "
                f"Saved {total_saved}/{total_sections} sections "
                f"({total_failed} failed) in {total_time:.1f}s"
            )
                
        except Exception as e:
            elapsed_time = time_module.time() - start_time
            logger.error(
                f"Background job error: Critical error during narrative sections generation "
                f"for project {project_id} (elapsed: {elapsed_time:.1f}s): {e}",
                exc_info=True
            )
            # Don't re-raise - this is a background job and we don't want to crash the main thread
    
    def _save_category_sections_to_db(
        self,
        project_id: str,
        sections: Dict[str, Any],
        category: str,
    ) -> Tuple[int, int]:
        """
        Save narrative sections for a specific category to the database.
        
        Args:
            project_id: The project ID to associate sections with
            sections: Dict with "sections" key containing list of section dicts
            category: The category name (for logging)
        
        Returns:
            Tuple of (saved_count, failed_count)
        """
        sections_list = sections.get("sections", [])
        if not sections_list:
            logger.warning(
                f"No sections found for category '{category}' in project {project_id}"
            )
            return (0, 0)
        
        saved_count = 0
        failed_count = 0
        
        for section in sections_list:
            # Ensure category matches (safety check)
            section_category = section.get("category")
            if section_category != category:
                logger.warning(
                    f"Section category mismatch: expected '{category}', got '{section_category}'. "
                    f"Skipping section '{section.get('name')}'"
                )
                failed_count += 1
                continue
            
            name = section.get("name")
            section_type = section.get("type", "text")
            content = section.get("content", "")
            position = section.get("position", 0)
            
            if not name:
                logger.warning(
                    f"Skipping section with missing name in category '{category}': {section}"
                )
                failed_count += 1
                continue
            
            try:
                self.db.create_narrative_section(
                    project_id=project_id,
                    category=category,
                    name=name,
                    section_type=section_type,
                    content=content,
                    position=position,
                )
                saved_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to save section '{name}' (category: {category}) "
                    f"for project {project_id}: {e}"
                )
                failed_count += 1
                continue
        
        return (saved_count, failed_count)

    # ─────────────────────────────────────────
    # Orchestrator
    # ─────────────────────────────────────────

    async def complete_stage(
        self,
        global_idea_state: GlobalIdeaState,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[Event, None]:
        """
        Complete the stage and yield events as they occur.
        
        Args:
            global_idea_state: The global idea state
            session_id: Session identifier
            user_id: Optional user ID (clerk_id). If not provided, will try to get from user_preferences or email.
        
        Yields:
            Event objects for each step of the completion process
        """
        results = {
            "project_id": None,
            "documents_updated": 0,
            "tasks_created": 0,
            "narrative_sections_generated": 0,
            "sections_saved": False,
            "errors": [],
        }

        try:
            # Step 0: Fetch lead user - try multiple sources for user_id
            resolved_user_id = None
            
            # Priority 1: Use provided user_id parameter
            if user_id:
                resolved_user_id = user_id
                logger.info(f"Using provided user_id: {resolved_user_id}")
            # Priority 2: Try user_preferences.user_id
            elif global_idea_state.user_preferences and global_idea_state.user_preferences.user_id:
                resolved_user_id = global_idea_state.user_preferences.user_id
                logger.info(f"Using user_id from user_preferences: {resolved_user_id}")
            # Priority 3: Try to get/create user from email
            lead_user = None
            if not resolved_user_id and global_idea_state.user_preferences and global_idea_state.user_preferences.user_email:
                logger.info(f"Attempting to get/create user from email: {global_idea_state.user_preferences.user_email}")
                try:
                    user_dict = self.db.get_or_create_user_by_email(
                        email=global_idea_state.user_preferences.user_email,
                        name=global_idea_state.user_preferences.user_name,
                        clerk_id=global_idea_state.user_preferences.user_id or "user_invited",
                    )
                    # Get the clerk_id from the user dict (might be the one we passed or existing)
                    resolved_user_id = user_dict.get("clerk_id")
                    if resolved_user_id:
                        logger.info(f"Resolved user_id from email: {resolved_user_id}")
                        # Convert user_dict to User object directly since we just got/created it
                        if "id" in user_dict and user_dict["id"] is not None:
                            user_dict["id"] = str(user_dict["id"])
                        lead_user = User(**user_dict)
                except Exception as e:
                    logger.warning(f"Failed to get/create user from email: {e}")
            
            # If we still don't have a user_id, raise a helpful error
            if not resolved_user_id:
                error_msg = (
                    "user_id is required but not found. Please provide one of:\n"
                    "- user_id parameter when calling complete_stage\n"
                    "- user_preferences.user_id in global_idea_state\n"
                    "- user_preferences.user_email in global_idea_state (will attempt to create/get user)"
                )
                logger.error(error_msg)
                yield Event(
                    event_type="error",
                    event_status="failed",
                    event_data={"error": error_msg}
                )
                raise ValueError(error_msg)

            # Fetch the user from database if we don't already have it
            if not lead_user:
                lead_user = self.get_user_from_db(user_id=resolved_user_id)
                if not lead_user:
                    error_msg = f"Lead user not found in DB with clerk_id: {resolved_user_id}"
                    logger.error(error_msg)
                    yield Event(
                        event_type="error",
                        event_status="failed",
                        event_data={"error": error_msg}
                    )
                    raise ValueError(error_msg)

            # IMPORTANT: use users.id (uuid) for project lead_user_id and reporter_id
            lead_user_db_id = safe_uuid_or_none(lead_user.id)
            if not lead_user_db_id:
                raise ValueError("Lead user's DB id is invalid")
            
            # Step 1: Load & sync team members (needed before creating project)
            yield Event(event_type="team_members_synced", event_status="started")
            members, updated_team = self.load_and_sync_team_members(global_idea_state)
            logger.info(f"Team members synced: {len(members)}")

            # Update global_idea_state.team (preserve other keys)
            # Note: This is safe because global_idea_state is passed by value (converted to string)
            # and we're working with a local copy in this method
            if updated_team:
                global_idea_state.team = updated_team
            yield Event(event_type="team_members_synced", event_status="completed")

            # Step 2: Create Project (requires team members)
            if not global_idea_state.idea_title:
                raise ValueError("idea_title is required to create a project")

            yield Event(event_type="project_created", event_status="started")
            project_id = self.create_project(
                idea_title=global_idea_state.idea_title,
                idea_summary_short=global_idea_state.idea_summary_short,
                lead_user_id=lead_user_db_id,
                team_ids=[member.id for member in members],
            )
            results["project_id"] = project_id
            yield Event(event_type="project_created", event_status="completed")

            # Step 3: Get all documents by session_id
            documents = self.get_all_documents_by_session_id(session_id)

            # Step 4: Update documents with project_id (requires project_id)
            if documents:
                yield Event(event_type="sources_updated", event_status="started")
                updated_documents = self.update_documents_project_id(
                    documents=documents,
                    project_id=project_id,
                )
                results["documents_updated"] = len(updated_documents)
                yield Event(event_type="sources_updated", event_status="completed")

            # Step 5: Generate full 4-week sprint
            yield Event(event_type="sprint_plan_generated", event_status="started")
            sprint_state = self.sprint_planner_agent.generate_all_weeks_sprint(
                idea_context=str(global_idea_state)
            )

            # Step 6: Save sprint tasks with dates (requires sprint plan and project_id)
            created_tasks = self.save_sprint_weeks_to_db(
                sprint_weeks=sprint_state.sprints,
                project_id=project_id,
                reporter_id=lead_user_db_id,
                base_date=datetime.now(timezone.utc),
                today_completed=False,
            )
            results["tasks_created"] = len(created_tasks)
            yield Event(event_type="sprint_plan_generated", event_status="completed")

            # Step 7: Start narrative sections generation in background (non-blocking)
            # This can take a long time, so we run it in a separate thread and don't wait for it
            yield Event(event_type="narrative_sections_started", event_status="started")
            narrative_thread = threading.Thread(
                target=self._generate_and_save_narrative_sections_background,
                args=(
                    project_id,
                    global_idea_state,
                    "Make sections practical, MVP-focused, and execution-ready. Use research_tool only when needed for public facts.",
                ),
                daemon=True,  # Thread will terminate when main program exits
                name=f"narrative-generation-{project_id}",
            )
            narrative_thread.start()
            logger.info(f"Started background job for narrative sections generation (project {project_id})")
            
            # Update results to indicate job was started (not completed)
            results["narrative_sections_generated"] = 0  # Will be updated by background job
            results["sections_saved"] = False  # Will be updated by background job
            results["narrative_job_started"] = True
            # Note: We don't yield "completed" here because narrative generation runs in background
            # The "started" event indicates the background job has been initiated

            logger.info(f"Stage completion successful for project {project_id} (narrative generation running in background)")

            # Final completion event - ensure project_id is a string
            project_id_str = str(project_id) if project_id else None
            yield Event(event_type="completed", event_status="completed", project_id=project_id_str)

        except Exception as e:
            error_msg = f"Error during stage completion: {str(e)}"
            logger.error(error_msg, exc_info=True)
            results["errors"].append(error_msg)
            raise
