from agents.common import construct_text, format_prompt
from agents.base_agent import BaseAgent
from agents.plan_agent import tech_tree_prompt, strategy_prompt, rules
from tools.llm import call_openai
from tools.format import extract_code
import json


def create_single_prompt():
    rules_prompt = "Rule checklist:\n" + "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(rules[1:])])
    return f"""
As a top-tier StarCraft II strategist, your task is to give one or more commands based on the current game state. Only give commands which can be executed immediately, instead of waiting for certain events.

{tech_tree_prompt}

{strategy_prompt}

{rules_prompt}
    """.strip()


class SingleAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_retry_attempts = 3

    def run(self, obs_text: str, verifier=None):
        prompt = (
            create_single_prompt()
            + "\n\n"
            + construct_text({"Observation": obs_text})
            + f"\n\nYour response should be an action JSON in the following format wrapped with triple backticks:\n{format_prompt}"
        )
        response = call_openai(**self.generation_config, prompt=prompt, need_json=True)[0]
        if verifier:
            for try_time in range(self.max_retry_attempts):
                ok, verification_message = verifier(response)
                if not ok:
                    print(response)
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
                    response = call_openai(prompt="Verify failed: " + verification_message, history=history, **self.generation_config)[0]

        try:
            actions = extract_code(response)
            return json.loads(actions)
        except Exception as e:
            return []
