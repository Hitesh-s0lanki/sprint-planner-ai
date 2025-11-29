from typing import AsyncGenerator, List, Dict, Any, Sequence, Union
from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langchain_core.messages import BaseMessage

from src.system_prompts.sprint_planner_system_prompt import sprint_planner_system_prompt
from src.states.agile_project_manager_agent_state import SprintPlanningState

class SprintPlannerAgent:
    def __init__(self, model, tools: Sequence[BaseTool] = None):
        self.name = "SprintPlannerAgent"
        self.instructions = sprint_planner_system_prompt()

        # wrap the base model to return a SprintPlanningState object
        self.model = model.with_structured_output(SprintPlanningState)

        self.tools = tools or []

        self.agent = create_agent(
            model=self.model,
            system_prompt=self.instructions,
            tools=self.tools,
        )

    def invoke(
        self,
        messages: Union[List[Dict[str, str]], List[BaseMessage]],
    ) -> SprintPlanningState:
        """
        Returns a SprintPlanningState Pydantic object.
        """
        return self.agent.invoke({"messages": messages})

    async def astream(
        self,
        messages: Union[List[Dict[str, str]], List[BaseMessage]],
    ) -> AsyncGenerator[SprintPlanningState, Any]:
        """
        Async streaming version; yields SprintPlanningState chunks or final state
        depending on how the underlying agent streams.
        """
        async for chunk in self.agent.astream({"messages": messages}):
            yield chunk