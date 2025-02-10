from sc2 import maps
from sc2.player import Bot, Computer
from sc2.main import run_game
from sc2.data import Race, Difficulty
from dotenv import load_dotenv

from players import SinglePlayer

import sys

load_dotenv()

map_name = sys.argv[1]

ai_player = SinglePlayer(
    player_name="SinglePlayerWithVerifier",
    model_name="DeepSeek-R1-Distill-Qwen-32B",
    service="vllm",
    vllm_base_url="http://172.18.30.73:12001/v1",
    generation_config={
        "n": 1,
        "max_tokens": 8192,
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "repetition_penalty": 1.1,
        "presence_penalty": 0.0,
    },
)
host_player = Bot(Race.Terran, ai_player)
join_player = Computer(Race.Terran, Difficulty.Easy)
res = run_game(
    maps.get(map_name),
    [host_player, join_player],
    realtime=False,
    rgb_render_config=None,
    save_replay_as=ai_player.log_path + "/replay.SC2Replay",
)
