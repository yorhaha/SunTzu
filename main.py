from sc2 import maps
from sc2.player import Bot, Computer
from sc2.main import run_game
from sc2.data import Race, Difficulty
from dotenv import load_dotenv

from player.llm_player import LLMPlayer

import sys

load_dotenv()

map_names = [sys.argv[1]]
n_game = int(sys.argv[2])

for map_name in map_names:
    for _ in range(n_game):
        host_player = Bot(Race.Terran, LLMPlayer())
        join_player = Computer(Race.Terran, Difficulty.Easy)
        res = run_game(
            maps.get(map_name),
            [host_player, join_player],
            realtime=False,
            rgb_render_config=None,
        )
