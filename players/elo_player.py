class Config:
    def __init__(self, data: dict):
        for k, v in data.items():
            self.__setattr__(k, v)

def get_elo_player(map_name: str, own_race: str, enemy_race: str):
    config_1 = Config({
        "map_name": map_name,
        "model_name": "Qwen2.5-7B-Instruct",
        "player_name": "Qwen2.5-7B Agent",
        "enable_rag": False,
        "enable_plan": True,
        "enable_plan_verifier": True,
        "enable_action_verifier": True,
        "base_url": "http://127.0.0.1:12001/v1",
        "api_key": "sk-11223344",
        "own_race": own_race,
        "enemy_race": enemy_race,
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