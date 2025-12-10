import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Union, Optional

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.messages import BaseMessage

from src.system_prompts.sprint_planner_system_prompt import sprint_planner_system_prompt
from src.states.agile_project_manager_agent_state import SprintWeek, SprintPlanningState
from src.tools.research_tool import research_tool

logger = logging.getLogger(__name__)


class SprintPlannerAgent:

    def __init__(self, model):
        self.name = "Sprint Planner Agent"
        self.instructions = sprint_planner_system_prompt()
        self.model = model

        self.tools = [research_tool]

        # Create agent with structured output binding
        self.agent = create_agent(
            model=self.model,
            system_prompt=self.instructions,
            tools=self.tools,
            response_format=ProviderStrategy(SprintWeek),
        )

    # ─────────────────────────────────────────
    # Low-level core APIs (same as before)
    # ─────────────────────────────────────────

    def invoke(
        self,
        messages: Union[List[Dict[str, str]], List[BaseMessage]],
    ) -> Dict[str, Any]:
        """
        Invoke the agent and return a normalized SprintWeek response dict.

        Returned structure example:
        {
            "structured_response": { ... SprintWeek as dict ... },
            "raw": ... (provider specific),
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
                        response["structured_response"] = {
                            "raw_response": structured_response
                        }

                # Other object → dict fallback
                elif not isinstance(structured_response, dict):
                    response["structured_response"] = (
                        dict(structured_response)
                        if hasattr(structured_response, "__dict__")
                        else {"raw_response": str(structured_response)}
                    )

            return response

        except Exception as e:
            logger.error(f"Error in SprintPlannerAgent.invoke: {e}", exc_info=True)
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
        Yields intermediate or final SprintWeek chunks.
        """
        async for chunk in self.agent.astream(
            {"messages": messages},
            config={"thread_id": session_id},
        ):
            yield chunk

    # ─────────────────────────────────────────
    # High-level helpers for week-by-week flow
    # ─────────────────────────────────────────

    @staticmethod
    def _build_week_prompt(idea_context: str, week: int) -> str:
        """
        Build the user-facing prompt for a specific week.
        You can customize the text for each week theme here.
        """
        if week == 1:
            week_context = (
                "This is **Week 1** sprint planning.\n\n"
                "- This is the start of the idea → execution journey.\n"
                "- Focus on clarity, foundations, and first real-world actions.\n"
                "- Keep tasks small, practical, and measurable.\n"
                "- Touch as many of the business areas as reasonable: "
                "Value Creation, Marketing, Sales, Value Delivery, Finance.\n"
            )
        elif week == 2:
            week_context = (
                "This is **Week 2** sprint planning.\n\n"
                "- Assume Week 1 is mostly done.\n"
                "- Focus on building and validating the first usable experience.\n"
                "- Include real user/prospect interactions where possible.\n"
            )
        elif week == 3:
            week_context = (
                "This is **Week 3** sprint planning.\n\n"
                "- Assume a basic version or prototype exists.\n"
                "- Focus on traction experiments: marketing + sales.\n"
                "- Track simple, quantitative metrics.\n"
            )
        else:
            week_context = (
                "This is **Week 4** sprint planning.\n\n"
                "- Assume we have real learnings from Weeks 1–3.\n"
                "- Focus on value delivery, refinement, and basic finance checks.\n"
                "- Summarize and consolidate learnings into clear next steps.\n"
            )

        return (
            "Here is my idea context:\n\n"
            f"{idea_context}\n\n"
            f"{week_context}\n"
            f"Please generate the sprint plan for **Week {week}** only, as a single SprintWeek JSON object."
        )

    def generate_week_sprint(
        self,
        idea_context: str,
        week: int,
        previous_messages: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        High-level helper:
        - Takes idea_context (used only for the first user message in a sequence)
        - Takes an optional messages history (user+assistant messages)
        - Appends a new user request for the given week
        - Calls invoke() and returns the response dict

        Usage:
            messages = []
            week1 = agent.generate_week_sprint(idea_context, week=1, previous_messages=messages)
            week2 = agent.generate_week_sprint(idea_context, week=2, previous_messages=messages)
            ...
        """
        messages = previous_messages[:] if previous_messages else []

        # Only include the full idea context the first time.
        # If previous_messages is empty, this is the first call in the conversation.
        if not messages:
            user_content = self._build_week_prompt(idea_context, week)
        else:
            # Subsequent weeks: we don't need to repeat full idea context,
            # but we can still remind the model which week we're planning.
            user_content = (
                f"We are continuing sprint planning for the same idea as before.\n\n"
                f"Please generate the sprint plan for **Week {week}** only, "
                f"as a single SprintWeek JSON object."
            )

        messages.append(
            {
                "role": "user",
                "content": user_content,
            }
        )

        response = self.invoke(messages)

        # For proper conversation continuity, append a synthetic assistant message
        # with the structured_response serialized as JSON string.
        if "structured_response" in response:
            try:
                assistant_payload = json.dumps(response["structured_response"])
            except TypeError:
                assistant_payload = str(response["structured_response"])

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_payload,
                }
            )

        # Return both the normalized response and updated messages
        return {
            "response": response,
            "messages": messages,
        }

    def plan_full_4_week_sprint(
        self,
        idea_context: str,
    ) -> Dict[str, Any]:
        """
        Convenience method to generate all 4 weeks in one go,
        while keeping a single conversation and passing idea_context only once.

        Returns:
            {
                "weeks": [week1_dict, week2_dict, week3_dict, week4_dict],
                "messages": full_messages_history
            }
        """
        all_weeks: List[Dict[str, Any]] = []
        messages: List[Dict[str, str]] = []

        for week in range(1, 5):
            result = self.generate_week_sprint(
                idea_context=idea_context,
                week=week,
                previous_messages=messages,
            )

            response = result["response"]
            messages = result["messages"]

            week_struct = response.get("structured_response")
            all_weeks.append(week_struct)

        return SprintPlanningState(sprints=all_weeks)
    
