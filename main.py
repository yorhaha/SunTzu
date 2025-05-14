from sc2 import maps
from sc2.player import Bot, Computer
from sc2.main import run_game
from sc2.data import Race, Difficulty, AIBuild
from dotenv import load_dotenv
from argparse import ArgumentParser
import json

from players import LLMPlayer

load_dotenv()

"""
Usage example:
python main.py --player_name spb --map_name Flat32 --difficulty Easy --model Qwen2.5-32B-Instruct --ai_build RandomBuild --enable_human --enable_plan --enable_plan_verifier --enable_action_verifier --enable_action_verifier
"""

parser = ArgumentParser()
parser.add_argument(
    "--map_name",
    choices=["Flat32", "Flat48", "Flat64", "Flat96", "Flat128", "Simple64", "Simple96", "Simple128"],
    help="Map name",
    required=True,
)
parser.add_argument(
    "--difficulty",
    choices=[
        "VeryEasy",
        "Easy",
        "Medium",
        "MediumHard",
        "Hard",
        "Harder",
        "VeryHard",
        "CheatVision",
        "CheatMoney",
        "CheatInsane",
    ],
    help="Bot difficulty",
    required=True,
)
parser.add_argument("--model_name", type=str, required=True, help="Model name")
parser.add_argument(
    "--ai_build", choices=["RandomBuild", "Rush", "Timing", "Power", "Macro", "Air"], help="AI build", default="RandomBuild"
)
parser.add_argument("--player_name", type=str, help="Player name", default="player")
parser.add_argument("--enable_rag", action="store_true", help="Enable RAG agent")
parser.add_argument("--enable_plan", action="store_true", help="Enable Plan agent")
parser.add_argument("--enable_plan_verifier", action="store_true", help="Enable Plan verifier agent")
parser.add_argument("--enable_action_verifier", action="store_true", help="Enable Action verifier agent")
parser.add_argument("--enable_human", action="store_true", help="Enable human agent")
args = parser.parse_args()

map_name = args.map_name
difficulty = args.difficulty
model_name = args.model_name
ai_build = args.ai_build
player_name = args.player_name

log_path = f"logs/{player_name}/{map_name}/{difficulty}/{ai_build}"

llm_config = {
    "service": "vllm",
    "vllm_base_url": "http://172.18.30.162:12001/v1",
    "model_name": model_name,
    "generation_config": {
        "n": 1,
        "max_tokens": 4096,
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "repetition_penalty": 1.1,
        "presence_penalty": 0.0,
    },
}
join_player = Computer(
    race=Race.Terran,
    difficulty=getattr(Difficulty, difficulty),
    ai_build=getattr(AIBuild, ai_build),
)
ai_player = LLMPlayer(
    config=args,
    player_name=player_name,
    log_path=log_path,
    **llm_config,
)
host_player = Bot(Race.Terran, ai_player)

with open(ai_player.log_path + "/config.json", "w", encoding="utf-8") as f:
    json.dump(vars(args), f, indent=4)

res = run_game(
    maps.get(map_name),
    [host_player, join_player],
    realtime=False,
    rgb_render_config=None,
    save_replay_as=ai_player.log_path + "/replay.SC2Replay",
)
