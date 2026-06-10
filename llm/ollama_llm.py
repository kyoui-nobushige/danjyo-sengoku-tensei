import requests
import json
from llm.base import BaseLLM, LLMMessage
import config


class OllamaLLM(BaseLLM):
    def __init__(self):
        self.base_url = config.OLLAMA_BASE_URL
        self.model = config.OLLAMA_MODEL

    def chat(self, system_prompt: str, messages: list[LLMMessage]) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}]
            + [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
        }
        resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
