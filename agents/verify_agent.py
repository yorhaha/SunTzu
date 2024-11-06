from autogen import ConversableAgent

from agents.common import construct_text
from agents.base_agent import BaseAgent
from tools.llm import call_openai

verify_role_prompt = f"""
As a top-tier StarCraft II strategist, your task is to give one or more commands based on the current game state.
Following are examples of commands you can give:
- Collect resources in a dispersed or centralized manner
- Build more production units
- Build more ground attack units
- Build more air attack units
- Gather some units for the defense of a certain location
- Select some units to attack certain units of the enemy
- Developing technology trees (constructing certain buildings)
- Upgrading units
- ...

Your response should be a list json in the following format wrapped with triple backticks:
```
[
    "<command_1>",
    "<command_2>",
    ...
]
```
And the length of the command list should be less than 4.
""".strip()


class VerifyAgent(BaseAgent):
    def run(self, obs_text: str):
        prompt = verify_role_prompt + "\n\n"
        prompt += construct_text(
            {
                "Observation": obs_text,
            }
        )
        response = call_openai(
            model_name=self.llm_config["model"], prompt=prompt, max_tokens=2048, n=1, temperature=0.0, service=self.service
        )[0]
        return response