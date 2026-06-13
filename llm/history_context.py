"""
史実コンテキストローダー

data/history/{warlord_id}.txt を読み込み、Wikipedia全文をAIプロンプトに注入する。
data/history/nenpo_{scenario_id}.txt から3年チャンク単位で史実イベントを注入する。
"""
from __future__ import annotations
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import GameState

_HISTORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "data", "history")

_cache: dict[str, str] = {}

CHUNK_SIZE = 3
BASE_YEAR = 1560


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


def load_nenpo(scenario_id: str = "hizen") -> str:
    path = os.path.join(_HISTORY_DIR, f"nenpo_{scenario_id}.txt")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def _parse_nenpo(text: str) -> list[dict]:
    """年表テキストをパース。戻り値: [{"year": int, "month": int|None, "text": str, "requires": list[str]}]"""
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('■') or line.startswith('【'):
            continue
        parts = line.split('|')
        if len(parts) < 2:
            continue
        year_raw = parts[0].replace('年', '').strip()
        month: int | None = None
        if '/' in year_raw:
            y_str, m_str = year_raw.split('/', 1)
            try:
                year = int(y_str)
                month = int(m_str)
            except ValueError:
                continue
        else:
            try:
                year = int(year_raw)
            except ValueError:
                continue
        content = parts[1].strip()
        requires: list[str] = []
        if len(parts) >= 3 and parts[2].startswith('requires:'):
            req_str = parts[2][len('requires:'):]
            requires = [r.strip() for r in req_str.split(',') if r.strip()]
        events.append({"year": year, "month": month, "text": content, "requires": requires})
    # 年・月順にソート（月不明は年内の最後に置く）
    events.sort(key=lambda e: (e["year"], e["month"] if e["month"] is not None else 13))
    return events


def _check_single_condition(cond: str, state: "GameState") -> bool:
    if cond.startswith('warlord_alive:'):
        wid = cond[len('warlord_alive:'):]
        w = state.warlords.get(wid)
        return w is not None and not w.is_defeated
    if cond.startswith('warlord_dead:'):
        wid = cond[len('warlord_dead:'):]
        w = state.warlords.get(wid)
        return w is None or w.is_defeated
    if cond.startswith('relation_hostile:'):
        ids = cond[len('relation_hostile:'):].split(',')
        if len(ids) < 2:
            return True
        w1 = state.warlords.get(ids[0])
        if w1 is None:
            return False
        return w1.relations.get(ids[1], 0) <= -40
    if cond.startswith('koku_gt:'):
        parts = cond[len('koku_gt:'):].split(',')
        if len(parts) < 2:
            return True
        wid, val_str = parts[0], parts[1]
        w = state.warlords.get(wid)
        if w is None:
            return False
        try:
            return w.total_koku(state) > float(val_str)
        except ValueError:
            return True
    return True


def check_requires(requires: list[str], state: "GameState") -> bool:
    """requires条件リストを全て満たす場合True。"""
    return all(_check_single_condition(c, state) for c in requires)


def _chunk_start(current_year: int, current_month: int) -> int:
    """チャンク開始年を返す。チャンクは BASE_YEAR の1月から CHUNK_SIZE 年ごと。"""
    # 年の最初のターン（1月）にチャンクが切り替わるよう year ベースで計算
    offset = (current_year - BASE_YEAR) // CHUNK_SIZE * CHUNK_SIZE
    return BASE_YEAR + offset


def is_chunk_boundary(current_year: int, current_month: int) -> bool:
    """現在のターンがチャンク開始月（チャンク初年の1月）ならTrue。"""
    if current_month != 1:
        return False
    return (current_year - BASE_YEAR) % CHUNK_SIZE == 0


def build_nenpo_context(
    current_year: int,
    current_month: int,
    state: "GameState",
    scenario_id: str = "hizen",
) -> str:
    """現在の3年チャンクのイベントを条件チェックしてプロンプト用テキストを返す。"""
    text = load_nenpo(scenario_id)
    if not text:
        return ""

    all_events = _parse_nenpo(text)
    start = _chunk_start(current_year, current_month)
    end = start + CHUNK_SIZE - 1

    chunk_events = [e for e in all_events if start <= e["year"] <= end]
    if not chunk_events:
        return (
            f"【{start}〜{end}年の史実年表】\n"
            f"（このチャンクに主要な史実イベントはない）\n"
            f"現在は{current_year}年。各勢力は状況に応じて行動せよ。"
        )

    lines = [f"【{start}〜{end}年の史実年表（現チャンク）】"]
    diverged: list[dict] = []

    for ev in chunk_events:
        if check_requires(ev["requires"], state):
            lines.append(f"  {ev['year']}年: {ev['text']}")
        else:
            diverged.append(ev)
            lines.append(f"  {ev['year']}年: ※史実乖離（前提未成立）— 代替展開を選択してよい")

    lines.append(f"\n現在は{current_year}年。上記史実の方向に向かうよう各勢力は行動せよ。")
    if diverged:
        lines.append(
            f"※{len(diverged)}件のイベントで前提条件が変化している。"
            "歴史は分岐しており、各勢力は現状に即した独自の判断を下してよい。"
        )

    return "\n".join(lines)


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
