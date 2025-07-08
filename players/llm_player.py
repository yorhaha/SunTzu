from .base_player import BasePlayer
from agents import PlanAgent, ActionAgent, RagAgent, SingleAgent
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.units import Units
from sc2.ids.buff_id import BuffId
import random


class LLMPlayer(BasePlayer):
    def __init__(self, config, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.config = config

        agent_config = {
            "model_name": self.model_name,
            "generation_config": self.generation_config,
            "llm_client": self.llm_client,
        }

        if config.enable_rag:
            self.rag_agent = RagAgent(config.own_race, **agent_config)
        if config.enable_plan or config.enable_plan_verifier:
            self.plan_agent = PlanAgent(config.own_race, **agent_config)
            self.action_agent = ActionAgent(config.own_race, **agent_config)
        else:
            self.agent = SingleAgent(config.own_race, **agent_config)

        self.plan_verifier = "llm" if config.enable_plan_verifier else None
        self.action_verifier = self.verify_actions if self.config.enable_action_verifier else None

        self.next_decision_time = -1
        
        # SCV auto-attack settings
        self.scv_auto_attack_distance = 4
        self.scv_auto_attack_time = 240

    def get_terran_suggestions(self):
        suggestions = []
        # 人口不足时建议建造Supply Depot
        if (
            self.supply_left < 5
            and not self.already_pending(UnitTypeId.SUPPLYDEPOT)
            and self._can_build(UnitTypeId.SUPPLYDEPOT)
        ):
            suggestions.append("Supply is low! Build a Supply Depot immediately.")
        # 没有Supply Depot时建议建造
        if (
            self.get_total_amount(UnitTypeId.SUPPLYDEPOT) < 1
            and self._can_build(UnitTypeId.SUPPLYDEPOT)
            and not self.already_pending(UnitTypeId.SUPPLYDEPOT)
        ):
            suggestions.append("At least one Supply Depot is necessary for development, consider building one.")
        # 没有MULE时建议建造
        if (
            self.get_total_amount(UnitTypeId.MULE) < 5
            and not self.already_pending(UnitTypeId.MULE)
            and self.townhalls(UnitTypeId.ORBITALCOMMAND).ready.exists
        ):
            suggestions.append("MULE can boost your economy, consider calling one from your Command Center.")
        # 没有Refinery时建议建造
        if self.get_total_amount(UnitTypeId.REFINERY) < 1 and self._can_build(UnitTypeId.REFINERY):
            suggestions.append("At least one Refinery is necessary for gas collection, consider building one.")
        # 没有Barracks时建议建造
        if (
            self.structures(UnitTypeId.SUPPLYDEPOT).exists
            and self.get_total_amount(UnitTypeId.BARRACKS) < 1
            and self.structures(UnitTypeId.SUPPLYDEPOT).ready.exists
        ):
            suggestions.append("At least one Barracks is necessary for attacking units, consider building one.")
        # 没有Barracks Tech Lab时建议建造
        barracks = self.structures(UnitTypeId.BARRACKS).ready
        if (
            barracks.exists
            and self.get_total_amount(UnitTypeId.BARRACKSTECHLAB) < 1
            and self._can_build(UnitTypeId.BARRACKSTECHLAB)
        ):
            if barracks.idle.exists:
                suggestions.append("At least one Barracks Tech Lab is necessary for advanced units, consider building one.")
            else:
                suggestions.append(
                    "Consider building a Barracks Tech Lab when one of your Barracks is idle to unlock advanced units."
                )
        # Marine数量少于2时建议建造
        if (
            self.structures(UnitTypeId.BARRACKS).ready.exists
            and self.get_total_amount(UnitTypeId.MARINE) < 2
            and self._can_build(UnitTypeId.MARINE)
        ):
            suggestions.append("At least 2 Marines are necessary for defensing, consider training one.")
        # 没有Marauder时建议建造
        if (
            self.structures(UnitTypeId.BARRACKSTECHLAB).ready.exists
            and self.get_total_amount(UnitTypeId.MARAUDER) < 1
            and self._can_build(UnitTypeId.MARAUDER)
        ):
            suggestions.append("At least one Marauder is necessary for defensing, consider training one.")
        # 只有一座Barracks时建议建造第二座
        if self.get_total_amount(UnitTypeId.BARRACKS) == 1 and self._can_build(UnitTypeId.BARRACKS):
            suggestions.append("Consider building a second Barracks to increase unit production.")
        # 如果有2个兵营且没有Factory时建议建造
        if (
            self.structures(UnitTypeId.BARRACKS).ready.amount >= 2
            and self.structures(UnitTypeId.BARRACKSTECHLAB).ready.exists
            and self.get_total_amount(UnitTypeId.FACTORY) == 0
            and self._can_build(UnitTypeId.FACTORY)
        ):
            suggestions.append("Consider building a Factory to unlock mechanical units.")
        # 有Factory时建议升级TechLab
        if (
            self.structures(UnitTypeId.FACTORY).ready.exists
            and self.get_total_amount(UnitTypeId.FACTORYTECHLAB) == 0
            and self._can_build(UnitTypeId.FACTORYTECHLAB)
        ):
            suggestions.append("Consider upgrade Factory Tech Lab to train powerful units.")
        if self.structures(UnitTypeId.FACTORYTECHLAB).ready.exists and self.get_total_amount(UnitTypeId.SIEGETANK) < 3:
            suggestions.append("Consider train Siege Tank to increase your army's firepower.")
        # 建议升级Command Center到Orbital Command
        cc = self.townhalls(UnitTypeId.COMMANDCENTER).ready
        if cc.exists:
            main_cc = cc.first  # 通常主基地优先升级
            if main_cc.is_idle and self._can_build(UnitTypeId.ORBITALCOMMAND) and self.get_total_amount(UnitTypeId.SCV) >= 16:
                suggestions.append("Upgrade Command Center to Orbital Command for better economy.")
        # 如果只有一座Orbital Command且没有Command Center时，建议建造新的Command Center
        if (
            self.get_total_amount(UnitTypeId.ORBITALCOMMAND) == 1
            and self.get_total_amount(UnitTypeId.COMMANDCENTER) == 0
            and self._can_build(UnitTypeId.COMMANDCENTER)
        ):
            suggestions.append("Consider building another Command Center to expand your base at another resource location.")
        # 维持适当的Marine和Marauder比例
        marine_count = self.get_total_amount(UnitTypeId.MARINE)
        marauder_count = self.get_total_amount(UnitTypeId.MARAUDER)

        if marine_count + marauder_count > 10:
            ratio = marauder_count / max(1, marine_count)
            if ratio < 0.5:
                suggestions.append("Increase Marauder production for better tanking.")
            elif ratio > 2.5:
                suggestions.append("Produce more Marines for DPS against light units.")

        return suggestions

    def get_protoss_suggestions(self):
        suggestions = []

        # 人口不足时建议建造Pylon (水晶塔)
        if (
            self.supply_left < 4
            and not self.already_pending(UnitTypeId.PYLON)
            and self._can_build(UnitTypeId.PYLON)
        ):
            suggestions.append("Supply is low! Build a Pylon immediately.")
        
        # 建筑没有能量时建议建造Pylon
        if self.structures.filter(lambda s: not s.is_powered and s.build_progress > 0.1).exists:
             if self._can_build(UnitTypeId.PYLON) and not self.already_pending(UnitTypeId.PYLON):
                suggestions.append("Some of your structures are unpowered! Build a Pylon nearby.")

        # 没有Pylon时建议建造
        if (
            self.get_total_amount(UnitTypeId.PYLON) < 1
            and self._can_build(UnitTypeId.PYLON)
            and not self.already_pending(UnitTypeId.PYLON)
        ):
            suggestions.append("At least one Pylon is necessary for development and power, consider building one.")

        # 有多余能量时建议使用Chrono Boost (星空加速)
        nexus = self.townhalls(UnitTypeId.NEXUS).ready
        if nexus.exists and nexus.first.energy >= 50:
            suggestions.append("Your Nexus has enough energy for Chrono Boost. Use it on the Nexus for more Probes or on a production building.")

        # 没有Assimilator (吸收厂) 时建议建造
        if self.get_total_amount(UnitTypeId.ASSIMILATOR) < 1 and self._can_build(UnitTypeId.ASSIMILATOR):
            suggestions.append("At least one Assimilator is necessary for gas collection, consider building one.")

        # 没有Gateway (传送门) 时建议建造
        if (
            self.structures(UnitTypeId.PYLON).exists
            and self.get_total_amount(UnitTypeId.GATEWAY) < 1
            and self._can_build(UnitTypeId.GATEWAY)
        ):
            suggestions.append("At least one Gateway is necessary for training ground units, consider building one.")

        # 没有Cybernetics Core (控制核心) 时建议建造
        if (
            self.structures(UnitTypeId.GATEWAY).ready.exists
            and self.get_total_amount(UnitTypeId.CYBERNETICSCORE) < 1
            and self._can_build(UnitTypeId.CYBERNETICSCORE)
        ):
            suggestions.append("A Cybernetics Core is necessary to unlock advanced units like Stalkers, consider building one.")

        # 建议研究Warpgate (折跃门) 科技
        cyber_core = self.structures(UnitTypeId.CYBERNETICSCORE).ready
        if (
            cyber_core.exists
            and self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 0
            and self.can_afford(UpgradeId.WARPGATERESEARCH)
        ):
            if cyber_core.idle.exists:
                suggestions.append("Cybernetics Core is ready. Research Warpgate technology to reinforce your army faster.")
            else:
                suggestions.append("Consider researching Warpgate technology when your Cybernetics Core is idle.")
                
        # Zealot (狂热者) 数量少于2时建议建造
        if (
            self.structures(UnitTypeId.GATEWAY).exists
            and self.get_total_amount(UnitTypeId.ZEALOT) < 2
            and self._can_build(UnitTypeId.ZEALOT)
        ):
            suggestions.append("At least 2 Zealots are necessary for early defense, consider training one.")

        # 没有Stalker (追猎者) 时建议建造
        if (
            self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists
            and self.get_total_amount(UnitTypeId.STALKER) < 1
            and self._can_build(UnitTypeId.STALKER)
        ):
            suggestions.append("At least one Stalker is useful for anti-air and kiting, consider training one.")
            
        # 传送门数量不足时建议建造更多
        gateway_count = self.get_total_amount(UnitTypeId.GATEWAY) + self.get_total_amount(UnitTypeId.WARPGATE)
        if 1 <= gateway_count < 3 and self._can_build(UnitTypeId.GATEWAY):
            suggestions.append("Consider building more Gateways to increase unit production.")

        # 维持适当的Zealot和Stalker比例
        zealot_count = self.get_total_amount(UnitTypeId.ZEALOT)
        stalker_count = self.get_total_amount(UnitTypeId.STALKER)

        if zealot_count + stalker_count > 10:
            # 理想比例：大约1个狂热者对应2个追猎者
            ratio = zealot_count / max(1, stalker_count)
            if ratio > 0.8: # 狂热者过多
                suggestions.append("Your army has many Zealots. Produce more Stalkers for ranged support.")
            elif ratio < 0.3: # 追猎者过多
                suggestions.append("Increase Zealot production to create a stronger frontline for your Stalkers.")

        # 发现敌人单位时建议攻击
        if self.enemy_units.exists:
            n_enemies = len([unit for unit in self.enemy_units if unit.name not in ["Probe", "SCV", "Drone", "MULE", "Overlord"]])
            if n_enemies > 0:
                suggestions.append(f"Enemy units detected ({n_enemies} units), consider attacking them with your army.")

        return suggestions


    def get_zerg_suggestions(self):
        suggestions = []
        
        # 人口不足时建议建造Overlord
        if (
            self.supply_left < 3
            and self.supply_cap < 200 # 避免在200人口时仍然提示
            and not self.already_pending(UnitTypeId.OVERLORD)
            and self._can_build(UnitTypeId.OVERLORD)
        ):
            suggestions.append("Supply is low! Morph an Overlord immediately.")

        # 没有Spawning Pool时建议建造
        if (
            self.get_total_amount(UnitTypeId.SPAWNINGPOOL) < 1
            and not self.already_pending(UnitTypeId.SPAWNINGPOOL)
            and self._can_build(UnitTypeId.SPAWNINGPOOL)
        ):
            suggestions.append("A Spawning Pool is required to create Zerglings, build one.")

        # 没有Queen时建议建造
        # 每个基地至少一个女王用于注卵和防御
        if (
            self.structures(UnitTypeId.SPAWNINGPOOL).ready.exists
            and self.get_total_amount(UnitTypeId.QUEEN) < self.townhalls.amount
            and self._can_build(UnitTypeId.QUEEN)
        ):
            suggestions.append("Build a Queen for each Hatchery to inject larva and defend.")

        # 有女王但基地没有注卵时建议注卵
        queens_with_energy = self.units(UnitTypeId.QUEEN).filter(lambda q: q.energy >= 25)
        hatcheries_needing_inject = self.townhalls.ready.filter(lambda h: not h.has_buff(BuffId.QUEENSPAWNLARVATIMER))
        if queens_with_energy.exists and hatcheries_needing_inject.exists:
            suggestions.append("Your Queen has energy! Use 'Inject Larva' on a Hatchery to boost production.")

        # 没有Extractor时建议建造
        if self.get_total_amount(UnitTypeId.EXTRACTOR) < 1 and self._can_build(UnitTypeId.EXTRACTOR):
            suggestions.append("At least one Extractor is necessary for gas collection, consider building one.")

        # Zergling数量少于6时建议建造
        if (
            self.structures(UnitTypeId.SPAWNINGPOOL).ready.exists
            and self.get_total_amount(UnitTypeId.ZERGLING) < 6
            and self._can_build(UnitTypeId.ZERGLING)
        ):
            suggestions.append("At least 6 Zerglings are necessary for early defense, consider training some.")

        # 建议扩张（建造第二个基地）
        if self.townhalls.amount < 2 and self._can_build(UnitTypeId.HATCHERY):
            suggestions.append("Consider building a second Hatchery to expand your economy and production.")

        # 建议建造Roach Warren
        if (
            self.structures(UnitTypeId.SPAWNINGPOOL).ready.exists
            and self.get_total_amount(UnitTypeId.ROACHWARREN) == 0
            and self._can_build(UnitTypeId.ROACHWARREN)
        ):
            suggestions.append("Consider building a Roach Warren to unlock Roaches, a strong armored unit.")

        # 没有Roach时建议建造
        if (
            self.structures(UnitTypeId.ROACHWARREN).ready.exists
            and self.get_total_amount(UnitTypeId.ROACH) < 5
            and self._can_build(UnitTypeId.ROACH)
        ):
            suggestions.append("Roaches are strong against many early units, consider training some.")

        # 建议升级到Lair (T2科技)
        if (
            self.structures(UnitTypeId.SPAWNINGPOOL).ready.exists
            and self.get_total_amount(UnitTypeId.LAIR) == 0
            and self.townhalls(UnitTypeId.HATCHERY).idle.exists
            and self._can_build(UnitTypeId.LAIR)
        ):
            suggestions.append("Upgrade a Hatchery to a Lair to unlock powerful mid-game units and upgrades.")

        # 有Lair时建议建造Hydralisk Den
        if (
            self.structures(UnitTypeId.LAIR).ready.exists
            and self.get_total_amount(UnitTypeId.HYDRALISKDEN) == 0
            and self._can_build(UnitTypeId.HYDRALISKDEN)
        ):
            suggestions.append("Build a Hydralisk Den to unlock Hydralisks, a versatile ranged unit.")

        # 有Hydralisk Den时建议训练Hydralisk
        if self.structures(UnitTypeId.HYDRALISKDEN).ready.exists and self.get_total_amount(UnitTypeId.HYDRALISK) < 5:
            suggestions.append("Consider training Hydralisks to strengthen your army's anti-air and ranged capabilities.")

        # 维持适当的Zergling和Roach比例
        zergling_count = self.get_total_amount(UnitTypeId.ZERGLING)
        roach_count = self.get_total_amount(UnitTypeId.ROACH)

        if zergling_count + roach_count > 20:
            # 计算蟑螂在(蟑螂+小狗)部队中的价值占比，蟑螂占2人口，小狗占0.5
            roach_supply = roach_count * 2
            zergling_supply = zergling_count * 0.5
            total_supply = roach_supply + zergling_supply
            
            if total_supply > 0:
                roach_ratio = roach_supply / total_supply
                if roach_ratio < 0.3: # 蟑螂占比过低
                    suggestions.append("Your army is Zergling-heavy. Add Roaches for a stronger frontline.")
                elif roach_ratio > 0.8: # 蟑螂占比过高
                    suggestions.append("Your army is Roach-heavy. Add Zerglings for more DPS and to surround enemies.")

        return suggestions
    
    def get_suggestions(self):
        suggestions = []

        # 发现敌人单位时建议攻击
        if self.enemy_units.exists:
            n_enemies = len(
                [unit for unit in self.enemy_units if unit.name not in ["Probe", "SCV", "Drone", "MULE", "Overlord"]]
            )
            if n_enemies > 0:
                suggestions.append(
                    f"Enemy units detected ({n_enemies} units), consider attacking them."
                )

        if self.time < 300 and self.time > 60:
            suggestions.append("The enemy will start a fierce attack at 03:00, so you need to start producing a large number of attack units, such as Marauder, at least at 02:30.")
        
        if self.minerals >= 500:
            suggestions.append("Too much minerals! Consider spending them on expanding or developing high technology.")

        if self.config.own_race == "Terran":
            suggestions.extend(self.get_terran_suggestions())
        elif self.config.own_race == "Protoss":
            suggestions.extend(self.get_protoss_suggestions())
        elif self.config.own_race == "Zerg":
            suggestions.extend(self.get_zerg_suggestions())

        return suggestions

    def log_current_iteration(self, iteration: int):
        print(f"================ iteration {iteration} ================")
        self.logging("iteration", iteration, save_trace=True)
        self.logging("time_seconds", int(self.time), save_trace=True)
        self.logging("minerals", self.minerals, save_trace=True)
        self.logging("vespene", self.vespene, save_trace=True)
        
        unit_mineral_value, unit_vespene_value = 0, 0
        for unit in self.units:
            unit_value = self.calculate_unit_value(unit.type_id)
            unit_mineral_value += unit_value.minerals
            unit_vespene_value += unit_value.vespene
        self.logging("unit_mineral_value", unit_mineral_value, save_trace=True)
        self.logging("unit_vespene_value", unit_vespene_value, save_trace=True)
        
        structure_mineral_value, structure_vespene_value = 0, 0
        for structure in self.structures:
            structure_value = self.calculate_unit_value(structure.type_id)
            structure_mineral_value += structure_value.minerals
            structure_vespene_value += structure_value.vespene
        self.logging("structure_mineral_value", structure_mineral_value, save_trace=True)
        self.logging("structure_vespene_value", structure_vespene_value, save_trace=True)
        
        self.logging("supply_army", self.supply_army, save_trace=True)
        self.logging("supply_workers", self.supply_workers, save_trace=True)
        self.logging("supply_left", self.supply_left, save_trace=True)
        self.logging("n_structures", len(self.structures), save_trace=True)
        self.logging("n_visible_enemy_units", len(self.enemy_units), save_trace=True)
        self.logging("n_visible_enemy_structures", len(self.enemy_structures), save_trace=True)
        unit_types = set(unit.type_id for unit in self.units)
        structure_types = set(unit.type_id for unit in self.structures)
        self.logging("n_unit_types", len(unit_types), save_trace=True)
        self.logging("n_structure_types", len(structure_types), save_trace=True)
        
    
    async def run(self, iteration: int):
        # send idle workers to minerals or gas automatically
        await self.distribute_workers()
        for unit in self.units:
            if unit.type_id in [UnitTypeId.MULE] or unit.is_constructing_scv:
                continue
            enemies_in_range = self.enemy_units.in_attack_range_of(unit)
            if enemies_in_range.exists:
                target = self.get_lowest_health_enemy(enemies_in_range)
                if target:
                    unit.attack(target)
            else:
                near_by_enemies = self.enemy_units.closer_than(self.scv_auto_attack_distance, unit.position)
                near_by_enemies = near_by_enemies.closer_than(self.scv_auto_attack_distance, self.start_location)
                target_enemy = self.get_lowest_health_enemy(near_by_enemies)
                if unit.type_id in [UnitTypeId.SCV] and self.time < self.scv_auto_attack_time and target_enemy:
                    unit.attack(target_enemy)

        # 10 iteration -> 1.7s
        if self.config.enable_random_decision_interval:
            decision_iteration = random.randint(8, 12)
            decision_minerals = random.randint(130, 200)
        else:
            decision_iteration = 10
            decision_minerals = 170
        if (
            iteration % decision_iteration == 0
            and self.minerals >= decision_minerals
            or iteration == self.next_decision_time
        ):
            self.next_decision_time = iteration + 9 * decision_iteration

            self.log_current_iteration(iteration)

            obs_text = await self.obs_to_text()
            
            # RAG is not ready yet, so we skip it for now
            # if self.config.enable_rag:
            #     rag_summary, rag_think = self.rag_agent.run(obs_text)
            #     self.logging("rag_summary", rag_summary, save_trace=True)
            #     self.logging("rag_think", rag_think, save_trace=True, print_log=False)
            #     obs_text += "\n\n# Hint\n" + rag_summary

            if self.config.enable_plan or self.config.enable_plan_verifier:
                suggestions = self.get_suggestions()
                self.logging("suggestions", suggestions, save_trace=True, print_log=False)

                plans, plan_think, plan_chat_history = self.plan_agent.run(obs_text, verifier=self.plan_verifier, suggestions=suggestions)
                self.logging("plans", plans, save_trace=True)
                self.logging("plan_think", plan_think, save_trace=True, print_log=False)
                self.logging("plan_chat_history", plan_chat_history, save_trace=True, print_log=False)

                plans = "\n".join([f"{i + 1}. {plan}" for i, plan in enumerate(plans)])

                actions, action_think, action_chat_history = self.action_agent.run(obs_text, plans, verifier=self.action_verifier)
                self.logging("actions", actions, save_trace=True)
                self.logging("action_think", action_think, save_trace=True, print_log=False)
                self.logging("action_chat_history", action_chat_history, save_trace=True, print_log=False)
            else:
                actions, action_think = self.agent.run(obs_text, verifier=self.action_verifier)
                self.logging("actions", actions, save_trace=True)
                self.logging("action_think", action_think, save_trace=True, print_log=False)

            await self.run_actions(actions)
            
        elif iteration % 10 == 0:
            self.log_current_iteration(iteration)
