from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

class SupportAgent:
    def __init__(self, model="gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model, temperature=0)

        self.system_prompt = SystemMessage(
            content=(
                "You are SupportAgent for SprintPlanner AI. "
                "Answer questions related to how the app works, "
                "idea submission, investor module, task generation, "
                "payments, roles, and general platform usage. "
                "Do NOT answer startup idea questions, that is handled by SimpleAgent."
            )
        )

    async def ask(self, query: str):
        messages = [
            self.system_prompt,
            HumanMessage(content=query)
        ]
        response = await self.llm.ainvoke(messages)
        return response.content
