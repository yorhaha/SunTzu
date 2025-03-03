from sc2 import maps
from sc2.player import Bot, Computer
from sc2.main import run_game
from sc2.data import Race, Difficulty, AIBuild
from dotenv import load_dotenv

from players import SinglePlayer, PlanActionPlayer

import sys

load_dotenv()

"""
Difficulty:
    VeryEasy
    Easy
    Medium
    MediumHard
    Hard
    Harder
    VeryHard
    CheatVision
    CheatMoney
    CheatInsane

AIBuild:
    RandomBuild
    Rush
    Timing
    Power
    Macro
    Air

Model:
    DeepSeek-R1-Distill-Qwen-32B
    Qwen2.5-72B-Instruct

Player:
    SinglePlayerWithVerifier
    PlanActionPlayerWithVerifier

Map: (for Melee)
    Flat32
    Flat48
    Flat64
    Flat96
    Flat128
    Simple64
    Simple96
    Simple128
"""

map_name = sys.argv[1]

llm_config = {
    "model_name": "DeepSeek-R1-Distill-Qwen-32B",
    "generation_config": {
        "n": 1,
        "max_tokens": 3072,
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "repetition_penalty": 1.1,
        "presence_penalty": 0.0,
    },
    "service": "vllm",
    "vllm_base_url": "http://172.18.30.73:12001/v1",
}
join_player = Computer(Race.Terran, Difficulty.Medium, ai_build=AIBuild.RandomBuild)

ai_player = PlanActionPlayer(
    player_name="PlanActionPlayerWithVerifier",
    log_path=f"logs/{map_name}/{join_player.difficulty.name}",
    **llm_config,
)
host_player = Bot(Race.Terran, ai_player)

res = run_game(
    maps.get(map_name),
    [host_player, join_player],
    realtime=False,
    rgb_render_config=None,
    save_replay_as=ai_player.log_path + "/replay.SC2Replay",
)

