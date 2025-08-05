#!/bin/bash

# --- 配置 ---
# 1. 设置您希望运行的总次数
TOTAL_RUNS=100

# 2. 定义所有选项的数组
MAP_OPTIONS=("Flat32" "Flat48" "Flat64")
DIFFICULTY_OPTIONS=("Medium" "MediumHard" "Hard" "Harder" "VeryHard")
AI_BUILD_OPTIONS=("RandomBuild" "Timing" "Rush" "Macro" "Power" "Air")
RACE_OPTIONS=("Terran" "Protoss" "Zerg")

MODEL_NAME="Qwen2.5-7B-Instruct"
BASE_URL="http://127.0.0.1:12001/v1"
API_KEY=""

# --- 主循环 ---
# 使用 for 循环运行 N 次
for (( i=1; i<=TOTAL_RUNS; i++ ))
do
    echo "=================================================="
    echo "===> 开始第 $i / $TOTAL_RUNS 次运行"
    echo "=================================================="

    # --- 随机选择配置 ---
    # 从数组中随机选择一个元素
    # 语法: ARRAY[ $RANDOM % ${#ARRAY[@]} ]
    # $RANDOM 是一个0-32767的随机数
    # ${#ARRAY[@]} 是数组的长度
    # % 是取模运算符，确保结果在数组索引范围内
    MAP=${MAP_OPTIONS[ $RANDOM % ${#MAP_OPTIONS[@]} ]}
    DIFFICULTY=${DIFFICULTY_OPTIONS[ $RANDOM % ${#DIFFICULTY_OPTIONS[@]} ]}
    AI_BUILD=${AI_BUILD_OPTIONS[ $RANDOM % ${#AI_BUILD_OPTIONS[@]} ]}
    OWN_RACE=${RACE_OPTIONS[ $RANDOM % ${#RACE_OPTIONS[@]} ]}
    ENEMY_RACE=${RACE_OPTIONS[ $RANDOM % ${#RACE_OPTIONS[@]} ]}

    # --- 执行命令 ---
    PLAYER_NAME="sc2agent"

    python main.py \
        --player_name "${PLAYER_NAME}" \
        --map_name "${MAP}" \
        --difficulty "${DIFFICULTY}" \
        --model "${MODEL}" \
        --ai_build "${AI_BUILD}" \
        --enable_plan \
        --enable_plan_verifier \
        --enable_action_verifier \
        --enable_random_decision_interval \
        --own_race "${OWN_RACE}" \
        --enemy_race "${ENEMY_RACE}" \
        --base_url "${BASE_URL}" \
        --api_key "${API_KEY}"

done

echo "=================================================="
echo "所有 ${TOTAL_RUNS} 次运行已全部完成。"
echo "=================================================="
