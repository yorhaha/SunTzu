from agents.base_agent import BaseAgent
from agents.common import construct_text, format_prompt
import json
from tools.format import extract_code, constrcut_openai_qa


# Define reusable rules
rules = [
    "Do not give any action that is irrelevant to the command.",
    "Each of units can only be used in the whole response once at most.",
    "If a unit is already performing an action as given command, you should ignore it, instead of giving a repeated action for it.",
    "VespeneGeyser cannot be harvested directly. Only mineral field and refinery can be harvested.",
    "One MineralField can only be harvested by one SCV.",
    "If one command cannot be finished, just ignore it.",
    "If resource is not enough, just complete the most important part of the command.",
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
        self.think = []
        self.chat_history = []

    def run(self, obs_text: str, command: str, verifier=None):
        self.think = []
        self.chat_history = []
        prompt = create_action_prompt() + "\n\n" + construct_text({"Observation": obs_text, "Command": command})
        response, messages = self.llm_client.call(prompt=prompt, **self.generation_config, need_json=True)
        self.think.append([response])
        self.chat_history.append(messages)
        # print(response)
        
        if verifier:
            history = constrcut_openai_qa(prompt, response)
            for try_time in range(self.max_retry_attempts):
                ok, verification_message = verifier(response)
                if not ok:
                    self.think[-1].append(verification_message)
                    # print(verification_message)
                    
                    response, messages = self.llm_client.call(prompt=verification_message, history=history, **self.generation_config, need_json=True)
                    self.think.append([response])
                    self.chat_history.append(messages)
                    # print(response)
                    
                    history.extend(constrcut_openai_qa(verification_message, response))
                else:
                    break

        try:
            actions = extract_code(response)
            actions = json.loads(actions)
            assert isinstance(actions, list)
            return actions, self.think, self.chat_history
        except Exception as e:
            return [], self.think, self.chat_history
