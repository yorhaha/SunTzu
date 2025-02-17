import time
import random
import os
import json
from threading import Thread
from tqdm import tqdm
from openai import OpenAI

from tools.format import extract_code
from tools.common import pause_for_continue


def get_client(model_name, service="", vllm_base_url=""):
    if service == "vllm":
        base_url = vllm_base_url
        api_key = os.getenv("VLLM_API_KEY")
    elif service == "siliconflow":
        base_url = "https://api.siliconflow.cn/v1"
        api_key = os.getenv("SILICONFLOW_API_KEY")
    elif service == "gptapi.us":
        base_url = "https://api.gptapi.us/v1"
        api_key = os.getenv("GPTAPI_US_API_KEY")

    elif model_name.startswith("glm"):
        base_url = "https://open.bigmodel.cn/api/paas/v4/"
        api_key = os.getenv("GLM_API_KEY")
    elif model_name.startswith("deepseek"):
        base_url = "https://api.deepseek.com/v1"
        api_key = os.getenv("DEEPSEEK_API_KEY")

    else:
        raise ValueError(f"Unsupported model: {model_name}")

    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
    )
    return client


def call_openai(
    model_name: str,
    prompt: str,
    max_tokens=2048,
    history=[],
    n=1,
    temperature=0.8,
    top_p=1,
    top_k=40,
    repetition_penalty=1.0,
    presence_penalty=0.0,
    timeout=60,
    system_message=None,
    service="",
    retry_times=10,
    vllm_base_url="",
    need_json=False,
):
    client = get_client(model_name, service, vllm_base_url)
    
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    
    def call_openai_thread():
        completion = client.chat.completions.create(
            model=model_name,
            messages=messages,
            max_tokens=max_tokens,
            n=n,
            temperature=temperature,
            top_p=top_p,
            # top_k=top_k,
            # repetition_penalty=repetition_penalty,
            # presence_penalty=presence_penalty,
            timeout=timeout,
        )

        response = [choice.message.content.strip() for choice in completion.choices]
        if need_json:
            json.loads(extract_code(response[0]))
        return response

    while True:
        for _ in range(retry_times):
            try:
                response = call_openai_thread()
                return response
            except Exception as e:
                print("Error while calling LLM service:", e)
                time.sleep(random.random() * 5)
                continue
        
        print("Connect LLM service failed.")
        print("Retry after 5 minutes or press Enter to retry immediately.")
        print("Use Ctrl+C to exit.")
        pause_for_continue(300)
    
    if service == "vllm":
        raise ValueError("请求LLM API失败，可能原因：API服务挂了；不在内网；超出上下文；模型不存在。")
    raise ValueError("Fail to connect LLM service:", client.base_url)
