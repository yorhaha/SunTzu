from agents.common import construct_text, TERRANN_TECH_TREE
from agents.base_agent import BaseAgent
from tools.llm import call_openai
from tools.format import extract_code, json_to_markdown
import json

tech_tree_prompt = f"""
Technology tree:
{TERRANN_TECH_TREE}
""".strip()

strategy_prompt = """
Our final aim: destroy all enemies as soon as possible.
Our strategy:
- Resource collection: produce SCVs (< 20); construct and gather Refinery
- Development: build attacking units and structures
- Attacking: concentrate forces to search and destroy enemies proactively
""".strip()

rules = [
    "Commands should be natural language, instead of code.",
    "The total cost of all commands should not exceed the current resources (minerals and gas).",
    "Commands should not build a structure which is already under construction.",
    "Only when the remaining unused supply is less than 6, construct a new one Supply Depot.",
    "Commands should not command some units to perform actions that are already being performed (e.g. harvesting resources).",
    "Commands should not build redundant buildings or units (e.g. >20 SCVs, or more than 1 Barracks).",
    "Commands cannot use abilities that are not supported by the unit or structure.",
    "Vespene Geyser cannot be harvested by SCV directly. A Refinery is needed.",
    # "If some SCVs are idle, command them to gather resources.",
    "Once we have more than 3 attackers, we should attack enemies proactively and immediately.",
    "Do not command SCVs to attack enemies.",
    "Build a structure that is not needed now (e.g. build a Missile Turret when there is no enemy air unit).",
    "Structure sequence: Supply Depot -> Refinery -> Barracks -> Tech lab -> Train many Marauder and Marine ...",
    "At least 5 Marines are needed once the Barracks is built.",
]
rules_prompt = "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(rules)])
rules_prompt = "Rule checklist:\n" + rules_prompt

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
plan_role_prompt = f"""
As a top-tier StarCraft II strategist, your task is to give one or more commands based on the current game state. Only give commands which can be executed immediately, instead of waiting for certain events.
{plan_example_prompt}

{tech_tree_prompt}

{strategy_prompt}

{rules_prompt}

Response format:
<Response start>
### Analysis for the current game state ###
1. Resource analysis
2. Technology tree analysis
3. Whether we are attacked and how to deal with it
4. Do we have a team (>= 3) of attackers to find and destroy the enemy? If so, attack enemy units/structures immediately.
5. What should we do now?

### Commands ###
Your commands should be a list json in the following format wrapped with triple backticks:
```
[
    "<command_1>",
    "<command_2>",
    ...
]
```
And the length of the command list should be less than 5.
<Response end>
""".strip()

plan_refine_role_prompt = f"""
As a top-tier StarCraft II strategist, your task is to give one or more commands based on the current game state. Only give commands which can be executed immediately, instead of waiting for certain events.
{plan_example_prompt}

{tech_tree_prompt}

{strategy_prompt}

{rules_prompt}

Your commands should be a list json in the following format wrapped with triple backticks:
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
plan_critic_role_prompt = (
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
        human_plan = str(input("Please provide a plan: \n"))
        human_plan = human_plan.strip().split("; ")
        return "```\n" + json.dumps(human_plan, indent=2) + "\n```"


class PlanAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_refine_times = 3

    def gene_new_plan(self, obs_text: str):
        prompt = plan_role_prompt + "\n\n" + construct_text({"Observation": obs_text})
        prompt += "\nEach command should be natural language like examples."
        response = call_openai(**self.generation_config, prompt=prompt, need_json=True)[0]
        print("========= Plan =========")
        print(response)
        return json.loads(extract_code(response))

    def critic_plan(self, plan: list[str], obs_text: str):
        prompt = plan_critic_role_prompt + "\n\n"
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
        gene_prompt = plan_refine_role_prompt + "\n\n" + construct_text({"Observation": obs_text})
        history = [
            {"role": "user", "content": gene_prompt},
            {"role": "assistant", "content": json_to_markdown(plan)},
        ]
        prompt = (
            critic
            + "\nAnalyze every error and provide revised commands. Each command should be natural language like examples."
        )
        response = call_openai(**self.generation_config, prompt=prompt, history=history, need_json=True)[0]
        print("========= Refine =========")
        print(response)
        return json.loads(extract_code(response))

    def run(self, obs_text: str):
        plan = self.gene_new_plan(obs_text)
        for _ in range(self.max_refine_times):
            critic = self.critic_plan(plan, obs_text)
            critic = json.loads(extract_code(critic))
            if critic["error_number"] == 0:
                break
            critic = "\n".join(critic["errors"])
            plan = self.refine_plan(obs_text, plan, critic)
        return plan
