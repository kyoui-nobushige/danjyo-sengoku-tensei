"""
戦国AI転生ストラテジー ─ メインエントリーポイント
"""
import os
import sys
import threading
import http.server
import webbrowser

_map_server = None
_MAP_PORT = 8765


def _start_map_server(directory: str) -> None:
    """map_adjacency.html 用のローカルHTTPサーバーをバックグラウンドで起動する。"""
    global _map_server
    if _map_server is not None:
        return
    os.chdir(directory)
    handler = http.server.SimpleHTTPRequestHandler
    handler.log_message = lambda *a: None  # アクセスログを抑制
    _map_server = http.server.HTTPServer(("127.0.0.1", _MAP_PORT), handler)
    t = threading.Thread(target=_map_server.serve_forever, daemon=True)
    t.start()

# ── LLM ファクトリ ────────────────────────────────────────────────

def create_llm():
    import config
    from ui.cli import choose_llm_provider
    provider = choose_llm_provider()
    config.LLM_PROVIDER = provider

    if provider == "anthropic":
        from llm.anthropic_llm import AnthropicLLM
        return AnthropicLLM()
    elif provider == "gemini":
        from llm.gemini_llm import GeminiLLM
        return GeminiLLM()
    elif provider == "lmstudio":
        from llm.lmstudio_llm import LMStudioLLM
        return LMStudioLLM()
    elif provider == "ollama":
        from llm.ollama_llm import OllamaLLM
        return OllamaLLM()
    else:
        raise ValueError(f"未知のLLMプロバイダ: {config.LLM_PROVIDER}")


# ── ゲームループ ──────────────────────────────────────────────────

def _handle_llm_error(e: Exception, cli) -> bool:
    """LLMエラーを処理し、継続可能なら True を返す。"""
    from llm.gemini_llm import GeminiQuotaError
    if isinstance(e, GeminiQuotaError):
        cli.show_message(f"\n[Geminiクォータ超過]\n{e}", style="bold red")
        cli.show_message("起動時にAnthropicを選択するか、明日再度お試しください。", style="yellow")
        return False
    # Gemini 503 等の一時的なサーバーエラー（クラス名で判定してimport不要にする）
    if type(e).__name__ == "ServerError":
        status = getattr(e, "status_code", "?")
        cli.show_message(f"[Gemini一時エラー {status}] AIの行動をスキップします。", style="dim yellow")
        return True
    raise e


def _check_skip_interrupt(state, prev_terrs: set, prev_rels: dict) -> tuple[bool, str]:
    """スキップを中断すべき条件を検出し (interrupted, reason) を返す。"""
    player_id = state.player_id

    # 領地喪失
    curr_terrs = {t.id for t in state.territories.values() if t.owner == player_id}
    if len(curr_terrs) < len(prev_terrs):
        lost_ids = prev_terrs - curr_terrs
        lost_names = [state.territories[tid].name for tid in lost_ids if tid in state.territories]
        names_str = "・".join(lost_names) if lost_names else "不明"
        return True, f"領地を{len(lost_ids)}城失いました！（{names_str}）"

    # 自領が包囲された
    for siege in state.sieges.values():
        t = state.territories.get(siege.territory_id)
        if t and t.owner == player_id:
            attacker = state.warlords.get(siege.attacker_id)
            name = attacker.name if attacker else "不明"
            return True, f"{t.name}が{name}に包囲されています！"

    # 関係値の急変（外交使者 or 敵対宣言）
    player = state.player
    for wid, w in state.warlords.items():
        if wid == player_id or w.is_defeated:
            continue
        prev = prev_rels.get(wid, 0)
        curr = player.relations.get(wid, 0)
        if curr - prev <= -25:
            return True, f"{w.name}との関係が急速に悪化しました（{prev:+d}→{curr:+d}）"
        if curr - prev >= 25:
            return True, f"{w.name}から外交の使者が参りました（{prev:+d}→{curr:+d}）"

    # 兵糧危機
    if player.food < 0:
        return True, "兵糧が尽きました！早急に手を打つ必要があります。"

    # 使者が来ている
    if state.pending_diplomacy:
        names = "・".join(d["from_name"] for d in state.pending_diplomacy)
        return True, f"使者が参っています（{names}）"

    return False, ""


def _run_player_siege(state, siege, cli) -> None:
    """プレイヤーが関わる籠城戦を1アクション処理する。"""
    from engine.combat import execute_siege
    territory_name = state.territories[siege.territory_id].name
    cli.show_siege_status(state, siege)
    action = cli.select_siege_action(state, siege)
    result = execute_siege(state, siege, action)
    cli.show_siege_result(result, territory_name)
    action_label = {"assault": "強攻", "surround": "包囲継続", "surrender": "降伏勧告", "retreat": "撤退"}.get(action, action)
    if result.territory_captured:
        log_msg = f"{territory_name}を攻略した！（籠城戦・{action_label}）"
    elif result.siege_continues:
        log_msg = f"{territory_name}を包囲中（{action_label}・{siege.duration}ヶ月目）"
    else:
        log_msg = f"{territory_name}の包囲を解除した（{action_label}）"
    state.add_log(state.player_id, log_msg)
    state.record_player_action(log_msg)


def main() -> None:
    from engine.game_state import load_scenario, save_game, write_map_state
    from engine.combat import preview_combat, execute_combat, retreat_combat, get_tactic_list
    from engine.diplomacy import apply_diplomacy_outcome, DiplomacyOutcome
    from engine.turn_manager import run_ai_turns
    from llm.warlord import (
        get_diplomacy_response, get_advisor_advice, chat_with_advisor,
        get_battle_report, ADVISOR_NAMES, WarlordDiplomacyResponse,
    )
    from llm.base import LLMMessage
    from ui import cli
    import config

    cli.show_title()

    scenario_map = {
        "1": ("桶狭間 (1560) ─ 東海", "okehazama_1560.json"),
        "2": ("九州三国志 (1560) ─ 肥前", "hizen_1560.json"),
    }
    cli.show_message("シナリオを選択してください:", "bold yellow")
    for key, (label, _) in scenario_map.items():
        cli.show_message(f"  {key}: {label}", "cyan")
    choice = cli.console.input("[dim]番号を入力 (Enterで1): [/dim]").strip() or "1"
    scenario_file = scenario_map.get(choice, scenario_map["1"])[1]
    scenario_path = os.path.join(
        os.path.dirname(__file__), "data", "scenarios", scenario_file
    )
    state = load_scenario(scenario_path)

    with open(scenario_path, encoding="utf-8") as f:
        import json
        scenario_meta = json.load(f)

    cli.show_scenario_intro(scenario_meta["title"], scenario_meta["description"])

    # ── プレイヤー選択 ────────────────────────────────────────────────
    playable = [
        w for w in state.warlords.values()
        if w.warlord_type in ("daimyo", "vassal")
    ]
    default_id = state.player_id
    cli.show_message("\nプレイヤーを選択してください:", "bold yellow")
    for i, w in enumerate(playable, 1):
        owned_terrs = [t for t in state.territories.values() if t.owner == w.id]
        total_stone = int(sum(t.koku for t in owned_terrs) * 10000)
        liege_note = (
            f"  従属: {state.warlords[w.liege].name}" if w.liege and w.liege in state.warlords else ""
        )
        default_mark = "  [bold green](推奨)[/bold green]" if w.id == default_id else ""
        cli.console.print(
            f"  [cyan]{i}[/cyan]: {w.name}（{w.faction_name}）  計{total_stone:,}石"
            f"{liege_note}{default_mark}"
        )
        terr_parts = [f"{t.name} {int(t.koku*10000):,}石" for t in owned_terrs[:3]]
        if len(owned_terrs) > 3:
            terr_parts.append(f"他{len(owned_terrs)-3}城")
        cli.console.print(f"     [dim]└ {' / '.join(terr_parts)}[/dim]")
    p_choice = cli.console.input("[dim]番号を入力 (Enterで推奨): [/dim]").strip()
    if p_choice.isdigit() and 1 <= int(p_choice) <= len(playable):
        chosen = playable[int(p_choice) - 1]
    else:
        chosen = state.warlords[default_id]
    if chosen.id != state.player_id:
        state.warlords[state.player_id].is_player = False
        state.player_id = chosen.id
        state.warlords[chosen.id].is_player = True

    # 転生者ヒント（シナリオJSONの start_hint から取得）
    hint = state.player.start_hint if hasattr(state.player, "start_hint") else ""
    if hint:
        cli.console.print("\n  [bold magenta]【転生者の記憶】[/bold magenta]")
        for line in hint.splitlines():
            prefix = "  [dim]" if line.startswith("（") else "  [magenta]"
            suffix = "[/dim]" if line.startswith("（") else "[/magenta]"
            cli.console.print(f"{prefix}{line}{suffix}")
        cli.console.print()
        cli.console.input("[dim]Enterで開始...[/dim]")
        cli.clear_screen()

    # ── LLM選択（ゲーム用・収集用） ──────────────────────────────────
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(__file__))
    from tools.fetch_warlord_history import missing_warlords, fetch_for_warlords

    scenario_warlord_ids = list(state.warlords.keys()) + list(state.external_powers.keys())
    missing = missing_warlords(scenario_warlord_ids)

    def _pick_llm(label: str, default_hint: str = ""):
        providers = {"1": "anthropic", "2": "gemini", "3": "lmstudio", "4": "ollama"}
        cli.show_message(f"\n【{label}】 1:Claude  2:Gemini  3:LMStudio  4:Ollama{default_hint}", "bold cyan")
        choice = cli.console.input("[dim]番号を入力 (Enterでデフォルト): [/dim]").strip()
        provider = providers.get(choice, config.LLM_PROVIDER)
        config.LLM_PROVIDER = provider
        if provider == "gemini":
            from llm.gemini_llm import GeminiLLM; return GeminiLLM()
        elif provider == "lmstudio":
            from llm.lmstudio_llm import LMStudioLLM; return LMStudioLLM()
        elif provider == "ollama":
            from llm.ollama_llm import OllamaLLM; return OllamaLLM()
        else:
            from llm.anthropic_llm import AnthropicLLM; return AnthropicLLM()

    if missing:
        cli.show_message(
            f"\n【史実データ未収集】{len(missing)}武将のWikipediaデータがありません。",
            "bold yellow"
        )
        cli.show_message("収集するとNPCが史実に基づいた動機で行動します（歴史の矯正力）。", "dim")
        ans = cli.console.input("[dim]今すぐ収集しますか？ (y/N): [/dim]").strip().lower()
        if ans == "y":
            fetch_llm = _pick_llm("史実収集用LLM", " ← ローカル推奨")
            fetch_for_warlords(fetch_llm, missing)

    llm = _pick_llm("ゲーム用LLM")

    while True:
        # ─ 終了判定 ──────────────────────────────────────────────
        ended, result = state.is_game_over()
        if ended:
            msg = state.win_message if result == "victory" else state.lose_message
            cli.show_game_over(result, msg)
            break

        # ─ 評定ループ（月内で複数行動可） ────────────────────────
        _skip_months = 0
        while True:
            # ─ 未応答の使者を処理 ─────────────────────────────────
            while state.pending_diplomacy:
                offer = state.pending_diplomacy.pop(0)
                response = cli.show_diplomacy_offer(
                    offer["from_name"], offer["narration"], offer["relation_delta"]
                )
                if response == "accept":
                    state.change_relation(state.player_id, offer["from_id"], offer["relation_delta"])
                    state.change_relation(offer["from_id"], state.player_id, offer["relation_delta"])
                elif response == "reject":
                    state.change_relation(state.player_id, offer["from_id"], -10)
                    state.change_relation(offer["from_id"], state.player_id, -10)
                # "ignore" は変化なし

            # ─ 状況表示 ──────────────────────────────────────────
            cli.show_turn_header(state)

            # ─ 継続中の籠城戦 ────────────────────────────────────
            for tid in list(state.sieges):
                siege = state.sieges.get(tid)
                if siege and siege.attacker_id == state.player_id:
                    _run_player_siege(state, siege, cli)

            # ─ プレイヤー行動 ─────────────────────────────────────
            action = cli.get_player_action()

            # 評定を終える
            if action == "e":
                break

            # スキップ
            if action == "n":
                _skip_months = cli.get_skip_target(state)
                if _skip_months > 0:
                    break
                continue

            # ─ LLM切替 ───────────────────────────────────────────
            if action == "l":
                llm = _pick_llm("LLM切替")
                cli.show_message(f"LLMを切り替えました。", "cyan")
                continue

            # ─ 地図表示 ───────────────────────────────────────────
            if action == "m":
                game_dir = os.path.dirname(os.path.abspath(__file__))
                map_json = os.path.join(game_dir, "map_state.json")
                write_map_state(state, map_json)
                _start_map_server(game_dir)
                webbrowser.open(f"http://127.0.0.1:{_MAP_PORT}/map_adjacency.html")
                cli.show_message("地図をブラウザで開きました。以降は自動更新されます。", "cyan")
                continue

            # ─ 保存 ──────────────────────────────────────────────
            if action == "s":
                save_path = os.path.join(os.path.dirname(__file__), "saves", "quicksave.json")
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                save_game(state, save_path)
                cli.show_message("セーブしました。", "green")
                cli.console.input("[dim]Enterで続ける...[/dim]")
                continue

            # ─ 状況確認 ──────────────────────────────────────────
            if action == "5":
                cli.show_detail(state)
                continue

            # ─ 軍師に相談（会話ループ） ───────────────────────────
            if action == "4":
                advisor_name = ADVISOR_NAMES.get(state.player_id, "軍師")
                _adv_history: list = []
                while True:
                    question = cli.get_advisor_question(bool(_adv_history))
                    if not question:
                        break
                    cli.show_message("考えています...", "dim")
                    try:
                        advice, _adv_history = chat_with_advisor(
                            llm, state, _adv_history, question
                        )
                    except Exception as e:
                        _handle_llm_error(e, cli)
                        break
                    cli.show_advisor_advice(advice, advisor_name)
                continue

            # ─ 内政 ──────────────────────────────────────────────
            if action == "2":
                from ui.cli import (
                    CAVALRY_BUY_PRICE, CAVALRY_SELL_PRICE, CAVALRY_RANCH_COST,
                    GUNNER_BUY_PRICE,  GUNNER_SELL_PRICE,  GUNNER_FORGE_COST,
                    MERCENARY_COST, COMMERCE_MAX,
                    commerce_invest_cost, select_territory_batch, confirm_batch,
                )
                player = state.player
                internal_action = cli.select_internal_action(player)
                if internal_action is None:
                    continue

                # 塩の交易
                if internal_action == "salt_trade":
                    result = cli.show_salt_trade(state)
                    if result is not None:
                        _tid, amount, revenue = result
                        player.salt_stock -= amount
                        player.treasury += revenue
                        dest_name = state.territories[_tid].name
                        from ui.cli import _koku_to_traditional
                        msg = (
                            f"{dest_name}へ塩{_koku_to_traditional(amount)}を売却。"
                            f"（+{revenue}貫  金庫:{player.treasury}貫  塩備蓄:{_koku_to_traditional(player.salt_stock)}）"
                        )
                        state.add_log(state.player_id, msg)
                        state.record_player_action(msg)
                        cli.show_message(msg, "cyan")
                    continue

                # 産業建設
                if internal_action == "industry":
                    territory_id = cli.select_internal_territory(state)
                    if territory_id is None:
                        continue
                    t = state.territories[territory_id]
                    from engine.industry import INDUSTRIES
                    player_inds = [i for terr in player.territories(state) for i in terr.industries]
                    ind_id = cli.select_industry(
                        t, player_inds,
                        llm=llm, state=state,
                        advisor_name=ADVISOR_NAMES.get(state.player_id, "軍師"),
                    )
                    if ind_id is None:
                        continue
                    ind = INDUSTRIES[ind_id]
                    if player.treasury < ind.cost:
                        cli.show_message(f"金庫不足。{ind.name}の建設には{ind.cost}貫必要。", "red")
                        continue
                    if t.under_construction:
                        cli.show_message(f"{t.name}はすでに建設中。完成を待て。", "yellow")
                        continue
                    player.treasury -= ind.cost
                    t.under_construction = ind_id
                    t.construction_turns_left = ind.turns_to_build
                    if ind.turns_to_build <= 1:
                        t.industries.append(ind_id)
                        t.under_construction = ""
                        t.construction_turns_left = 0
                        if ind_id == "rice_grid":
                            t.koku = round(t.koku * 1.2, 5)
                        cli.show_message(
                            f"[magenta]【転生者の知識】{t.name}に「{ind.name}」を建設した。（-{ind.cost}貫）[/magenta]",
                            "magenta"
                        )
                    else:
                        cli.show_message(
                            f"[magenta]【転生者の知識】{t.name}で「{ind.name}」の建設を開始。"
                            f"（-{ind.cost}貫  完成まで{ind.turns_to_build}ヶ月）[/magenta]",
                            "magenta"
                        )
                    continue

                # 領地選択が必要なアクション（単体）
                if internal_action in ("draft", "mercenary", "2"):
                    territory_id = cli.select_internal_territory(state)
                    if territory_id is None:
                        continue
                    t = state.territories[territory_id]

                    if internal_action == "draft":
                        draft_cap = max(1, int(t.koku * 100 * t.loyalty / 100))
                        current_gap = max(0, t.max_troops - t.troops)
                        gain = min(draft_cap, current_gap)
                        if gain <= 0:
                            msg = f"{t.name}はすでに兵力が上限か民忠が低すぎる。"
                        else:
                            t.troops += gain
                            t.loyalty = max(0, t.loyalty - 5)
                            msg = f"{t.name}で徴兵。（+{gain}兵  民忠{t.loyalty}%）"

                    elif internal_action == "mercenary":
                        if player.treasury < MERCENARY_COST:
                            msg = f"金庫不足。傭兵には{MERCENARY_COST}貫/兵必要。"
                        else:
                            n = cli.select_unit_amount("傭兵雇用", MERCENARY_COST, player.treasury)
                            if n > 0:
                                cost = n * MERCENARY_COST
                                t.troops += n
                                t.training = min(100, t.training + 5)
                                player.treasury -= cost
                                msg = f"{t.name}に傭兵{n}人。（-{cost}貫  練度{t.training}）"
                            else:
                                continue

                    elif internal_action == "2":
                        if t.fortification < 5:
                            t.fortification += 1
                            msg = f"{t.name}の城を強化した。（防衛{t.fortification}/5）"
                        else:
                            msg = f"{t.name}はすでに最高の防衛力を持つ。"

                    state.add_log(state.player_id, msg)
                    state.record_player_action(msg)
                    cli.show_message(msg, "cyan")
                    continue

                # 一括選択アクション（商業投資・新田開発）
                if internal_action in ("commerce_invest", "shinden"):
                    if internal_action == "commerce_invest":
                        _cost_fn    = commerce_invest_cost
                        _label_fn   = lambda t: f"商業Lv{t.commerce}"
                        _eligible   = lambda t: t.commerce < COMMERCE_MAX
                        _detail_fn  = lambda t: f"商業Lv{t.commerce}→{t.commerce+1}"
                    else:
                        _cost_fn    = lambda t: max(10, int(t.koku * 30))
                        _label_fn   = lambda t: f"石高{int(t.koku*10000)}石"
                        _eligible   = lambda _: True
                        _detail_fn  = lambda t: f"+{int(t.koku*0.0389*10000)}石"

                    territory_ids = select_territory_batch(state, _cost_fn, _label_fn, _eligible)
                    if not territory_ids:
                        continue

                    total_cost = sum(_cost_fn(state.territories[tid]) for tid in territory_ids)
                    if player.treasury < total_cost:
                        cli.show_message(
                            f"金庫不足。合計{total_cost}貫必要（金庫:{player.treasury}貫）", "red"
                        )
                        continue

                    if not confirm_batch(player, territory_ids, state, _cost_fn, _detail_fn):
                        continue

                    msgs = []
                    for tid in territory_ids:
                        t = state.territories[tid]
                        cost = _cost_fn(t)
                        if player.treasury < cost:
                            msgs.append(f"{t.name}:金庫不足")
                            continue
                        if internal_action == "commerce_invest":
                            old_lv = t.commerce
                            old_income = int(old_lv * 5 * t.loyalty / 100)
                            player.treasury -= cost
                            t.commerce += 1
                            new_income = int(t.commerce * 5 * t.loyalty / 100)
                            msgs.append(
                                f"{t.name} 商業Lv{old_lv}→{t.commerce}"
                                f"（-{cost}貫 月収+{new_income-old_income}貫）"
                            )
                        else:
                            gain_koku = round(t.koku * 0.0389, 5)
                            gain_stone = int(gain_koku * 10000)
                            t.koku = round(t.koku + gain_koku, 5)
                            player.treasury -= cost
                            msgs.append(
                                f"{t.name} 石高+{gain_stone}石→計{int(t.koku*10000)}石（-{cost}貫）"
                            )

                    combined_msg = " / ".join(msgs)
                    state.add_log(state.player_id, combined_msg)
                    state.record_player_action(combined_msg)
                    cli.show_message(combined_msg, "cyan")
                    continue

                # 騎馬・鉄砲の売買・生産
                msg = None
                if internal_action == "c_buy":
                    n = cli.select_unit_amount("騎馬購入", CAVALRY_BUY_PRICE, player.treasury)
                    if n > 0:
                        cost = n * CAVALRY_BUY_PRICE
                        player.cavalry += n
                        player.treasury -= cost
                        msg = f"騎馬を{n}騎購入した。（-{cost}貫  騎馬計{player.cavalry}騎）"

                elif internal_action == "c_sell":
                    n = cli.select_sell_amount("騎馬", player.cavalry, CAVALRY_SELL_PRICE)
                    if n > 0:
                        gain = n * CAVALRY_SELL_PRICE
                        player.cavalry -= n
                        player.treasury += gain
                        msg = f"騎馬を{n}騎売却した。（+{gain}貫  騎馬計{player.cavalry}騎）"

                elif internal_action == "c_ranch":
                    highland = [t for t in player.territories(state) if t.koku > 0 and getattr(t, "terrain", "plains") == "highland"]
                    if not highland:
                        cli.show_message("放牧には山間部の領地が必要です。", "yellow")
                        continue
                    n = cli.select_unit_amount("放牧（騎馬増産）", CAVALRY_RANCH_COST, player.treasury)
                    if n > 0:
                        cost = n * CAVALRY_RANCH_COST
                        player.cavalry += n
                        player.treasury -= cost
                        msg = f"放牧で騎馬を{n}騎増やした。（-{cost}貫  騎馬計{player.cavalry}騎）"

                elif internal_action == "g_buy":
                    from engine.industry import has_saltpeter
                    if has_saltpeter(player.territories(state)):
                        g_price = GUNNER_BUY_PRICE // 2
                        price_note = "（硝石自給5貫）"
                    elif player.liege in ("matsuura", "arima"):
                        g_price = 7
                        price_note = "（従属割引7貫）"
                    else:
                        g_price = GUNNER_BUY_PRICE
                        price_note = ""
                    n = cli.select_unit_amount(f"鉄砲購入{price_note}", g_price, player.treasury)
                    if n > 0:
                        cost = n * g_price
                        player.gunners += n
                        player.treasury -= cost
                        msg = f"鉄砲を{n}丁購入した。（-{cost}貫  鉄砲計{player.gunners}丁）"

                elif internal_action == "g_sell":
                    n = cli.select_sell_amount("鉄砲", player.gunners, GUNNER_SELL_PRICE)
                    if n > 0:
                        gain = n * GUNNER_SELL_PRICE
                        player.gunners -= n
                        player.treasury += gain
                        msg = f"鉄砲を{n}丁売却した。（+{gain}貫  鉄砲計{player.gunners}丁）"

                elif internal_action == "g_forge":
                    forge_terrs = [t for t in player.territories(state) if getattr(t, "has_foundry", False)]
                    if not forge_terrs:
                        cli.show_message("鉄砲増産には鍛冶場のある領地が必要です。", "yellow")
                        continue
                    n = cli.select_unit_amount("鉄砲増産", GUNNER_FORGE_COST, player.treasury)
                    if n > 0:
                        cost = n * GUNNER_FORGE_COST
                        player.gunners += n
                        player.treasury -= cost
                        msg = f"鉄砲を{n}丁増産した。（-{cost}貫  鉄砲計{player.gunners}丁）"

                if msg:
                    state.add_log(state.player_id, msg)
                    state.record_player_action(msg)
                    cli.show_message(msg, "cyan")

            # ─ 出陣 ──────────────────────────────────────────────
            elif action == "3":
                from_id = cli.select_attack_source(state)
                if from_id is None:
                    continue
                to_id = cli.select_attack_target(state, from_id)
                if to_id is None:
                    continue

                from_t = state.territories[from_id]
                troops = cli.select_troops_to_send(from_t.troops)

                attack_goal = cli.select_attack_goal(state, to_id)
                if not attack_goal:
                    continue

                advisor_name = ADVISOR_NAMES.get(state.player_id, "軍師")
                cli.show_message("軍師が状況を報告中...", "dim")
                try:
                    report1 = get_battle_report(
                        llm, state,
                        from_t.name, state.territories[to_id].name,
                        troops, state.territories[to_id].troops,
                        "出陣前"
                    )
                except Exception as e:
                    if not _handle_llm_error(e, cli):
                        continue
                    continue
                cli.show_battle_report(report1, advisor_name)

                tactic = cli.select_tactic(get_tactic_list())
                if not tactic:
                    continue

                preview = preview_combat(state, from_id, to_id, troops, tactic, attack_goal)
                cli.show_battle_phase(preview)

                try:
                    report2 = get_battle_report(
                        llm, state,
                        from_t.name, state.territories[to_id].name,
                        troops, preview.effective_def_troops,
                        f"交戦直前（戦力比{preview.ratio:.2f}）"
                    )
                except Exception as e:
                    if not _handle_llm_error(e, cli):
                        continue
                    continue
                cli.show_battle_report(report2, advisor_name)

                decision = cli.get_battle_continue()

                if decision == "retreat":
                    losses = retreat_combat(state, from_id, troops)
                    cli.show_message(f"撤退した。損害: {losses:,}", "yellow")
                    state.add_log(state.player_id,
                                  f"{state.territories[to_id].name}への攻撃を中止。撤退損害{losses}")
                else:
                    result_obj = execute_combat(state, from_id, to_id, troops, preview)
                    to_name = state.territories[to_id].name
                    cli.show_combat_result(from_t.name, to_name, troops, result_obj)
                    if result_obj.territory_captured:
                        outcome_label = "攻略"
                    elif result_obj.siege_started:
                        outcome_label = "野戦勝利→籠城"
                    else:
                        outcome_label = "失敗"
                    log_msg = (
                        f"{to_name}への攻撃[{result_obj.tactic}]: "
                        f"{outcome_label} （我方損害{result_obj.attacker_losses}）"
                    )
                    state.add_log(state.player_id, log_msg)
                    state.record_player_action(log_msg)

                    if result_obj.siege_started:
                        siege = state.sieges.get(to_id)
                        if siege:
                            _run_player_siege(state, siege, cli)

            # ─ 外交 ──────────────────────────────────────────────
            elif action == "1":
                target_id = cli.select_diplomacy_target(state)
                if target_id is None:
                    continue

                if target_id.startswith("ext:"):
                    ep_id = target_id[4:]
                    ep = state.external_powers.get(ep_id)
                    if not ep:
                        continue

                    action_pair = cli.select_external_diplomacy_action(ep)
                    if action_pair is None:
                        continue

                    action_key, action_label = action_pair
                    conversation: list[LLMMessage] = [
                        LLMMessage("user", f"【申し入れ】{action_label}を申し上げます。")
                    ]

                    cli.show_message("交渉中...", "dim")

                    response = None
                    for exchange_i in range(config.MAX_DIPLOMACY_EXCHANGES):
                        try:
                            from llm.warlord import get_external_power_response
                            response = get_external_power_response(
                                llm, state, ep, action_label, conversation
                            )
                        except Exception as e:
                            if not _handle_llm_error(e, cli):
                                break
                            break

                        cli.show_warlord_dialogue(
                            ep.name,
                            response.dialogue,
                            response.thought,
                            response.response_type,
                        )

                        if exchange_i == config.MAX_DIPLOMACY_EXCHANGES - 1:
                            break
                        if response.response_type in ("accept", "reject"):
                            break

                        follow_up = cli.get_diplomacy_follow_up()
                        if follow_up == "end":
                            break

                        conversation.append(LLMMessage("assistant", response.dialogue))
                        conversation.append(LLMMessage("user", follow_up))

                    if response:
                        ep.relation = max(-100, min(100, ep.relation + response.relation_delta))
                        log_msg = (
                            f"{ep.name}と外交（{action_label}）。"
                            f"関係値: {ep.relation:+d}"
                        )
                        state.add_log(state.player_id, log_msg)
                        state.record_player_action(log_msg)
                        cli.show_message(
                            f"外交終了。{ep.name}との関係値: {ep.relation:+d}", "magenta"
                        )
                    continue

                action_pair = cli.select_diplomacy_action()
                if action_pair is None:
                    continue

                action_key, action_label = action_pair
                target_warlord = state.warlords[target_id]

                conversation: list[LLMMessage] = [
                    LLMMessage("user", f"【申し入れ】{action_label}を提案します。")
                ]

                cli.show_message("交渉中...", "dim")

                for exchange_i in range(config.MAX_DIPLOMACY_EXCHANGES):
                    try:
                        response: WarlordDiplomacyResponse = get_diplomacy_response(
                            llm, state, target_warlord, action_label, conversation
                        )
                    except Exception as e:
                        if not _handle_llm_error(e, cli):
                            break
                        break
                    cli.show_warlord_dialogue(
                        target_warlord.name,
                        response.dialogue,
                        response.thought,
                        response.response_type,
                    )

                    if exchange_i == config.MAX_DIPLOMACY_EXCHANGES - 1:
                        break
                    if response.response_type in ("accept", "reject"):
                        break

                    follow_up = cli.get_diplomacy_follow_up()
                    if follow_up == "end":
                        break

                    conversation.append(LLMMessage("assistant", response.dialogue))
                    conversation.append(LLMMessage("user", follow_up))

                outcome = DiplomacyOutcome(
                    action_type=action_key,
                    warlord_response=response.response_type,
                    dialogue=response.dialogue,
                    thought=response.thought,
                    relation_delta=response.relation_delta,
                    narrative="",
                )
                apply_diplomacy_outcome(state, state.player_id, target_id, outcome)
                val_now = state.player.relations.get(target_id, 0)
                cli.show_message(
                    f"外交終了。{target_warlord.name}との関係値: {val_now:+d}",
                    "cyan",
                )
                state.record_player_action(f"{target_warlord.name}と外交（{action_label}）")

        # ─ 月処理ループ（通常1回 / スキップ時N回） ─────────────────
        months_to_run = _skip_months if _skip_months > 0 else 1
        is_watching = _skip_months > 0
        outer_game_ended = False

        if is_watching:
            cli.console.print()  # ウォッチモード開始の余白

        for month_i in range(months_to_run):
            old_year, old_month = state.year, state.month
            prev_terrs = {t.id for t in state.territories.values() if t.owner == state.player_id}
            prev_rels = dict(state.player.relations)

            # AI行動
            try:
                ai_msgs = run_ai_turns(state, llm)
            except Exception as e:
                if not _handle_llm_error(e, cli):
                    ai_msgs = []
                else:
                    ai_msgs = []

            # 月進行（advance_turn 前後の差分で収入を正確に表示）
            treasury_before = state.player.treasury
            state.advance_turn()
            ev_msgs = state.process_events()

            if not is_watching:
                # ─ 通常表示 ──────────────────────────────────────
                cli.show_ai_actions(ai_msgs)
                inc = state._calc_income(state.player_id)  # 兵糧表示用（今月の収支）
                net = inc["food_net"]
                sign = "+" if net >= 0 else ""
                style = "green" if net >= 0 else "yellow"
                cli.show_message(
                    f"【兵糧】入{inc['food_income']}石 - 消{inc['food_consumption']}石"
                    f" = {sign}{net}石  （備蓄: {state.player.food}石）",
                    style
                )
                gold_earned = state.player.treasury - treasury_before
                if gold_earned > 0:
                    cli.show_message(
                        f"【月収入】+{gold_earned}貫  （金庫: {state.player.treasury}貫）",
                        "yellow"
                    )
                if state.player.salt_stock >= 0.001:
                    from ui.cli import _koku_to_traditional
                    cli.show_message(
                        f"【塩備蓄】{_koku_to_traditional(state.player.salt_stock)}  "
                        f"[dim](tで交易)[/dim]",
                        "cyan"
                    )
                for msg in ev_msgs:
                    cli.show_message(f"\n【歴史イベント】{msg}", "bold yellow")
                cli.show_turn_end(state)
            else:
                # ─ ウォッチモード表示 ─────────────────────────────
                all_this = ai_msgs + [f"【歴史イベント】{m}" for m in ev_msgs]
                cli.show_watch_month(old_year, old_month, all_this)

                # 中断チェック（最終月以外）
                is_last = (month_i == months_to_run - 1)
                if not is_last:
                    interrupted, reason = _check_skip_interrupt(state, prev_terrs, prev_rels)
                    if interrupted:
                        if cli.ask_skip_interrupt(reason) == "stop":
                            break  # 評定へ戻る

            # ゲーム終了チェック
            ended, result = state.is_game_over()
            if ended:
                msg = state.win_message if result == "victory" else state.lose_message
                cli.show_game_over(result, msg)
                outer_game_ended = True
                break

        if outer_game_ended:
            break

        # 地図サーバーが起動中なら状態を自動更新
        if _map_server is not None:
            game_dir = os.path.dirname(os.path.abspath(__file__))
            write_map_state(state, os.path.join(game_dir, "map_state.json"))


if __name__ == "__main__":
    main()
