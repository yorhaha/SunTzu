from autogen import ConversableAgent

from agents.base_agent import BaseAgent


analysis_critic_role_prompt = """
As a top-tier StarCraft II strategist, your task is to:
1. firstly, ask another strategist to give analysis based on current game stage.
2. secondly, point out specific errors for given analysis, and end your response with "Please provide a new improved analysis"
Note: just focus on the errors and don't provide a new analysis.
""".strip()

analysis_actor_role_prompt = """
As a top-tier StarCraft II strategist, your task is to give practical and feasible game analysis based on given information for the current game. Your analysis format should be:

1. Own ground offensive force: ...
2. Own ground defense force: ...
3. Own air attack force: ...
4. Own air defense force: ...

Note: just focus on the situation analysis and don't provide any suggestions.
""".strip()


class AnalysisDiscussAgent(BaseAgent):
    def __init__(self, model_name: str):
        super().__init__(model_name)
        self.analysis_critic = ConversableAgent(
            name="AnalysisCritic",
            system_message=analysis_critic_role_prompt,
            llm_config=self.llm_config,
        )
        self.analysis_actor = ConversableAgent(
            name="AnalysisActor",
            system_message=analysis_actor_role_prompt,
            llm_config=self.llm_config,
        )

    def run(self, obs_text: str):
        analysis = self.analysis_critic.initiate_chat(
            self.analysis_actor,
            message=obs_text,
            summary_method=None,
            max_turns=2,
        )
        return analysis
