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


def render_help(topic: Optional[str] = None) -> str:
    """Renders global or topic-specific command manual."""
    if topic:
        t = topic.lower().strip()
        if t in ("create", "创建", "建房"):
            return (
                "🎮 【指令详情：/rr 创建】\n"
                "──────────────────────\n"
                "• 语法：`/rr 创建 [名称] [Bot数] [密码]` 或 键值形式\n"
                "• 示例：\n"
                "  - `/rr 创建`                    (使用默认名称与3个Bot)\n"
                "  - `/rr 创建 死亡峡谷 4`          (名称: 死亡峡谷, 4个Bot)\n"
                "  - `/rr 创建 决斗房 3 123456`     (设置房间密码为 123456)\n"
                "  - `/rr 创建 name=试炼场 bots=4`  (键值对配置参数)\n"
                "• 说明：创建后自动与当前群聊会话绑定，后续操作无需反复键入房间号。"
            )
        elif t in ("start", "开始", "开局"):
            return (
                "🎮 【指令详情：/rr 开始】\n"
                "──────────────────────\n"
                "• 语法：`/rr 开始 [房间号] [随机种子]`\n"
                "• 示例：\n"
                "  - `/rr 开始`              (启动当前群聊绑定的房间)\n"
                "  - `/rr 开始 FQZBQ`        (启动指定房间)\n"
                "  - `/rr 开始 123456`       (使用固定随机种子开局，用于复现与测试)\n"
                "  - `/rr 开始 FQZBQ 123456` (指定房间号和固定随机种子)\n"
                "• 说明：正式开局要求房间成员（真人+Bot）在 3 至 6 人之间。"
            )
        elif t in ("step", "步进", "走步", "bot步进"):
            return (
                "🎮 【指令详情：/rr 步进】\n"
                "──────────────────────\n"
                "• 语法：`/rr 步进 [房间号] [步数]` 或 `/rr 步进 自动`\n"
                "• 示例：\n"
                "  - `/rr 步进`              (当前行动 Bot 走一步)\n"
                "  - `/rr 步进 3`            (连续推进 3 步决策)\n"
                "  - `/rr 步进 自动`         (自动快进推进直到终局或对局结束，上限5步)\n"
                "  - `/rr 步进 FQZBQ 5`      (指定房间连续推进 5 步)\n"
                "• 说明：仅在轮到 Bot 行动时生效；若轮到真人，请使用移动或开火指令。"
            )
        elif t in ("shoot", "开火", "开枪", "射击", "fire"):
            return (
                "🎯 【指令详情：/rr 开火】\n"
                "──────────────────────\n"
                "• 语法：`/rr 开火 [房间号] <方向>` 或 `/rr 开火 <方向>`\n"
                "• 方向参数支持多种输入：\n"
                "  - 中文方向：上、下、左、右、北、南、西、东\n"
                "  - 英文键位：w(上)、s(下)、a(左)、d(右)、up/down/left/right\n"
                "  - 键盘数字：8(上)、2(下)、4(左)、6(右)\n"
                "  - 箭头符号：↑、↓、←、→\n"
                "• 示例：`/rr 开火 上`、`/rr 开火 d`、`/rr 开火 6`\n"
                "• 说明：向指定方向击发左轮手枪，实弹击中实体目标造成致命伤害或破坏掩体。"
            )
        elif t in ("move", "移动", "走", "走位"):
            return (
                "🚶 【指令详情：/rr 移动】\n"
                "──────────────────────\n"
                "• 语法：`/rr 移动 [房间号] <方向>` 或直接输入方向快捷键\n"
                "• 快捷走位：在群里直接发送 `/rr 上`、`/rr 右`、`/rr w`、`/rr 6` 即可快速移动！\n"
                "• 示例：`/rr 移动 上`、`/rr 移动 东`、`/rr 移动 a`\n"
                "• 说明：向目标格子移动一步，遭遇墙壁/出界会受阻，进入水洼会延迟涉水。"
            )
        elif t in ("bot", "机器人", "席位", "加bot", "减bot"):
            return (
                "🤖 【指令详情：/rr bot 席位管理】\n"
                "──────────────────────\n"
                "• 语法：\n"
                "  - `/rr bot 加 [房间号]`   (等待阶段增加一个 Bot)\n"
                "  - `/rr bot 减 [房间号]`   (等待阶段移除一个 Bot)\n"
                "  - `/rr bot 4 [房间号]`    (快速调整等待房间 Bot 数为 4 个)\n"
                "• 说明：仅可在开局前（⏳ 等待中）调整 Bot 席位。"
            )
        elif t in ("view", "战况", "对局", "info"):
            return (
                "📊 【指令详情：/rr 战况】\n"
                "──────────────────────\n"
                "• 语法：`/rr 战况 [房间号] [条数/模式]`\n"
                "• 示例：\n"
                "  - `/rr 战况`              (查看当前绑定房间战报)\n"
                "  - `/rr 战况 10`           (查看战报并展示最新 10 条事件记录)\n"
                "  - `/rr 战况 简略`         (仅查看玩家存活与血量，不打印大地图)\n"
                "  - `/rr 战况 详细`         (包含完整 Emoji 战术棋盘与战况流水)"
            )
        elif t in ("bind", "绑定", "切房", "解绑"):
            return (
                "🔗 【指令详情：/rr 会话绑定】\n"
                "──────────────────────\n"
                "• 语法：\n"
                "  - `/rr 绑定 <房间号>`     (将当前群聊切换绑定到指定房间)\n"
                "  - `/rr 解绑`              (清除当前群聊的房间记忆)"
            )

    return (
        "🔫 【俄罗斯轮盘】群聊主持人指令指南 🔫\n"
        "──────────────────────\n"
        "🎮 房间管理：\n"
        "  • /rr 房间 [状态]        - 查看对局列表 (支持: 等待/进行/全部)\n"
        "  • /rr 创建 [名称] [Bot] [密码] - 创建对局房间 (默认3个Bot)\n"
        "  • /rr bot 加/减/<数量>   - 在等待阶段调整 Bot 席位\n"
        "  • /rr 开始 [房间] [种子] - 装填弹巢开局 (支持固定随机种子)\n"
        "  • /rr 战况 [房间] [条数] - 查看棋盘、血量与流水 (支持简略/详细)\n"
        "  • /rr 绑定 <房间号>      - 切换当前群聊绑定的活跃房间\n"
        "  • /rr 解散 [房间号]      - 强制结束并解散房间\n"
        "\n"
        "🎯 对局行动 (当前轮到你的回合时)：\n"
        "  • /rr 开火 [房间] <方向> - 扣动扳机 (支持: 上/下/左/右/w/s/a/d/8/2/4/6)\n"
        "  • /rr 移动 [房间] <方向> - 战术移动 (快捷走位: 直接发 `/rr 上`、`/rr 右`)\n"
        "  • /rr 等待 [房间号]      - 放弃本回合行动\n"
        "  • /rr 自戕 [房间号]      - 绝望认输，饮弹自戕\n"
        "  • /rr 步进 [步数/自动]   - 轮到Bot时推进 (支持多步: `/rr 步进 3` 或 `自动`)\n"
        "\n"
        "⚙️ 系统查询：\n"
        "  • /rr 状态              - 检查轮盘游戏后端连接与当前活跃房间\n"
        "  • /rr 规则              - 查看权威规则与特殊地形硬度\n"
        "  • /rr 帮助 <子指令>      - 查看指定指令的详细参数说明\n"
        "──────────────────────\n"
        "💡 提示：所有子指令均支持中文前缀，如 `/轮盘 开火 右`"
    )


def render_rooms_summary(rooms: List[Dict[str, Any]], filter_phase: Optional[str] = None) -> str:
    filter_zh = {
        "waiting": "⏳ 等待中",
        "in_game": "⚔️ 激战中",
        "finished": "🏁 已终局",
    }.get(filter_phase or "", "")
    title_suffix = f" [{filter_zh}]" if filter_zh else ""

    if not rooms:
        return f"🎲 当前大厅内暂无活跃房间{title_suffix}。使用 `/rr 创建` 开启一局新挑战！"

    lines = [f"📋 【当前轮盘对局列表】{title_suffix}(共 {len(rooms)} 间)：", "──────────────────────"]
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
