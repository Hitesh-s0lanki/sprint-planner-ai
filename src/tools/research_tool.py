from langchain.tools import tool
from langchain_core.messages import HumanMessage
from src.llms.openai_llm import OpenAILLM
from src.agents.research_agent import ResearchAgent
from src.utils.context_vars import get_db, get_session_id
from src.utils.utils import markdown_to_blocknote
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
        
        title = result_message["title"]
        brief_summary = result_message["brief_summary"]
        
        # Save to database if db and session_id are available
        db = get_db()
        session_id = get_session_id()
        
        if db and session_id:
            try:
                # Convert brief_summary to BlockNote JSON format using utility function
                # This handles plain text and markdown properly
                blocknote_content = markdown_to_blocknote(brief_summary)
                
                db.create_document(
                    session_id=session_id,
                    title=title,
                    content=blocknote_content,  # BlockNote JSON format
                    added_by="ai",
                )
                logger.info(f"Saved research document to database: {title}")
            except Exception as db_error:
                logger.error(f"Error saving research document to database: {db_error}", exc_info=True)
                # Don't fail the tool if DB save fails, just log it
        
        return brief_summary
            
    except Exception as e:
        logger.error(f"Error in research_tool: {e}", exc_info=True)
        return f"Error during research: {str(e)}"

