"""
Russian Roulette AstrBot Plugin - Host and presentation layer for QQ users.
Interacts with the authoritative Russian Roulette backend via MCP.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

try:
    from astrbot.api import AstrBotConfig, logger
    from astrbot.api.event import AstrMessageEvent, filter
    from astrbot.api.star import Context, Star
except ImportError:
    # Standalone mock fallback for local unit testing outside AstrBot environment
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("astrbot.plugin.russian_roulette")

    class Star:  # type: ignore
        def __init__(self, context: Any):
            self.context = context

    class Context:  # type: ignore
        pass

    class AstrBotConfig(dict):  # type: ignore
        pass

    class AstrMessageEvent:  # type: ignore
        def __init__(self, sender_id: str = "mock_user", message_str: str = ""):
            self.sender_id = sender_id
            self.message_str = message_str
            self.unified_msg_origin = "mock_session"

        def get_sender_id(self) -> str:
            return self.sender_id

        def get_sender_name(self) -> str:
            return f"User_{self.sender_id}"

        def get_message_str(self) -> str:
            return self.message_str

        def plain_result(self, text: str) -> str:
            return text

    class filter:  # type: ignore
        @staticmethod
        def command(cmd_name: str):
            def decorator(func):
                return func
            return decorator


try:
    from .mcp_client import McpError, RussianRouletteMcpClient
    from .renderer import (
        render_game_view,
        render_help,
        render_rooms_summary,
        render_step_result,
    )
except ImportError:
    from mcp_client import McpError, RussianRouletteMcpClient
    from renderer import (
        render_game_view,
        render_help,
        render_rooms_summary,
        render_step_result,
    )

DIRECTION_MAP = {
    # Up
    "上": "up", "北": "up", "up": "up", "w": "up", "u": "up", "↑": "up", "8": "up", "前": "up",
    # Down
    "下": "down", "南": "down", "down": "down", "s": "down", "↓": "down", "2": "down", "后": "down",
    # Left
    "左": "left", "西": "left", "left": "left", "a": "left", "l": "left", "←": "left", "4": "left",
    # Right
    "右": "right", "东": "right", "right": "right", "d": "right", "r": "right", "→": "right", "6": "right",
}


class RussianRoulettePlugin(Star):
    """
    AstrBot plugin acting as a referee host and state presenter for Russian Roulette.
    All game state, chamber mechanics, terrain and rules are 100% evaluated by the backend.
    """

    def __init__(self, context: Context, config: Optional[AstrBotConfig | dict] = None):
        super().__init__(context)
        self.config: Dict[str, Any] = config if config is not None else {}
        server_url = self.config.get("server_url", "http://127.0.0.1:8787")
        mcp_endpoint = self.config.get("mcp_endpoint", "/api/mcp/call")
        self.client = RussianRouletteMcpClient(server_url=server_url, mcp_endpoint=mcp_endpoint)
        
        # Session context -> Active room_id cache (makes chat play convenient)
        self._session_rooms: Dict[str, str] = {}
        logger.info(f"RussianRoulettePlugin initialized with backend: {server_url}")

    def _resolve_room_id(self, event: AstrMessageEvent, candidate: Optional[str]) -> Optional[str]:
        if candidate and candidate.strip():
            rid = candidate.strip().upper()
            if rid not in DIRECTION_MAP:  # Not a direction parameter
                return rid
        session_id = getattr(event, "unified_msg_origin", "default")
        return self._session_rooms.get(session_id)

    def _set_active_room(self, event: AstrMessageEvent, room_id: str) -> None:
        session_id = getattr(event, "unified_msg_origin", "default")
        self._session_rooms[session_id] = room_id

    @filter.command("rr")
    async def handle_rr(self, event: AstrMessageEvent):
        """
        主指令入口：/rr [子指令] [参数]
        """
        raw = ""
        if hasattr(event, "get_message_str"):
            try:
                raw = event.get_message_str()
            except Exception:
                pass
        if not raw and hasattr(event, "message_str"):
            raw = event.message_str

        parts = raw.strip().split()
        if parts and parts[0].lstrip("/").lower() in ("rr", "轮盘"):
            parts = parts[1:]
        sub_cmd = parts[0] if parts else "帮助"
        args = parts[1:] if len(parts) > 1 else []
        async for res in self._dispatch_command(event, sub_cmd, args):
            yield res

    @filter.command("轮盘")
    async def handle_roulette(self, event: AstrMessageEvent):
        """
        中文别名入口：/轮盘 [子指令] [参数]
        """
        raw = ""
        if hasattr(event, "get_message_str"):
            try:
                raw = event.get_message_str()
            except Exception:
                pass
        if not raw and hasattr(event, "message_str"):
            raw = event.message_str

        parts = raw.strip().split()
        if parts and parts[0].lstrip("/").lower() in ("rr", "轮盘"):
            parts = parts[1:]
        sub_cmd = parts[0] if parts else "帮助"
        args = parts[1:] if len(parts) > 1 else []
        async for res in self._dispatch_command(event, sub_cmd, args):
            yield res

    async def _dispatch_command(self, event: AstrMessageEvent, sub_cmd: str, args: List[str]):
        cmd = sub_cmd.lower().strip()

        try:
            if cmd in ("help", "帮助", "?", "？"):
                topic = args[0] if args else None
                yield event.plain_result(render_help(topic))

            elif cmd in ("status", "状态", "ping"):
                yield event.plain_result(await self._handle_status())

            elif cmd in ("rooms", "房间", "列表", "list"):
                yield event.plain_result(await self._handle_list_rooms(args))

            elif cmd in ("create", "创建", "建房"):
                yield event.plain_result(await self._handle_create_room(event, args))

            elif cmd in ("start", "开始", "开局"):
                yield event.plain_result(await self._handle_start_room(event, args))

            elif cmd in ("view", "战况", "对局", "info", "看"):
                yield event.plain_result(await self._handle_view_room(event, args))

            elif cmd in ("shoot", "开火", "开枪", "射击", "fire"):
                yield event.plain_result(await self._handle_shoot(event, args))

            elif cmd in ("move", "移动", "走", "走步", "走位"):
                yield event.plain_result(await self._handle_move(event, args))

            elif cmd in ("wait", "等待", "跳过", "pass"):
                yield event.plain_result(await self._handle_wait(event, args))

            elif cmd in ("suicide", "自戕", "自杀", "饮弹"):
                yield event.plain_result(await self._handle_suicide(event, args))

            elif cmd in ("step", "步进", "下一步", "走步"):
                yield event.plain_result(await self._handle_step(event, args))

            elif cmd in ("bot", "bots", "机器人", "加bot", "减bot"):
                yield event.plain_result(await self._handle_bot_setup(event, cmd, args))

            elif cmd in ("bind", "绑定", "切房"):
                yield event.plain_result(await self._handle_bind_room(event, args))

            elif cmd in ("unbind", "解绑", "离开"):
                yield event.plain_result(await self._handle_unbind_room(event))

            elif cmd in ("dissolve", "解散", "关闭", "kill"):
                yield event.plain_result(await self._handle_dissolve(event, args))

            elif cmd in ("rules", "规则"):
                yield event.plain_result(await self._handle_rules())

            elif cmd in DIRECTION_MAP:
                # Direct directional shortcut: e.g. /rr 上, /rr 右, /rr w, /rr 6
                yield event.plain_result(await self._handle_move(event, [cmd] + args))

            else:
                yield event.plain_result(
                    f"❓ 未知轮盘指令: `{sub_cmd}`\n输入 `/rr 帮助` 查看所有可用指令清单。"
                )
        except McpError as e:
            yield event.plain_result(f"❌ 轮盘游戏错误 [{e.code}]: {e.message}")
        except Exception as e:
            logger.exception("Unexpected error in RussianRoulettePlugin")
            yield event.plain_result(f"⚠️ 执行异常: {e}")

    # --- Command implementations ---

    async def _handle_status(self) -> str:
        url = self.client.get_full_url()
        try:
            rooms = await self.client.list_rooms()
            return (
                f"✅ 轮盘后端连接正常！\n"
                f"• 服务地址: {self.client.server_url}\n"
                f"• MCP端点: {self.client.mcp_endpoint}\n"
                f"• 当前活跃房间: {len(rooms)} 间"
            )
        except Exception as e:
            return (
                f"❌ 无法连接到轮盘后端！\n"
                f"• 目标端点: {url}\n"
                f"• 失败原因: {e}\n"
                f"• 建议检查 roulette-backend 或 roulette-local 是否正在运行。"
            )

    async def _handle_list_rooms(self, args: List[str]) -> str:
        filter_phase: Optional[str] = None
        if args:
            arg0 = args[0].lower().strip()
            if arg0 in ("wait", "waiting", "等待", "等"):
                filter_phase = "waiting"
            elif arg0 in ("ingame", "in_game", "进行", "激战", "战斗", "游戏中"):
                filter_phase = "in_game"
            elif arg0 in ("finished", "结束", "已结束", "终局"):
                filter_phase = "finished"

        rooms = await self.client.list_rooms(filter_phase=filter_phase)
        return render_rooms_summary(rooms, filter_phase=filter_phase)

    async def _handle_create_room(self, event: AstrMessageEvent, args: List[str]) -> str:
        # Syntax options:
        # 1. /rr 创建
        # 2. /rr 创建 [名称] [bot数] [密码]
        # 3. /rr 创建 name=xxx bots=4 pass=123
        default_bots = int(self.config.get("default_bots", 3))
        room_name = f"QQ群轮盘_{event.get_sender_name()}"
        initial_bots = default_bots
        password: Optional[str] = None

        pos_args = []
        for a in args:
            if "=" in a:
                k, v = a.split("=", 1)
                k = k.lower().strip()
                v = v.strip()
                if k in ("bots", "bot", "人数", "人", "count"):
                    try:
                        initial_bots = int(v)
                    except ValueError:
                        pass
                elif k in ("pass", "pwd", "password", "密码"):
                    password = v or None
                elif k in ("name", "名称", "房间名"):
                    room_name = v
            else:
                pos_args.append(a)

        # Parse positional args flexibly
        if len(pos_args) == 1:
            if pos_args[0].isdigit():
                initial_bots = int(pos_args[0])
            else:
                room_name = pos_args[0]
        elif len(pos_args) == 2:
            if pos_args[0].isdigit():
                initial_bots = int(pos_args[0])
                room_name = pos_args[1]
            elif pos_args[1].isdigit():
                room_name = pos_args[0]
                initial_bots = int(pos_args[1])
            else:
                room_name = pos_args[0]
                password = pos_args[1]
        elif len(pos_args) >= 3:
            room_name = pos_args[0]
            if pos_args[1].isdigit():
                initial_bots = int(pos_args[1])
                password = pos_args[2]
            else:
                password = pos_args[1]
                if pos_args[2].isdigit():
                    initial_bots = int(pos_args[2])

        initial_bots = max(1, min(7, initial_bots))
        result = await self.client.create_room(
            room_name=room_name,
            initial_bots=initial_bots,
            password=password,
        )
        room_id = result.get("id", "?????")
        self._set_active_room(event, room_id)

        pwd_str = f"• 房间密码: `{password}`\n" if password else ""
        return (
            f"🎉 成功创建轮盘对局房间 [{room_id}]「{room_name}」！\n"
            f"• 预置 Bot 席位: {initial_bots} 个\n"
            f"{pwd_str}"
            f"• 当前本群默认绑定房间: [{room_id}]\n"
            f"──────────────────────\n"
            f"👉 请输入 `/rr 开始 {room_id}` 正式装填左轮开战！"
        )

    async def _handle_start_room(self, event: AstrMessageEvent, args: List[str]) -> str:
        room_candidate = None
        seed: Optional[int] = None

        for a in args:
            if a.startswith("seed=") or a.startswith("种子="):
                try:
                    seed = int(a.split("=", 1)[1])
                except ValueError:
                    pass
            elif a.isdigit() and len(a) > 5:
                # Long integer is unambiguous seed
                seed = int(a)
            elif a.isdigit() and seed is None and len(args) == 1:
                # E.g. /rr 开始 12345
                seed = int(a)
            elif not room_candidate:
                room_candidate = a

        room_id = self._resolve_room_id(event, room_candidate)
        if not room_id:
            return "⚠️ 请指定要开启的5位房间号，或先使用 `/rr 创建` 建立房间。"

        self._set_active_room(event, room_id)
        result = await self.client.start_match(room_id, seed=seed)
        room_view = await self.client.inspect_room(room_id)
        show_board = bool(self.config.get("show_visual_board", True))
        max_events = int(self.config.get("max_event_records", 5))
        view_text = render_game_view(room_view, show_visual_board=show_board, max_events=max_events)

        seed_str = f" (固定随机种子: {seed})" if seed is not None else ""
        return f"🔫 俄罗斯轮盘装填完毕，保险拔除，对决正式开始！{seed_str}\n\n{view_text}"

    async def _handle_view_room(self, event: AstrMessageEvent, args: List[str]) -> str:
        room_candidate = None
        max_events = int(self.config.get("max_event_records", 5))
        show_board = bool(self.config.get("show_visual_board", True))

        for a in args:
            if a in ("简略", "简报", "brief", "summary", "无图"):
                show_board = False
            elif a in ("详细", "地图", "detail", "map"):
                show_board = True
            elif a.isdigit():
                max_events = max(1, min(20, int(a)))
            elif not room_candidate:
                room_candidate = a

        room_id = self._resolve_room_id(event, room_candidate)
        if not room_id:
            return "⚠️ 请指定房间号，如 `/rr 战况 88888`，或先使用 `/rr 创建` 建房。"

        room_view = await self.client.inspect_room(room_id)
        return render_game_view(room_view, show_visual_board=show_board, max_events=max_events)

    async def _handle_shoot(self, event: AstrMessageEvent, args: List[str]) -> str:
        # Syntax: /rr 开火 [房间号] <方向> 或 /rr 开火 <方向> [房间号]
        direction_str = None
        room_candidate = None

        for a in args:
            if a.lower() in DIRECTION_MAP:
                direction_str = a
            elif not room_candidate:
                room_candidate = a

        if not direction_str:
            return "⚠️ 请指定开火方向，例如：`/rr 开火 上`、`/rr 开火 右`、`/rr 开火 6`"

        room_id = self._resolve_room_id(event, room_candidate)
        if not room_id:
            return "⚠️ 请指定房间号，例如：`/rr 开火 88888 上`"

        direction = DIRECTION_MAP.get(direction_str.lower())
        command = {"type": "shoot", "direction": direction}
        step_res = await self.client.force_command(room_id, command)
        
        # Follow up with battle report
        summary = render_step_result(step_res)
        room_view = step_res.get("room") or await self.client.inspect_room(room_id)
        show_board = bool(self.config.get("show_visual_board", True))
        view_text = render_game_view(room_view, show_visual_board=show_board, max_events=3)
        return f"{summary}\n\n{view_text}"

    async def _handle_move(self, event: AstrMessageEvent, args: List[str]) -> str:
        # Syntax: /rr 移动 [房间号] <方向> 或 /rr 移动 <方向> [房间号]
        direction_str = None
        room_candidate = None

        for a in args:
            if a.lower() in DIRECTION_MAP:
                direction_str = a
            elif not room_candidate:
                room_candidate = a

        if not direction_str:
            return "⚠️ 请指定移动方向，例如：`/rr 移动 上`、`/rr 移动 右`、`/rr 移动 6`"

        room_id = self._resolve_room_id(event, room_candidate)
        if not room_id:
            return "⚠️ 请指定房间号，例如：`/rr 移动 88888 上`"

        direction = DIRECTION_MAP.get(direction_str.lower())
        command = {"type": "move", "direction": direction}
        step_res = await self.client.force_command(room_id, command)

        summary = render_step_result(step_res)
        room_view = step_res.get("room") or await self.client.inspect_room(room_id)
        show_board = bool(self.config.get("show_visual_board", True))
        view_text = render_game_view(room_view, show_visual_board=show_board, max_events=3)
        return f"{summary}\n\n{view_text}"

    async def _handle_wait(self, event: AstrMessageEvent, args: List[str]) -> str:
        candidate = args[0] if len(args) >= 1 else None
        room_id = self._resolve_room_id(event, candidate)
        if not room_id:
            return "⚠️ 请指定房间号，例如：`/rr 等待 88888`"

        command = {"type": "wait"}
        step_res = await self.client.force_command(room_id, command)
        summary = render_step_result(step_res)
        room_view = step_res.get("room") or await self.client.inspect_room(room_id)
        show_board = bool(self.config.get("show_visual_board", True))
        view_text = render_game_view(room_view, show_visual_board=show_board, max_events=3)
        return f"{summary}\n\n{view_text}"

    async def _handle_suicide(self, event: AstrMessageEvent, args: List[str]) -> str:
        candidate = args[0] if len(args) >= 1 else None
        room_id = self._resolve_room_id(event, candidate)
        if not room_id:
            return "⚠️ 请指定房间号，例如：`/rr 自戕 88888`"

        command = {"type": "suicide"}
        step_res = await self.client.force_command(room_id, command)
        summary = render_step_result(step_res)
        room_view = step_res.get("room") or await self.client.inspect_room(room_id)
        show_board = bool(self.config.get("show_visual_board", True))
        view_text = render_game_view(room_view, show_visual_board=show_board, max_events=3)
        return f"{summary}\n\n{view_text}"

    async def _handle_step(self, event: AstrMessageEvent, args: List[str]) -> str:
        room_candidate = None
        count = 1

        for a in args:
            if a in ("auto", "自动", "全部", "回合", "到底"):
                count = 6
            elif a.isdigit():
                count = min(10, max(1, int(a)))
            elif not room_candidate:
                room_candidate = a

        room_id = self._resolve_room_id(event, room_candidate)
        if not room_id:
            return "⚠️ 请指定房间号，例如：`/rr 步进 88888`"

        if count <= 1:
            step_res = await self.client.step_bot(room_id)
            summary = render_step_result(step_res)
            room_view = step_res.get("room") or await self.client.inspect_room(room_id)
            show_board = bool(self.config.get("show_visual_board", True))
            view_text = render_game_view(room_view, show_visual_board=show_board, max_events=3)
            return f"{summary}\n\n{view_text}"

        # Multi-step loop
        step_logs = []
        last_step_res = {}
        for i in range(1, count + 1):
            try:
                last_step_res = await self.client.step_bot(room_id)
                action_desc = last_step_res.get("action_desc", "行动完成")
                step_logs.append(f"• 第 {i} 步: {action_desc}")
                if last_step_res.get("is_match_finished", False):
                    step_logs.append("🏁 对局宣告结束！")
                    break
            except McpError as e:
                step_logs.append(f"⚠️ 步进暂停 [{e.code}]: {e.message}")
                break

        header = f"🎯 【连续步进执行结果】(共推进 {len([l for l in step_logs if l.startswith('•')])} 步)：\n" + "\n".join(step_logs)
        room_view = last_step_res.get("room") or await self.client.inspect_room(room_id)
        show_board = bool(self.config.get("show_visual_board", True))
        view_text = render_game_view(room_view, show_visual_board=show_board, max_events=4)
        return f"{header}\n\n{view_text}"

    async def _handle_bot_setup(self, event: AstrMessageEvent, cmd: str, args: List[str]) -> str:
        action = None
        target_count = None
        room_candidate = None

        if cmd in ("加bot", "加机器人"):
            action = "add"
            if args:
                room_candidate = args[0]
        elif cmd in ("减bot", "减机器人"):
            action = "remove"
            if args:
                room_candidate = args[0]
        else:
            if not args:
                # Check if session has active room in game -> fallback to step
                room_id = self._resolve_room_id(event, None)
                if room_id:
                    try:
                        view = await self.client.inspect_room(room_id)
                        if view.get("phase") == "in_game":
                            return await self._handle_step(event, [])
                    except Exception:
                        pass
                return "⚠️ 请指定 bot 操作，例如：`/rr bot 加`、`/rr bot 减` 或 `/rr bot 4`"

            first = args[0].lower().strip()
            if first in ("add", "加", "增加", "+"):
                action = "add"
                room_candidate = args[1] if len(args) > 1 else None
            elif first in ("remove", "del", "减", "减少", "-"):
                action = "remove"
                room_candidate = args[1] if len(args) > 1 else None
            elif first.isdigit():
                target_count = int(first)
                room_candidate = args[1] if len(args) > 1 else None
            else:
                room_candidate = first
                if len(args) > 1:
                    second = args[1].lower().strip()
                    if second in ("add", "加", "增加", "+"):
                        action = "add"
                    elif second in ("remove", "del", "减", "减少", "-"):
                        action = "remove"
                    elif second.isdigit():
                        target_count = int(second)

        room_id = self._resolve_room_id(event, room_candidate)
        if not room_id:
            return "⚠️ 请指定房间号，例如：`/rr bot 加 88888`，或先使用 `/rr 创建` 建房。"

        if action:
            res = await self.client.setup_bots(room_id, action)
            members = res.get("members", [])
            bot_count = len([m for m in members if m.get("kind") == "bot"])
            act_zh = "增加" if action == "add" else "移除"
            return f"🤖 成功为房间 [{room_id}] {act_zh} 1 名 Bot！当前总成员: {len(members)} 人 (Bot: {bot_count} 名)"

        if target_count is not None:
            view = await self.client.inspect_room(room_id)
            members = view.get("members", [])
            current_bots = [m for m in members if m.get("kind") == "bot"]
            diff = target_count - len(current_bots)
            if diff == 0:
                return f"🤖 房间 [{room_id}] 当前 Bot 数量已为 {target_count} 个，无需调整。"
            elif diff > 0:
                for _ in range(min(5, diff)):
                    await self.client.setup_bots(room_id, "add")
            else:
                for _ in range(min(5, -diff)):
                    await self.client.setup_bots(room_id, "remove")
            view = await self.client.inspect_room(room_id)
            new_bots = len([m for m in view.get("members", []) if m.get("kind") == "bot"])
            return f"🤖 成功调整房间 [{room_id}] 的 Bot 席位为 {new_bots} 个！"

        return "⚠️ 未知 Bot 操作，请参考：`/rr bot 加` 或 `/rr bot 减`"

    async def _handle_bind_room(self, event: AstrMessageEvent, args: List[str]) -> str:
        if not args:
            return "⚠️ 请指定要绑定的房间号，例如：`/rr 绑定 FQZBQ`"
        room_id = args[0].strip().upper()
        try:
            view = await self.client.inspect_room(room_id)
            self._set_active_room(event, room_id)
            name = view.get("name", "未命名房间")
            phase = view.get("phase", "unknown")
            return f"🔗 已将当前群聊切换绑定至房间 [{room_id}]「{name}」(阶段: {phase})！后续指令可直接输入。"
        except McpError as e:
            return f"❌ 无法绑定房间 [{room_id}]: {e.message}"

    async def _handle_unbind_room(self, event: AstrMessageEvent) -> str:
        session_id = getattr(event, "unified_msg_origin", "default")
        old = self._session_rooms.pop(session_id, None)
        if old:
            return f"🔓 已解除当前群聊与房间 [{old}] 的绑定记忆。"
        return "ℹ️ 当前群聊未绑定任何房间。"

    async def _handle_dissolve(self, event: AstrMessageEvent, args: List[str]) -> str:
        candidate = args[0] if len(args) >= 1 else None
        room_id = self._resolve_room_id(event, candidate)
        if not room_id:
            return "⚠️ 请指定要解散的房间号，例如：`/rr 解散 88888`"

        await self.client.dissolve_room(room_id)
        session_id = getattr(event, "unified_msg_origin", "default")
        if self._session_rooms.get(session_id) == room_id:
            self._session_rooms.pop(session_id, None)

        return f"🚫 房间 [{room_id}] 已被裁判强制解散，相关对局数据已清空。"

    async def _handle_rules(self) -> str:
        try:
            rules = await self.client.query_rules()
            desc = rules.get("description", "左轮弹巢装填有真弹与空弹，幸存到最后者胜出。")
            return (
                f"📖 【俄罗斯轮盘权威规则】\n"
                f"──────────────────────\n"
                f"{desc}\n\n"
                f"• 防弹盾牌：每局玩家均拥有一面单次生效防弹盾，可抵挡一次致命实弹伤害。\n"
                f"• 特殊地形：\n"
                f"  - 🧱 墙体：不可穿行，可抵挡普通子弹。\n"
                f"  - 🌊 水洼：涉水移动延迟，连续两回合在水中将溺水淘汰。\n"
                f"  - 📦 木箱：掩体，承受撞击或射击后可能损毁。"
            )
        except Exception:
            return (
                "📖 【俄罗斯轮盘规则简述】\n"
                "• 玩家在地图上轮流行动（移动或开火）；\n"
                "• 左轮手枪弹巢中随机混装真弹与空弹；\n"
                "• 拥有单次防弹盾，击碎后失去保护；\n"
                "• 活到最后的幸存者获胜！"
            )
