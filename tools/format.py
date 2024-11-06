import re
import json

code_pattern = re.compile(r"```.*?\n(.*?)\n```", re.DOTALL)


def extract_code(text):
    code = code_pattern.search(text)
    if code:
        return code.group(1).strip()
    return ""


def parse_function_call(function_call):
    pattern = r"(?P<name>\w+)\((?P<params>.*)\)"
    match = re.match(pattern, function_call.strip())

    if not match:
        return None

    function_name = match.group("name")
    params_str = match.group("params")

    param_pattern = r"(?P<key>\w+)\s*=\s*(?P<value>[^,]+)"

    params = re.findall(param_pattern, params_str)

    params_dict = {key: eval(value) for key, value in params}
    result = {"name": function_name, "parameters": params_dict}

    return result


def test_extract_code():
    text = """
test

```python
def test():
    print("test")
```

thanks
"""
    print(extract_code(text))


def test_parse_function_call():
    function_call = 'call_openai(max_tokens=2048, n=1, temperature=0.8, top_p=1, name="yes")'

    print(json.dumps(parse_function_call(function_call), indent=2))


if __name__ == "__main__":
    test_extract_code()
    test_parse_function_call()
