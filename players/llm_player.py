from .base_player import BasePlayer
from agents import PlanAgent, ActionAgent, RagAgent, SingleAgent
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.units import Units
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
        self.scv_auto_attack_distance = 2
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
            suggestions.append("Consider building a second Barracks to increase unit production with 400 minerals.")
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
            and self.already_pending_upgrade(UpgradeId.WARPGATETECHNOLOGY) == 0
            and self.can_afford(UpgradeId.WARPGATETECHNOLOGY)
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

        if self.time < 300:
            suggestions.append(
                "The enemy will start a fierce attack at 03:00, so you need to start producing a large number of attack units at least at 02:00."
            )

        if self.config.own_race == "Terran":
            suggestions.extend(self.get_terran_suggestions())
        elif self.config.own_race == "Protoss":
            suggestions.extend(self.get_protoss_suggestions())

        # # --- 侦测到敌方早期运营和单位 ---
        # # 侦测到敌方攻城坦克 (Siege Tank)
        # if self.enemy_units(UnitTypeId.SIEGETANK).exists:
        #     suggestions.append(
        #         "Enemy Siege Tanks detected! Consider: Producing Vikings for air superiority and vision, getting your own Siege Tanks, using Medivac drops to harass, or Banshees if their anti-air is weak (requires cloaking)."
        #     )
        # # 侦测到敌方大量生化部队 (Marine, Marauder)
        # # 你可能需要更精确的条件来判断“大量”，例如单位数量或组合
        # if self.enemy_units(UnitTypeId.MARINE).amount >= 6 or self.enemy_units(UnitTypeId.MARAUDER).amount >= 3:
        #     suggestions.append("Significant enemy bio force (Marines/Marauders) detected! Consider: Matching with your own bio and upgrading infantry weapons/armor, producing Siege Tanks, planting Widow Mines, or using Hellions/Hellbats (with Infernal Pre-Igniter against Marines).")
        # # 侦测到敌方维京战机 (Viking)
        # if self.enemy_units(UnitTypeId.VIKINGFIGHTER).exists:
        #     suggestions.append(
        #         "Enemy Vikings detected! Consider: Producing your own Vikings to contest air control, building Missile Turrets for static defense, or using massed stimmed Marines if you have ground superiority and they overcommit to Vikings."
        #     )
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
