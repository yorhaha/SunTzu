from autogen import ConversableAgent

from agents.base_agent import BaseAgent
from agents.common import format_prompt, construct_text
from tools.llm import call_openai

action_actor_role_prompt = f"""
As a top-tier StarCraft II executor, your task is to give some actions to finish the given command as possible as you can.
If the command connot be finished, just given empty actions.

Requirements:
1. Each of our units can only be used in your whole response once at most.
2. If a unit is already performing an action as given command, you should not give a repeated action for it. And do not give some actions that are irrelevant to the command.
3. Your response should be an action json in the following format wrapped with triple backticks:
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
        response = call_openai(
            model_name=self.llm_config["model"],
            prompt=prompt,
            max_tokens=512,
            n=1,
            temperature=self.temperature,
            service=self.service
        )[0]
        if verifier:
            retry_count = 0
            while retry_count < 5:
                ok, message = verifier(response)
                if not ok:
                    print(response)
                    print(message)
                    retry_count += 1
                    history = [
                        {
                            "role": "user",
                            "content": prompt,
                        },
                        {
                            "role": "assistant",
                            "content": response,
                        }
                    ]
                    response = call_openai(
                        model_name=self.llm_config["model"],
                        prompt="Verify failed: " + message,
                        max_tokens=2048,
                        history=history,
                        n=1,
                        temperature=self.temperature,
                        service=self.service
                    )[0]
                else:
                    break
        return response


action_critique_role_prompt = """
As a top-tier StarCraft II strategist, your task is to:
1. firstly, ask another strategist to give an action list strictly following given plan
2. secondly, point out specific errors for given the actions and end with "Please provide a new improved action list"
Note: just focus on the errors and don't provide a new action list. Some error types:
- Actions are not supported by the unit or structure abilities.
- Command some units to perform actions that are already being performed.
- Not following the given plan.
""".strip()


class ActionDiscussAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.action_critic = ConversableAgent(
            name="ActionCritic",
            system_message=action_critique_role_prompt,
            llm_config=self.llm_config,
        )
        self.action_actor = ConversableAgent(
            name="ActionActor",
            system_message=action_actor_role_prompt,
            llm_config=self.llm_config,
        )

    def run(self, obs_text: str, plan: str):
        prompt = construct_text(
            {
                "Observation": obs_text,
                "Plan": plan,
            }
        )
        action = self.action_critic.initiate_chat(
            self.action_actor,
            message=prompt,
            summary_method=None,
            max_turns=1,
            silent=True,
        )
        return action


action_choose_role_prompt = """
As a top-tier StarCraft II strategist, your task is to choose the best action list based on the current game state. Remember to output the action list with the best performance.
""".strip()

action_choose_option_template = """
###Action list###
Option 1:
```
{action_list1}
```
Option 2:
```
{action_list2}
```
""".strip()


class ActionChooseAgent(BaseAgent):
    def __init__(self, model_name: str):
        super().__init__(model_name)
        self.action_actor = ConversableAgent(
            name="ActionChoose",
            system_message=action_choose_role_prompt,
            llm_config=self.llm_config,
        )

    def run(self, obs_text: str, action_list1: list, action_list2: list):
        history = [
            {
                "content": obs_text
                + "\n\n"
                + action_choose_option_template.format(
                    action_list1="\n".join(action_list1),
                    action_list2="\n".join(action_list2),
                ),
                "role": "user",
            }
        ]
        action = self.action_actor.generate_reply(
            messages=history,
        )
        history.append({"content": action, "role": "assistant"})
        return history
