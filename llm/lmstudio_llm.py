import requests
from llm.base import BaseLLM, LLMMessage
import config


class LMStudioLLM(BaseLLM):
    def __init__(self):
        self.base_url = config.LMSTUDIO_BASE_URL
        self.model = config.LMSTUDIO_MODEL

    def chat(self, system_prompt: str, messages: list[LLMMessage]) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}]
            + [{"role": m.role, "content": m.content} for m in messages],
            "temperature": 0.7,
            "max_tokens": config.ANTHROPIC_MAX_TOKENS,
            "stream": False,
        }
        resp = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
