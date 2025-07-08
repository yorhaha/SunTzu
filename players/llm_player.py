from .base_player import BasePlayer
from agents import PlanAgent, ActionAgent, RagAgent, SingleAgent
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.ability_id import AbilityId
from sc2.units import Units
from sc2.unit import Unit
import random
from typing import Dict, List, Set


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
            self.rag_agent = RagAgent(**agent_config)
        if config.enable_plan or config.enable_plan_verifier:
            self.plan_agent = PlanAgent(**agent_config)
            self.action_agent = ActionAgent(**agent_config)
        else:
            self.agent = SingleAgent(**agent_config)

        self.plan_verifier = "llm" if config.enable_plan_verifier else None
        self.action_verifier = self.verify_actions if self.config.enable_action_verifier else None
        
        self.next_decision_time = -1
        
        # SCV auto-attack settings
        self.scv_auto_attack_distance = 4
        self.scv_auto_attack_time = 240

    def get_lowest_health_enemy(self, units: Units):
        """Get the enemy unit with the lowest health."""
        if not units.exists:
            return None
        return min(units, key=lambda unit: unit.health + unit.shield)

    def _can_build(self, unit_type):
        """辅助函数，检查是否可以且尚未开始建造某个单位/建筑。"""
        return self.can_afford(unit_type) and not self.already_pending(unit_type)

    def get_total_amount(self, unit_type: UnitTypeId):
        """获取指定单位类型的总数量，包括正在建造的和已完成的。"""
        unit_amount = self.units(unit_type).amount
        structures_amount = self.structures(unit_type).amount
        pending_amount = self.already_pending(unit_type)
        return unit_amount + structures_amount + pending_amount

    def get_suggestions(self):
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
        # 发现敌人单位时建议攻击
        if self.enemy_units.exists:
            n_enemies = len([unit for unit in self.enemy_units if unit.name not in ["SCV", "MULE"]])
            if n_enemies > 0:
                suggestions.append(f"Enemy units detected ({n_enemies} units), consider attacking them.")
        
        if self.time < 300 and self.structures(UnitTypeId.BARRACKS).ready.exists:
            suggestions.append("The enemy will start a fierce attack at 03:00, so you need to start producing a large number of attack units, such as Marauder, at least at 02:30.")
        
        if self.minerals >= 500:
            suggestions.append("Too much minerals! Consider spending them on expanding or developing high technology.")

        return suggestions

    def print_current_iteration(self, iteration: int):
        print(f"================ iteration {iteration} ================")
        self.logging("iteration", iteration, save_trace=True, print_log=False)
        self.logging("time_seconds", int(self.time), save_trace=True)
        self.logging("minerals", self.minerals, save_trace=True, print_log=False)
        self.logging("vespene", self.vespene, save_trace=True, print_log=False)
        
        unit_mineral_value, unit_vespene_value = 0, 0
        for unit in self.units:
            unit_value = self.calculate_unit_value(unit.type_id)
            unit_mineral_value += unit_value.minerals
            unit_vespene_value += unit_value.vespene
        self.logging("unit_mineral_value", unit_mineral_value, save_trace=True, print_log=False)
        self.logging("unit_vespene_value", unit_vespene_value, save_trace=True, print_log=False)
        
        structure_mineral_value, structure_vespene_value = 0, 0
        for structure in self.structures:
            structure_value = self.calculate_unit_value(structure.type_id)
            structure_mineral_value += structure_value.minerals
            structure_vespene_value += structure_value.vespene
        self.logging("structure_mineral_value", structure_mineral_value, save_trace=True, print_log=False)
        self.logging("structure_vespene_value", structure_vespene_value, save_trace=True, print_log=False)
        
        self.logging("supply_army", self.supply_army, save_trace=True, print_log=False)
        self.logging("supply_workers", self.supply_workers, save_trace=True, print_log=False)
        self.logging("supply_left", self.supply_left, save_trace=True, print_log=False)
        self.logging("n_structures", len(self.structures), save_trace=True, print_log=False)
        self.logging("n_visible_enemy_units", len(self.enemy_units), save_trace=True, print_log=False)
        self.logging("n_visible_enemy_structures", len(self.enemy_structures), save_trace=True, print_log=False)
        unit_types = set(unit.type_id for unit in self.units)
        structure_types = set(unit.type_id for unit in self.structures)
        self.logging("n_unit_types", len(unit_types), save_trace=True, print_log=False)
        self.logging("n_structure_types", len(structure_types), save_trace=True, print_log=False)

    
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
                
        # 100 -> 17s
        decision_iteration = random.randint(8, 12)
        decision_minerals = random.randint(130, 200)
        # decision_iteration = 10
        # decision_minerals = 170
        if (
            iteration % decision_iteration == 0 and self.minerals >= decision_minerals
            or iteration == self.next_decision_time
        ):
            self.next_decision_time = iteration + 9 * decision_iteration

            self.print_current_iteration(iteration)

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
            self.print_current_iteration(iteration)
