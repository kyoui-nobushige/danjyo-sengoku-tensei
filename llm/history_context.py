"""
史実コンテキストローダー

data/history/{warlord_id}.txt を読み込み、
Wikipedia全文をAIプロンプトに注入する。
"""
from __future__ import annotations
import os

_HISTORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "data", "history")

_cache: dict[str, str] = {}


def load_history(warlord_id: str) -> str:
    if warlord_id in _cache:
        return _cache[warlord_id]
    path = os.path.join(_HISTORY_DIR, f"{warlord_id}.txt")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    _cache[warlord_id] = text
    return text


def build_historical_pressure(warlord_id: str, current_year: int) -> str:
    """
    武将のWikipedia全文を「史実資料」として返す。
    txtファイルがない場合は空文字を返す。
    """
    text = load_history(warlord_id)
    if not text:
        return ""
    return (
        f"【あなたに関するWikipedia史実資料】\n"
        f"{text}\n"
        f"【/史実資料】\n"
        f"上記の史実を踏まえ、{current_year}年時点の状況として自然に行動せよ。"
        f"ただし現在のゲーム状況が史実と異なる場合は、状況に即して判断してよい。"
    )
