"""
watch_requests.py — llm_request.json の新規書き込みを検知して stdout に出力する。
Monitor ツールでこのスクリプトを監視し、Claude Code が応答を書く。

使い方:
  python watch_requests.py
"""
import hashlib
import io
import json
import os
import sys
import time

# Windows の cp932 問題を回避
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

_GAME_DIR = os.path.dirname(os.path.abspath(__file__))
_REQUEST_FILE = os.path.join(_GAME_DIR, "llm_request.json")

_POLL_INTERVAL = 0.5  # 秒

def main():
    last_hash = None
    print("WATCH_READY", flush=True)

    while True:
        try:
            if os.path.exists(_REQUEST_FILE):
                with open(_REQUEST_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                h = hashlib.md5(content.encode()).hexdigest()
                if h != last_hash:
                    last_hash = h
                    # 1行で出力（Monitor が1行ごとに通知するため）
                    print(f"REQUEST:{content}", flush=True)
            else:
                # ファイルが消えたらハッシュをリセット（次のリクエストに備える）
                last_hash = None
        except (OSError, UnicodeDecodeError):
            pass
        time.sleep(_POLL_INTERVAL)

if __name__ == "__main__":
    main()
