from .base_player import BasePlayer
from agents import PlanAgent, ActionAgent, RagAgent, SingleAgent
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.ability_id import AbilityId
from sc2.units import Units
import random


class LLMPlayer(BasePlayer):
    def __init__(self, config, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.config = config

        agent_config = {
            "model_name": self.model_name,
            "service": self.service,
            "vllm_base_url": self.vllm_base_url,
            **self.generation_config,
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

        self.k = 5
        self.next_k = 0

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
            and self._can_build(UnitTypeId.BARRACKS)
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
            self.structures(UnitTypeId.BARRACKS).exists
            and self.get_total_amount(UnitTypeId.MARINE) < 2
            and self._can_build(UnitTypeId.MARINE)
        ):
            suggestions.append("At least 2 Marines are necessary for defensing, consider training one.")
        # 没有Marauder时建议建造
        if (
            self.structures(UnitTypeId.BARRACKSTECHLAB).exists
            and self.get_total_amount(UnitTypeId.MARAUDER) < 1
            and self._can_build(UnitTypeId.MARAUDER)
        ):
            suggestions.append("At least one Marauder is necessary for defensing, consider training one.")
        # 只有一座Barracks时建议建造第二座
        if self.get_total_amount(UnitTypeId.BARRACKS) == 1 and self._can_build(UnitTypeId.BARRACKS):
            suggestions.append("Consider building a second Barracks to increase unit production.")
        # 建议升级Command Center到Orbital Command
        cc = self.townhalls(UnitTypeId.COMMANDCENTER).ready
        if cc.exists:
            main_cc = cc.first  # 通常主基地优先升级
            if main_cc.is_idle and self._can_build(UnitTypeId.ORBITALCOMMAND) and self.get_total_amount(UnitTypeId.SCV) >= 16:
                suggestions.append("Upgrade Command Center to Orbital Command for better economy.")
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
        
        if self.time < 300:
            suggestions.append("The enemy will start a fierce attack at 03:00, so you need to start producing a large number of attack units, such as Marauder, at least at 02:30.")
        
        # # --- 侦测到敌方早期运营和单位 ---
        # # 侦测到敌方攻城坦克 (Siege Tank)
        # if self.enemy_units(UnitTypeId.SIEGETANK).exists:
        #     suggestions.append("Enemy Siege Tanks detected! Consider: Producing Vikings for air superiority and vision, getting your own Siege Tanks, using Medivac drops to harass, or Banshees if their anti-air is weak (requires cloaking).")
        # # 侦测到敌方大量生化部队 (Marine, Marauder)
        # # 你可能需要更精确的条件来判断“大量”，例如单位数量或组合
        # if self.enemy_units(UnitTypeId.MARINE).amount >= 6 or self.enemy_units(UnitTypeId.MARAUDER).amount >= 3:
        #     suggestions.append("Significant enemy bio force (Marines/Marauders) detected! Consider: Matching with your own bio and upgrading infantry weapons/armor, producing Siege Tanks, planting Widow Mines, or using Hellions/Hellbats (with Infernal Pre-Igniter against Marines).")
        # # 侦测到敌方维京战机 (Viking)
        # if self.enemy_units(UnitTypeId.VIKINGFIGHTER).exists:
        #     suggestions.append("Enemy Vikings detected! Consider: Producing your own Vikings to contest air control, building Missile Turrets for static defense, or using massed stimmed Marines if you have ground superiority and they overcommit to Vikings.")
        # if self.enemy_units(UnitTypeId.BANSHEE).exists:
        #     suggestions.append("Enemy Banshees detected! Consider: Immediately building Missile Turrets, producing Vikings, getting a Raven for detection, or using Orbital Scans to reveal and engage.")
        #     if not self.enemy_units(UnitTypeId.BANSHEE).first.is_cloaked: # Check if any are uncloaked to remind about cloaking
        #         suggestions.append("Be aware enemy Banshees might get cloaking soon.")
        # # 侦测到敌方铁鸦 (Raven)
        # if self.enemy_units(UnitTypeId.RAVEN).exists:
        #     suggestions.append("Enemy Ravens detected! Consider: Producing Vikings to snipe them, using Ghosts with EMP to disable them. Use scans if they cloak. Be wary of Interference Matrix and Auto-Turrets.")
        # # 侦测到敌方战列巡航舰 (Battlecruiser)
        # if self.enemy_units(UnitTypeId.BATTLECRUISER).exists:
        #     suggestions.append("Enemy Battlecruisers detected! Consider: Massing Vikings, using Ravens (Anti-Armor Missile), Ghosts (EMP for Yamato/Jump), building Missile Turret clusters, or producing your own Battlecruisers for counter-Yamato.")
        # # --- 侦测到敌方幽灵 (Ghost) ---
        # if self.enemy_units(UnitTypeId.GHOST).exists:
        #     suggestions.append("Enemy Ghosts detected! Consider: Producing your own Ghosts for counter-EMP or snipes, spreading your units to minimize EMP impact, using Ravens (Interference Matrix). Scout for Nuke attempts (red dot).")
        #     # --- 侦测到敌方建筑及运营意图 ---

        # # 侦测到敌方早期多个兵营 (Barracks) - 可能表示速生化部队rush
        # # (self.time < 210 is roughly 3:30 game time)
        # if self.enemy_structures(UnitTypeId.BARRACKS).amount >= 2 and self.time < 210:
        #     suggestions.append("Enemy has multiple Barracks early! Prepare for bio aggression. Consider Bunkers, Siege Tanks, or matching bio production quickly.")
        # # 侦测到敌方早期重工厂 (Factory) - 可能有恶火骚扰或坦克推进
        # if self.enemy_structures(UnitTypeId.FACTORY).exists and self.time < 180: # Factory before 3:00
        #     if not self.enemy_units(UnitTypeId.HELLION).exists and not self.enemy_units(UnitTypeId.SIEGETANK).exists:
        #         suggestions.append("Early enemy Factory detected! Be prepared for Hellions or an early Siege Tank. Consider Marines and a Bunker at your natural expansion.")
        # # 侦测到敌方早期星港 (Starport)
        # if self.enemy_structures(UnitTypeId.STARPORT).exists and self.time < 270: # Starport before 4:30
        #     suggestions.append("Early enemy Starport detected! Prepare for air units. Consider Missile Turrets and Vikings. Scout if it has a Tech Lab (Banshees/Ravens) or Reactor (Vikings/Medivacs).")
        #     if self.enemy_structures(UnitTypeId.STARPORTTECHLAB).exists:
        #         suggestions.append("Enemy Starport has a Tech Lab - high chance of Banshees or Ravens. Prioritize detection (Missile Turrets, your own Raven, Orbital Scans) and Vikings.")

        # if self.minerals >= 300 and self.vespene >= 200:
        #     suggestions.append("You have enough resource to consider expanding. Consider building a Command Center at a safe location to boost your economy.")
        # 侦测到敌方扩张 (新的指挥中心 Command Center)
        # 这需要更复杂的逻辑来判断是否是“新”扩张，例如通过位置或数量变化
        # 简化版：如果敌方基地数量大于已知的主基地数量（通常为1，除非有特殊开局）
        # if self.enemy_structures(UnitTypeId.COMMANDCENTER).amount > self.enemy_structures(UnitTypeId.COMMANDCENTER).filter(lambda x: x.is_main_base).amount if hasattr(self.enemy_structures(UnitTypeId.COMMANDCENTER).first, 'is_main_base') else self.enemy_structures(UnitTypeId.COMMANDCENTER).amount > 1 : # simplified detection
        #     suggestions.append("Enemy expansion detected! Consider: Applying pressure with your army if you have an advantage, expanding yourself to keep up economically, or scouting their follow-up tech choices from the new base.")
        # 扩张时机建议
        # if (self.structures(UnitTypeId.BARRACKS).amount >= 2 and
        #     self._can_build(UnitTypeId.COMMANDCENTER) and
        #     not self.already_pending(UnitTypeId.COMMANDCENTER)):
        #     suggestions.append("Consider expanding to new base for economy boost.")

        return suggestions

    async def run(self, iteration: int):
        # send idle workers to minerals or gas automatically
        await self.distribute_workers()

        for unit in self.units:
            if unit.type_id in [UnitTypeId.SCV, UnitTypeId.MULE]:
                continue
            enemies_in_range = self.enemy_units.in_attack_range_of(unit)
            if enemies_in_range.exists:
                target = self.get_lowest_health_enemy(enemies_in_range)
                if target:
                    unit.attack(target)
                    # await self.chat_send(f"{unit.type_id} attacking {target.type_id}")
                    # self.last_action.append(
                    #     f"[System] {unit.type_id}[{self.tag_to_id(unit.tag)}] attacking {target.type_id}[{self.tag_to_id(target.tag)}]"
                    # )
            # else:
            #     structures_in_range = self.enemy_structures.in_attack_range_of(unit)
            #     if structures_in_range.exists:
            #         target = self.get_lowest_health_enemy(structures_in_range)
            #         if target:
            #             unit.attack(target)
            #             await self.chat_send(f"{unit.type_id} attacking {target.type_id}")
            #             self.last_action.append(
            #                 f"[System] {unit.type_id}[{self.tag_to_id(unit.tag)}] attacking {target.type_id}[{self.tag_to_id(target.tag)}]"
            #             )
        # 100 -> 17s
        # decision_iteration = random.randint(8, 12)
        # decision_minerals = random.randint(130, 200)
        decision_iteration = 10
        decision_minerals = 170
        if iteration % decision_iteration == 0 and self.minerals >= decision_minerals:
            self.logging("iteration", iteration, level="info", save_trace=True, print_log=False)
            obs_text = await self.obs_to_text()
            self.logging("time_seconds", int(self.time), level="info", save_trace=True, print_log=False)
            self.logging("minerals", self.minerals, level="info", save_trace=True, print_log=False)
            self.logging("vespene", self.vespene, level="info", save_trace=True, print_log=False)
            self.logging("supply_army", self.supply_army, level="info", save_trace=True, print_log=False)
            self.logging("supply_workers", self.supply_workers, level="info", save_trace=True, print_log=False)
            self.logging("supply_left", self.supply_left, level="info", save_trace=True, print_log=False)
            self.logging("n_structures", len(self.structures), level="info", save_trace=True, print_log=False)
            self.logging("n_enemy_units", len(self.enemy_units), level="info", save_trace=True, print_log=False)
            self.logging("n_enemy_structures", len(self.enemy_structures), level="info", save_trace=True, print_log=False)
            unit_types = set(unit.type_id for unit in self.units)
            structure_types = set(unit.type_id for unit in self.structures)
            self.logging("n_unit_types", len(unit_types), level="info", save_trace=True, print_log=False)
            self.logging("n_structure_types", len(structure_types), level="info", save_trace=True, print_log=False)

            if self.config.enable_rag:
                rag_summary, rag_think = self.rag_agent.run(obs_text)
                self.logging("rag_summary", rag_summary, save_trace=True)
                self.logging("rag_think", rag_think, save_trace=True, print_log=False)
                obs_text += "\n\n# Hint\n" + rag_summary

            if self.config.enable_plan or self.config.enable_plan_verifier:
                suggestions = self.get_suggestions()
                self.logging("suggestions", suggestions, save_trace=True, print_log=False)

                plans, plan_think, plan_chat_history = self.plan_agent.run(obs_text, verifier=self.plan_verifier, suggestions=suggestions)
                self.logging("plans", plans, save_trace=True)
                self.logging("plan_think", plan_think, save_trace=True, print_log=False)
                self.logging("plan_chat_history", plan_chat_history, save_trace=True, print_log=False)

                # if self.next_k > 0:
                #     self.next_k -= 1
                # if self.config.enable_human and self.next_k == 0:
                # print("=== 决策介入 ===")
                # print("输入0：直接执行规划")
                # print("输入1：反馈修改意见")
                # print("输入2：输入新规划并执行")

                # op = input("请输入操作：")
                # if op == "0":
                #     pass
                # elif op == "1":
                #     self.next_k = self.k
                #     print("请输入修改意见：")
                #     feedback = input()
                #     self.logging("human_feedback", feedback, save_trace=True)
                #     plans = self.plan_agent.refine_plan(obs_text, plans, feedback)
                #     self.logging("human_refine_plan", plans, save_trace=True)
                # elif op == "2":
                #     self.next_k = self.k
                #     print("请输入新规划（用英文分号间隔多条规划）：")
                #     new_plan = input()
                #     plans = new_plan.split(";")
                #     self.logging("human_plan", new_plan, save_trace=True)
                # else:
                #     print("输入错误，直接执行规划")
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
