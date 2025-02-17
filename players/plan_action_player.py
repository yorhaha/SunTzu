from .base_player import BasePlayer
from agents import PlanAgent, ActionAgent


class PlanActionPlayer(BasePlayer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.plan_agent = PlanAgent(
            model_name=self.model_name,
            service=self.service,
            vllm_base_url=self.vllm_base_url,
            **self.generation_config,
        )
        self.action_agent = ActionAgent(
            model_name=self.model_name,
            service=self.service,
            vllm_base_url=self.vllm_base_url,
            **self.generation_config,
        )

    async def on_step(self, iteration: int):
        self.send_idle_scv_to_mineral()
        if len(self.units) == 0 or len(self.structures) == 0:
            return
        # 100 -> 17s
        if iteration % 10 == 0 and self.minerals > 170:
            self.logging("iteration", iteration, level="info", save_trace=True, print_log=False)
            obs_text = await self.obs_to_text()

            plans, plan_think = self.plan_agent.run(obs_text)
            self.logging("plans", plans, save_trace=True)
            self.logging("plan_think", plan_think, save_trace=True, print_log=False)
            plans = "\n".join([f"{i + 1}. {plan}" for i, plan in enumerate(plans)])

            actions, action_think = self.action_agent.run(obs_text, plans, verifier=self.verify_actions)
            self.logging("actions", actions, save_trace=True)
            self.logging("action_think", action_think, save_trace=True, print_log=False)

            await self.run_actions(actions)

        if iteration % 15 == 0:
            self.update_tag_to_health()
