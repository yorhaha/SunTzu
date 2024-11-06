from tools.llm import get_client


def get_llm_config(model_name, service, temperature):
    llm_config = {
        "model": model_name,
        "temperature": temperature,
        "cache_seed": None,
    }
    client = get_client(model_name, service=service)
    llm_config["api_key"] = client.api_key
    llm_config["base_url"] = client.base_url
    return llm_config


class BaseAgent:
    def __init__(self, model_name: str, service="", temperature=1e-5):
        self.llm_config = get_llm_config(model_name, service, temperature)
        self.service = service
        self.temperature = temperature

    def run(self):
        raise NotImplementedError()
