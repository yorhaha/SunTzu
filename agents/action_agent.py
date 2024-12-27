from agents.base_agent import BaseAgent
from agents.common import format_prompt, construct_text
import json
from tools.llm import call_openai
from tools.format import extract_code

rules = [
    "Do not give any action that is irrelevant to the command.",
    "Each of units can only be used in the whole response once at most.",
    "If a unit is already performing an action as given command, you should ignore it, instead of giving a repeated action for it.",
    "VespeneGeyser cannot be harvested directly. Only mineral field and refinery can be harvested.",
    "One MineralField can only be harvested by one SCV.",
    "If one command connot be finished, just ignore it.",
]
rules_prompt = "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(rules)])
rules_prompt = "Rule checklist:\n" + rules_prompt

action_actor_role_prompt = f"""
As a top-tier StarCraft II executor, your task is to give some actions to finish the given command as possible as you can.

{rules_prompt}

Your response should be an action json in the following format wrapped with triple backticks:
{format_prompt}
""".strip()


class ActionAgent(BaseAgent):
    def run(self, obs_text: str, command: str, verifier=None):
        prompt = action_actor_role_prompt + "\n\n"
        prompt += construct_text(
            {
                "Observation": obs_text,
                "Command": command,
            }
        )
        response = call_openai(prompt=prompt, **self.generation_config)[0]
        if verifier:
            for try_time in range(5):
                ok, message = verifier(response)
                if not ok:
                    print(response)
                    print(message)
                    history = [
                        {
                            "role": "user",
                            "content": prompt,
                        },
                        {
                            "role": "assistant",
                            "content": response,
                        },
                    ]
                    response = call_openai(prompt="Verify failed: " + message, history=history, **self.generation_config)[0]

        try:
            actions = extract_code(response)
            return json.loads(actions)
        except Exception as e:
            return []
