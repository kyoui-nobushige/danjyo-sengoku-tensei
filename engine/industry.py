"""
産業技術システム

転生者の知識チートによる内政特化要素。
プレイヤーのみが建設可能（NPCは「知らない」）。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import Territory


@dataclass
class IndustryDef:
    id: str
    name: str
    desc: str           # 転生者の記憶として表示するフレーバーテキスト
    cost: int           # 建設コスト（貫）
    turns_to_build: int # 建設ターン数（月）
    gold_per_month: int # 毎月の金収入（貫）
    food_per_month: int # 毎月の兵糧収入（石）
    requires_coast: bool = False  # 沿岸領地が必要
    requires_highland: bool = False
    requires_industry: list[str] = field(default_factory=list)  # 前提産業
    # 特殊効果フラグ
    provides_salt: bool = False        # 塩を産出（交易品）
    provides_saltpeter: bool = False   # 硝石を産出（鉄砲自給コスト半減）
    provides_gunpowder: bool = False   # 火薬（硝石+炭が前提）
    provides_charcoal: bool = False    # 木炭（コークス前提）
    provides_coke: bool = False        # コークス（製鉄効率化）
    max_per_territory: int = 1         # 同一領地に建設できる上限


# 産業マスタ定義
INDUSTRIES: dict[str, IndustryDef] = {

    "salt_farm": IndustryDef(
        id="salt_farm",
        name="流下式塩田",
        desc="海水を段階的に濃縮する製法。従来の入浜より3倍効率がいい。沿岸の砂浜があれば作れる。",
        cost=200,
        turns_to_build=3,
        gold_per_month=0,   # 塩は交易品として蓄積・売却する（直接金収入なし）
        food_per_month=0,
        requires_coast=True,
        provides_salt=True,
    ),

    "shiitake_farm": IndustryDef(
        id="shiitake_farm",
        name="椎茸栽培（原木栽培）",
        desc="コナラの原木に種菌を植える。3年後から毎年収穫。京・博多で高値がつく。",
        cost=80,
        turns_to_build=6,
        gold_per_month=15,
        food_per_month=0,
        requires_highland=False,
    ),

    "rice_grid": IndustryDef(
        id="rice_grid",
        name="正条植え",
        desc="苗を縦横等間隔に植える。風通しがよくなり収量が2割増える。農民への指導が要る。",
        cost=50,
        turns_to_build=1,
        gold_per_month=0,
        food_per_month=0,  # 効果は石高に直接反映（build時に koku×0.2 加算）
    ),

    "rapeseed_oil": IndustryDef(
        id="rapeseed_oil",
        name="菜種油生産",
        desc="菜の花から油を絞る。灯明用に寺社・町人が買う。冬場の裏作にもなる。",
        cost=60,
        turns_to_build=2,
        gold_per_month=12,
        food_per_month=0,
    ),

    "soap_workshop": IndustryDef(
        id="soap_workshop",
        name="石鹸工房",
        desc="灰汁と油を煮詰める。南蛮人から聞いた製法だ。港町でしか売れないが値がいい。",
        cost=120,
        turns_to_build=2,
        gold_per_month=20,
        food_per_month=0,
        requires_industry=["rapeseed_oil"],
    ),

    "charcoal_kiln": IndustryDef(
        id="charcoal_kiln",
        name="炭焼き窯",
        desc="製鉄・製陶の燃料になる。木の多い山間部が向いている。",
        cost=40,
        turns_to_build=1,
        gold_per_month=5,
        food_per_month=0,
        provides_charcoal=True,
    ),

    "saltpeter_pit": IndustryDef(
        id="saltpeter_pit",
        name="硝石蔵（堆肥式）",
        desc="藁・糞尿・石灰を積み重ねて2年熟成させると硝酸カリウムが取れる。"
             "これで火薬が領内自給できる。鉄砲の購入コストが半分になる。",
        cost=150,
        turns_to_build=24,  # 2年かかる
        gold_per_month=0,
        food_per_month=0,
        provides_saltpeter=True,
    ),

    "coal_mine": IndustryDef(
        id="coal_mine",
        name="石炭採掘",
        desc="地面から黒い石が出る場所がある。燃やせば木炭より長持ちする。",
        cost=180,
        turns_to_build=4,
        gold_per_month=20,
        food_per_month=0,
        provides_charcoal=True,  # 炭の代替として機能
    ),

    "beehive_furnace": IndustryDef(
        id="beehive_furnace",
        name="蜂の巣炉（コークス炉）",
        desc="石炭を蒸し焼きにするとコークスになる。製鉄の効率が飛躍的に上がる。",
        cost=300,
        turns_to_build=6,
        gold_per_month=0,
        food_per_month=0,
        requires_industry=["coal_mine"],
        provides_coke=True,
    ),

    "pottery": IndustryDef(
        id="pottery",
        name="陶器窯",
        desc="肥前の土は陶器に向いている。日用品から茶器まで、博多・長崎で売れる。",
        cost=100,
        turns_to_build=3,
        gold_per_month=18,
        food_per_month=0,
        requires_industry=["charcoal_kiln"],
    ),

    "porcelain": IndustryDef(
        id="porcelain",
        name="磁器窯（白磁・青磁）",
        desc="白い土（陶石）を使えば透き通るような白磁ができる。南蛮人が目の色を変える。",
        cost=250,
        turns_to_build=6,
        gold_per_month=50,
        food_per_month=0,
        requires_industry=["pottery"],
    ),

    "glass_workshop": IndustryDef(
        id="glass_workshop",
        name="ガラス工房",
        desc="珪砂と草木灰を高温で溶かす。南蛮人から製法を聞き出した。窓・レンズ・瓶。",
        cost=400,
        turns_to_build=8,
        gold_per_month=60,
        food_per_month=0,
        requires_coast=True,
        requires_industry=["beehive_furnace"],
    ),

    "pencil_workshop": IndustryDef(
        id="pencil_workshop",
        name="鉛筆工房",
        desc="黒鉛を細く削り、木で挟む。寺子屋・算用師・武家に売れる。誰も作っていない。",
        cost=80,
        turns_to_build=2,
        gold_per_month=10,
        food_per_month=0,
    ),
}


def can_build(ind: IndustryDef, territory, player_industries: list[str]) -> tuple[bool, str]:
    """建設可否を判定。(可否, 理由)を返す。"""
    if ind.id in territory.industries:
        return False, "すでに建設済み"
    if getattr(territory, "under_construction", None) == ind.id:
        return False, "建設中"
    if ind.requires_coast and not getattr(territory, "is_coast", False):
        return False, "沿岸領地が必要"
    if ind.requires_highland and not (getattr(territory, "terrain", "") == "highland"):
        return False, "山間部領地が必要"
    for req in ind.requires_industry:
        if req not in player_industries:
            req_name = INDUSTRIES[req].name if req in INDUSTRIES else req
            return False, f"前提産業「{req_name}」が必要"
    return True, ""


def build_cost_display(ind: IndustryDef) -> str:
    parts = [f"{ind.cost}貫"]
    if ind.turns_to_build > 1:
        parts.append(f"建設{ind.turns_to_build}ヶ月")
    return "・".join(parts)


def industry_income_summary(territory) -> dict[str, int]:
    """領地の産業収入合計を返す。"""
    gold = 0
    food = 0
    for ind_id in getattr(territory, "industries", []):
        ind = INDUSTRIES.get(ind_id)
        if ind:
            gold += ind.gold_per_month
            food += ind.food_per_month
    return {"gold": gold, "food": food}


def has_saltpeter(player_territories) -> bool:
    """プレイヤー領地のどこかに硝石蔵があるか。"""
    return any(
        "saltpeter_pit" in getattr(t, "industries", [])
        for t in player_territories
    )
