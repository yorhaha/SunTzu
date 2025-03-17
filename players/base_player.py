from sc2.bot_ai import BotAI
from sc2.units import Units
from sc2.unit import Unit
from sc2.units import Units
from sc2.unit import Unit
from sc2.position import Point2
from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId

import time
import os
import json
import pandas as pd

from tools.logger import setup_logger
from tools.format import extract_code
from tools.ops import IterativeMean

ignore_actions = []


class TargetType:
    NONE = "None"
    POINT = "Point"
    UNIT = "Unit"
    POINT_OR_UNIT = "PointOrUnit"


def load_knowledge():
    TerranAbilityData = pd.read_csv("knowledge/TerranAbility.csv")
    with open("knowledge/data.json", "r") as f:
        game_data = json.load(f)

    TerranAbility = {}
    for idx, item in TerranAbilityData.iterrows():
        ability = item["ability"]
        description = item["description"]
        ability_data = [item for item in game_data["Ability"] if item["name"] == ability]
        if len(ability_data) == 0:
            print("Ignored ability:", ability)
            continue
        ability_data = ability_data[0]
        target = ability_data["target"]
        if not isinstance(target, str):
            if "Build" in target:
                target = TargetType.POINT
            elif "BuildOnUnit" in target:
                target = TargetType.UNIT
            else:
                target = TargetType.NONE
        TerranAbility[ability] = {
            "enabled": item["enabled"],
            "description": description,
            "target": target,  # None, Point, Unit, PointOrUnit
        }
    return TerranAbility


TerranAbility = load_knowledge()


class BasePlayer(BotAI):
    def __init__(self, player_name, model_name, generation_config, log_path="logs", service="", vllm_base_url=None):
        super().__init__()

        if service == "vllm":
            assert vllm_base_url is not None, "vllm_base_url must be provided for vllm service"
        assert isinstance(generation_config, dict), "generation_config must be a dictionary"

        self.player_name = player_name
        self.model_name = model_name
        self.generation_config = generation_config
        self.service = service
        self.vllm_base_url = vllm_base_url

        time_str = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
        self.real_model_name = self.model_name.split("/")[-1]
        self.log_path = f"{log_path}/{self.real_model_name}/{time_str}"
        os.makedirs(f"{self.log_path}/info", exist_ok=True)
        self.logger = setup_logger(f"{player_name}_{self.real_model_name}", log_dir=self.log_path)

        self._tag_to_id = {}
        self._id_to_tag = {}
        self._id_to_abilities = {}
        self.next_id = 1

        self.last_action = []
        self.trace = {}
        self.tag_to_health = {}

        self.sbr = IterativeMean()
        self.resource_cost = 0
        self.n_supply_army = []
        self.n_supply_workers = []
        self.n_structure = []

    def logging(self, key: str, value, level="info", save_trace=False, save_file=False, print_log=True):
        idx = self.state.game_loop
        if level in ["info", "warning", "error"] and print_log:
            text = f"({idx}) {key}: {str(value)}"
            if level == "info":
                self.logger.info(text)
            elif level == "warning":
                self.logger.warning(text)
            elif level == "error":
                self.logger.error(text)

        if save_trace:
            if idx not in self.trace:
                self.trace[idx] = {}
            self.trace[idx][key] = value
            with open(f"{self.log_path}/trace.json", "w", encoding="utf-8") as f:
                json.dump(self.trace, f, indent=2, ensure_ascii=False)

        if save_file:
            with open(f"{self.log_path}/info/{idx}-{key}.txt", "w", encoding="utf-8") as f:
                if isinstance(value, list) or isinstance(value, dict):
                    value = json.dumps(value, indent=2, ensure_ascii=False)
                f.write(value)

    async def on_end(self, game_result):
        game_result = game_result.name
        self.logging("game_result", game_result, save_trace=True)
        self.logging("SBR", round(self.sbr.mean, 4), save_trace=True)
        
        time_cost = self.time_formatted.split(":")
        time_cost = int(time_cost[0]) * 60 + int(time_cost[1])
        self.logging("time_cost", time_cost, save_trace=True)
        self.logging("RUR", round(self.resource_cost / time_cost, 4), save_trace=True)
        
        self.logging("n_supply_army", self.n_supply_army, save_trace=True, print_log=False)
        self.logging("n_supply_workers", self.n_supply_workers, save_trace=True, print_log=False)
        self.logging("n_structure", self.n_structure, save_trace=True, print_log=False)

        with open(f"{self.log_path}/trace.json", "w", encoding="utf-8") as f:
            json.dump(self.trace, f, indent=2, ensure_ascii=False)

    def update_tag_to_health(self):
        self.tag_to_health = {unit.tag: unit.health for unit in self.units}
        self.tag_to_health.update({unit.tag: unit.health for unit in self.structures})

    async def on_step(self, iteration: int):
        # before run
        if len(self.units) == 0 or len(self.structures) == 0:
            return
        self.sbr.update(int(self.supply_used == self.supply_cap))
        
        if iteration % 10 == 0:
            self.n_supply_army.append(self.supply_army)
            self.n_supply_workers.append(self.supply_workers)
            self.n_structure.append(len(self.structures))

        await self.run(iteration)

        # after run
        if iteration % 15 == 0:
            self.update_tag_to_health()

    async def run(self, iteration: int):
        raise NotImplementedError

    def verify_actions(self, actions):
        if isinstance(actions, str):
            try:
                actions = json.loads(extract_code(actions))
            except json.JSONDecodeError:
                return False, "Action must be a json list wrapped with triple backticks and without comments"
        if not isinstance(actions, list):
            return False, "Action must be a list"

        errors = []
        cost_minerals, cost_vespene, cost_supply = 0, 0, 0
        for action in actions:
            ok, message_or_cost = self.check_action(action)
            if not ok:
                errors.append(json.dumps(action, indent=2, ensure_ascii=False) + "\n>> Error: " + message_or_cost)
            else:
                cost_minerals += message_or_cost[0]
                cost_vespene += message_or_cost[1]
                cost_supply += message_or_cost[2]
        
        if self.minerals < cost_minerals:
            errors.append(">>>> Total actions error: minerals is not enough for executing all actions")
        if self.vespene < cost_vespene:
            errors.append(">>>> Total actions error: vespene is not enough for executing all actions")
        if self.supply_left < cost_supply:
            errors.append(">>>> Total actions error: supply is not enough for executing all actions")
            
        if errors:
            return False, "\n\n".join(errors)
        return True, ""

    def check_action(self, action: dict):
        if not isinstance(action, dict):
            return False, "Action must be a dictionary"

        ### required keys checks
        # action check
        base_keys = ["action", "units"]
        for key in base_keys:
            if key not in action:
                return False, f"Missing required key: {key}"
        action_name = action["action"]
        if action_name not in TerranAbility:
            return False, f"Unknown action: {action['action']}"
        # target check
        target_type = TerranAbility[action_name]["target"]
        if target_type == TargetType.NONE:
            required_keys = base_keys
        elif target_type == TargetType.POINT:
            required_keys = base_keys + ["target_position"]
        elif target_type == TargetType.UNIT:
            required_keys = base_keys + ["target_unit"]

        if target_type != TargetType.POINT_OR_UNIT:
            unused_keys = [key for key in action.keys() if key not in required_keys]
            for key in required_keys:
                if key not in action:
                    return False, f"Missing required key: {key}"
        else:
            if "target_position" in action and "target_unit" in action:
                return False, "Cannot have both `target_position` and `target_unit`"
            if "target_position" not in action and "target_unit" not in action:
                return False, "Missing required key: target_position or target_unit"
            unused_keys = [key for key in action.keys() if key not in base_keys + ["target_position", "target_unit"]]
        ### unused keys check
        if unused_keys:
            unused_keys = [key for key in action.keys() if key not in ["action", "units"]]
            return False, f"Unused keys: {unused_keys}"

        ### value check
        if not isinstance(action_name, str):
            return False, "`action` must be a string"
        if not isinstance(action["units"], list) and len(action["units"]) > 0:
            return False, "`units` must be a non-empty list of integers"
        if "target_position" in action:
            if not (len(action["target_position"]) == 2 and all(isinstance(i, int) for i in action["target_position"])):
                return False, "`target_position` must be a list of two integers"
        if "target_unit" in action:
            if not isinstance(action["target_unit"], int):
                return False, "`target_unit` must be an integer"
            if action["target_unit"] not in self._id_to_tag:
                return False, f"Unit with id {action['target_unit']} not found"
            target_unit = self.get_unit_by_id(action["target_unit"])
            if target_unit is None:
                return False, f"Unit with id {action['target_unit']} not found"
            if action_name == "HARVEST_GATHER_SCV":
                if target_unit.name not in ["MineralField", "MineralField750", "Refinery"]:
                    return (
                        False,
                        f"Unit [{action['target_unit']}]{target_unit.name} cannot be harvested or has been consumed. Only mineral field and refinery can be harvested.",
                    )
                if target_unit.build_progress < 1.0:
                    return False, f"Unit [{action['target_unit']}]{target_unit.name} is still building"
                if target_unit.ideal_harvesters > 0 and target_unit.assigned_harvesters >= target_unit.ideal_harvesters:
                    return False, f"Unit [{action['target_unit']}]{target_unit.name} is fully harvested"

        ### unit checks
        for unit_id in action["units"]:
            if not isinstance(unit_id, int):
                return False, "`units` must be a list of integers"
            if unit_id not in self._id_to_tag:
                return False, f"Unit with id {unit_id} not found"
            if unit_id not in self._id_to_abilities:
                return False, f"Unit with id {unit_id} not found"
            unit = self.get_unit_by_id(unit_id)
            if not unit:
                return False, f"Unit {unit_id} doesn't exist"
            if not unit.is_mine:
                return False, f"Unit {unit_id} is not mine"
            if action_name not in self._id_to_abilities[unit_id]:
                return False, f"[{unit_id}]{unit.name} cannot perform action {action_name} or resource is not enough"
            if unit.is_constructing_scv:
                return False, f"[{unit_id}]{unit.name} is constructing, cannot perform other actions"

        ### action_name check
        building_units = self.get_building_units()
        building_units = [name.lower() for name in building_units]
        if action_name.startswith("TERRANBUILD_") or action_name.startswith("BUILD_"):
            build_name = action_name.split("_")[1].lower()
            if build_name in building_units:
                return False, f"[{action['units'][0]}]{self.units[0].name} is already under construction"
        if action_name == "TERRANBUILD_SUPPLYDEPOT":
            if self.supply_cap - self.supply_used >= 7:
                return False, "There is still space for supply depot, no need to build new Supply Depot."
        
        ### resource check
        cost = self.calculate_cost(AbilityId[action_name]) * len(action["units"])
        if self.minerals < cost.minerals:
            return False, f"Minerals is not enough for action {action_name}"
        if self.vespene < cost.vespene:
            return False, f"Vespene is not enough for action {action_name}"
        supply_cost = self.calculate_supply_cost(AbilityId[action_name]) * len(action["units"])
        if self.supply_left < supply_cost:
            return False, f"Supply is not enough for action {action_name}"

        return True, [cost.minerals, cost.vespene, supply_cost]

    def get_building_units(self):
        building_units = []
        for unit in self.units:
            if unit.build_progress < 1.0:
                building_units.append(unit)
        return [unit.name for unit in building_units]

    ################ tag id mapping
    def tag_to_id(self, tag: int):
        if tag not in self._tag_to_id:
            next_id = tag % 1000
            while next_id in self._id_to_tag:
                next_id = (next_id + 1) % 1000
            self._tag_to_id[tag] = next_id
            self._id_to_tag[next_id] = tag
            # self._tag_to_id[tag] = self.next_id
            # self._id_to_tag[self.next_id] = tag
            # self.next_id += 1
        return self._tag_to_id[tag]

    def id_to_tag(self, _id: int):
        return self._id_to_tag[_id]

    def get_unit_by_tag(self, tag: int):
        unit = self.all_units.find_by_tag(tag)
        return unit

    def get_unit_by_id(self, _id: int):
        tag = self.id_to_tag(_id)
        return self.get_unit_by_tag(tag)

    ################ run actions
    async def run_actions(self, actions):
        for action in actions:
            try:
                action_check_result, action_check_msg = self.check_action(action)
                if not action_check_result:
                    action["is_valid"] = False
                    action["error"] = action_check_msg
                else:
                    for unit_id in action["units"]:
                        ability = AbilityId[action["action"]]
                        target = None
                        available_abilities = await self.get_available_abilities([self.get_unit_by_id(unit_id)])
                        assert ability in available_abilities[0], f"Unit {unit_id} cannot perform action {action['action']}"
                        if "target_unit" in action:
                            target = self.get_unit_by_id(action["target_unit"])
                            assert target is not None, f"Unit with id {action['target_unit']} not found"
                        elif "target_position" in action:
                            target = Point2(action["target_position"])
                            if "BUILD_" in ability.name:
                                target = await self.find_placement(ability, target, max_distance=1000)
                            assert target is not None, f"Invalid target position: {action['target_position']}"
                        self.get_unit_by_id(unit_id)(ability=ability, target=target)
                        cost = self.calculate_cost(ability)
                        self.resource_cost += cost.minerals + cost.vespene
            except Exception as e:
                action["is_valid"] = False
                action["error"] = str(e)

        self.logging("valid_actions", "\n" + json.dumps(actions, indent=2, ensure_ascii=False))
        self.logging("valid_actions", actions, save_trace=True, print_log=False)
        valid_actions = [json.dumps(action, ensure_ascii=False) for action in actions if action.get("is_valid", True)]
        self.last_action.extend(valid_actions)

    ################ obs to text
    async def obs_to_text(self):
        obs = {}
        obs["Round state"] = self.round_state_to_text()
        obs["Own units"] = await self.units_to_text(self.units)
        obs["Unit abilities"] = await self.abilities_to_text(self.units)
        obs["Own structures"] = await self.structures_to_text(self.structures)
        obs["Structure abilities"] = await self.abilities_to_text(self.structures)
        obs["Visible enemy units"] = await self.units_to_text(self.enemy_units)
        obs["Visible enemy structures"] = await self.structures_to_text(self.enemy_structures)
        obs["Action history"] = self.action_history_to_text()
        obs["Map information"] = self.miner_to_text() + "\n" + self.gas_to_text()
        obs["Ability description"] = self.get_ability_desc(obs["Unit abilities"] + obs["Structure abilities"])
        obs_text = "\n\n".join([f"# {key}\n{value}" for key, value in obs.items()])

        self.logging("obs", obs, save_trace=True, print_log=False)
        self.logging("obs_text", obs_text, save_file=True, print_log=False)
        return obs_text

    def get_ability_desc(self, text: str):
        desc = []
        for action in TerranAbility:
            if TerranAbility[action].get("enabled", False) and action in text:
                action_desc = TerranAbility[action]["description"]
                action_keys = TerranAbility[action]["target"]
                desc.append(f"{action}(target: {action_keys}): {action_desc}")
                try:
                    cost = self.units[0]._bot_object.game_data.calculate_ability_cost(AbilityId[action])
                    if cost.minerals and cost.vespene:
                        desc[-1] += f" Cost: {cost.minerals} minerals, {cost.vespene} vespene."
                    elif cost.vespene:
                        desc[-1] += f" Cost: {cost.vespene} vespene."
                    elif cost.minerals:
                        desc[-1] += f" Cost: {cost.minerals} minerals."
                except Exception as e:
                    pass
        return "\n".join(desc)

    async def structures_to_text(self, structures: Units):
        if len(structures) == 0:
            return "[Empty]"
        return "\n".join([await self.unit_to_text(structure) for structure in structures])

    def round_state_to_text(self):
        text = ""
        text += "Time: {}\n".format(self.time_formatted)
        text += "Race: {}\n".format(self.race.name)
        text += "Minerals: {}\n".format(self.minerals)
        text += "Vespene: {}\n".format(self.vespene)
        text += "Supply army: {}\n".format(self.supply_army)
        text += "Supply workers: {}\n".format(self.supply_workers)
        text += "Supply unused: {}".format(self.supply_cap - self.supply_used)

        return text.strip()

    def action_history_to_text(self):
        if len(self.last_action) == 0:
            return "[Empty]"
        return "\n".join(self.last_action[-10:])

    async def units_to_text(self, units: Units):
        if len(units) == 0:
            return "[Empty]"
        return "\n".join([await self.unit_to_text(unit) for unit in units])

    async def unit_to_text(self, unit: Unit):
        text = ""

        if unit.build_progress == 1.0:
            text += f"[{self.tag_to_id(unit.tag)}]{unit.name}\n"
        else:
            text += f"[{self.tag_to_id(unit.tag)}]{unit.name}(building {int(unit.build_progress * 100)}%)\n"
        text += f"Position: ({int(unit.position.x)}, {int(unit.position.y)})\n"

        if unit.build_progress == 1.0:
            if int(unit.health_max) and unit.build_progress == 1.0:
                text += f"Health: {int(unit.health)}/{int(unit.health_max)} ({int(unit.health_percentage * 100)}%)\n"
            if unit.shield_max > 0.0:
                text += f"Shield: {int(unit.shield)}/{int(unit.shield_max)}\n"
            if unit.energy_max > 0.0:
                text += f"Energy: {int(unit.energy)}/{int(unit.energy_max)}\n"
            if unit.is_mine:
                states = self.unit_state_to_text(unit)
                if states:
                    text += f"State: {states}\n"

                assigned = unit.assigned_harvesters
                ideal = unit.ideal_harvesters
                surplus = unit.surplus_harvesters
                if ideal > 0:
                    if surplus > 0:
                        text += f"Harvesters: {assigned}/{ideal} (no more SCV accepted, surplus {surplus})\n"
                    elif surplus == 0:
                        text += f"Harvesters: {assigned}/{ideal} (no more SCV accepted)\n"
                    else:
                        text += f"Harvesters: {assigned}/{ideal}\n"

                # Production list
                if unit.is_structure:
                    production_list = []
                    unit_orders = unit.orders
                    for unit_order in unit_orders:
                        if "Train " in unit_order.ability.friendly_name:
                            production_list.append(unit_order.ability.friendly_name[6:])
                    if production_list:
                        text += f"Production list: {', '.join(production_list)}\n"
        return text.strip()

    async def abilities_to_text(self, units: Units):
        unit_name_to_abilities = {}
        text = ""
        for unit in units:
            if not unit.build_progress == 1.0:
                continue
            abilities = await self.unit_ability_to_text(unit)
            if unit.name not in unit_name_to_abilities:
                unit_name_to_abilities[unit.name] = abilities
                if abilities:
                    text += f"{unit.name}: {abilities}\n"

        return text.strip()

    async def unit_ability_to_text(self, unit: Unit):
        abilities = []
        ability_ids = await self.get_available_abilities([unit], ignore_resource_requirements=True)
        valid_ability_ids = []
        for ability_id in ability_ids[0]:
            if ability_id.name == "NULL_NULL":
                continue
            if ability_id.name not in TerranAbility:
                ignore_actions.append(ability_id.name)
                print(f"Unknown ability: {ability_id.name}")
                # pdb.set_trace()
            elif TerranAbility[ability_id.name].get("enabled", False):
                valid_ability_ids.append(ability_id)
        abilities = [ability_id.name for ability_id in valid_ability_ids]
        # if unit.name == "SCV":
        #     abilities = [a for a in abilities if a not in ["MOVE_MOVE", "ATTACK_ATTACK", "EFFECT_REPAIR_SCV"]]
        self._id_to_abilities[self.tag_to_id(unit.tag)] = abilities
        abilities = ", ".join(abilities)

        return abilities

    def unit_state_to_text(self, unit: Unit):
        order_target = unit.order_target or ""
        order_target_name = ""
        if order_target:
            if isinstance(order_target, Point2):
                order_target = f"({int(order_target.x)}, {int(order_target.y)})"
            elif isinstance(order_target, int):
                target_unit = self.get_unit_by_tag(order_target)
                if target_unit:
                    order_target_name = self.get_unit_by_tag(order_target).name
                    order_target = self.tag_to_id(order_target)

        states = []
        if unit.is_moving:
            if order_target:
                states.append(f"moving to [{order_target}]{order_target_name}")
            else:
                states.append("moving")
        if unit.is_attacking:
            if order_target:
                states.append(f"attacking [{order_target}]{order_target_name}")
            else:
                states.append("attacking")
        if unit.is_repairing:
            if order_target:
                states.append(f"repairing [{order_target}]{order_target_name}")
            else:
                states.append("repairing")
        # if unit.is_gathering:
        #     if order_target:
        #         states.append(f"gathering [{order_target}]{order_target_name}")
        #     else:
        #         states.append("gathering")

        if unit.is_idle:
            states.append("idle")
        if unit.is_flying:
            states.append("flying")
        if unit.is_transforming:
            states.append("transforming")
        if unit.is_patrolling:
            states.append("patrolling")
        if unit.tag in self.tag_to_health and unit.health < self.tag_to_health[unit.tag]:
            states.append("under attack")

        if unit.is_constructing_scv:
            states.append("constructing")

        return "|".join(states)

    def miner_to_text(self):
        center = self.start_location
        miners = []
        num_SCV = len([unit for unit in self.units if unit.name == "SCV"])
        cloest_miners = self.mineral_field.closest_n_units(center, 100)
        cloest_miners = [mineral for mineral in cloest_miners if mineral.mineral_contents > 0]
        cloest_miners = cloest_miners[: 2 * num_SCV]
        for mineral in cloest_miners:
            miners.append(f"[{self.tag_to_id(mineral.tag)}]({int(mineral.position.x)}, {int(mineral.position.y)})")
        if len(miners) == 0:
            return "No mineral fields found"
        return "Closest mineral fields: " + ", ".join(miners)

    def gas_to_text(self):
        center = self.start_location
        gases = []
        cloest_gases = self.vespene_geyser.closest_n_units(center, 100)
        cloest_gases = [gas for gas in cloest_gases if gas.vespene_contents > 0]
        cloest_gases = cloest_gases[:10]
        for gas in cloest_gases:
            gases.append(f"[{self.tag_to_id(gas.tag)}]({int(gas.position.x)}, {int(gas.position.y)})")
        if len(gases) == 0:
            return "No vespene geysers found"
        return "Closest vespene geysers: " + ", ".join(gases)
