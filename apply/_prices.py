import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(".env")
client = OpenAI(api_key=os.getenv("TOKENHARBOR_API_KEY"), base_url="https://tokenharbor.ai/v1")
models = client.models.list()
want = {"deepseek-v4.1-flash:free", "deepseek-v4.1-flash", "deepseek-v4-flash:free",
        "claude-haiku-5.5", "openai/gpt-oss-120b"}
for m in models.data:
    mid = getattr(m, "id", "")
    if mid in want:
        raw = getattr(m, "model_dump", lambda: {})()
        pricing = raw.get("pricing") or raw.get("options") or {}
        print(mid, "->", json.dumps(pricing)[:220])
