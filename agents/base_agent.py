class BaseAgent:
    def __init__(
        self,
        model_name: str,
        service="",
        vllm_base_url="",
        n=1,
        max_tokens=2048,
        temperature=0.8,
        top_p=1,
        top_k=40,
        repetition_penalty=1.0,
        presence_penalty=0.0,
    ):
        self.model_name = model_name
        self.generation_config = {
            "model_name": model_name,
            "service": service,
            "vllm_base_url": vllm_base_url,
            "n": n,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repetition_penalty": repetition_penalty,
            "presence_penalty": presence_penalty,
        }
        self.think = []

    def run(self):
        raise NotImplementedError()

    def save_think(self, think):
        self.think.append(think)
