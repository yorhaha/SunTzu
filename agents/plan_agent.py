from agents.common import construct_text, TERRANN_TECH_TREE
from agents.base_agent import BaseAgent
from tools.llm import call_openai
from tools.format import extract_code, json_to_markdown
import json


def construct_ordered_list(items: list[str]) -> str:
    return "\n".join([f"{i+1}. {item}" for i, item in enumerate(items)])


# Define reusable prompts
tech_tree_prompt = f"""
Technology tree:
{TERRANN_TECH_TREE}
""".strip()

strategy_prompt = """
Our final aim: destroy all enemies as soon as possible.
Our strategy:
- Resource collection: produce SCVs; construct and gather Refinery
- Development: build attacking units and structures
- Attacking: concentrate forces to search and destroy enemies proactively
""".strip()

rules = [
    "Commands should be natural language, instead of code.",
    "Base structures development: Supply Depot -> Refinery -> 2 Barracks ...",
    "Attacking units development: 3 Marines -> Tech lab -> many Marauder and Marine ...",
    "Marauder is the key to gain victory, which needs a Tech lab based on an idle Barracks. So it's wrong to use all Barracks to train Marine.",
    "The total cost of all commands should not exceed the current resources (minerals and gas).",
    "Vespene Geyser cannot be harvested by SCV directly. A Refinery is precondition.",
    "Commands should not train too many SCVs, whose number should not exceed the capacity of CommandCenter and Refinery.",
    "Commands should not allocate SCVs beyond the harvesters limit for Refinery.",
    "Commands should not build a structure which is already under construction.",
    "Commands should not build redundant structures(e.g. more than 2 Barracks).",
    "Commands should not use abilities that are not supported by the unit or structure.",
    "Commands should not build a structure that is not needed now (e.g. build a Missile Turret when there is no enemy air unit).",
    "The production list capacity of Barracks is 5. If the list is full, do not use it to train units.",
    "Only when the remaining unused supply is less than 6, construct a new one Supply Depot.",
]
rules_prompt = "Rule checklist:\n" + construct_ordered_list(rules)

plan_example_prompt = """
Following are some examples:
- Do nothing and just wait;
- Train 1/2/3/... SCV/Marine/Viking/...
- Build a supply depot;
- Upgrade to Orbital Command;
- Command 2 SCV to gather Vespene Gas;
- Attack visible enemies;
- ...
""".strip()


############## Plan Role Prompt ###############
def create_plan_prompt(with_cot=True):
    cot_prompt = """
### Analysis for the current game state ###
1. Resource analysis
2. Technology tree analysis
3. Our situation of being attacked and where it comes from
4. What should we do now
    """
    return f"""
As a top-tier StarCraft II strategist, your task is to give one or more commands based on the current game state. Only give commands which can be executed immediately, instead of waiting for certain events.
{plan_example_prompt}

{tech_tree_prompt}

{strategy_prompt}

{rules_prompt}

Response format:
<Response start>{cot_prompt if with_cot else ""}
### Commands ###
Your commands should be a list JSON in the following format wrapped with triple backticks:
```
[
    "<command_1>",
    "<command_2>",
    ...
]
```
<Response end>
    """.strip()


############## Plan Critic Role Prompt ###############
def create_plan_critic_prompt():
    return (
        """
As a top-tier StarCraft II player, your task is to verify that they have violated given rules. If so, please point out the errors and provide suggestions for improvement or removal. If OK, just tell it to output again.
%s

Analyze the given rules one by one, and then provide a summary for errors at the end as follows:
```
{
    "errors": [
        "Error 1: ...",
        "Error 2: ...",
        ...
    ],
    "error_number": 0/1/2/...
}
```
    """.strip()
        % rules_prompt
    )


class PlanHumanAgent(BaseAgent):
    def run(self, obs_text: str):
        human_plan = input("Please provide a plan: \n").strip()
        human_plan = human_plan.split("; ") if human_plan else []
        if not human_plan:
            print("No valid commands provided!")
            return []
        return "```\n" + json.dumps(human_plan, indent=2) + "\n```"


class PlanAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_refine_times = 3

    def gene_new_plan(self, obs_text: str):
        prompt = create_plan_prompt() + "\n\n" + construct_text({"Observation": obs_text})
        prompt += "\nEach command should be natural language like examples."
        response = call_openai(**self.generation_config, prompt=prompt, need_json=True)[0]
        print("========= Plan =========")
        print(response)
        return json.loads(extract_code(response))

    def critic_plan(self, plan: list[str], obs_text: str):
        prompt = create_plan_critic_prompt() + "\n\n"
        prompt += construct_text(
            {
                "Observation": obs_text,
                "Plan": plan,
            }
        )
        response = call_openai(**self.generation_config, prompt=prompt, need_json=True)[0]
        print("========= Critic =========")
        print(response)
        return response

    def refine_plan(self, obs_text: str, plan: list[str], critic: str):
        gene_prompt = create_plan_prompt(with_cot=False) + "\n\n" + construct_text({"Observation": obs_text})
        history = [
            {"role": "user", "content": gene_prompt},
            {"role": "assistant", "content": json_to_markdown(plan)},
        ]
        prompt = (
            "Errors:\n"
            + critic
            + "\nAnalyze every error step by step. Fix them by adding, removing, or modifying commands. Give new commands finally."
        )
        response = call_openai(**self.generation_config, prompt=prompt, history=history, need_json=True)[0]
        print("========= Refine =========")
        print(response)
        return json.loads(extract_code(response))

    def refine_plan_until_ready(self, obs_text: str, plan: list[str]):
        for _ in range(self.max_refine_times):
            critic = self.critic_plan(plan, obs_text)
            critic = json.loads(extract_code(critic))
            if critic.get("error_number", 0) == 0:
                return plan
            critic = construct_ordered_list(critic.get("errors", []))
            plan = self.refine_plan(obs_text, plan, critic)
        return plan

    def run(self, obs_text: str):
        plan = self.gene_new_plan(obs_text)
        plan = self.refine_plan_until_ready(obs_text, plan)
        return plan
