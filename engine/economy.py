"""
経済状態モジュール

塩・商品の生産量と距離別価格を計算し、軍師プロンプトに渡す経済コンテキストを生成する。
"""
from __future__ import annotations
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import GameState

SALT_BASE_PRICE = 20            # 文/升（沿岸産地、1560年相当）
SALT_PRODUCTION_PER_FARM = 500  # 升/月（流下式塩田1基・ゲーム収益換算）
SALT_COST_PER_KM = 1            # 文/升/km（甲府モデル: 80km→100文 から導出）
_BFS_KM_PER_TILE = 20           # km_to_coast 未設定時のタイル→km換算

# 史実：小佐々領の塩田データ（慶長検地前後の記録）
# 雪の浦村分 1町3反3畝10歩半 → 入浜式年産 12.7915石
# 宮村分    8反8畝3歩      → 入浜式年産  9.2036石（460.181俵×0.02石/俵換算）
# 合計      2町2反1畝13.5歩 → 入浜式年産 21.9951石
SALT_FARM_AREA_TEXT = "2町2反1畝13.5歩"       # 塩田の合計面積（雪の浦村＋宮村）
SALT_FARM_IRIHAMA_ANNUAL_KOKU = 21.9951        # 石/年（入浜式・合計）
SALT_FARM_RYUKA_MULTIPLIER = 3.0               # 流下式は入浜式の約3倍効率
# 流下式合計: 65.9853石/年 ≈ 5.499石/月


def _coast_ids(state: GameState) -> set[str]:
    return {tid for tid, t in state.territories.items() if getattr(t, "is_coast", False)}


def _bfs_tile_distance(state: GameState) -> dict[str, int]:
    """km_to_coast 未設定の領地向けBFSタイル距離。"""
    from engine.game_state import ADJACENCY
    coast = _coast_ids(state)
    dist: dict[str, int] = {tid: 0 for tid in coast}
    q = deque(coast)
    while q:
        cur = q.popleft()
        for nb in ADJACENCY.get(cur, []):
            if nb not in dist:
                dist[nb] = dist[cur] + 1
                q.append(nb)
    for tid in state.territories:
        if tid not in dist:
            dist[tid] = 4
    return dist


def km_to_coast_of(territory, bfs_tile_dist: dict[str, int]) -> int:
    """領地の沿岸からのkm距離。JSONの明示値を最優先、なければis_coast→BFS換算。"""
    stored = getattr(territory, "km_to_coast", 0)
    if stored > 0:
        return stored
    if getattr(territory, "is_coast", False):
        return 0
    return bfs_tile_dist.get(territory.id, 4) * _BFS_KM_PER_TILE


def salt_price_at_km(km: int) -> int:
    """距離kmに応じた塩の売価（文/升）。price = base + km × cost_per_km"""
    return SALT_BASE_PRICE + km * SALT_COST_PER_KM


def _player_salt_farms(state: GameState):
    """プレイヤー領で稼働中の流下式塩田がある領地リスト。"""
    return [
        t for t in state.player.territories(state)
        if "salt_farm" in getattr(t, "industries", [])
    ]


def _player_salt_under_construction(state: GameState):
    return [
        t for t in state.player.territories(state)
        if getattr(t, "under_construction", "") == "salt_farm"
    ]


def build_economic_context(state: GameState) -> str:
    """軍師プロンプトに差し込む経済状況ブロックを返す。内容ゼロなら空文字。"""
    from engine.industry import INDUSTRIES

    lines: list[str] = []
    player_terrs = state.player.territories(state)
    bfs = _bfs_tile_distance(state)

    # ── 塩の生産状況 ─────────────────────────────────────
    salt_farms = _player_salt_farms(state)
    salt_wip = _player_salt_under_construction(state)

    if salt_farms or salt_wip:
        lines.append("【塩の生産状況（プレイヤー領）】")
        for t in salt_farms:
            lines.append(f"  {t.name}: 流下式塩田 稼働中 / 月{SALT_PRODUCTION_PER_FARM}升")
        for t in salt_wip:
            rem = getattr(t, "construction_turns_left", 0)
            lines.append(f"  {t.name}: 流下式塩田 建設中（あと{rem}ヶ月）")
        total = len(salt_farms) * SALT_PRODUCTION_PER_FARM
        if total:
            lines.append(f"  月産合計: {total}升")

    # ── km距離別塩相場 ─────────────────────────────────────
    price_rows: list[tuple[str, str, int, int]] = []  # (城名, 勢力名, km, 価格)
    for wid, w in state.warlords.items():
        if w.is_defeated:
            continue
        terrs = w.territories(state)
        if not terrs:
            continue
        best = max(terrs, key=lambda t: getattr(t, "koku", 0))
        km = km_to_coast_of(best, bfs)
        price_rows.append((best.name, w.name, km, salt_price_at_km(km)))

    if price_rows:
        lines.append("【主要城下の塩相場（産地20文＋1文/km）】")
        for tname, wname, km, price in sorted(price_rows, key=lambda x: x[3]):
            lines.append(f"  {tname}（{wname}領）: {price}文/升 ─ 沿岸から約{km}km")

    # ── 産業収入サマリ ─────────────────────────────────────
    ind_lines: list[str] = []
    for t in player_terrs:
        for ind_id in getattr(t, "industries", []):
            ind = INDUSTRIES.get(ind_id)
            if ind and (ind.gold_per_month or ind.food_per_month):
                parts = []
                if ind.gold_per_month:
                    parts.append(f"月{ind.gold_per_month}貫")
                if ind.food_per_month:
                    parts.append(f"月{ind.food_per_month}石")
                ind_lines.append(f"  {t.name} - {ind.name}: {' / '.join(parts)}")

    if ind_lines:
        lines.append("【産業収入（プレイヤー領）】")
        lines.extend(ind_lines)
        total_gold = sum(
            INDUSTRIES[i].gold_per_month
            for t in player_terrs
            for i in getattr(t, "industries", [])
            if i in INDUSTRIES
        )
        lines.append(f"  産業収入合計: 月{total_gold}貫")

    if not lines:
        return ""
    return "【経済状況】\n" + "\n".join(lines)
