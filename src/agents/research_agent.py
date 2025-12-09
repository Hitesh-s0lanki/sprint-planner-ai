import os
from dotenv import load_dotenv
import logging

from typing import List, Dict, Sequence, Union, Optional
from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langchain_core.messages import BaseMessage, AIMessage

from src.system_prompts.research_agent_system_prompt import research_agent_system_prompt

# If you're using langchain-community tools (adjust imports if your paths differ)
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.utilities import ArxivAPIWrapper
from langchain_community.tools.arxiv.tool import ArxivQueryRun

load_dotenv()
logger = logging.getLogger(__name__)

def build_research_tools() -> List[BaseTool]:
    """
    Default research tools:
      - Tavily web search
      - Arxiv scholarly search
    """
    
    os.environ["TAVILY_API_KEY"] = os.getenv("TAVILY_API_KEY")
    
    tavily_tool = TavilySearchResults(
        max_results=5,
        include_answer=True,
        include_raw_content=False,
    )

    arxiv_wrapper = ArxivAPIWrapper(
        max_results=5,
    )
    arxiv_tool = ArxivQueryRun(api_wrapper=arxiv_wrapper)

    return [tavily_tool, arxiv_tool]


class ResearchAgent:
    def __init__(self, model, tools: Optional[Sequence[BaseTool]] = None):
        self.name = "ResearchAgent"
        self.instructions = research_agent_system_prompt()
        self.model = model
        self.tools = list(tools) if tools is not None else build_research_tools()

        self.agent = create_agent(
            model=self.model,
            system_prompt=self.instructions,
            tools=self.tools,
        )

    def invoke(
        self,
        messages: Union[List[Dict[str, str]], List[BaseMessage]],
    ) -> BaseMessage:
        """
        Invoke the research agent and return ONLY the last assistant message.
        """
        try:
            result = self.agent.invoke({"messages": messages})
            # LangChain `create_agent` typically returns a dict with "messages"
            # which is a list[BaseMessage]. We return just the last one.
            agent_messages: List[BaseMessage] = result.get("messages", [])
            
            if not agent_messages:
                logger.warning("Research agent returned no messages")
                return AIMessage(content="No response generated from research agent.")
            
            return agent_messages[-1]
            
        except Exception as e:
            logger.error(f"Error in ResearchAgent.invoke: {e}", exc_info=True)
            # Return an error message as AIMessage
            return AIMessage(content=f"Error during research: {str(e)}")

