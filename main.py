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
    "上": "up",
    "北": "up",
    "up": "up",
    "w": "up",
    "下": "down",
    "南": "down",
    "down": "down",
    "s": "down",
    "左": "left",
    "西": "left",
    "left": "left",
    "a": "left",
    "右": "right",
    "东": "right",
    "right": "right",
    "d": "right",
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
        self._session_rooms[session_id] = room_id.upper()

    @filter.command("rr")
    async def handle_rr(self, event: AstrMessageEvent, sub_cmd: str = "帮助", *args):
        """
        主指令入口：/rr [子指令] [参数]
        """
        async for res in self._dispatch_command(event, sub_cmd, list(args)):
            yield res

    @filter.command("轮盘")
    async def handle_roulette(self, event: AstrMessageEvent, sub_cmd: str = "帮助", *args):
        """
        中文别名入口：/轮盘 [子指令] [参数]
        """
        async for res in self._dispatch_command(event, sub_cmd, list(args)):
            yield res

    async def _dispatch_command(self, event: AstrMessageEvent, sub_cmd: str, args: List[str]):
        cmd = sub_cmd.lower().strip()

        try:
            if cmd in ("help", "帮助", "?", "？"):
                yield event.plain_result(render_help())

            elif cmd in ("status", "状态", "ping"):
                yield event.plain_result(await self._handle_status())

            elif cmd in ("rooms", "房间", "列表", "list"):
                yield event.plain_result(await self._handle_list_rooms())

            elif cmd in ("create", "创建", "建房"):
                yield event.plain_result(await self._handle_create_room(event, args))

            elif cmd in ("start", "开始", "开局"):
                yield event.plain_result(await self._handle_start_room(event, args))

            elif cmd in ("view", "战况", "状态", "info", "看"):
                yield event.plain_result(await self._handle_view_room(event, args))

            elif cmd in ("shoot", "开火", "开枪", "射击", "fire"):
                yield event.plain_result(await self._handle_shoot(event, args))

            elif cmd in ("move", "移动", "走", "走步"):
                yield event.plain_result(await self._handle_move(event, args))

            elif cmd in ("wait", "等待", "跳过", "pass"):
                yield event.plain_result(await self._handle_wait(event, args))

            elif cmd in ("suicide", "自戕", "自杀", "饮弹"):
                yield event.plain_result(await self._handle_suicide(event, args))

            elif cmd in ("step", "步进", "下一步", "bot"):
                yield event.plain_result(await self._handle_step(event, args))

            elif cmd in ("dissolve", "解散", "关闭", "kill"):
                yield event.plain_result(await self._handle_dissolve(event, args))

            elif cmd in ("rules", "规则"):
                yield event.plain_result(await self._handle_rules())

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
                f"✅ 轮盘赌后端连接正常！\n"
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

    async def _handle_list_rooms(self) -> str:
        rooms = await self.client.list_rooms()
        return render_rooms_summary(rooms)

    async def _handle_create_room(self, event: AstrMessageEvent, args: List[str]) -> str:
        # Syntax: /rr 创建 [名称/房间号] [bot数]
        default_bots = int(self.config.get("default_bots", 3))
        room_name = f"QQ群轮盘局_{event.get_sender_name()}"
        initial_bots = default_bots

        if len(args) >= 1:
            if args[0].isdigit():
                initial_bots = int(args[0])
            else:
                room_name = args[0]
        if len(args) >= 2 and args[1].isdigit():
            initial_bots = int(args[1])

        initial_bots = max(1, min(7, initial_bots))
        result = await self.client.create_room(room_name=room_name, initial_bots=initial_bots)
        room_id = result.get("id", "?????")
        self._set_active_room(event, room_id)

        return (
            f"🎉 成功创建轮盘对局房间 [{room_id}]「{room_name}」！\n"
            f"• 预置 Bot 席位: {initial_bots} 个\n"
            f"• 当前本群默认绑定房间: [{room_id}]\n"
            f"──────────────────────\n"
            f"👉 请输入 `/rr 开始 {room_id}` 正式装填左轮开战！"
        )

    async def _handle_start_room(self, event: AstrMessageEvent, args: List[str]) -> str:
        candidate = args[0] if len(args) >= 1 else None
        room_id = self._resolve_room_id(event, candidate)
        if not room_id:
            return "⚠️ 请指定要开启的5位房间号，或先使用 `/rr 创建` 建立房间。"

        self._set_active_room(event, room_id)
        result = await self.client.start_match(room_id)
        room_view = await self.client.inspect_room(room_id)
        show_board = bool(self.config.get("show_visual_board", True))
        max_events = int(self.config.get("max_event_records", 5))
        view_text = render_game_view(room_view, show_visual_board=show_board, max_events=max_events)

        return f"🔫 俄罗斯轮盘装填完毕，保险拔除，对决正式开始！\n\n{view_text}"

    async def _handle_view_room(self, event: AstrMessageEvent, args: List[str]) -> str:
        candidate = args[0] if len(args) >= 1 else None
        room_id = self._resolve_room_id(event, candidate)
        if not room_id:
            return "⚠️ 请指定房间号，如 `/rr 战况 88888`，或先使用 `/rr 创建` 建房。"

        room_view = await self.client.inspect_room(room_id)
        show_board = bool(self.config.get("show_visual_board", True))
        max_events = int(self.config.get("max_event_records", 5))
        return render_game_view(room_view, show_visual_board=show_board, max_events=max_events)

    async def _handle_shoot(self, event: AstrMessageEvent, args: List[str]) -> str:
        # Syntax: /rr 开火 [房间号] <方向>  或 /rr 开火 <方向>
        direction_str = None
        room_candidate = None

        if len(args) == 1:
            direction_str = args[0]
        elif len(args) >= 2:
            room_candidate = args[0]
            direction_str = args[1]
        else:
            return "⚠️ 请指定开火方向，例如：`/rr 开火 上` 或 `/rr 开火 88888 东`"

        room_id = self._resolve_room_id(event, room_candidate)
        if not room_id:
            return "⚠️ 请指定房间号，例如：`/rr 开火 88888 上`"

        direction = DIRECTION_MAP.get(direction_str.lower())
        if not direction:
            return f"⚠️ 无效方向: `{direction_str}`，支持：上/下/左/右 (或北/南/西/东/w/s/a/d)"

        command = {"type": "shoot", "direction": direction}
        step_res = await self.client.force_command(room_id, command)
        
        # Follow up with battle report
        summary = render_step_result(step_res)
        room_view = step_res.get("room") or await self.client.inspect_room(room_id)
        show_board = bool(self.config.get("show_visual_board", True))
        view_text = render_game_view(room_view, show_visual_board=show_board, max_events=3)
        return f"{summary}\n\n{view_text}"

    async def _handle_move(self, event: AstrMessageEvent, args: List[str]) -> str:
        # Syntax: /rr 移动 [房间号] <方向>  或 /rr 移动 <方向>
        direction_str = None
        room_candidate = None

        if len(args) == 1:
            direction_str = args[0]
        elif len(args) >= 2:
            room_candidate = args[0]
            direction_str = args[1]
        else:
            return "⚠️ 请指定移动方向，例如：`/rr 移动 上` 或 `/rr 移动 88888 西`"

        room_id = self._resolve_room_id(event, room_candidate)
        if not room_id:
            return "⚠️ 请指定房间号，例如：`/rr 移动 88888 上`"

        direction = DIRECTION_MAP.get(direction_str.lower())
        if not direction:
            return f"⚠️ 无效方向: `{direction_str}`，支持：上/下/左/右 (或北/南/西/东/w/s/a/d)"

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
        candidate = args[0] if len(args) >= 1 else None
        room_id = self._resolve_room_id(event, candidate)
        if not room_id:
            return "⚠️ 请指定房间号，例如：`/rr 步进 88888`"

        step_res = await self.client.step_bot(room_id)
        summary = render_step_result(step_res)
        room_view = step_res.get("room") or await self.client.inspect_room(room_id)
        show_board = bool(self.config.get("show_visual_board", True))
        view_text = render_game_view(room_view, show_visual_board=show_board, max_events=3)
        return f"{summary}\n\n{view_text}"

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
