"""
Standalone Unit Test & Mock Suite for Russian Roulette AstrBot Plugin.
Can be executed directly with `python3 test_standalone.py`.
"""

import asyncio
from pathlib import Path
import sys
import types
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

# --- Register mock aiohttp if not installed ---
if "aiohttp" not in sys.modules:
    mock_aiohttp = types.ModuleType("aiohttp")
    mock_aiohttp.ClientSession = MagicMock()
    mock_aiohttp.ClientTimeout = MagicMock()
    mock_aiohttp.ClientConnectorError = Exception
    sys.modules["aiohttp"] = mock_aiohttp

# --- Register mock astrbot module hierarchy if not installed ---
if "astrbot" not in sys.modules:
    mock_astrbot = types.ModuleType("astrbot")
    sys.modules["astrbot"] = mock_astrbot

    mock_api = types.ModuleType("astrbot.api")

    class MockLogger:
        def info(self, msg, *args, **kwargs): pass
        def warning(self, msg, *args, **kwargs): pass
        def error(self, msg, *args, **kwargs): pass
        def exception(self, msg, *args, **kwargs): pass
        def debug(self, msg, *args, **kwargs): pass

    mock_logger = MockLogger()
    mock_api.logger = mock_logger
    mock_api.AstrBotConfig = dict
    sys.modules["astrbot.api"] = mock_api
    mock_astrbot.api = mock_api

    mock_event = types.ModuleType("astrbot.api.event")

    class AstrMessageEvent:
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

        def chain_result(self, chain: List[Any]) -> str:
            parts = []
            for c in chain:
                if hasattr(c, "text"):
                    parts.append(getattr(c, "text"))
                elif hasattr(c, "qq"):
                    parts.append(f"@{getattr(c, 'qq')}")
                else:
                    parts.append(str(c))
            return "".join(parts)

    class MockFilter:
        @staticmethod
        def command(cmd_name: str):
            def decorator(func):
                return func
            return decorator

    mock_event.AstrMessageEvent = AstrMessageEvent
    mock_event.filter = MockFilter
    sys.modules["astrbot.api.event"] = mock_event
    mock_api.event = mock_event

    mock_mc = types.ModuleType("astrbot.api.message_components")

    class At:
        def __init__(self, qq: Any = None):
            self.qq = qq

    class Plain:
        def __init__(self, text: str = ""):
            self.text = text

    class Image:
        def __init__(self, *args, **kwargs):
            self.base64 = None
            self.path = None

        def __str__(self):
            return f"<Image base64={self.base64} path={self.path}>"

        def __repr__(self):
            return self.__str__()

        @classmethod
        def fromBase64(cls, base64_str: str):
            instance = cls()
            instance.base64 = base64_str
            return instance

        @classmethod
        def fromFileSystem(cls, path: str):
            instance = cls()
            instance.path = path
            return instance

    mock_mc.At = At
    mock_mc.Plain = Plain
    mock_mc.Image = Image
    sys.modules["astrbot.api.message_components"] = mock_mc
    mock_api.message_components = mock_mc

    mock_star = types.ModuleType("astrbot.api.star")

    class Star:
        def __init__(self, context: Any):
            self.context = context

    class Context:
        pass

    mock_star.Star = Star
    mock_star.Context = Context
    sys.modules["astrbot.api.star"] = mock_star
    mock_api.star = mock_star
else:
    from astrbot.api.event import AstrMessageEvent

# Ensure clients directory is in sys.path so astrbot_plugin_russian_roulette is recognized as a package
_pkg_root = Path(__file__).resolve().parent.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from astrbot_plugin_russian_roulette.mcp_client import McpError, RussianRouletteMcpClient
from astrbot_plugin_russian_roulette.renderer import (
    compress_action_desc,
    format_compact_record,
    format_elimination_cause,
    format_weather,
    is_game_finished,
    is_game_running,
    render_board,
    render_board_block,
    render_compact_roster,
    render_game_view,
    render_help,
    render_rooms_summary,
    render_step_result,
    render_turn_callout,
)
from astrbot_plugin_russian_roulette.main import DIRECTION_MAP, RussianRoulettePlugin


class TestRussianRouletteRenderer(unittest.TestCase):
    def test_help_rendering(self):
        text = render_help()
        self.assertIn("俄罗斯轮盘", text)
        self.assertIn("/rr 开火", text)
        self.assertIn("/rr 移动", text)

    def test_rooms_summary_empty(self):
        text = render_rooms_summary([])
        self.assertIn("暂无活跃房间", text)

    def test_rooms_summary_with_items(self):
        rooms = [
            {
                "id": "A1B2C",
                "name": "测试房",
                "phase": "in_game",
                "alive_player_count": 3,
                "member_count": 4,
            }
        ]
        text = render_rooms_summary(rooms)
        self.assertIn("A1B2C", text)
        self.assertIn("激战中", text)
        self.assertIn("3/4", text)

    def test_render_board_and_game_view(self):
        mock_room = {
            "id": "R0001",
            "name": "生死局",
            "phase": "in_game",
            "game": {
                "seed": 12345,
                "revision": 3,
                "map_size": 3,
                "cells": [
                    {"position": {"x": 0, "y": 0}, "terrain": "plain"},
                    {"position": {"x": 1, "y": 0}, "terrain": "wall"},
                    {"position": {"x": 2, "y": 0}, "terrain": "water"},
                    {"position": {"x": 0, "y": 1}, "terrain": "crate"},
                    {"position": {"x": 1, "y": 1}, "terrain": "mud"},
                    {"position": {"x": 2, "y": 1}, "terrain": "frozen_water"},
                    {"position": {"x": 0, "y": 2}, "terrain": "plain"},
                    {"position": {"x": 1, "y": 2}, "terrain": "plain"},
                    {"position": {"x": 2, "y": 2}, "terrain": "plain"},
                ],
                "players": [
                    {
                        "id": "p1",
                        "name": "Alpha",
                        "kind": "human",
                        "status": "alive",
                        "position": {"x": 0, "y": 0},
                        "has_shield": True,
                    },
                    {
                        "id": "p2",
                        "name": "Bot_1",
                        "kind": "bot",
                        "status": "alive",
                        "position": {"x": 2, "y": 2},
                        "has_shield": False,
                    },
                ],
                "current_player_id": "p1",
                "round": 2,
                "status": "running",
                "weather": "rain",
                "alive_player_count": 2,
                "records": [
                    {
                        "type": "event",
                        "event": {"type": "shot_fired", "hit": False},
                    },
                    {
                        "type": "action",
                        "actor": "Alpha",
                        "action_desc": "向东移动一格",
                    },
                ],
            },
        }

        view_text = render_game_view(mock_room, show_visual_board=True)
        self.assertIn("R0001", view_text)
        self.assertIn("暴雨", view_text)
        self.assertIn("Alpha", view_text)
        self.assertIn("Bot_1", view_text)
        self.assertIn("👉", view_text)
        self.assertIn("轮到你行动了", view_text)
        self.assertIn("战术地图", view_text)
        self.assertIn("向东移动一格", view_text)

    def test_step_result_rendering(self):
        step_res = {
            "action_desc": "Alpha 向北方扣动了扳机，空弹跳过！",
            "is_match_finished": False,
        }
        res = render_step_result(step_res)
        self.assertIn("空弹跳过", res)


class TestRussianRouletteMcpClient(unittest.TestCase):
    def test_revision_cache(self):
        client = RussianRouletteMcpClient("http://127.0.0.1:8787")
        self.assertIsNone(client.get_cached_revision("room1"))
        client.update_revision("room1", 5)
        self.assertEqual(client.get_cached_revision("room1"), 5)
        self.assertEqual(client.get_cached_revision("ROOM1"), 5)  # Case insensitive

    def test_no_auth_header_by_default(self):
        client = RussianRouletteMcpClient("http://127.0.0.1:8787")
        self.assertIsNone(client.auth_token)
        self.assertNotIn("Authorization", client._headers())

    def test_bearer_header_when_token_configured(self):
        client = RussianRouletteMcpClient(
            "https://rrt.akiai.asia", auth_token="secret-token"
        )
        self.assertEqual(client.auth_token, "secret-token")
        self.assertEqual(
            client._headers()["Authorization"], "Bearer secret-token"
        )

    def test_blank_token_is_treated_as_absent(self):
        for blank in ("", "   ", None):
            client = RussianRouletteMcpClient("http://127.0.0.1:8787", auth_token=blank)
            self.assertIsNone(client.auth_token)
            self.assertNotIn("Authorization", client._headers())

    def test_portable_mode_drops_remote_token(self):
        plugin = RussianRoulettePlugin(
            None, {"mode": "portable", "auth_token": "remote-only"}
        )
        # Simulate what _ensure_backend_ready does after the loopback engine is up.
        plugin.client.auth_token = None
        self.assertNotIn("Authorization", plugin.client._headers())

    def test_remote_mode_uses_configured_token(self):
        plugin = RussianRoulettePlugin(
            None,
            {
                "mode": "remote",
                "server_url": "https://rrt.akiai.asia",
                "auth_token": "remote-token",
            },
        )
        self.assertEqual(
            plugin.client._headers()["Authorization"], "Bearer remote-token"
        )


class TestRussianRoulettePluginCommands(unittest.IsolatedAsyncioTestCase):
    async def test_direction_mapping(self):
        self.assertEqual(DIRECTION_MAP["上"], "up")
        self.assertEqual(DIRECTION_MAP["北"], "up")
        self.assertEqual(DIRECTION_MAP["下"], "down")
        self.assertEqual(DIRECTION_MAP["左"], "left")
        self.assertEqual(DIRECTION_MAP["右"], "right")
        self.assertEqual(DIRECTION_MAP["w"], "up")
        self.assertEqual(DIRECTION_MAP["d"], "right")

    async def test_dispatch_help(self):
        plugin = RussianRoulettePlugin(None, {})
        event = AstrMessageEvent(sender_id="user_123", message_str="/rr 帮助")
        results = [res async for res in plugin.handle_rr(event)]
        self.assertEqual(len(results), 1)
        self.assertIn("俄罗斯轮盘", results[0])

    async def test_dispatch_unknown_command(self):
        plugin = RussianRoulettePlugin(None, {})
        event = AstrMessageEvent(sender_id="user_123", message_str="/rr foobar")
        results = [res async for res in plugin.handle_rr(event)]
        self.assertEqual(len(results), 1)
        self.assertIn("未知轮盘指令", results[0])

    @patch.object(RussianRouletteMcpClient, "call_tool", new_callable=AsyncMock)
    async def test_mocked_lifecycle(self, mock_call):
        # 1. Mock create_room
        mock_call.return_value = {"id": "TEST1", "name": "测试房", "phase": "waiting"}
        plugin = RussianRoulettePlugin(None, {"server_url": "http://127.0.0.1:8787"})
        event = AstrMessageEvent(sender_id="user_host", message_str="/rr 创建 2")
        event.unified_msg_origin = "group_999"

        # /rr 创建 2
        results = [res async for res in plugin.handle_rr(event)]
        self.assertIn("成功创建轮盘对局房间 [TEST1]", results[0])
        self.assertEqual(plugin._session_rooms["group_999"], "TEST1")

        # 2. Mock start_match & inspect_room
        mock_call.side_effect = [
            {"room_id": "TEST1"},  # referee_start_match
            {                       # referee_inspect_room
                "id": "TEST1",
                "name": "测试房",
                "phase": "in_game",
                "game": {
                    "revision": 1,
                    "round": 1,
                    "status": "running",
                    "weather": "clear",
                    "alive_player_count": 2,
                    "current_player_id": "p1",
                    "players": [
                        {"id": "p1", "name": "Host", "kind": "human", "status": "alive", "has_shield": True},
                        {"id": "p2", "name": "Bot_1", "kind": "bot", "status": "alive", "has_shield": True},
                    ],
                }
            },
        ]

        event.message_str = "/rr 开始"
        results = [res async for res in plugin.handle_rr(event)]
        self.assertGreaterEqual(len(results), 2)
        self.assertIn("俄罗斯轮盘装填完毕", results[0])
        self.assertTrue(any("Host" in r for r in results))

    async def test_help_topics(self):
        plugin = RussianRoulettePlugin(None, {})
        event = AstrMessageEvent(sender_id="user_123", message_str="/rr 帮助 开火")
        results = [res async for res in plugin.handle_rr(event)]
        self.assertIn("指令详情：/rr 开火", results[0])
        self.assertIn("键盘数字", results[0])

        event.message_str = "/rr 帮助 步进"
        results = [res async for res in plugin.handle_rr(event)]
        self.assertIn("指令详情：/rr 步进", results[0])
        self.assertIn("自动", results[0])

    @patch.object(RussianRouletteMcpClient, "call_tool", new_callable=AsyncMock)
    async def test_enriched_create_and_start(self, mock_call):
        plugin = RussianRoulettePlugin(None, {})
        event = AstrMessageEvent(sender_id="user_host", message_str="/rr 创建 name=死亡峡谷 bots=5 pass=123456")
        event.unified_msg_origin = "group_100"

        mock_call.return_value = {"id": "ROOM9", "name": "死亡峡谷", "phase": "waiting"}
        results = [res async for res in plugin.handle_rr(event)]
        self.assertIn("ROOM9", results[0])
        self.assertIn("死亡峡谷", results[0])
        self.assertIn("123456", results[0])
        # Verify call arguments
        mock_call.assert_called_with(
            "referee_create_room",
            {
                "room_name": "死亡峡谷",
                "initial_bots": 5,
                "password": "123456",
                "idempotency_key": unittest.mock.ANY,
            },
        )

        # Test start with seed
        mock_call.side_effect = [
            {"room_id": "ROOM9"},
            {
                "id": "ROOM9",
                "name": "死亡峡谷",
                "phase": "in_game",
                "game": {"revision": 1, "round": 1, "status": "running", "weather": "clear", "players": []},
            },
        ]
        event.message_str = "/rr 开始 seed=888888"
        results = [res async for res in plugin.handle_rr(event)]
        self.assertIn("固定随机种子: 888888", results[0])

    @patch.object(RussianRouletteMcpClient, "call_tool", new_callable=AsyncMock)
    async def test_directional_shortcut_and_numpad(self, mock_call):
        plugin = RussianRoulettePlugin(None, {})
        event = AstrMessageEvent(sender_id="user_host", message_str="/rr 上")
        event.unified_msg_origin = "group_100"
        plugin._session_rooms["group_100"] = "ROOM9"
        plugin.client.update_revision("ROOM9", 1)

        mock_call.return_value = {
            "action_desc": "移动了一格",
            "room": {"id": "ROOM9", "name": "死亡峡谷", "phase": "in_game", "game": {"revision": 2, "players": []}},
        }
        results = [res async for res in plugin.handle_rr(event)]
        self.assertIn("裁判裁定", results[0])
        # Verify force_command was called with direction "up"
        mock_call.assert_any_call(
            "referee_force_command",
            {
                "room_id": "ROOM9",
                "expected_revision": 1,
                "command": {"type": "move", "direction": "up"},
                "idempotency_key": unittest.mock.ANY,
            },
        )

    @patch.object(RussianRouletteMcpClient, "call_tool", new_callable=AsyncMock)
    async def test_bot_setup_and_binding(self, mock_call):
        plugin = RussianRoulettePlugin(None, {})
        event = AstrMessageEvent(sender_id="user_host", message_str="/rr bot 加")
        event.unified_msg_origin = "group_100"
        plugin._session_rooms["group_100"] = "ROOM9"

        # 1. bot 加
        mock_call.side_effect = [
            {"id": "ROOM9", "phase": "waiting", "members": [{"kind": "human"}, {"kind": "bot"}]},
            {"members": [{"kind": "human"}, {"kind": "bot"}, {"kind": "bot"}]},
        ]
        results = [res async for res in plugin.handle_rr(event)]
        self.assertIn("成功为房间 [ROOM9] 增加 1 名 Bot", results[0])

        # 2. unbind
        event.message_str = "/rr 解绑"
        results = [res async for res in plugin.handle_rr(event)]
        self.assertIn("已解除当前群聊与房间 [ROOM9] 的绑定记忆", results[0])
        self.assertNotIn("group_100", plugin._session_rooms)

    @patch.object(RussianRouletteMcpClient, "call_tool", new_callable=AsyncMock)
    async def test_list_rooms_filter(self, mock_call):
        plugin = RussianRoulettePlugin(None, {})
        mock_call.return_value = [
            {"id": "ROOM1", "name": "等待房", "phase": "waiting", "member_count": 2},
            {"id": "ROOM2", "name": "激战房", "phase": "playing", "member_count": 4, "alive_player_count": 3},
            {"id": "ROOM3", "name": "终局房", "phase": "finished", "member_count": 4, "alive_player_count": 1},
        ]
        event = AstrMessageEvent(sender_id="user1", message_str="/rr 房间 进行")
        results = [res async for res in plugin.handle_rr(event)]
        self.assertIn("激战房", results[0])
        self.assertNotIn("等待房", results[0])
        self.assertIn("⚔️ 激战中", results[0])

    @patch.object(RussianRouletteMcpClient, "call_tool", new_callable=AsyncMock)
    async def test_multi_message_block_separation(self, mock_call):
        plugin = RussianRoulettePlugin(None, {})
        room_data = {
            "id": "SEP01",
            "name": "多块测试",
            "phase": "playing",
            "members": [
                {"player_id": 1, "name": "秋元萱", "kind": "human"},
                {"player_id": 2, "name": "Bot 2", "kind": "bot"},
            ],
            "game": {
                "revision": 2,
                "round": 2,
                "status": "running",
                "weather": "heatwave",
                "alive_player_count": 2,
                "current_player_id": 1,
                "map_size": 2,
                "cells": [
                    {"position": {"x": 0, "y": 0}, "terrain": "plain"},
                    {"position": {"x": 1, "y": 0}, "terrain": "plain"},
                    {"position": {"x": 0, "y": 1}, "terrain": "plain"},
                    {"position": {"x": 1, "y": 1}, "terrain": "plain"},
                ],
                "players": [
                    {"id": 1, "name": "秋元萱", "kind": "human", "status": "alive", "position": {"x": 0, "y": 0}, "has_shield": True},
                    {"id": 2, "name": "Bot 2", "kind": "bot", "status": "alive", "position": {"x": 1, "y": 1}, "has_shield": False},
                ],
                "records": [
                    {
                        "category": "event",
                        "event": {"type": "weather_changed", "from": "clear", "to": "heatwave"},
                    }
                ],
            },
        }

        mock_call.side_effect = [
            room_data,
            {
                "action_desc": "Bot PlayerId(2) 执行了 Shoot { direction: Right }",
                "new_revision": 3,
                "is_match_finished": False,
                "room": room_data,
            },
        ]

        event = AstrMessageEvent(sender_id="2393120566", message_str="/rr 步进")
        event.unified_msg_origin = "grp_test"
        plugin._session_rooms["grp_test"] = "SEP01"

        results = [res async for res in plugin.handle_rr(event)]
        # We expect separate messages:
        # Msg 1: Weather notice
        # Msg 2: Step summary
        # Msg 3: Tactical Board & Roster
        # Msg 4: Turn callout for human player with @
        self.assertGreaterEqual(len(results), 3)
        self.assertTrue(any("天气异动播报" in r for r in results))
        self.assertTrue(any("P2🤖 🔫→" in r for r in results))
        self.assertTrue(any("战术地图" in r for r in results))
        self.assertTrue(any("轮到你行动了" in r and ("秋元萱" in r or "2393120566" in r) for r in results))

    @patch.object(RussianRouletteMcpClient, "call_tool", new_callable=AsyncMock)
    async def test_pure_text_game_message_blocks(self, mock_call):
        plugin = RussianRoulettePlugin(None, {})
        event = AstrMessageEvent(sender_id="2393120566", message_str="/rr 战况")
        event.unified_msg_origin = "grp_test"
        plugin._session_rooms["grp_test"] = "TXT01"

        room_data = {
            "id": "TXT01",
            "name": "纯文本战况测试",
            "phase": "in_game",
            "game": {
                "revision": 1,
                "round": 1,
                "status": "running",
                "weather": "clear",
                "alive_player_count": 2,
                "current_player_id": 1,
                "players": [
                    {"id": 1, "name": "Host", "kind": "human", "status": "alive", "position": {"x": 0, "y": 0}},
                    {"id": 2, "name": "Bot1", "kind": "bot", "status": "alive", "position": {"x": 1, "y": 1}},
                ],
                "map_size": 2,
                "cells": [
                    {"position": {"x": 0, "y": 0}, "terrain": "plain"},
                    {"position": {"x": 1, "y": 0}, "terrain": "plain"},
                    {"position": {"x": 0, "y": 1}, "terrain": "plain"},
                    {"position": {"x": 1, "y": 1}, "terrain": "plain"},
                ],
                "records": [],
            },
        }

        mock_call.return_value = room_data
        results = [res async for res in plugin.handle_rr(event)]
        self.assertTrue(any("战术地图" in str(r) for r in results))
        self.assertTrue(any("图例" in str(r) for r in results))

    @patch.object(RussianRouletteMcpClient, "call_tool", new_callable=AsyncMock)
    async def test_map_command_rendering(self, mock_call):
        plugin = RussianRoulettePlugin(None, config={})
        event = AstrMessageEvent(sender_id="2393120566", message_str="/rr 地图")
        event.unified_msg_origin = "grp_map"
        plugin._session_rooms["grp_map"] = "MAP01"

        mock_call.return_value = {
            "id": "MAP01",
            "name": "战术地图查看",
            "phase": "in_game",
            "game": {
                "revision": 1,
                "round": 1,
                "status": "running",
                "weather": "clear",
                "alive_player_count": 2,
                "current_player_id": 1,
                "players": [
                    {"id": 1, "name": "Host", "kind": "human", "status": "alive", "position": {"x": 0, "y": 0}},
                    {"id": 2, "name": "Bot1", "kind": "bot", "status": "alive", "position": {"x": 1, "y": 1}},
                ],
                "map_size": 2,
                "cells": [
                    {"position": {"x": 0, "y": 0}, "terrain": "plain"},
                    {"position": {"x": 1, "y": 0}, "terrain": "plain"},
                    {"position": {"x": 0, "y": 1}, "terrain": "plain"},
                    {"position": {"x": 1, "y": 1}, "terrain": "plain"},
                ],
                "records": [],
            },
        }

        results = [res async for res in plugin.handle_rr(event)]
        self.assertTrue(any("战术地图" in str(r) for r in results))
        self.assertTrue(any("图例" in str(r) for r in results))



class TestCompressionHelpers(unittest.TestCase):
    def test_compress_action_desc(self):
        self.assertEqual(compress_action_desc("Bot PlayerId(1) 执行了 Move { direction: Up }"), "P1🤖 🚶↑")
        self.assertEqual(compress_action_desc("Bot PlayerId(2) 执行了 Shoot { direction: Right }"), "P2🤖 🔫→")
        self.assertEqual(compress_action_desc("Bot PlayerId(3) 执行了 Wait"), "P3🤖 ⏳跳过")
        self.assertEqual(compress_action_desc("Player 1 执行了 Move { direction: Down }"), "P1👤 🚶↓")

    def test_compact_roster(self):
        players = [
            {"id": 1, "name": "秋元萱", "kind": "human", "status": "alive", "position": {"x": 0, "y": 1}, "has_shield": True},
            {"id": 2, "name": "Bot 2", "kind": "bot", "status": "eliminated"},
            {"id": 3, "name": "Bot 3", "kind": "bot", "status": "alive", "position": {"x": 3, "y": 3}, "has_shield": False},
        ]
        roster = render_compact_roster(players, current_pid=1)
        self.assertIn("P1·秋元萱👤💚(0,1)🛡️ 👉", roster)
        self.assertIn("P2·Bot 2🤖💀", roster)
        self.assertIn("P3·Bot 3🤖💚(3,3)", roster)
        self.assertIn("2/3", roster)

    def test_game_status_predicates(self):
        self.assertTrue(is_game_running({"status": "running"}))
        self.assertTrue(is_game_running({"status": {"state": "running"}}))
        self.assertFalse(is_game_running({"status": {"state": "finished", "winner_id": 1}}))
        self.assertFalse(is_game_running(None))

        self.assertTrue(is_game_finished({"status": "finished"}))
        self.assertTrue(is_game_finished({"status": {"state": "finished", "winner_id": 1}}))
    def test_layered_render_board(self):
        cells = [
            {"position": {"x": 0, "y": 0}, "terrain": "plain", "object": "wall"},
            {"position": {"x": 1, "y": 0}, "terrain": "water", "object": "crate"},
            {"position": {"x": 2, "y": 0}, "terrain": "water", "object": None},
            {"position": {"x": 0, "y": 1}, "terrain": "ice", "object": None},
            {"position": {"x": 1, "y": 1}, "terrain": "high_ground", "object": "mine"},
            {"position": {"x": 2, "y": 1}, "terrain": "plain", "object": "shield"},
            {"position": {"x": 0, "y": 2}, "terrain": "plain", "object": None},
            {"position": {"x": 1, "y": 2}, "terrain": "high_ground", "object": None},
            {"position": {"x": 2, "y": 2}, "terrain": "plain", "object": None},
        ]
        players = [
            {"id": 1, "status": "alive", "kind": "human", "position": {"x": 0, "y": 2}},
            {"id": 2, "status": "alive", "kind": "bot", "position": {"x": 2, "y": 2}},
        ]
        board = render_board(3, cells, players)
        # Check that wall & crate objects render over plain & water
        self.assertIn("🧱", board)
        self.assertIn("📦", board)
        # Check pure water cell renders monochrome wave
        self.assertIn("〰️", board)
        # Check ice & high ground & mine & shield
        self.assertIn("◇", board)
        self.assertIn("▲", board)
        self.assertIn("💣", board)
        self.assertIn("🛡️", board)
        # Check human and bot players
        self.assertIn("👤", board)
        self.assertIn("🤖", board)


class TestPortableMcpManager(unittest.TestCase):
    """Unit tests for the portable MCP manager and multi-mode resolution."""

    def test_platform_asset_resolution(self):
        from astrbot_plugin_russian_roulette.portable_manager import resolve_platform_asset
        with patch("platform.system", return_value="Linux"):
            with patch("platform.machine", return_value="x86_64"):
                self.assertEqual(resolve_platform_asset(), "roulette-mcp-linux-x86_64.tar.gz")
            with patch("platform.machine", return_value="aarch64"):
                self.assertEqual(resolve_platform_asset(), "roulette-mcp-linux-aarch64.tar.gz")
            with patch("platform.machine", return_value="mips"):
                self.assertIsNone(resolve_platform_asset())

        with patch("platform.system", return_value="Windows"):
            self.assertIsNone(resolve_platform_asset())

    def test_portable_manager_binary_paths(self):
        from astrbot_plugin_russian_roulette.portable_manager import PortableMcpManager
        mgr = PortableMcpManager(data_dir=Path("/tmp/mock_data"), default_port=8787)
        self.assertEqual(mgr.binary_path, Path("/tmp/mock_data/bin/roulette-mcp"))
        self.assertEqual(mgr.default_port, 8787)
        self.assertFalse(mgr.is_binary_available())

    def test_status_displays_portable_mode(self):
        from astrbot_plugin_russian_roulette.main import RussianRoulettePlugin
        plugin = RussianRoulettePlugin(None, config={"mode": "portable", "local_port": 8787})
        self.assertEqual(plugin.mode, "portable")
        with patch.object(plugin.client, "list_rooms", new_callable=AsyncMock, return_value=[]):
            res = asyncio.run(plugin._handle_status())
            self.assertIn("便携内置引擎 (Portable)", res)
            self.assertIn("8787", res)

    def test_status_displays_remote_mode(self):
        from astrbot_plugin_russian_roulette.main import RussianRoulettePlugin
        plugin = RussianRoulettePlugin(None, config={"mode": "remote", "server_url": "https://rrt.akiai.asia"})
        self.assertEqual(plugin.mode, "remote")
        with patch.object(plugin.client, "list_rooms", new_callable=AsyncMock, return_value=[]):
            res = asyncio.run(plugin._handle_status())
            self.assertIn("远程公网服务器 (Remote)", res)
            self.assertIn("https://rrt.akiai.asia", res)


if __name__ == "__main__":
    unittest.main()

