import uuid
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from src.states.global_idea_state import GlobalIdeaState
from src.states.agile_project_manager_agent_state import SprintTask, SprintPlanningState
from src.database.neon_db import NeonDB
from src.agents.sprint_planner_agent import SprintPlannerAgent

logger = logging.getLogger(__name__)


class StageCompletion:
    """
    Handles the completion stage of the sprint planning workflow.
    Orchestrates project creation, document updates, task generation, and narrative creation.
    """
    
    def __init__(self, db: NeonDB, sprint_planner_agent: SprintPlannerAgent):
        """
        Initialize StageCompletion with a database instance.
        
        Args:
            db: NeonDB instance for database operations
        """
        self.db = db
        self.sprint_planner_agent = sprint_planner_agent
    
    def create_project(
        self,
        idea_title: str,
        idea_summary_short: Optional[str],
        lead_user_id: str
    ) -> str:
        """
        Create a new project in the database.
        
        Args:
            idea_title: The title/name of the project
            idea_summary_short: Short description/summary of the idea
            lead_user_id: User ID from UserPreferences
            
        Returns:
            project_id: The UUID of the created project
        """
        # Generate a unique project key (e.g., "PROJ-{short_uuid}")
        project_key = f"PROJ-{str(uuid.uuid4())[:8].upper()}"
        
        try:
            project = self.db.create_project(
                key=project_key,
                name=idea_title,
                description=idea_summary_short,
                status="active",
                lead_user_id=lead_user_id
            )
            
            project_id = project["id"]
            logger.info(f"Created project with ID: {project_id}, key: {project_key}")
            return project_id
            
        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            raise
    
    def get_all_documents_by_session_id(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all documents associated with a session_id.
        
        Args:
            session_id: The session ID to fetch documents for
            
        Returns:
            List of document dictionaries
        """
        try:
            documents = self.db.get_documents_by_session_id(
                session_id=session_id,
                include_trashed=False
            )
            logger.info(f"Retrieved {len(documents)} documents for session_id: {session_id}")
            return documents
            
        except Exception as e:
            logger.error(f"Failed to get documents for session_id {session_id}: {e}")
            raise
    
    def update_documents_project_id(
        self,
        documents: List[Dict[str, Any]],
        project_id: str
    ) -> List[Dict[str, Any]]:
        """
        Update project_id for all documents.
        
        Args:
            documents: List of document dictionaries to update
            project_id: The project ID to assign to all documents
            
        Returns:
            List of updated document dictionaries
        """
        updated_documents = []
        
        for doc in documents:
            document_id = doc.get("id")
            if not document_id:
                logger.warning(f"Skipping document without ID: {doc}")
                continue
                
            try:
                updated_doc = self.db.update_document(
                    document_id=document_id,
                    project_id=project_id
                )
                updated_documents.append(updated_doc)
                logger.debug(f"Updated document {document_id} with project_id {project_id}")
                
            except Exception as e:
                logger.error(f"Failed to update document {document_id}: {e}")
                # Continue with other documents even if one fails
                continue
        
        logger.info(f"Updated {len(updated_documents)} documents with project_id: {project_id}")
        return updated_documents
    
    def generate_tasks(
        self,
        global_idea_state: GlobalIdeaState,
        sprint_planning_state: Optional[SprintPlanningState] = None
    ) -> List[SprintTask]:
        """
        Generate tasks from the sprint planning state.
        
        TODO: This will be implemented later with more details.
        For now, returns an empty list or tasks from sprint_planning_state if provided.
        
        Args:
            global_idea_state: The global idea state containing all agent states
            sprint_planning_state: Optional sprint planning state with tasks
            
        Returns:
            List of SprintTask objects
        """
        # TODO: Implement task generation logic
        # For now, extract tasks from sprint_planning_state if available
        tasks = []
        
        if sprint_planning_state and sprint_planning_state.sprint:
            for sprint_week in sprint_planning_state.sprint:
                tasks.extend(sprint_week.tasks)
        
        logger.info(f"Generated {len(tasks)} tasks")
        return tasks
    
    def save_tasks_to_db(
        self,
        tasks: List[SprintTask],
        project_id: str,
        reporter_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Save tasks to the database.
        
        Args:
            tasks: List of SprintTask objects to save
            project_id: The project ID to associate tasks with
            reporter_id: Optional reporter/user ID who created the tasks
            
        Returns:
            List of created task dictionaries
        """
        created_tasks = []
        
        for idx, task in enumerate(tasks, start=1):
            # Generate a task key (e.g., "TASK-1", "TASK-2")
            task_key = f"TASK-{idx}"
            
            # Calculate due date based on timeline_days if needed
            due_date = None
            if task.timeline_days:
                # TODO: Calculate actual due date based on project start date
                # For now, we'll leave it as None
                pass
            
            try:
                created_task = self.db.create_task(
                    project_id=project_id,
                    key=task_key,
                    title=task.title,
                    description=task.description,
                    status="backlog",  # Default status
                    priority=task.priority,
                    assignee_id=task.assigneeId,
                    reporter_id=reporter_id,
                    parent_task_id=None,  # TODO: Handle parent tasks if needed
                    due_date=due_date
                )
                created_tasks.append(created_task)
                logger.debug(f"Created task {task_key}: {task.title}")
                
                # TODO: Handle sub_tasks if they need to be created as separate tasks
                # with parent_task_id pointing to the main task
                
            except Exception as e:
                logger.error(f"Failed to create task {task_key}: {e}")
                # Continue with other tasks even if one fails
                continue
        
        logger.info(f"Created {len(created_tasks)} tasks for project {project_id}")
        return created_tasks
    
    def generate_narrative(
        self,
        global_idea_state: GlobalIdeaState,
        project_id: str
    ) -> str:
        """
        Generate narrative text for the project.
        
        TODO: Will provide more info later.
        For now, returns a placeholder.
        
        Args:
            global_idea_state: The global idea state containing all agent states
            project_id: The project ID
            
        Returns:
            Narrative text as a string
        """
        # TODO: Implement narrative generation logic
        # This could combine information from global_idea_state to create
        # a comprehensive project narrative
        
        narrative = f"Project narrative for {global_idea_state.idea_title or 'Untitled Project'}"
        logger.info(f"Generated narrative for project {project_id}")
        return narrative
    
    def save_project_sections_to_db(
        self,
        project_id: str,
        sections: Dict[str, Any]
    ) -> bool:
        """
        Save project sections to the database.
        
        TODO: This assumes a project_sections table exists or will be created.
        For now, this is a placeholder implementation.
        
        Args:
            project_id: The project ID
            sections: Dictionary containing section data to save
            
        Returns:
            True if successful, False otherwise
        """
        # TODO: Implement project sections saving logic
        # This might require:
        # 1. Creating a project_sections table if it doesn't exist
        # 2. Saving sections as JSONB or separate rows
        # 3. Linking sections to the project
        
        logger.info(f"Saving project sections for project {project_id}")
        logger.warning("save_project_sections_to_db is not yet implemented")
        return False
    
    def complete_stage(
        self,
        global_idea_state: GlobalIdeaState,
        session_id: str
    ) -> Dict[str, Any]:
       
        # create a sprint planning state
        results = {
            "project_id": None,
            "documents_updated": 0,
            "tasks_created": 0,
            "narrative": None,
            "sections_saved": False,
            "errors": []
        }
        
        try:
            # Step 1: Create Project
            if not global_idea_state.idea_title:
                raise ValueError("idea_title is required to create a project")
            
            lead_user_id = None
            if global_idea_state.user_preferences and global_idea_state.user_preferences.user_id:
                lead_user_id = global_idea_state.user_preferences.user_id
            else:
                raise ValueError("user_id from UserPreferences is required to create a project")
            
            project_id = self.create_project(
                idea_title=global_idea_state.idea_title,
                idea_summary_short=global_idea_state.idea_summary_short,
                lead_user_id=lead_user_id
            )
            results["project_id"] = project_id
            
            # Step 2: Get all documents by session_id
            documents = self.get_all_documents_by_session_id(session_id)
            
            # Step 3: Update documents with project_id
            if documents:
                updated_documents = self.update_documents_project_id(
                    documents=documents,
                    project_id=project_id
                )
                results["documents_updated"] = len(updated_documents)
            
            
            # Step 4: Generate tasks
            tasks = self.sprint_planner_agent.plan_full_4_week_sprint(
                idea_context=str(global_idea_state)
            )
            
            # Step 5: Save tasks to DB
            if tasks:
                reporter_id = lead_user_id
                created_tasks = self.save_tasks_to_db(
                    tasks=tasks,
                    project_id=project_id,
                    reporter_id=reporter_id
                )
                results["tasks_created"] = len(created_tasks)
            
            # Step 6: Generate narrative
            narrative = self.generate_narrative(
                global_idea_state=global_idea_state,
                project_id=project_id
            )
            results["narrative"] = narrative
            
            # Step 7: Save project sections
            # TODO: Define what sections to save
            sections = {}  # Placeholder
            sections_saved = self.save_project_sections_to_db(
                project_id=project_id,
                sections=sections
            )
            results["sections_saved"] = sections_saved
            
            logger.info(f"Stage completion successful for project {project_id}")
            
        except Exception as e:
            error_msg = f"Error during stage completion: {str(e)}"
            logger.error(error_msg, exc_info=True)
            results["errors"].append(error_msg)
            raise
        
        return results
