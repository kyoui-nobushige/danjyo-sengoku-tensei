from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import GameState

# 外交アクションの種類
DIPLOMACY_ACTIONS = {
    "propose_alliance": {"label": "同盟の提案", "base_cost": 0, "relation_req": 0},
    "trade":            {"label": "物資援助",   "base_cost": 0, "relation_req": -30},
    "threaten":         {"label": "脅迫",       "base_cost": 0, "relation_req": -100},
    "apologize":        {"label": "謝罪",       "base_cost": 0, "relation_req": -100},
    "demand_surrender": {"label": "降伏勧告",   "base_cost": 0, "relation_req": -100},
    "small_talk":       {"label": "世間話",     "base_cost": 0, "relation_req": -100},
}


@dataclass
class DiplomacyOutcome:
    action_type: str
    warlord_response: str          # "accept" | "reject" | "counter" | "threaten" | "neutral"
    dialogue: str                  # 武将のセリフ
    thought: str                   # 武将の本音
    relation_delta: int
    narrative: str                 # ゲームログ用


def apply_diplomacy_outcome(
    state: GameState,
    player_id: str,
    target_id: str,
    outcome: DiplomacyOutcome,
) -> None:
    state.change_relation(player_id, target_id, outcome.relation_delta)

    relation_now = state.warlords[player_id].relations.get(target_id, 0)
    wname = state.warlords[target_id].name

    if outcome.warlord_response == "accept" and outcome.action_type == "propose_alliance":
        state.add_log(player_id, f"{wname}との同盟が成立した。（関係値: {relation_now}）")
    elif outcome.warlord_response == "reject":
        state.add_log(player_id, f"{wname}との交渉は不調に終わった。（関係値: {relation_now}）")
    else:
        state.add_log(player_id, f"{wname}と外交を行った。（関係値: {relation_now}）")
