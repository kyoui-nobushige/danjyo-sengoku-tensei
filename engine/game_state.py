from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import json
import copy


POPULATION_PER_MANOKU = 7000  # 鬼頭宏推計(1600年肥前253200人÷30.99万石)×1560年補正


@dataclass
class ExternalPower:
    """シナリオ外勢力（外交対象だがマップに登場しない）"""
    id: str
    name: str
    faction: str
    relation: int = 0   # プレイヤーとの関係値
    note: str = ""


@dataclass
class Territory:
    id: str
    name: str
    owner: str          # warlord_id or "neutral"
    troops: int
    koku: float         # 石高(万石)
    fortification: int  # 0-5: 防御力
    population: int = 0      # 人口（0=自動計算）
    loyalty: int = 70        # 民忠誠度 0-100
    training: int = 50       # 練度 0-100
    morale: int = 70         # 士気 0-100
    port_tier: int = 0       # 港格 0=なし 1=沿岸 2=外洋 3=南蛮港
    commerce: int = 0        # 商業レベル 0-10（投資で上昇・金収入に直結）
    is_coast: bool = False   # 沿岸領地フラグ（塩田など前提）
    km_to_coast: int = 0    # 最寄り沿岸からの距離（km）。塩価格計算に使用。
    industries: list = field(default_factory=list)          # 建設済み産業IDリスト
    under_construction: str = ""  # 建設中の産業ID（空文字=なし）
    construction_turns_left: int = 0  # 残り建設ターン数

    def __post_init__(self):
        if self.population == 0 and self.koku > 0:
            self.population = int(self.koku * POPULATION_PER_MANOKU)

    @property
    def max_troops(self) -> int:
        """人口の30%を農兵動員の上限とする（傭兵はこの上限を超えられる）"""
        return max(int(self.population * 0.3), 1)

    @property
    def defense_bonus(self) -> float:
        return 1.0 + self.fortification * 0.1


@dataclass
class Warlord:
    id: str
    name: str
    faction_name: str
    is_player: bool
    intelligence: int   # 0-100: 謀略・外交
    military: int       # 0-100: 戦闘
    charisma: int       # 0-100: 家臣統率・外交
    prestige: int       # 0-100: 威信(外交に影響)
    relations: dict[str, int] = field(default_factory=dict)
    bond_types: dict[str, str] = field(default_factory=dict)  # 血縁・役職など固定ラベル
    is_defeated: bool = False
    alert_level: int = 50   # 0-100: 警戒度（高いほど発覚しやすい）
    warlord_type: str = "daimyo"  # "daimyo" | "vassal" | "clan"
    liege: str = ""  # 従属国の場合の宗主国ID
    loyalty_to_liege: int = 100  # 宗主国への忠誠度 0-100（0で造反・討伐対象）
    treasury: int = 0   # 金庫（貫文）港・交易収入
    food: int = 0       # 兵糧備蓄（石）石高収入
    cavalry: int = 0    # 騎馬兵数
    gunners: int = 0    # 鉄砲兵数
    salt_stock: float = 0.0  # 塩備蓄（石）流下式塩田の産出物・交易コマンドで売却
    start_hint: str = ""  # 転生者ヒント（シナリオJSONから。空なら非表示）

    def relation_label(self, target_id: str) -> str:
        if target_id in self.bond_types:
            return self.bond_types[target_id]
        v = self.relations.get(target_id, 0)
        if v <= -70: return "交戦中"
        if v <= -40: return "敵対"
        if v <= -10: return "警戒"
        if v <= 20:  return "中立"
        if v <= 50:  return "友好"
        if v <= 80:  return "同盟"
        return "盟友"

    def territories(self, state: GameState) -> list[Territory]:
        return [t for t in state.territories.values() if t.owner == self.id]

    def total_troops(self, state: GameState) -> int:
        return sum(t.troops for t in self.territories(state))

    def total_koku(self, state: GameState) -> int:
        return sum(t.koku for t in self.territories(state))


@dataclass
class LogEntry:
    turn: int
    year: int
    month: int
    actor: str
    text: str


@dataclass
class SiegeState:
    territory_id: str    # 籠城中の領地
    from_territory: str  # 包囲軍の出発地
    attacker_id: str     # 包囲側武将ID
    attacker_troops: int # 包囲軍兵力
    duration: int = 0    # 経過ターン数


@dataclass
class GameState:
    year: int
    month: int
    turn: int
    player_id: str
    warlords: dict[str, Warlord]
    territories: dict[str, Territory]
    log: list[LogEntry] = field(default_factory=list)
    player_action_history: list[str] = field(default_factory=list)
    sieges: dict[str, SiegeState] = field(default_factory=dict)  # key: territory_id
    events: list[dict] = field(default_factory=list)
    external_powers: dict[str, ExternalPower] = field(default_factory=dict)
    pending_diplomacy: list[dict] = field(default_factory=list)  # AIからプレイヤーへの未応答使者
    win_condition: dict = field(default_factory=dict)
    win_message: str = ""
    lose_message: str = ""

    def record_player_action(self, action: str) -> None:
        self.player_action_history.append(f"T{self.turn}: {action}")
        if len(self.player_action_history) > 5:
            self.player_action_history.pop(0)

    # ── ヘルパー ─────────────────────────────────────────────────

    @property
    def player(self) -> Warlord:
        return self.warlords[self.player_id]

    def ai_warlords(self) -> list[Warlord]:
        return [w for w in self.warlords.values()
                if not w.is_player and not w.is_defeated
                and w.warlord_type in ("daimyo", "vassal")]

    def get_warlord_by_territory(self, territory_id: str) -> Optional[Warlord]:
        t = self.territories[territory_id]
        if t.owner == "neutral":
            return None
        return self.warlords.get(t.owner)

    def adjacent_territories(self, territory_id: str) -> list[str]:
        return [tid for tid in ADJACENCY.get(territory_id, []) if tid in self.territories]

    def can_attack(self, from_id: str, to_id: str) -> bool:
        return to_id in self.adjacent_territories(from_id)

    def change_relation(self, wid_a: str, wid_b: str, delta: int) -> None:
        wa = self.warlords[wid_a]
        wb = self.warlords[wid_b]
        wa.relations[wid_b] = max(-100, min(100, wa.relations.get(wid_b, 0) + delta))
        wb.relations[wid_a] = max(-100, min(100, wb.relations.get(wid_a, 0) + delta))

    def add_log(self, actor: str, text: str) -> None:
        self.log.append(LogEntry(self.turn, self.year, self.month, actor, text))

    def advance_turn(self) -> None:
        self.turn += 1
        self.month += 1
        if self.month > 12:
            self.month = 1
            self.year += 1

        # 兵力自然回復（包囲中は補充なし）
        for t in self.territories.values():
            if t.owner != "neutral" and t.id not in self.sieges:
                replenishment = max(int(t.koku * 32), 10)
                t.troops = min(t.troops + replenishment, t.max_troops)

        # 産業建設進捗
        completed_msgs = []
        for t in self.territories.values():
            if t.under_construction and t.owner == self.player_id:
                t.construction_turns_left -= 1
                if t.construction_turns_left <= 0:
                    from engine.industry import INDUSTRIES
                    ind = INDUSTRIES.get(t.under_construction)
                    if ind and t.under_construction not in t.industries:
                        t.industries.append(t.under_construction)
                        # 正条植えは石高に直接反映
                        if t.under_construction == "rice_grid":
                            t.koku = round(t.koku * 1.2, 5)
                    completed_msgs.append(
                        f"【産業完成】{t.name}に「{ind.name if ind else t.under_construction}」が完成した。"
                    )
                    t.under_construction = ""
                    t.construction_turns_left = 0
        if completed_msgs:
            for msg in completed_msgs:
                self.add_log("system", msg)

        # 塩の月産（流下式塩田）
        from engine.economy import SALT_FARM_IRIHAMA_ANNUAL_KOKU, SALT_FARM_RYUKA_MULTIPLIER
        salt_monthly = SALT_FARM_IRIHAMA_ANNUAL_KOKU * SALT_FARM_RYUKA_MULTIPLIER / 12
        for t in self.territories.values():
            if "salt_farm" in getattr(t, "industries", []) and t.owner in self.warlords:
                w = self.warlords[t.owner]
                if not w.is_defeated:
                    w.salt_stock += salt_monthly

        # 収入計算（月次）
        for wid, w in self.warlords.items():
            if w.is_defeated:
                continue
            inc = self._calc_income(wid)
            new_food = max(0, w.food + inc["food_net"])
            max_food = int(sum(
                t.koku for t in self.territories.values() if t.owner == wid
            ) * 400 * 12)
            w.food = min(new_food, max(max_food, 1))
            w.treasury += inc["gold"]

    def _calc_income(self, warlord_id: str) -> dict:
        """武将の月次収入を項目別に計算して返す。"""
        food_income = 0
        gold_income = 0
        for t in self.territories.values():
            if t.owner != warlord_id:
                continue
            loyalty_rate = t.loyalty / 100
            # 兵糧: 1万石→400石/月（忠誠度係数）
            food_income += int(t.koku * 400 * loyalty_rate)
            # 商業収入: 商業レベル×5貫/月（忠誠度係数）
            gold_income += int(t.commerce * 5 * loyalty_rate)
            # 帆別銭: 港格に応じた固定収入（貫文/月）
            PORT_INCOME = {1: 10, 2: 30, 3: 80}
            gold_income += PORT_INCOME.get(t.port_tier, 0)
            # 産業収入（転生者技術）
            from engine.industry import industry_income_summary
            ind_inc = industry_income_summary(t)
            gold_income += ind_inc["gold"]
            food_income += ind_inc["food"]
        # 消費: 平時は兵力×0.5石/月（出陣・籠城時は別途）
        food_consumption = int(sum(
            t.troops for t in self.territories.values() if t.owner == warlord_id
        ) * 0.5)
        return {
            "food_income": food_income,
            "food_consumption": food_consumption,
            "food_net": food_income - food_consumption,
            "gold": gold_income,
        }

    def process_events(self) -> list[str]:
        """現在の年月に一致するイベントを処理し、表示メッセージのリストを返す。"""
        messages = []
        remaining = []
        for ev in self.events:
            if ev["year"] == self.year and ev["month"] == self.month:
                if ev["type"] == "rename_territory":
                    t = self.territories.get(ev["id"])
                    if t:
                        old_name = t.name
                        t.name = ev["new_name"]
                        messages.append(f"{old_name}が{t.name}と改名された。")
                elif ev["type"] == "upgrade_port_conditional":
                    cond = ev.get("conditions", {})
                    passed = True
                    if "territory_owner" in cond:
                        c = cond["territory_owner"]
                        t_check = self.territories.get(c["id"])
                        if not t_check or t_check.owner != c["owner"]:
                            passed = False
                    if "external_relation" in cond:
                        c = cond["external_relation"]
                        ep = self.external_powers.get(c["id"])
                        if not ep or ep.relation < c["min"]:
                            passed = False
                    branch = ev["if_true"] if passed else ev.get("if_false")
                    if branch:
                        t_target = self.territories.get(branch["id"])
                        if t_target and "port_tier" in branch:
                            t_target.port_tier = branch["port_tier"]
                            msg_key = "if_true_message" if passed else "if_false_message"
                            msg = ev.get(msg_key, f"{t_target.name}の港格が変化した。")
                            messages.append(msg)
                elif ev["type"] == "npc_war":
                    skip_list = ev.get("skip_if_neutralized", [])
                    if not any(self._is_target_neutralized(wid) for wid in skip_list):
                        for change in ev.get("result", []):
                            ctype = change.get("type")
                            if ctype == "transfer_territory":
                                for tid in change.get("territories", []):
                                    t = self.territories.get(tid)
                                    if t and t.owner == change.get("from"):
                                        t.owner = change["to"]
                            elif ctype == "make_vassal":
                                vassal_w = self.warlords.get(change.get("vassal"))
                                if vassal_w and not vassal_w.is_defeated:
                                    vassal_w.liege = change.get("lord")
                            elif ctype == "defeat":
                                d_w = self.warlords.get(change.get("warlord"))
                                if d_w:
                                    d_w.is_defeated = True
                                    for tid, t in self.territories.items():
                                        if t.owner == change.get("warlord"):
                                            t.owner = change.get("to", ev.get("attacker", "neutral"))
                        msg = ev.get("message", "")
                        if msg:
                            messages.append(msg)
                elif ev["type"] == "narration":
                    skip_list = ev.get("skip_if_neutralized", [])
                    if not any(self._is_target_neutralized(wid) for wid in skip_list):
                        msg = ev.get("message", "")
                        if msg:
                            messages.append(msg)
            else:
                remaining.append(ev)
        self.events = remaining
        return messages

    def vassal_loyalty_decay(self, vassal_id: str, enemy_of_liege_id: str) -> int:
        """従属が宗主の敵に使者を送った際の忠誠度減少量を返し、適用する。
        弱い従属ほど減少幅が小さい（寝返りを誘発しにくいため宗主も黙認しがち）。"""
        w = self.warlords.get(vassal_id)
        if not w or not w.liege:
            return 0
        liege = self.warlords.get(w.liege)
        if not liege:
            return 0
        # 宗主の敵かどうか判定（関係値 <= -40）
        liege_rel = liege.relations.get(enemy_of_liege_id, 0)
        if liege_rel > -40:
            return 0
        vassal_koku = w.total_koku(self)
        liege_koku = liege.total_koku(self)
        # 弱いほど減少小（min=2, max=20）
        ratio = vassal_koku / max(liege_koku, 0.1)
        delta = max(2, min(20, int(20 * ratio)))
        w.loyalty_to_liege = max(0, w.loyalty_to_liege - delta)
        return delta

    def _is_target_neutralized(self, wid: str) -> bool:
        """対象が滅亡済みまたはプレイヤーの従属下にある場合True。"""
        w = self.warlords.get(wid)
        if w is None or w.is_defeated:
            return True
        if w.liege == self.player_id:
            return True
        player_vassals = {ow.id for ow in self.warlords.values() if ow.liege == self.player_id}
        return w.liege in player_vassals

    def warlord_rank(self, wid: str) -> str:
        """石高と従属勢力数から大名ランクを返す。"""
        w = self.warlords.get(wid)
        if w is None or w.is_defeated:
            return ""
        koku = w.total_koku(self)
        subordinates = sum(
            1 for ow in self.warlords.values()
            if ow.liege == wid and not ow.is_defeated and ow.warlord_type == "vassal"
        )
        if koku < 1.0:
            return "国人"
        if subordinates >= 1:
            return "大名"
        return "小大名"

    def is_game_over(self) -> tuple[bool, str]:
        player_territories = [t for t in self.territories.values() if t.owner == self.player_id]
        if not player_territories or self.player.is_defeated:
            return True, "defeat"

        if self.win_condition:
            ctype = self.win_condition.get("type")
            if ctype == "defeat_or_subjugate_all":
                targets = self.win_condition.get("targets", [])
                if targets and all(self._is_target_neutralized(tid) for tid in targets):
                    return True, "victory"
        else:
            if not self.ai_warlords():
                return True, "victory"

        return False, ""

    def to_context_summary(self) -> str:
        """LLMへ渡すゲーム状況サマリ"""
        lines = [f"【現在の状況: {self.year}年{self.month}月】"]
        for wid, w in self.warlords.items():
            if w.is_defeated:
                continue
            terrs = w.territories(self)
            troops = w.total_troops(self)
            koku = w.total_koku(self)
            if w.is_player:
                label = "（プレイヤー）"
            elif w.warlord_type == "clan":
                label = "（一門）"
            else:
                label = ""
            lines.append(f"  {w.name}{label}: {[t.name for t in terrs]} 兵力{troops} 石高{koku}万石")
        lines.append("【関係値】")
        for wid, w in self.warlords.items():
            for oid, val in w.relations.items():
                if wid < oid:  # 重複防止
                    ow = self.warlords[oid]
                    lines.append(f"  {w.name}↔{ow.name}: {val}（{w.relation_label(oid)}）")
        return "\n".join(lines)


# ── 隣接マップ ────────────────────────────────────────────────────
ADJACENCY: dict[str, list[str]] = {
    # 桶狭間シナリオ（尾張・東海）
    "owari":   ["mino", "mikawa", "ise"],
    "mino":    ["owari", "omi", "ise"],
    "mikawa":  ["owari", "totomi"],
    "totomi":  ["mikawa", "suruga", "ise"],
    "suruga":  ["totomi", "ise"],
    "ise":     ["owari", "mino", "totomi", "suruga"],
    # 九州三国志シナリオ（肥前）
    # ── 佐嘉平野（佐賀市・神埼市・小城市・蓮池・鳥栖） ──
    "saga":        ["seifukuji", "hasuike", "chiba", "mitsuse"],
    "seifukuji":   ["saga", "katsuo", "mitsuse", "chiba", "hasuike"],
    "katsuo":      ["seifukuji"],
    "hasuike":     ["saga", "ariojo", "seifukuji"],
    "chiba":       ["saga", "hasuike", "kajimine", "seifukuji", "mitsuse"],
    "mitsuse":     ["saga", "kajimine", "seifukuji", "chiba"],
    # ── 内陸（多久・武雄） ──
    "kajimine":    ["chiba", "mitsuse", "tsukazaki", "kishidake"],
    "tsukazaki":       ["kajimine", "imarijo", "iimorijo", "matsutake", "ariojo"],
    # ── 島原半島（有馬直轄） ──
    "hinoe":       ["isahaya", "fukaejo", "kuchinotu"],
    "koujirojo":   ["fukaejo", "takezakijo", "isahaya"],
    "fukaejo":     ["hinoe", "koujirojo", "kuchinotu"],
    "kuchinotu":   ["hinoe", "fukaejo"],
    "takezakijo":  ["koujirojo", "ariojo", "isahaya"],
    # ── 藤津郡ハブ（鹿島・太良・東彼杵） ──
    "ariojo":     ["hasuike", "takezakijo", "matsutake", "tsukazaki"],
    "matsutake":   ["omurajo", "iimorijo", "tsukazaki", "ariojo", "hariojo"],
    # ── 大村湾岸 ──
    "omurajo":     ["isahaya", "matsutake", "tsunomijo", "yokose"],
    "yokose":      ["omurajo"],
    "hariojo":     ["kosazajo", "tsunomijo", "iimorijo", "matsutake"],
    "tsunomijo": ["isahaya", "omurajo", "hariojo", "tawaraishi"],
    # ── 諫早・深堀 ──
    "isahaya":     ["hinoe", "omurajo", "tsunomijo", "koujirojo", "takezakijo", "tawaraishi"],
    "tawaraishi":      ["isahaya", "tsunomijo", "kosazajo"],
    # ── 西彼杵半島 ──
    "kosazajo":    ["katsuodake", "hariojo", "tawaraishi", "inakajo", "hongojo"],
    "inakajo":     ["kosazajo", "enoshimajo", "katsuodake", "egawa", "aokatajo"],
    "enoshimajo":  ["inakajo", "hongojo", "katsuodake"],
    "hongojo":     ["enoshimajo", "katsuodake", "kosazajo"],
    # ── 松浦・上松浦 ──
    "katsuodake":  ["kosazajo", "imarijo", "naoya", "iimorijo", "hongojo", "inakajo", "enoshimajo"],
    "kishidake":   ["imarijo", "onigajo", "hidakajo", "kajimine"],
    "hidakajo":    ["kishidake", "onigajo"],
    "iimorijo":    ["katsuodake", "naoya", "imarijo", "tsukazaki", "matsutake", "hariojo"],
    "naoya":     ["katsuodake", "imarijo", "iimorijo"],
    "imarijo":    ["katsuodake", "kishidake", "tsukazaki", "naoya", "onigajo", "iimorijo"],
    "onigajo":     ["kishidake", "imarijo", "hidakajo"],
    # ── 五島列島 ──
    "egawa":       ["aokatajo", "inakajo"],
    "aokatajo":    ["egawa", "inakajo", "katsuodake"],
}


# ── シナリオローダー ───────────────────────────────────────────────

def load_scenario(path: str) -> GameState:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    player_id = data["player_id"]
    warlords = {}
    for wd in data["warlords"]:
        w = Warlord(
            id=wd["id"],
            name=wd["name"],
            faction_name=wd["faction_name"],
            is_player=(wd["id"] == player_id),
            intelligence=wd["intelligence"],
            military=wd["military"],
            charisma=wd["charisma"],
            prestige=wd["prestige"],
            relations={r["target"]: r["value"] for r in wd.get("relations", [])},
            bond_types={b["target"]: b["label"] for b in wd.get("bond_types", [])},
            warlord_type=wd.get("warlord_type", "daimyo"),
            liege=wd.get("liege", ""),
            loyalty_to_liege=wd.get("loyalty_to_liege", 100),
            treasury=wd.get("treasury", 0),
            food=wd.get("food", 0),
            cavalry=wd.get("cavalry", 0),
            gunners=wd.get("gunners", 0),
            salt_stock=float(wd.get("salt_stock", 0.0)),
            start_hint=wd.get("start_hint", ""),
        )
        warlords[w.id] = w

    territories = {}
    for td in data["territories"]:
        t = Territory(
            id=td["id"],
            name=td["name"],
            owner=td["owner"],
            troops=td["troops"],
            koku=td["koku"],
            fortification=td.get("fortification", 1),
            population=td.get("population", 0),
            loyalty=td.get("loyalty", 70),
            training=td.get("training", 50),
            morale=td.get("morale", 70),
            port_tier=td.get("port_tier", 0),
            commerce=td.get("commerce", 0),
            is_coast=td.get("is_coast", td.get("port_tier", 0) > 0),
            km_to_coast=td.get("km_to_coast", 0),
            industries=td.get("industries", []),
        )
        territories[t.id] = t

    PORT_INCOME = {1: 10, 2: 30, 3: 80}
    for wid, w in warlords.items():
        if w.food == 0 and w.treasury == 0 and w.warlord_type in ("daimyo", "vassal"):
            owned = [t for t in territories.values() if t.owner == wid]
            if owned:
                food_income = sum(int(t.koku * 400 * (t.loyalty / 100)) for t in owned)
                port_income = sum(PORT_INCOME.get(t.port_tier, 0) for t in owned)
                w.food = food_income * 3
                w.treasury = max(port_income * 3, 50)

    external_powers = {}
    for ep_data in data.get("external_powers", []):
        ep = ExternalPower(
            id=ep_data["id"],
            name=ep_data["name"],
            faction=ep_data.get("faction", ""),
            relation=ep_data.get("relation", 0),
            note=ep_data.get("note", ""),
        )
        external_powers[ep.id] = ep

    return GameState(
        year=data["year"],
        month=data["month"],
        turn=1,
        player_id=data["player_id"],
        warlords=warlords,
        territories=territories,
        events=data.get("events", []),
        external_powers=external_powers,
        win_condition=data.get("win_condition", {}),
        win_message=data.get("win_message", ""),
        lose_message=data.get("lose_message", ""),
    )


def save_game(state: GameState, path: str) -> None:
    data = {
        "year": state.year,
        "month": state.month,
        "turn": state.turn,
        "player_id": state.player_id,
        "warlords": [
            {
                "id": w.id,
                "name": w.name,
                "faction_name": w.faction_name,
                "is_player": w.is_player,
                "intelligence": w.intelligence,
                "military": w.military,
                "charisma": w.charisma,
                "prestige": w.prestige,
                "relations": [{"target": k, "value": v} for k, v in w.relations.items()],
                "is_defeated": w.is_defeated,
                "warlord_type": w.warlord_type,
                "liege": w.liege,
                "loyalty_to_liege": w.loyalty_to_liege,
                "treasury": w.treasury,
                "food": w.food,
                "cavalry": w.cavalry,
                "gunners": w.gunners,
                "salt_stock": w.salt_stock,
            }
            for w in state.warlords.values()
        ],
        "territories": [
            {
                "id": t.id,
                "name": t.name,
                "owner": t.owner,
                "troops": t.troops,
                "koku": t.koku,
                "fortification": t.fortification,
                "population": t.population,
                "loyalty": t.loyalty,
                "training": t.training,
                "morale": t.morale,
                "port_tier": t.port_tier,
                "commerce": t.commerce,
                "is_coast": t.is_coast,
                "km_to_coast": t.km_to_coast,
                "industries": t.industries,
                "under_construction": t.under_construction,
                "construction_turns_left": t.construction_turns_left,
            }
            for t in state.territories.values()
        ],
        "external_powers": [
            {"id": ep.id, "name": ep.name, "faction": ep.faction, "relation": ep.relation}
            for ep in state.external_powers.values()
        ],
        "log": [
            {"turn": e.turn, "year": e.year, "month": e.month, "actor": e.actor, "text": e.text}
            for e in state.log[-50:]
        ],
        "sieges": [
            {
                "territory_id": s.territory_id,
                "from_territory": s.from_territory,
                "attacker_id": s.attacker_id,
                "attacker_troops": s.attacker_troops,
                "duration": s.duration,
            }
            for s in state.sieges.values()
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_map_state(state: GameState, path: str) -> None:
    """地図表示用の軽量JSONを書き出す（map_adjacency.htmlがポーリングで読む）。"""
    # 勢力圏: 宗主ID → 支配城IDリスト（宗主自身＋配下の城を集約）
    factions: dict[str, list[str]] = {}
    for t in state.territories.values():
        if t.owner == "neutral":
            continue
        w = state.warlords.get(t.owner)
        if w is None:
            continue
        top = w.id if w.is_player else (w.liege if w.liege else w.id)
        factions.setdefault(top, []).append(t.id)

    data = {
        "year": state.year,
        "month": state.month,
        "turn": state.turn,
        "player_id": state.player_id,
        "castles": {
            t.id: {
                "owner": t.owner,
                "troops": t.troops,
                "name": t.name,
                "koku": t.koku,
                "port_tier": t.port_tier,
            }
            for t in state.territories.values()
        },
        "factions": factions,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
