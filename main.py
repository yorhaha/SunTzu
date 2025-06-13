from sc2 import maps
from sc2.player import Bot, Computer
from sc2.main import run_game
from sc2.data import Race, Difficulty, AIBuild
from dotenv import load_dotenv
from argparse import ArgumentParser
import json
import os

from players import LLMPlayer
from tools import constants
from tools.llm import LLMClient

load_dotenv()


def parse_args():
    """
    Usage example:
    python main.py --player_name spb --map_name Flat32 --difficulty Medium --model Qwen2.5-32B-Instruct --ai_build RandomBuild --enable_plan --enable_plan_verifier --enable_action_verifier
    """
    parser = ArgumentParser()
    parser.add_argument(
        "--map_name",
        choices=constants.map_choices,
        help="Map name",
        required=True,
    )
    parser.add_argument(
        "--difficulty",
        choices=constants.difficulty_choices,
        help="Bot difficulty",
        required=True,
    )
    parser.add_argument("--model_name", type=str, required=True, help="Model name")
    parser.add_argument(
        "--ai_build",
        choices=constants.ai_build_choices,
        help="AI build",
        default="RandomBuild",
    )
    parser.add_argument(
        "--player_name", type=str, help="Player name", default="default_player"
    )
    parser.add_argument("--enable_rag", action="store_true", help="Enable RAG agent")
    parser.add_argument("--enable_plan", action="store_true", help="Enable Plan agent")
    parser.add_argument(
        "--enable_plan_verifier", action="store_true", help="Enable Plan verifier agent"
    )
    parser.add_argument(
        "--enable_action_verifier",
        action="store_true",
        help="Enable Action verifier agent",
    )
    parser.add_argument(
        "--base_url",
        type=str,
        default=os.getenv("BASE_URL", ""),
        help="Base URL for the LLM API service",
    )
    parser.add_argument(
        "--api_key",
        type=str,
        default=os.getenv("API_KEY", ""),
        help="API key for the LLM API service",
    )

    args = parser.parse_args()

    if args.enable_plan_verifier and not args.enable_plan:
        raise ValueError(
            "Plan verifier requires Plan agent to be enabled. Please enable Plan agent with --enable_plan."
        )
    if not args.base_url or not args.api_key:
        raise ValueError(
            "Base URL and API key must be provided. Please set them using --base_url and --api_key."
        )

    return args


args = parse_args()
log_path = f"logs/{args.player_name}/{args.map_name}_{args.difficulty}_{args.ai_build}"

map_name = args.map_name
difficulty = args.difficulty
model_name = args.model_name
ai_build = args.ai_build
player_name = args.player_name

# Initialize LLM service
llm_config = {
    "model_name": model_name,
    "generation_config": {
        "model_name": model_name,
        "n": 1,
        "max_tokens": 6144,
        "temperature": 0.1,
        "top_p": 0.8,
        "top_k": 20,
        "repetition_penalty": 1.1,
        "presence_penalty": 0.0,
    },
    "llm_client": LLMClient(
        base_url=args.base_url,
        api_key=args.api_key,
    ),
}

# Initialize players
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
