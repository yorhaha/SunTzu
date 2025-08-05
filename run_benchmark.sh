#!/bin/bash

# ==============================================================================
#                                 配置区域
# ==============================================================================

# 定义要运行的对战组合列表。格式: "TvP", "TvZ", "PvZ" 等
# T: Terran, P: Protoss, Z: Zerg
MATCHUPS=("TvT" "PvP" "ZvZ")

# 每个对战组合要运行的次数
RUNS_PER_MATCHUP=20

# StarCraft II 参数
MAP_NAME="Flat48"
DIFFICULTY="Harder"
AI_BUILD="RandomBuild"

# 模型和API参数
MODEL_NAME="Qwen2.5-7B-Instruct"
BASE_URL="http://127.0.0.1:12001/v1"
API_KEY=""

# Agent功能开关
ENABLE_PLAN="--enable_plan"
ENABLE_PLAN_VERIFIER="--enable_plan_verifier"
ENABLE_ACTION_VERIFIER="--enable_action_verifier"

# 每次启动之间的间隔时间（秒）
SLEEP_INTERVAL=10

# ==============================================================================
#                                 脚本主体
# ==============================================================================

# 用于存储所有后台进程的PID
pids=()

# 函数：根据首字母获取完整种族名称
get_full_race_name() {
    case "$1" in
        T) echo "Terran" ;;
        P) echo "Protoss" ;;
        Z) echo "Zerg" ;;
        *) echo "" ;; # 返回空字符串表示失败
    esac
}

# 遍历所有定义的对战组合
for matchup in "${MATCHUPS[@]}"; do
    # 使用正则表达式验证格式是否为 "XvY"
    if [[ ! "$matchup" =~ ^[TPZ]v[TPZ]$ ]]; then
        echo "警告: 跳过无效的对战组合格式 '$matchup'" >&2
        continue
    fi

    own_char="${matchup:0:1}"
    enemy_char="${matchup:2:1}"

    OWN_RACE=$(get_full_race_name "$own_char")
    ENEMY_RACE=$(get_full_race_name "$enemy_char")

    echo "------------------------------------------------------------"
    echo "准备为对战 [$matchup] ($DIFFICULTY $MAP_NAME $AI_BUILD) 启动 $RUNS_PER_MATCHUP 次运行"
    echo "Model: ${MODEL_NAME} ($BASE_URL)"
    echo "------------------------------------------------------------"

    # 为当前对战组合运行指定次数
    for i in $(seq 1 $RUNS_PER_MATCHUP); do
        echo "=> 启动第 $i / $RUNS_PER_MATCHUP 次运行 for $matchup..."

        nohup python main.py \
            --player_name "${matchup}_benchmark" \
            --map_name "$MAP_NAME" \
            --difficulty "$DIFFICULTY" \
            --model "$MODEL_NAME" \
            --ai_build "$AI_BUILD" \
            --base_url "$BASE_URL" \
            --api_key "$API_KEY" \
            $ENABLE_PLAN \
            $ENABLE_PLAN_VERIFIER \
            $ENABLE_ACTION_VERIFIER \
            --own_race "$OWN_RACE" \
            --enemy_race "$ENEMY_RACE" &
        
        # 记录最后一个后台进程的PID
        pids+=($!)
        
        # 稍微等待一下，避免瞬间启动过多进程导致系统负载过高
        sleep $SLEEP_INTERVAL
    done
done

echo "============================================================"
echo "所有任务已在后台启动！"
echo "总共启动了 ${#pids[@]} 个进程。"
echo "所有进程的 PID 列表: ${pids[*]}"
echo ""
echo "你可以使用以下命令来监控它们的状态:"
echo "ps -p ${pids[*]}"
echo ""
echo "如果你想一次性终止所有这些进程，请使用:"
echo "kill ${pids[*]}"
echo "============================================================"

# (可选) 如果你希望脚本等待所有后台任务完成后再退出，可以取消下面这行的注释
# wait
