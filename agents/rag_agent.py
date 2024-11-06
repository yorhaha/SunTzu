from autogen import ConversableAgent

from agents.base_agent import BaseAgent

rag_role_prompt = """
As a top-tier StarCraft II strategist, your task is to generate a query sentence based on the given context. The query should be concise and clear to get the key information.
""".strip()


class RagAgent(BaseAgent):
    def __init__(self, model_name: str):
        super().__init__(model_name)
        self.rag_agent = ConversableAgent(
            name="RagAgent",
            llm_config=self.llm_config,
        )

    def generate_reply(self, messages: list):
        return self.rag_agent.generate_reply(messages=messages)
