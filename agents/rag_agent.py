from autogen import ConversableAgent

from agents.base_agent import BaseAgent

rag_role_prompt = """
As a top-tier StarCraft II strategist, your task is to generate a query sentence based on the given context. The query should be concise and clear to get the key information.
""".strip()


class RagAgent(BaseAgent):
    pass