from langchain.agents import create_agent
from typing import AsyncGenerator, List, Dict, Any, Union
from langchain_core.messages import BaseMessage
from langchain.agents.structured_output import ProviderStrategy
import json
import logging

from src.states.execution_preferences_agent_state import ExecutionPreferencesState
from src.system_prompts.execution_preferences import get_execution_preferences_instructions

from src.tools.research_tool import research_tool

logger = logging.getLogger(__name__)

class ExecutionPreferencesAgent:
    
    def __init__(self, model):
        self.name = "Execution Preferences Agent"
        self.instructions = get_execution_preferences_instructions()
        self.model = model
        self.tools = [research_tool]
        
        # Create the agent executable upon initialization
        self.agent = create_agent(
            model=self.model,
            system_prompt=self.instructions,
            tools=self.tools,
            response_format=ProviderStrategy(ExecutionPreferencesState)
        )

    def invoke(self, messages: Union[List[Dict[str, str]], List[BaseMessage]]) -> Dict[str, Any]:
        """
        Invoke the agent and return properly formatted response.
        Handles errors and ensures proper JSON serialization.
        """
        try:
            response = self.agent.invoke({"messages": messages})
            
            # Handle the structured_response - convert Pydantic model to dict if needed
            if "structured_response" in response:
                structured_response = response["structured_response"]
                
                # If it's a Pydantic model, convert to dict
                if hasattr(structured_response, 'model_dump'):
                    response["structured_response"] = structured_response.model_dump()
                elif isinstance(structured_response, str):
                    # If it's a string, try to parse as JSON
                    try:
                        response["structured_response"] = json.loads(structured_response)
                    except json.JSONDecodeError:
                        # If not valid JSON, wrap it in a dict
                        response["structured_response"] = {"raw_response": structured_response}
                elif not isinstance(structured_response, dict):
                    # If it's some other type, convert to dict
                    response["structured_response"] = dict(structured_response) if hasattr(structured_response, '__dict__') else {"raw_response": str(structured_response)}
            
            return response
            
        except Exception as e:
            logger.error(f"Error in ExecutionPreferencesAgent.invoke: {e}", exc_info=True)
            # Return error response in expected format
            return {
                "error": True,
                "error_message": str(e),
                "structured_response": {
                    "error": True,
                    "error_message": str(e),
                    "state": "error"
                }
            }

    async def astream(self, messages: Union[List[Dict[str, str]], List[BaseMessage]], session_id: str) -> AsyncGenerator[Dict[str, Any], Any]:
        async for chunk in self.agent.astream({"messages": messages}, config = {
            "thread_id": session_id
        }):
            yield chunk
            
