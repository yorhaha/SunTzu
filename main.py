from sc2 import maps
from sc2.player import Bot, Computer
from sc2.main import run_game
from sc2.data import Race, Difficulty
from dotenv import load_dotenv

from player.llm_player import LLMPlayer
from player.no_player import NoPlayer

import sys

load_dotenv()

map_name = sys.argv[1]

llm_player = LLMPlayer()
host_player = Bot(Race.Terran, llm_player)
join_player = Computer(Race.Terran, Difficulty.Easy)
res = run_game(
    maps.get(map_name),
    [host_player, join_player],
    realtime=False,
    rgb_render_config=None,
    save_replay_as=llm_player.log_path + ".SC2Replay",
)
