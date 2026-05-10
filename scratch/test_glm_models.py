
import os
import json
from openai import OpenAI

def test_models():
    api_key = "4d5ba3e66af04c6db476f94b7506be36.dd05X0p66QBAARgx"
    base_url = "https://open.bigmodel.cn/api/paas/v4"
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        models = client.models.list()
        print("Available models:")
        for m in models.data:
            print(f"- {m.id}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_models()
