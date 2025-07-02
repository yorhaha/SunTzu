from agents.common import construct_text, TechTree
from agents.base_agent import BaseAgent
from tools.format import extract_code, json_to_markdown, construct_ordered_list
import json


def construct_tech_tree_prompt(race: str):
    return f"""
Technology tree:
{TechTree[race]}
""".strip()

strategy_prompt = """
Our final aim: destroy all enemies as soon as possible.
Our strategy:
- Resource collection: produce workers and gather minerals and gas
- Development: build attacking units and structures
- Attacking: concentrate forces to search and destroy enemies proactively
""".strip()

def construct_plan_example(race: str):
    if race == "Terran":
        return """
Following are some examples:
- Do nothing and just wait;
- Train 1/2/3/... SCV/Marine/Viking/...
- Build a supply depot;
- Upgrade to Orbital Command;
- Attack visible enemies;
- ...
""".strip()
    elif race == "Protoss":
        return """
Following are some examples:
- Do nothing and just wait;
- Train 1/2/3/... Probe/Stalker/Zealot/...
- Build a Pylon;
- Upgrade to Warp Gate;
- Attack visible enemies;
- ...
""".strip()
    elif race == "Zerg":
        return """
Following are some examples:
- Do nothing and just wait;
- Train 1/2/3/... Drone/Zergling/Hydralisk/...
- Build a Hatchery;
- Upgrade to Lair;
- Attack visible enemies;
- ...
""".strip()
    else:
        raise ValueError(f"Unknown race: {race}")

def construct_rules(race: str):
    rules = [
        "Commands should be natural language, instead of code.",
        "Produce as many units with the strongest attack power as possible.",
        "The total cost of all commands should not exceed the current resources (minerals and gas).",
        "Commands should not send workers to gather resources because the system will do it automatically.",
        "Commands should not build redundant structures while the existing ones are idle.",
        "Commands should not use abilities that are not supported currently.",
        "Commands should not build a structure that is not needed now (e.g. build a Missile Turret but there is no enemy air unit).",
        "The unit production list capacity of structures is 5. If the list is full, do not add more units to it.",
    ]
    if race == "Terran":
        rules += [
            "Commands should not train too many SCVs or MULEs, whose number should not exceed the capacity of CommandCenter and Refinery.",
            "Commands can construct a new one Supply Depot only when the remaining unused supply is less than 7.",
        ]
    elif race == "Protoss":
        rules += [
            "Commands should not train too many Probes, whose number should not exceed the capacity of Nexus and Assimilator.",
            "Commands can construct a new one Pylon only when the remaining unused supply is less than 7.",
        ]
    elif race == "Zerg":
        rules += [
            "Commands should not train too many Drones, whose number should not exceed the capacity of Hatchery and Extractor.",
            "Commands can construct a new one Overlord only when the remaining unused supply is less than 7.",
        ]
    else:
        raise ValueError(f"Unknown race: {race}")
    return rules


############## Plan Role Prompt ###############
def create_plan_prompt(race: str, rules: list[str]):
    plan_example_prompt = construct_plan_example(race)
    tech_tree_prompt = construct_tech_tree_prompt(race)
    rules_prompt = "Rule checklist:\n" + construct_ordered_list(rules)
    return f"""
As a top-tier StarCraft II strategist, your task is to give one or more commands based on the current game state. Only give commands which can be executed immediately, instead of waiting for certain events.
{plan_example_prompt}

{tech_tree_prompt}

{strategy_prompt}

{rules_prompt}

Your commands should be a list JSON in the following format wrapped with triple backticks:
```
[
    "<command_1>",
    "<command_2>",
    ...
]
```
    """.strip()


############## Plan Critic Role Prompt ###############
def create_plan_critic_prompt(rules: list[str]):
    rules_prompt = "Rule checklist:\n" + construct_ordered_list(rules)
    return (
        """
As a top-tier StarCraft II player, your task is to verify that they have violated given rules. If so, please point out the errors and provide suggestions for improvement or removal. If OK, just tell it to output again.
%s

Analyze the given rules one by one, and then provide a summary for errors at the end as follows, wrapped with triple backticks::
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
    def __init__(self, race, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.race = race
        self.rules = construct_rules(race)
        self.plan_example = construct_plan_example(race)

        self.max_refine_times = 3
        self.think = []
        self.chat_history = []

    def gene_new_plan(self, obs_text: str, rules: list[str]):
        prompt = create_plan_prompt(self.race, rules) + "\n\n" + construct_text({"Observation": obs_text})
        prompt += "\nEach command should be natural language like examples. Think step by step."
        response, messages = self.llm_client.call(**self.generation_config, prompt=prompt, need_json=True)
        self.think.append([response])
        self.chat_history.append(messages)
        return json.loads(extract_code(response))

    def critic_plan(self, plan: list[str], obs_text: str, rules: list[str]):
        prompt = create_plan_critic_prompt(rules) + "\n\n"
        prompt += construct_text(
            {
                "Observation": obs_text,
                "Plan": plan,
            }
        )
        response, messages = self.llm_client.call(**self.generation_config, prompt=prompt, need_json=True)
        self.think[-1].append(response)
        self.chat_history.append(messages)
        return response

    def refine_plan(self, obs_text: str, plan: list[str], critic: str, rules: list[str]):
        gene_prompt = create_plan_prompt(self.race, rules) + "\n\n" + construct_text({"Observation": obs_text})
        history = [
            {"role": "user", "content": gene_prompt},
            {"role": "assistant", "content": json_to_markdown(plan)},
        ]
        prompt = (
            "Errors:\n"
            + critic
            + "\nAnalyze every error step by step. Fix them by adding, removing, or modifying commands. Give new commands finally."
        )
        response, messages = self.llm_client.call(**self.generation_config, prompt=prompt, history=history, need_json=True)
        self.think.append([response])
        self.chat_history.append(messages)
        return json.loads(extract_code(response))

    def refine_plan_until_ready(self, obs_text: str, plan: list[str], rules: list[str]):
        for _ in range(self.max_refine_times):
            critic = self.critic_plan(plan, obs_text, rules)
            critic = json.loads(extract_code(critic))
            if isinstance(critic, list):
                critic = {"error_number": len(critic), "errors": critic}
            if critic.get("error_number", 0) == 0:
                return plan
            critic = construct_ordered_list(critic.get("errors", []))
            plan = self.refine_plan(obs_text, plan, critic, rules)
        return plan

    def run(self, obs_text: str, verifier=None, suggestions: list[str] = []):
        self.think = []
        self.chat_history = []
        rules = self.rules + suggestions
        plan = self.gene_new_plan(obs_text, rules)
        if verifier == "llm":
            plan = self.refine_plan_until_ready(obs_text, plan, rules)
        return plan, self.think, self.chat_history
