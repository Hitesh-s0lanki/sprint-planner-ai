import os
from dotenv import load_dotenv
import logging
import json

from typing import List, Dict, Sequence, Union, Optional, Any
from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.tools import BaseTool
from langchain_core.messages import BaseMessage

from src.states.research_agent_state import ResearchAgentState
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

        # Create the agent executable upon initialization
        self.agent = create_agent(
            model=self.model,
            system_prompt=self.instructions,
            tools=self.tools,
            response_format=ProviderStrategy(ResearchAgentState)
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
            
            return response["structured_response"]
            
        except Exception as e:
            logger.error(f"Error in ResearchAgent.invoke: {e}", exc_info=True)
            # Return error response in expected format
            return {
                "error": True,
                "error_message": str(e),
                "structured_response": {
                    "error": True,
                    "error_message": str(e),
                    "brief_summary": f"Error during research: {str(e)}"
                }
            }

