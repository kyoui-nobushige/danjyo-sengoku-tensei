from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from engine.game_state import SiegeState

if TYPE_CHECKING:
    from engine.game_state import GameState


# ── 戦術定義 ──────────────────────────────────────────────────────

TACTICS: dict[str, dict] = {
    "frontal": {
        "label": "正面突撃",
        "desc": "兵数が物を言う。安定しているが奇跡は起きない。",
        "atk_mod": 1.0,
    },
    "surprise": {
        "label": "奇襲",
        "desc": "少数でも戦力差を覆せる。察知されると返り討ちになる。",
        "atk_mod": 1.7,
        "fail_atk_mod": 0.4,
        "fail_chance_base": 0.25,
    },
    "ambush": {
        "label": "待ち伏せ",
        "desc": "地の利を活かす。攻撃力は落ちるが損害を抑えられる。",
        "atk_mod": 0.8,
        "def_reduction": 0.7,
    },
    "feint": {
        "label": "陽動",
        "desc": "囮で敵を引き出す。敵が分散すれば本隊が有利になる。",
        "atk_mod": 0.7,
        "enemy_confusion": 0.55,
    },
}


def get_tactic_list() -> list[tuple[str, str, str]]:
    return [(k, v["label"], v["desc"]) for k, v in TACTICS.items()]


# ── 兵種別戦闘力 ──────────────────────────────────────────────────

CAVALRY_MULT = 1.5
GUNNER_MULT  = 2.0

def calc_combat_power(troops: int, cavalry: int, gunners: int) -> float:
    """足軽・騎馬・鉄砲を戦闘力に換算する。"""
    return troops * 1.0 + cavalry * CAVALRY_MULT + gunners * GUNNER_MULT


# ── 本陣護衛兵力 ──────────────────────────────────────────────────

HQ_GUARD_RATIO = 0.06   # 総兵力の6%が本陣護衛

def get_hq_guard_troops(total_troops: int) -> int:
    return max(int(total_troops * HQ_GUARD_RATIO), 300)


# 戦術ごとの本陣発覚率
HQ_DISCOVERY_RATE: dict[str, float] = {
    "surprise": 0.15,   # 奇襲：発覚しにくい
    "feint":    0.30,   # 陽動：囮で注意をそらす
    "frontal":  0.75,   # 正面突撃：ほぼ発覚
    "ambush":   0.50,   # 待ち伏せ：移動中に発見されやすい
}


# ── イベント ──────────────────────────────────────────────────────

@dataclass
class BattleEvent:
    name: str
    description: str
    attacker_mod: float = 1.0
    defender_mod: float = 1.0


def _generate_events(state: GameState, to_id: str, tactic: str) -> list[BattleEvent]:
    events = []
    to_t = state.territories[to_id]
    # 桶狭間：5月・奇襲・今川領 → 急雨
    if (state.month == 5 and
            to_t.owner == "yoshimoto" and
            tactic == "surprise" and
            random.random() < 0.6):
        events.append(BattleEvent(
            name="急雨",
            description="突如として激しい雨が降り始めた！今川の大軍が混乱し指揮系統が乱れた。",
            attacker_mod=1.1,
            defender_mod=0.55,
        ))
    return events


# ── 戦況プレビュー（状態変更なし） ───────────────────────────────

@dataclass
class BattlePreview:
    tactic_label: str
    tactic_note: str
    events: list[BattleEvent]
    ratio: float
    phase_report: str
    attack_goal: str        # "full_army" | "headquarters"
    hq_discovered: bool     # 本陣強襲時：発覚したか
    effective_def_troops: int  # 実際に戦う敵兵数
    # 内部計算値（executeで再利用）
    _atk_mod: float
    _def_mod: float
    _surprise_failed: bool


def preview_combat(
    state: GameState,
    from_id: str,
    to_id: str,
    troops_sent: int,
    tactic: str,
    attack_goal: str = "full_army",
) -> BattlePreview:
    from_t = state.territories[from_id]
    to_t   = state.territories[to_id]
    attacker = state.warlords[from_t.owner]
    defender_military = (30 if to_t.owner == "neutral"
                         else state.warlords[to_t.owner].military)

    tac = TACTICS.get(tactic, TACTICS["frontal"])

    # ── 本陣強襲：発覚判定 ───────────────────────────────────────
    hq_discovered = False
    effective_def_troops = to_t.troops
    if attack_goal == "headquarters" and to_t.owner != "neutral":
        base_disc = HQ_DISCOVERY_RATE.get(tactic, 0.5)
        # 義元の警戒度で発覚率が上下する（alert_level 50が基準）
        alert_mod = (state.warlords[to_t.owner].alert_level - 50) / 100
        disc_rate = max(0.05, min(0.95, base_disc + alert_mod))
        hq_discovered = random.random() < disc_rate
        if not hq_discovered:
            effective_def_troops = get_hq_guard_troops(to_t.troops)
        # 発覚した場合は全軍で迎え撃つ（effective_def_troopsはそのまま全兵力）

    # 奇襲察知判定（全軍交戦時のみ）
    surprise_failed = False
    if tactic == "surprise" and attack_goal == "full_army":
        power_ratio = troops_sent / max(to_t.troops, 1)
        fail_chance = tac["fail_chance_base"] + max(0, 0.3 - power_ratio * 0.1)
        if random.random() < min(fail_chance, 0.5):
            surprise_failed = True

    # 戦術係数
    if tactic == "surprise" and surprise_failed:
        atk_mod   = tac["fail_atk_mod"]
        tactic_note = "【奇襲失敗】察知されていた。"
    elif tactic == "surprise":
        atk_mod   = tac["atk_mod"]
        tactic_note = "【奇襲成功】敵の虚を突いた！"
    elif tactic == "feint":
        atk_mod   = tac["atk_mod"]
        tactic_note = "【陽動展開】囮部隊が動いている。"
    else:
        atk_mod   = tac["atk_mod"]
        tactic_note = ""

    def_mod = 1.0
    if tactic == "ambush":
        def_mod = tac["def_reduction"]
    elif tactic == "feint":
        def_mod = tac["enemy_confusion"]

    # イベント
    events = _generate_events(state, to_id, tactic)
    total_atk_mod = atk_mod
    total_def_mod = def_mod
    for ev in events:
        total_atk_mod *= ev.attacker_mod
        total_def_mod *= ev.defender_mod

    # 戦力比（乱数なしで概算、effective_def_troopsを使用）
    def_cavalry = 0 if to_t.owner == "neutral" else state.warlords[to_t.owner].cavalry
    def_gunners = 0 if to_t.owner == "neutral" else state.warlords[to_t.owner].gunners
    # 本陣強襲・未発覚時は特殊部隊が分散しているため守備側の騎馬・鉄砲を無効化
    if attack_goal == "headquarters" and not hq_discovered:
        def_cavalry = 0
        def_gunners = 0

    atk_eff = calc_combat_power(troops_sent, attacker.cavalry, attacker.gunners)
    def_eff  = calc_combat_power(effective_def_troops, def_cavalry, def_gunners)
    base_atk = atk_eff * (0.5 + attacker.military / 200)
    base_def = def_eff  * (0.5 + defender_military / 200) * to_t.defense_bonus
    base_ratio = base_atk / max(base_def, 1)
    atk_power = base_atk * total_atk_mod
    def_power = base_def * total_def_mod
    ratio = atk_power / max(def_power, 1)

    # フェーズレポート
    lines = []
    if attack_goal == "headquarters":
        if hq_discovered:
            lines.append("【発覚】本陣への接近が露見した。全軍が迎撃に出た。")
        else:
            warlord_name = state.warlords[to_t.owner].name if to_t.owner != "neutral" else "敵"
            lines.append(f"【本陣接近】{warlord_name}の護衛 {effective_def_troops:,} のみが相手。")
    if tactic_note:
        lines.append(tactic_note)
    for ev in events:
        lines.append(f"【{ev.name}】{ev.description}")
    atk_special = (f" [騎{attacker.cavalry:,} 銃{attacker.gunners:,}→戦力{int(atk_eff):,}]"
                   if attacker.cavalry or attacker.gunners else "")
    lines.append(f"\n我が軍 歩{troops_sent:,}{atk_special} vs 迎撃兵力 {effective_def_troops:,}")
    if abs(ratio - base_ratio) > 0.02:
        lines.append(f"戦力比: 素の {base_ratio:.2f} → 戦術補正後 {ratio:.2f}")
    else:
        lines.append(f"戦力比: {ratio:.2f}")
    if ratio >= 1.5:
        lines.append("→ 圧倒的優勢。押し進めば攻略できる。")
    elif ratio >= 1.0:
        lines.append("→ 優勢。損害は出るが突破できる。")
    elif ratio >= 0.7:
        lines.append("→ 劣勢。突入すれば損害が大きい。撤退も選択肢。")
    elif ratio >= 0.4:
        lines.append("→ 大きく劣勢。勝機は薄い。")
    else:
        lines.append("→ 絶望的な劣勢。撤退しないと壊滅する。")

    return BattlePreview(
        tactic_label=tac["label"],
        tactic_note=tactic_note,
        events=events,
        ratio=ratio,
        phase_report="\n".join(lines),
        attack_goal=attack_goal,
        hq_discovered=hq_discovered,
        effective_def_troops=effective_def_troops,
        _atk_mod=total_atk_mod,
        _def_mod=total_def_mod,
        _surprise_failed=surprise_failed,
    )


# ── 戦闘実行（状態変更あり） ──────────────────────────────────────

@dataclass
class CombatResult:
    attacker_id: str
    defender_id: str
    from_territory: str
    to_territory: str
    attacker_troops_sent: int
    attacker_losses: int
    defender_losses: int
    victory: bool
    territory_captured: bool
    siege_started: bool
    tactic: str
    events: list[BattleEvent]
    narrative: str


def execute_combat(
    state: GameState,
    from_id: str,
    to_id: str,
    troops_sent: int,
    preview: BattlePreview,
) -> CombatResult:
    from_t = state.territories[from_id]
    to_t   = state.territories[to_id]
    attacker = state.warlords[from_t.owner]
    defender_military = (30 if to_t.owner == "neutral"
                         else state.warlords[to_t.owner].military)

    def_cavalry = 0 if to_t.owner == "neutral" else state.warlords[to_t.owner].cavalry
    def_gunners = 0 if to_t.owner == "neutral" else state.warlords[to_t.owner].gunners
    if preview.attack_goal == "headquarters" and not preview.hq_discovered:
        def_cavalry = 0
        def_gunners = 0

    atk_power = (calc_combat_power(troops_sent, attacker.cavalry, attacker.gunners)
                 * (0.5 + attacker.military / 200)
                 * preview._atk_mod * random.uniform(0.85, 1.15))
    def_power = (calc_combat_power(preview.effective_def_troops, def_cavalry, def_gunners)
                 * (0.5 + defender_military / 200)
                 * to_t.defense_bonus * preview._def_mod * random.uniform(0.85, 1.15))
    ratio = atk_power / max(def_power, 1)

    # 奇襲失敗は問答無用で大敗
    if preview._surprise_failed:
        victory = False
        atk_loss_rate = random.uniform(0.55, 0.80)
        def_loss_rate = random.uniform(0.02, 0.10)
        narrative = f"奇襲が察知されており、{to_t.name}で待ち伏せられていた。"
    elif ratio >= 1.5:
        victory = True
        atk_loss_rate = random.uniform(0.10, 0.25)
        def_loss_rate = random.uniform(0.60, 0.85)
        narrative = f"圧倒的な勢いで{to_t.name}を制圧した。"
    elif ratio >= 1.0:
        victory = True
        atk_loss_rate = random.uniform(0.25, 0.45)
        def_loss_rate = random.uniform(0.40, 0.60)
        narrative = f"激戦の末、{to_t.name}を攻め落とした。"
    elif ratio >= 0.7:
        victory = False
        atk_loss_rate = random.uniform(0.30, 0.50)
        def_loss_rate = random.uniform(0.15, 0.30)
        narrative = f"{to_t.name}の守備を崩せず退却した。"
    else:
        victory = False
        atk_loss_rate = random.uniform(0.50, 0.75)
        def_loss_rate = random.uniform(0.05, 0.15)
        narrative = f"{to_t.name}で壊滅的な敗北を喫した。"

    atk_losses = int(troops_sent * atk_loss_rate)
    def_losses = int(preview.effective_def_troops * def_loss_rate)

    from_t.troops -= atk_losses
    from_t.troops = max(from_t.troops, 0)
    to_t.troops = max(to_t.troops - def_losses, 0)

    # 騎馬・鉄砲の損害
    attacker.cavalry = max(0, attacker.cavalry - int(attacker.cavalry * atk_loss_rate))
    attacker.gunners = max(0, attacker.gunners - int(attacker.gunners * atk_loss_rate))
    if to_t.owner != "neutral":
        def_w = state.warlords[to_t.owner]
        def_w.cavalry = max(0, def_w.cavalry - int(def_w.cavalry * def_loss_rate))
        def_w.gunners = max(0, def_w.gunners - int(def_w.gunners * def_loss_rate))

    territory_captured = False
    siege_started = False
    old_owner = to_t.owner
    if victory:
        remaining = max(troops_sent - atk_losses, 1)
        from_t.troops = max(from_t.troops - remaining, 0)

        if old_owner == "neutral":
            # 中立地は即占領（城なし）
            territory_captured = True
            to_t.owner = from_t.owner
            to_t.troops = remaining
        else:
            # 敵領地：残兵は城に退いて籠城
            siege_started = True
            if preview.attack_goal == "headquarters" and not preview.hq_discovered:
                narrative = f"{state.warlords[old_owner].name}の本陣を突破した。残兵は城に退いた。包囲を開始する。"
            elif ratio >= 1.5:
                narrative = f"野戦で圧倒し、{to_t.name}の残兵は城に退いた。包囲を開始する。"
            else:
                narrative = f"激戦の末、野戦で勝利。{to_t.name}の残兵は城に籠った。包囲を開始する。"
            state.sieges[to_id] = SiegeState(
                territory_id=to_id,
                from_territory=from_id,
                attacker_id=from_t.owner,
                attacker_troops=remaining,
            )

    return CombatResult(
        attacker_id=from_t.owner,
        defender_id=old_owner,
        from_territory=from_id,
        to_territory=to_id,
        attacker_troops_sent=troops_sent,
        attacker_losses=atk_losses,
        defender_losses=def_losses,
        victory=victory,
        territory_captured=territory_captured,
        siege_started=siege_started,
        tactic=preview.tactic_label,
        events=preview.events,
        narrative=narrative,
    )


# ── 籠城戦 ───────────────────────────────────────────────────────

@dataclass
class SiegeResult:
    action: str              # "assault" | "surround" | "surrender" | "retreat"
    territory_captured: bool
    attacker_losses: int
    defender_losses: int
    narrative: str
    siege_continues: bool


def execute_siege(
    state: GameState,
    siege: SiegeState,
    action: str,
) -> SiegeResult:
    to_t   = state.territories[siege.territory_id]
    from_t = state.territories[siege.from_territory]

    if action == "assault":
        fortress_mult = 1.5 + to_t.fortification * 0.25
        ratio = siege.attacker_troops / max(to_t.troops * fortress_mult, 1)
        atk_loss_rate = random.uniform(0.25, 0.50)

        if ratio >= 2.0:
            success = random.random() < 0.90
            def_loss_rate = random.uniform(0.70, 0.90)
            narrative = f"{to_t.name}の城門を突破した。城内に突入する！" if success else "城壁を越えられず、多大な損害を被った。"
        elif ratio >= 1.2:
            success = random.random() < 0.60
            def_loss_rate = random.uniform(0.45, 0.70) if success else random.uniform(0.15, 0.35)
            narrative = "激しい攻城戦の末、城が陥落した。" if success else "城壁を越えられず退却した。"
        elif ratio >= 0.7:
            success = random.random() < 0.25
            def_loss_rate = random.uniform(0.20, 0.40) if success else random.uniform(0.05, 0.20)
            narrative = "薄氷を踏む攻城戦で城を落とした。" if success else "攻城に失敗。損害が大きい。"
        else:
            success = random.random() < 0.08
            def_loss_rate = random.uniform(0.10, 0.25) if success else random.uniform(0.02, 0.10)
            narrative = "奇跡的に城が陥落した。" if success else f"{to_t.name}の城壁は厚く、壊滅的な損害を受けた。"

        atk_losses = int(siege.attacker_troops * atk_loss_rate)
        def_losses = int(to_t.troops * def_loss_rate)
        siege.attacker_troops = max(siege.attacker_troops - atk_losses, 0)
        to_t.troops = max(to_t.troops - def_losses, 0)

        if success or to_t.troops == 0:
            _capture_from_siege(state, siege)
            return SiegeResult(action="assault", territory_captured=True,
                               attacker_losses=atk_losses, defender_losses=def_losses,
                               narrative=narrative, siege_continues=False)
        if siege.attacker_troops <= 100:
            _abandon_siege(state, siege)
            return SiegeResult(action="assault", territory_captured=False,
                               attacker_losses=atk_losses, defender_losses=def_losses,
                               narrative=narrative + "\n包囲軍は壊滅し撤退した。", siege_continues=False)
        return SiegeResult(action="assault", territory_captured=False,
                           attacker_losses=atk_losses, defender_losses=def_losses,
                           narrative=narrative, siege_continues=True)

    elif action == "surround":
        atk_attrition = int(siege.attacker_troops * random.uniform(0.01, 0.03))
        def_starvation = int(to_t.troops * random.uniform(0.05, 0.10))
        siege.attacker_troops = max(siege.attacker_troops - atk_attrition, 0)
        to_t.troops = max(to_t.troops - def_starvation, 0)
        siege.duration += 1

        if to_t.troops == 0:
            _capture_from_siege(state, siege)
            return SiegeResult(action="surround", territory_captured=True,
                               attacker_losses=atk_attrition, defender_losses=def_starvation,
                               narrative=f"兵糧が尽き、{to_t.name}が開城した。",
                               siege_continues=False)
        return SiegeResult(action="surround", territory_captured=False,
                           attacker_losses=atk_attrition, defender_losses=def_starvation,
                           narrative=f"包囲{siege.duration}ヶ月目。城内の兵糧が尽きつつある（守備兵残{to_t.troops:,}）。",
                           siege_continues=True)

    elif action == "surrender":
        defender_w = state.warlords.get(to_t.owner)
        rate = 0.20
        if siege.attacker_troops > to_t.troops * 3:
            rate += 0.25
        rate += siege.duration * 0.08
        if defender_w and defender_w.prestige > 70:
            rate -= 0.15
        if defender_w and len(defender_w.territories(state)) <= 1:
            rate += 0.20
        rate = max(0.05, min(rate, 0.85))

        if random.random() < rate:
            _capture_from_siege(state, siege)
            return SiegeResult(action="surrender", territory_captured=True,
                               attacker_losses=0, defender_losses=0,
                               narrative=f"{to_t.name}が降伏を受け入れた。",
                               siege_continues=False)
        return SiegeResult(action="surrender", territory_captured=False,
                           attacker_losses=0, defender_losses=0,
                           narrative=f"降伏勧告を拒否された（受諾率{rate:.0%}）。包囲を続ける。",
                           siege_continues=True)

    else:  # retreat
        losses = int(siege.attacker_troops * random.uniform(0.05, 0.15))
        siege.attacker_troops = max(siege.attacker_troops - losses, 0)
        _abandon_siege(state, siege)
        return SiegeResult(action="retreat", territory_captured=False,
                           attacker_losses=losses, defender_losses=0,
                           narrative=f"{to_t.name}の包囲を解いて撤退した。",
                           siege_continues=False)


def _capture_from_siege(state: GameState, siege: SiegeState) -> None:
    to_t = state.territories[siege.territory_id]
    old_owner = to_t.owner
    to_t.owner = siege.attacker_id
    to_t.troops = max(siege.attacker_troops, 1)
    if old_owner != "neutral":
        state.change_relation(siege.attacker_id, old_owner, -20)
    _check_warlord_defeat(state, old_owner)
    state.sieges.pop(siege.territory_id, None)


def _abandon_siege(state: GameState, siege: SiegeState) -> None:
    from_t = state.territories[siege.from_territory]
    from_t.troops += siege.attacker_troops
    state.sieges.pop(siege.territory_id, None)


def retreat_combat(state: GameState, from_id: str, troops_sent: int) -> int:
    """撤退時の損害を計算して適用。損害数を返す。"""
    losses = int(troops_sent * random.uniform(0.10, 0.20))
    state.territories[from_id].troops -= losses
    state.territories[from_id].troops = max(state.territories[from_id].troops, 0)
    return losses


def _check_warlord_defeat(state: GameState, warlord_id: str) -> None:
    if warlord_id == "neutral":
        return
    w = state.warlords.get(warlord_id)
    if w is None:
        return
    if not [t for t in state.territories.values() if t.owner == warlord_id]:
        w.is_defeated = True
        state.add_log("system", f"【滅亡】{w.name}は全領地を失い滅亡した。")
