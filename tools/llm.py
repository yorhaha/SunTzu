import time
import random
import os
from threading import Thread
from tqdm import tqdm
from openai import OpenAI


def get_client(model_name, service=""):
    if service == "vllm":
        base_url = "http://localhost:12001/v1"
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
    timeout=60,
    system_message="You are a helpful assistant.",
    service="",
    retry_times=3,
):
    client = get_client(model_name, service)
    messages = [
        {"role": "system", "content": system_message},
        *history,
        {"role": "user", "content": prompt},
    ]

    for _ in range(retry_times):
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens,
                n=n,
                temperature=temperature,
                top_p=top_p,
                timeout=timeout,
            )

            response = [choice.message.content.strip() for choice in completion.choices]

            return response
        except Exception as e:
            continue
    raise ValueError("Fail to connect LLM service:", client.base_url)


def batch_call_openai(
    n_thread: int,
    model_name: str,
    prompts,
    temperature=0.2,
    max_tokens=2000,
    retry_times=5,
    show_progress=True,
    print_response=False,
    service="",
):
    client = get_client(model_name, service)

    responses = [""] * n
    n = len(prompts)
    batch_size = n // n_thread

    def call_openai_thread(start, end):
        for i, prompt in tqdm(enumerate(prompts[start:end]), total=end - start, disable=not show_progress):
            content = ""
            for _ in range(retry_times):
                try:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a helpful assistant.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    content = response.choices[0].message.content

                    if n_thread == 1 or print_response:
                        tqdm.write("\033[91m" + "==== Response ====" + "\033[0m")
                        tqdm.write(content)

                    assert content, "Empty response"
                    break
                except Exception as e:
                    tqdm.write(f"Error: {e}")
                    time.sleep(random.random() * 5)

            responses[start + i] = content

    threads = []

    for i in range(n_thread):
        start = i * batch_size
        end = n if i == n_thread - 1 else (i + 1) * batch_size
        thread = Thread(target=call_openai_thread, args=(start, end))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
    return responses
