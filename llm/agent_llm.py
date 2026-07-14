import json, subprocess
from llm.base import BaseLLM, LLMMessage


class AgentLLM(BaseLLM):
    def chat(self, system_prompt: str, messages: list[LLMMessage]) -> str:
        prompt = f"{system_prompt}\n\n"
        for m in messages:
            label = "ユーザー" if m.role == "user" else "軍師"
            prompt += f"{label}: {m.content}\n"
        prompt += "軍師:"
        try:
            r = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True, text=True, timeout=60,
                encoding="utf-8", stdin=subprocess.DEVNULL,
            )
            return r.stdout.strip()
        except Exception as e:
            print(f"[AgentLLM] エラー: {e}")
            return ""
