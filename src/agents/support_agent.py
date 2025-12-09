from langchain.agents import create_agent
from typing import AsyncGenerator, List, Dict, Any, Union
from langchain_core.messages import BaseMessage

class SupportAgent:
    def __init__(self, model):
        self.system_prompt = "You are a helpful assistant."
        self.model = model

        # Create the agent executable upon initialization
        self.agent = create_agent(
            model=self.model,
            system_prompt=self.system_prompt,
        )

    def invoke(self, messages: Union[List[Dict[str, str]], List[BaseMessage]]) -> Dict[str, Any]:
        return self.agent.invoke({"messages": messages})

    async def astream(self, messages: Union[List[Dict[str, str]], List[BaseMessage]]) -> AsyncGenerator[Dict[str, Any], Any]:
        async for chunk in self.agent.astream({"messages": messages}):
            yield chunk