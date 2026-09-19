"""
Russian Roulette Match Status and Event Renderer for AstrBot.
Formats game views, ASCII tactical boards, player statuses, and drama events into chat messages.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def format_weather(weather: str) -> str:
    mapping = {
        "clear": "☀️ 晴朗",
        "rain": "🌧️ 暴雨 (水洼扩增)",
        "wind": "💨 狂风 (弹道漂移)",
        "extreme_cold": "❄️ 极寒 (水面结冰)",
    }
    return mapping.get(weather.lower(), f"🌤️ {weather}")


def format_elimination_cause(cause: str) -> str:
    mapping = {
        "shot": "💥 被左轮实弹击毙",
        "elbow_duel": "🥊 拼肘决斗战败",
        "mine": "💣 触碰地雷炸碎",
        "drowned": "🌊 溺水身亡",
        "suicide": "☠️ 扣动扳机自戕",
        "collision": "🧱 剧烈撞墙身亡",
    }
    return mapping.get(cause.lower(), f"💀 {cause}")


def render_help() -> str:
    return (
        "🔫 【俄罗斯轮盘】群聊主持人指令指南 🔫\n"
        "──────────────────────\n"
        "🎮 房间管理：\n"
        "  • /rr 房间              - 查看当前所有对局房间\n"
        "  • /rr 创建 [名称] [Bot数] - 创建对局房间 (默认3个Bot)\n"
        "  • /rr 开始 [房间号]      - 装填弹巢，正式开局\n"
        "  • /rr 战况 [房间号]      - 查看当前棋盘、玩家血量与事件\n"
        "  • /rr 解散 [房间号]      - 强制结束并解散房间\n"
        "\n"
        "🎯 对局行动 (当前轮到你的回合时)：\n"
        "  • /rr 开火 [房间号] <方向> - 向方向扣动扳机 (上/下/左/右)\n"
        "  • /rr 移动 [房间号] <方向> - 在地图上移动一格 (上/下/左/右)\n"
        "  • /rr 等待 [房间号]       - 放弃本回合行动\n"
        "  • /rr 自戕 [房间号]       - 绝望认输，饮弹自戕\n"
        "  • /rr 步进 [房间号]       - 轮到Bot时，推进Bot走一步\n"
        "\n"
        "⚙️ 系统查询：\n"
        "  • /rr 状态              - 检查轮盘游戏后端连接与配置\n"
        "  • /rr 规则              - 查看权威规则与特殊地形硬度\n"
        "──────────────────────\n"
        "💡 提示：所有子指令均支持中文前缀，如 `/轮盘 开火 上`"
    )


def render_rooms_summary(rooms: List[Dict[str, Any]]) -> str:
    if not rooms:
        return "🎲 当前大厅内暂无活跃房间。使用 `/rr 创建` 开启一局新挑战！"

    lines = [f"📋 【当前轮盘对局列表】(共 {len(rooms)} 间)：", "──────────────────────"]
    phase_icons = {
        "waiting": "⏳ 等待中",
        "in_game": "⚔️ 激战中",
        "finished": "🏁 已终局",
        "dissolved": "🚫 已解散",
    }
    for r in rooms:
        rid = r.get("id", "?????")
        name = r.get("name", "未命名房间")
        phase = r.get("phase", "unknown")
        phase_str = phase_icons.get(phase, phase)
        alive = r.get("alive_player_count", r.get("member_count", 0))
        total = r.get("member_count", 0)
        lines.append(f"• 房间 [{rid}]「{name}」| 阶段: {phase_str} | 存活: {alive}/{total}")
    lines.append("──────────────────────")
    lines.append("输入 `/rr 战况 [房间号]` 查看具体房间全知视角")
    return "\n".join(lines)


def render_board(map_size: int, cells: List[Dict[str, Any]], players: List[Dict[str, Any]]) -> str:
    """Renders a compact visual ASCII/Emoji grid for chat."""
    if not cells or map_size <= 0:
        return ""

    # Build coordinate occupant map
    player_positions: Dict[tuple[int, int], str] = {}
    for idx, p in enumerate(players, start=1):
        if p.get("status") == "alive" and p.get("position"):
            pos = p["position"]
            player_positions[(pos["x"], pos["y"])] = f"P{idx}"

    terrain_symbols = {
        "plain": "⬜",
        "wall": "🧱",
        "water": "🌊",
        "crate": "📦",
        "frozen_water": "🧊",
        "mud": "🟫",
    }

    grid: List[List[str]] = [["⬜" for _ in range(map_size)] for _ in range(map_size)]
    for cell in cells:
        pos = cell.get("position", {})
        x, y = pos.get("x", 0), pos.get("y", 0)
        if 0 <= x < map_size and 0 <= y < map_size:
            if (x, y) in player_positions:
                grid[y][x] = f"👤"
            else:
                t = cell.get("terrain", "plain")
                grid[y][x] = terrain_symbols.get(t, "▫️")

    board_lines = []
    board_lines.append("🗺️ 【战术地图】")
    for row in grid:
        board_lines.append(" ".join(row))
    return "\n".join(board_lines)


def render_game_view(
    room_view: Dict[str, Any],
    show_visual_board: bool = True,
    max_events: int = 5,
) -> str:
    """Renders omniscient referee snapshot into formatted battle status."""
    room_id = room_view.get("id", "?????")
    room_name = room_view.get("name", "未命名房间")
    phase = room_view.get("phase", "waiting")
    game = room_view.get("game")

    if phase == "waiting" or not game:
        members = room_view.get("members", [])
        lines = [
            f"🏠 房间 [{room_id}]「{room_name}」 (⏳ 待开局)",
            "──────────────────────",
            f"已入座席位 ({len(members)} 人)：",
        ]
        for idx, m in enumerate(members, start=1):
            role_icon = "🤖" if m.get("is_bot") else "👤"
            host_tag = " [👑房主]" if m.get("is_host") else ""
            lines.append(f"  {idx}. {role_icon} {m.get('player_name', 'Player')}{host_tag}")
        lines.append("──────────────────────")
        lines.append(f"输入 `/rr 开始 {room_id}` 即可装填转轮、开启对决！")
        return "\n".join(lines)

    # Active match rendering
    round_no = game.get("round", 1)
    weather = format_weather(game.get("weather", "clear"))
    status = game.get("status", "running")
    alive_count = game.get("alive_player_count", 0)
    current_pid = game.get("current_player_id")

    lines = [
        f"⚔️ 房间 [{room_id}]「{room_name}」 战报",
        f"第 {round_no} 回合 | 天气: {weather} | 存活: {alive_count} 人",
        "──────────────────────",
    ]

    # Players status
    players = game.get("players", [])
    current_player_name = "无"
    lines.append("👥 【玩家席位】")
    for idx, p in enumerate(players, start=1):
        pid = p.get("id", "")
        pname = p.get("name", f"Player_{idx}")
        pkind = "🤖" if p.get("kind") == "bot" else "👤"
        pstatus = p.get("status", "alive")

        if pid == current_pid:
            current_player_name = pname
            turn_mark = " 👉 [当前行动]"
        else:
            turn_mark = ""

        if pstatus == "alive":
            shield_icon = "🛡️ [盾牌完好]" if p.get("has_shield") else "⛔ [无盾]"
            pos = p.get("position")
            pos_str = f"({pos['x']},{pos['y']})" if pos else "(未知)"
            lines.append(f"  {idx}. {pkind} {pname} | 💚 存活 | 坐标 {pos_str} | {shield_icon}{turn_mark}")
        else:
            cause_detail = ""
            if isinstance(pstatus, dict) and "eliminated" in pstatus:
                cause_detail = format_elimination_cause(pstatus["eliminated"])
            lines.append(f"  {idx}. {pkind} {pname} | 💀 出局 {cause_detail}")

    lines.append("──────────────────────")

    # Current turn prompt
    if status == "running":
        lines.append(f"🌟 当前轮次：{current_player_name}")
        lines.append("提示：轮到真人的可使用 `/rr 开火` 或 `/rr 移动`；轮到Bot的可输入 `/rr 步进`")
    elif status == "finished":
        winner = "无人幸存 (平局)"
        for p in players:
            if p.get("status") == "alive":
                winner = f"🎉 胜者：{p.get('name')}"
                break
        lines.append(f"🏁 【对局结束】 {winner}")

    # Visual tactical board
    if show_visual_board and "map_size" in game and "cells" in game:
        board_str = render_board(int(game["map_size"]), game["cells"], players)
        if board_str:
            lines.append("──────────────────────")
            lines.append(board_str)

    # Recent drama records
    records = game.get("records", [])
    if records:
        recent = records[-max_events:]
        lines.append("──────────────────────")
        lines.append("📜 【最新战况流水】")
        for rec in reversed(recent):
            lines.append(f"  • {format_record(rec)}")

    return "\n".join(lines)


def format_record(record: Dict[str, Any]) -> str:
    """Formats a single GameRecord entry into human-readable chat text."""
    category = record.get("category") or record.get("type", "unknown")
    if category == "action":
        actor = record.get("actor_id") or record.get("actor", "玩家")
        cmd = record.get("command", {})
        if isinstance(cmd, dict):
            ctype = cmd.get("type", "")
            cdir = cmd.get("direction", "")
            dir_zh = {"up": "上", "down": "下", "left": "左", "right": "右"}.get(cdir, cdir)
            if ctype == "move":
                return f"🚶 Player {actor} 向【{dir_zh}】移动了一格"
            elif ctype == "shoot":
                return f"🔫 Player {actor} 向【{dir_zh}】扣动了扳机！"
            elif ctype == "wait":
                return f"⏳ Player {actor} 选择按兵不动，跳过回合"
            elif ctype == "suicide":
                return f"☠️ Player {actor} 扣动扳机饮弹自戕！"
        desc = record.get("action_desc", "执行了行动")
        return f"[{actor}] {desc}"
    elif category == "event":
        event = record.get("event", {})
        etype = event.get("type", "")
        if etype == "moved":
            actor = event.get("actor_id", "?")
            f = event.get("from", {})
            t = event.get("to", {})
            return f"🚶 Player {actor} 从 ({f.get('x')},{f.get('y')}) 移动到 ({t.get('x')},{t.get('y')})"
        elif etype == "move_blocked":
            actor = event.get("actor_id", "?")
            reason = event.get("reason", "")
            reason_map = {"boundary": "出界撞墙", "wall": "撞击水泥墙", "crate": "被木箱阻挡"}
            return f"🚫 Player {actor} 移动受阻 ({reason_map.get(reason, reason)})"
        elif etype == "elbow_duel":
            a = event.get("attacker_id")
            d = event.get("defender_id")
            w = event.get("winner_id")
            return f"🥊 狭路相逢拼肘决斗！Player {a} vs Player {d} -> Player {w} 胜出！"
        elif etype == "empty_chamber":
            actor = event.get("actor_id", "?")
            forced = " [必中保底轮次]" if event.get("forced") else ""
            return f"💨 咔哒！Player {actor} 扣动扳机，是空弹！{forced}"
        elif etype == "shot_missed":
            actor = event.get("actor_id", "?")
            return f"💥 砰！Player {actor} 击发实弹，未命中任何目标脱靶！"
        elif etype == "shield_consumed":
            p = event.get("player_id", "?")
            return f"🛡️ 咔嚓！Player {p} 的防弹护盾碎裂，抵挡了致命伤害！"
        elif etype == "player_eliminated":
            p = event.get("player_id", "?")
            cause = format_elimination_cause(event.get("cause", ""))
            by = event.get("by_player_id")
            by_str = f"（由 Player {by} 击杀）" if by else ""
            return f"💀 Player {p} 出局！{cause} {by_str}"
        elif etype == "terrain_damaged":
            return "💥 地形破损！掩体被强力贯穿！"
        elif etype == "terrain_changed":
            to_t = event.get("to", "")
            return f"🗺️ 地形演变: 变为 {to_t}"
        return f"⚡ 事件: {etype}"
    elif category == "turn":
        p = record.get("player_id", "?")
        r = record.get("round", 1)
        return f"🔄 第 {r} 回合：轮到 Player {p} 行动"
    elif category == "notification":
        notif = record.get("notification", {})
        if isinstance(notif, dict):
            ntype = notif.get("type", "")
            if ntype == "match_started":
                return f"📢 裁判哨响：对决正式开打！(种子: {notif.get('seed')})"
            elif ntype == "match_finished":
                w = notif.get("winner_id")
                return f"🏁 裁判哨响：对决落幕！胜者: Player {w}" if w else "🏁 裁判哨响：同归于尽，无人幸存！"
        return f"📢 {record.get('message', notif)}"
    return f"ℹ️ {record}"


def render_step_result(step_res: Dict[str, Any]) -> str:
    """Renders action or step outcome."""
    action_desc = step_res.get("action_desc", "行动完成")
    is_finished = step_res.get("is_match_finished", False)
    winner = step_res.get("winner_player_id")

    lines = [f"🎯 【裁判裁定】{action_desc}"]
    if is_finished:
        winner_text = f"🏆 获胜者：Player {winner}" if winner else "💀 全部出局，同归于尽！"
        lines.append(f"\n🏁 对局宣告结束！{winner_text}")
    return "\n".join(lines)
