# ── APIキー ───────────────────────────────────────────────────────
# このファイルを config.py にリネームしてAPIキーを入力してください
ANTHROPIC_API_KEY = ""   # https://console.anthropic.com でAPIキーを取得
GEMINI_API_KEY = ""      # https://aistudio.google.com/apikey でAPIキーを取得

# ── LLM設定(起動時に選択可能。ここはデフォルト) ──────────────────
LLM_PROVIDER = "anthropic"   # "anthropic" | "gemini" | "lmstudio" | "ollama"

ANTHROPIC_MODEL = "claude-sonnet-4-6"
ANTHROPIC_MAX_TOKENS = 1024
GEMINI_MAX_TOKENS = 8192

GEMINI_MODEL = "gemini-2.5-flash"   # gemini-2.5-flash / gemini-2.0-flash など

LMSTUDIO_BASE_URL = "http://localhost:1234"
LMSTUDIO_MODEL = "google/gemma-4-e2b"

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.1:8b"

# ── ゲーム設定 ────────────────────────────────────────────────────
MAX_DIPLOMACY_EXCHANGES = 3
AI_WARLORD_THINK_VISIBLE = True
