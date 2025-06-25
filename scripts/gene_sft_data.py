import glob
import json
import random
from collections import Counter
from tqdm import tqdm

trace_files = []
for folders in [
    r"logs\sc2agent-2\*\Qwen2.5-32B-Instruct\*\trace.json",
]:
    trace_files.extend(glob.glob(folders))
print(f"Found {len(trace_files)} trace files.")

def get_step_score(trace, i, eval_window_seconds=25):
    """
    在给定的函数定义下，评估单个步骤(i)的动作质量。

    通过比较步骤i的状态和未来约25秒后的状态，来评估动作的净成果。
    使用更合理的权重和逻辑，避免了原始版本中的核心缺陷。
    """

    start_state = trace[i]
    start_time = start_state["time_seconds"]
    
    # ------------------ 权重定义 (重新平衡) ------------------
    EVALUATION_WINDOW_SECONDS = eval_window_seconds  # 定义一个25秒的评估窗口

    # 负分项 (惩罚)
    PENALTY_SUPPLY_BLOCK = -20      # 卡人口是重大失误，惩罚加重
    PENALTY_WORKER_LOSS = -12       # 损失农民代价高昂
    PENALTY_ARMY_LOSS_PER_SUPPLY = -3 # 按损失的军队人口计算
    PENALTY_STRUCTURE_LOSS = -25    # 损失建筑很伤
    # 基于游戏时间的资源浮动惩罚 (动态惩罚)
    PENALTY_MINERAL_FLOAT_PER_100 = -1 # 每100溢出矿物的惩罚
    PENALTY_VESPENE_FLOAT_PER_100 = -2 # 每100溢出瓦斯的惩罚

    # 正分项 (奖励)
    REWARD_WORKER_PRODUCED = 6      # 奖励农民生产
    REWARD_ARMY_PRODUCED_PER_SUPPLY = 2 # 按增加的军队人口计算
    REWARD_ENEMY_UNIT_KILLED = 4    # 击杀敌方单位
    REWARD_ENEMY_STRUCTURE_KILLED = 30 # 摧毁敌方建筑是巨大优势
    REWARD_STRUCTURE_BUILT = 8      # 奖励新建筑
    REWARD_NEW_STRUCTURE_TYPE = 15  # 奖励科技进步 (解锁新建筑类型)
    # -----------------------------------------------------------

    # --- 寻找评估窗口的终点状态 ---
    future_state = None
    # 从当前步骤之后开始寻找
    for step in range(i + 1, len(trace)):
        state = trace[step]
        if state["time_seconds"] >= start_time + EVALUATION_WINDOW_SECONDS:
            future_state = state
            break
    
    # 如果找不到满足时间窗口的未来状态 (比如这是游戏最后几秒)，就用最后一个状态
    if future_state is None:
        if i < len(trace) - 1:
            future_state = trace[-1]
        else:
            # 如果当前步骤已是最后一步，无法评估
            return 0

    score = 0
    
    # --- 1. 经济健康度评估 ---
    
    # a. 卡人口惩罚: 如果在评估期结束时仍然卡人口
    # supply_left 为 1 或 0 都视为即将或已经卡住
    if future_state["supply_left"] <= 1:
        score += PENALTY_SUPPLY_BLOCK

    # b. 资源浮动惩罚 (动态阈值)
    # 阈值随游戏时间增长，前期要求更严格
    minute = future_state["time_seconds"] / 60
    mineral_threshold = 250 + minute * 100  # 阈值随时间放宽
    vespene_threshold = 150 + minute * 80
    
    if future_state["minerals"] > mineral_threshold:
        excess_minerals = future_state["minerals"] - mineral_threshold
        score += (excess_minerals / 100) * PENALTY_MINERAL_FLOAT_PER_100
        
    if future_state["vespene"] > vespene_threshold:
        excess_vespene = future_state["vespene"] - vespene_threshold
        score += (excess_vespene / 100) * PENALTY_VESPENE_FLOAT_PER_100
        
    # --- 2. 单位数量净变化评估 ---
    
    # a. 农民变化
    worker_delta = future_state["supply_workers"] - start_state["supply_workers"]
    if worker_delta > 0:
        score += worker_delta * REWARD_WORKER_PRODUCED
    elif worker_delta < 0:
        score += abs(worker_delta) * PENALTY_WORKER_LOSS

    # b. 军队人口变化
    army_delta = future_state["supply_army"] - start_state["supply_army"]
    if army_delta > 0:
        score += army_delta * REWARD_ARMY_PRODUCED_PER_SUPPLY
    elif army_delta < 0:
        score += abs(army_delta) * PENALTY_ARMY_LOSS_PER_SUPPLY
        
    # --- 3. 战果评估 ---
    
    # a. 敌方单位损失
    enemy_units_killed = start_state["n_enemy_units"] - future_state["n_enemy_units"]
    if enemy_units_killed > 0:
        score += enemy_units_killed * REWARD_ENEMY_UNIT_KILLED
        
    # b. 敌方建筑损失
    enemy_structures_destroyed = start_state["n_enemy_structures"] - future_state["n_enemy_structures"]
    if enemy_structures_destroyed > 0:
        score += enemy_structures_destroyed * REWARD_ENEMY_STRUCTURE_KILLED
        
    # --- 4. 建筑与科技评估 ---
    
    # a. 我方建筑数量变化
    structure_delta = future_state["n_structures"] - start_state["n_structures"]
    if structure_delta > 0:
        score += structure_delta * REWARD_STRUCTURE_BUILT
    elif structure_delta < 0:
        score += abs(structure_delta) * PENALTY_STRUCTURE_LOSS

    # b. 科技进步 (新建筑类型)
    if future_state["n_structure_types"] > start_state["n_structure_types"]:
        new_types = future_state["n_structure_types"] - start_state["n_structure_types"]
        score += new_types * REWARD_NEW_STRUCTURE_TYPE

    return score


n_plans = 0
n_actions = 0

plan_turn_cnter = Counter()
action_turn_cnter = Counter()
plan_time_cnter = Counter()
action_time_cnter = Counter()
action_counter = Counter()
step_score_cnter = Counter()

sft_data = []
for trace_file in tqdm(trace_files):
    tqdm.write(f"Processing {trace_file}...")
    with open(trace_file, "r", encoding="utf-8") as f:
        trace_data = json.load(f)
    trace_data = list(trace_data.values())
    if trace_data[-1]["game_result"] != "Victory":
        continue
    trace_data = trace_data[:-1]
    while trace_data[-1]["n_enemy_units"] == 0:
        trace_data.pop()
    for i, trace in enumerate(trace_data):
        gamma = 1.0
        for window in range(5, 60, 5):
            step_score = get_step_score(trace_data, i, eval_window_seconds=window) * gamma
            if window > 20:
                gamma *= 0.9  # 每个窗口的分数递减
        gamma = int(gamma / 100)
        step_score_cnter.update([step_score])
        if step_score <= 50:
            continue
        if "plans" not in trace or "actions" not in trace:
            continue
        
        ### Add Plan
        if len(trace["plan_think"][-1]) == 1:
            trace["plan_think"] = trace["plan_think"][:-1]
            trace["plan_chat_history"] = trace["plan_chat_history"][:-1]
        
        if 1 <= len(trace["plans"]) <= 5:
            if '"error_number": 0' in trace["plan_think"][-1][-1]:
                if 'Once ' not in trace["plan_think"][-1][-2]:
                    sft_data.append({"conversations": trace["plan_chat_history"][-2]})
                    plan_turn_cnter.update([len(trace["plan_chat_history"][-2])])
                    plan_time_cnter.update([trace["time_seconds"]])
                    n_plans += 1
            
            sft_data.append({"conversations": trace["plan_chat_history"][-1]})
            plan_turn_cnter.update([len(trace["plan_chat_history"][-1])])
            plan_time_cnter.update([trace["time_seconds"]])
            n_plans += 1
            
            plan_time_cnter.update([trace["time_seconds"]])
            if len(trace["plan_chat_history"]) > 2:
                sft_data.append({"conversations": trace["plan_chat_history"][-3]})
                plan_turn_cnter.update([len(trace["plan_chat_history"][-3])])
                plan_time_cnter.update([trace["time_seconds"]])
                n_plans += 1
        
        # Add Action
        has_invalid_action = False
        for action in trace["valid_actions"]:
            if "is_valid" in action and not action["is_valid"]:
                has_invalid_action = True
                break
        if len(trace["actions"]) > 0 and not has_invalid_action:
            action_set = set([action["action"] for action in trace["actions"]])
            if len(action_set) == 1 and "ATTACK_ATTACK" in action_set:
                continue
            sft_data.append({"conversations": trace["action_chat_history"][-1]})
            action_turn_cnter.update([len(trace["action_chat_history"][-1])])
            action_time_cnter.update([trace["time_seconds"]])
            n_actions += 1
            action_counter.update([action["action"] for action in trace["actions"]])

with open("sc2-0618.json", "w", encoding="utf-8") as f:
    sft_data_str = json.dumps(sft_data, indent=4, ensure_ascii=False)
    sft_data_str = sft_data_str.replace('"role": "user",', '"from": "human",')
    sft_data_str = sft_data_str.replace('"role": "assistant",', '"from": "gpt",')
    sft_data_str = sft_data_str.replace('"content":', '"value":')
    f.write(sft_data_str)
print(f"Plan turn counts: {plan_turn_cnter}")
print(f"Action turn counts: {action_turn_cnter}")
print(f"Total plans: {n_plans}, Total actions: {n_actions}")

import matplotlib.pyplot as plt

# plot the distribution of time cnter
plt.figure(figsize=(10, 5))
plt.subplot(1, 2, 1)
plt.bar(plan_time_cnter.keys(), plan_time_cnter.values(), color='blue', alpha=0.7)
plt.title('Plan Time Distribution')
plt.xlabel('Time (seconds)')
plt.ylabel('Count')
plt.subplot(1, 2, 2)
plt.bar(action_time_cnter.keys(), action_time_cnter.values(), color='orange', alpha=0.7)
plt.title('Action Time Distribution')
plt.xlabel('Time (seconds)')
plt.ylabel('Count')
plt.tight_layout()
plt.show()

# plot actions with hbar chart
plt.figure(figsize=(10, 5))
sorted_actions = action_counter.most_common()
plt.barh([action[0] for action in sorted_actions], [action[1] for action in sorted_actions], color='green', alpha=0.7)
plt.title('Action Distribution')
plt.xlabel('Count')
plt.ylabel('Action')
plt.tight_layout()
plt.show()

# plot step score distribution
plt.figure(figsize=(10, 5))
plt.bar(step_score_cnter.keys(), step_score_cnter.values(), color='purple', alpha=0.7)
plt.title('Step Score Distribution')
plt.xlabel('Step Score')
plt.ylabel('Count')
plt.tight_layout()
plt.show()

