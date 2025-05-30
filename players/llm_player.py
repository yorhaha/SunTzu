from .base_player import BasePlayer
from agents import PlanAgent, ActionAgent, RagAgent, SingleAgent
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.ability_id import AbilityId
from sc2.units import Units


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
        return self.units(unit_type).amount + self.already_pending(unit_type)

    def get_suggestions(self):
        suggestions = []
        # 人口不足时建议建造Supply Depot
        if (
            self.supply_left < 5
            and not self.already_pending(UnitTypeId.SUPPLYDEPOT)
            and self.can_afford(UnitTypeId.SUPPLYDEPOT)
        ):
            suggestions.append("Supply is low! Build a Supply Depot immediately.")
        # 没有Supply Depot时建议建造
        if self.get_total_amount(UnitTypeId.SUPPLYDEPOT) < 1 and self.can_afford(UnitTypeId.SUPPLYDEPOT):
            suggestions.append("At least one Supply Depot is necessary for development, consider building one.")
        # 没有Refinery时建议建造
        if self.get_total_amount(UnitTypeId.REFINERY) < 1 and self.can_afford(UnitTypeId.REFINERY):
            suggestions.append("At least one Refinery is necessary for gas collection, consider building one.")
        # 没有Barracks时建议建造
        if (
            self.structures(UnitTypeId.SUPPLYDEPOT).exists
            and self.get_total_amount(UnitTypeId.BARRACKS) < 1
            and self.can_afford(UnitTypeId.BARRACKS)
        ):
            suggestions.append("At least one Barracks is necessary for attacking units, consider building one.")
        # 没有Barracks Tech Lab时建议建造
        barracks = self.structures(UnitTypeId.BARRACKS).ready
        if (
            barracks.exists
            and self.get_total_amount(UnitTypeId.BARRACKSTECHLAB) < 1
            and self.can_afford(UnitTypeId.BARRACKSTECHLAB)
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
            and self.can_afford(UnitTypeId.MARINE)
        ):
            suggestions.append("At least 2 Marines are necessary for defensing, consider training one.")
        # 没有Marauder时建议建造
        if (
            self.structures(UnitTypeId.BARRACKSTECHLAB).exists
            and self.get_total_amount(UnitTypeId.MARAUDER) < 1
            and self.can_afford(UnitTypeId.MARAUDER)
        ):
            suggestions.append("At least one Marauder is necessary for defensing, consider training one.")
        # 只有一座Barracks时建议建造第二座
        if self.get_total_amount(UnitTypeId.BARRACKS) < 2 and self.can_afford(UnitTypeId.BARRACKS):
            suggestions.append("Consider building a second Barracks to increase unit production.")
        # 建议升级Command Center到Orbital Command
        cc = self.townhalls(UnitTypeId.COMMANDCENTER).ready
        if cc.exists:
            main_cc = cc.first  # 通常主基地优先升级
            if main_cc.is_idle and self.can_afford(UnitTypeId.ORBITALCOMMAND) and self.get_total_amount(UnitTypeId.SCV) >= 16:
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

        # 扩张时机建议
        # if (self.structures(UnitTypeId.BARRACKS).amount >= 2 and
        #     self.can_afford(UnitTypeId.COMMANDCENTER) and
        #     not self.already_pending(UnitTypeId.COMMANDCENTER)):
        #     suggestions.append("Consider expanding to new base for economy boost.")

        return suggestions

    async def run(self, iteration: int):
        # send idle workers to minerals or gas automatically
        await self.distribute_workers()

        for unit in self.units:
            if unit.type_id not in [UnitTypeId.SCV, UnitTypeId.MULE]:
                continue
            enemies_in_range = self.enemy_units.in_attack_range_of(unit)
            if enemies_in_range.exists:
                target = self.get_lowest_health_enemy(enemies_in_range)
                if target:
                    unit.attack(target)
                    self.chat_send(f"{unit.type_id} attacking {target.type_id}")
                    self.last_action.append(
                        f"[System] {unit.type_id}[{self.tag_to_id(unit.tag)}] attacking {target.type_id}[{self.tag_to_id(target.tag)}]"
                    )
        # 100 -> 17s
        if iteration % 10 == 0 and self.minerals > 170:
            self.logging("iteration", iteration, level="info", save_trace=True, print_log=False)
            obs_text = await self.obs_to_text()

            if self.config.enable_rag:
                rag_summary, rag_think = self.rag_agent.run(obs_text)
                self.logging("rag_summary", rag_summary, save_trace=True)
                self.logging("rag_think", rag_think, save_trace=True, print_log=False)
                obs_text += "\n\n# Hint\n" + rag_summary

            if self.config.enable_plan or self.config.enable_plan_verifier:
                suggestions = self.get_suggestions()
                self.logging("suggestions", suggestions, save_trace=True, print_log=False)

                plans, plan_think = self.plan_agent.run(obs_text, verifier=self.plan_verifier, suggestions=suggestions)
                self.logging("plans", plans, save_trace=True)
                self.logging("plan_think", plan_think, save_trace=True, print_log=False)

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

                actions, action_think = self.action_agent.run(obs_text, plans, verifier=self.action_verifier)
                self.logging("actions", actions, save_trace=True)
                self.logging("action_think", action_think, save_trace=True, print_log=False)
            else:
                actions, action_think = self.agent.run(obs_text, verifier=self.action_verifier)
                self.logging("actions", actions, save_trace=True)
                self.logging("action_think", action_think, save_trace=True, print_log=False)

            await self.run_actions(actions)
