import time

def timer(func):
    def wrapper(*args, **kwargs):
        print(f"[{func.__name__}] running ...", end=" ", flush=True)
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"cost {int(elapsed_time)} seconds.")
        return result

    return wrapper
