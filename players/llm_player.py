from .base_player import BasePlayer
from agents import PlanAgent, ActionAgent, RagAgent, SingleAgent


class LLMPlayer(BasePlayer):
    def __init__(self, config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.config = config
        
        agent_config = {
            "model_name": self.model_name,
            "service": self.service,
            "vllm_base_url": self.vllm_base_url,
            **self.generation_config,
        }
        
        if config.enable_rag:
            self.rag_agent = RagAgent(**agent_config)
        if config.enable_plan or config.enable_plan_verifier:
            self.plan_agent = PlanAgent(**agent_config)
            self.action_agent = ActionAgent(**agent_config)
        else:
            self.agent = SingleAgent(**agent_config)
        
        self.plan_verifier = "llm" if config.enable_plan_verifier else None
        self.action_verifier = self.verify_actions if self.config.enable_action_verifier else None

    async def run(self, iteration: int):
        if iteration % 5 == 0:
            await self.distribute_workers()
        # 100 -> 17s
        if iteration % 10 == 0 and self.minerals > 170:
            self.logging("iteration", iteration, level="info", save_trace=True, print_log=False)
            obs_text = await self.obs_to_text()
            
            if self.config.enable_rag:
                rag_summary, rag_think = self.rag_agent.run(obs_text)
                self.logging("rag_summary", rag_summary, save_trace=True)
                self.logging("rag_think", rag_think, save_trace=True, print_log=False)
                obs_text += "\n\n# Hint\n" + rag_summary

            if self.config.enable_plan or self.config.enable_plan_verifier:
                plans, plan_think = self.plan_agent.run(obs_text, verifier=self.plan_verifier)
                self.logging("plans", plans, save_trace=True)
                self.logging("plan_think", plan_think, save_trace=True, print_log=False)
                plans = "\n".join([f"{i + 1}. {plan}" for i, plan in enumerate(plans)])

                
                actions, action_think = self.action_agent.run(obs_text, plans, verifier=self.action_verifier)
                self.logging("actions", actions, save_trace=True)
                self.logging("action_think", action_think, save_trace=True, print_log=False)
            else:
                actions, action_think = self.agent.run(obs_text, verifier=self.action_verifier)
                self.logging("actions", actions, save_trace=True)
                self.logging("action_think", action_think, save_trace=True, print_log=False)

            await self.run_actions(actions)
