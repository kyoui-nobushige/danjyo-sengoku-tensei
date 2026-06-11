"""
Rich ベースのCLI UI
"""
from __future__ import annotations
import os
import sys
import unicodedata
from typing import TYPE_CHECKING, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.rule import Rule
from rich import box

if TYPE_CHECKING:
    from engine.game_state import GameState, Warlord

console = Console(force_terminal=True, legacy_windows=False)


def _input(prompt: str) -> str:
    """全角数字・記号を半角に正規化して返す。IME切替不要にする。"""
    raw = console.input(prompt).strip()
    return unicodedata.normalize('NFKC', raw)


def clear_screen() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')


# ── LLM選択 ───────────────────────────────────────────────────────

def choose_llm_provider() -> str:
    console.print(Panel(
        "[bold]使用するAIを選んでください[/bold]\n\n"
        "  [1] [cyan]Claude[/cyan]   Anthropic APIキー必要・有料・最高品質\n"
        "  [2] [green]Gemini[/green]   Google APIキー必要・無料枠あり\n"
        "  [3] [dim]ローカル[/dim]  LM Studio使用・APIキー不要・完全無料\n\n"
        "  [dim]APIキーの取得方法・費用目安は README.md を参照[/dim]",
        title="[bold yellow]AI選択[/bold yellow]",
        border_style="yellow",
        padding=(1, 4),
    ))
    while True:
        choice = _input("  選択 [1/2/3] > ")
        if choice == "1":
            console.print("  [cyan]Claude を使用します[/cyan]\n")
            return "anthropic"
        if choice == "2":
            console.print("  [green]Gemini を使用します[/green]\n")
            return "gemini"
        if choice == "3":
            console.print("  [dim]ローカル(LM Studio)を使用します[/dim]\n")
            return "lmstudio"
        console.print("  [red]1・2・3 のいずれかを入力してください[/red]")


# ── タイトル ──────────────────────────────────────────────────────

def show_title() -> None:
    clear_screen()
    title = Text()
    title.append("戦国AI転生ストラテジー\n", style="bold yellow")
    title.append("弾正戦国転生記", style="bold white")
    console.print(Panel(title, border_style="red", padding=(1, 4)))
    console.print()


def show_scenario_intro(title: str, description: str) -> None:
    console.print(Panel(
        f"[bold]{title}[/bold]\n\n{description}",
        border_style="yellow",
        title="[red]シナリオ",
    ))
    console.print()
    console.input("[dim]Enterで開始...[/dim]")
    clear_screen()


# ── 季節ヘルパー（旧暦: 1-3春/4-6夏/7-9秋/10-12冬） ─────────────

_SEASON = {1:"春",2:"春",3:"春",4:"夏",5:"夏",6:"夏",7:"秋",8:"秋",9:"秋",10:"冬",11:"冬",12:"冬"}
_SEASON_COLOR = {"春":"green","夏":"yellow","秋":"orange3","冬":"cyan"}

def _months_to_next_season(month: int) -> int:
    """現在月から次季の初月まで何ヶ月か返す（1〜3）。"""
    next_start = ((month - 1) // 3 + 1) * 3 + 1  # 4, 7, 10, 13
    return next_start - month


# ── ターンヘッダ（毎ターン・2カラムレイアウト） ───────────────────

def show_turn_header(state: GameState) -> None:
    console.print(Rule(style="dim"))
    player = state.player
    player_terrs = player.territories(state)
    total_troops = sum(t.troops for t in player_terrs)
    home = max(player_terrs, key=lambda t: t.koku) if player_terrs else None

    inc = state._calc_income(player.id)
    net = inc["food_net"]
    food_sign = "+" if net >= 0 else ""
    food_color = "green" if net >= 0 else "yellow"

    # ── 右パネル（大名ステータス） ────────────────────────────────
    r = Text()
    r.append("\n")
    # 簡易顔グラ（名前2文字）
    n = player.name[:2]
    r.append("  ┌──────────┐\n", style="yellow")
    r.append(f"  │  {n}　　│\n", style="bold yellow")
    r.append( "  │  　　　　│\n", style="yellow")
    r.append( "  └──────────┘\n", style="yellow")
    r.append("\n")
    r.append("  ─────────────\n", style="dim")
    rank = state.warlord_rank(player.id)
    if rank:
        r.append("  身分  ", style="dim")
        rank_color = {"国人": "white", "小大名": "cyan", "大名": "yellow", "戦国大名": "bold red"}.get(rank, "white")
        r.append(f"{rank}\n", style=rank_color)
    if home:
        r.append("  本拠  ", style="dim")
        r.append(f"{home.name}\n", style="cyan")
    r.append("  支配  ", style="dim")
    r.append(f"{len(player_terrs)}城\n")
    total_stone = int(sum(t.koku for t in player_terrs) * 10000)
    r.append("  石高  ", style="dim")
    r.append(f"{total_stone:,}石\n", style="cyan")
    r.append("  総兵  ", style="dim")
    r.append(f"{total_troops:,}\n", style="cyan")
    if player.cavalry > 0 or player.gunners > 0:
        r.append("  騎馬  ", style="dim")
        r.append(f"{player.cavalry:,}\n", style="cyan")
        r.append("  鉄砲  ", style="dim")
        r.append(f"{player.gunners:,}\n", style="cyan")
    r.append("  兵糧  ", style="dim")
    r.append(f"{player.food:,}石 ")
    r.append(f"({food_sign}{net})\n", style=food_color)
    r.append("  金庫  ", style="dim")
    r.append(f"{player.treasury}貫\n", style="yellow")
    commerce_income = sum(int(t.commerce * 5 * t.loyalty / 100) for t in player_terrs)
    if commerce_income > 0:
        r.append("  商業  ", style="dim")
        r.append(f"+{commerce_income}貫/月\n", style="yellow")
    # 産業収入（塩以外）
    from engine.industry import industry_income_summary
    ind_gold = sum(industry_income_summary(t)["gold"] for t in player_terrs)
    if ind_gold > 0:
        r.append("  産業  ", style="dim")
        r.append(f"+{ind_gold}貫/月\n", style="magenta")
    # 塩田月産・備蓄
    salt_farms = [t for t in player_terrs if "salt_farm" in getattr(t, "industries", [])]
    if salt_farms:
        from engine.economy import SALT_FARM_IRIHAMA_ANNUAL_KOKU, SALT_FARM_RYUKA_MULTIPLIER
        monthly = len(salt_farms) * SALT_FARM_IRIHAMA_ANNUAL_KOKU * SALT_FARM_RYUKA_MULTIPLIER / 12
        r.append("  月産塩 ", style="dim")
        r.append(f"+{_koku_to_traditional(monthly)}/月\n", style="cyan")
    if player.salt_stock >= 0.001:
        r.append("  塩備蓄 ", style="dim")
        r.append(f"{_koku_to_traditional(player.salt_stock)}\n", style="cyan")
    # 港情報
    ports = [(t.name, t.port_tier) for t in player_terrs if t.port_tier > 0]
    if ports:
        PORT_LABEL = {1: "沿岸", 2: "外洋", 3: "南蛮"}
        r.append("  ─────────────\n", style="dim")
        r.append("  港湾\n", style="dim")
        for pname, ptier in ports:
            color = {1: "white", 2: "cyan", 3: "bold yellow"}.get(ptier, "white")
            r.append(f"  {pname[:4]:<5}", style="white")
            r.append(PORT_LABEL[ptier] + "\n", style=color)
    r.append("  ─────────────\n", style="dim")
    r.append("  関係値\n", style="dim")
    shown = 0
    for wid, w in state.warlords.items():
        if wid == player.id or w.is_defeated or w.warlord_type == "clan":
            continue
        if shown >= 7:
            break
        val = player.relations.get(wid, 0)
        label = player.relation_label(wid)
        color = _relation_color(val)
        r.append(f"  {w.name[:4]:<5}", style="white")
        r.append(f"{label}\n", style=color)
        shown += 1

    right_panel = Panel(r, border_style="yellow", padding=(0, 0))

    # ── 左パネル（ターン・ログ・メニュー） ────────────────────────
    recent = state.log[-5:]
    log_lines = []
    for e in recent:
        name = state.warlords[e.actor].name if e.actor in state.warlords else e.actor
        if e.actor == player.id:
            log_lines.append(f"  [bold cyan]> {name}:[/bold cyan] {e.text}")
        else:
            log_lines.append(f"  [dim]{name}: {e.text}[/dim]")
    logs = "\n".join(log_lines) or "  [dim]（まだ動きなし）[/dim]"

    season = _SEASON[state.month]
    s_color = _SEASON_COLOR[season]
    left_content = "\n".join([
        "",
        f"  [bold yellow]─── {state.year}年 {state.month}月[/bold yellow]"
        f"[{s_color}]【{season}】[/{s_color}]"
        f"[bold yellow]  評定 ───[/bold yellow]",
        "",
        "  [dim]── 直近の動き ─────────────────────────[/dim]",
        logs,
        "",
        "  [bold]── 評定（行動を選択） ───────────────────[/bold]",
        "",
        "  [[bold cyan]1[/bold cyan]] 外交         [[bold cyan]2[/bold cyan]] 内政・徴兵",
        "  [[bold cyan]3[/bold cyan]] 出陣         [[bold cyan]4[/bold cyan]] 軍師に相談",
        "  [[bold cyan]5[/bold cyan]] 詳細情報     [[bold cyan]S[/bold cyan]] セーブ   [[bold cyan]M[/bold cyan]] 地図   [[bold cyan]L[/bold cyan]] LLM切替",
        "  [[bold green]E[/bold green]] 評定を終える   [[bold green]N[/bold green]] スキップ（次月/数月/次季）",
        "",
    ])
    left_panel = Panel(left_content, border_style="blue", padding=(0, 0))

    # ── Table.grid で横並び ───────────────────────────────────────
    grid = Table.grid(expand=True)
    grid.add_column(ratio=3)
    grid.add_column(min_width=22)
    grid.add_row(left_panel, right_panel)
    console.print(grid)


# ── 詳細ステータス（[5]押下時のみ） ──────────────────────────────

def show_status(state: GameState) -> None:
    player = state.player

    # 領土テーブル
    territory_table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    territory_table.add_column("領土", width=8)
    territory_table.add_column("支配", width=10)
    territory_table.add_column("兵力", justify="right", width=8)
    territory_table.add_column("石高", justify="right", width=8)
    territory_table.add_column("防衛", justify="center", width=6)

    for t in state.territories.values():
        if t.owner == "neutral":
            owner_str = "[dim]中立[/dim]"
            row_style = "dim"
        elif t.owner == player.id:
            owner_str = f"[green]{player.name}[/green]"
            row_style = "green"
        else:
            w = state.warlords[t.owner]
            owner_str = f"[red]{w.name}[/red]"
            row_style = ""

        fort_str = "★" * t.fortification + "☆" * (5 - t.fortification)
        base_troops = t.koku * 250
        if t.troops > base_troops:
            troops_str = f"{base_troops:,} [dim]({t.troops:,})[/dim]"
        else:
            troops_str = f"{t.troops:,}"
        territory_table.add_row(
            t.name, owner_str,
            troops_str, f"{int(t.koku*10000):,}石", fort_str,
            style=row_style,
        )

    # 関係値テーブル
    relation_table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    relation_table.add_column("相手", width=10)
    relation_table.add_column("関係値", justify="right", width=6)
    relation_table.add_column("状態", width=8)

    for wid, w in state.warlords.items():
        if wid == player.id or w.is_defeated or w.warlord_type == "clan":
            continue
        val = player.relations.get(wid, 0)
        label = player.relation_label(wid)
        color = _relation_color(val)
        relation_table.add_row(w.name, f"{val:+d}", f"[{color}]{label}[/{color}]")

    if state.external_powers:
        relation_table.add_row("[dim]── 外部 ──[/dim]", "", "")
        for ep in state.external_powers.values():
            color = _relation_color(ep.relation)
            relation_table.add_row(
                f"[magenta]{ep.name}[/magenta]",
                f"[{color}]{ep.relation:+d}[/{color}]",
                "[dim]外部勢力[/dim]",
            )

    console.print(Columns([territory_table, relation_table], equal=False, expand=False))
    console.print()


def _relation_color(val: int) -> str:
    if val <= -70: return "red"
    if val <= -40: return "orange3"
    if val <= -10: return "yellow"
    if val <= 20:  return "white"
    if val <= 50:  return "cyan"
    return "green"


# ── アクション選択 ────────────────────────────────────────────────

def get_player_action() -> str:
    while True:
        choice = _input("  選択 > ").lower()
        if choice in ("1", "2", "3", "4", "5", "s", "m", "e", "n", "l"):
            return choice
        console.print("  [red]1〜5、S、M、L、E、Nのいずれかを入力してください[/red]")


# ── 外交 ──────────────────────────────────────────────────────────

def select_diplomacy_target(state: GameState) -> Optional[str]:
    targets = [w for w in state.ai_warlords()]
    ext_powers = list(state.external_powers.values())

    if not targets and not ext_powers:
        console.print("[red]交渉できる相手がいない。[/red]")
        return None

    console.print("\n[bold]【外交相手】[/bold]")
    for i, w in enumerate(targets, 1):
        val = state.player.relations.get(w.id, 0)
        label = state.player.relation_label(w.id)
        console.print(f"  [{i}] {w.name}（{label} {val:+d}）")

    offset = len(targets)
    if ext_powers:
        console.print("  [dim]── シナリオ外勢力 ──[/dim]")
        for i, ep in enumerate(ext_powers, offset + 1):
            color = _relation_color(ep.relation)
            console.print(
                f"  [{i}] [bold magenta]{ep.name}[/bold magenta]"
                f"（{ep.faction}  関係値:[{color}]{ep.relation:+d}[/{color}]）"
            )
    console.print("  [0] キャンセル")

    while True:
        choice = _input("  選択 > ")
        if choice == "0":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(targets):
                return targets[idx].id
            ep_idx = idx - offset
            if 0 <= ep_idx < len(ext_powers):
                return f"ext:{ext_powers[ep_idx].id}"
        except ValueError:
            pass
        console.print("  [red]番号を入力してください[/red]")


def select_external_diplomacy_action(ep) -> Optional[tuple[str, str]]:
    """シナリオ外勢力との外交アクション選択UI。"""
    from llm.warlord import EXTERNAL_POWER_ACTIONS
    actions = EXTERNAL_POWER_ACTIONS.get(ep.id, [
        ("friendly_envoy", "友好使節を送る"),
        ("small_talk",     "近況を伺う"),
    ])
    color = _relation_color(ep.relation)
    console.print(f"\n[bold magenta]【{ep.name}（{ep.faction}）との外交】[/bold magenta]")
    console.print(f"  関係値: [{color}]{ep.relation:+d}[/{color}]")
    if ep.note:
        console.print(f"  [dim]{ep.note}[/dim]")
    console.print()
    for i, (key, label) in enumerate(actions, 1):
        console.print(f"  [{i}] {label}")
    console.print("  [0] キャンセル")

    while True:
        choice = _input("  選択 > ")
        if choice == "0":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(actions):
                return actions[idx]
        except ValueError:
            pass
        console.print("  [red]番号を入力してください[/red]")


def select_diplomacy_action() -> Optional[tuple[str, str]]:
    actions = [
        ("propose_alliance", "同盟の提案"),
        ("trade",            "物資援助の申し出"),
        ("threaten",         "脅迫"),
        ("apologize",        "謝罪"),
        ("demand_surrender", "降伏勧告"),
        ("small_talk",       "世間話（関係値微増狙い）"),
    ]
    console.print("\n[bold]【申し入れ内容】[/bold]")
    for i, (key, label) in enumerate(actions, 1):
        console.print(f"  [{i}] {label}")
    console.print("  [0] キャンセル")

    while True:
        choice = _input("  選択 > ")
        if choice == "0":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(actions):
                return actions[idx]
        except ValueError:
            pass
        console.print("  [red]番号を入力してください[/red]")


def show_warlord_dialogue(warlord_name: str, dialogue: str, thought: str, response_type: str) -> None:
    color_map = {
        "accept": "green", "reject": "red", "counter": "yellow",
        "threaten": "red", "neutral": "white",
    }
    color = color_map.get(response_type, "white")
    console.print(Panel(
        f"[{color}]{dialogue}[/{color}]",
        title=f"[bold]{warlord_name}[/bold]",
        border_style=color,
    ))
    if thought:
        console.print(f"  [dim italic]（本音: {thought}）[/dim italic]")


def get_diplomacy_follow_up() -> str:
    console.print("[bold]【返答】[/bold]  [1]続ける  [0]終了")
    while True:
        choice = _input("  選択 > ")
        if choice == "0":
            return "end"
        if choice == "1":
            msg = console.input("  あなたの言葉: ").strip()
            if msg:
                return msg
            console.print("  [red]言葉を入力してください[/red]")


# ── 内政 ──────────────────────────────────────────────────────────

def select_internal_territory(state: GameState) -> Optional[str]:
    owned = [t for t in state.territories.values() if t.owner == state.player_id]
    if not owned:
        return None

    console.print("\n[bold]【内政対象】[/bold]")
    for i, t in enumerate(owned, 1):
        port_str = f"  港Tier{t.port_tier}" if t.port_tier > 0 else ""
        console.print(
            f"  [{i}] {t.name}  {int(t.koku*10000):,}石"
            f"  商業Lv{t.commerce}  兵力:{t.troops:,}  防衛:{t.fortification}/5{port_str}"
        )
    console.print("  [0] キャンセル")

    while True:
        choice = _input("  選択 > ")
        if choice == "0":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(owned):
                return owned[idx].id
        except ValueError:
            pass
        console.print("  [red]番号を入力してください[/red]")


def commerce_invest_cost(t) -> int:
    """商業投資コスト（石高 × レベルに比例）。"""
    return max(30, int((t.commerce + 1) * 30 * (1 + t.koku * 2)))


def select_territory_batch(
    state: "GameState",
    cost_fn,
    label_fn,
    eligible_fn,
) -> list[str]:
    """複数領地の一括選択。番号/カンマ区切り/A=全部/0=キャンセル。"""
    owned = [t for t in state.territories.values() if t.owner == state.player_id]
    eligible = [t for t in owned if eligible_fn(t)]
    if not eligible:
        console.print("  [dim]対象となる領地がありません。[/dim]")
        return []

    console.print(
        "\n[bold]【内政対象】[/bold]"
        "  [dim]番号・スペース/カンマ区切り・A=全部・0=キャンセル[/dim]"
    )
    for i, t in enumerate(eligible, 1):
        cost = cost_fn(t)
        extra = label_fn(t)
        console.print(f"  [{i}] {t.name}  {int(t.koku*10000):,}石  {extra}  コスト:{cost}貫")
    console.print(f"  [A] 全部（{len(eligible)}箇所  合計{sum(cost_fn(t) for t in eligible)}貫）")
    console.print("  [0] キャンセル")

    while True:
        choice = _input("  選択 > ").strip().lower()
        if choice == "0":
            return []
        if choice == "a":
            return [t.id for t in eligible]
        try:
            nums = [int(x) for x in choice.replace(",", " ").split()]
            ids = []
            for n in nums:
                if 1 <= n <= len(eligible):
                    ids.append(eligible[n - 1].id)
                else:
                    ids = []
                    break
            if ids:
                return list(dict.fromkeys(ids))
        except ValueError:
            pass
        console.print("  [red]番号で入力してください（例: 1  / 1,3  / A）[/red]")


def confirm_batch(player, territory_ids: list, state: "GameState", cost_fn, detail_fn) -> bool:
    """複数選択時の確認プレビュー。Yで実行、nでキャンセル。"""
    if len(territory_ids) <= 1:
        return True
    total = sum(cost_fn(state.territories[tid]) for tid in territory_ids)
    console.print(f"\n[bold]【一括実行確認】[/bold]  合計[yellow]{total}貫[/yellow]  残金庫:{player.treasury - total}貫")
    for tid in territory_ids:
        t = state.territories[tid]
        console.print(f"  {t.name}: -{cost_fn(t)}貫  {detail_fn(t)}")
    choice = _input("  実行しますか？ [Y/n] > ").strip().lower()
    return choice != "n"


# ── 内政・軍備メニュー定数 ───────────────────────────────────────

CAVALRY_BUY_PRICE  = 5    # 貫/騎（相場購入）
CAVALRY_SELL_PRICE = 3    # 貫/騎（売却）
CAVALRY_RANCH_COST = 2    # 貫/騎（放牧・山間部領地が必要）
GUNNER_BUY_PRICE   = 10   # 貫/丁（相場購入）
GUNNER_SELL_PRICE  = 6    # 貫/丁（売却）
GUNNER_FORGE_COST  = 6    # 貫/丁（増産・鍛冶場領地が必要）


MERCENARY_COST = 5       # 傭兵 貫/兵
COMMERCE_MAX   = 10      # 商業レベル上限

def select_internal_action(player: "Warlord") -> Optional[str]:
    """内政トップメニュー。"""
    console.print(f"\n[bold]【内政・軍備】[/bold]  [dim]金庫: {player.treasury}貫[/dim]")
    console.print(f"  [1] 徴兵（無料・民忠↓）  [2] 傭兵（[bold yellow]{MERCENARY_COST}貫/兵[/bold yellow]・即戦力）")
    console.print(f"  [3] 城強化（防衛+1）      [4] 商業投資（金収入↑）")
    console.print(
        f"  [5] 騎馬を買う  [bold yellow]{CAVALRY_BUY_PRICE}貫/騎[/bold yellow]"
        f"  [6] 騎馬を売る  [dim]{CAVALRY_SELL_PRICE}貫/騎[/dim]  現在:[cyan]{player.cavalry:,}騎[/cyan]"
    )
    console.print(
        f"  [7] 鉄砲を買う  [bold yellow]{GUNNER_BUY_PRICE}貫/丁[/bold yellow]"
        f"  [8] 鉄砲を売る  [dim]{GUNNER_SELL_PRICE}貫/丁[/dim]  現在:[cyan]{player.gunners:,}丁[/cyan]"
    )
    console.print(
        f"  [9] 放牧（騎馬増産[bold green]{CAVALRY_RANCH_COST}貫/騎[/bold green]・山間部）"
        f"  [[bold cyan]a[/bold cyan]] 鉄砲増産（[bold green]{GUNNER_FORGE_COST}貫/丁[/bold green]・鍛冶場）"
    )
    console.print(f"  [[bold cyan]b[/bold cyan]] 新田開発（石高+10年分・石高比例コスト）")
    console.print(f"  [[bold magenta]i[/bold magenta]] [bold magenta]【転生者の知識】産業建設[/bold magenta]")
    if player.salt_stock >= 0.001:
        stock_str = _koku_to_traditional(player.salt_stock)
        console.print(
            f"  [[bold cyan]t[/bold cyan]] [bold cyan]塩を交易する[/bold cyan]"
            f"  [dim]備蓄: {stock_str}[/dim]"
        )
    console.print(f"  [0] キャンセル")
    MAP = {"1": "draft", "2": "mercenary", "3": "2", "4": "commerce_invest",
           "5": "c_buy", "6": "c_sell", "7": "g_buy", "8": "g_sell",
           "9": "c_ranch", "a": "g_forge", "b": "shinden", "i": "industry",
           "t": "salt_trade"}
    while True:
        choice = _input("  選択 > ").lower()
        if choice == "0":
            return None
        if choice in MAP:
            if choice == "t" and player.salt_stock < 0.001:
                console.print("  [red]塩の備蓄がありません[/red]")
                continue
            return MAP[choice]
        console.print("  [red]0〜9またはa/b/i/tを入力してください[/red]")


def select_industry(
    territory,
    player_all_industries: list[str],
    llm=None,
    state=None,
    advisor_name: str = "軍師",
) -> "Optional[str]":
    """産業建設メニュー。建設する産業IDを返す。キャンセルはNone。"""
    from engine.industry import INDUSTRIES, can_build, build_cost_display
    console.print(f"\n[bold magenta]【転生者の知識】産業建設 ─ {territory.name}[/bold magenta]")
    if territory.under_construction:
        from engine.industry import INDUSTRIES as IND
        ind = IND.get(territory.under_construction)
        console.print(
            f"  [yellow]建設中: {ind.name if ind else territory.under_construction}"
            f" (残{territory.construction_turns_left}ヶ月)[/yellow]"
        )
    if territory.industries:
        names = [INDUSTRIES[i].name if i in INDUSTRIES else i for i in territory.industries]
        console.print(f"  [green]建設済: {' / '.join(names)}[/green]")

    options = []
    for ind in INDUSTRIES.values():
        ok, reason = can_build(ind, territory, player_all_industries)
        options.append((ind, ok, reason))

    console.print()
    idx = 1
    valid = {}
    for ind, ok, reason in options:
        if ok:
            eff = []
            if ind.gold_per_month: eff.append(f"+{ind.gold_per_month}貫/月")
            if ind.food_per_month: eff.append(f"+{ind.food_per_month}石/月")
            if ind.provides_saltpeter: eff.append("鉄砲自給コスト半減")
            if ind.provides_salt: eff.append("塩・交易品")
            if ind.id == "rice_grid": eff.append("石高+20%（即時）")
            eff_str = "・".join(eff) if eff else "特殊効果"
            console.print(
                f"  [{idx}] [bold]{ind.name}[/bold]  {build_cost_display(ind)}"
                f"  [cyan]{eff_str}[/cyan]"
            )
            console.print(f"      [dim italic]{ind.desc}[/dim italic]")
            valid[str(idx)] = ind.id
            idx += 1
        else:
            console.print(f"  [dim]　　{ind.name}  [red]×{reason}[/red][/dim]")

    console.print("  [0] キャンセル")
    while True:
        choice = _input("  選択 > ").strip()
        if choice == "0":
            return None
        if choice in valid:
            return valid[choice]
        if choice == "?" and llm is not None and state is not None:
            _industry_advisor_chat(llm, state, territory, advisor_name)
            continue
        console.print("  [red]番号を入力してください[/red]")


def _koku_to_traditional(koku: float) -> str:
    """石（小数）→「XX石X斗X升X合X勺」形式の文字列。1石=10斗=100升=1000合=10000勺"""
    total_shaku = round(koku * 10000)  # 勺単位（1石=10000勺）
    # 石・斗・升・合・勺の単位で分解
    ko = total_shaku // 10000
    total_shaku %= 10000
    to = total_shaku // 1000
    total_shaku %= 1000
    sho = total_shaku // 100
    total_shaku %= 100
    go = total_shaku // 10
    shaku = total_shaku % 10
    parts = []
    if ko:   parts.append(f"{ko}石")
    if to:   parts.append(f"{to}斗")
    if sho:  parts.append(f"{sho}升")
    if go:   parts.append(f"{go}合")
    if shaku: parts.append(f"{shaku}勺")
    return "".join(parts) if parts else "0升"


def _build_industry_consult_context(state, territory) -> str:
    """産業相談用コンテキスト。生産量を伝統単位で記述する。"""
    from engine.industry import INDUSTRIES, can_build
    from engine.economy import (
        SALT_PRODUCTION_PER_FARM, SALT_BASE_PRICE, SALT_COST_PER_KM,
        SALT_FARM_AREA_TEXT, SALT_FARM_IRIHAMA_ANNUAL_KOKU, SALT_FARM_RYUKA_MULTIPLIER,
        _bfs_tile_distance, km_to_coast_of, salt_price_at_km,
    )

    lines: list[str] = []
    player_inds = [i for t in state.player.territories(state) for i in t.industries]
    bfs = _bfs_tile_distance(state)

    # ── 対象領地の現状 ─────────────────────────────
    lines.append(f"【{territory.name}の現状】")
    if territory.industries:
        built_names = [INDUSTRIES[i].name if i in INDUSTRIES else i for i in territory.industries]
        lines.append(f"建設済み産業: {' / '.join(built_names)}")
    else:
        lines.append("建設済み産業: なし")
    if territory.under_construction:
        ind = INDUSTRIES.get(territory.under_construction)
        rem = getattr(territory, "construction_turns_left", 0)
        lines.append(f"建設中: {ind.name if ind else territory.under_construction}（残{rem}ヶ月）")

    # ── 建設可能産業の詳細（伝統単位つき） ──────────
    lines.append("")
    lines.append("【建設可能な産業と収益（詳細）】")
    for ind in INDUSTRIES.values():
        ok, _ = can_build(ind, territory, player_inds)
        if not ok:
            continue
        detail_parts: list[str] = []
        if ind.id == "salt_farm":
            # 軍師が知っているのは現行（入浜式）の実態のみ。流下式は転生者の秘密知識。
            irihama_str = _koku_to_traditional(SALT_FARM_IRIHAMA_ANNUAL_KOKU)
            km = km_to_coast_of(territory, bfs)
            price = salt_price_at_km(km)
            detail_parts.append(f"現在の塩田（入浜式）: {SALT_FARM_AREA_TEXT} / 年産{irihama_str}")
            detail_parts.append(f"産地売値: {price}文/升")
            detail_parts.append(
                "※「流下式」は殿のみが知る未知の製法。"
                "軍師はこの言葉を知らず、殿から説明されて初めて反応する。"
            )
        elif ind.gold_per_month:
            detail_parts.append(f"月収入{ind.gold_per_month}貫")
        if ind.food_per_month:
            detail_parts.append(f"月産{ind.food_per_month}石")
        if ind.id == "rice_grid":
            koku = getattr(territory, "koku", 0)
            detail_parts.append(f"石高+{int(koku * 0.2)}石（即時・{territory.name}現在{koku}石の20%）")
        detail_parts.append(f"建設費{ind.cost}貫")
        if ind.turns_to_build > 1:
            detail_parts.append(f"建設{ind.turns_to_build}ヶ月")
        lines.append(f"・{ind.name}: {' / '.join(detail_parts)}")

    # ── 塩の近隣相場（塩田に関係する場合のヒント） ───
    price_rows = []
    for w in state.warlords.values():
        if w.is_defeated:
            continue
        terrs = w.territories(state)
        if not terrs:
            continue
        best = max(terrs, key=lambda t: getattr(t, "koku", 0))
        km = km_to_coast_of(best, bfs)
        price_rows.append((best.name, w.name, km, salt_price_at_km(km)))
    if price_rows:
        lines.append("")
        lines.append("【主要城下の塩相場（参考）】")
        for tname, wname, km, price in sorted(price_rows, key=lambda x: x[3])[:5]:
            lines.append(f"  {tname}（{wname}領）: {price}文/升")

    lines.append("")
    lines.append(
        "【回答の指示】\n"
        "上記の具体的な数字を根拠にして答えよ。"
        "生産量は升・斗・石など当世の単位で述べよ。"
        "貫換算はあくまで補足とし、まず実物量（升・石）を先に語れ。"
        "現在の建設状況（建設済み・なし）を踏まえて答えよ。"
    )
    return "\n".join(lines)


def _industry_advisor_chat(llm, state, territory, advisor_name: str) -> None:
    """産業建設メニュー内の隠し軍師相談。"""
    from llm.warlord import get_advisor_advice
    console.print()
    console.print(f"  [dim]（足音が近づき、戸が静かに開く）[/dim]")
    console.print()
    console.print(
        f"  [bold cyan]{advisor_name}[/bold cyan]"
        f"  「殿、いかがなさいますか？」"
    )
    console.print()
    words = console.input("  殿 > ").strip()
    if not words:
        console.print(f"  [dim]{advisor_name} 「……お呼びでしたか。では、また後ほど」[/dim]")
        console.print()
        return
    console.print()
    console.print(f"  [dim]{advisor_name} が考えをまとめています……[/dim]")
    consult_ctx = _build_industry_consult_context(state, territory)
    question = f"{consult_ctx}\n\n【殿の問い】{words}"
    try:
        advice = get_advisor_advice(llm, state, question)
    except Exception:
        console.print(f"  [red]{advisor_name} 「……しばし、お待ちを」（返答できませんでした）[/red]")
        console.print()
        return
    console.print(Panel(
        advice,
        title=f"[bold cyan]{advisor_name}の返答[/bold cyan]",
        border_style="cyan",
    ))
    console.input("[dim]Enterで産業建設に戻る...[/dim]")
    console.print()


def select_unit_amount(unit_name: str, unit_cost: int, treasury: int, current: int = 0) -> int:
    """購入・生産数量を選択する。0=キャンセル。"""
    max_n = treasury // unit_cost if unit_cost > 0 else 0
    console.print(
        f"\n[bold]{unit_name}[/bold]  {unit_cost}貫/口  "
        f"金庫:{treasury}貫  最大{max_n:,}口"
    )
    presets = [20, 50, 100]
    for i, n in enumerate(presets, 1):
        affordable = "[dim]（金庫不足）[/dim]" if n * unit_cost > treasury else ""
        console.print(f"  [{i}] {n}口  {affordable}")
    console.print("  [4] 手入力  [0] キャンセル")
    while True:
        choice = _input("  選択 > ")
        if choice == "0":
            return 0
        if choice in ("1", "2", "3"):
            n = presets[int(choice) - 1]
            if n * unit_cost > treasury:
                console.print(f"  [red]金庫不足（必要:{n * unit_cost}貫）[/red]")
                continue
            return n
        if choice == "4":
            try:
                n = int(_input("  数量 > "))
                if n <= 0:
                    continue
                if n * unit_cost > treasury:
                    console.print(f"  [red]金庫不足（必要:{n * unit_cost}貫）[/red]")
                    continue
                return n
            except ValueError:
                pass
        console.print("  [red]有効な選択をしてください[/red]")


def select_sell_amount(unit_name: str, current: int, sell_price: int) -> int:
    """売却数量を選択する。0=キャンセル。"""
    if current <= 0:
        console.print(f"  [red]{unit_name}がいない。[/red]")
        return 0
    console.print(
        f"\n[bold]{unit_name}売却[/bold]  {sell_price}貫/口  現在:{current:,}口"
    )
    presets = [20, 50, current]
    labels  = ["20口", "50口", f"全部({current:,}口)"]
    for i, (n, lbl) in enumerate(zip(presets, labels), 1):
        if n > current:
            continue
        console.print(f"  [{i}] {lbl}")
    console.print("  [4] 手入力  [0] キャンセル")
    while True:
        choice = _input("  選択 > ")
        if choice == "0":
            return 0
        if choice in ("1", "2", "3"):
            n = presets[int(choice) - 1]
            if n > current:
                console.print("  [red]保有数を超えています[/red]")
                continue
            return n
        if choice == "4":
            try:
                n = int(_input("  数量 > "))
                if 0 < n <= current:
                    return n
                console.print("  [red]有効な数を入力してください[/red]")
            except ValueError:
                pass
        console.print("  [red]有効な選択をしてください[/red]")


# ── 出陣 ──────────────────────────────────────────────────────────

def select_attack_source(state: GameState) -> Optional[str]:
    owned = [t for t in state.territories.values() if t.owner == state.player_id and t.troops > 100]
    if not owned:
        console.print("[red]出撃できる兵力がない。[/red]")
        return None

    console.print("\n[bold]【出撃元】[/bold]")
    for i, t in enumerate(owned, 1):
        adj_enemies = [
            state.territories[aid].name
            for aid in state.adjacent_territories(t.id)
            if state.territories[aid].owner != state.player_id
        ]
        console.print(f"  [{i}] {t.name}  兵力:{t.troops:,}  隣接敵地:{adj_enemies}")
    console.print("  [0] キャンセル")

    while True:
        choice = _input("  選択 > ")
        if choice == "0":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(owned):
                return owned[idx].id
        except ValueError:
            pass
        console.print("  [red]番号を入力してください[/red]")


def select_attack_target(state: GameState, from_territory_id: str) -> Optional[str]:
    adj_ids = state.adjacent_territories(from_territory_id)
    targets = [state.territories[aid] for aid in adj_ids if state.territories[aid].owner != state.player_id]
    if not targets:
        console.print("[red]攻撃できる隣接地がない。[/red]")
        return None

    console.print("\n[bold]【攻撃先】[/bold]")
    for i, t in enumerate(targets, 1):
        owner = state.warlords[t.owner].name if t.owner != "neutral" else "中立"
        console.print(f"  [{i}] {t.name}（{owner}）  兵力:{t.troops:,}  防衛:{t.fortification}/5")
    console.print("  [0] キャンセル")

    while True:
        choice = _input("  選択 > ")
        if choice == "0":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(targets):
                return targets[idx].id
        except ValueError:
            pass
        console.print("  [red]番号を入力してください[/red]")


def select_troops_to_send(from_troops: int) -> int:
    console.print(f"\n[bold]【出撃兵力】[/bold]  現在:{from_troops:,}")
    console.print(f"  [1]全軍({from_troops:,})  [2]半数({from_troops//2:,})  [3]少数({from_troops//4:,})  [4]手入力")
    presets = {"1": from_troops, "2": from_troops // 2, "3": from_troops // 4}
    while True:
        choice = _input("  選択 > ")
        if choice in presets:
            return max(1, presets[choice])
        if choice == "4":
            try:
                n = int(_input("  兵数を入力: "))
                if 1 <= n <= from_troops:
                    return n
            except ValueError:
                pass
        console.print("  [red]有効な選択をしてください[/red]")


def select_attack_goal(state, to_territory_id: str) -> str:
    from engine.combat import get_hq_guard_troops
    to_t = state.territories[to_territory_id]
    if to_t.owner == "neutral":
        return "full_army"
    warlord_name = state.warlords[to_t.owner].name
    guard = get_hq_guard_troops(to_t.troops)
    console.print(f"\n[bold]【攻撃目標】[/bold]")
    console.print(f"  [1] 全軍と交戦          {to_t.name} {to_t.troops:,}と戦う")
    console.print(f"  [2] {warlord_name}の本陣を狙う  護衛 {guard:,} を突破して指揮系統を崩す")
    console.print("  [0] キャンセル")
    while True:
        choice = _input("  選択 > ")
        if choice == "1":
            return "full_army"
        if choice == "2":
            return "headquarters"
        if choice == "0":
            return ""
        console.print("  [red]1か2を入力してください[/red]")


def select_tactic(tactics: list[tuple[str, str, str]]) -> str:
    console.print("\n[bold]【戦術選択】[/bold]")
    for i, (key, label, desc) in enumerate(tactics, 1):
        console.print(f"  [{i}] [bold]{label}[/bold]  {desc}")
    console.print("  [0] キャンセル")
    while True:
        choice = _input("  選択 > ")
        if choice == "0":
            return ""
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(tactics):
                return tactics[idx][0]
        except ValueError:
            pass
        console.print("  [red]番号を入力してください[/red]")


def show_battle_report(report: str, advisor_name: str = "軍師") -> None:
    console.print(Panel(
        f"[bold]{report}[/bold]",
        title=f"[bold yellow]{advisor_name}の報告[/bold yellow]",
        border_style="yellow",
    ))


def show_battle_phase(preview) -> None:
    console.print(Panel(
        preview.phase_report,
        title="[bold yellow]── 戦況報告 ──[/bold yellow]",
        border_style="yellow",
    ))


def get_battle_continue() -> str:
    console.print("[bold]【判断】[/bold]  [1]押し進む  [0]撤退する")
    while True:
        choice = _input("  選択 > ")
        if choice == "1":
            return "continue"
        if choice == "0":
            return "retreat"
        console.print("  [red]1か0を入力してください[/red]")


def show_combat_result(from_name: str, to_name: str, troops: int, result) -> None:
    if result.victory:
        if result.territory_captured:
            color, outcome = "green", "攻略"
        elif result.siege_started:
            color, outcome = "yellow", "野戦勝利→籠城へ"
        else:
            color, outcome = "green", "勝利"
    else:
        color, outcome = "red", "敗北"

    event_lines = "\n".join(f"【{ev.name}】{ev.description}" for ev in result.events)
    body = ""
    if event_lines:
        body += event_lines + "\n\n"
    body += (
        f"{result.narrative}\n\n"
        f"戦術:[cyan]{result.tactic}[/cyan]  "
        f"派遣:[white]{troops:,}[/white]  "
        f"我方損害:[red]{result.attacker_losses:,}[/red]  "
        f"敵方損害:[green]{result.defender_losses:,}[/green]"
    )
    console.print(Panel(
        body,
        title=f"[bold {color}]{from_name}→{to_name} [{outcome}][/bold {color}]",
        border_style=color,
    ))


def show_siege_status(state, siege) -> None:
    to_t = state.territories[siege.territory_id]
    defender_name = state.warlords[to_t.owner].name if to_t.owner != "neutral" else "中立"
    fort_str = "★" * to_t.fortification + "☆" * (5 - to_t.fortification)
    duration_str = f"{siege.duration}ヶ月目" if siege.duration > 0 else "開始直後"
    console.print(Panel(
        f"包囲軍:[cyan]{siege.attacker_troops:,}[/cyan]  "
        f"籠城兵:[red]{to_t.troops:,}[/red]（{defender_name}）  "
        f"城防衛:[yellow]{fort_str}[/yellow]  "
        f"包囲期間:[dim]{duration_str}[/dim]",
        title=f"[bold yellow]【籠城戦】{to_t.name}[/bold yellow]",
        border_style="yellow",
    ))


def select_siege_action(state, siege) -> str:
    to_t = state.territories[siege.territory_id]
    fortress_mult = 1.5 + to_t.fortification * 0.25
    ratio = siege.attacker_troops / max(to_t.troops * fortress_mult, 1)
    ratio_hint = f"攻城比:{ratio:.2f}"
    surrender_hint = f"包囲{siege.duration}ヶ月・包囲軍{siege.attacker_troops:,}vs籠城{to_t.troops:,}"

    console.print(f"\n[bold]【包囲方針】[/bold]  {ratio_hint}")
    console.print(f"  [1] [bold]強攻[/bold]    城門を破る。損害大・早期決着。")
    console.print(f"  [2] [bold]包囲継続[/bold]  兵糧を断つ。損害少・時間かかる。")
    console.print(f"  [3] [bold]降伏勧告[/bold]  {surrender_hint}")
    console.print(f"  [4] [bold]撤退[/bold]    包囲を解く。一部損害あり。")
    while True:
        choice = _input("  選択 > ")
        if choice == "1": return "assault"
        if choice == "2": return "surround"
        if choice == "3": return "surrender"
        if choice == "4": return "retreat"
        console.print("  [red]1〜4を入力してください[/red]")


def show_siege_result(result, territory_name: str) -> None:
    if result.territory_captured:
        color, title = "green", f"★ {territory_name} 攻略 ★"
    elif result.siege_continues:
        color, title = "yellow", f"{territory_name} 包囲継続"
    else:
        color, title = "dim", f"{territory_name} 包囲解除"

    body = result.narrative
    if result.attacker_losses or result.defender_losses:
        body += (
            f"\n\n我方損害:[red]{result.attacker_losses:,}[/red]  "
            f"敵方損害:[green]{result.defender_losses:,}[/green]"
        )
    console.print(Panel(body, title=f"[bold {color}]{title}[/bold {color}]", border_style=color))


# ── 軍師 ──────────────────────────────────────────────────────────

def get_advisor_question(is_continuation: bool = False) -> str:
    if not is_continuation:
        console.print("\n[bold]【軍師に相談】[/bold]")
        console.print("  [dim]例: 今川とどう戦う？　龍造寺に備えるには？[/dim]")
    return _input("  [dim]（空欄で評定に戻る）[/dim] > ").strip()


def show_diplomacy_offer(from_name: str, narration: str, rel_delta: int) -> str:
    """AIからプレイヤーへの使者を表示し、応答を返す（'accept'/'ignore'/'reject'）。"""
    console.print(Panel(
        f"[bold]{narration}[/bold]\n\n"
        f"  [Y] 受け入れる（関係値 [green]+{rel_delta}[/green]）\n"
        f"  [N] 無視する（変化なし）\n"
        f"  [R] 拒絶する（関係値 [red]-10[/red]）",
        title=f"[bold yellow]── 使者 ── {from_name}[/bold yellow]",
        border_style="yellow",
    ))
    while True:
        choice = _input("  応答 [Y/N/R] > ").lower()
        if choice in ("y", "yes", ""):
            console.print(f"  [green]使者を受け入れた。[/green]\n")
            return "accept"
        if choice in ("n", "no"):
            console.print(f"  [dim]使者を無視した。[/dim]\n")
            return "ignore"
        if choice in ("r",):
            console.print(f"  [red]使者を拒絶した。[/red]\n")
            return "reject"
        console.print("  [red]Y・N・R のいずれかを入力してください[/red]")


def show_advisor_advice(advice: str, advisor_name: str = "藤吉郎") -> None:
    console.print(Panel(
        advice,
        title=f"[bold cyan]軍師・{advisor_name}の進言[/bold cyan]",
        border_style="cyan",
    ))
    console.input("[dim]Enterで続ける...[/dim]")


# ── ログ・ステータス詳細（[5]用） ─────────────────────────────────

def show_detail(state: GameState) -> None:
    console.print(Rule("[bold cyan]── 詳細ステータス ──[/bold cyan]", style="cyan"))
    show_status(state)

    entries = state.log[-15:]
    if entries:
        console.print(Rule("[bold]── 直近の出来事 ──[/bold]", style="dim"))
        table = Table(box=box.SIMPLE, show_header=False)
        table.add_column("T", width=3, style="dim")
        table.add_column("内容")
        for e in entries:
            table.add_row(f"{e.turn}", e.text)
        console.print(table)

    console.input("[dim]Enterで戻る...[/dim]")


# ── メッセージ・AI行動 ────────────────────────────────────────────

def show_ai_actions(messages: list[str]) -> None:
    if not messages:
        return
    console.print(Rule("[dim]AI武将の行動[/dim]", style="dim"))
    for msg in messages:
        console.print(f"  [dim]{msg}[/dim]")


def show_message(msg: str, style: str = "white") -> None:
    console.print(f"  [{style}]{msg}[/{style}]")


def get_skip_target(state: GameState) -> int:
    """スキップ月数を選択して返す。0=キャンセル。"""
    m = state.month
    season = _SEASON[m]
    to_season = _months_to_next_season(m)
    next_s = _SEASON[1 if m + to_season > 12 else m + to_season]
    next_s_color = _SEASON_COLOR[next_s]

    console.print(f"\n[bold]【スキップ】[/bold]  {state.year}年{m}月（{season}）")
    console.print(f"  [1] 1ヶ月  [2] 2ヶ月  [3] 3ヶ月")
    console.print(
        f"  [[bold cyan]Q[/bold cyan]] 次季まで"
        f"（{to_season}ヶ月後・[{next_s_color}]{next_s}[/{next_s_color}]）"
        f"  [[bold cyan]H[/bold cyan]] 手入力"
    )
    console.print("  [0] キャンセル")
    while True:
        choice = _input("  > ").lower()
        if choice == "0":
            return 0
        if choice in ("1", "2", "3"):
            return int(choice)
        if choice == "q":
            return to_season
        if choice == "h":
            try:
                n = int(_input("  月数 (1-24) > "))
                if 1 <= n <= 24:
                    return n
            except ValueError:
                pass
            console.print("  [red]1〜24の数字を入力してください[/red]")
            continue
        console.print("  [red]0〜3、Q、Hを入力してください[/red]")


_WATCH_BORING = ("様子を見", "兵力増加", "内政を強化", "見合わせた", "兵を集")


def show_watch_month(year: int, month: int, messages: list[str]) -> None:
    """スキップ中の1ヶ月分をウォッチモードで1行表示する。"""
    season = _SEASON[month]
    s_color = _SEASON_COLOR[season]
    notable = [m for m in messages if not any(b in m for b in _WATCH_BORING)]
    header = f"  [dim]{year}年{month}月[{s_color}]({season})[/{s_color}][/dim]"
    if notable:
        summary = "  /  ".join(notable[:3])
        console.print(f"{header}  [dim]{summary}[/dim]")
    else:
        console.print(f"{header}  [dim]平穏[/dim]")


def ask_skip_interrupt(reason: str) -> str:
    """スキップ中断時に評定を開くか続行するかを問う。'stop'/'continue'を返す。"""
    console.print()
    console.print(Panel(
        f"[bold yellow]{reason}[/bold yellow]",
        title="[bold red]── 急報 ──[/bold red]",
        border_style="red",
    ))
    console.print("  [[bold red]1[/bold red]] 評定を開く（スキップ中断）")
    console.print("  [[bold dim]2[/bold dim]] このまま様子を見る（スキップ継続）")
    while True:
        choice = _input("  選択 > ")
        if choice == "1":
            return "stop"
        if choice == "2":
            return "continue"
        console.print("  [red]1か2を入力してください[/red]")


def show_salt_trade(state: "GameState") -> "Optional[tuple[str, float, int]]":
    """塩の交易UI。(territory_id, 売却量石, 収益貫) を返す。キャンセルはNone。"""
    from engine.economy import _bfs_tile_distance, km_to_coast_of, salt_price_at_km
    player = state.player
    stock = player.salt_stock
    stock_str = _koku_to_traditional(stock)
    console.print(f"\n[bold cyan]【塩の交易】[/bold cyan]  備蓄: [cyan]{stock_str}[/cyan]")

    bfs = _bfs_tile_distance(state)
    destinations: list[tuple[str, str, int, int]] = []  # (terr_id, label, km, price_文/升)
    for t in sorted(state.territories.values(), key=lambda x: x.name):
        if t.owner == state.player_id:
            continue
        km = km_to_coast_of(t, bfs)
        price = salt_price_at_km(km)
        owner_name = state.warlords[t.owner].name if t.owner in state.warlords else "中立"
        destinations.append((t.id, f"{t.name}（{owner_name}）", km, price))
    destinations.sort(key=lambda x: -x[3])  # 高値順

    console.print("\n  [bold]売先  城  距離  価格[/bold]")
    for i, (tid, label, km, price) in enumerate(destinations[:12], 1):
        # 石1石あたりの売価を算出（1石=100升）
        per_koku = price * 100 // 1000  # 貫/石
        console.print(f"  [{i:2d}] {label:<16}  ~{km:3d}km  {price}文/升（{per_koku}貫/石）")
    console.print("  [ 0] キャンセル")

    while True:
        choice = _input("  目的地番号 > ").strip()
        if choice == "0":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(destinations[:12]):
                break
        except ValueError:
            pass
        console.print("  [red]番号を入力してください[/red]")

    tid, label, km, price_per_sho = destinations[idx]
    per_koku_kan = price_per_sho * 100 / 1000  # 貫/石

    console.print(f"\n  {label}  {price_per_sho}文/升 ─ {per_koku_kan:.1f}貫/石")
    console.print(f"  備蓄: {stock_str}")
    console.print(f"  [1] 全量売る（{stock_str}）")
    console.print(f"  [2] 量を指定する")
    console.print(f"  [0] キャンセル")
    while True:
        choice = _input("  選択 > ").strip()
        if choice == "0":
            return None
        if choice == "1":
            amount = stock
            break
        if choice == "2":
            try:
                raw = _input(f"  売却量（石、最大{stock:.3f}）> ")
                amount = float(raw)
                if 0 < amount <= stock:
                    break
                console.print("  [red]有効な量を入力してください[/red]")
            except ValueError:
                console.print("  [red]数値を入力してください[/red]")
        else:
            console.print("  [red]0〜2を入力してください[/red]")

    revenue_kan = int(amount * 100 * price_per_sho / 1000)
    amount_str = _koku_to_traditional(amount)
    console.print(
        f"\n  [cyan]{label}[/cyan] へ [bold]{amount_str}[/bold] を売却。"
        f"  収益 [bold yellow]+{revenue_kan}貫[/bold yellow]"
    )
    return tid, amount, revenue_kan


def show_turn_end(state: "GameState") -> None:
    console.print(Rule(f"[dim]{state.year}年{state.month}月 終了[/dim]", style="dim"))
    console.input("[dim]Enter で次の月へ...[/dim]")


# ── ゲームエンド ──────────────────────────────────────────────────

def show_game_over(result: str, message: str = "") -> None:
    if result == "victory":
        body = f"[bold yellow]{message}[/bold yellow]" if message else "[bold yellow]勝利した！[/bold yellow]"
        console.print(Panel(
            body,
            title="[bold green]★ 勝利 ★[/bold green]",
            border_style="green",
        ))
    else:
        body = f"[bold]{message}[/bold]" if message else "[bold]滅亡した。歴史はまだあなたを必要としている。[/bold]"
        console.print(Panel(
            body,
            title="[bold red]× 敗北 ×[/bold red]",
            border_style="red",
        ))
    console.input("[dim]Enterで終了...[/dim]")
