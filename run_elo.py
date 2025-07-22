from sc2 import maps
from sc2.player import Bot
from sc2.main import run_game
from sc2.data import Race
import json

from players import LLMPlayer
from tools.llm import LLMClient

MAP_NAME = "Flat48"
RACE = "Terran"

enable_random_decision_interval = False

class Config:
    def __init__(self, data: dict):
        for k, v in data.items():
            self.__setattr__(k, v)

config_1 = Config({
    "map_name": MAP_NAME,
    "model_name": "Qwen2.5-7B-Instruct",
    "player_name": "Qwen2.5-7B Agent",
    "enable_rag": False,
    "enable_plan": True,
    "enable_plan_verifier": True,
    "enable_action_verifier": True,
    "base_url": "http://127.0.0.1:12001/v1",
    "api_key": "sk-11223344",
    "own_race": RACE,
    "enemy_race": RACE,
    "enable_random_decision_interval": enable_random_decision_interval,
})

llm_config_1 = {
    "model_name": config_1.model_name,
    "generation_config": {
        "model_name": config_1.model_name,
        "n": 1,
        "max_tokens": 6144,
        "temperature": 0.1,
        "top_p": 0.8,
        "top_k": 20,
        "repetition_penalty": 1.1,
        "presence_penalty": 0.0,
    },
    "llm_client": LLMClient(
        base_url=config_1.base_url,
        api_key=config_1.api_key,
    ),
}

config_2 = Config({
    "map_name": MAP_NAME,
    "model_name": "Qwen2.5-7B-v2",
    "player_name": "Qwen2.5-7B-v2 Agent",
    "enable_rag": False,
    "enable_plan": True,
    "enable_plan_verifier": True,
    "enable_action_verifier": True,
    "base_url": "http://127.0.0.1:12004/v1",
    "api_key": "sk-11223344",
    "own_race": RACE,
    "enemy_race": RACE,
    "enable_random_decision_interval": enable_random_decision_interval,
})

llm_config_2 = {
    "model_name": config_2.model_name,
    "generation_config": {
        "model_name": config_2.model_name,
        "n": 1,
        "max_tokens": 6144,
        "temperature": 0.1,
        "top_p": 0.8,
        "top_k": 20,
        "repetition_penalty": 1.1,
        "presence_penalty": 0.0,
    },
    "llm_client": LLMClient(
        base_url=config_2.base_url,
        api_key=config_2.api_key,
    ),
}


log_path_1 = f"logs/elo/{config_1.map_name}/{config_1.model_name} v.s. {config_2.model_name}"

# Initialize players
ai_player_1 = LLMPlayer(
    config=config_1,
    player_name=config_1.player_name,
    log_path=log_path_1,
    **llm_config_1,
)
ai_player_2 = LLMPlayer(
    config=config_2,
    player_name=config_2.player_name,
    enable_logging=False,
    **llm_config_2,
)

player_1 = Bot(getattr(Race, config_1.own_race), ai_player_1)
player_2 = Bot(getattr(Race, config_2.own_race), ai_player_2)


with open(ai_player_1.log_path + "/config_1.json", "w", encoding="utf-8") as f:
    json.dump(vars(config_1), f, indent=4)
with open(ai_player_1.log_path + "/config_2.json", "w", encoding="utf-8") as f:
    json.dump(vars(config_2), f, indent=4)

res = run_game(
    maps.get(MAP_NAME),
    [player_1, player_2],
    realtime=False,
    rgb_render_config=None,
    save_replay_as=ai_player_1.log_path + "/replay.SC2Replay",
)
