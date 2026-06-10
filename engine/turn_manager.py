"""
AIターン処理

AI武将の行動判断はバッチLLM（1ターン=1回呼び出し）で決定する。
LLM失敗時はルールベースにフォールバックする。
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import random

from engine.combat import preview_combat, execute_combat, execute_siege
from engine.diplomacy import apply_diplomacy_outcome, DiplomacyOutcome

if TYPE_CHECKING:
    from engine.game_state import GameState
    from llm.base import BaseLLM


def run_ai_turns(state: "GameState", llm: "BaseLLM | None" = None) -> list[str]:
    """全AI武将のターンを処理し、ログ文字列リストを返す。
    LLMが渡されていればバッチ1回呼び出し、なければルールベース。
    """
    messages = []

    # 継続中のAI籠城戦を処理
    for tid in list(state.sieges):
        siege = state.sieges.get(tid)
        if siege and siege.attacker_id != state.player_id:
            msg = _ai_resolve_siege(state, siege)
            if msg:
                state.add_log(siege.attacker_id, msg)
                wname = state.warlords[siege.attacker_id].name
                messages.append(f"【{wname}】{msg}")

    ai_warlords = state.ai_warlords()

    # バッチLLMで全武将の行動を1回で取得
    llm_actions: dict = {}
    if llm is not None:
        try:
            from llm.warlord import get_all_ai_actions_batch
            llm_actions = get_all_ai_actions_batch(llm, state, ai_warlords)
        except Exception:
            llm_actions = {}

    for warlord in ai_warlords:
        warlord.alert_level = _calc_alert_level(state, warlord.id)

        llm_act = llm_actions.get(warlord.id)
        if llm_act:
            action_type = llm_act.action_type
            target_id   = llm_act.target_id
            narration   = llm_act.narration
            rel_delta   = llm_act.relation_delta
        else:
            # LLMが行動を返さなかった武将はルールベース
            action_type, target_id, narration, rel_delta = _decide_action(state, warlord.id)

        result_msg = _execute_action(state, warlord.id, action_type, target_id, narration, rel_delta)
        if result_msg:
            state.add_log(warlord.id, result_msg)
            messages.append(f"【{warlord.name}】{result_msg}")
    return messages


# ── ルールベース行動決定 ───────────────────────────────────────────

def _calc_alert_level(state: "GameState", warlord_id: str) -> int:
    """隣接敵の脅威度から警戒度（0-100）を計算する。"""
    threat = 0
    for t in state.territories.values():
        if t.owner != warlord_id:
            continue
        for adj_id in state.adjacent_territories(t.id):
            adj = state.territories[adj_id]
            if adj.owner not in ("neutral", warlord_id):
                threat += min(40, adj.troops // 150)
    return min(100, threat)


def _decide_action(
    state: "GameState", warlord_id: str
) -> tuple[str, str, str, int]:
    """行動を (action_type, target_id, narration, relation_delta) で返す。"""
    warlord = state.warlords[warlord_id]
    owned = [t for t in state.territories.values() if t.owner == warlord_id]
    if not owned:
        return "wait", "", f"{warlord.name}は様子を見ている。", 0

    total_troops = sum(t.troops for t in owned)

    # 従属関係（忠誠度が残っている場合のみ攻撃禁止。造反（0以下）なら臨戦）
    my_vassals = {
        w.id for w in state.warlords.values()
        if w.liege == warlord_id and not w.is_defeated and w.loyalty_to_liege > 0
    }
    liege_protected = (
        {warlord.liege}
        if warlord.liege and state.warlords.get(warlord.liege) and warlord.loyalty_to_liege > 0
        else set()
    )
    protected_owners = my_vassals | liege_protected

    # 攻撃候補（宗主国・従属国・友好相手を除外）
    attack_candidates: list[tuple] = []
    for ot in owned:
        for adj_id in state.adjacent_territories(ot.id):
            adj = state.territories[adj_id]
            if adj.owner == warlord_id or adj.owner in protected_owners:
                continue
            rel = warlord.relations.get(adj.owner, 0)
            if rel >= 0:
                continue  # 友好・中立は攻撃しない
            attack_candidates.append((ot, adj))

    # ── 攻撃（兵力300超・隣接敵あり・40%確率・兵力比1.2倍以上） ──
    viable = [(f, t) for f, t in attack_candidates if total_troops >= t.troops * 1.2]
    if viable and total_troops > 300 and random.random() < 0.40:
        from_t, to_t = min(viable, key=lambda x: x[1].troops)
        return "attack", to_t.id, "", 0

    # ── 外交（20%確率） ──────────────────────────────────────────
    if random.random() < 0.20:
        others = [
            w for w in state.warlords.values()
            if w.id != warlord_id and not w.is_defeated
            and w.warlord_type in ("daimyo", "vassal")
        ]
        if others:
            target = random.choice(others)
            delta = random.randint(3, 8)
            return "diplomacy", target.id, f"{warlord.name}が{target.name}に使者を送った。", delta

    # ── 内政（残り） ────────────────────────────────────────────
    target_t = max(owned, key=lambda t: t.koku)
    return "develop", target_t.id, "", 0


def _execute_action(
    state: "GameState",
    warlord_id: str,
    action_type: str,
    target_id: str,
    narration: str,
    rel_delta: int,
) -> str:
    warlord = state.warlords[warlord_id]

    if action_type == "attack":
        return _ai_attack(state, warlord_id, target_id)

    elif action_type == "diplomacy":
        if target_id and target_id in state.warlords and not state.warlords[target_id].is_defeated:
            # プレイヤー宛の使者は即時適用せず、評定で応答を求める
            if target_id == state.player_id:
                state.pending_diplomacy.append({
                    "from_id": warlord_id,
                    "from_name": warlord.name,
                    "relation_delta": rel_delta,
                    "narration": narration or f"{warlord.name}から使者が参りました。",
                })
                return f"{warlord.name}から使者が参りました。"
            state.change_relation(warlord_id, target_id, rel_delta)
            if warlord.liege:
                decay = state.vassal_loyalty_decay(warlord_id, target_id)
                if decay > 0:
                    return f"{narration}（忠誠度-{decay}：宗主国の敵と接触）"
            return narration
        return ""

    elif action_type == "develop":
        return _ai_develop(state, warlord_id, target_id)

    else:
        return ""  # wait は表示しない


# ── 攻撃・籠城・内政の実行 ────────────────────────────────────────

def _ai_attack(state: "GameState", warlord_id: str, target_id: str) -> str:
    warlord = state.warlords[warlord_id]

    owned_territories = [t for t in state.territories.values() if t.owner == warlord_id]
    if not owned_territories:
        return ""

    attack_candidates = []
    for ot in owned_territories:
        for adj_id in state.adjacent_territories(ot.id):
            adj_t = state.territories[adj_id]
            if adj_t.owner != warlord_id:
                attack_candidates.append((ot, adj_t))

    if not attack_candidates:
        return ""

    chosen_from, chosen_to = None, None
    for (from_t, to_t) in attack_candidates:
        if to_t.id == target_id:
            chosen_from, chosen_to = from_t, to_t
            break
    if chosen_from is None:
        # LLMが無効な target_id を返した場合、プレイヤー領地を避けて選ぶ
        non_player = [(f, t) for f, t in attack_candidates if t.owner != state.player_id]
        if non_player:
            chosen_from, chosen_to = min(non_player, key=lambda x: x[1].troops)
        else:
            return ""  # プレイヤー領地しかない場合は行動しない

    if chosen_from.troops <= 100:
        return ""

    troops_sent = int(chosen_from.troops * random.uniform(0.4, 0.7))
    tactic = random.choice(["frontal", "surprise", "frontal"])
    preview = preview_combat(state, chosen_from.id, chosen_to.id, troops_sent, tactic)
    result = execute_combat(state, chosen_from.id, chosen_to.id, troops_sent, preview)

    if result.territory_captured:
        return f"{warlord.name}が{chosen_to.name}を攻略した！（派遣:{troops_sent} 損害:{result.attacker_losses}）"
    elif result.siege_started:
        siege = state.sieges.get(chosen_to.id)
        if siege:
            msg = _ai_resolve_siege(state, siege)
            if msg:
                return msg
        return f"{warlord.name}が{chosen_to.name}を包囲した。"
    else:
        return f"{warlord.name}が{chosen_to.name}へ攻撃したが撃退された。（損害:{result.attacker_losses}）"


def _ai_resolve_siege(state: "GameState", siege) -> str:
    to_t = state.territories[siege.territory_id]
    warlord = state.warlords.get(siege.attacker_id)
    if not warlord:
        return ""
    fortress_mult = 1.5 + to_t.fortification * 0.25
    ratio = siege.attacker_troops / max(to_t.troops * fortress_mult, 1)
    action = "assault" if ratio >= 1.5 else "surround"
    result = execute_siege(state, siege, action)
    action_label = "強攻" if action == "assault" else "包囲"
    if result.territory_captured:
        return f"{warlord.name}が{to_t.name}を攻略した！（{action_label}）"
    elif result.siege_continues:
        return f"{warlord.name}が{to_t.name}を包囲中。（{action_label}・{siege.duration}ヶ月目）"
    else:
        return f"{warlord.name}の{to_t.name}包囲は失敗に終わった。"


def _ai_develop(state: "GameState", warlord_id: str, target_id: str) -> str:
    warlord = state.warlords[warlord_id]
    owned = [t for t in state.territories.values() if t.owner == warlord_id]
    if not owned:
        return ""

    target_t = state.territories.get(target_id)
    if target_t is None or target_t.owner != warlord_id:
        target_t = owned[0]

    max_troops = target_t.koku * 250
    target_t.troops = min(int(target_t.troops * 1.1), max_troops)
    return ""  # 内政は静かに処理（毎回表示しない）
