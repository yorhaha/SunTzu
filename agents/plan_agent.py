from autogen import ConversableAgent

from agents.common import construct_text, TERRANN_TECH_TREE
from agents.base_agent import BaseAgent
from tools.llm import call_openai
import json

"""
- Command idle workers to gather resources

- Build more production units
- Build more ground attack units
- Build more air attack units
- Gather some units for the defense of a certain location
- Select some units to attack certain units of the enemy
- Upgrade structures or unlock new technologies
- Upgrading units
- Command some workers to collect Vespene Gas
- ...
"""

plan_role_prompt = f"""
As a top-tier StarCraft II strategist, your task is to give one or more commands based on the current game state.
Following are some examples:
- Train n SCV/Marine/...
- Build a supply depot;
- Build a refinery;
- Build a Barracks;
- Train n Marine;
- Upgrade to Orbital Command;
- Command 2 SCV to gather Vespene Gas;
- Command some units to attack visible enemies;
- ...

You are encouraged to:
- Collect more resources
- Develop a more advanced technology tree
- Build more attacking units
- Attack enemy invading units
Analyze the current game state and decide what to do next from above aims before providing a command list.

Tips:
- The number of Supplies should be 1-3 more than the number of Consumes for it to be appropriate; otherwise, you should produce SCVs or attack units as soon as possible;
- When resources are abundant, you should develop a more advanced technology tree while building an appropriate amount of attack and defense units.

Technology tree:
{TERRANN_TECH_TREE}

Your response should be a list json in the following format wrapped with triple backticks:
```
[
    "<command_1>",
    "<command_2>",
    ...
]
```
And the length of the command list should be less than 3.
""".strip()

class PlanHumanAgent(BaseAgent):
    def run(self, obs_text: str):
        human_plan = str(input("Please provide a plan: \n"))
        human_plan = human_plan.strip().split("; ")
        return "```\n" + json.dumps(human_plan, indent=2) + "\n```"

class PlanAgent(BaseAgent):
    def run(self, obs_text: str):    
        prompt = plan_role_prompt + "\n\n"
        prompt += construct_text(
            {
                "Observation": obs_text,
            }
        )
        prompt += "\nEach command should be natural language like examples."
        response = call_openai(
            model_name=self.llm_config["model"], prompt=prompt, max_tokens=512, n=1, temperature=0.0, service=self.service
        )[0]
        return response


plan_critic_role_prompt = """
As a top-tier StarCraft II player, your task is to judge if the given commands are feasible and practical based on the current game state. If not, please point out the errors and provide suggestions for improvement or removal. If OK, just tell it to output again.

You are encouraged to:
- Collect more resources
- Develop a more advanced technology tree
- Build more attacking units
- Attack enemy invading units

Some frequent errors:
- Commands are not supported by the unit or structure abilities.
- Commands some units to perform actions that are already being performed.
- Commands are not in natural language.
- Current resources are not enough for the given commands.
- Too soon or too late to develop certain technology trees.
- Build redundant units or buildings.
- Commands has been executed in the action history.
- Assign excess harvesters to a resource node or structure.
- Build a refinery on a Vespene Gas node that is already being harvested.

Your response should be simple and clear, and end with "Please provide a new improved command list".
""".strip()

plan_actor_role_prompt = plan_role_prompt


class PlanDiscussAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan_actor = ConversableAgent(
            name="PlanActor",
            system_message=plan_actor_role_prompt,
            llm_config=self.llm_config,
        )
        self.plan_critic = ConversableAgent(
            name="PlanCritic",
            system_message=plan_critic_role_prompt,
            llm_config=self.llm_config,
        )

    def run(self, obs_text: str):
        message = f"{obs_text}\nEach command should be natural language like examples."
        plan = self.plan_critic.initiate_chat(
            self.plan_actor,
            message=message,
            summary_method=None,
            max_turns=2,
        )
        return plan.chat_history[-1]["content"]
