from langchain.agents import create_agent
from typing import AsyncGenerator, List, Dict, Any, Sequence, Union
from langchain_core.tools import BaseTool
from langchain_core.messages import BaseMessage
from langchain.agents.structured_output import ProviderStrategy

from src.states.idea_evaluation_agent_state import IdeaEvaluationState
from src.system_prompts.idea_evaluation import get_idea_evaluator_instructions

class IdeaEvaluationAgent:
    
    def __init__(self, model, tools: Sequence[BaseTool] = None):
        self.name = "Idea Evaluator Agent"
        self.instructions = get_idea_evaluator_instructions()
        self.model = model
        self.tools = tools or []
        
        # Create the agent executable upon initialization
        self.agent = create_agent(
            model=self.model,
            system_prompt=self.instructions,
            tools=self.tools,
            response_format=ProviderStrategy(IdeaEvaluationState)
        )

    def invoke(self, messages: Union[List[Dict[str, str]], List[BaseMessage]]) -> Dict[str, Any]:
        return self.agent.invoke({"messages": messages})

    async def astream(self, messages: Union[List[Dict[str, str]], List[BaseMessage]], session_id: str) -> AsyncGenerator[Dict[str, Any], Any]:
        async for chunk in self.agent.astream({"messages": messages}, config = {
            "thread_id": session_id
        }):
            yield chunk
            
