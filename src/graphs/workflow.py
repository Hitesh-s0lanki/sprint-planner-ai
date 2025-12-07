import json
from typing import List, Dict
import logging

from src.agents.idea_evaluation_agent import IdeaEvaluationAgent

from src.models.chat_transfer_model import ChatResponse
from src.handlers.message_storage import (    
    save_agent_message,
)

logger = logging.getLogger(__name__)

## All the agents will be initialized here and executed in sequence
class Workflow:
    def __init__(self, model):
        self.idea_evaluation_agent = IdeaEvaluationAgent(model=model)
        
    async def execute(self, messages: List[Dict[str, str]], stage: int, session_id: str, user_id: str, db):
        try:
            follow_up_question = ""
            state = None
            structured_response = None
            
            if stage == 1:
                response = self.idea_evaluation_agent.invoke(messages)
                
                # Check for error in response
                if response.get("error") or (isinstance(response.get("structured_response"), dict) and response.get("structured_response", {}).get("error")):
                    error_message = response.get("error_message") or response.get("structured_response", {}).get("error_message", "Unknown error occurred")
                    logger.error(f"Agent returned error: {error_message}")
                    return ChatResponse(
                        connection_status="error",
                        error_message=error_message,
                        idea_state_stage=stage,
                        formatted_output=response.get("structured_response")
                    )
                
                structured_response = response.get("structured_response")
                
                if not structured_response:
                    error_message = "Agent returned empty structured_response"
                    logger.error(error_message)
                    return ChatResponse(
                        connection_status="error",
                        error_message=error_message,
                        idea_state_stage=stage
                    )
                
                # Ensure structured_response is a dict
                if not isinstance(structured_response, dict):
                    if hasattr(structured_response, 'model_dump'):
                        structured_response = structured_response.model_dump()
                    else:
                        structured_response = {"raw_response": str(structured_response)}
                
                state = structured_response.get("state")
                follow_up_question = structured_response.get("follow_up_question", "")
                
            if state == "completed":
                # update the ideas data in the database        
                stage = stage + 1
        
            
            if follow_up_question or state == "completed":
                # Serialize structured_response to JSON string for database storage
                formatted_output_json = json.dumps(structured_response) if structured_response else None
                
                # update the messages data in the database
                await save_agent_message(
                    session_id=session_id,
                    user_id=user_id,
                    content=follow_up_question,
                    db=db,
                    stage=stage,
                    formatted_output=formatted_output_json
                )
                
                return ChatResponse(
                    connection_status="active",
                    response_content=follow_up_question,
                    idea_state_stage=stage,
                    formatted_output=structured_response
                )
            
            # if the state is not completed and there is no follow_up_question
            error_message = "State is not completed and there is no follow_up_question"
            logger.warning(error_message)
            return ChatResponse(
                connection_status="error",
                error_message=error_message,
                idea_state_stage=stage
            )
            
        except Exception as e:
            logger.error(f"Error in workflow.execute: {e}", exc_info=True)
            return ChatResponse(
                connection_status="error",
                error_message=f"Workflow execution error: {str(e)}",
                idea_state_stage=stage
            )            
