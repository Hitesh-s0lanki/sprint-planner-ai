import json
import logging
import time
from typing import AsyncGenerator, List, Dict, Any, Union, Optional

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.messages import BaseMessage

from src.system_prompts.narrative_section_generator import generate_narrative_section
from src.states.narrative_agent_state import NarrativeSectionResponse, NarrativeSection
from src.tools.research_tool import research_tool

logger = logging.getLogger(__name__)

# Delay between narrative section generation requests (in seconds)
# Helps prevent rate limiting and API blocking
NARRATIVE_SECTION_DELAY = 2.0  # 2 seconds between requests


class NarrativeSectionAgent:
    """
    Generates ONE narrative section at a time in Markdown.
    Keeps conversation continuity so idea context is passed only once.
    """

    def __init__(self, model):
        self.name = "Narrative Section Generator Agent"
        self.instructions = generate_narrative_section()
        self.model = model
        self.tools = [research_tool]

        self.agent = create_agent(
            model=self.model,
            system_prompt=self.instructions,
            tools=self.tools,
            response_format=ProviderStrategy(NarrativeSectionResponse),
        )

    # ─────────────────────────────────────────
    # Low-level core APIs
    # ─────────────────────────────────────────

    def invoke(
        self,
        messages: Union[List[Dict[str, str]], List[BaseMessage]],
    ) -> Dict[str, Any]:
        """
        Invoke and normalize structured response.

        Returns:
        {
          "structured_response": { "section": {...} },
          "raw": ...,
          ...
        }
        """
        try:
            response = self.agent.invoke({"messages": messages})

            if "structured_response" in response:
                structured_response = response["structured_response"]

                # Pydantic model → dict
                if hasattr(structured_response, "model_dump"):
                    response["structured_response"] = structured_response.model_dump()

                # JSON string → dict
                elif isinstance(structured_response, str):
                    try:
                        response["structured_response"] = json.loads(structured_response)
                    except json.JSONDecodeError:
                        response["structured_response"] = {"raw_response": structured_response}

                # Fallback
                elif not isinstance(structured_response, dict):
                    response["structured_response"] = (
                        dict(structured_response)
                        if hasattr(structured_response, "__dict__")
                        else {"raw_response": str(structured_response)}
                    )

            return response

        except Exception as e:
            logger.error(f"Error in NarrativeSectionAgent.invoke: {e}", exc_info=True)
            return {
                "error": True,
                "error_message": str(e),
                "structured_response": {
                    "error": True,
                    "error_message": str(e),
                },
            }

    async def astream(
        self,
        messages: Union[List[Dict[str, str]], List[BaseMessage]],
        session_id: str,
    ) -> AsyncGenerator[Dict[str, Any], Any]:
        """
        Async streaming version.
        Yields intermediate chunks.
        """
        async for chunk in self.agent.astream(
            {"messages": messages},
            config={"thread_id": session_id},
        ):
            yield chunk

    # ─────────────────────────────────────────
    # High-level helpers (section-by-section)
    # ─────────────────────────────────────────

    @staticmethod
    def _build_section_prompt(
        idea_context: str,
        category: str,
        section_name: str,
        *,
        instruction: Optional[str] = None,
        section_type: str = "text",
        position: Optional[int] = None,
        existing_content: Optional[str] = None,
    ) -> str:
        """
        Build user prompt for one section generation/refactor.
        """
        meta_lines = [
            f"Category: {category}",
            f"Section name: {section_name}",
            f"Section type: {section_type}",
        ]
        if position is not None:
            meta_lines.append(f"Position: {position}")
        if instruction:
            meta_lines.append(f"Instruction: {instruction}")

        header = "\n".join(meta_lines)

        # If refactoring existing AI section
        if existing_content:
            return (
                "Idea context:\n"
                f"{idea_context}\n\n"
                f"{header}\n\n"
                "Existing section content to refactor:\n"
                f"{existing_content}\n\n"
                "Task: Refactor and improve the section content. Output Markdown only."
            )

        # Creating new section
        return (
            "Idea context:\n"
            f"{idea_context}\n\n"
            f"{header}\n\n"
            "Task: Create the requested section content. Output Markdown only."
        )

    def generate_section(
        self,
        idea_context: str,
        category: str,
        section_name: str,
        *,
        instruction: Optional[str] = None,
        section_type: str = "text",
        position: int = 0,
        existing_content: Optional[str] = None,
        previous_messages: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        High-level helper:
        - Passes idea_context only on first call
        - Maintains conversation with previous_messages
        - Generates ONE section as NarrativeSectionResponse

        Returns:
          {
            "response": normalized_response_dict,
            "messages": updated_messages
          }
        """
        messages = previous_messages[:] if previous_messages else []

        if not messages:
            user_content = self._build_section_prompt(
                idea_context=idea_context,
                category=category,
                section_name=section_name,
                instruction=instruction,
                section_type=section_type,
                position=position,
                existing_content=existing_content,
            )
        else:
            # Don't repeat full idea context; keep it short
            user_content = (
                f"We are continuing narrative generation for the same idea as before.\n\n"
                f"Category: {category}\n"
                f"Section name: {section_name}\n"
                f"Section type: {section_type}\n"
                f"Position: {position}\n"
                + (f"Instruction: {instruction}\n" if instruction else "")
                + ("\nExisting section content to refactor:\n" + existing_content + "\n" if existing_content else "")
                + "\nTask: Output the requested section content as Markdown only."
            )

        messages.append({"role": "user", "content": user_content})

        response = self.invoke(messages)

        # Append assistant message for continuity (serialize structured_response)
        if "structured_response" in response:
            try:
                assistant_payload = json.dumps(response["structured_response"])
            except TypeError:
                assistant_payload = str(response["structured_response"])

            messages.append({"role": "assistant", "content": assistant_payload})

        return {"response": response, "messages": messages}

    def generate_category_sections(
        self,
        idea_context: str,
        category: str,
        section_names: List[str],
        *,
        instruction: Optional[str] = None,
        section_type: str = "text",
        start_position: int = 0,
    ) -> NarrativeSectionResponse:
        """
        Convenience: generate all sections for a single category sequentially.
        Keeps one conversation and passes idea_context only once.

        Returns a list of NarrativeSection dicts.
        """
        sections: List[Dict[str, Any]] = []
        messages: List[Dict[str, str]] = []

        for idx, name in enumerate(section_names):
            try:
                # Add delay between requests to prevent rate limiting (except for first request)
                if idx > 0:
                    logger.debug(f"Waiting {NARRATIVE_SECTION_DELAY}s before generating next section...")
                    time.sleep(NARRATIVE_SECTION_DELAY)
                
                result = self.generate_section(
                    idea_context=idea_context,
                    category=category,
                    section_name=name,
                    instruction=instruction,
                    section_type=section_type,
                    position=start_position + idx,
                    previous_messages=messages,
                )

                response = result["response"]
                messages = result["messages"]

                # Check for errors in response
                if response.get("error"):
                    logger.warning(
                        f"Error generating section '{name}' (category: {category}): "
                        f"{response.get('error_message', 'Unknown error')}"
                    )
                    # Add delay even on error to prevent rapid retries
                    if idx < len(section_names) - 1:
                        time.sleep(NARRATIVE_SECTION_DELAY)
                    continue

                sr = response.get("structured_response", {})
                section = sr.get("section") if isinstance(sr, dict) else None
                if section:
                    sections.append(section)
                    logger.debug(f"Successfully generated section '{name}' (category: {category})")
                else:
                    logger.warning(
                        f"Failed to extract section from response for '{name}' "
                        f"(category: {category})"
                    )
            except Exception as e:
                logger.error(
                    f"Exception while generating section '{name}' (category: {category}): {e}",
                    exc_info=True
                )
                # Add delay even on exception to prevent rapid retries
                if idx < len(section_names) - 1:
                    time.sleep(NARRATIVE_SECTION_DELAY)
                # Continue with next section instead of failing completely
                continue

        return {"sections": sections, "messages": messages}

    def generate_full_narrative(
        self,
        idea_context: str,
        plan: Dict[str, List[str]],
        *,
        instruction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Optional convenience:
        plan = {
          "narrative": ["Executive Summary", "PR-Style Launch", ...],
          "product": [...],
          ...
        }

        Generates everything sequentially with a single conversation history.
        """
        all_sections: List[Dict[str, Any]] = []
        messages: List[Dict[str, str]] = []

        total_sections = sum(len(names) for names in plan.values())
        current_section = 0
        
        for category, section_names in plan.items():
            for position, section_name in enumerate(section_names):
                current_section += 1
                try:
                    # Add delay between requests to prevent rate limiting (except for first request)
                    if current_section > 1:
                        logger.debug(
                            f"Waiting {NARRATIVE_SECTION_DELAY}s before generating section "
                            f"{current_section}/{total_sections} ({section_name})..."
                        )
                        time.sleep(NARRATIVE_SECTION_DELAY)
                    
                    result = self.generate_section(
                        idea_context=idea_context,
                        category=category,
                        section_name=section_name,
                        instruction=instruction,
                        position=position,
                        previous_messages=messages,
                    )
                    response = result["response"]
                    messages = result["messages"]

                    # Check for errors in response
                    if response.get("error"):
                        logger.warning(
                            f"Error generating section '{section_name}' (category: {category}): "
                            f"{response.get('error_message', 'Unknown error')}"
                        )
                        # Add delay even on error to prevent rapid retries
                        if current_section < total_sections:
                            time.sleep(NARRATIVE_SECTION_DELAY)
                        continue

                    sr = response.get("structured_response", {})
                    section = sr.get("section") if isinstance(sr, dict) else None
                    if section:
                        all_sections.append(section)
                        logger.debug(
                            f"Successfully generated section {current_section}/{total_sections}: "
                            f"'{section_name}' (category: {category})"
                        )
                    else:
                        logger.warning(
                            f"Failed to extract section from response for '{section_name}' "
                            f"(category: {category})"
                        )
                except Exception as e:
                    logger.error(
                        f"Exception while generating section '{section_name}' "
                        f"(category: {category}): {e}",
                        exc_info=True
                    )
                    # Add delay even on exception to prevent rapid retries
                    if current_section < total_sections:
                        time.sleep(NARRATIVE_SECTION_DELAY)
                    # Continue with next section instead of failing completely
                    continue

        logger.info(
            f"Completed narrative generation: {len(all_sections)}/{total_sections} sections generated"
        )
        return {"sections": all_sections, "messages": messages}

