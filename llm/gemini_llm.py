# pip install google-genai
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from llm.base import BaseLLM, LLMMessage
import config


class GeminiQuotaError(Exception):
    pass


class GeminiLLM(BaseLLM):
    def __init__(self):
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.model = config.GEMINI_MODEL

    def chat(self, system_prompt: str, messages: list[LLMMessage]) -> str:
        contents = []
        for m in messages:
            role = "user" if m.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})

        try:
            response = self.client.models.generate_content(
                model=self.model,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                    max_output_tokens=config.GEMINI_MAX_TOKENS,
                ),
                contents=contents,
            )
        except ClientError as e:
            code = getattr(e, 'status_code', None) or getattr(e, 'code', None) or (e.args[0] if e.args else 0)
            if str(code).startswith('429') or '429' in str(e):
                raise GeminiQuotaError(
                    "Gemini APIのレート制限に達しました（RPM・RPD・TPMのいずれか）。\n"
                    "時間をおくか、起動時にAnthropicまたはLM Studio / Ollamaを選択してください。"
                ) from e
            raise
        # response.text が None になるケース（安全フィルタ等）を保護
        return response.text or ""
