"""
Standalone Unit Test & Mock Suite for Russian Roulette AstrBot Plugin.
Can be executed directly with `python3 test_standalone.py`.
"""

import asyncio
import unittest
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

from mcp_client import McpError, RussianRouletteMcpClient
from renderer import (
    format_elimination_cause,
    format_weather,
    render_board,
    render_game_view,
    render_help,
    render_rooms_summary,
    render_step_result,
)
from main import DIRECTION_MAP, AstrMessageEvent, RussianRoulettePlugin


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
        self.assertIn("当前行动", view_text)
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
        self.assertIn("俄罗斯轮盘装填完毕", results[0])
        self.assertIn("Host", results[0])


if __name__ == "__main__":
    unittest.main()
