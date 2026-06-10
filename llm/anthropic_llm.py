import anthropic
from llm.base import BaseLLM, LLMMessage
import config


class AnthropicLLM(BaseLLM):
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.model = config.ANTHROPIC_MODEL
        self.max_tokens = config.ANTHROPIC_MAX_TOKENS

    def chat(self, system_prompt: str, messages: list[LLMMessage]) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        return response.content[0].text
