from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMMessage:
    role: str     # "user" | "assistant"
    content: str


class BaseLLM(ABC):
    @abstractmethod
    def chat(self, system_prompt: str, messages: list[LLMMessage]) -> str:
        """system_promptとメッセージ履歴を受け取り、応答テキストを返す"""
        ...
