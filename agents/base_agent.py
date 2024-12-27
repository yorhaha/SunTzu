class BaseAgent:
    def __init__(
        self,
        model_name: str,
        service="",
        vllm_ip="localhost",
        vllm_port=12001,
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
            "vllm_ip": vllm_ip,
            "vllm_port": vllm_port,
            "n": n,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repetition_penalty": repetition_penalty,
            "presence_penalty": presence_penalty,
        }

    def run(self):
        raise NotImplementedError()
