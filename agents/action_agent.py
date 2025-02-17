from agents.base_agent import BaseAgent
from agents.common import construct_text, format_prompt
import json
from tools.llm import call_openai
from tools.format import extract_code


# Define reusable rules
rules = [
    "Do not give any action that is irrelevant to the command.",
    "Each of units can only be used in the whole response once at most.",
    "If a unit is already performing an action as given command, you should ignore it, instead of giving a repeated action for it.",
    "VespeneGeyser cannot be harvested directly. Only mineral field and refinery can be harvested.",
    "One MineralField can only be harvested by one SCV.",
    "If one command cannot be finished, just ignore it.",
]
rules_prompt = "Rule checklist:\n" + "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(rules)])


# Define the prompt template
def create_action_prompt():
    return f"""
As a top-tier StarCraft II executor, your task is to give some actions to finish the given command as possible as you can.

{rules_prompt}

Your response should be an action JSON in the following format wrapped with triple backticks:
{format_prompt}
    """.strip()


class ActionAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_retry_attempts = 5

    def run(self, obs_text: str, command: str, verifier=None):
        prompt = create_action_prompt() + "\n\n" + construct_text({"Observation": obs_text, "Command": command})
        response = call_openai(prompt=prompt, **self.generation_config, need_json=True)[0]
        self.save_think(response)
        print(response)
        if verifier:
            for try_time in range(self.max_retry_attempts):
                ok, verification_message = verifier(response)
                if not ok:
                    self.save_think(verification_message)
                    print(verification_message)
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
                    response = call_openai(prompt=verification_message, history=history, **self.generation_config, need_json=True)[0]
                    self.save_think(response)
                    print(response)

        try:
            actions = extract_code(response)
            actions = json.loads(actions)
            assert isinstance(actions, list)
            return actions, self.think
        except Exception as e:
            return [], self.think
