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
        self.scv_auto_attack_distance = 2
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

    async def distribute_workers(self, resource_ratio: float = 2) -> None:
        """
        一个经过优化的工人分配函数。
        它通过一次遍历所有工人来统计信息，然后高效地将空闲或过剩的工人重新分配到短缺的矿区或气矿。

        - 性能更高：避免了嵌套循环和不必要的重复计算。
        - 逻辑更优：优先就近分配，并能处理跨基地的工人调动。
        - 策略清晰：基于明确的饱和度标准（矿区16个，气矿3个）进行分配。

        :param resource_ratio: 期望的晶体矿/瓦斯采集工人比例。如果实际比例低于此值，优先采矿；反之，优先采气。
        """
        workers = [unit for unit in self.units if unit.type_id in [UnitTypeId.SCV, UnitTypeId.MULE, UnitTypeId.DRONE, UnitTypeId.PROBE]]
        if not workers or not self.townhalls.ready:
            return

        # 1. 数据准备：缓存基地、矿区和气矿信息
        # =================================================
        ready_bases = self.townhalls.ready
        ready_gas_buildings = self.gas_buildings.ready
        
        # 定义理想的工人数量
        IDEAL_WORKERS_PER_GAS = 3
        IDEAL_WORKERS_PER_BASE = 16

        # 缓存每个基地附近的矿区
        base_to_minerals: Dict[int, Set[int]] = {}
        mineral_to_base: Dict[int, int] = {}
        for base in ready_bases:
            # 使用8.0的距离作为标准来关联矿区
            nearby_minerals = self.mineral_field.closer_than(8.0, base)
            base_to_minerals[base.tag] = {mf.tag for mf in nearby_minerals}
            for mineral in nearby_minerals:
                mineral_to_base[mineral.tag] = base.tag

        # 2. 状态统计：一次遍历所有工人，统计每个采集点的工作人数
        # =================================================
        base_worker_count: Dict[int, int] = {base.tag: 0 for base in ready_bases}
        gas_worker_count: Dict[int, int] = {gas.tag: 0 for gas in ready_gas_buildings}
        
        # 将所有工人分为三类：采矿、采气、其他（包括空闲、建造等）
        mining_workers: Dict[int, List[Unit]] = {base.tag: [] for base in ready_bases}
        gas_workers: Dict[int, List[Unit]] = {gas.tag: [] for gas in ready_gas_buildings}
        other_workers: List[Unit] = []

        for worker in workers:
            order = worker.order_target
            if order:
                if order in mineral_to_base:
                    base_tag = mineral_to_base[order]
                    base_worker_count[base_tag] += 1
                    mining_workers[base_tag].append(worker)
                elif order in gas_worker_count:
                    gas_worker_count[order] += 1
                    gas_workers[order].append(worker)
                else:
                    other_workers.append(worker)
            else:
                other_workers.append(worker)

        # 3. 识别待分配工人和空缺岗位
        # =================================================
        worker_pool: List[Unit] = [w for w in other_workers if w.is_idle] # 从空闲工人开始
        deficit_jobs: List[Unit] = []

        # 检查气矿的过剩与短缺
        for gas in ready_gas_buildings:
            difference = gas_worker_count[gas.tag] - IDEAL_WORKERS_PER_GAS
            if difference > 0:
                # 将多余的工人加入待分配池
                worker_pool.extend(gas_workers[gas.tag][:difference])
            elif difference < 0:
                # 将空缺岗位加入列表
                deficit_jobs.extend([gas] * -difference)

        # 检查基地的过剩与短缺
        for base in ready_bases:
            # 确保基地附近有矿
            if not base_to_minerals.get(base.tag):
                continue
            
            num_minerals = len(base_to_minerals[base.tag])
            ideal_for_this_base = min(IDEAL_WORKERS_PER_BASE, num_minerals * 2)
            
            difference = base_worker_count[base.tag] - ideal_for_this_base
            if difference > 0:
                worker_pool.extend(mining_workers[base.tag][:difference])
            elif difference < 0:
                deficit_jobs.extend([base] * -difference)

        # 4. 执行分配
        # =================================================
        if not worker_pool or not deficit_jobs:
            return # 没有需要移动的工人或没有空缺的岗位

        # 根据资源比例决定分配优先级
        # 注意：这里我们检查的是工人比例，而不是资源存量比例，这更直接地反映了采集效率
        current_mineral_workers = sum(base_worker_count.values())
        current_gas_workers = sum(gas_worker_count.values())
        
        # 避免除零错误
        if current_gas_workers == 0 or current_mineral_workers / current_gas_workers < resource_ratio:
            # 缺矿，优先分配到矿区
            job_priority = sorted(deficit_jobs, key=lambda job: job.has_vespene)
        else:
            # 缺气，优先分配到气矿
            job_priority = sorted(deficit_jobs, key=lambda job: not job.has_vespene)

        # 开始分配
        for job in job_priority:
            if not worker_pool:
                break
            
            # 找到离这个岗位最近的待分配工人
            worker_to_assign = min(worker_pool, key=lambda w: w.distance_to(job))
            
            worker_pool.remove(worker_to_assign)
            
            if job.has_vespene:
                worker_to_assign.gather(job)
            else:
                # 分配到基地时，找到该基地附近的一个矿片
                target_mineral = self.mineral_field.filter(
                    lambda mf: mf.tag in base_to_minerals[job.tag]
                ).closest_to(worker_to_assign)
                worker_to_assign.gather(target_mineral)

        # 如果分配完所有岗位后仍有空闲工人（例如，所有地方都饱和了），让他们去最近的矿区
        if worker_pool:
            all_minerals = self.mineral_field.filter(lambda mf: any(mf.distance_to(b) <= 8 for b in ready_bases))
            if all_minerals:
                for worker in worker_pool:
                    if worker.is_idle:
                        target_mineral = all_minerals.closest_to(worker)
                        worker.gather(target_mineral)
    
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

                while True:
                    plans, plan_think, plan_chat_history = self.plan_agent.run(obs_text, verifier=self.plan_verifier, suggestions=suggestions)
                    if '"error_number": 0' not in plan_think[-1][-1]:
                        return
                    break
                self.logging("plans", plans, save_trace=True)
                self.logging("plan_think", plan_think, save_trace=True, print_log=False)
                self.logging("plan_chat_history", plan_chat_history, save_trace=True, print_log=False)

                # while True:
                actions, action_think, action_chat_history = self.action_agent.run(obs_text, plans, verifier=self.action_verifier)
                # if action_think[-1][-1] == "":
                #     break
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
