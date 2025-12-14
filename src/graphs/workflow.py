import json
from typing import List, Dict, Tuple, Optional, Any, Union, AsyncGenerator
import logging
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from src.agents.idea_evaluation_agent import IdeaEvaluationAgent
from src.agents.deep_idea_analysis_agent import DeepIdeaAnalysisAgent
from src.agents.market_competition_agent import MarketCompetitionAgent
from src.agents.team_profile_agent import TeamProfileAgent
from src.agents.technology_implementation_agent import TechnologyImplementationAgent
from src.agents.business_goals_agent import BusinessGoalsAgent
from src.agents.execution_preferences_agent import ExecutionPreferencesAgent
from src.agents.constraint_analysis_agent import ConstraintAnalysisAgent
from src.agents.sprint_planner_agent import SprintPlannerAgent
from src.agents.narrative_agent import NarrativeSectionAgent

from src.database.neon_db import NeonDB
from src.handlers.stage_completion import StageCompletion

from src.states.global_idea_state import GlobalIdeaState
from src.models.chat_transfer_model import ChatResponse, UserPreferences

from src.handlers.message_storage import (    
    save_agent_message,
)

from src.utils.context_vars import set_db, set_session_id

logger = logging.getLogger(__name__)

## All the agents will be initialized here and executed in sequence
class Workflow:
    """
    Workflow class that manages the multi-stage agent execution.
    
    Thread Safety:
    - Global state updates are protected by a reentrant lock (_state_lock)
    - All state access should use the provided thread-safe methods:
      - get_global_idea_state() - for reading state
      - get_global_idea_state_snapshot() - for background jobs
      - set_global_idea_state() - for replacing entire state
      - update_global_idea_state() - for merging updates
      - update_global_idea_state_field() - for single field updates
    - Direct access to self.global_idea_state should be avoided
    """
    def __init__(self, model, db: NeonDB):
        """Initialize workflow with all agents and global state."""
        # Global Idea State
        self.global_idea_state = GlobalIdeaState()
        
        # Thread-safe lock for global state updates
        # Using RLock (reentrant lock) to allow nested calls from the same thread
        import threading
        self._state_lock = threading.RLock()
        
        # Initialize all agents for stages 1-8
        self.idea_evaluation_agent = IdeaEvaluationAgent(model=model)
        self.team_profile_agent = TeamProfileAgent(model=model)
        self.deep_idea_analysis_agent = DeepIdeaAnalysisAgent(model=model)
        self.market_competition_agent = MarketCompetitionAgent(model=model)
        self.technology_implementation_agent = TechnologyImplementationAgent(model=model)
        self.business_goals_agent = BusinessGoalsAgent(model=model)
        self.execution_preferences_agent = ExecutionPreferencesAgent(model=model)
        self.constraint_analysis_agent = ConstraintAnalysisAgent(model=model)
        self.sprint_planner_agent = SprintPlannerAgent(model=model)
        self.narrative_agent = NarrativeSectionAgent(model=model)
        
        self.stage_completion = StageCompletion(
            db=db,
            sprint_planner_agent=self.sprint_planner_agent,
            narrative_agent=self.narrative_agent,
        )
        
    
    def _get_agent_for_stage(self, stage: int) -> Optional[Any]:
        """
        Get the appropriate agent for the given stage.
        
        Args:
            stage: Stage number (1-8)
            
        Returns:
            Agent instance or None if stage is invalid
        """
        agent_map = {
            1: self.idea_evaluation_agent,
            2: self.team_profile_agent,
            3: self.deep_idea_analysis_agent,
            4: self.market_competition_agent,
            5: self.technology_implementation_agent,
            6: self.business_goals_agent,
            7: self.execution_preferences_agent,
            8: self.constraint_analysis_agent,
        }
        return agent_map.get(stage)
    
    def _enhance_message_with_context(
        self, 
        messages: List[Union[Dict[str, str], BaseMessage]], 
        stage: int,
        user_preferences: Optional[UserPreferences] = None
    ) -> List[Union[Dict[str, str], BaseMessage]]:
        """
        Enhance the last message with user preferences and/or global idea state context.
        Handles both dictionary messages and LangChain BaseMessage objects.
        
        Args:
            messages: List of messages to enhance (can be dicts or LangChain messages)
            stage: Current stage number (determines if global state should be added)
            user_preferences: Optional user preferences to add
            
        Returns:
            Enhanced messages list (creates a copy to avoid mutating input)
            
        Raises:
            ValueError: If messages list is empty
        """
        if not messages:
            raise ValueError("Messages list cannot be empty")
        
        # Create a copy to avoid mutating the original
        enhanced_messages = messages.copy()
        last_message = enhanced_messages[-1]
        content_parts = []
        
        # Add user preferences first if provided
        if user_preferences:
            content_parts.append("<< user preferences >>")
            content_parts.append(user_preferences.model_dump_json())
            content_parts.append("<< user preferences >>")
            content_parts.append("")  # Empty line separator
        
        # Note: Global idea state context is now added via greeting message
        # when transitioning to next stage, not in message enhancement
        
        # Add original content at the end
        if content_parts:
            # Handle both dictionary and LangChain message objects
            if isinstance(last_message, BaseMessage):
                # LangChain message object - update content attribute
                original_content = getattr(last_message, 'content', "")
                enhanced_content = "\n".join(content_parts) + "\n" + str(original_content)
                # Create a new message with updated content (LangChain messages are immutable)
                if isinstance(last_message, HumanMessage):
                    enhanced_messages[-1] = HumanMessage(content=enhanced_content)
                elif isinstance(last_message, AIMessage):
                    enhanced_messages[-1] = AIMessage(content=enhanced_content)
                else:
                    # Fallback: try to create same type with content
                    try:
                        enhanced_messages[-1] = type(last_message)(content=enhanced_content)
                    except Exception as e:
                        logger.warning(f"Could not create enhanced message of type {type(last_message)}: {e}")
                        # Keep original message if we can't enhance it
            elif isinstance(last_message, dict):
                # Dictionary message - update content key
                last_message = last_message.copy()
                original_content = last_message.get("content", "")
                enhanced_content = "\n".join(content_parts) + "\n" + str(original_content)
                last_message["content"] = enhanced_content
                enhanced_messages[-1] = last_message
            else:
                logger.warning(f"Unknown message type: {type(last_message)}, skipping enhancement")
        
        return enhanced_messages
    
    def _process_agent_response(self, response: Dict, stage: int) -> Tuple[Optional[ChatResponse], Optional[Dict]]:
        """
        Process agent response and handle errors.
        
        Args:
            response: The agent response dictionary
            stage: Current stage number
            
        Returns:
            Tuple of (error_response, None) if error occurred, or (None, structured_response_dict) if successful
        """
        # Check for error in response
        if response.get("error") or (isinstance(response.get("structured_response"), dict) and response.get("structured_response", {}).get("error")):
            error_message = response.get("error_message") or response.get("structured_response", {}).get("error_message", "Unknown error occurred")
            logger.error(f"Stage {stage} agent returned error: {error_message}")
            return ChatResponse(
                connection_status="error",
                error_message=error_message,
                idea_state_stage=stage,
                formatted_output=response.get("structured_response")
            ), None
        
        structured_response = response.get("structured_response")
        
        if not structured_response:
            error_message = f"Stage {stage} agent returned empty structured_response"
            logger.error(error_message)
            return ChatResponse(
                connection_status="error",
                error_message=error_message,
                idea_state_stage=stage
            ), None
        
        # Ensure structured_response is a dict
        if not isinstance(structured_response, dict):
            if hasattr(structured_response, 'model_dump'):
                structured_response = structured_response.model_dump()
            else:
                structured_response = {"raw_response": str(structured_response)}
        
        return None, structured_response
    
    def _create_stage_greeting_message(self, formatted_output_json: Optional[str] = None, user_preferences: Optional[UserPreferences] = None) -> HumanMessage:
        """
        Create a greeting message for the next stage with global idea context.
        
        Returns:
            HumanMessage with greeting and global context
        """
        # Helper function to filter out None and empty values
        def filter_empty_values(data: Dict) -> Dict:
            """Filter out keys with None, empty string, empty list, or empty dict values."""
            filtered = {}
            for key, value in data.items():
                if value is None:
                    continue
                if isinstance(value, str) and value.strip() == "":
                    continue
                if isinstance(value, list) and len(value) == 0:
                    continue
                if isinstance(value, dict) and len(value) == 0:
                    continue
                filtered[key] = value
            return filtered
        
        print(f"global_idea_state: {self.global_idea_state.idea_title}")
        
        # Get the context JSON - either formatted_output_json or filtered global_idea_state
        if formatted_output_json:
            context_json = formatted_output_json
        else:
            # Get global state as dict and filter out empty values
            global_state_dict = self.global_idea_state.model_dump()
            filtered_state = filter_empty_values(global_state_dict)
            context_json = json.dumps(filtered_state, indent=2) if filtered_state else "{}"
        
        greeting_content = f"""Let's continue our discussion. Here's the idea context so far:

        << idea context >>

        {context_json}

        << idea context >>
        """
        
        if user_preferences:
            greeting_content += f"""
            << user preferences >>

            {user_preferences.model_dump_json()}

            << user preferences >>
            """
        
        return HumanMessage(content=greeting_content)
        
    async def execute(
        self, 
        messages: List[Union[Dict[str, str], BaseMessage]], 
        stage: int, 
        session_id: str, 
        user_id: str, 
        db, 
        user_preferences: Optional[UserPreferences] = None
    ) -> AsyncGenerator[ChatResponse, None]:
        """
        Execute workflow for a given stage.
        
        Args:
            messages: List of messages to process
            stage: Current stage number (1-8, or 9 for direct stage completion)
            session_id: Session identifier
            user_id: User identifier
            db: Database instance
            user_preferences: Optional user preferences
            
        Returns:
            ChatResponse with agent response or error
        """
        try:
            # Handle stage 9 directly - trigger stage completion immediately
            if stage == 9:
                logger.info("Stage 9 detected - triggering stage completion directly")
                # Stream events from stage completion
                # Get a thread-safe snapshot of global state to pass to background job
                # This ensures the background thread has an immutable snapshot that won't change
                # even if the main thread updates the state during background processing
                global_state_copy = self.get_global_idea_state_snapshot()
                async for event in self.stage_completion.complete_stage(
                    global_state_copy, 
                    session_id,
                    user_id=user_id
                ):
                    yield ChatResponse(
                        connection_status="events_streaming",
                        event=event,
                        idea_state_stage=9
                    )
                # Final completion response
                yield ChatResponse(
                    connection_status="events_completed",
                    idea_state_stage=9,
                    response_content="All stages completed. Project created successfully."
                )
                
                await save_agent_message(
                    session_id=session_id,
                    user_id=user_id,
                    content="All stages completed. Project created successfully.",
                    db=db,
                    stage=9,  # Use stage 9 (max allowed) instead of 10
                    formatted_output=None
                )
                
                return
            
            # Validate stage (1-8 for normal workflow)
            if stage is None or not isinstance(stage, int) or stage < 1 or stage > 8:
                error_message = f"Invalid stage: {stage}. Must be between 1 and 8, or 9 for stage completion."
                logger.error(error_message)
                yield ChatResponse(
                    connection_status="error",
                    error_message=error_message,
                    idea_state_stage=stage
                )
                return
            
            # Validate messages list is not empty
            if not messages:
                error_message = "Messages list cannot be empty"
                logger.error(error_message)
                yield ChatResponse(
                    connection_status="error",
                    error_message=error_message,
                    idea_state_stage=stage
                )
                return
            
            # Enhance messages with context (user preferences and/or global state)
            try:
                enhanced_messages = self._enhance_message_with_context(messages, stage, user_preferences)
            except ValueError as e:
                logger.error(f"Error enhancing messages: {e}")
                yield ChatResponse(
                    connection_status="error",
                    error_message=str(e),
                    idea_state_stage=stage
                )
                return
            
            # For stages > 1, always prepend the greeting message with global context
            if stage > 1:
                greeting_message = self._create_stage_greeting_message(user_preferences=user_preferences)
                enhanced_messages = [greeting_message] + enhanced_messages
            
            # Set context variables for db and session_id so tools can access them
            set_db(db)
            set_session_id(session_id)
            
            # Get the appropriate agent for this stage
            agent = self._get_agent_for_stage(stage)
            if not agent:
                error_message = f"No agent found for stage {stage}"
                logger.error(error_message)
                yield ChatResponse(
                    connection_status="error",
                    error_message=error_message,
                    idea_state_stage=stage
                )
                return
            
            # Invoke the agent
            response = agent.invoke(enhanced_messages)
            
            # Process the response
            error_response, structured_response = self._process_agent_response(response, stage)
            if error_response:
                yield error_response
                return
            
            # Extract state and follow_up_question
            state = structured_response.get("state")
            follow_up_question = structured_response.get("follow_up_question", "")
            current_stage = stage
            
            # If state is completed, update global state and move to next stage
            if state == "completed":
                # Update global state with completed stage data
                self.update_global_idea_state(structured_response)
                next_stage = stage + 1
                
                # Save completed stage message to database
                formatted_output_json = json.dumps(structured_response) if structured_response else None
                await save_agent_message(
                    session_id=session_id,
                    user_id=user_id,
                    content="Stage completed",
                    db=db,
                    stage=stage,
                    formatted_output=formatted_output_json
                )
                
                # Validate next stage is within bounds
                # Scenario 2: Stage 8 completion -> next_stage becomes 9 (COMMENTED OUT FOR NOW)
                if next_stage > 8:
                    logger.info(f"Stage {stage} completed, next stage is {next_stage} - triggering stage completion")
                    yield ChatResponse(
                        connection_status="active",
                        idea_state_stage=9,
                        response_content="Sprint planning in progress..."
                    )
                    return
                #     # Stage 8 completed, next_stage is 9 - trigger stage completion
                #     logger.info(f"Stage {stage} completed, next stage is {next_stage} - triggering stage completion")
                #     # Stream events from stage completion
                #     async for event in self.stage_completion.complete_stage(self.global_idea_state, session_id):
                #         yield ChatResponse(
                #             connection_status="events_streaming",
                #             event=event,
                #             idea_state_stage=next_stage
                #         )
                #     # Final completion response
                #     yield ChatResponse(
                #         connection_status="events_completed",
                #         idea_state_stage=next_stage,
                #         response_content="All stages completed. Project created successfully."
                #     )
                #     return
                
                # For now, only handle stages 1-8 (normal workflow progression)
                if next_stage <= 8: 
                    # Update current stage to next stage
                    current_stage = next_stage
                    
                    # Invoke next stage agent
                    next_agent = self._get_agent_for_stage(next_stage)
                    if not next_agent:
                        error_message = f"No agent found for stage {next_stage}"
                        logger.error(error_message)
                        yield ChatResponse(
                            connection_status="error",
                            error_message=error_message,
                            idea_state_stage=next_stage
                        )
                        return
                    
                    # For next stage (> 1), create greeting message with global context
                    # The greeting message will be prepended automatically in the main flow for stages > 1
                    # But when transitioning, we need to invoke with just the greeting message to start the conversation
                    greeting_message = self._create_stage_greeting_message()
                    next_response = next_agent.invoke([greeting_message])
                    next_error_response, next_structured_response = self._process_agent_response(next_response, next_stage)
                    
                    if next_error_response:
                        yield next_error_response
                        return
                    
                    # Update variables for next stage response
                    state = next_structured_response.get("state")
                    follow_up_question = next_structured_response.get("follow_up_question", "")
                    structured_response = next_structured_response
            
            # Return response if there's a follow_up_question
            if follow_up_question:
                # Serialize structured_response to JSON string for database storage
                formatted_output_json = json.dumps(structured_response) if structured_response else None

                await save_agent_message(
                    session_id=session_id,
                    user_id=user_id,
                    content=follow_up_question,
                    db=db,
                    stage=current_stage,
                    formatted_output=formatted_output_json
                )
                
                yield ChatResponse(
                    connection_status="active",
                    response_content=follow_up_question,
                    idea_state_stage=current_stage,
                    formatted_output=structured_response
                )
                return
            
            # If the state is not completed and there is no follow_up_question
            error_message = "State is not completed and there is no follow_up_question"
            logger.warning(error_message)
            yield ChatResponse(
                connection_status="error",
                error_message=error_message,
                idea_state_stage=current_stage
            )
            return
            
        except Exception as e:
            logger.error(f"Error in workflow.execute: {e}", exc_info=True)
            # Use stage from outer scope, fallback to 1 if undefined or None
            error_stage = stage if ('stage' in locals() and stage is not None and isinstance(stage, int)) else 1
            yield ChatResponse(
                connection_status="error",
                error_message=f"Workflow execution error: {str(e)}",
                idea_state_stage=error_stage
            )
            return            

    def update_global_idea_state(self, structured_response: Dict) -> None:
        """
        Thread-safe update of the global idea state with the structured response.
        Merges new values from structured_response with existing state values.
        Only updates fields that are present in structured_response (non-None values).
        Preserves existing values for fields not present in structured_response.
        
        This method is thread-safe and prevents race conditions when multiple
        requests try to update the state simultaneously.
        
        Args:
            structured_response: Dictionary containing state fields to update
        """
        with self._state_lock:
            try:
                # Get current state as dict (creates a snapshot)
                current_state_dict = self.global_idea_state.model_dump()
                
                # Filter out None values from structured_response to avoid overwriting existing values
                # Only update fields that have actual values (not None)
                updates = {k: v for k, v in structured_response.items() if v is not None}
                
                # Merge updates into current state
                merged_state = {**current_state_dict, **updates}
                
                # Create new state instance from merged dict (atomic assignment)
                self.global_idea_state = GlobalIdeaState.model_validate(merged_state, strict=False)
                logger.debug("Updated global idea state successfully")
            except Exception as e:
                logger.error(f"Error updating global idea state: {e}", exc_info=True)
                raise
        
    def get_global_idea_state(self) -> GlobalIdeaState:
        """
        Thread-safe getter for the current global idea state.
        Returns a copy to prevent external modifications.
        
        This method should be used when you need to read the state in a thread-safe manner.
        For background jobs or long-running operations, use get_global_idea_state_snapshot()
        to get an immutable snapshot.
        
        Returns:
            GlobalIdeaState instance (copy)
        """
        with self._state_lock:
            # Return a copy to prevent external modifications
            # This ensures thread safety even if the returned object is modified elsewhere
            return GlobalIdeaState.model_validate(self.global_idea_state.model_dump())
    
    def get_global_idea_state_snapshot(self) -> GlobalIdeaState:
        """
        Get an immutable snapshot of the global idea state for background jobs.
        
        This is the recommended method for passing state to background threads,
        as it ensures the state won't change during the background operation.
        
        Returns:
            GlobalIdeaState instance (immutable snapshot)
        """
        with self._state_lock:
            # Create a deep copy to ensure complete immutability
            return GlobalIdeaState.model_validate(self.global_idea_state.model_dump())
    
    def set_global_idea_state(self, new_state: GlobalIdeaState) -> None:
        """
        Thread-safe setter for the global idea state.
        Replaces the entire state atomically.
        
        Args:
            new_state: New GlobalIdeaState instance to set
        """
        with self._state_lock:
            # Create a copy to ensure we don't hold a reference to external state
            self.global_idea_state = GlobalIdeaState.model_validate(new_state.model_dump())
            logger.debug("Global idea state replaced")
    
    def update_global_idea_state_field(self, field_name: str, value: Any) -> None:
        """
        Thread-safe update of a single field in the global idea state.
        
        Args:
            field_name: Name of the field to update
            value: New value for the field
        """
        with self._state_lock:
            try:
                current_state_dict = self.global_idea_state.model_dump()
                current_state_dict[field_name] = value
                self.global_idea_state = GlobalIdeaState.model_validate(current_state_dict, strict=False)
                logger.debug(f"Updated global idea state field '{field_name}'")
            except Exception as e:
                logger.error(f"Error updating global idea state field '{field_name}': {e}", exc_info=True)
                raise
    