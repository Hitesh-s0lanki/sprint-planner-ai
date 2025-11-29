from langchain.tools import tool
from langchain_core.messages import HumanMessage
from src.llms.openai_llm import OpenAILLM
from src.agents.research_agent import ResearchAgent

@tool("research_tool")
def research_tool(query: str) -> str:
    """
    Search the web for information.
    """
    
    model = OpenAILLM().get_llm_model()
    
    research_agent = ResearchAgent(model=model)
    
    return research_agent.invoke({"messages": [HumanMessage(content=query)]})

