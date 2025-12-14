import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Union

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
        self.messages = []

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
    def _build_week_prompt(week: int) -> str:
        """
        Build a clear, execution-focused prompt for a specific sprint week.
        """

        week_focus_map = {
            1: (
                "WEEK 1 - PROBLEM CLARITY & DEMAND SIGNALS\n"
                "- This is the start of execution.\n"
                "- Focus on understanding users, validating the core problem, and testing demand.\n"
                "- Prefer conversations, observations, and simple shadow tests over building.\n"
                "- Small, real-world actions only.\n"
            ),
            2: (
                "WEEK 2 - MINIMUM VIABLE EXPERIENCE\n"
                "- Assume Week 1 insights are available.\n"
                "- Focus on building the smallest usable experience (manual or no-code is fine).\n"
                "- Users should be able to try something end-to-end.\n"
                "- Continue collecting feedback.\n"
            ),
            3: (
                "WEEK 3 - TRACTION & CONVERSION EXPERIMENTS\n"
                "- Assume a basic product or prototype exists.\n"
                "- Focus on getting users: outreach, demos, trials, signups.\n"
                "- Introduce simple sales or commitment signals.\n"
                "- Track a few clear metrics.\n"
            ),
            4: (
                "WEEK 4 - DELIVERY, LEARNING & NEXT STEPS\n"
                "- Assume real user interactions from Weeks 1-3.\n"
                "- Focus on delivering value to real users.\n"
                "- Fix the biggest friction points.\n"
                "- Capture learnings and define clear next steps.\n"
            ),
        }

        week_context = week_focus_map.get(
            week,
            "Focus on practical execution aligned with the current stage."
        )

        return (
            "You are planning a startup sprint.\n\n"
            
            f"{week_context}\n\n"
            f"Generate the sprint plan for **Week {week} only**.\n"
            "- Output a single SprintWeek JSON object.\n"
            "- Include only actionable, execution-driven tasks.\n"
            "- Every task must have a clear Definition of Done.\n"
        )


    def generate_week_sprint(
        self,
        idea_context: str,
        week: int,
    ) -> Dict[str, Any]:
        
        if week == 1:
            self.messages.append({
                "role": "user",
                "content": f"""
                   <<< idea context >>>
                   {idea_context}
                   <<< idea context >>>
                """,
            })
            
        self.messages.append({
            "role": "user",
            "content": self._build_week_prompt(week),
        })

        response = self.invoke(self.messages)
        
        self.messages.append({
            "role": "assistant",
            "content": str(response["structured_response"]),
        })

        return response["structured_response"]
    
    def generate_all_weeks_sprint(
        self,
        idea_context: str,
    ) -> Dict[str, Any]:
        all_weeks: List[Dict[str, Any]] = []
        for week in range(1, 5):
            try:
                all_weeks.append(self.generate_week_sprint(idea_context, week))
            except Exception as e:
                logger.error(f"Error in SprintPlannerAgent.generate_all_weeks_sprint: {e}", exc_info=True)
                continue
        return SprintPlanningState(sprints=all_weeks)       
