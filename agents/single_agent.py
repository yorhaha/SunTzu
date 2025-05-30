from agents.common import construct_text, format_prompt
from agents.base_agent import BaseAgent
from agents.plan_agent import tech_tree_prompt, strategy_prompt, default_rules
from tools.llm import call_openai
from tools.format import extract_code, constrcut_openai_qa
import json


def create_single_prompt():
    rules_prompt = "Rule checklist:\n" + "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(default_rules[1:])])
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
        self.think = []

    def run(self, obs_text: str, verifier=None):
        self.think = []
        prompt = (
            create_single_prompt()
            + "\n\n"
            + construct_text({"Observation": obs_text})
            + f"\n\nYour response should be an action JSON in the following format wrapped with triple backticks:\n{format_prompt}"
        )
        response = call_openai(prompt=prompt, **self.generation_config, need_json=True)
        self.think.append([response])
        print(response)
        
        if verifier:
            history = constrcut_openai_qa(prompt, response)
            for try_time in range(self.max_retry_attempts):
                ok, verification_message = verifier(response)
                if not ok:
                    self.think[-1].append(verification_message)
                    print(verification_message)
                    
                    response = call_openai(prompt=verification_message, history=history, **self.generation_config, need_json=True)
                    self.think.append([response])
                    print(response)
                    
                    history.extend(constrcut_openai_qa(verification_message, response))
                else:
                    break

        try:
            actions = extract_code(response)
            actions = json.loads(actions)
            assert isinstance(actions, list)
            return actions, self.think
        except Exception as e:
            return [], self.think
