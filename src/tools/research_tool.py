from langchain.tools import tool
from langchain_core.messages import HumanMessage
from src.llms.openai_llm import OpenAILLM
from src.agents.research_agent import ResearchAgent
import logging

logger = logging.getLogger(__name__)

@tool("research_tool")
def research_tool(query: str) -> str:
    """
    Search the web for information.
    """
    try:
        model = OpenAILLM().get_llm_model()
        
        research_agent = ResearchAgent(model=model)
        
        # research_agent.invoke expects a list of messages, not a dict
        result_message = research_agent.invoke([HumanMessage(content=query)])
        
        # Extract content from BaseMessage and return as string
        if hasattr(result_message, 'content'):
            return str(result_message.content)
        else:
            return str(result_message)
            
    except Exception as e:
        logger.error(f"Error in research_tool: {e}", exc_info=True)
        return f"Error during research: {str(e)}"

