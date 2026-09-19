"""
Russian Roulette MCP Client module for AstrBot.
Communicates with the Russian Roulette backend server via MCP JSON-RPC protocol.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    aiohttp = None  # type: ignore
    HAS_AIOHTTP = False

logger = logging.getLogger("astrbot.plugin.russian_roulette")


class McpError(Exception):
    """Base exception for MCP communication and business errors."""

    def __init__(self, code: str, message: str, raw_response: Optional[dict] = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.raw_response = raw_response or {}


class RussianRouletteMcpClient:
    """
    Asynchronous MCP client to interact with Russian Roulette backend.
    Maintains revision tracking and idempotency for referee tools.
    """

    def __init__(self, server_url: str = "http://127.0.0.1:8787", mcp_endpoint: str = "/api/mcp/call"):
        self.server_url = server_url.rstrip("/")
        self.mcp_endpoint = mcp_endpoint if mcp_endpoint.startswith("/") else f"/{mcp_endpoint}"
        self._revision_cache: Dict[str, int] = {}

    def get_full_url(self) -> str:
        return f"{self.server_url}{self.mcp_endpoint}"

    def update_revision(self, room_id: str, revision: int) -> None:
        self._revision_cache[room_id.upper()] = revision

    def get_cached_revision(self, room_id: str) -> Optional[int]:
        return self._revision_cache.get(room_id.upper())

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invokes an MCP tool on the Russian Roulette backend.
        Returns parsed JSON dict of the result.
        """
        endpoint = self.get_full_url()
        payload = {
            "tool": tool_name,
            "name": tool_name,
            "arguments": arguments,
        }

        if HAS_AIOHTTP and aiohttp is not None:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        endpoint,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=10.0),
                    ) as response:
                        if response.status != 200:
                            text = await response.text()
                            raise McpError(
                                code="HTTP_ERROR",
                                message=f"HTTP {response.status}: {text}",
                            )

                        body = await response.json()
            except aiohttp.ClientConnectorError as e:
                raise McpError(
                    code="CONNECTION_ERROR",
                    message=f"无法连接到轮盘服务 ({self.server_url})，请检查后端是否已启动: {e}",
                ) from e
            except Exception as e:
                if isinstance(e, McpError):
                    raise
                raise McpError(code="NETWORK_ERROR", message=f"请求失败: {e}") from e
        else:
            def _sync_request():
                req = urllib.request.Request(
                    endpoint,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=10.0) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as e:
                    text = e.read().decode("utf-8", errors="replace")
                    raise McpError(code="HTTP_ERROR", message=f"HTTP {e.code}: {text}")
                except urllib.error.URLError as e:
                    raise McpError(
                        code="CONNECTION_ERROR",
                        message=f"无法连接到轮盘服务 ({self.server_url})，请检查后端是否已启动: {e}",
                    )
                except Exception as e:
                    if isinstance(e, McpError):
                        raise
                    raise McpError(code="NETWORK_ERROR", message=f"请求失败: {e}")

            body = await asyncio.to_thread(_sync_request)

        # Handle direct JSON response (from roulette-backend McpDispatcher)
        if isinstance(body, list):
            return body

        if isinstance(body, dict):
            # Handle standard MCP CallToolResult with "content"
            if "content" in body:
                is_error = body.get("is_error", False)
                contents = body.get("content", [])
                raw_text = ""
                for c in contents:
                    if isinstance(c, dict) and c.get("type") == "text":
                        raw_text += c.get("text", "")

                parsed_data = {}
                if raw_text:
                    try:
                        parsed_data = json.loads(raw_text)
                    except json.JSONDecodeError:
                        parsed_data = {"raw_text": raw_text}

                if is_error:
                    code = parsed_data.get("code", "MCP_TOOL_ERROR")
                    message = parsed_data.get("message", raw_text or "未知错误")
                    raise McpError(code=code, message=message, raw_response=parsed_data)

                return parsed_data

            if "error" in body:
                err = body["error"]
                if isinstance(err, dict):
                    raise McpError(
                        code=str(err.get("code", "MCP_ERROR")),
                        message=err.get("message", str(err)),
                        raw_response=body,
                    )
                raise McpError(code="MCP_ERROR", message=str(err), raw_response=body)

            return body

        return body

    # --- High-level Referee operations ---

    async def list_rooms(self, filter_phase: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists active and waiting match rooms."""
        args: Dict[str, Any] = {}
        if filter_phase:
            args["filter_phase"] = filter_phase
        result = await self.call_tool("referee_list_rooms", args)
        if isinstance(result, list):
            return result
        return result.get("rooms", [])

    async def inspect_room(self, room_id: str) -> Dict[str, Any]:
        """Inspects omniscient room snapshot and syncs revision cache."""
        room_id = room_id.upper().strip()
        result = await self.call_tool("referee_inspect_room", {"room_id": room_id})
        
        # Sync revision cache if game is active
        game = result.get("game")
        if game and "revision" in game:
            self.update_revision(room_id, int(game["revision"]))
        return result

    async def create_room(
        self,
        room_name: str,
        initial_bots: int = 3,
        password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a referee-managed game room with initial bots."""
        key = str(uuid.uuid4())
        result = await self.call_tool(
            "referee_create_room",
            {
                "room_name": room_name,
                "initial_bots": initial_bots,
                "password": password,
                "idempotency_key": key,
            },
        )
        room_id = result.get("id", "")
        if room_id:
            # New room starts at revision 0
            self.update_revision(room_id, 0)
        return result

    async def start_match(self, room_id: str, seed: Optional[int] = None) -> Dict[str, Any]:
        """Starts match in room_id."""
        room_id = room_id.upper().strip()
        # Room start requires expected_revision = 0
        key = str(uuid.uuid4())
        result = await self.call_tool(
            "referee_start_match",
            {
                "room_id": room_id,
                "seed": seed,
                "expected_revision": 0,
                "idempotency_key": key,
            },
        )
        game = result.get("game")
        if game and "revision" in game:
            self.update_revision(room_id, int(game["revision"]))
        return result

    async def step_bot(self, room_id: str) -> Dict[str, Any]:
        """Advances turn for current bot."""
        room_id = room_id.upper().strip()
        revision = await self._ensure_revision(room_id)
        key = str(uuid.uuid4())
        try:
            result = await self.call_tool(
                "referee_step_bot",
                {
                    "room_id": room_id,
                    "expected_revision": revision,
                    "idempotency_key": key,
                },
            )
        except McpError as e:
            if e.code == "REVISION_CONFLICT":
                # Refresh revision once and retry
                fresh_view = await self.inspect_room(room_id)
                fresh_rev = fresh_view.get("game", {}).get("revision")
                if fresh_rev is not None and fresh_rev != revision:
                    return await self.call_tool(
                        "referee_step_bot",
                        {
                            "room_id": room_id,
                            "expected_revision": fresh_rev,
                            "idempotency_key": str(uuid.uuid4()),
                        },
                    )
            raise

        if "new_revision" in result:
            self.update_revision(room_id, int(result["new_revision"]))
        return result

    async def force_command(
        self,
        room_id: str,
        command: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Executes a player command via referee authority."""
        room_id = room_id.upper().strip()
        revision = await self._ensure_revision(room_id)
        key = str(uuid.uuid4())
        try:
            result = await self.call_tool(
                "referee_force_command",
                {
                    "room_id": room_id,
                    "expected_revision": revision,
                    "command": command,
                    "idempotency_key": key,
                },
            )
        except McpError as e:
            if e.code == "REVISION_CONFLICT":
                fresh_view = await self.inspect_room(room_id)
                fresh_rev = fresh_view.get("game", {}).get("revision")
                if fresh_rev is not None and fresh_rev != revision:
                    return await self.call_tool(
                        "referee_force_command",
                        {
                            "room_id": room_id,
                            "expected_revision": fresh_rev,
                            "command": command,
                            "idempotency_key": str(uuid.uuid4()),
                        },
                    )
            raise

        if "new_revision" in result:
            self.update_revision(room_id, int(result["new_revision"]))
        return result

    async def dissolve_room(self, room_id: str) -> Dict[str, Any]:
        """Force dissolves room."""
        room_id = room_id.upper().strip()
        result = await self.call_tool("referee_dissolve_room", {"room_id": room_id})
        self._revision_cache.pop(room_id, None)
        return result

    async def query_rules(self) -> Dict[str, Any]:
        """Queries game rules, weather, and terrain hardness mechanics."""
        return await self.call_tool("referee_query_rules", {})

    async def _ensure_revision(self, room_id: str) -> int:
        rev = self.get_cached_revision(room_id)
        if rev is None:
            view = await self.inspect_room(room_id)
            game = view.get("game")
            if not game or "revision" not in game:
                raise McpError(code="NOT_IN_GAME", message="对局尚未开始或已结束")
            rev = int(game["revision"])
            self.update_revision(room_id, rev)
        return rev
